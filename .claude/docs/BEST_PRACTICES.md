# Python Best Practices for Agent-Driven Development

> Synthesized from 7 research domains (testing, typing, packaging, quality, project structure,
> documentation, CI/CD) plus agent-development patterns. These are the practices **we adopt in
> pyclawd projects** — not a generic guide, but an opinionated, agent-tuned set of rules.

---

## The Core Shift: Agent vs Human Coding

> **Empirical evidence:** A 2026 ETH Zurich study (arXiv:2601.20404) measured 124 real pull
> requests across 10 Python repositories. Human-curated AGENTS.md files reduced median task
> time by **28.64%** (98.6s → 70.3s) and output tokens by **16.58%**. A follow-up study
> (arXiv:2602.11988) found that LLM-generated AGENTS.md files **degraded task success by 0.5–3%
> while increasing costs by 20%+**. The rule: write AGENTS.md by hand, curate only the
> non-inferable details.

Most best-practice guides are written for humans who forget to run things, find strict configs
annoying, and want low-friction local development. **Agents change the calculus entirely:**

| What humans avoid | Why agents embrace it |
|---|---|
| `--strict-markers` (breaks on typos) | The agent always registers markers correctly |
| `strict = true` in mypy (noisy) | The agent fixes every type error immediately |
| `filterwarnings = ["error"]` (loud) | The agent treats each warning as a task to close |
| Running the full check on every change | The agent has no context-switching cost |
| Auto-fixing lint (scary) | The agent reviews every diff anyway |
| `-n auto` parallel tests | The agent doesn't care about terminal output order |
| High coverage thresholds | The agent writes tests, not excuses |

**The rule:** If a stricter setting would make an agent's life easier but a human's life harder,
adopt the stricter setting. The agent is the primary developer of pyclawd projects.

---

## 1. Testing

### Markers: mark slow, not fast

Tests are fast by default — that is the expected state. Mark exceptions only:

- `slow` — speed axis: tests that take >1s (machine learning, large data, network)
- `integration` — scope axis: tests requiring live databases, external APIs, filesystem writes
- `long` — tests too expensive for the default gate (multi-minute training runs, etc.)

Never create a `@pytest.mark.fast` or `@pytest.mark.unit` marker. Unmarked tests run in every
tier; the default gate excludes `slow` and `integration`.

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tests taking >1s — excluded from fast tier",
    "integration: tests requiring external services or filesystem",
    "long: tests too expensive for the default gate (multi-minute)",
]
```

### Always use `--strict-markers` and `--strict-config`

A typo'd marker (`@pytest.mark.siow`) silently passes without `--strict-markers`. An agent
registers markers in pyproject.toml once and never makes this mistake again — so we gain
safety for free.

```toml
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "-n", "auto",
]
```

### Three tiers — not two

| Tier | Marker filter | Wall-time target | When |
|---|---|---|---|
| `fast` | `-m "not slow and not integration"` | <30s | Smoke check, every iteration |
| `default` | `-m "not slow"` | <5 min | Every push, PR gate |
| `all` | `` (no filter) | uncapped | Nightly, pre-merge to main |

The key distinction: `fast` also excludes `integration`; `default` includes integration but not
slow. An agent can run `pyclawd test fast` after every file change and `pyclawd test run` before
declaring work done.

### Parallel by default

Always use `pytest-xdist` (`-n auto`). Trail of Bits found 67% wall-clock reduction on a real
codebase. Agents don't care about scrambled output order; they care about iteration speed.

Use `--dist=loadscope` if you have module-level shared fixtures; `--dist=worksteal` otherwise.

### Float comparisons

Always use `pytest.approx`. Never `assert result == 0.3`.

```python
assert result == pytest.approx(0.3)              # rel tolerance 1e-6
assert error == pytest.approx(0.0, abs=1e-8)     # absolute for near-zero
```

### Stochastic tests

Pin a seed explicitly. Unseeded stochastic tests are the most common cause of intermittent
failures in agent fix-loops:

```python
rng = np.random.default_rng(seed=42)
```

Or use `pytest-randomly` — it prints the seed on every run, so failures are reproducible.

### Mock discipline

Mock at system boundaries only (HTTP, DB, clock, filesystem). Never mock internal functions.
Dependency injection > `mocker.patch`. An agent that patches internals will write tests that
pass but break on refactor — exactly what makes a codebase brittle.

### Fix-loop doctrine

1. `pyclawd test failures` — see what failed
2. Fix the **cause**, not the assertion
3. `pyclawd test fix` (`pytest --lf`) — rerun only failures
4. `pyclawd test run` — verify the full default gate

Never weaken a test to make it pass.

---

## 2. Type Checking

### Strict from day one on new code

With an agent writing the code, there is no excuse for not using `strict = true`. The agent
annotates every function as it writes it. `disallow_untyped_defs` costs nothing when you start
annotated.

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_configs = true
warn_unused_ignores = true
```

