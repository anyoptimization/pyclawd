---
name: pyclawd
description: Start-here overview of pyclawd AND the complete best-practices doctrine for working in a pyclawd project. Covers the mental model and Python coding standards (testing, typing, linting, packaging, docs, CI) and the agent-specific rules that differ from manual development — the *why* behind the repo's AGENTS.md operational contract. Read this before any other pyclawd-* skill. Use when orienting in a pyclawd project, explaining what pyclawd is, or needing a reminder of the rules.
when_to_use: Orienting in a pyclawd repo, picking the right command, understanding the mental model, or refreshing on best practices before starting work. The umbrella over the focused pyclawd-* skills.
---

# pyclawd — mental model + best practices

pyclawd is **a config-driven dev-task CLI for Python projects**. One file —
`.pyclawd/config.py` — describes the project; `pyclawd <verb>` is the single
stable contract for every task. Humans and AI agents drive the project the same
way.

> **How this skill relates to `AGENTS.md`.** Every pyclawd repo ships an
> `AGENTS.md` that is *always* in your context — the **operational contract**: the
> command quick-reference, boundaries, and non-negotiables. This skill is the
> **doctrine behind it** — the *why*, and the testing / typing / packaging
> deep-dives. AGENTS.md says *what to run*; this skill says *how to write good
> code*. Where they could overlap, AGENTS.md owns the command surface, so reach for
> AGENTS.md (or `pyclawd config`) for the exact commands rather than a table here.

---

## 0. Before you touch code

```bash
pyclawd config          # resolved config + env var knobs — run this first
pyclawd doctor          # is the env healthy? fix any FAIL rows first
pyclawd ls              # code map: file → one-line description
pyclawd ls --missing    # find files with no docstring (keep this empty)
```

`pyclawd config` shows the exact command every verb will run, all three
`PYCLAWD_*` override variables (set or not), and their current effective values.
Run it before anything else to know exactly what you're working with.

---

## 1. The CLI is the only interface

**ALWAYS run Python via `pyclawd python`. NEVER call bare `python`.**

```bash
pyclawd python script.py
pyclawd python -m pytest ...
pyclawd python -c "import mypkg"
```

`pyclawd python` runs in the project's configured env with the repo root on
`PYTHONPATH`. Bare `python` misses the env and the in-tree source.

The full command quick-reference lives in the repo's **`AGENTS.md`** (always in
your context) and `pyclawd config` shows what each verb resolves to *for this
project* — consult those rather than a copy here that can drift. The focused skills
go deep on each area: `pyclawd-tests`, `pyclawd-quality`, `pyclawd-golden`,
`pyclawd-doctor`, `pyclawd-docs`.

### Exit-code contract

- `0` — success
- `2` — command exists but project hasn't configured this feature
- other — the underlying tool's own exit code

Agents branch on exit codes, not output text. Never parse output when the exit
code tells you what you need.

---

## 2. Testing

### Test tiers

| Tier | Marker filter | Wall-time | When to run |
|---|---|---|---|
| `fast` | `not slow and not integration` | <30s | After every file change |
| `run` (default) | `not slow` | <5 min | Before opening a PR |
| `all` | _(no filter)_ | uncapped | Nightly / pre-release |

### Marking

Mark exceptions only — never mark fast or unit:

```python
@pytest.mark.slow        # speed axis: test takes >1s
@pytest.mark.integration # scope axis: needs live DB, network, filesystem
```

