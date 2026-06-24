---
name: pyclawd-quality
description: Run pyclawd's code-quality toolchain — lint, format, typecheck, descriptions — and the aggregate `pyclawd check` gate. Covers single-file scoping for parallelization, --fix, --skip, --log, and the DescriptionConfig knobs. Use when cleaning up code, before a commit or PR, or when asked "is this code good / ready".
when_to_use: Tidying or finishing code, before committing/opening a PR, checking a single file in parallel, or any "is this ready / is this clean" check. `pyclawd check` is the canonical "am I done" gate.
---

# pyclawd-quality

Lint / format / typecheck / descriptions — plus one aggregate gate. Every tool's
argv comes from the project's `.pyclawd/config.py` (`QualityConfig`) — nothing
about ruff/mypy is hardcoded. If quality is unconfigured, the affected command
self-reports and exits 2 instead of crashing.

---

## Commands

| Task | Command |
|---|---|
| Lint (report only) | `pyclawd lint` |
| Lint and autofix | `pyclawd lint --fix` |
| Lint a single file / dir | `pyclawd lint src/mypkg/foo.py` |
| Format files in place | `pyclawd format` |
| Format check (no writes) | `pyclawd format --check` |
| Format a single file / dir | `pyclawd format src/mypkg/foo.py` |
| Type-check | `pyclawd typecheck` |
| Type-check a single file / dir | `pyclawd typecheck src/mypkg/foo.py` |
| Aggregate gate (the "done" check) | `pyclawd check` |
| Gate on one file (parallelization) | `pyclawd check src/mypkg/foo.py` |
| Gate on multiple files | `pyclawd check src/foo.py src/bar.py` |

---

## `pyclawd check` — the aggregate gate

Runs all quality steps **regardless of individual failures** so the full picture
is visible in one shot. Output is always printed **inline**. The `test` step runs
only if all quality steps passed.

```bash
pyclawd check                        # full project: format-check → lint → typecheck → test
pyclawd check --fix                  # autofix format+lint, then check everything
pyclawd check --skip test            # quality only, no tests
pyclawd check --skip typecheck       # format + lint only
pyclawd check --fail-fast            # stop at the first failure (CI mode)
pyclawd check --log                  # also write each step's output to a log file
pyclawd check src/mypkg/foo.py       # scope quality steps to one file
pyclawd check src/mypkg/             # scope to a directory
pyclawd check src/a.py src/b.py      # scope to multiple files
```

Summary always printed after all steps:
```
  ✓  format-check
  ✗  lint  (exit 1)
  ✓  typecheck
  ✓  descriptions
  ·  test  (skipped — fix quality first)
```

`--log` additionally writes each failing quality step to a file and shows the
path in the summary — use for CI artifacts or when you want a persistent record.

### Single-file / path scoping

Paths are appended to each quality-step command. **Quality cmds must be
target-less** for this to work:

```python
# ✓ correct — target-less; tool reads its scope from pyproject.toml config
QualityConfig(lint_cmd=["ruff", "check"], typecheck_cmd=["mypy"])

# ✗ wrong — baked-in target; pyclawd check foo.py → mypy mypkg foo.py
#            → "Duplicate module" or whole-package scan instead of per-file
QualityConfig(lint_cmd=["ruff", "check", "mypkg"], typecheck_cmd=["mypy", "mypkg"])
```

mypy also needs these in `[tool.mypy]` to avoid "Duplicate module" when given a
single path:
```toml
explicit_package_bases = true
mypy_path = "."
```
The scaffold template includes both automatically.

---

## Descriptions step

When `"descriptions"` is in `quality.check_sequence`, `pyclawd check` verifies
that every eligible source file has a one-line top-of-file description (module
docstring or leading `#` comment). It runs alongside the other quality steps —
not after them — so it's never skipped due to format/lint failures.

Configure which files are checked via `DescriptionConfig` in `.pyclawd/config.py`:

```python
from pyclawd import Project, DescriptionConfig

project = Project(
    ...
    descriptions=DescriptionConfig(
        # include: file must match ≥1 pattern (default: Python/Cython only)
        include=[r"\.pyx?$"],
        # exclude: skip if any pattern matches (default: nothing excluded)
        exclude=[r"vendor/", r"_generated/"],
    ),
)
```

**Default behaviour** (`DescriptionConfig()` with no args):
- Only `.py` and `.pyx` files are checked — Fortran, C, data files are ignored.
- No paths are excluded.

**Common overrides:**
```python
# Exclude vendored Python
DescriptionConfig(exclude=[r"vendor/"])

# Also check Cython header files
DescriptionConfig(include=[r"\.pyx?$", r"\.pxd$"])

# Exclude generated code
DescriptionConfig(exclude=[r"_pb2\.py$", r"vendor/"])
```

`pyclawd check src/mypkg/foo.py` scopes the descriptions check to that file too
— useful when parallelizing per-file quality checks.

---

## `--fix` / `--check` doctrine

- Use mutating verbs (`format`, `lint --fix`, `check --fix`) while iterating locally.
- Use non-mutating verbs (`format --check`, plain `lint`, plain `check`) as gates
  — they never rewrite files. This is what CI runs.
- Always finish with a clean `pyclawd check` before declaring work done or
  opening a PR.
