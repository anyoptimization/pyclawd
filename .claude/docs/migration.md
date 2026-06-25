# Migrating a large framework to pyclawd — a playbook

Field-tested process for bringing a mature, pre-existing Python framework under pyclawd's quality regime with **zero behavior regression**, using a fleet of cheap AI agents whose work is verified — never trusted.

> Distilled from migrating **pymoo** (~315 `.py` files, an established scientific-Python
> framework) from *fully red* to a green `pyclawd check`: ~312 per-file commits,
> behavior proven unchanged across 80+ output checks. The spine below generalizes;
> the commands are the ones pyclawd ships today.

---

## The shape of the problem

A mature framework predates the toolchain. Typical start state:

- No `[tool.ruff]` / `[tool.mypy]` config.
- Hundreds of files unformatted; hundreds of lint errors.
- Most files missing a one-line description; docstrings in some other style (e.g. numpy).

Goal: `pyclawd check` green (format → lint → typecheck → descriptions → test), the
project's docstring convention applied, types **only** in annotations, every file
described — **without changing any runtime behavior**.

The whole job in one sentence: *define a gate, make every file pass it, and prove you
changed nothing observable.* Two of those three are mechanical. The third is the one
that bites — which is why golden baselines come **before** any edit.

---

## Phase 0 — Foundation first (do not skip)

Stand up the gate and conventions, and commit that as its own change, **before touching
a single source file**.

1. **Curate the ruff rules to the goal — do not boil the ocean.** Enabling *all* `D`
   (docstring) rules surfaces a second, much larger project: "document every public
   class/method/function/init/magic." On pymoo that was ~2559 errors, ~1800 of them the
   "document every symbol" mandate. Curate to what you actually want:
   - **D100/D104** (module/package docstrings) = the one-line-per-file convention.
   - **D2xx/D4xx** docstring *style* (mostly autofixable).
   - **ignore D101/D102/D103/D105/D107** (the per-symbol mandates) for a first pass.
   An un-passable gate gets ignored; a curated one gets cleared.

2. **Pick the project's docstring convention in `pyproject.toml`** before requiring
   anything — `[tool.ruff.lint.pydocstyle] convention = "numpy"` (or google). Existing
   docstrings then pass lint with no rewrite.

3. **Target-less quality commands** in `.pyclawd/config.py` (e.g. `["ruff", "check"]`,
   `["mypy"]` — *not* `["mypy", "pkg"]`). Each tool reads its own scope from
   `pyproject.toml` (`[tool.mypy] files=[...]`, ruff `include`/`extend-exclude`). This is
   what makes `pyclawd check <file>` work: pyclawd appends the path for single-file and
   nothing for whole-project. A hardcoded target makes `check <file>` run
   `mypy pkg <file>` → "Duplicate module", or lint the whole package per file. The
   failure is silent and confusing; get this right up front.

4. **Typecheck config:** `[tool.mypy] files=["<pkg>"]` for the whole-project default,
   plus `explicit_package_bases = true` so single-file `mypy <file>` resolves.

5. **Add `descriptions` to `check_sequence`** so the one-line-per-file code-map
   convention is gated. Scope it now via `DescriptionConfig(include=[...], exclude=[...])`
   (default is `.py`/`.pyx` only) — see Phase 4.

6. **Transition-friendly doc tooling.** If the framework renders docstrings (Sphinx etc.),
   pick a setup that renders **both** the old and new style during the migration so
   nothing breaks mid-flight. We swapped `numpydoc` → `sphinx.ext.napoleon` with both
   `napoleon_numpy_docstring` and `napoleon_google_docstring` enabled, rebuilt docs to
   confirm, and flipped the old one off only at the very end.

7. **Write the convention down** (`.claude/CLAUDE.md`): docstring style, types in
   annotations only, one-line-per-file. The fleet reads this.

After Phase 0 the gate is *defined*. Everything else is making files pass it.

---

## Phase 1 — Baseline behavior with `golden`

The quality gate proves code is **clean**, never that behavior is **unchanged**. Close
that gap with the shipped golden oracle **on the known-good tree, before editing**.

1. Add a `GoldenConfig` to `.pyclawd/config.py` (`baseline_dir`, `marker`, `precision`,
   `rtol`, `atol`; defaults: `tests/golden`, marker `golden`, `precision=10`,
   `rtol=1e-9`, `atol=1e-12`).
2. Write golden tests over the framework's observable surface — algorithm results,
   problem evaluations, indicators, decomposition, sorting — by tagging each test
   `@pytest.mark.golden` and **returning the value to snapshot** (the pytest plugin
   captures the return value and compares it against the committed baseline):

   ```python
   @pytest.mark.golden
   @pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
   def test_minimize(problem):
       result = minimize(get_problem(problem), seed=42)
       return result.F          # return a dict to snapshot several values at once
   ```
   Always pass explicit `ids=` on parametrized goldens (index-based ids silently re-map
   baselines). The plugin auto-registers (pytest11 entry point), so this works in a bare
   pytest repo with zero pyclawd references.
3. **Record and commit the baselines on the clean tree:**

   ```bash
   pyclawd golden update        # record baselines (a human blesses; or `pytest --golden-update`)
   git diff tests/golden        # review the captured values
   git commit                   # the committed baseline IS the behavior contract
   ```

The migration is now **correct iff `pyclawd golden` stays green** — no stash-juggling,
no hand-rolled diff. The committed baseline means any future drift fails in CI forever and
`git blame` shows when a number moved.