### Suppress per-module, not globally

Never `ignore_missing_imports = true` at the global level. It turns every missing module into
`Any` and silences all downstream type errors. Install stub packages first (`types-requests`,
`boto3-stubs`, etc.); per-module suppress as last resort:

```toml
[[tool.mypy.overrides]]
module = ["requests.*", "boto3.*"]
ignore_missing_imports = true
```

### Specific `type: ignore` codes always

```python
result = untyped_api()  # type: ignore[no-untyped-call]  # not: # type: ignore
```

`warn_unused_ignores = true` keeps suppressions from rotting as mypy improves.

### Modern syntax for Python 3.10+

```python
# YES
def f(x: int | None) -> list[str]: ...

# NO
from typing import Optional, List, Union
def f(x: Optional[int]) -> List[str]: ...
```

### `py.typed` marker on every distributed package

Add an empty `src/mypackage/py.typed` file and declare it in pyproject.toml. Without it, type
checkers treat your package as untyped and ignore all your annotations downstream.

### Prefer `TypeIs` over `TypeGuard` for narrowing (Python 3.13+ / typing_extensions)

`TypeIs` narrows in both the `True` and `False` branch. Use `TypeGuard` only when narrowing
to an incompatible type.

---

## 3. Linting and Formatting (ruff)

### ruff replaces everything

One binary replaces flake8, black, isort, pyupgrade, flake8-bugbear, flake8-comprehensions, and
~50 plugins. Use it for both linting and formatting.

### Standard rule set for pyclawd projects

```toml
[tool.ruff.lint]
select = [
    "E", "F",    # pycodestyle + pyflakes (baseline)
    "I",         # isort
    "UP",        # pyupgrade (modernize syntax)
    "B",         # bugbear (real bug detection)
    "C4",        # comprehension simplification
    "SIM",       # simplify
    "RUF",       # ruff-native
    "PGH",       # catches blanket type:ignore (PGH003)
    "RUF100",    # unused noqa comments
]
ignore = [
    "E501",      # line length — formatter handles it
]
```

### Agents always auto-fix

In manual development, `--fix` is "scary" because the diff is large. For agents, `--fix` is
the default — we review every diff anyway. Run `ruff check --fix` and `ruff format` on every
change, not just pre-commit.

This means `pyclawd lint --fix` + `pyclawd format` should be reflexive, not deliberate.

### Unsafe fixes: review before applying

`F401` in `__init__.py`, side-effect imports, and `UP007` on wrong `target-version` are the
main dangerous cases. The agent should use `--diff` before `--unsafe-fixes`.

### Always specify suppression codes

```python
from .module import Thing  # noqa: F401  — not: # noqa
result = api()  # type: ignore[no-untyped-call]  — not: # type: ignore
```

---

## 4. Packaging and Build

### src layout — non-negotiable

Every pyclawd project uses `src/` layout. It forces a clean `pip install -e .` and prevents
the "works locally, breaks for users" class of bugs.

```
my-project/
├── src/my_package/
├── tests/
├── pyproject.toml
```

### hatchling as default build backend

hatchling is the PyPA tutorial default, supports hooks, VCS versioning, and has good editable
install support. Use `uv_build` for zero-config uv-first projects.

### VCS-driven versioning with hatch-vcs

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "vcs"

