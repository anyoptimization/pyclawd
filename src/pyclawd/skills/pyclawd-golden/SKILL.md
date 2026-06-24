---
name: pyclawd-golden
description: Prove behavior is *unchanged* across a refactor or migration with pyclawd's golden behavior-regression oracle — committed snapshot baselines compared with a per-snapshot tolerance. Covers the record→review→commit bless workflow, why the hash is only a fast path (tolerance is the gate), parametrized-test keys, and reading a golden failure. Use when refactoring, doing a batch/fleet migration, or when "did this change any numbers?" must be answered.
when_to_use: Refactoring or migrating code that must not change observable outputs, verifying a fleet of agent edits, adding a regression baseline, or a golden test failed and you need to tell a real regression from an intended change. The complement to `pyclawd-quality` — quality proves *clean*, golden proves *unchanged*.
---

# pyclawd-golden

The static gate (`pyclawd check`: format/lint/typecheck/test) proves code is
**clean**. It cannot prove behavior is **unchanged** — a "clean" lint fix can
still change a number. `golden` closes that gap: it snapshots an observable value
to a **committed baseline** and fails when a future run drifts from it. Because the
baseline is in git, any later behavior change fails in CI forever, and `git blame`
shows exactly when and how a number moved.

Golden is **opt-in per project** (a `GoldenConfig`); like every pyclawd group, if
it is unconfigured the command self-reports and exits `2` instead of crashing.

---

## When to reach for golden

- **Refactors / migrations that must not change outputs** — the canonical case.
  (Motivating story: a fleet refactor of pymoo where one static-clean edit,
  `X[:, J]` → `X[:, np.array(J)]`, broke runtime; only an output compare caught it.)
- **Fleet/batch agent edits** — verify each agent changed *style*, not *behavior*.
- **Locking in a known-good result** before touching the code around it.

Not for: asserting *new* expected values (that's an ordinary `assert`); golden
asserts *sameness* against a recorded baseline.

---

## The mental model — the hash is an optimization, tolerance is the gate

This is the one thing to internalize. A golden snapshot stores both an inline
**value** and a **hash**:

1. **Fast path** — hash the new value's canonical (rounded) form; if it equals the
   stored hash, pass immediately.
2. **Fallback** — on a hash miss, compare the new value to the stored value with a
   **per-snapshot tolerance** (`rtol`/`atol`). Within tolerance → still passes.
   Outside → fails with a `baseline → actual` diff.

So a hash mismatch **never fails a test on its own.** That is deliberate: it means
committed baselines survive cross-platform float jitter (BLAS ±1 ULP) instead of
flaking on it. Rounding (`precision`) only stabilizes the fast-path hash; the
*semantic* gate is the tolerance.

The inline value is also what makes a `git diff` of a baseline readable
(`0.925 → 0.522`) — the whole reason baselines are committed.

---

## Writing a golden test

```python
@pytest.mark.golden
@pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
def test_minimize(golden, problem):
    result = minimize(get_problem(problem), seed=42)
    golden(result.F, label="F", rtol=1e-9)      # objective vector
    golden(result.indicator, label="indicator") # scalar — stored inline
```

- The `golden` fixture auto-keys each snapshot from the test node id. For a
  parametrized test the id already carries the case (`test_minimize[sphere]`), so
  every case gets its own baseline entry.
- **Multiple snapshots in one test need a distinct `label=`.**
- Overrides per call: `label=`, `precision=`, `rtol=`, `atol=`.
- Scalars/small data are stored **inline** (readable diffs); big arrays use a
  hash + a sidecar artifact.

### Parametrized tests — use stable `ids=`

The snapshot key comes from the param id. If you parametrize over **objects
without `ids=`**, pytest names them by index (`algo0`, `algo1`) — and inserting
one case silently re-maps every key, so you'd compare the wrong baseline. **Always
pass explicit `ids=`** for golden parametrized tests; the fixture warns on
index-based auto-ids.

---

## The workflow — record, review, commit (the bless)

```bash
pyclawd golden                 # GATE: compare against committed baselines (the default)
pyclawd golden update          # RECORD/bless baselines after an *intended* change
pyclawd golden update -k de    # bless only matching cases (merges — never wipes others)
git diff <baseline-dir>        # REVIEW the value changes — this diff is the record
git commit                     # commit the reviewed baselines
pyclawd golden status          # list snapshots; flag orphaned/missing baselines
pyclawd golden prune           # remove baselines whose tests no longer exist
```

**Blessing is a human act.** `golden update` records new baselines; a human
reviews the `git diff` and commits it. The PR diff of the baseline *is* the
record of what behavior changed and why.

> **Never wire `golden update` into an autonomous loop's self-gate.** An agent
> cannot tell an intended behavior change from a bug, so an auto-blessing loop
> launders regressions into baselines. Agents run `pyclawd golden` (compare); a
> human runs `update`.

`golden update -k` and `prune` are separate on purpose: a filtered update only
touches matched cases (so running a subset never wipes the rest), and removing
orphaned baselines is an explicit step, never inferred from "didn't run".

---

## Reading a golden failure

```
GoldenError: golden: test_minimize[sphere]::F
  value drifted beyond tolerance (rtol=1e-09, atol=1e-12)
  baseline: [0.925444, 0.001444]
  actual:   [0.522729, 0.076729]
```

The diff tells you *what* moved, not just *that* it did. Then decide:

- **Unintended (a regression):** fix the code — do **not** bless. The golden goes
  green on its own once behavior is restored.
- **Intended (a real behavior change):** `pyclawd golden update`, review the diff,
  commit. The history now records the change.

If a baseline is missing (`no baseline for …`), you never recorded it — run
`pyclawd golden update` and commit first.

---

## Doctrine for a migration / batch run

1. **Record baselines on the known-good tree first**, and commit them. Now the
   migration is correct iff golden stays green — no stash-juggling.
2. **Agents compare, humans bless.** Re-run `pyclawd golden` per file/batch; never
   trust an agent's self-report.
3. **Prove the oracle bites.** Keep a meta-test that plants a regression and
   asserts golden catches it — a *passing* golden test alone proves nothing.
4. **Numbers → prove same number; non-numeric (plots/IO) → prove it still runs.**

---

## Where to go next

| Need | Skill |
|---|---|
| Lint / format / typecheck / the `check` gate | `pyclawd-quality` |
| Running tiered tests, the fix-loop | `pyclawd-tests` |
| Env looks wrong, imports fail | `pyclawd-doctor` |
| Mental model + full doctrine | `pyclawd` (umbrella) · `AGENTS.md` |
