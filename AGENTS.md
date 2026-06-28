# AGENTS.md — working in a pyclawd project

This is the agent doctrine for **any** project that adopts **pyclawd** — a
config-driven Python dev-task CLI: one file (`.pyclawd/config.py`) describes the
project and `pyclawd <verb>` is the single contract for every task, so humans and
AI agents drive it the same way. (pyclawd dogfoods pyclawd, so this is also the
doctrine for working on pyclawd's own source — see `.claude/CLAUDE.md` for the
extras specific to developing the toolkit itself.)

This file is the **operational contract** — the commands, the boundaries, the
non-negotiables. It is always in your context, so follow it. For the *why* behind
the rules — the testing taxonomy, typing, packaging, and docstring doctrine, with
examples — invoke the **`pyclawd` skill** (Claude Code; installed user-scope and
shared across every pyclawd project). In short: **AGENTS.md is what to run; the
skill is how to write good code.**

## Critical rule — how to run Python

**ALWAYS run Python through `pyclawd python`. NEVER call bare `python` / `python -c`.**

```bash
pyclawd python script.py          # run a script
pyclawd python -m pytest ...      # run a module
pyclawd python -c "import mypkg"  # quick check
```

`pyclawd python` runs in the project's configured env (the `conda_env` in
`.pyclawd/config.py`, or whatever env pyclawd is installed into) with the repo root
on `PYTHONPATH`. Bare `python` misses the env and the in-tree source.

## Commands — quick reference

| Task | Command |
|---|---|
| Resolved config (what each command runs) | `pyclawd config` |
| Health-check the dev env | `pyclawd doctor` |
| Run Python in the env | `pyclawd python <file>` · `-m <mod>` · `-c <code>` |
| Fast smoke tests (<30s, xdist) | `pyclawd test fast` |
| Default test gate (not `slow`) | `pyclawd test run` |
| Everything incl. `slow` | `pyclawd test all` |
| Select tests | `pyclawd test -k <kw>` · `pyclawd test tests/path::node` |
| Fix-loop | `pyclawd test failures` → `pyclawd test fix` → `pyclawd test run` |
| Slowest tests | `pyclawd test timings [--top N] [--slow-threshold S]` (S = list tests slower than S seconds — `slow`-marker candidates) |
| Coverage | `pyclawd coverage [--check] [--html]` |
| Prove behavior unchanged | `pyclawd golden [-k EXPR]` · `golden update [-k EXPR]` · `status` · `prune` · `vendor <file>` (bare pytest: `@pytest.mark.golden` + `return`; bless with `pytest --golden-update`) |
| Lint / autofix | `pyclawd lint` · `pyclawd lint --fix` · `pyclawd lint <file...>` |
| Format / check | `pyclawd format` · `pyclawd format --check` · `pyclawd format <file...>` |
| Type-check | `pyclawd typecheck` · `pyclawd typecheck <file...>` |
| **Aggregate quality gate** | `pyclawd check` · `--fix` · `--skip <verb>` · `--fail-fast` · `--changed` · `--json` · `pyclawd check <file...>` |
| Build / dist / clean | `pyclawd compile` · `pyclawd dist` · `pyclawd clean [--ext]` |
| Docs (if configured) | `pyclawd docs build\|run\|render\|serve\|status\|failures\|exec <page>` |
| Code map (file → description) | `pyclawd ls [DIR]` · `pyclawd ls --missing` · `pyclawd ls --py` |
| Manage agent skills | `pyclawd skills list` · `pyclawd skills install` |
| Web diff/review dashboard (extra) | `pyclawd web serve` · `web add <path>` · `web list` · `web remove <name>` (needs `pip install 'pyclawd[web]'`) |
| Version + config drift | `pyclawd version` · `pyclawd version --json` |
| What changed (since config) | `pyclawd changelog [--since V] [--full]` |
| Repo root | `pyclawd root` |

