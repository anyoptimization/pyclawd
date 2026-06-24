# pyclawd Improvement Roadmap

> Based on research across 7 Python best-practice domains (testing, typing, packaging, quality,
> project structure, docs, CI/CD) plus agent-development patterns. Items are grouped by type
> and urgency. Anything in **Fix Now** has a clear, small implementation path.

---

## Status

### Completed

**Sprint 1 — scaffold correctness (all done)**
- ✅ #1 `--strict-markers` + `--strict-config` in scaffold addopts
- ✅ #2 Markers registered in `pyproject.toml.tmpl`
- ✅ #3 `fast` ≠ `default` tier distinction fixed
- ✅ #4 `py.typed` added to scaffold
- ✅ #5 Expanded ruff rule set in scaffold
- ✅ #6 mypy strict mode in scaffold
- ✅ #7 Coverage config in scaffold
- ✅ #8 `filterwarnings = ["error"]` in scaffold
- ✅ #9 `minversion` in scaffold

**Sprint 2 — agent ergonomics (all done)**
- ✅ #10 `pyclawd check --fix` mode
- ✅ #11 `pyclawd test timings --slow-threshold` flag
- ✅ #16b `DoctorConfig`: check for pytest-xdist, pytest-cov

**Sprint 3 — new features (all done)**
- ✅ `pyclawd config` — show resolved effective configuration *(added this session; was not in original roadmap)*
- ✅ #12 `pyclawd coverage` command
- ✅ #13 `pyclawd new --ci` GitHub Actions scaffold (`ci.yml.tmpl` in template map)
- ✅ #14 `pyclawd doctor --json` machine-readable output

### Pending / Deferred
- #17 Rename `markers` dict keys (`default` → `run`)
- #18 `integration_files` vs `integration` marker unification
- #19 `uv` as default Python runner
- #20 AGENTS.md audit

---

## Fix Now (small, clear, backward-compatible)

### 1. Scaffold: add `--strict-markers` and `--strict-config` to addopts ✅

**Gap:** The scaffold template doesn't emit `--strict-markers` or `--strict-config` in
`pyproject.toml.tmpl`. A newly-scaffolded project silently ignores marker typos.

**Fix:** In `src/pyclawd/scaffold/templates/pyproject.toml.tmpl`, add to addopts:
```toml
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "-n", "auto",
]
```

**Impact:** Every `pyclawd new` project is immediately strict. Agents get safety for free.

---

### 2. Scaffold: register markers in pyproject.toml.tmpl ✅

**Gap:** `--strict-markers` without registered markers means the scaffold immediately errors
on `@pytest.mark.slow` etc. The markers must be registered.

**Fix:** Add to `pyproject.toml.tmpl`:
```toml
markers = [
    "slow: tests taking >1s — excluded from fast tier",
    "integration: tests requiring external services or filesystem",
    "long: tests too expensive for the default gate",
]
```

---

### 3. Fix tier naming: fast ≠ default ✅

**Current state in pyclawd's own config:**
```python
markers={"default": "not slow", "fast": "not slow", "all": ""},
```
`fast` and `default` have the same filter. That means `pyclawd test fast` is identical to
`pyclawd test run`. The distinction is meaningless.

**Fix (two-axis model from research):**
```python
markers={
    "fast": "not slow and not integration",   # <30s smoke tier
    "default": "not slow",                    # default gate (integration OK, slow excluded)
    "all": "",                                # everything
},
```

**Why:** `fast` should also exclude `integration` tests (which may spin up databases, network,
etc). `default` is the PR gate — integration tests are welcome here, slow tests are not.

Update this in:
- `.pyclawd/config.py` (pyclawd dogfoods itself)
- `src/pyclawd/scaffold/templates/config.py.tmpl`
- `AGENTS.md` tier documentation

---

### 4. Scaffold: add `py.typed` to the generated package ✅

**Gap:** Scaffold doesn't create `src/{{ name }}/py.typed`. Without it, downstream type
checkers treat the package as untyped and ignore all annotations.

**Fix:** Add a `py.typed.tmpl` (empty file) and generate it into the package directory. Add
to `pyproject.toml.tmpl`:
```toml
[tool.hatch.build.targets.wheel]
include = ["src/{{ name }}/py.typed"]
```

---

### 5. Scaffold: expand default ruff rule set ✅

**Current scaffold emits:** (likely minimal E, F, I)

**Fix:** Update `pyproject.toml.tmpl` to the research-backed standard set:
```toml
[tool.ruff.lint]
select = [
    "E", "F",
    "I",
    "UP",
    "B",
    "C4",
    "SIM",
    "RUF",
    "PGH",
    "RUF100",
]
ignore = ["E501"]
unfixable = ["F401"]   # flag unused imports but don't auto-remove (side-effect risk)

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]        # re-exports are intentional
"tests/**/*.py" = ["S101"]      # assert is fine in tests
```

---

### 6. Scaffold: add mypy strict mode ✅

**Current:** Scaffold likely uses minimal or no mypy config.

