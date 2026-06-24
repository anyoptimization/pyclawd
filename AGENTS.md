# AGENTS.md — working in a pyclawd project

This is the agent doctrine for **any** project that adopts **pyclawd**. pyclawd is a project-generic Python dev-task CLI: one config file (`.pyclawd/config.py`) describes the project, and humans and AI agents drive it the same way. This file complements `README.md` — it is the commands-first contract for agents.

## Critical rule — how to run Python

**ALWAYS run Python through `pyclawd python`. NEVER call bare `python` / `python -c`.**

```bash
pyclawd python script.py          # run a script
pyclawd python -m pytest ...      # run a module
pyclawd python -c "import mypkg"  # quick check
```

`pyclawd python` runs in the project's configured env (the `conda_env` in `.pyclawd/config.py`, or whatever env pyclawd is installed into) with the repo root on `PYTHONPATH`. Bare `python` misses the env and the in-tree source.

## Commands — quick reference

| Task | Command |
|---|---|
| Resolved config (what each command runs) | `pyclawd config` |
| Health-check the dev env | `pyclawd doctor` |
| Run Python in the env | `pyclawd python <file>` · `-m <mod>` · `-c <code>` |
| Fast smoke tests (<30s, xdist) | `pyclawd test fast` |
| Default test gate (not `long`) | `pyclawd test run` |
| Everything incl. `long` | `pyclawd test all` |
| Select tests | `pyclawd test -k <kw>` · `pyclawd test tests/path::node` |
| Fix-loop | `pyclawd test failures` → `pyclawd test fix` → `pyclawd test run` |
| Slowest tests | `pyclawd test timings [--top N]` |
| Lint / autofix | `pyclawd lint` · `pyclawd lint --fix` · `pyclawd lint <file...>` |
| Format / check | `pyclawd format` · `pyclawd format --check` · `pyclawd format <file...>` |
| Type-check | `pyclawd typecheck` · `pyclawd typecheck <file...>` |
| **Aggregate quality gate** | `pyclawd check` · `--fix` · `--skip <verb>` · `--fail-fast` · `pyclawd check <file...>` |
| Build / dist / clean | `pyclawd compile` · `pyclawd dist` · `pyclawd clean [--ext]` |
| Docs (if configured) | `pyclawd docs build\|run\|render\|serve\|status\|failures\|exec <page>` |
| Scaffold / adopt | `pyclawd new <name>` · `pyclawd new` |
| Code map (file → description) | `pyclawd ls [DIR]` · `pyclawd ls --missing` · `pyclawd ls --py` |
| Repo root / version | `pyclawd root` · `pyclawd version` |

`pyclawd check` runs all quality steps (format-check → lint → typecheck) **regardless of individual failures**, then **test** (only if quality passed). Each failing quality step is tee'd to a log file whose path appears in the summary — read those files to see the full output. Use `--skip <verb>` (repeatable) to omit a step entirely, `--fail-fast` to stop at the first failure, and `--fix` to apply format+lint autofixes in-place before checking. Build/dist/clean and docs commands only do real work when the project configures them; otherwise they degrade gracefully. Override config discovery with `--config PATH` (or the `PYCLAWD_CONFIG` env var); by default pyclawd walks up from cwd to find `.pyclawd/config.py`.

## Architecture — generic core + per-project config

pyclawd ships a project-agnostic command layer. Everything project-specific lives in one file:

- **`.pyclawd/config.py`** — defines a module-level `project = Project(...)` (from `pyclawd import Project`). The directory containing `.pyclawd/` **is** the repo root.
- The `Project` model groups config: `QualityConfig` (lint/format/typecheck/check argv), `TestConfig` (tests dir + tier markers), `DocsConfig` (docs toolchain, or `None`), `DoctorConfig` (deps/binaries/tool-files to probe). Unset groups disable their commands cleanly.
- To inspect a project's setup, read its `.pyclawd/config.py` — it is the single source of truth for env, paths, markers, and checks.
- **Every module opens with a one-line docstring** (PEP 257). `pyclawd ls` surfaces the code map; `pyclawd ls --missing` finds gaps. Keep `pyclawd ls --missing` empty.
- **Docstrings use Google style, no types** — type annotations are the source of truth (mypy), docstrings add the *why/what*. `pyclawd lint` enforces this via `D` + `DOC` ruff rules (tests are exempt). Pattern: `Args:` / `Returns:` / `Raises:` sections with plain descriptions, no type repetition. NumPy-style (`Parameters\n----------`) is wrong and will fail lint.

> **Before writing any docstring:** read `pyproject.toml` to check what
> convention this repo uses. Matching the existing style is more important
> than any default.

## Adopting an existing repo — docstring convention

The scaffold defaults to **Google style** (`D`/`DOC` ruff rules). Existing
repos may use a different convention or none at all. Set it once in
`pyproject.toml` — no docstrings need rewriting:

```toml
# NumPy-style repo (scientific / pandas-ecosystem)
[tool.ruff.lint.pydocstyle]
convention = "numpy"

# No docstring enforcement (legacy codebase, gradual adoption)
[tool.ruff.lint]
ignore = ["D", "DOC"]

# Enforce style on existing docstrings but don't require them everywhere yet
# (D10x = "missing docstring" rules; omit them to adopt style without the backlog)
[tool.ruff.lint]
ignore = ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]
```

For a large repo with NumPy-style docstrings (e.g. pymoo, numpy, scipy
ecosystem): set `convention = "numpy"` in `pyproject.toml` and existing
docstrings pass lint immediately — no conversion needed.

## Boundaries

### Always
- Run code via `pyclawd python` — never bare `python`.
- Run `pyclawd doctor` first when the env looks off or tests fail to import.
- Run `pyclawd check` (or at least `pyclawd test run`) **before declaring work done** or opening a PR.
- Fix the **cause** of a failing test, not the assertion — use tolerances for floats, pin seeds for stochastic tests.
- Match existing patterns; read `.pyclawd/config.py` before assuming how the project is wired.

### Ask first
- Destructive cleans — `pyclawd clean --ext` removes compiled extensions and forces a recompile.
- Committing, pushing, or opening PRs.
- Changing `.pyclawd/config.py`, dependencies, or the public API surface.
- Re-running a full docs build or `pyclawd test all` when it is expensive.

### Never
- Never call bare `python`/`pip` outside the project env.
- Never commit secrets, tokens, or credentials.
- Never edit generated artifacts (e.g. executed `.ipynb`); edit the source.
- Never weaken or delete a test to make a suite pass.
- Never leave the tree with a failing `pyclawd check`.

## How you know you're done

- `pyclawd check` is green (format-check, lint, typecheck, and tests all ✓).
- `pyclawd doctor` exits 0 — no FAILs.
- Behavior is verified by tests, not just by inspection.
