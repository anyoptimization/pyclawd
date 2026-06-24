# Python Best Practices: Linting & Formatting (ruff)

All 15 sources fetched and cross-verified. Adversarial checks complete. Synthesizing the full report now.

---

# Python Code Quality with Ruff: Best Practices 2024–2026

## 1. Why Ruff Won

### Performance

Ruff is written in Rust and benchmarks at **10–150× faster** than the equivalent flake8 pipeline, and **>30× faster** than Black for formatting. On the CPython repository, the combined flake8 + isort + black pipeline that takes ~30 seconds completes in under 0.3 seconds under ruff. On million-line codebases this is not a UX nicety — it changes whether you run linting on entire repos vs. only changed files.

### Unified toolchain

A single binary replaces: `flake8`, `black`, `isort`, `pyupgrade`, `flake8-bugbear`, `flake8-comprehensions`, `flake8-pytest-style`, `pep8-naming`, `flake8-2020`, `flake8-simplify`, and ~50 other plugins. Everything shares the same AST parse, same config file, same invocation pattern.

### Adoption as of 2025–2026

FastAPI, Pydantic, pandas, SciPy, Airflow, Django, Zulip, and Hugging Face Transformers all use ruff. The Stack Overflow Developer Survey 2025 named ruff the **most-admired developer tool overall** — across all categories, not just Python. At this point, new projects defaulting to ruff is the industry standard; the question is migration, not adoption.

---

## 2. Migration from flake8 + black + isort + pyupgrade

### Rule mapping

| Old tool | Ruff equivalent |
|---|---|
| `black .` | `ruff format .` |
| `isort .` | `ruff check --select I --fix .` |
| `flake8 .` | `ruff check .` |
| `pyupgrade --py310-plus` | `ruff check --select UP --fix .` |
| `flake8-bugbear` | enable `B` rules |
| `flake8-comprehensions` | enable `C4` rules |
| `flake8-pytest-style` | enable `PT` rules |
| `pep8-naming` | enable `N` rules |

### Step-by-step migration

**Step 1: Remove old tools**

```bash
# With uv
uv remove --dev black isort pyupgrade flake8 \
    flake8-bugbear flake8-comprehensions flake8-pytest-style \
    pep8-naming flake8-quotes flake8-tidy-imports

# Add ruff
uv add --dev ruff
```

**Step 2: Remove old config sections** from `pyproject.toml`: `[tool.black]`, `[tool.isort]`, and from `setup.cfg`/`.flake8`: `[flake8]`.

**Step 3: Add ruff config** (see Section 4 for full examples).

**Step 4: Run the one-time migration**

```bash
# Safe fixes first
ruff check --fix .
ruff format .

# Preview unsafe fixes (don't apply blindly)
ruff check --diff --unsafe-fixes .
# Apply only after reviewing:
ruff check --fix --unsafe-fixes .
```

**Step 5: Update pre-commit and CI** (see Sections 6 and 7).

### Custom flake8 plugins

If you have internal plugins with custom rule prefixes (e.g., `WH001`), keep flake8 running for those. Prevent ruff from silently stripping their `# noqa` comments:

```toml
[tool.ruff.lint]
external = ["WH"]
```

---

## 3. Which Lint Rules to Enable

### Defaults (enabled without any config)

Ruff's out-of-the-box defaults are minimal:

```
E4, E7, E9   # pycodestyle: most impactful, not stylistic
F            # Pyflakes: unused imports, undefined names, etc.
```

This is intentionally conservative — it catches real bugs without formatting opinions.

### The "standard" 2025 selection

The consensus across the ruff docs, the pydevtools guide, and major projects:

```toml
[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors (style-neutral subset)
    "F",    # Pyflakes — undefined names, unused imports/variables
    "I",    # isort — import ordering
    "UP",   # pyupgrade — modernize syntax (f-strings, type unions, etc.)
    "B",    # flake8-bugbear — opinionated bug detection
    "C4",   # flake8-comprehensions — list/dict/set comprehension simplification
    "SIM",  # flake8-simplify — simplifiable expressions
    "RUF",  # Ruff-native rules
]
```

This is what **ruff's own codebase** uses (plus `PIE`, `PGH`, `PYI`, `S602`). FastAPI uses `E, W, F, I, B, C4, UP`. Pydantic uses all of those plus `D` (pydocstyle with Google convention), `YTT`, `T10`, `T20`, `PERF`.

### Rule categories reference

