# Quality doctrine

Lint / format / typecheck / descriptions, plus the aggregate `pyclawd check` gate.
Every tool's argv comes from `QualityConfig` in `.pyclawd/config.py` — nothing
about ruff/mypy is hardcoded. If quality is unconfigured, the affected command
self-reports and exits 2 instead of crashing. For the exact command list see
`AGENTS.md`; this file is the doctrine.

## What `pyclawd check` proves — and what it doesn't

`pyclawd check` proves code **clean** (static): it cannot prove behavior is
**unchanged**. A clean edit can still move a number. That gap is closed by the
golden oracle (`@pytest.mark.golden` + committed baselines, run as its own gate) —
see the **pyclawd-golden** skill. The two are complementary: quality proves
*clean*, golden proves *unchanged*.

## The gate sequence

`pyclawd check` runs every quality step **regardless of individual failures** so
the full picture is visible in one shot, streaming each step's output inline. The
sequence is **format-check → lint → typecheck → descriptions → test**, with the
`test` step running only if all quality steps passed.

The summary is always printed:

```
  ✓  format-check
  ✗  lint  (exit 1)
  ✓  typecheck
  ✓  descriptions
  ·  test  (skipped — fix quality first)
```

Key flags (full reference in `AGENTS.md`):

- `--fix` — autofix format+lint in place, then check everything.
- `--skip <verb>` (repeatable) — omit a step (e.g. `--skip test`, `--skip typecheck`).
- `--fail-fast` — stop at the first failure (CI mode).
- `--log` — also write each step's output to a log file and show the path; for CI
  artifacts or a persistent record.

## Path scoping + orchestration

Positional paths are appended to each quality-step command, so a fleet can verify
one file per agent in parallel:

```bash
pyclawd check src/mypkg/foo.py        # quality on one file
pyclawd check src/a.py src/b.py       # multiple files
pyclawd check --changed [--against main]   # git-changed source files
pyclawd check --json                  # one machine-readable result object
pyclawd check src/foo.py --test       # path-scoped BUT also run the whole suite
```

**Path-scoped runs are quality-only by default.** Positional paths, `--changed`,
and `--json` all drop the whole-suite `test` step (it never scopes to a file) —
pass `--test` to force it back. This is why a per-file fleet uses `pyclawd check
<file>` (or `--changed --json`) and never needs `--skip test`.

`--json` emits one object —
`{"passed", "scoped", "paths", "steps":[{"verb","status","exit_code","log","reason"}]}`
— and nothing else on stdout (step output goes to log files). An orchestrator
branches on `passed` / per-step `status` (`ok`/`fail`/`skipped`) to decide
commit-vs-no-commit per file, instead of grepping human text.

### Prerequisite: target-less quality cmds

For `pyclawd check <file>` to scope correctly, the quality cmds must be
**target-less** — pyclawd appends the path, so no target baked in:

```python
# ✓ correct — tool reads its scope from pyproject.toml when no path is given
QualityConfig(lint_cmd=["ruff", "check"], typecheck_cmd=["mypy"])

# ✗ wrong — baked-in target; `pyclawd check foo.py` → `mypy mypkg foo.py`
#            → "Duplicate module" or a whole-package scan instead of per-file
QualityConfig(lint_cmd=["ruff", "check", "mypkg"], typecheck_cmd=["mypy", "mypkg"])
```

mypy also needs these in `[tool.mypy]` to avoid "Duplicate module" on a single
path (the scaffold template includes both):

```toml
explicit_package_bases = true
mypy_path = "."
```

## Ruff (lint + format)

Standard rule set: `E F I B UP SIM C4 RUF PGH D` (the scaffold default; the `D`
rules check docstring style under the Google convention below). Agents use `--fix`
unconditionally — we review every diff anyway.

Suppression: always specify the code.

```python
x = thing()  # noqa: F401                          — not bare # noqa
y = api()    # type: ignore[no-untyped-call]       — not bare # type: ignore
```

## mypy (type checking)

New code uses `strict = true` from day one — strict mode costs nothing on a fresh
file. Use modern syntax:

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

## Descriptions step + DescriptionConfig

When `"descriptions"` is in `quality.check_sequence`, `pyclawd check` verifies
every eligible source file has a one-line top-of-file description (module docstring
or leading `#` comment). It runs **alongside** the other quality steps, not after
them, so it's never skipped due to format/lint failures. Configure which files via
`DescriptionConfig` — see [mental-model.md](mental-model.md) for the knobs.
`pyclawd check src/mypkg/foo.py` scopes the descriptions check to that file too.

## Docstring convention — Google style, no types

ruff checks docstring style under the **Google** convention (the `D` rules). Type
annotations are the single source of truth (mypy owns types); docstrings add the
*why/what* that annotations can't.

> ruff's `convention = "google"` selects which `D` rules run — it does **not**
> hard-reject a well-formed NumPy `Parameters` block on its own (and the `DOC`
> pydoclint rules only run under ruff's unstable `preview`, which pyclawd does not
> select). Treat Google style as the rule, upheld by review and agents — write
> `Args:`/`Returns:`, never NumPy sections.

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

Representative `D` rules enforced (Google convention, tests exempt):

- `D103` — every public function needs a docstring
- `D205` — blank line between summary and body
- `D416` — section names end with a colon (`Args:` not `Args`)

### Opting out / changing convention for an existing repo

Set it once in `pyproject.toml` — no docstrings need rewriting:

```toml
# NumPy-style repo (scientific / pandas-ecosystem)
[tool.ruff.lint.pydocstyle]
convention = "numpy"

# No docstring enforcement at all (legacy codebase, gradual adoption)
[tool.ruff.lint]
ignore = ["D", "DOC"]

# Enforce style on existing docstrings but don't require them everywhere yet
[tool.ruff.lint]
ignore = ["D100", "D101", "D102", "D103", "D104", "D105", "D106", "D107"]
```

Read the current `pyproject.toml` before writing docstrings — matching the existing
convention matters more than any default.

## `--fix` / `--check` doctrine

- Use mutating verbs (`format`, `lint --fix`, `check --fix`) while iterating locally.
- Use non-mutating verbs (`format --check`, plain `lint`, plain `check`) as gates —
  they never rewrite files. This is what CI runs.
- Always finish with a clean `pyclawd check` before declaring work done or opening
  a PR.