Run `pyclawd config` first — it shows the exact command every verb resolves to and
the `PYCLAWD_*` override knobs (`PYCLAWD_CONFIG`, `PYCLAWD_DISCOVERY`,
`PYCLAWD_PYTHON`, `PYCLAWD_WORK_DIR`). To run pyclawd **without committing** a
`.pyclawd/` folder, set `PYCLAWD_DISCOVERY=".local/.pyclawd:.pyclawd"` once (a
relative pattern — safe across all repos/projects) and keep a gitignored
`<repo>/.local/.pyclawd/config.py`; walk-up finds it and `root` still resolves to
the repo. `pyclawd check` runs all quality steps (format-check → lint →
typecheck) **regardless of individual failures**, streaming output inline, then runs
**test** only if quality passed. Use `--skip <verb>` (repeatable) to omit a step,
`--fail-fast` to stop at the first failure, `--fix` to apply format+lint autofixes
in place, and `--log` to also write each step's output to a log file (CI artifacts).
Optional positional paths (e.g. `pyclawd check src/mypkg/foo.py`) scope quality
steps to specific files — this requires **target-less quality cmds** in
`.pyclawd/config.py` (e.g. `["ruff", "check"]` not `["ruff", "check", "src"]`; the
tool reads its own target from `pyproject.toml` when no paths are given). `--changed
[--against <ref>]` scopes to git-changed source files; `--json` emits a
machine-readable per-step result for orchestration. **A path-scoped run (positional
paths, `--changed`, or `--json`) is quality-only by default** — the whole-suite test
step never scopes to a file, so it is dropped unless you pass `--test`. Build/dist/
clean and docs commands only do real work when the project configures them;
otherwise they degrade gracefully (exit 2 = not configured). Override config
discovery with `--config PATH` (or the `PYCLAWD_CONFIG` env var); by default pyclawd
walks up from cwd to find `.pyclawd/config.py`.

## Test tiers

| Tier | Marker filter | When |
|---|---|---|
| `fast` | `not slow and not integration` | After every edit — <30s smoke |
| `run` (default) | `not slow` | Before opening a PR |
| `all` | _(no filter)_ | Nightly / pre-release |

Mark slow tests `@pytest.mark.slow`, tests needing live services
`@pytest.mark.integration`. Unmarked tests run in every tier — never mark a test
`fast`. The fix-loop and failure taxonomy live in the `pyclawd` skill's `references/tests.md`.

## Behavior oracle (golden)

`pyclawd check` proves code **clean** (format/lint/typecheck/test); it cannot prove
behavior **unchanged** — a clean edit can still move a number. `pyclawd golden`
closes that gap: it compares observable outputs against **committed** baselines and
fails on drift (tolerance is the gate; the stored hash is only a fast path, so
baselines survive cross-platform float jitter; values are inline so `git diff` shows
`0.925 → 0.522`). Workflow: **agents compare, humans bless** — `pyclawd golden`
gates, `pyclawd golden update [-k EXPR]` records an *intended* change (merges, never
wipes others), then a human reviews the baseline `git diff` and commits; `status`
lists snapshots, `prune` drops orphaned ones. Write a golden test by tagging it
`@pytest.mark.golden` and **`return`ing the value** to snapshot — the pytest plugin
captures the return value and compares it. It works **standalone in a bare-pytest repo
with zero pyclawd references** (no `import pyclawd`, no `.pyclawd/config.py`): just add
`pyclawd` as a dev-dep and run `pytest` (`pytest --golden-update` to bless). For
**zero pyclawd dependency at all**, `pyclawd golden vendor <file>` copies the engine +
plugin into one self-contained file the project commits and registers via
`pytest_plugins`. golden is a **separate tier** — exclude it from the unit tiers
(`"default": "not slow and not golden"`) and run it as its own gate. The
`pyclawd golden` CLI is the optional wrapper; `GoldenConfig` lets it drive the plugin
(unset → `pyclawd golden` exits 2, but the plugin still works under bare `pytest`). Full
doctrine in the **`pyclawd-golden`** skill.

## Architecture — generic core + per-project config

pyclawd ships a project-agnostic command layer. Everything project-specific lives
in one file:

- **`.pyclawd/config.py`** — defines a module-level `project = Project(...)` (from
  `pyclawd import Project`). The directory containing `.pyclawd/` **is** the repo
  root.
