---
name: pyclawd-adopt
description: Adopting pyclawd into an EXISTING (often large/legacy) Python repo and driving it from a red codebase to a green `pyclawd check` with ZERO behavior regression. Bootstrap with `pyclawd new` (adopt mode — no name, run inside the repo → writes .pyclawd/config.py + AGENTS.md/CLAUDE.md + installs skills), then follow the field-tested playbook: curate the quality gate so it is actually passable (don't enable every docstring rule; pick the project's docstring convention), pin the existing test suite then lay targeted golden baselines for what it doesn't cover BEFORE editing any source, then fix in small verified batches with per-file commits. Triggers — "adopt pyclawd", "onboard this repo to pyclawd", "get this existing/legacy repo ready for pyclawd", "make this red codebase pass check", "bring this framework under pyclawd".
when_to_use: First-time onboarding of an existing/legacy repo — standing up the gate, getting a red codebase to green, or planning a large mechanical cleanup that must not change behavior. The onboarding counterpart to pyclawd-upgrade (which is for AFTER a pyclawd version bump, not first adoption).
---

# pyclawd-adopt

Bring a mature, pre-existing Python repo under pyclawd's quality regime with **zero
behavior regression**. The job in one sentence: *define a gate, make every file pass
it, and prove you changed nothing observable.* Two of those three are mechanical
(formatting, docstrings, annotations). The third — proving behavior unchanged — is the
one that bites, which is why you **pin an oracle before any edit**: the repo's existing
test suite first, then targeted golden baselines for the outputs it doesn't cover.

This is the onboarding skill. For the *different* migration after pyclawd itself is
upgraded (config version drift), use **pyclawd-upgrade** instead — that is not adoption.

> Field-tested on **pymoo** (~315 `.py` files, an established scientific-Python
> framework) taken from *fully red* to a green `pyclawd check`: ~312 per-file commits,
> behavior proven unchanged across 80+ output checks, 0 unexplained diffs. The steps
> below are written generically — they apply to any repo; pymoo is just the worked
> example for the numbers.

## The shape of the problem

A mature framework predates the toolchain. Typical start state: no `[tool.ruff]` /
`[tool.mypy]` config; hundreds of files unformatted with hundreds of lint errors; most
files missing a one-line description; docstrings in some other style (e.g. numpy). The
goal: `pyclawd check` green (format → lint → typecheck → descriptions → test), the
project's docstring convention applied, types **only** in annotations, every file
described — **without changing any runtime behavior**.

---

## Step 0 — bootstrap with `pyclawd new` (adopt mode)

Run inside the existing repo with **no positional name** — that selects adopt mode.
**Run it first** (start with `--dry-run`) to get the lay of the land: adopt mode now
**inspects the repo and tells you what it found and what is missing** before you write
anything.

```bash
pyclawd new --dry-run     # preview exactly what would be written (nothing is) + the readiness report
pyclawd new               # interactive at a TTY; pick conda env / tests dir / docs
pyclawd new --yes         # non-interactive: accept inferred defaults (agents/CI)
```

Adopt mode is layout-aware. It **detects the project layout** — a flat layout (package
directory at the repo root, e.g. `pysamoo/`) versus a `src/` layout — and sets `src_dir`
accordingly instead of hardcoding `src`. It **infers `root_markers`** from what actually
exists (`setup.py` / `setup.cfg` / `pyproject.toml` / the package `__init__.py`), so the
written config matches the repo as-is.

It then prints a **Phase-0 readiness report**: what it detected (layout, package,
`src_dir`, markers) and what is **missing** for `pyclawd check` to run — e.g. "no
`pyproject.toml`" or "no `[tool.ruff]` / `[tool.mypy]` / pydocstyle convention" — pointing
back at this skill. Read that report first; it is your checklist for Phase 0 below.