**Fix:** In `pyproject.toml.tmpl`:
```toml
[tool.mypy]
python_version = "{{ python_version }}"
strict = true
warn_unused_configs = true
warn_unused_ignores = true
```

Agents write annotated code from the start. Strict mode costs nothing on a new project.

---

### 7. Scaffold: add coverage config ✅

**Gap:** Scaffold doesn't configure `pytest-cov` or coverage thresholds.

**Fix:** Add to `pyproject.toml.tmpl`:
```toml
[tool.coverage.run]
source = ["src/{{ name }}"]
branch = true
relative_files = true    # required for CI

[tool.coverage.report]
show_missing = true
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
]
```
And add `--cov=src/{{ name }} --cov-report=term-missing` to test addopts.

---

### 8. Scaffold: `filterwarnings = ["error"]` ✅

Agents can fix every warning as it appears. Add to `pyproject.toml.tmpl`:
```toml
filterwarnings = [
    "error",
    # Add per-library exceptions as needed:
    # "ignore::DeprecationWarning:third_party_lib",
]
```

This surfaces deprecation debt immediately rather than letting it accumulate silently.

---

### 9. Scaffold: add `minversion` to pytest config ✅

```toml
[tool.pytest.ini_options]
minversion = "8.0"
```

Guards against running on an old pytest that doesn't support features the config uses.

---

## Add (new features, larger scope)

### 10. `pyclawd check --fix` mode ✅

**Idea:** `pyclawd check` currently runs format-check → lint → typecheck → test in check-only
mode. Add `pyclawd check --fix` that runs format → lint-fix → typecheck → test instead.

This gives agents a single command that auto-repairs everything fixable and then validates.
Current workaround is `pyclawd format && pyclawd lint --fix && pyclawd check`.

**Implementation:** In `commands/quality.py`, add `--fix` flag to the `check` command.
When `--fix`, substitute `format_cmd` for `format_check_cmd` and `lint_fix_cmd` for `lint_cmd`.

---

### 10b. `pyclawd config` — show resolved effective configuration ✅

*(Added this session — was not in the original roadmap.)*

**Idea:** `pyclawd config` prints the fully-resolved `Project` configuration as seen by
pyclawd after loading `.pyclawd/config.py`. Useful for agents and humans to confirm which
env, paths, markers, and tool options are actually in effect — especially when `--config`
or `PYCLAWD_CONFIG` is in play.

---

### 11. `pyclawd coverage` command ✅

A dedicated coverage command:
```bash
pyclawd coverage          # run tests with coverage, open report
pyclawd coverage --check  # fail if below threshold
pyclawd coverage --html   # generate HTML report
```

Currently an agent must construct the pytest+cov invocation manually. A dedicated command
surfaces the threshold, source paths, and report format from config.

**Config addition to `TestConfig`:**
```python
@dataclass(frozen=True)
class CoverageConfig:
    threshold: int = 80
    report_formats: list[str] = field(default_factory=lambda: ["term-missing"])
```

---

### 12. Machine-readable output mode (`--json` / `--machine`) ✅

**Problem:** `pyclawd doctor` output is human-readable rich text. An agent parsing it must
screen-scrape. Add `pyclawd doctor --json` that emits structured output:

```json
{
  "checks": [
    {"name": "ruff", "status": "ok", "detail": "0.9.3"},
    {"name": "mypy", "status": "warn", "detail": "not found — pip install mypy"}
  ],
  "ok": false
}
```

Similarly, `pyclawd test --json` could emit machine-readable pass/fail/skip counts.

---

### 13. `pyclawd new --ci` — generate GitHub Actions workflow ✅

Scaffold a `.github/workflows/ci.yml` that implements the research-backed three-job pipeline:
- `lint` (pre-commit + mypy)
- `test-fast` (matrix, uv, `--locked`, `not slow`)
- `test-slow` (main branch only, `slow or integration`)

Include uv caching, `--strict-config`, coverage upload. This is the gap between "pyclawd
new generates a working project" and "pyclawd new generates a fully CI-wired project".

---

### 14. `pyclawd doctor` — Django-style check structure ✅

**Current:** Doctor reports OK/WARN/FAIL with a flat function approach.

**Upgrade:** Model after Django's System Check Framework. Each check returns a typed message:
```python
@dataclass
class CheckResult:
    id: str       # e.g., "pyclawd.W001"
    severity: Literal["ok", "warn", "fail"]
    message: str  # what's wrong
    hint: str     # how to fix it
```

This enables:
- `--json` output for agent consumption (no screen-scraping)
- `SILENCED_CHECKS = ["pyclawd.W001"]` in config for known-acceptable issues
- `pyclawd doctor --json | jq '.checks[] | select(.severity == "fail")'` in CI

Errors (fail) should block `pyclawd test` from running. Warnings are advisory.

---

### 14b. `pyclawd timings --slow-threshold N` — identify marker candidates ✅

Current: `pyclawd test timings --top N` shows the N slowest tests.

Add: `pyclawd test timings --slow-threshold 1.0` lists tests taking >1s that don't have
`@pytest.mark.slow`. These are **unmarked slow tests** — the most common source of tier
inaccuracy.