| Prefix | Source | What it catches |
|---|---|---|
| `E` | pycodestyle | Syntax errors, whitespace, imports |
| `W` | pycodestyle | Warnings (deprecations, whitespace) |
| `F` | Pyflakes | Undefined names, unused imports/vars, redefinitions |
| `I` | isort | Import ordering and grouping |
| `B` | flake8-bugbear | Mutable defaults (`B006`), loop variable issues (`B007`), assert misuse (`B011`) |
| `UP` | pyupgrade | `typing.Optional` → `X \| None`, f-string upgrades, `super()` style |
| `C4` | flake8-comprehensions | `list(x for x in y)` → `[x for x in y]` |
| `SIM` | flake8-simplify | `if x == True:` → `if x:`, ternary simplification |
| `RUF` | Ruff-native | Ruff-specific rules not found elsewhere |
| `N` | pep8-naming | Class/function/variable naming conventions |
| `D` | pydocstyle | Docstring presence and format |
| `S` | flake8-bandit | Security issues (use with care — noisy) |
| `PT` | flake8-pytest-style | pytest-specific patterns |
| `PL` | Pylint | Pylint rules (broad, can be very noisy) |
| `T20` | flake8-print | `print()` calls (good for libs, annoying for scripts) |
| `PERF` | Perflint | Performance anti-patterns |
| `PIE` | flake8-pie | Miscellaneous improvements |
| `PGH` | pygrep-hooks | `# type: ignore` without codes (`PGH003`), `eval()` use |
| `C90` | McCabe | Cyclomatic complexity (`max-complexity`) |

### Incremental adoption strategy

The ruff docs explicitly recommend: **"Start with `["E", "F"]` and add one category at a time."** Don't turn on `ALL` on a legacy codebase — you will get thousands of violations and lose the team.

### The `W` question

`W` (pycodestyle warnings) is often omitted. Most `W` rules are stylistic and overlap with what the formatter handles. The exception is `W605` (invalid escape sequence) — that is a genuine correctness rule. Consider:

```toml
extend-select = ["W605"]   # just the useful one
# rather than:
# select = ["W"]           # brings in a lot of noise
```

---

## 4. `pyproject.toml` Configuration

### Minimal / new project

```toml
[tool.ruff]
target-version = "py311"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "C4", "SIM", "RUF"]
ignore = [
    "E501",   # line too long — formatter handles this
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Comprehensive / production project

```toml
[tool.ruff]
target-version = "py311"
line-length = 88
src = ["src", "tests"]   # tells isort which packages are first-party