This writes `./.pyclawd/config.py` (a `Project` with `QualityConfig` / `TestConfig` /
`DoctorConfig`), lands `AGENTS.md` + `CLAUDE.md` (never clobbers existing ones), and
installs the bundled pyclawd skills into user scope. The project name comes from the
current directory; `--pkg`, `--conda-env`, `--tests-dir`, `--docs`, `--compile` set the
rest (`--no-agent` / `--no-skills` opt out). It refuses to overwrite an existing config
unless `--force`. Verify with `pyclawd root` (resolves the repo) and `pyclawd doctor`
(env sanity — see **pyclawd-doctor** if it FAILs).

After this the gate exists but is almost certainly **red** (the readiness report tells you
why). Everything below makes it green without moving a number.

---

## Phase 0 — make the gate passable (before touching any source file)

Stand up the gate and conventions and **commit that as its own change** before editing a
single source file. Editing source against a moving gate is chaos.

**Fast start when the repo has no tool config.** If the readiness report flagged a missing
`pyproject.toml` or absent `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest]` sections, run:

```bash
pyclawd new --scaffold-pyproject     # drop a STARTER ruff/mypy/pytest config
```

This writes a starter `[tool.ruff]` / `[tool.ruff.lint.pydocstyle]` / `[tool.mypy]` /
`[tool.pytest.ini_options]` config — creating `pyproject.toml` if it is absent, and
otherwise **appending only the missing sections, never clobbering existing ones**. It is a
**runnable starting point, not the finished gate**: it replaces the blank page, but you
still **curate** it per the steps below — which `D` rules you actually want and which
docstring convention the project uses. Skip the flag and write the sections by hand if you
prefer; either way the curation in steps 1–2 is the agent's job, not the flag's.

1. **Curate the ruff `D` rules to your goal — do not boil the ocean.** Enabling *all*
   docstring (`D`) rules surfaces a second, much larger project: "document every public
   class / method / function / `__init__` / magic." On pymoo that was ~2559 errors,
   ~1800 of them this per-symbol mandate. Curate to what you actually want for a first
   pass:
   - keep **D100 / D104** (module / package docstrings) — these encode the
     one-line-per-file convention;
   - keep **D2xx / D4xx** (docstring *style* — mostly autofixable);
   - **ignore D101 / D102 / D103 / D105 / D107** (the per-symbol mandates) for now.

   An un-passable gate gets disabled; a curated one gets cleared. You can tighten later.

2. **Pick the project's docstring convention in `pyproject.toml`** before requiring
   anything: `[tool.ruff.lint.pydocstyle] convention = "numpy"` (or `"google"`). Existing
   docstrings then pass lint with no rewrite — you migrate them on your own schedule, not
   the gate's.

3. **Use target-less quality commands** in `.pyclawd/config.py` — `["ruff", "check"]`,
   `["mypy"]`, **not** `["mypy", "pkg"]`. Each tool reads its own scope from
   `pyproject.toml` (mypy `files=[...]`, ruff `include` / `extend-exclude`). This is what
   makes `pyclawd check <file>` work: pyclawd appends the path for single-file mode and
   nothing for the whole project. A hardcoded target makes `check <file>` run
   `mypy pkg <file>` → "Duplicate module", or lint the whole package per file — a silent,
   confusing failure. Get this right up front. (`pyclawd new` already emits target-less
   commands; preserve that.)

4. **Typecheck config:** `[tool.mypy] files = ["<pkg>"]` for the whole-project default,
   plus `explicit_package_bases = true` so single-file `mypy <file>` resolves.

5. **Add `descriptions` to `check_sequence`** so the one-line-per-file code-map convention
   is gated, and scope it with `DescriptionConfig(include=[...], exclude=[...])` (default:
   `.py` / `.pyx` only) — see *Scope decisions* below.

6. **Write the convention down** in `AGENTS.md` / `CLAUDE.md`: docstring style, types in
   annotations only, one-line-per-file. The fleet (and future you) reads this.

