# Mental model + agent doctrine

The deep "why" behind a pyclawd project. `AGENTS.md` (always in your context) is
the *what to run*; this is the *how to think*.

## What pyclawd is

pyclawd is **a config-driven dev-task CLI for Python projects**. One file —
`.pyclawd/config.py` — describes the project; `pyclawd <verb>` is the single
stable contract for every task. Humans and AI agents drive the project the same
way.

Two ideas carry everything:

- **The CLI verbs are the contract.** `pyclawd test`, `pyclawd check`,
  `pyclawd python`, … never change shape across projects. You learn them once.
- **The tools are the opinion.** *Which* linter, type checker, test runner, build
  backend a verb shells out to is named in `.pyclawd/config.py` (the scaffold's
  default opinion: ruff + mypy + pytest + hatchling + `src/` layout). Swap a tool
  by editing one config field; the verb stays identical.

## The CLI is the only interface

**ALWAYS run Python via `pyclawd python`. NEVER call bare `python`.**

```bash
pyclawd python script.py
pyclawd python -m pytest ...
pyclawd python -c "import mypkg"
```

`pyclawd python` runs in the project's configured env with the repo root on
`PYTHONPATH`. Bare `python` misses the env and the in-tree source.

### Exit-code contract

Agents branch on exit codes, not output text. Never parse output when the exit
code already tells you what you need.

- `0` — success
- `2` — command exists but the project hasn't configured this feature **or** a CLI
  usage error (Typer reuses `2` for bad arguments)
- other — the underlying tool's own exit code

One exception: `pyclawd docs` preflight returns distinct codes — `3` when the
`pandoc` binary is missing, `1` for "no built docs yet" — so a nonzero from docs
is not always the runner's code.

## Config is the source of truth

Before assuming anything about how a project is wired:

```bash
pyclawd config          # resolved view: what each command will actually run
cat .pyclawd/config.py  # raw source: structure + comments + all fields
```

`pyclawd config` shows the effective values after env-var overrides and lists all
override levers every time — set or not:

| Env var | What it overrides |
|---|---|
| `PYCLAWD_CONFIG` | A specific config file/dir to load (default: walk-up from cwd) |
| `PYCLAWD_DISCOVERY` | Search path of config dirs for walk-up (default: `.pyclawd`) |
| `PYCLAWD_PYTHON` | Python interpreter for all commands (default: sys.executable) |
| `PYCLAWD_WORK_DIR` | Where logs and junit XML are written (default: tmpdir) |

Use both: `pyclawd config` for orientation, `config.py` for understanding intent.

### Using pyclawd without committing the config

Some repos (e.g. shared/work repos) shouldn't carry a `.pyclawd/` folder. Keep the
config **uncommitted and local** instead of pinning a global absolute
`PYCLAWD_CONFIG` (an absolute path can't serve multiple repos — it pins one root):

```bash
# one-time, in your shell profile — safe globally because it's a RELATIVE pattern,
# resolved per-cwd, so every repo still finds its own config:
export PYCLAWD_DISCOVERY=".local/.pyclawd:.pyclawd"

# per repo, once:
mkdir -p .local/.pyclawd && pyclawd new            # write .local/.pyclawd/config.py
echo ".local/" >> .gitignore                       # never committed
```

Now `pyclawd <verb>` walks up from cwd, finds `<repo>/.local/.pyclawd/config.py`,
and resolves `root` back to `<repo>` (the wrapper dir is stripped). A committed
`.pyclawd/` still works as the fallback. Entries are `os.pathsep`-separated, first
match wins. Simpler alternative: keep `.pyclawd/` but gitignore it.

## What changes when an agent is coding

The strict knobs humans turn off for noise stay **on** for agents — each warning
is a task to close, not a distraction.

| Humans skip this | Agents do it every time |
|---|---|
| `--strict-markers` (noisy) | Always on — typos error immediately |
| mypy strict (lots of errors) | Always on — fix each annotation as you write it |
| `filterwarnings = ["error"]` (loud) | Always on — each warning is a task to close |
| Auto-fix lint (scary diff) | Always — we review the diff anyway |
| Running tests on every change | `pyclawd test fast` after every file save |
| High coverage (takes time) | Write the tests — agents don't get tired |

### Non-interactive always

Every pyclawd command is non-interactive when stdin is not a TTY. Pass `--yes` /
`--non-interactive` when in doubt. Never hang waiting for `[Y/n]`.

### Never bypass hooks

`git commit --no-verify` is banned. A blocked pre-commit hook means something is
wrong — fix the underlying issue. Bypassing hooks defeats the quality system.

## `pyclawd ls` — orient first, with the code map

`pyclawd ls` is the **first thing to run when you land in a pyclawd repo**, and
again before you implement any helper. It prints the **code map**: every source
file with its one-line description, so you learn where things live — and whether
the thing you're about to write already exists — without opening a single file.

```bash
pyclawd ls              # the whole src_dir: file → one-line description
pyclawd ls src/utils/   # scope to a subtree
pyclawd ls --py         # Python files only
pyclawd ls --missing    # files lacking a one-liner (exploratory; see below)
```

Two reasons it earns being a reflex, not an afterthought:

- **Orientation.** One command gives you the shape of the repo. Reach for it before
  grepping around or reading files top-to-bottom — the map points you at the right
  file directly.
- **It prevents duplicate divergence.** The most common structural damage in
  agent-coded repos is the same helper reimplemented slightly differently every
  session. Scan the map before adding a utility; if it already exists, use it.

### One-line descriptions + DescriptionConfig

The map is only as good as the descriptions it reads. **Every module** opens with a
one-line top-of-file description — a module docstring's first line for `.py` (PEP
257), else a leading `#` comment. `pyclawd ls` builds the code map from these, which
is *why* the `descriptions` gate (below) keeps them present and accurate.

The **enforced gate** is the `descriptions` step of `pyclawd check`, which checks
every file matched by `DescriptionConfig` in `.pyclawd/config.py`:

```python
from pyclawd import Project, DescriptionConfig

project = Project(
    ...,
    descriptions=DescriptionConfig(
        include=[r"\.pyx?$"],        # default: Python/Cython only
        exclude=[r"vendor/"],        # skip vendored / generated Python
    ),
)
```

Default (`DescriptionConfig()`): only `.py`/`.pyx`, nothing excluded — Fortran, C,
data files are never checked.

`pyclawd ls --missing` is the broader **exploratory** view — it also lists
templates/Markdown the gate ignores, so it may legitimately be non-empty even when
`check` is green. Trust the `descriptions` step, not `ls --missing`, as the gate.

## How you know you're done

1. `pyclawd check` is green — format-check ✓, lint ✓, typecheck ✓, **descriptions
   ✓**, test ✓. The `descriptions` step is the real one-liner gate (every
   `DescriptionConfig`-included file), not `ls --missing`.
2. `pyclawd doctor` exits 0 — no FAILs.
3. Behavior is verified by tests, not just by inspection.