- The `Project` model groups config: `QualityConfig` (lint/format/typecheck/check
  argv), `TestConfig` (tests dir + tier markers), `DocsConfig` (docs toolchain, or
  `None`), `DoctorConfig` (deps/binaries/tool-files to probe), `BuildConfig`
  (compile/dist/clean argv, via `project.build`, or `None`), `CoverageConfig`,
  `DescriptionConfig`, and `GoldenConfig` (the behavior-oracle wrapper, or `None`).
  Unset optional groups disable their commands cleanly.
- To inspect a project's setup, read its `.pyclawd/config.py` — it is the single
  source of truth for env, paths, markers, and checks.

**Every module opens with a one-line docstring** (PEP 257) — `pyclawd ls` surfaces
the code map and `pyclawd ls --missing` finds the gaps; keep it empty. Which files
are checked is controlled by `DescriptionConfig(include=[...], exclude=[...])` on
`Project` (default: `.py`/`.pyx` only). **Docstrings use Google style, no types**
(`Args:` / `Returns:` / `Raises:` with plain descriptions — annotations carry the
types). `pyclawd lint` checks docstring style via ruff's `D` rules (Google
convention; tests exempt) — write `Args:`/`Returns:`, not NumPy
`Parameters`/`----------`. The `pyclawd` skill has examples and shows how to change
the convention when adopting an existing repo.

## Boundaries

### Always
- Run code via `pyclawd python` — never bare `python`.
- Run `pyclawd doctor` first when the env looks off or tests fail to import.
- Run `pyclawd check` (or at least `pyclawd test run`) **before declaring work done**
  or opening a PR.
- Fix the **cause** of a failing test, not the assertion — use tolerances for
  floats, pin seeds for stochastic tests.
- Match existing patterns; read `.pyclawd/config.py` before assuming how the project
  is wired.

### Ask first
- Destructive cleans — `pyclawd clean --ext` removes compiled extensions and forces
  a recompile.
- Committing, pushing, or opening PRs.
- Changing `.pyclawd/config.py`, dependencies, or the public API surface.
- Re-running a full docs build or `pyclawd test all` when it is expensive.

### Never
- Never call bare `python`/`pip` outside the project env.
- Never commit secrets, tokens, or credentials.
- Never edit generated artifacts (e.g. executed `.ipynb`); edit the source.
- Never weaken or delete a test to make a suite pass.
- Never leave the tree with a failing `pyclawd check`.
- Never use `git commit --no-verify` to bypass pre-commit hooks — fix the cause.
- Never wire `pyclawd golden update` into an autonomous loop — agents compare,
  humans bless.

## How you know you're done

- `pyclawd check` is green (format-check, lint, typecheck, descriptions, and tests
  all ✓). The `descriptions` step is the enforced gate — it passes when every
  `DescriptionConfig`-included file (default `.py`/`.pyx`) has a one-line
  description.
- `pyclawd doctor` exits 0 — no FAILs.
- Behavior is verified by tests, not just by inspection.

`pyclawd ls --missing` is the broader **exploratory** view: it lists *every* repo
file lacking a one-liner, including templates and Markdown the `descriptions` gate
deliberately ignores. It may legitimately be non-empty even when `pyclawd check` is
green — the gate is `descriptions`, not `ls --missing`.

---

**Going deeper.** This file is the contract. For the doctrine behind it, invoke the
Claude Code skills: **`pyclawd`** is the umbrella router — a lean overview plus
on-demand reference docs (`references/mental-model.md`, `references/tests.md`,
`references/quality.md`, `references/docs.md`, `references/packaging.md`) that carry
the testing, quality, docs, and packaging doctrine. Four focused standalone skills
sit alongside it: **`pyclawd-adopt`** (adopt pyclawd into an existing repo —
red-to-green with zero behavior regression; `pyclawd new` adopt mode now detects the
flat-vs-`src` layout, infers `root_markers`, and prints a Phase-0 readiness report of
what is missing, with `--scaffold-pyproject` to drop a starter ruff/mypy/pytest config),
**`pyclawd-golden`** (the behavior
oracle), **`pyclawd-doctor`** (diagnose a broken env), and **`pyclawd-upgrade`**
(migrate a project *after* a pyclawd version bump, when `pyclawd version` shows config
drift — the upgrade counterpart to `pyclawd-adopt`'s first-time onboarding). They are
generic (not
specific to any one repo) and update centrally when pyclawd is upgraded — which is
exactly why the deep doctrine lives there and is not duplicated into this file.