7. **Transition-friendly doc tooling (if the repo renders docstrings).** Pick a setup
   that renders **both** the old and new style during the migration so nothing breaks
   mid-flight (e.g. swap `numpydoc` → `sphinx.ext.napoleon` with both
   `napoleon_numpy_docstring` and `napoleon_google_docstring` on; flip the old one off
   only at the very end).

Commit Phase 0 on its own. The gate is now *defined*; everything else is making files
pass it.

---

## Pin an oracle before any edit — tests first, golden for the gaps

Adoption edits are mechanical (formatting, docstrings, annotations, curated lint fixes) —
by definition they must not change behavior. You need an oracle that *proves* that, pinned
on the known-good tree **before** editing. Use two layers, cheapest first.

**1. Primary oracle — the existing test suite.** A mature repo already ships tests; they
encode its behavior and what matters. Pin them green on the untouched tree and keep them
green after every batch — for mechanical changes, an identically-passing suite is your
first proof nothing moved.

```bash
pyclawd test run      # (or `all`) on the known-good tree — this is your floor
```

If the suite is red *before* you start, fix the environment first (see **pyclawd-doctor**) —
never start a migration on a suite you can't trust.

**2. Targeted supplement — golden.** Tests prove pass/fail, not *same value*, and their
coverage is uneven. The quality gate has the same blind spot: it proves code **clean**, never
behavior **unchanged** — a "clean" lint fix can still move a number. Add golden baselines
only for the observable outputs the tests **don't** already lock — exact numeric results,
serialized artifacts, anything under-tested — and especially **before a broad `ruff --fix`**
(the one cleanup step that can actually change behavior). Don't snapshot everything; pick the
handful — for a numeric framework, the matrix — of outputs that genuinely characterize
behavior. (On pymoo, pass/fail tests left most exact numbers unlocked, so golden carried
80+ output checks; a well-tested app may need only a few.) **Read the `pyclawd-golden` skill
for the full mechanics**; the adoption-critical points:

1. Add a `GoldenConfig` to `.pyclawd/config.py` (`baseline_dir`, `marker`, `precision`,
   `rtol`, `atol`).
2. Write golden tests over the **observable surface the tests don't already pin** —
   algorithm results, problem evaluations, indicators, sorting, decomposition — by tagging
   each `@pytest.mark.golden` and **`return`ing the value to snapshot**:

   ```python
   @pytest.mark.golden
   @pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
   def test_minimize(problem):
       res = minimize(get_problem(problem), seed=42)
       return res.F          # return a dict to snapshot several values at once
   ```
   Always pass explicit `ids=` on parametrized goldens (index-based ids silently re-map
   baselines).
3. **Record and commit the baselines on the clean tree:**

   ```bash
   pyclawd golden update     # record baselines (a human blesses; or `pytest --golden-update`)
   git diff tests/golden     # review the captured values — the committed baseline IS the contract
   git commit
   ```
4. **Make golden its own tier** so it stays out of the unit suite — exclude the marker in
   every `TestConfig` tier (e.g. `"default": "not slow and not golden"`) and run
   `pyclawd golden` as a separate gate.
5. **Prove the oracle bites:** keep a meta-test that plants a regression and asserts
   golden catches it. A passing golden suite that *can't* fail proves nothing.

**The mini-recipe:** identify the 3–5 outputs that matter → snapshot → bless once on the
clean tree → grind.

The migration is now **correct iff the existing tests stay green *and* `pyclawd golden`
stays green** — no stash-juggling, no hand-rolled diffs, and any future drift fails in CI
forever with `git blame` showing when a number moved.

---

## The grind — fix in small, verified batches

Now make files pass the gate. Most files need only a one-line module description +
`ruff format`. Work in small batches and **verify every batch — agent self-reports are
not evidence** (on pymoo ~3–4% of agents claimed PASS while the gate actually failed).

