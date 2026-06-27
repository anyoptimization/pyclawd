# pyclawd

**An opinionated framework for AI-agent-driven Python development.**

pyclawd gives a coding agent (and the human next to it) a single, deterministic command surface for working on a Python project: run code in the right environment, run tiered tests with a `--lf` fix-loop, lint/format/typecheck behind one aggregate `check` gate, build cached docs, health-check the setup with `doctor`, and scaffold or adopt a best-practice project. Humans and agents drive the project *exactly the same way* — through `pyclawd` — so the agent never has to guess which tool, flag, or env to use.

### What "opinionated" means

The opinions are encoded in **the choice of tools**, not in the command layer. pyclawd ships an empty, generic core; each project's [`.pyclawd/config.py`](#architecture--one-config-file) names the concrete toolchain — and the scaffolder (`pyclawd new`) picks a strong default set:

| Concern | Opinion baked into the scaffold |
|---|---|
| Lint + format | **ruff** (`ruff check` / `ruff format`) |
| Type-checking | **mypy** |
| Tests | **pytest** with tiered markers (`fast` / `default` / `all`) + xdist |
| Packaging | **hatchling** + PEP 621 + PEP 735 dev group, `src/` layout, `py.typed` |
| Docs (optional) | isolated **jupyter-cache**/Sphinx notebook pipeline |
| Agent doctrine | `AGENTS.md` + bundled Claude Code skills |

Swap any of them by editing one config field — the verbs (`pyclawd test`, `pyclawd check`, …) stay identical, so agent muscle-memory and CI both keep working. **The CLI is the stable contract; the tools behind it are the opinion.**

### Why agents like it

- **One surface, deterministic exit codes.** `0` = success, `2` = "not configured for this project", otherwise the tool's own code — so an agent can branch on results instead of scraping text.
- **Self-describing, never-crashing.** Unconfigured command groups (docs, quality, compile) self-report cleanly instead of dumping a traceback.
- **Ships its own agent doctrine.** `AGENTS.md` + `pyclawd-*` Claude Code skills travel with every scaffolded/adopted project, so the agent reads the rules of the repo before touching it.

## Install

```bash
pip install -e ".[dev]"   # from a checkout — includes ruff/mypy/pytest
pip install pyclawd       # once published
```

This installs the `pyclawd` executable.

## Quick start

```bash
pyclawd new myproj      # scaffold a fresh best-practice project
cd myproj

pyclawd new             # …or, inside an existing repo, ADOPT pyclawd
                        # (detects flat-vs-src layout, infers root_markers, writes
                        #  ./.pyclawd/config.py, and prints a Phase-0 readiness report)
pyclawd new --scaffold-pyproject   # also drop a starter ruff/mypy/pytest config

pyclawd doctor          # health-check the dev env
pyclawd test fast       # <30s smoke tier
pyclawd check           # the full quality gate
```

## Commands

| Task | Command |
|---|---|
| Health-check the dev env | `pyclawd doctor` |
| Run Python in the project env | `pyclawd python <file>` · `-m <mod>` · `-c <code>` |
| Fast smoke tests (<30s, xdist) | `pyclawd test fast` |
| Default test gate / everything | `pyclawd test run` · `pyclawd test all` |
| Select tests | `pyclawd test -k <kw>` · `pyclawd test tests/path::node` |
| Test fix-loop | `pyclawd test failures` → `pyclawd test fix` → `pyclawd test run` |
| Lint / format / typecheck | `pyclawd lint [--fix]` · `pyclawd format [--check]` · `pyclawd typecheck` |
| Aggregate quality gate | `pyclawd check` |
| Build / dist / clean | `pyclawd compile` · `pyclawd dist` · `pyclawd clean [--ext]` |
| Docs (if configured) | `pyclawd docs build\|run\|render\|serve\|status\|failures\|exec <page>` |
| Scaffold / adopt | `pyclawd new <name>` · `pyclawd new` (adopt: detects layout + Phase-0 readiness) · `pyclawd new --scaffold-pyproject` |
| Code map (file → description) | `pyclawd ls [DIR]` · `pyclawd ls --missing` · `pyclawd ls --py` |
| Repo root / version | `pyclawd root` · `pyclawd version` |

`pyclawd check` runs the quality steps **format-check → lint → typecheck regardless of individual failures** (so you see the full picture in one shot), then runs **test** only if quality passed — with a per-step ✓/✗ summary, the CI-parity "am I done?" gate. Add `--fail-fast` to stop at the first failure, `--fix` to autofix format+lint, `--skip <verb>` to omit a step. Commands for build, dist, and docs only do work when the project configures them; otherwise they degrade gracefully. Override config discovery with `--config PATH` or `PYCLAWD_CONFIG`; by default pyclawd walks up from the cwd to find `.pyclawd/config.py`.

## Code map — one-line file descriptions

