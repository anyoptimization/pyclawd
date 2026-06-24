---
name: pyclawd
description: Start-here overview of pyclawd AND the complete best-practices doctrine for working in a pyclawd project. Covers the mental model, the full command surface, Python coding standards (testing, typing, linting, packaging, docs, CI), and the agent-specific rules that differ from manual development. Read this before any other pyclawd-* skill. Use when orienting in a pyclawd project, deciding which command to run, explaining what pyclawd is, or needing a reminder of the rules.
when_to_use: Orienting in a pyclawd repo, picking the right command, understanding the mental model, or refreshing on best practices before starting work. The umbrella over the focused pyclawd-* skills.
---

# pyclawd — mental model + best practices

pyclawd is **a config-driven dev-task CLI for Python projects**. One file —
`.pyclawd/config.py` — describes the project; `pyclawd <verb>` is the single
stable contract for every task. Humans and AI agents drive the project the same
way.

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

### Full command surface

| Task | Command | When |
|---|---|---|
| Resolved config | `pyclawd config` | Start of session — see what every command runs |
| Health-check | `pyclawd doctor` | Start of session, on env weirdness |
| Run Python | `pyclawd python <file\|module\|-c>` | Always |
| Fast smoke (<30s) | `pyclawd test fast` | After every edit |
| Default PR gate | `pyclawd test run` | Before declaring done |
| Full suite | `pyclawd test all` | Nightly / release |
| Fix-loop | `pyclawd test failures` → `pyclawd test fix` | When tests fail |
| Slowest tests | `pyclawd test timings [--top N]` | Finding slow-unmarked tests |
| Lint / autofix | `pyclawd lint` · `pyclawd lint --fix` · `pyclawd lint <file...>` | On code changes |
| Format / check | `pyclawd format` · `pyclawd format --check` · `pyclawd format <file...>` | On code changes |
| Type-check | `pyclawd typecheck` · `pyclawd typecheck <file...>` | On code changes |
| **Done gate** | `pyclawd check` | Before every PR / commit |
| Done + autofix | `pyclawd check --fix` | When format/lint need fixing |
| Build / dist | `pyclawd compile` · `pyclawd dist` | On release |
| Docs | `pyclawd docs build\|exec\|failures\|status\|serve` | When editing docs |
| Code map | `pyclawd ls [DIR]` · `pyclawd ls --missing` | Navigation |
| Scaffold | `pyclawd new <name>` · `pyclawd new` (adopt) | New projects |
| Repo root | `pyclawd root` | Sanity check |

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
@pytest.mark.long        # too expensive for the default gate
```

Unmarked tests run in **every** tier. `--strict-markers` and `--strict-config`
are always on — typo'd markers error immediately.

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

The scaffold defaults to **Google style** enforced by ruff `D`/`DOC` rules.
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
individual failures**, then **test** (only if quality passed). Each failing
quality step is tee'd to a log file — the path is shown in the summary so the
agent can read the full output. This is the definition of done.

```bash
pyclawd check                        # see all quality issues in one shot; tests run if quality passes
pyclawd check --fix                  # autofix format+lint, then check everything
pyclawd check --skip test            # quality only, no tests
pyclawd check --skip typecheck       # format + lint only
pyclawd check --fail-fast            # stop at first failure (CI mode)
pyclawd check src/mypkg/foo.py       # quality on one file (parallelization)
```

When `pyclawd check` fails at quality steps, the summary shows log paths:
```
  ✗  format-check  →  /tmp/pyclawd/logs/check/20260624-format-check.log
  ✗  lint          →  /tmp/pyclawd/logs/check/20260624-lint.log
  ✓  typecheck
  ·  test  (skipped — fix quality first)
```
Read the log files to see the full tool output (file lists, error details).

### Ruff (lint + format)

Standard rule set: `E F I B UP SIM C4 RUF PGH`. Always runs via
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

ruff enforces **Google-style docstrings** (`D` + `DOC` rules). Type
annotations are the single source of truth (mypy owns types); docstrings add
the *why/what* that annotations can't.

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

Rules enforced by `pyclawd lint`:
- `D103` — every public function needs a docstring (tests exempted)
- `D205` — blank line between summary and body
- `D416` — section names end with colon (`Args:` not `Args`)
- `DOC` — parameter names in docstring match the actual signature

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
| `PYCLAWD_CONFIG` | Which config file to load (default: walk-up from cwd) |
| `PYCLAWD_PYTHON` | Python interpreter for all commands (default: sys.executable) |
| `PYCLAWD_WORK_DIR` | Where logs and junit XML are written (default: tmpdir) |

Reading `.pyclawd/config.py` directly gives you the full structure and comments.
Use both: `pyclawd config` for orientation, `config.py` for understanding intent.

---

## Where to go next

| Need | Skill |
|---|---|
| Running or fixing tests | `pyclawd-tests` |
| Lint, format, typecheck, check gate | `pyclawd-quality` |
| Env looks wrong, import fails | `pyclawd-doctor` |
| Building docs | `pyclawd-docs` |
| Full doctrine + project boundaries | `AGENTS.md` at repo root |
| Research-backed best practices | `.claude/docs/BEST_PRACTICES.md` |
| Improvement roadmap | `.claude/docs/PYCLAWD_ROADMAP.md` |