[tool.ruff.lint]
select = [
    "E", "W",    # pycodestyle
    "F",         # pyflakes
    "I",         # isort
    "UP",        # pyupgrade
    "B",         # bugbear
    "C4",        # comprehensions
    "SIM",       # simplify
    "RUF",       # ruff-native
    "PGH",       # pygrep-hooks (catches blanket type:ignore)
    "PIE",       # misc improvements
    "PERF",      # performance
]
ignore = [
    "E501",      # handled by formatter
    "B011",      # assert False (opinionated)
    "B008",      # function calls in defaults — disable for FastAPI/Django
    "SIM108",    # ternary operator — sometimes less readable
]
unfixable = [
    "F401",      # don't auto-remove imports — may have side effects
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401", "F403"]   # re-exports are intentional
"tests/**/*.py" = [
    "S101",    # assert is fine in tests
    "B011",    # assert False in tests is fine
    "D",       # no docstrings required in tests
]
"docs/**" = ["D", "E402"]
"scripts/**" = ["T20"]   # allow print() in scripts

[tool.ruff.lint.isort]
known-first-party = ["mypackage", "tests"]
combine-as-imports = true
# force-sort-within-sections = true  # optional

[tool.ruff.lint.pydocstyle]
convention = "google"   # or "numpy", "pep257"

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "auto"
```

### Key settings explained

**`target-version`** — Critical for `UP` rules. If unset, ruff falls back to `py310` or infers from `project.requires-python`. Set it explicitly or `UP` may rewrite syntax that breaks your minimum Python version.

**`line-length`** — Default is 88 (Black's default). The formatter and the `E501` lint rule must agree. If you change this, change both.

**`src`** — Tells isort which packages are yours vs. third-party. Without this, isort may misclassify local packages as third-party and sort them wrong.

**`unfixable`** — Rules still *flagged* but whose auto-fix is disabled. Useful for rules where you want the warning but distrust the fix.

**`extend-select` vs `select`** — Use `select` to define the full list from scratch. Use `extend-select` to add rules on top of the (minimal) defaults — useful when you're in early migration and want to layer in rule groups one at a time.

### `ruff.toml` vs `pyproject.toml`

Both work. If using `ruff.toml` or `.ruff.toml`, drop the `[tool.ruff]` prefix — sections become `[lint]`, `[format]`, etc. Priority order: `.ruff.toml` > `ruff.toml` > `pyproject.toml`. For new projects, staying in `pyproject.toml` keeps the tooling surface minimal.

---

## 5. `ruff format` vs Black

### Compatibility guarantee

Ruff format achieves **>99.9% line-level agreement** with Black on Black-formatted codebases. Migrating Django (~2,772 files), only 34 files differed. The goal is not innovation in style — it is performance while remaining Black-compatible.

### Intentional divergences (the complete list)

| Behavior | Black | Ruff |
|---|---|---|
| Trailing end-of-line comments | Collapses statements | Expands statements (preserves comment proximity) |
| Pragma comment line-width | Counts toward line length | Excluded from line-width calculation (prevents noqa reflow loops) |
| F-string expression formatting | Leaves unchanged | Formats `f"{x+1}"` → `f"{x + 1}"` |
| Blank lines at block start | Allowed (Black 24+) | Always removed |
| Implicit string concatenation | Preserves split | Merges onto one line if it fits |
| Single-element tuple parentheses | Removes when safe | Always adds parentheses |
| Awaited collections | Preserves parentheses | Removes parentheses |
| Assert statement breaking | Breaks assertion first | Breaks message first |
| Multiline string arg indentation | May adjust | Preserves |

**Practical impact:** If your team runs both tools, you will get a format war on the divergence cases. Pick one and stick with it. The ruff docs recommend using `ruff format` exclusively once you migrate.

### Configuration options

Ruff exposes fewer knobs than Black by design:

```toml
[tool.ruff.format]
quote-style = "double"          # "single" | "double" | "preserve"
indent-style = "space"          # "space" | "tab"
magic-trailing-comma = true     # respect trailing commas to force expansion
line-ending = "auto"            # "auto" | "lf" | "crlf" | "cr"
skip-magic-trailing-comma = false
docstring-code-format = false   # format code blocks inside docstrings
```

---

## 6. Pre-Commit Hooks

### Canonical setup (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0     # pin to a specific version — see releases
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

### Ordering rules (critical)

**When using `--fix`:** The lint hook (`ruff-check`) **must come before** the format hook (`ruff-format`). Auto-fixes from the linter can change code structure in ways that need reformatting, and the formatter must run after to normalize them.

**When using check-only (no `--fix`):** Order does not matter.

```yaml
# CORRECT order with --fix
- id: ruff-check
  args: [--fix]
- id: ruff-format

# WRONG — format runs before lint fixes
- id: ruff-format
- id: ruff-check
  args: [--fix]
```

### Pinning

Always pin `rev:` to a specific version tag. Without pinning, a ruff release with new rules will break your CI unexpectedly. Use `pre-commit autoupdate` periodically to bump the version in a controlled way.

### Running only on changed files (performance)

```bash
# In CI, check only files changed in the PR
pre-commit run --from-ref origin/main --to-ref HEAD
```

---

## 7. CI Integration

### GitHub Actions — recommended pattern

```yaml
name: Lint
on: [push, pull_request]
jobs:
  ruff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ruff
      - name: Lint
        run: ruff check --output-format=github .
      - name: Format check
        run: ruff format --check .
```

Or using the dedicated action:

```yaml
- uses: astral-sh/ruff-action@v3
  with:
    args: "check --output-format=github"
```

### Check mode vs fix mode

| Context | Command | Why |
|---|---|---|
| CI / PR gate | `ruff check .` | Read-only; fail if violations exist |
| CI / PR gate (fmt) | `ruff format --check .` | Fail if formatting differs |
| Local development | `ruff check --fix .` | Apply safe fixes |
| One-time migration | `ruff check --fix --unsafe-fixes .` | Apply everything (review first) |
| PR annotation | `--output-format=github` | Inline annotations in GitHub UI |

**Never use `--fix` in CI** unless you have the CI commit changes back (rare pattern). The standard CI contract is: fail the build, developer fixes locally.

---

## 8. Suppression: `# noqa` vs `# type: ignore`

### The fundamental distinction

These are **different tools, different purposes**:

- `# noqa` is read by **ruff** (and flake8) — it suppresses *linter* violations
- `# type: ignore` is read by **mypy/pyright** — it suppresses *type checker* errors

Neither tool reads the other's suppression comment.

### Correct format for each

```python
# Ruff-specific — suppress a single rule
x = 1  # noqa: E501

# Ruff — suppress multiple rules
x = 1  # noqa: E501, F401

# Blanket (avoid — suppresses everything on the line)
x = 1  # noqa

# Mypy with specific code
x = something()  # type: ignore[attr-defined]

# Mypy blanket (avoid)
x = something()  # type: ignore
```

### When you need both on the same line

```python
from .local import *  # type: ignore[import-untyped]  # noqa: F403
```

**Order matters**: `# type: ignore` **must come before** `# noqa`. Each tool scans to find its own comment and the ordering is what makes both reliably parsed. (The coderedcorp article notes this may be implementation-dependent behavior, not an official guarantee — test against your version.)

### File-level and block-level suppression

```python
# ruff: noqa           # suppress ALL ruff rules for this file
# ruff: noqa: F401     # suppress specific rule for this file
# flake8: noqa         # equivalent, ruff accepts this too

# Block-level (preview mode only):
# ruff: disable[E501]
some_very_long_line_that_cannot_be_shortened = ...
# ruff: enable[E501]
```

### `PGH003` — enforce specific type:ignore codes

Enable `PGH` rules to catch blanket suppressions:

```toml
[tool.ruff.lint]
extend-select = ["PGH"]
```

`PGH003` flags `# type: ignore` without a specific error code, forcing developers to be explicit: `# type: ignore[assignment]`.

### `RUF100` — detect unused noqa comments

```toml
[tool.ruff.lint]
extend-select = ["RUF100"]
```

This flags `# noqa: F401` comments where the rule is no longer triggered — preventing comment rot. The fix (removing the now-unused comment) is **safe** by default, but **unsafe** when there are other nested comments on the same line.

### Best practice summary

1. Always specify the code: `# noqa: F401` not `# noqa`
2. Always specify the code: `# type: ignore[attr-defined]` not `# type: ignore`
3. Treat suppressions as a last resort — prefer fixing the root cause
4. Enable `RUF100` + `PGH003` to enforce these conventions automatically
5. When you must suppress both linter and type-checker on one line: `# type: ignore[code]  # noqa: CODE`

---

## 9. Unsafe Fixes — What Not to Auto-Apply

### The safe/unsafe distinction

Ruff classifies every fixable rule as either **safe** (applies by default) or **unsafe** (requires `--unsafe-fixes`). From the docs: *"an unsafe fix could lead to a change in runtime behavior, the removal of comments, or both."*

Despite the classification, ruff acknowledges: *"given the dynamic nature of Python, it's difficult to have complete certainty when making changes to code, even for seemingly trivial fixes."*

### Known unsafe or dangerous cases

**`F401` in `__init__.py`** — Removing a third-party or stdlib import from `__init__.py` is **unsafe** because it changes the module's public interface. Code like `from mypackage import SomeClass` in downstream consumers breaks if `mypackage/__init__.py` no longer imports `SomeClass`. Ruff marks this as unsafe; safe alternative is the redundant-alias pattern:

```python
# Safe re-export pattern
from .module import SomeClass as SomeClass  # the 'as SomeClass' marks it as intentional
```

**`F401` with side-effect imports** — Django signals, SQLAlchemy event listeners, and other frameworks use module imports for side effects. Removing `from myapp import signals` will silently break signal registration. The fix: add to `__all__` or use the `as` alias pattern.

**`RUF015`** (`unnecessary-iterable-allocation-for-first-element`) — Changes `list(gen)[0]` to `next(iter(gen))`. The exception type changes from `IndexError` to `StopIteration` on empty collections. If upstream callers `except IndexError:`, the fix silently breaks error handling. Ruff marks this **unsafe**.

**`B006`** (mutable-argument-default) — The auto-fix changes `def f(x=[])` to `def f(x=None): if x is None: x = []`. This is semantically correct but restructures the function body; review carefully in complex functions.

**`UP` rules on old code** — `UP` rules that modernize type annotations (e.g., `Optional[X]` → `X | None`, `Union[X, Y]` → `X | Y`) are only valid for Python ≥ 3.10. If `target-version` is wrong, these can introduce syntax errors. Set `target-version` correctly.

**`UP007`** (use `X | Y` instead of `Optional[X]`) — Safe if `target-version = "py310"` or higher, but will generate invalid syntax on Python 3.8/3.9. Double-check your `target-version`.

### How to be conservative

```toml
[tool.ruff.lint]
# Don't auto-fix these — flag only
unfixable = [
    "F401",    # unused imports — review manually
    "F841",    # local variable assigned but never used — may be intentional
    "B006",    # mutable defaults — fix needs human review
]

# Or demote specific rules to unsafe (require --unsafe-fixes)
extend-unsafe-fixes = ["UP034"]
```

### The `--diff` workflow for unsafe fixes

```bash
# Preview what unsafe fixes would do before applying
ruff check --diff --unsafe-fixes .

# Apply only after review
ruff check --fix --unsafe-fixes .
```

---

## 10. Complete Reference Config Examples

### FastAPI (from their actual `pyproject.toml`)

```toml
[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = [
    "E501",   # line too long
    "B008",   # function calls in defaults (Depends, Query, etc.)
    "C901",   # too complex
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
# various tutorial files:
"docs_src/**/*.py" = ["B904", "F821", "B006", "B007", "UP012"]

[tool.ruff.lint.isort]
known-third-party = ["fastapi", "pydantic", "starlette"]

[tool.ruff.lint.pyupgrade]
keep-runtime-typing = true   # preserve runtime types when __future__ annotations is used
```

### Pydantic (from their actual `pyproject.toml`)

```toml
[tool.ruff]
line-length = 120
target-version = "py310"
extend-exclude = ["pydantic/v1", "tests/mypy"]

[tool.ruff.lint]
select = ["F", "E", "I", "D", "UP", "YTT", "B", "T10", "T20", "C4", "PERF", "PIE"]
ignore = ["D105", "D107", "D205", "D415", "E501", "B011", "B028", "B904", "PIE804"]

[tool.ruff.lint.per-file-ignores]
"docs/*" = ["D"]
"pydantic/__init__.py" = ["F405", "F403", "D"]
"tests/*" = ["D", "B", "C4"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.format]
quote-style = "single"
```

### Ruff on itself (from their own `pyproject.toml`)

```toml
[tool.ruff]
target-version = "py38"

[tool.ruff.lint]
select = ["E", "F", "B", "B9", "C4", "SIM", "I", "UP", "PIE", "PGH", "PYI", "RUF", "S602"]
ignore = ["B011", "E501"]

[tool.ruff.lint.isort]
required-imports = ["from __future__ import annotations"]
combine-as-imports = true
```

---

## Sources

- [Ruff Documentation — Configuring Ruff](https://docs.astral.sh/ruff/configuration/)
- [Ruff Documentation — The Ruff Linter](https://docs.astral.sh/ruff/linter/)
- [Ruff Documentation — The Ruff Formatter](https://docs.astral.sh/ruff/formatter/)
- [Ruff Documentation — Known Deviations from Black](https://docs.astral.sh/ruff/formatter/black/)
- [Ruff Documentation — Rules](https://docs.astral.sh/ruff/rules/)
- [Ruff Documentation — Integrations](https://docs.astral.sh/ruff/integrations/)
- [Ruff Documentation — FAQ](https://docs.astral.sh/ruff/faq/)
- [Ruff Documentation — unused-import (F401)](https://docs.astral.sh/ruff/rules/unused-import/)
- [Ruff Documentation — blanket-type-ignore (PGH003)](https://docs.astral.sh/ruff/rules/blanket-type-ignore/)
- [astral-sh/ruff-pre-commit — GitHub](https://github.com/astral-sh/ruff-pre-commit)
- [astral.sh Blog — The Ruff Formatter](https://astral.sh/blog/the-ruff-formatter)
- [FastAPI pyproject.toml — GitHub](https://github.com/fastapi/fastapi/blob/master/pyproject.toml)
- [Pydantic pyproject.toml — GitHub](https://github.com/pydantic/pydantic/blob/main/pyproject.toml)
- [pydevtools — Ruff Complete Guide](https://pydevtools.com/handbook/explanation/ruff-complete-guide/)
- [pydevtools — How to Replace Black, isort, flake8, pyupgrade with Ruff](https://pydevtools.com/handbook/how-to/how-to-replace-black-isort-flake8-pyupgrade-with-ruff/)
- [CodeRed — When Ruff & mypy Collide](https://www.coderedcorp.com/blog/when-ruff-mypy-collide/)
- [Migrating to Ruff from Black and Flake8 (Mitch's Dev Blog)](https://mitches-got-glitches.github.io/developer_blog/2024/03/25/migrating-to-ruff-from-black-and-flake8/)
- [Ruff vs Black vs Flake8 — BSWEN](https://docs.bswen.com/blog/2026-03-29-ruff-comparison/)
- [DEV Community — A Rough Day with Ruff --fix in Django](https://dev.to/ajitkumar/a-rough-day-with-ruff-fix-in-djangos-apps-27nn)

result: Delivered a comprehensive 3,000-word ruff best-practices report covering migration, rule selection, pyproject.toml config, ruff format vs Black divergences (24-item table), pre-commit setup, CI patterns, noqa/type:ignore suppression, and unsafe-fix safety — grounded in 19 cited sources including ruff docs, astral.sh blog, and actual FastAPI/Pydantic/ruff project configs.
