---
name: pyclawd
description: Start-here overview of pyclawd — the mental model and the full command surface. pyclawd is a config-driven dev-task CLI: one `.pyclawd/config.py` describes the project, and humans and agents drive it the same way via `pyclawd <verb>`. Read this to understand what pyclawd offers and how the pieces fit before reaching for the focused skills (pyclawd-tests/-quality/-docs/-doctor). Use when orienting in a pyclawd project, deciding which command to run, or explaining what pyclawd is.
when_to_use: Orienting in a pyclawd repo, picking the right command, or understanding the mental model. The umbrella over the focused pyclawd-* skills.
---

# pyclawd — the mental model

pyclawd is **an opinionated, config-driven dev-task CLI for Python projects**. The
opinions are not in the command layer — they live in the **choice of tools** each
project names in its `.pyclawd/config.py`. The CLI verbs are the stable contract;
the tools behind them are the opinion.

Four ideas explain everything:

1. **Generic core + one config file.** pyclawd ships a project-agnostic command
   layer. Everything project-specific — env, paths, test tiers, lint/type tools,
   docs toolchain, doctor checks — lives in a single module-level
   `project = Project(...)` in `.pyclawd/config.py`. The directory containing
   `.pyclawd/` **is** the repo root. Read that file first; it is the single source
   of truth.
2. **The CLI is the contract.** `pyclawd test`, `pyclawd check`, … stay identical
   across projects; swap a tool by editing one config field and the verbs don't
   move. Humans and AI agents drive the project the *same way*.
3. **Deterministic & self-describing.** Exit codes are an API: `0` success, `2`
   "not configured for this project", otherwise the underlying tool's own code.
   Unconfigured groups (docs, quality, compile) self-report instead of crashing,
   so `pyclawd --help` and `pyclawd doctor` always work.
4. **Agent-native.** Every adopted project carries `AGENTS.md` (the doctrine) and
   the bundled `pyclawd-*` skills, so an agent reads the rules before touching code.

## What pyclawd offers (the command surface)

| Task | Command | Focused skill |
|---|---|---|
| Health-check the dev env | `pyclawd doctor` | `pyclawd-doctor` |
| Run code in the project's Python | `pyclawd python <file>` · `-m <mod>` · `-c <code>` | — |
| Tiered tests + fix-loop | `pyclawd test fast\|run\|all` · `failures` · `fix` · `timings` | `pyclawd-tests` |
| Lint / format / typecheck | `pyclawd lint [--fix]` · `pyclawd format [--check]` · `pyclawd typecheck` | `pyclawd-quality` |
| **The "am I done?" gate** | `pyclawd check` (format-check → lint → typecheck → test, fail-fast) | `pyclawd-quality` |
| Build / dist / clean | `pyclawd compile` · `pyclawd dist` · `pyclawd clean [--ext]` | — |
| Docs (if configured) | `pyclawd docs build\|run\|render\|serve\|status\|failures\|exec` | `pyclawd-docs` |
| Code map (file → description) | `pyclawd ls` · `pyclawd ls --missing` · `pyclawd ls --py` | — |
| Scaffold / adopt | `pyclawd new <name>` · `pyclawd new` | — |
| Manage skills | `pyclawd skills list` · `pyclawd skills install` | — |
| Repo root / version | `pyclawd root` · `pyclawd version` | — |

## Two conventions worth knowing

- **Always run Python via `pyclawd python`** — never bare `python`. It launches the
  project's interpreter (see below) with the repo root on `PYTHONPATH`.
- **Every source file opens with a one-line description** — the module docstring's
  first line for `.py` (PEP 257), else a leading `#` comment. `pyclawd ls` renders
  the resulting code map; `pyclawd ls --missing` finds files still lacking one. When
  you add a file, give it a top-of-file one-liner so the map stays complete.

## How the interpreter/env is chosen

`pyclawd python` (and every command that runs code) resolves the interpreter in one
place, with this precedence:

1. `PYCLAWD_PYTHON` env var (a full command, e.g. `PYCLAWD_PYTHON="uv run python"`) —
   a per-invocation override.
2. `Project.python_cmd` in config — a venv path, `["conda","run","-n","env","python"]`,
   `["uv","run","python"]`, etc.
3. `sys.executable` — the default (install pyclawd into the env you develop in).

`pyclawd doctor` shows the resolved launcher as its **python exec** row.

## Where to go next

- Running or fixing tests → **`pyclawd-tests`**
- Clean/typed code, the `check` gate → **`pyclawd-quality`**
- Env looks wrong, imports fail → **`pyclawd-doctor`**
- Building docs (only if the project configures `DocsConfig`) → **`pyclawd-docs`**
- The full doctrine + boundaries → `AGENTS.md` at the repo root
- How this project is wired (tools, env, markers) → `.pyclawd/config.py`