[tool.hatch.version.raw-options]
local_scheme = "no-local-version"   # required for PyPI
```

Tag a release: `git tag v1.0.0 && git push --tags`. No manual version bumps.

### Expose `__version__` via importlib

```python
import importlib.metadata
__version__ = importlib.metadata.version(__name__)
```

### Dependencies: lower-bounded in libraries, lock for apps

```toml
dependencies = [
    "httpx>=0.27",   # library: lower-bound only
    "rich~=13.0",    # compatible release
]
```

Commit `uv.lock` for apps and services. For libraries, do not commit it.

---

## 5. Project Structure and Conventions

### Every file gets a one-line module docstring

```python
"""HTTP utilities for the API client layer."""
```

This is machine-readable. `pyclawd ls` builds a code map from these one-liners. An agent
navigating an unfamiliar codebase reads the map first. `pyclawd ls --missing` finds gaps.
**Keep this list empty.**

### AGENTS.md is the agent's primary contract

The `AGENTS.md` / `CLAUDE.md` is the single highest-value documentation artifact for agent
development. It must contain:

1. Exact commands with flags (`pyclawd test fast`, not "run the tests")
2. Tech stack and Python version
3. Critical conventions the agent would otherwise get wrong
4. Three-tier boundaries: Always / Ask first / Never
5. Non-standard tooling

Optimal length: 20–150 lines. Over 300, most is ignored. Auto-generated AGENTS.md reduces
task success — write it by hand.

### .pyclawd/config.py is the single source of truth

No per-agent guessing of test commands, lint flags, or env names. Everything the agent needs
to run the project lives in config.py. Before assuming anything about a project's setup, read
`.pyclawd/config.py`.

### `.env` for secrets, never committed

```
.env            ← gitignored
.env.example    ← committed, empty values, documents required keys
```

Add gitleaks to pre-commit to catch accidental secret commits.

---

## 6. Documentation

### Docstrings: Google style with Napoleon

Google style is the most readable inline and pairs well with Sphinx Napoleon and ruff's `D`
rule set. With PEP 484 annotations, omit types from `Args`:

```python
def compute(x: float, n: int) -> float:
    """Raise x to the power of n.

    Args:
        x: The base value.
        n: The exponent.

    Returns:
        x raised to the power of n.

    Raises:
        ValueError: If n is negative.
    """
```

### Jupyter notebooks in docs: use jupyter-cache

Execute notebooks once, cache the outputs. Only re-execute when the source changes. This is
the correct architecture for agent-maintained docs: the agent edits source notebooks, the
cache ensures outputs are always current without always re-running expensive computations.

```python
# conf.py for myst-nb
nb_execution_mode = "cache"          # execute → cache → reuse
nb_execution_timeout = 120
```

### `pyclawd docs` verbs an agent uses

- `pyclawd docs build` — full build (execute + render)
- `pyclawd docs exec <page>` — re-execute a specific notebook
- `pyclawd docs failures` — list notebooks that failed to execute
- `pyclawd docs status` — cache hit/miss summary

An agent should check `pyclawd docs failures` after editing any notebook source.

---

## 7. CI/CD

### uv in CI — always

uv is 8–12x faster than pip on cold installs, near-zero on warm cache. The `astral-sh/setup-uv`
action handles caching automatically with `enable-cache: true`.

```yaml
- uses: astral-sh/setup-uv@v8.1.0
  with:
    python-version: "3.12"
    enable-cache: true
- run: uv sync --locked --all-extras --dev
```

Always use `--locked` in CI — fails the job if `uv.lock` is stale.

### Three-job pipeline

```
lint → test-fast (matrix) → test-slow (main only)
```

- `lint` runs pre-commit + mypy — fastest, no tests
- `test-fast` runs on every PR across all supported Python versions
- `test-slow` runs only on main branch pushes and release tags

Never put slow/integration tests in the required PR gate.

### Coverage

- Branch coverage (`branch = true`) — more honest than line coverage alone
- Start at current baseline, commit it, never let it drop
- `relative_files = true` is required in CI (absolute paths break coverage merging)
- 80% is the practical floor; ratchet upward with each PR
- Use `py-cov-action` for PR comments (no external service needed)

### Renovate over Dependabot for uv projects

Dependabot does not support `uv.lock`. Use Renovate with automerge for patches.

### Trusted Publishers for PyPI releases (no stored secrets)

```yaml
permissions:
  id-token: write    # OIDC — no PYPI_TOKEN secret needed
steps:
  - uses: pypa/gh-action-pypi-publish@release/v1