> Prove the oracle bites: keep a meta-test that plants a regression and asserts golden
> catches it. A passing golden suite that can't fail proves nothing.

---

## Phase 2 — Fleet migration, module by module

- **A cheap model does ~90% of it.** Most files need only a one-line docstring +
  `ruff format`. Use the small/fast tier for editing; reserve judgment for the
  orchestrator's *verification* step, not the editing step.
- **Amortize agent context.** One file per agent wastes the ~20k startup overhead. Hand
  each agent **5–10 files** (or a group file to read) — ~3× cheaper per file. Per-file
  *commits* stay; only the *agents* batch.
- **Per-file contract** each agent follows:
  1. add a one-line module description (for `__init__.py`, describe the package);
  2. migrate docstrings to the target style — **types only in annotations**;
  3. fix lint **behavior-preservingly** — a bare `# noqa: <CODE>` for an *intentional*
     false positive (numpy `== None` elementwise, the idiomatic `I` index, an intentional
     bare `except`). **Never change logic/control-flow/API; never delete code with side
     effects;** prefer `# noqa` over a clever rewrite;
  4. add type annotations to satisfy mypy (annotations are runtime-neutral);
  5. format;
  6. **keep edits comment-minimal — no change-narration** (the *why* goes in the commit);
  7. self-check `pyclawd check <file> --skip test` → quality green. (Per-file `check`
     skips `test` because `test` runs the whole suite, never file-scoped; while the repo
     is mid-migration, also `--skip format-check --skip lint` to reach typecheck/
     descriptions on not-yet-migrated neighbors.)

---

## Phase 3 — Verify every batch (non-negotiable)

Agent self-reports are not evidence. On pymoo ~3–4% of agents claimed PASS while the gate
actually failed (over-narrow type annotations). The gate is the authority.

1. **Re-run the gate yourself, per file:** `pyclawd check <file>`. Never commit on an
   agent's word.
2. **Prove behavior unchanged:** `pyclawd golden`. Green = every numeric surface matches
   the committed baseline within tolerance. This is what caught the one real pymoo
   regression: an agent "fixed" `X[:, J]` → `X[:, np.array(J)]`, which crashes on an empty
   index array — *gate-green, runtime-broken.* Only the oracle saw it.
3. **Periodically run the full suite** (`pyclawd test run`) — its absolute-value
   assertions catch what a sampled golden misses.
4. **Commit only verified files, one file per commit** → clean, bisectable history if
   anything ever surfaces later.

---

## Phase 4 — Scope decisions

Not every file should be restyled, and not every file can carry a docstring.

- **Vendored / 3rd-party code:** don't touch the logic. Scope ruff and mypy to your own
  package (`extend-exclude`, `files=`). If the descriptions check still flags it, exclude
  it rather than editing it.
- **Non-source files** (`.f90`, `.dat`, fixtures, data): they can't carry a Python
  docstring. Exclude them from the descriptions gate with
  `DescriptionConfig(exclude=[...])` (the default already limits to `.py`/`.pyx`, but tune
  `include`/`exclude` for the repo's layout).
- The three exclusion knobs to keep aligned: `DescriptionConfig.exclude` (the code-map
  gate), ruff `extend-exclude` (lint/format), mypy `files=` (types).

---

## Phase 5 — Final regression evaluation (two explicit bars)

Distinguish them and hold every numeric surface to the strong one.

- **"Same numbers" (strong):** `pyclawd golden` green across the full matrix — algorithms ×
  problems, problem evaluations, operators (via algorithms), indicators, decomposition,
  non-dominated sorting. Byte-identical via the fast-path hash, or within `rtol`/`atol`
  for cross-platform float jitter. (We ran 80+ such checks, 0 unexplained diffs.)
- **"It runs" (only where there is no number to compare):** plots, IO, parallel backends,
  example scripts, docs notebooks. Run them. For docs, force re-execution
  (`pyclawd docs build` with re-exec) — a code-keyed cache would otherwise hide a
  source-level regression.

Everything that emits a number → prove it's the same number. Non-numeric surfaces → prove
they still run.

---

## Hard-won lessons (the portable ones)

1. **The gate proves "clean," not "unchanged."** Pair `pyclawd check` with `pyclawd golden`
   from day one — record baselines on the known-good tree *before* the first edit.
2. **Foundation before files.** Define the gate + conventions (Phase 0) and commit it,
   then make files pass. Editing source against a moving gate is chaos.
3. **Curate rules to the goal.** A gate nobody can pass gets disabled. Enable the rules
   that encode your actual convention; defer the rest.
4. **Cheap fleet + relentless verification beats careful-but-slow** — *if and only if*
   verification is real (gate + golden + tests), never the agent's self-report.
5. **Per-file commits.** Cheap insurance, huge payoff for trust and bisection.
6. **Behavior-preserving lint only.** The danger isn't docstrings or formatting — it's an
   over-eager "lint fix" that changes semantics. Prefer `# noqa`; golden is what saves you
   when an agent gets clever anyway.

---

## Where to go next

| Need | Reference |
|---|---|
| Prove behavior unchanged (the oracle) | `pyclawd-golden` skill · `examples/golden_demo/` |
| Lint / format / typecheck / `check` gate | `pyclawd-quality` skill |
| Tiered tests, the fix-loop | `pyclawd-tests` skill |
| Mental model + full doctrine | `pyclawd` (umbrella) · `AGENTS.md` |