Two orthogonal axes — **speed** (`slow`) and **scope** (`integration`) — because a
test can be fast-but-needs-a-DB or slow-but-hermetic. Unmarked tests run in
**every** tier. `--strict-markers` and `--strict-config` are always on — typo'd
markers error immediately. (Need a nightly-only third expense tier? Add your own
`long` marker + a `default = "not long"` tier; it's not in the default set.)

Distinct from markers: use `pytest.importorskip` / `skipif` when a test should
**skip itself** because an optional dependency/service is absent — that's
orthogonal to tier deselection and the two can apply to the same test.

### Fix-loop doctrine

1. `pyclawd test failures` — see what's red
2. Fix the **cause**, not the assertion
3. `pyclawd test fix` (`pytest --lf`) — rerun only the failures
4. `pyclawd test run` — full pass to verify no regressions

### Brittle test rules

| Problem | Fix |
|---|---|
| Float equality fails | `pytest.approx(expected)` — never `== 0.3` |
| Stochastic flap | Pin `seed=42` in the test body, or use `pytest-randomly` |
| Mass import errors | Run `pyclawd doctor` — it's an env problem, not a test bug |
| Order-dependent tests | Reset all global state in fixtures; never rely on run order |

### Existing repos with a quality backlog

If `pyclawd check` is already red when you arrive, the repo has pre-existing
lint/format debt. **Don't reformat files you aren't otherwise touching** — it
balloons your diff. Two options:

- **Preferred:** land a one-commit baseline PR first — `pyclawd format && pyclawd lint --fix` — zero logic change, makes the gate live going forward.
- **If not yet:** scope to changed files only — `pyclawd lint src/mypkg/myfile.py` — and note the pre-existing backlog in your PR description.

### Docstring style — opting out or changing convention

The scaffold defaults to **Google style**, checked by ruff's `D` rules.
For repos with an existing docstring convention, set it once in
`pyproject.toml` — no docstrings need rewriting:

```toml
# NumPy-style repo (e.g. scientific / pandas-ecosystem)
[tool.ruff.lint.pydocstyle]
convention = "numpy"

# No docstring enforcement at all (legacy codebase, gradual adoption)
[tool.ruff.lint]
ignore = ["D", "DOC"]

# Enforce style on existing docstrings but don't require them everywhere yet
[tool.ruff.lint]
ignore = ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]
```

Read the current `pyproject.toml` to see what's configured before writing any
docstrings — matching the existing convention matters more than any default.

### Never

- Weaken or delete a test to make a suite pass
- Mock internal functions — mock at system boundaries (HTTP, DB, clock) only
- Leave `pyclawd test run` red

---

## 3. Code quality

### The gate: `pyclawd check`

Runs all quality steps (format-check → lint → typecheck) **regardless of
individual failures**, streaming each step's output inline. Then runs **test**
only if quality passed.

```bash
pyclawd check                        # full project; all quality steps + tests
pyclawd check --fix                  # autofix format+lint, then check everything
pyclawd check --skip test            # quality only, no tests
pyclawd check --skip typecheck       # format + lint only
pyclawd check --fail-fast            # stop at first failure (CI mode)
pyclawd check src/mypkg/foo.py       # quality on one file — parallelization
pyclawd check --log                  # also write each step's output to a log file
```

All output is printed inline — you can read it directly in the terminal or
conversation context. `--log` additionally writes each failing step to a file and
shows the path in the summary; use it for CI artifacts or when you want a
persistent record.

The summary is always printed:
```
  ✓  format-check
  ✗  lint  (exit 1)
  ✓  typecheck
  ·  test  (skipped — fix quality first)
```

#### Prerequisite for `pyclawd check <file>` to work correctly

Quality cmds must be **target-less** — pyclawd appends the path, so no target
baked in:

```python
QualityConfig(lint_cmd=["ruff", "check"], typecheck_cmd=["mypy"])  # ✓
QualityConfig(lint_cmd=["ruff", "check", "mypkg"], typecheck_cmd=["mypy", "mypkg"])  # ✗
```

mypy also needs in `[tool.mypy]`:
```toml
explicit_package_bases = true
mypy_path = "."
```
The scaffold template includes both automatically. See `pyclawd-quality` skill for
the full contract.

#### Descriptions step and `DescriptionConfig`

When `"descriptions"` is in `check_sequence`, `pyclawd check` verifies every
eligible source file has a one-line top-of-file docstring or `#` comment.
Configure via `DescriptionConfig` in `.pyclawd/config.py`:

```python
from pyclawd import Project, DescriptionConfig

project = Project(
    ...
    descriptions=DescriptionConfig(
        include=[r"\.pyx?$"],        # default: Python/Cython only
        exclude=[r"vendor/"],        # skip vendored Python
    ),
)
```

Default (`DescriptionConfig()` with no args): only `.py`/`.pyx` files, nothing
excluded. Fortran, C, data files are never checked by default.

### Ruff (lint + format)

Standard rule set: `E F I B UP SIM C4 RUF PGH D` (the scaffold's default; the `D`
rules check docstring style under the Google convention below). Always runs via
`pyclawd lint` / `pyclawd format`. Agents use `--fix` unconditionally — we
review every diff anyway.

Suppression: always specify the code.
```python
x = thing()  # noqa: F401       — not: # noqa
y = api()    # type: ignore[no-untyped-call]  — not: # type: ignore
```

### mypy (type checking)

New code uses `strict = true` from day one. Agents write annotated code
immediately; strict mode costs nothing on a fresh file. Use modern syntax:

```python
def f(x: int | None) -> list[str]: ...   # YES — Python 3.10+
from typing import Optional, List         # NO — legacy
```

Suppress per-module, never globally:
```toml
[[tool.mypy.overrides]]
module = ["requests.*"]
ignore_missing_imports = true
```

### Docstring convention — Google style, no types

ruff checks docstring style under the **Google** convention (the `D` rules). Type
annotations are the single source of truth (mypy owns types); docstrings add
the *why/what* that annotations can't.

> Note: ruff's `convention = "google"` selects which `D` rules run — it does **not**
> hard-reject a well-formed NumPy `Parameters` block on its own (and the `DOC`
> pydoclint rules only run under ruff's unstable `preview`, so pyclawd does not
> select them). Treat Google style as the rule here, upheld by review and agents —
> write `Args:`/`Returns:`, never NumPy sections.

```python
# ✓ correct — no types in docstring, annotations carry them
def foo(x: int, y: str) -> bool:
    """Check whether x satisfies y.

    Args:
        x: The threshold value.
        y: The pattern to match against.

    Returns:
        True if x satisfies the pattern.

    Raises:
        ValueError: If y is empty.
    """

# ✗ wrong — NumPy style, types duplicated
def foo(x: int, y: str) -> bool:
    """Check whether x satisfies y.

    Parameters
    ----------
    x : int        ← don't repeat the type
        The threshold.
    """
```

Rules enforced by `pyclawd lint` (the `D` family, Google convention):
- `D103` — every public function needs a docstring (tests exempted)
- `D205` — blank line between summary and body
- `D416` — section names end with colon (`Args:` not `Args`)

**Every module** also needs a one-line top-of-file docstring. `pyclawd ls`
builds the code map from these; `pyclawd ls --missing` finds gaps. **Keep
`pyclawd ls --missing` empty.**

---

## 4. Packaging

- Always `src/` layout — `src/my_package/` with `tests/` outside
- Always `pip install -e .` (editable) during development
- Always add `src/my_package/py.typed` — without it type checkers ignore your annotations downstream
- Version via `hatch-vcs` (git tags → version), expose via `importlib.metadata.version(__name__)`

---

## 5. Agent-specific rules

### What changes when an agent is coding

| Humans skip this | Agents do it every time |
|---|---|
| `--strict-markers` (noisy) | Always on — typos error immediately |
| mypy strict (lots of errors) | Always on — fix each annotation as you write it |
| `filterwarnings = ["error"]` (loud) | Always on — each warning is a task to close |
| Auto-fix lint (scary diff) | Always — we review the diff anyway |
| Running tests on every change | `pyclawd test fast` after every file save |
| High coverage (takes time) | Write the tests — agents don't get tired |

### The code map prevents duplicate divergence

Before implementing any utility, check the code map:

```bash
pyclawd ls              # scan the whole src_dir
pyclawd ls src/utils/   # scope to a subdirectory
```

If a utility already exists, use it. The most common structural damage in
agent-coded repos is the same helper reimplemented slightly differently in
every session.

### Non-interactive always

Every pyclawd command is non-interactive when stdin is not a TTY. Pass `--yes`
/ `--non-interactive` when in doubt. Never hang waiting for `[Y/n]`.

### Never bypass hooks

```
Never: git commit --no-verify
```

A blocked pre-commit hook means something is wrong. Fix the underlying issue.
Bypassing hooks defeats the entire quality system.

### How you know you're done

1. `pyclawd check` is green (format-check ✓, lint ✓, typecheck ✓, test ✓)
2. `pyclawd doctor` exits 0 — no FAILs
3. `pyclawd ls --missing` is empty — every file has a one-liner
4. Behavior is verified by tests, not just by inspection

---

## 6. Config is the source of truth

Before assuming anything about how a project is wired:

```bash
pyclawd config          # resolved view: what each command will actually run
cat .pyclawd/config.py  # raw source: structure + comments + all fields
```

`pyclawd config` shows the effective values after env-var overrides and lists
all three override levers every time — set or not:

| Env var | What it overrides |
|---|---|
| `PYCLAWD_CONFIG` | A specific config file/dir to load (default: walk-up from cwd) |
| `PYCLAWD_DISCOVERY` | Search path of config dirs for walk-up (default: `.pyclawd`) |
| `PYCLAWD_PYTHON` | Python interpreter for all commands (default: sys.executable) |
| `PYCLAWD_WORK_DIR` | Where logs and junit XML are written (default: tmpdir) |

Reading `.pyclawd/config.py` directly gives you the full structure and comments.
Use both: `pyclawd config` for orientation, `config.py` for understanding intent.

### Using pyclawd without committing the config

Some repos (e.g. shared/work repos) shouldn't carry a `.pyclawd/` folder. Keep the
config **uncommitted and local** instead of pointing a global `PYCLAWD_CONFIG` at a
fixed path (an absolute env var can't serve multiple repos — it pins one root):

```bash
# one-time, in your shell profile — safe globally because it's a RELATIVE pattern,
# resolved per-cwd, so every repo/project still finds its own config:
export PYCLAWD_DISCOVERY=".local/.pyclawd:.pyclawd"

# per repo, once:
mkdir -p .local/.pyclawd && pyclawd new            # write .local/.pyclawd/config.py
echo ".local/" >> .gitignore                       # never committed
```

Now `cd` into any repo and `pyclawd <verb>` walks up from cwd, finds
`<repo>/.local/.pyclawd/config.py`, and resolves `root` back to `<repo>` (the
`.local/.pyclawd` wrapper is stripped). A committed `.pyclawd/` still works as the
fallback. `PYCLAWD_DISCOVERY` entries are `os.pathsep`-separated, first match wins.
The simpler alternative — keep `.pyclawd/` but gitignore it — also works if you
don't mind the folder existing in the repo dir.

---

## Where to go next

| Need | Skill |
|---|---|
| Running or fixing tests | `pyclawd-tests` |
| Lint, format, typecheck, check gate | `pyclawd-quality` |
| Prove behavior unchanged (refactor/migration) | `pyclawd-golden` |
| Env looks wrong, import fails | `pyclawd-doctor` |
| Building docs | `pyclawd-docs` |
| pyclawd was upgraded — migrate the config | `pyclawd-upgrade` |
| Full doctrine + project boundaries | `AGENTS.md` at repo root |
| Research-backed best practices | `.claude/docs/BEST_PRACTICES.md` |
| Improvement roadmap | `.claude/docs/PYCLAWD_ROADMAP.md` |