```

---

## 8. Agent-Specific Patterns

### Deterministic CLI surface over raw tool invocations

An agent should always call `pyclawd test fast` rather than constructing a pytest command from
scratch. This ensures the correct env, markers, config file, and PYTHONPATH are always used.
The CLI contract is the stable interface; the tool invocation is the implementation detail.

### Exit-code contract

Every pyclawd command follows:
- `0` — success
- `2` — not configured (command exists but project doesn't use this feature)
- Other — tool's own exit code (pytest failures, mypy errors, etc.)

Agents can script on exit codes without parsing output.

### `pyclawd doctor` before debugging anything

When imports fail, tests fail to collect, or the env looks wrong, run `pyclawd doctor` first.
It probes every tool dependency and reports OK/WARN/FAIL in a machine-readable format. This
eliminates a whole class of "why is this broken" debugging.

### Machine-readable output for agent consumption

When running tools in fix-loops, use structured output where available:
- `ruff check --output-format=json` for programmatic error parsing
- `pytest --tb=short -q` for compact, scannable failure output
- `mypy --no-pretty` for single-line error format

### Code map first, then read files

Before editing an unfamiliar subsystem, run `pyclawd ls <dir>` to get the map of files and
their purpose. This is faster than reading every file and surfaces the right entry points.

### Never bypass hooks

An agent blocked by a pre-commit hook must fix the underlying issue, not run `git commit
--no-verify`. Add this explicitly to AGENTS.md: `Never: git commit --no-verify`. Pre-commit
hooks are the automated guardrails that fire exactly when the agent's change doesn't meet the
standard — bypassing them defeats the entire quality system.

### Avoid "God Prompt" functions

Agents given too broad a scope in one prompt create 300–500 line functions (the "God Prompt"
anti-pattern). Break tasks into smaller, named units. The code map (`pyclawd ls`) helps agents
verify that a utility they need already exists before creating a duplicate — **duplicate
divergence** (same utility reimplemented slightly differently per session) is the most common
structural damage from agent-coded projects.

### Never leave `pyclawd check` red

The gate is: `format-check → lint → typecheck → test`. An agent declaring "done" with a
failing gate is declaring incorrect work done. The gate is the definition of done.

### All CLIs must be non-interactive by default

Any pyclawd command that prompts for input must detect TTY and short-circuit in non-interactive
mode. Pattern: `if not sys.stdin.isatty(): use_defaults()`. Add `--yes`/`--non-interactive`
flags for cases where TTY detection is wrong. Never block on `[Y/n]` in a subprocess an agent
calls — the agent will time out or loop.

### Scaffold output should be immediately green

A freshly `pyclawd new`-ed project should pass `pyclawd check` with zero changes. If scaffold
output has lint violations, unregistered markers, or failing type checks, the scaffold is broken.

---

## Quick-Reference Checklist

| Topic | Rule |
|---|---|
| Tests: markers | Mark `slow` and `integration` only; never `fast`/`unit` |
| Tests: config | `--strict-markers --strict-config` always in addopts |
| Tests: parallelism | `-n auto` in addopts |
| Tests: tiers | fast (not slow+integration) / default (not slow) / all (no filter) |
| Tests: floats | `pytest.approx` — never `==` on floats |
| Tests: stochastic | `seed=42` explicitly or `pytest-randomly` |
| Typing: new code | `strict = true` from day one |
| Typing: suppressions | Always specify code: `# type: ignore[attr-defined]` |
| Typing: distribution | `py.typed` in every published package |
| Linting: rules | `E F I UP B C4 SIM RUF PGH RUF100` |
| Linting: agent behavior | Always `--fix` + `ruff format`; treat lint as auto-repaired not warned |
| Packaging: layout | `src/` always |
| Packaging: versioning | `hatch-vcs` (git tags → version) |
| Packaging: `__version__` | `importlib.metadata.version(__name__)` |
| Structure: module docs | One-liner docstring on every `.py` file |
| Structure: agent docs | `AGENTS.md` with exact commands, boundaries |
| CI: package manager | `uv` + `--locked` + `enable-cache: true` |
| CI: pipeline | lint → fast tests → slow tests (main only) |
| CI: coverage | branch coverage, `relative_files = true`, floor + ratchet |
| CI: gate | Never require slow/integration in PR required checks |
| Agent: CLI | Always use `pyclawd <verb>`; never raw tool invocations |
| Agent: done criteria | `pyclawd check` green + `pyclawd doctor` exit 0 |
