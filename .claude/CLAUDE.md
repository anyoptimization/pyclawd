# CLAUDE.md — working on the pyclawd repo itself

> This file orients an agent working **on pyclawd's own source**. For the doctrine
> that applies to *any* project that adopts pyclawd, see [`../AGENTS.md`](../AGENTS.md)
> (the repo-root `CLAUDE.md` just `@`-includes it). Read that first — it is the
> commands-first contract. This file adds what is specific to developing pyclawd.

## What pyclawd is

pyclawd is an **opinionated framework for AI-agent-driven Python development**. It
gives an agent one deterministic command surface (`pyclawd …`) for running code,
tests, lint/format/typecheck, docs, and health-checks on a Python project.

The *opinions* are not in the command layer — they are in the **choice of tools**
each project names in its `.pyclawd/config.py` (and that `pyclawd new` scaffolds by
default): **ruff** (lint+format), **mypy** (types), **pytest** (tiered tests),
**hatchling** + `src/` layout (packaging), an optional **jupyter-cache** docs
pipeline, and bundled agent skills. The CLI verbs are the stable contract; the tools
behind them are the opinion. Change a tool by editing one config field — `pyclawd
test` / `pyclawd check` stay identical.

## Tools & prerequisites (per command)

pyclawd itself only depends on **typer** + **rich** (it's a thin orchestrator).
Each command group, though, shells out to a tool that must be present — the
"opinion" is *which* tool, named in `.pyclawd/config.py`. `pyclawd doctor` probes
all of these and reports OK/WARN/FAIL.

| Command(s) | Requires | Notes |
|---|---|---|
| `pyclawd python`, everything | the project's env (here conda `default`) | `conda_env` in config; pyclawd runs `sys.executable` with the repo on `PYTHONPATH` |
| `pyclawd test …` | **pytest** | `test fast` also wants **pytest-xdist** (`-n auto`) |
| `pyclawd lint` / `format` | **ruff** | argv set in `QualityConfig` |
| `pyclawd typecheck` | **mypy** | argv set in `QualityConfig` |
| `pyclawd compile` / `dist` | the project's build backend | only if `project.build` (a `BuildConfig`) sets `compile_cmd` / `dist_cmd`; `build=None` → exit 2 |
| `pyclawd docs build/run/render/exec` | a **`./docs` runner** (sphinx + nbsphinx, via uvx or installed) | delegated to `DocsConfig.runner`; **`render` also needs the `pandoc` system binary** |
| `pyclawd docs failures` / `timings` | a **jupyter-cache** backend at `cache_db`; `failures` imports `jupyter_cache` + `nbformat` **in this env** | see the backend note on `DocsConfig` |

Nothing is required to *register* a command — unconfigured/absent tooling
self-reports (exit `2` for quality/docs, a WARN row in `doctor`) rather than
crashing. So `pyclawd --help` and `pyclawd doctor` always work.

## Repo shape

- `src/pyclawd/` — the generic core. Key modules:
  - `project.py` — the frozen-dataclass config model (`Project` + nested `*Config`).
  - `discovery.py` — locate/load `.pyclawd/config.py` (`--config` › `PYCLAWD_CONFIG` › walk-up).
  - `cli.py` — the Typer app; a thin assembler that registers command groups.
  - `commands/` — one module per group (`test`, `quality`, `build`, `docs`, `new`, `skills`, `benchmark`, `api`).
  - `api.py` / `impact.py` / `benchmark.py` — the three oracle/feedback engines: public-surface AST snapshot (`pyclawd api`), diff→test coverage reverse-map (`pyclawd test changed`), and best-of-N timing gate (`pyclawd benchmark`). `benchmark_plugin.py` is benchmark's standalone pytest plugin (sibling of `pytest_plugin.py`).
  - `run.py` / `tests.py` / `logs.py` / `doctor.py` — the subprocess + pipeline logic.
  - `scaffold/templates/` — `*.tmpl` files rendered by `pyclawd new`.
  - `skills/` — the bundled `pyclawd-*` Claude Code skills.
- `.pyclawd/config.py` — pyclawd's own config; **pyclawd dogfoods pyclawd**, so it is
  also the canonical minimal worked example. Read it before assuming how things wire.
- `tests/` — uses an isolated `tests/pytest.ini` (run with `-c tests/pytest.ini`).

## Working on this repo

```bash
pyclawd doctor                         # health-check the env
pyclawd test fast                      # quick smoke (<30s)
pyclawd check                          # format-check → lint → typecheck → test (the gate)
python -m pytest tests -c tests/pytest.ini   # tests directly (before install / in CI)
```

`pyclawd check` must be **green before any change is done** (it currently is). The
toolchain is the dogfooded one: ruff + mypy + pytest, all configured in
`pyproject.toml`.

### House rules specific to pyclawd

- **The core stays project-agnostic.** Nothing under `src/pyclawd/` may hardcode a
  tool name, path, or marker — every such value comes from the loaded `Project`.
  If you need a new knob, add a field to the config model, don't special-case it.
- **Every file opens with a one-line description.** The module docstring's first
  line for `.py` (PEP 257), else a leading `#` comment. `pyclawd ls` renders the
  code map; `pyclawd ls --missing` finds gaps. New file → add a top-of-file
  one-liner so the map stays complete (keep `pyclawd ls --missing` empty).
- **Commands degrade, never crash.** An unconfigured group (e.g. `docs`, `quality`)
  self-reports and exits `2`; an undefined test tier applies no `-m` filter. Keep
  that contract — prefer `dict.get(...)` / clean `typer.Exit` over raw `KeyError`s.
- **Exit-code contract:** `0` ok · `2` = not-configured **or** a CLI usage error
  (Typer's own convention) · otherwise the underlying tool's own code. Note that
  `pyclawd docs` preflight uses distinct codes — `3` for a missing `pandoc` binary,
  `1` for "no built docs yet" — so don't assume every nonzero from docs is the
  runner's code.
- **Keep the dogfood honest.** If you add a command or config field, update
  `.pyclawd/config.py`, `AGENTS.md`, `README.md`, and the scaffold templates so a
  freshly-`pyclawd new`-ed project still matches reality.
- **Tests for new logic.** This repo values good coverage of the pure logic
  (arg heuristics, tier resolution, discovery precedence, the quality gate) —
  add unit tests next to the existing ones, no network, `tmp_path`-based.