**Per-file contract:**
1. add a one-line module description (for `__init__.py`, describe the package);
2. migrate docstrings to the chosen style — **types only in annotations**;
3. fix lint **behavior-preservingly** — a bare `# noqa: <CODE>` for an *intentional*
   false positive (numpy `== None` elementwise, an idiomatic index name, an intentional
   bare `except`). **Never change logic / control-flow / API; never delete code with side
   effects.** Prefer `# noqa` over a clever rewrite;
4. add type annotations to satisfy mypy (annotations are runtime-neutral);
5. format; keep edits comment-minimal — no change-narration (the *why* goes in the commit).

**Verify each file / batch yourself:**
```bash
pyclawd check <file>          # re-run the gate per file — never commit on an agent's word
pyclawd golden               # prove behavior unchanged: every numeric surface matches baseline
pyclawd test run             # periodically — absolute-value asserts catch what sampled golden misses
```
The fix-loop (`pyclawd test failures` → `pyclawd test fix` → `pyclawd test run`) is in
the `pyclawd` skill's `references/tests.md`. When the repo is mid-migration, a per-file
`pyclawd check <file> --skip test` (and, against not-yet-migrated neighbors,
`--skip format-check --skip lint`) lets you reach typecheck/descriptions cleanly.

`pyclawd golden` is exactly what caught the one real pymoo regression: an agent "fixed"
`X[:, J]` → `X[:, np.array(J)]`, which crashes on an empty index array — *gate-green,
runtime-broken.* Only the output oracle saw it.

**Commit per file (or per small batch).** Cheap insurance, huge payoff: clean, bisectable
history if anything surfaces later. **Agents compare, humans bless** — re-run
`pyclawd golden` to gate; a human runs `pyclawd golden update` and commits the reviewed
baseline diff. **Never wire `golden update` into an autonomous loop** (it would launder
regressions into baselines).

---

## Scope decisions — not every file should be touched

- **Vendored / 3rd-party code:** don't touch the logic. Scope ruff and mypy to your own
  package (`extend-exclude`, `files=`). If the descriptions check still flags it, exclude
  it rather than editing it.
- **Non-source files** (`.f90`, `.dat`, fixtures, data) can't carry a Python docstring —
  exclude them from the descriptions gate via `DescriptionConfig(exclude=[...])`.
- Keep the **three exclusion knobs aligned:** `DescriptionConfig.exclude` (code-map gate),
  ruff `extend-exclude` (lint/format), mypy `files=` (types).

## The two final bars

Distinguish them and hold every surface to the right one:

- **"Same numbers" (strong):** `pyclawd golden` green across the full matrix — algorithms ×
  problems, evaluations, operators, indicators, decomposition, sorting. Everything that
  emits a number must prove it's the *same* number.
- **"It runs" (only where there is no number to compare):** plots, IO, parallel backends,
  example scripts, docs notebooks. Run them. For docs, force re-execution
  (`pyclawd docs build`) — a code-keyed cache would otherwise hide a source-level
  regression.

## How you know adoption is done

- `pyclawd check` green (format-check → lint → typecheck → descriptions → test).
- `pyclawd golden` green across the full observable matrix.
- `pyclawd doctor` exits 0; `pyclawd ls --missing` is empty (every file described).

---

## Where to go next

| Need | Where |
|---|---|
| Prove behavior unchanged — record/compare/bless baselines (the oracle) | **pyclawd-golden** |
| The `check` gate: target-less cmds, docstring convention, single-file scoping | the `pyclawd` skill's `references/quality.md` |
| Tiered tests + the fix-loop | the `pyclawd` skill's `references/tests.md` |
| Env looks broken — wrong interpreter, mass import failures (do this first) | **pyclawd-doctor** |
| Migrate AFTER a pyclawd **version bump** (not first adoption — different job) | **pyclawd-upgrade** |
| Mental model + full doctrine | **pyclawd** (router) · `AGENTS.md` |
