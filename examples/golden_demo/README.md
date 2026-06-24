# golden — worked example (the 5a spec artifact)

A runnable, end-to-end demonstration of pyclawd's **behavior-regression oracle**.
The static gate (`pyclawd check`: format/lint/typecheck/test) proves code is
*clean*; `golden` proves behavior is *unchanged*. This directory is the concrete
artifact the council review required before building the full feature — a real
test, the real baseline file it produces, and a real failure-and-fix transcript.

## The files

| File | Role |
|---|---|
| `../../src/pyclawd/golden.py` | the engine (canonicalize → hash → tolerant compare; record/gate) |
| `conftest.py` | wires the `golden` fixture + `@pytest.mark.golden` marker (future: a pyclawd pytest plugin) |
| `test_optimize.py` | a real golden test — snapshots a seeded "optimizer" objective vector |
| `golden/test_optimize.json` | the **committed baseline** — inline values + fast-path hashes |
| `test_meta.py` | meta-tests proving the oracle *bites* (catches planted drift) |

## The workflow

**1. Gate (the default — compare against committed baselines):**

```
pyclawd python -m pytest examples/golden_demo -m golden
```

**2. Bless (record baselines after an _intentional_ behavior change):**

```
PYCLAWD_GOLDEN_UPDATE=1 pyclawd python -m pytest examples/golden_demo -m golden
git diff examples/golden_demo/golden/   # review the value changes, then commit
```

Blessing is a **human-run, human-reviewed, human-committed** act — never wired
into an autonomous loop's self-gate. The PR diff of the baseline file *is* the
record of what behavior changed and when (`git blame`).

## What a committed baseline looks like

```jsonc
{
  "test_minimize[sphere]::F":         { "hash": "sha256:82b1…", "value": [0.925444, 0.001444] },
  "test_minimize[sphere]::indicator": { "hash": "sha256:af5d…", "value": 0.9254451266 },
  "test_scalar_metric":               { "hash": "sha256:a4ff…", "value": 0.4653799416 }
}
```

The **inline `value`** is what makes a `git diff` read `0.925 → 0.522`; the
**`hash`** is only a fast path in front of the tolerant comparison.

## The failure transcript (regression caught)

Inject a "clean" edit that changes behavior (here: `seed=42 → seed=43`) and the
gate fails with **what** drifted, not just that it did:

```
pyclawd.golden.GoldenError: golden: test_minimize[sphere]::F
  value drifted beyond tolerance (rtol=1e-09, atol=1e-12)
  baseline: [0.925444, 0.001444]
  actual:   [0.522729, 0.076729]
```

Revert the edit → the gate is green again. No baseline was touched.

## Which design questions this resolves

The council flagged these as must-answer-before-building. The example answers
each concretely:

- **"Exact vs tolerant is a contradiction."** It isn't — they're sequenced. The
  **hash is demoted to an optimization**; a hash miss falls back to a tolerant
  value compare (`test_meta.py::test_subtolerance_jitter_passes_via_value_fallback`).
  This is what stops committed baselines flaking on cross-platform BLAS jitter.
- **"Rounding vs tolerance — which is the gate?"** Rounding (`precision`) only
  stabilizes the fast-path hash; **tolerance (`rtol`/`atol`) is the semantic
  gate**, stored *per snapshot* in the entry, not centrally.
- **"Hash tells you THAT not WHAT changed."** Inline values give a real
  `baseline → actual` diff on failure (see the transcript above).
- **"No silent pickle."** An unserializable value raises loudly
  (`test_meta.py::test_unserializable_value_is_loud_not_pickled`).
- **"A passing golden test doesn't prove it tests anything."** The meta-tests
  plant a regression and assert the oracle catches it.
- **Parametrized keys** come from the pytest node id (`test_minimize[sphere]`),
  one stable per-case baseline entry; the fixture guards against unstable
  index-based auto-ids.

## Not yet exercised here (the designed extensions)

This pure-Python core covers the **inline-value path** (scalars, small vectors —
the readable, common case). The full feature adds the **sidecar path** for big
arrays/frames (`.npz`/`.csv` + `np.allclose`/`assert_frame_equal`) and the
`pyclawd golden` / `update -k` / `status` / `prune` command layer — the council's
recommended Story 5b, built on top of this validated 5a core.