The output should be directly actionable: "Add `@pytest.mark.slow` to these 3 tests."

---

### 15. `pyclawd lint --strict-mode` for F401 in `__init__.py`

`F401` is marked `unfixable` by default because auto-removing imports in `__init__.py` breaks
re-exports. Add a `--strict-mode` that enables unsafe fixes with a diff preview first:

```bash
pyclawd lint --strict-mode   # shows diff, asks for confirmation
```

This is the difference between "safe default for agents" and "thorough cleanup mode".

---

### 16. TTY detection and `--non-interactive` on `pyclawd new`

`pyclawd new` currently does TTY detection (commit 449894b). Audit all other commands that
could prompt — any interactive prompt in a subprocess an agent spawns will time out or loop.

Pattern to enforce across all commands:
```python
if not sys.stdin.isatty() or non_interactive:
    use_configured_defaults()
else:
    prompt_user()
```

Add `--non-interactive` / `--yes` as an explicit override for when the TTY check is wrong.
This is table stakes for agent-callable CLIs.

---

### 16b. `DoctorConfig` additions: check for pytest plugins ✅

Currently `doctor` checks binaries and tool files. Add checks for important pytest plugins:

```python
dev_deps = [
    "pytest",
    "pytest-xdist",      # required for -n auto
    "pytest-cov",        # required for coverage
]
```

An agent running `pyclawd test fast` with `-n auto` in addopts but without pytest-xdist
installed will get a confusing error. Doctor should surface this as WARN.

---

## Reconsider (architectural questions)

### 17. Rename `markers` dict keys for clarity

**Current:** `{"fast": "...", "default": "...", "all": "..."}`

**Issue:** The key `"default"` maps to `pyclawd test run`, not `pyclawd test default`. This
is confusing. Consider:

- Rename `"default"` → `"run"` to match the CLI verb (`pyclawd test run`)
- Or: document the mapping explicitly in config.py

---

### 18. `integration_files` vs `integration` marker — unify

Currently pyclawd has two mechanisms for excluding integration tests:
- `TestConfig.integration_files` — deselects whole files by path
- `"not integration"` in the `fast` marker expression

These are independent and can diverge. A file excluded by `integration_files` but whose tests
don't carry `@pytest.mark.integration` won't appear in `pyclawd test fast -m "integration"`
output, creating confusion.

**Options:**
- Drop `integration_files` and mandate `@pytest.mark.integration` (cleaner, requires
  one-time migration)
- Keep both but make `doctor` warn when `integration_files` is non-empty and the `fast` tier
  doesn't also say `not integration` in its marker expression

---

### 19. Consider `uv run` as the default Python runner

Currently `pyclawd python` runs via the conda env's `sys.executable`. With uv becoming the
dominant package manager, consider:
- Auto-detect `uv.lock` at repo root → offer `uv run` as the runner
- Keep conda as fallback when no `uv.lock` is present

This would make `pyclawd python script.py` equivalent to `uv run python script.py` on uv
projects, automatically respecting the uv-managed venv.

---

### 20. pyclawd-specific AGENTS.md tuning

The research confirms AGENTS.md is most valuable when it contains exact commands with flags.
Audit `AGENTS.md` and `CLAUDE.md` against the research findings:

- Are all `pyclawd test fast/run/all` commands there with their expected wall-time? ✓
- Is the three-tier doctrine (fast/default/all) explained? Partially
- Is `pyclawd test failures → fix → run` fix-loop documented? Partially
- Are the tier marker expressions explained? No — add them
- Is the distinction between `integration_files` and `integration` marker explained? No

---

## Priority Order (suggested)

### Sprint 1 — Scaffold correctness ✅ Complete
1. ✅ Add `--strict-markers` + `--strict-config` to scaffold
2. ✅ Register markers in scaffold
3. ✅ Fix `fast` ≠ `default` tier distinction
4. ✅ Add `py.typed` to scaffold
5. ✅ Expand ruff rules in scaffold
6. ✅ Add mypy strict to scaffold

### Sprint 2 — Agent ergonomics ✅ Complete
7. ✅ Add coverage config to scaffold
8. ✅ Add `filterwarnings = ["error"]` to scaffold
9. ✅ `DoctorConfig`: check for pytest-xdist, pytest-cov
10. ✅ `pyclawd check --fix` mode
11. ✅ `pyclawd test timings --slow-threshold` command

### Sprint 3 — New features ✅ Complete
12. ✅ `pyclawd config` command (show resolved configuration) *(added this session)*
13. ✅ `pyclawd coverage` command
14. ✅ `pyclawd new --ci` GitHub Actions scaffold
15. ✅ Machine-readable output (`pyclawd doctor --json`)

### Ongoing / Deferred
- #17 Rename `markers` dict keys (`default` → `run`)
- #18 Decide on `integration_files` vs marker unification
- #19 Consider uv as default runner (when uv adoption is clearer)
- #20 Audit AGENTS.md against research findings