pyclawd promotes a tiny "good Python code" convention: **every module opens with a one-line docstring.** The first line of the module docstring (PEP 257) is the file's description; a leading `#` comment is the fallback, and for non-Python text files the first leading comment (`#`, `//`, or `<!-- ... -->`) is used.

`pyclawd ls` surfaces that convention as a skimmable, agent-friendly map of the repo — every tracked file (via `git ls-files`, so `.gitignore` is honoured) paired with its description, ending in an `N files · M described · K missing` footer:

```bash
pyclawd ls                  # the code map for the default root (src_dir, then repo root)
pyclawd ls src/pkg/commands  # list a specific directory (relative to cwd, or absolute)
pyclawd ls --missing        # only the gaps — files lacking a description
pyclawd ls --py             # limit to .py files
pyclawd ls --tracked        # only git-tracked files (default shows untracked too)
```

By default `pyclawd ls` shows **all** files — tracked plus untracked-but-not-ignored (`.gitignore` is still honored); pass `--tracked` to restrict to git-tracked files.

`pyclawd ls` takes an optional `DIR` to list. With no argument it defaults to the project's **`src_dir`** (the code/source root — configurable in `.pyclawd/config.py`, defaults to `src`) when that exists, otherwise the repo root; a header line names the root being listed and paths are shown relative to it. Outside a git repo it falls back to walking the tree (skipping `.git`, `__pycache__`, the tool caches, `build`/`dist`, etc.), and it never crashes on a bad file — anything unreadable or unparseable is treated as having no description. A non-existent `DIR` exits `2`; otherwise `pyclawd ls` always exits `0` — use `--missing` to review the gaps to fill.

## Architecture — one config file

pyclawd is a project-agnostic core. Everything project-specific lives in a single `.pyclawd/config.py` that defines a module-level `project` object. The directory containing `.pyclawd/` **is** the repo root.

```python
from pyclawd import DoctorConfig, Project, QualityConfig, TestConfig

project = Project(
    name="myproject",
    conda_env=None,                       # or "myenv"; None = env-agnostic
    root_markers=["pyproject.toml", "src/myproject/__init__.py"],
    quality=QualityConfig(                # lint/format/typecheck/check argv
        lint_cmd=["ruff", "check"],
        lint_fix_cmd=["ruff", "check", "--fix"],
        format_cmd=["ruff", "format"],
        format_check_cmd=["ruff", "format", "--check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck", "descriptions", "test"],
    ),
    test=TestConfig(                      # tests dir + tier marker expressions
        tests_dir="tests/",
        classname_prefix="tests.",
        integration_files=[],
        markers={"fast": "not slow and not integration", "default": "not slow", "all": ""},
    ),
    doctor=DoctorConfig(                  # what `pyclawd doctor` probes
        core_deps=["typer", "rich"],
        dev_deps=["pytest"],
        tool_files=[],
        binaries=[("ruff", "pip install ruff"), ("mypy", "pip install mypy")],
    ),
    docs=None,                            # set a DocsConfig to enable `pyclawd docs`
)
```

The nested configs (`QualityConfig`, `TestConfig`, `DocsConfig`, `DoctorConfig`, plus the optional `BuildConfig` via `project.build` and `GoldenConfig`) each gate their command group: leave one out and those commands self-report as unconfigured instead of crashing (e.g. `build=None` → `compile`/`dist`/`clean` exit 2).

Two worked examples bracket the range:

- **Minimal** — this repo's own [`.pyclawd/config.py`](.pyclawd/config.py): env-agnostic, pure-Python, no compile, no docs. pyclawd dogfoods itself.
- **Full (every knob, annotated)** — [`examples/config.reference.py`](examples/config.reference.py): a compiled-extension project that also builds docs, exercising `compile`/`dist`/`clean --ext`, a `DocsConfig`, 5-tier + integration-suite markers, scoped quality argv, and a custom `extra_doctor_checks` hook. A unit test keeps it valid.

Copy whichever is closer and delete what you don't use.

## Skills

pyclawd ships agent-facing slash-command skills under [`skills/`](skills/): the start-here umbrella `pyclawd` router skill (a lean overview plus on-demand `references/{mental-model,tests,quality,docs,packaging}.md` carrying the testing/quality/docs/packaging doctrine) plus the four focused standalone skills `pyclawd-adopt` (adopt pyclawd into an existing repo — red-to-green with zero behavior regression), `pyclawd-golden`, `pyclawd-doctor`, and `pyclawd-upgrade` (migrate *after* a pyclawd version bump — the upgrade counterpart to first-time adoption). They are thin wrappers over the CLI. `pyclawd skills install` copies (or symlinks) the `pyclawd-*` directories into your **user-scope** `~/.claude/skills/` by default — they are generic, so they are shared across every project rather than committed per-repo — see [`skills/README.md`](skills/README.md). Agent doctrine for any pyclawd project lives in [`AGENTS.md`](AGENTS.md).

## Status

pyclawd is intended as a reusable starter template: adopt it with `pyclawd new`, then evolve `.pyclawd/config.py` as the project grows.
