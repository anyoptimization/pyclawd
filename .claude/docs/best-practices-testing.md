# Python Best Practices: Testing (pytest)

All sources fetched. Running adversarial verification, then synthesizing.

**Verification of key claims (3-vote check):**
- `--import-mode=importlib` recommended for new projects: CONFIRMED (pytest docs, qaskills, multiple sources) — with caveat: known issue with src layout + no editable install (GitHub #11475)
- `pytest.approx` default rel tolerance 1e-6: CONFIRMED (pytest docs, O'Reilly, codecut.ai all agree)
- PyPI test suite 81% faster with xdist + path restriction: CONFIRMED (Trail of Bits 2025 firsthand account)
- Mark-slow-not-fast doctrine: CONFIRMED (pytest-skip-slow plugin, xarray issue, official marker docs all show "slow" as the mark)
- `--strict-markers` turns typos into errors not warnings: CONFIRMED (pytest docs + multiple practice guides)
- Factory fixtures returning functions: CONFIRMED (pytest official docs)
- `tmp_path` returns `pathlib.Path`: CONFIRMED (pytest docs)

No claims refuted. Now writing the full synthesis.

---

# Python pytest Best Practices: 2024–2026 Synthesis

## 1. Test Organization: Directory Layout

### The Consensus Layout (src + separate tests/)

The overwhelming 2024-2026 consensus is the **src layout with tests outside the package**:

```
my_project/
├── pyproject.toml
├── src/
│   └── my_package/
│       ├── __init__.py
│       ├── models/
│       └── services/
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── models/
    │   └── services/
    ├── integration/
    └── e2e/
```

**Why `src/` layout:** Prevents pytest from accidentally importing the working-tree copy of your package instead of the installed/editable version. This was historically a subtle trap with `prepend` import mode — the `src/` barrier forces a clean separation. Both pytest's official "Good Integration Practices" doc and virtually every 2025-2026 guide treat it as the default starting point.

**Why tests/ outside the package:** Tests don't ship in the distribution; keeping them outside avoids deployment artifacts and means you test the installed package (via `pip install -e .`) rather than the raw source tree.

**For libraries/small projects:** Embedding tests inside the package (e.g., `src/my_package/tests/`) is acceptable and can improve co-location, but requires `__init__.py` in the tests directories.

### Subdirectory Tiering vs. Flat Structure

The **Testing Pyramid** approach of `tests/unit/`, `tests/integration/`, `tests/e2e/` gives developers an immediate high-level orientation. For projects following this pattern, mirror the source structure inside each tier:

```
tests/unit/models/test_user.py     ← mirrors src/my_package/models/user.py
tests/unit/services/test_billing.py
```

For smaller projects or those primarily using markers for tiering, a flat `tests/` is perfectly fine — let markers carry the classification instead of directories.

### conftest.py Placement Strategy

- **`tests/conftest.py`** — broadly shared fixtures: database connections, HTTP clients, global monkeypatches
- **`tests/unit/conftest.py`** — fixtures scoped to unit tests only
- **`tests/integration/conftest.py`** — fixtures requiring live services
- Never put test *functions* in conftest.py — only fixtures and hooks

---

## 2. pytest Configuration: pyproject.toml

The authoritative home for pytest configuration in 2024-2026 is `pyproject.toml` under `[tool.pytest.ini_options]`. `pytest.ini` still works but is redundant if you already have `pyproject.toml`.

### Production-Ready Baseline

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",                        # show extra test summary for all except passed
    "--strict-markers",           # typo'd marker → error, not silent ignore
    "--strict-config",            # unknown config keys → error
    "--import-mode=importlib",    # recommended for new projects (see caveat below)
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services",
    "smoke: critical-path tests that must pass in every run",
    "long: marks tests too expensive for the default gate",
]
```

**`-ra` flag:** Shows a short summary of all non-passed tests (skipped, xfailed, errors) at the end. Far more useful than the default which shows nothing.

**`--strict-markers`:** Turns an unregistered marker like `@pytest.mark.siow` (typo of `slow`) from a silent warning into an error. This is among the highest-value single-line additions to any config — it prevents entire test categories silently not running.

**`--strict-config`:** Rejects unknown config keys. Prevents silent misconfiguration.

**`testpaths = ["tests"]`:** Critical for performance. The Trail of Bits 2025 case study on PyPI's test suite found that restricting pytest's scan path reduced *collection time alone* from 7.84s to 2.60s — a 66% reduction before any test ran.

### Import Mode Caveat

`--import-mode=importlib` is pytest's official recommendation for new projects; it does not mutate `sys.path` when importing test modules. However, there is a **known limitation** (GitHub issue #11475): when using a `src/` layout without an editable install (`pip install -e .`), importlib mode can cause `ModuleNotFoundError` for the package under test. The workaround is either:
- Always use `pip install -e .` (strongly recommended anyway for dev workflows), or
- Fall back to `prepend` mode and add `pythonpath = ["src"]` to your config:

```toml
[tool.pytest.ini_options]
addopts = ["--import-mode=prepend"]  # or omit — prepend is still the default
pythonpath = ["src"]
```

---

## 3. Markers: Registration, Strict Enforcement, and the Slow/Fast Doctrine

### Registering Markers

Two equivalent approaches — pick one and be consistent:

**In `pyproject.toml`** (preferred — one file):
```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services",
]
```

**In `conftest.py`** (useful when markers are generated dynamically):
```python
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests requiring external services"
    )
```

Both approaches register before test collection. The description after the colon is surfaced by `pytest --markers` and serves as inline documentation.

### The Mark-Slow-Not-Fast Doctrine (2024-2026 Consensus)

**Mark slow tests, not fast ones.** This is the near-universal 2024-2026 recommendation:

- Tests are fast by default — that is the expected state.
- Slow tests are the exception; they earn a marker.
- Running `pytest` with no flags runs everything. Running `pytest -m "not slow"` skips the heavies.
- The default CI gate typically excludes `slow` and `long`; a nightly or pre-merge full suite includes them.

**Why not mark fast?** Marking fast tests with `@pytest.mark.fast` requires maintaining a second set of markers that grow stale — every new test that isn't marked `fast` gets silently excluded from fast runs. This is the same failure mode that `--strict-markers` protects against at the marker level.

The [`pytest-skip-slow`](https://pypi.org/project/pytest-skip-slow/) plugin (by Python Testing with pytest author Brian Okken) codifies this: `@pytest.mark.slow` tests are skipped by default; `--slow` re-includes them. Zero config beyond a `pip install`.

**DIY conftest hook** (no plugin required) — the officially documented pattern:

```python
# conftest.py
import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return  # --runslow given: do not skip slow tests
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
```

Usage:
```bash
pytest              # skips slow tests
pytest --runslow    # includes slow tests
```

### Marker Expression Syntax

```bash
pytest -m "not slow"                      # exclude slow
pytest -m "smoke"                         # only smoke
pytest -m "integration and not slow"      # integration, but fast only
pytest -m "unit or smoke"                 # union
```

---

## 4. Speed Tiers: Fast Smoke, Default Gate, Full Suite

The tiered approach is stable across all authoritative 2024-2026 sources. The exact names vary but the pattern is consistent:

| Tier | Marker Filter | Wall Time Target | When to Run |
|---|---|---|---|
| **Fast/Smoke** | `-m "smoke"` or `-m "not slow and not integration"` | < 30s | Pre-commit, every save |
| **Default Gate** | `-m "not slow"` (or no -m) | < 5 min | Every push, PR check |
| **Full Suite** | No filter (includes `slow`, `long`, `integration`) | Uncapped | Nightly, pre-merge to main |

### xdist for Parallelism

`pytest-xdist` is now standard infrastructure for any suite of non-trivial size:

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = ["-n", "auto"]   # fan across all CPU cores

# or as a CI flag:
# pytest -n auto
```

The Trail of Bits 2025 PyPI case study found `--numprocesses=auto` alone cut wall-clock time by 67%. Combined with their other changes (path restriction, coverage optimization), the total was 81%.

**xdist distribution strategies:**
- `--dist=load` (default): spread tests across workers as they free up — good for heterogeneous test durations
- `--dist=loadscope`: keep test classes/modules together — necessary when tests share module-level fixtures
- `--dist=loadfile`: all tests in a file on one worker — required when tests write to shared files
- `--dist=worksteal` (newer): idle workers steal from busy queues — often best overall

**Coverage with xdist:** `pytest-cov` handles the multi-process case automatically — each worker collects its own `.coverage.workerN` file and they are merged at the end. No special configuration needed.

**Database isolation with xdist** — when tests touch a database, each worker needs its own:

```python
@pytest.fixture(scope="session")
def db_engine(worker_id):
    db_name = f"testdb_{worker_id}"
    engine = create_engine(f"postgresql://localhost/{db_name}")
    # create schema, yield, drop
    yield engine
    engine.dispose()
```

### CI Pipeline Pattern

```bash
# Fast gate (pre-commit / PR smoke)
pytest -n auto -m "smoke" --tb=short

# Default gate (every PR)
pytest -n auto -m "not slow" --cov=src/my_package --cov-fail-under=85 -ra

# Full suite (nightly)
pytest -n auto --cov=src/my_package --cov-report=xml -ra
```

---

## 5. Fixtures: Scope, Factories, Parametrize, tmp_path

### Scope Selection — the Performance Lever

| Scope | Lifetime | Use For |
|---|---|---|
| `function` (default) | Per test | Mutable state, cheap to create |
| `class` | Per test class | Class-level shared state |
| `module` | Per file | Moderate-cost objects shared across a file |
| `package` | Per package dir | Rare — objects shared across a directory |
| `session` | Entire run | Expensive, read-only resources (DB engine, HTTP session, compiled model) |

**Rule of thumb:** Use the broadest scope that preserves isolation. The database pattern (session-scoped engine + function-scoped transaction rollback) is the canonical example:

```python
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("postgresql://localhost/testdb")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

Schema is created once per run; each test gets a clean transaction that's rolled back.

### Factory Fixtures

When a test needs multiple independent instances with different configurations, return a factory function:

```python
@pytest.fixture
def make_user():
    created = []
    def _make(name="alice", role="viewer", **kwargs):
        user = User(name=name, role=role, **kwargs)
        db.session.add(user)
        created.append(user)
        return user
    yield _make
    for u in created:
        db.session.delete(u)

def test_admin_can_delete(make_user):
    admin = make_user(role="admin")
    victim = make_user(name="bob")
    assert admin.can_delete(victim)
```

The factory accumulates created objects so teardown can clean them all up, even if the test created an unpredictable number.

### Parametrize

Use `@pytest.mark.parametrize` to eliminate copy-paste tests:

```python
@pytest.mark.parametrize("input,expected", [
    (2, 4),
    (3, 9),
    (-1, 1),
    (0, 0),
])
def test_square(input, expected):
    assert square(input) == expected
```

For fixtures that should run across multiple implementations, parametrize the fixture itself:

```python
@pytest.fixture(params=["sqlite", "postgres"])
def db(request):
    return create_db(request.param)
```

Every test that uses `db` will run twice — once per backend. Use `ids=` for readable test names:

```python
@pytest.fixture(params=[json_parser, toml_parser], ids=["json", "toml"])
def parser(request):
    return request.param
```

### tmp_path and tmp_path_factory

`tmp_path` is a **function-scoped** built-in fixture returning a `pathlib.Path` to a per-test temporary directory. Prefer it over the older `tmpdir` (which returns `py.path.local`):

```python
def test_writes_output(tmp_path):
    output = tmp_path / "result.txt"
    my_function(output)
    assert output.read_text() == "expected"
```

For session-scoped shared temp directories (e.g., a downloaded dataset shared across all tests), use `tmp_path_factory`:

```python
@pytest.fixture(scope="session")
def downloaded_dataset(tmp_path_factory):
    path = tmp_path_factory.mktemp("data")
    download_fixture_data(path / "dataset.csv")
    return path
```

pytest cleans up `tmp_path` directories from the last 3 test runs automatically (configurable via `--basetemp`).

---

## 6. Avoiding Brittle Tests

### Float Comparisons: pytest.approx

Never write `assert result == 0.3` for floating-point arithmetic. Use `pytest.approx`:

```python
# Wrong — fails due to floating-point representation
assert 0.1 + 0.2 == 0.3

# Right
assert 0.1 + 0.2 == pytest.approx(0.3)

# Lists, tuples, numpy arrays — all work
assert [0.1 + 0.2, 0.4 + 0.2] == pytest.approx([0.3, 0.6])

# Dicts
assert {"a": 0.1 + 0.2} == pytest.approx({"a": 0.3})
```

**Default tolerances:**
- Relative: `1e-6` (one part in a million) — the default for most numeric tests
- Absolute: `1e-12` — applied when numbers are close to zero (relative tolerance breaks down near zero)

**Custom tolerances:**
```python
# Looser relative tolerance for ML results
assert model_accuracy == pytest.approx(0.95, rel=1e-2)  # ±1%

# Absolute tolerance when result should be near zero
assert error_term == pytest.approx(0.0, abs=1e-5)
```

**When to use absolute vs relative:** Use `abs` when comparing values that can be zero or near-zero (relative tolerance would demand impossible precision). Use `rel` (the default) for all other cases. For ML-style comparisons where the scale varies, `rel` is almost always correct.

### Stochastic and Random Tests

**Option 1: Seed explicitly in the test** — deterministic, portable, zero dependencies:

```python
import random, numpy as np

def test_shuffled_batch():
    rng = np.random.default_rng(seed=42)  # modern numpy API
    data = rng.integers(0, 100, size=1000)
    result = my_algorithm(data)
    assert result.mean() == pytest.approx(49.5, rel=0.05)
```

**Option 2: `pytest-randomly`** — randomizes test order *and* resets `random.seed()` / `np.random.seed()` before each test using a per-run seed that is printed:

```
platform linux -- Python 3.12.3, pytest-8.2.0, pytest-randomly-3.15.0
Using --randomly-seed=1234567890
```

Reproduce a specific failure with `pytest --randomly-seed=1234567890`. Install via `pip install pytest-randomly`; no config needed.

**Option 3: Statistical tolerance** — for inherently stochastic outputs, test properties over many samples rather than exact values:

```python
def test_distribution_is_uniform():
    counts = Counter(random_choice(["a", "b", "c"]) for _ in range(10_000))
    for v in counts.values():
        assert v == pytest.approx(10_000 / 3, rel=0.1)  # within 10%
```

**Autouse seed fixture** (conftest.py pattern for NumPy-heavy projects):

```python
@pytest.fixture(autouse=True)
def fixed_seed():
    np.random.seed(0)
    random.seed(0)
    yield
    # No teardown needed — each test resets on entry
```

### Don't Mock Internals

The 2024-2026 consensus (consistent across pytest docs, pytest-with-eric, mergify, codilime):

- **Mock at system boundaries** — external HTTP APIs, databases, filesystem, clocks — not at internal function calls
- **Test behavior, not implementation** — if a refactor changes which internal function is called but produces the same observable output, the test should still pass
- **Dependency injection over global patching** — make dependencies explicit parameters so tests can supply substitutes directly rather than patching globals:

```python
# Fragile: patching internals
def test_sends_email(mocker):
    mocker.patch("my_package.notifications.smtplib.SMTP")  # implementation detail
    send_welcome_email("user@example.com")

# Robust: inject the transport
def test_sends_email():
    transport = FakeTransport()
    send_welcome_email("user@example.com", transport=transport)
    assert transport.sent[0]["to"] == "user@example.com"
```

**When mocking is legitimate:**
- External HTTP APIs (use `responses` or `httpretty`)
- Time (`freezegun` or `mocker.patch("time.time", return_value=...)`)
- File system for tests that otherwise need real I/O (prefer `tmp_path` instead when feasible)
- Third-party services you don't control

---

## 7. Fixtures and conftest.py: House Rules

```python
# tests/conftest.py — canonical patterns

import pytest

# 1. Expensive shared resource — session scope
@pytest.fixture(scope="session")
def app_client():
    app = create_app(testing=True)
    with app.test_client() as client:
        yield client

# 2. Factory pattern — function scope, multiple instances
@pytest.fixture
def make_order():
    def _make(product="widget", qty=1, **kwargs):
        return Order(product=product, qty=qty, **kwargs)
    return _make

# 3. autouse for cross-cutting concerns (use sparingly)
@pytest.fixture(autouse=True)
def reset_cache():
    yield
    cache.clear()

# 4. Marker-based fixture activation
@pytest.fixture(autouse=True)
def require_db(request, db_session):
    if request.node.get_closest_marker("integration"):
        # only activate for integration-marked tests
        pass
    # function-scoped, no overhead for non-integration tests
```

**Key rules:**
- One state-changing action per fixture — tight setup/teardown coupling prevents orphaned resources on failure
- Yield for teardown, not `request.addfinalizer` (cleaner, same semantics)
- Request only what you need — fixtures that declare many dependencies become slow and fragile
- Never import fixtures — pytest wires them by name automatically; manual imports cause double-execution

---

## 8. addopts: Recommended Complete Config

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",                        # summary for all non-passed
    "--strict-markers",           # typos → error
    "--strict-config",            # unknown keys → error
    "-n", "auto",                 # parallel (requires pytest-xdist)
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services",
    "smoke: critical-path tests",
    "long: marks tests too expensive for default gate",
]
filterwarnings = [
    "error",                      # all warnings → errors (surfacing debt)
    "ignore::DeprecationWarning:third_party_lib",  # suppress specific noisy deps
]
```

**`filterwarnings = ["error"]`:** Promotes all warnings to errors. Controversial but increasingly common in 2025 projects — it forces you to fix deprecation debt rather than let it accumulate silently. Add specific ignores for third-party libraries you can't control.

**Do not put `-x` (stop on first failure) in addopts** — it should stay a developer convenience flag, not a default, because CI needs to see all failures at once.

---

## Summary: The 2025-2026 Checklist

| Practice | Setting/Pattern |
|---|---|
| src layout | `src/my_package/` + `tests/` separate |
| Config location | `[tool.pytest.ini_options]` in `pyproject.toml` |
| Restrict scan | `testpaths = ["tests"]` |
| Typo safety | `--strict-markers`, `--strict-config` in `addopts` |
| Import mode | `--import-mode=importlib` (with editable install) |
| Parallel by default | `-n auto` (xdist) |
| Mark slow, not fast | `@pytest.mark.slow`; default runs everything; exclude with `-m "not slow"` |
| Skip slow by default | conftest hook with `--runslow`, or `pytest-skip-slow` |
| Float equality | `pytest.approx(expected, rel=1e-6)` or `abs=` for near-zero |
| Stochastic tests | `pytest-randomly`, or explicit `seed=42` in test body |
| Mock discipline | Mock boundaries (HTTP, DB, clock), not internals |
| Fixture scope | Broadest scope that preserves isolation; session engine + function rollback |
| Factories | Return a `_make(...)` function, collect for cleanup |
| Temp files | `tmp_path` (function) / `tmp_path_factory` (session) |
| Speed tiers | smoke (<30s) / default gate (~5min, no `slow`) / full suite (nightly) |

---

**Sources:**
- [pytest Good Integration Practices (official docs)](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [pytest How to mark test functions (official docs)](https://docs.pytest.org/en/stable/how-to/mark.html)
- [pytest Working with custom markers (official docs)](https://docs.pytest.org/en/stable/example/markers.html)
- [pytest How to use fixtures (official docs)](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [pytest import mechanisms and sys.path (official docs)](https://docs.pytest.org/en/stable/explanation/pythonpath.html)
- [Making PyPI's test suite 81% faster — Trail of Bits Blog, May 2025](https://blog.trailofbits.com/2025/05/01/making-pypis-test-suite-81-faster/)
- [Pytest Best Practices 2026: Fixtures, Markers, Config — QASkills](https://qaskills.sh/blog/pytest-best-practices-2026)
- [pytest-skip-slow by Brian Okken (pytest-dev)](https://github.com/okken/pytest-skip-slow)
- [pytest-randomly (pytest-dev)](https://github.com/pytest-dev/pytest-randomly)
- [pytest-xdist (PyPI)](https://pypi.org/project/pytest-xdist/)
- [5 Best Practices For Organizing Tests — Pytest with Eric](https://pytest-with-eric.com/pytest-best-practices/pytest-organize-tests/)
- [Ultimate Guide To Pytest Markers — Pytest with Eric](https://pytest-with-eric.com/pytest-best-practices/pytest-markers/)
- [Stop Flaky Float Tests with pytest.approx() — CodeCut](https://codecut.ai/stop-flaky-float-tests-with-pytest-approx/)
- [Testing randomness — Python Testing & CI tutorial (Ed Bennett)](https://edbennett.github.io/python-testing-ci/05-randomness/index.html)
- [Common Mocking Problems — Pytest with Eric](https://pytest-with-eric.com/mocking/pytest-common-mocking-problems/)
- [Testing with Python part 3: pytest setup — Bite code!](https://www.bitecode.dev/p/testing-with-python-part-3-pytest)
- [Advanced Pytest Patterns: Parametrization and Factory Methods — Fiddler AI Blog](https://www.fiddler.ai/blog/advanced-pytest-patterns-harnessing-the-power-of-parametrization-and-factory-methods)
- [13 Proven Ways To Improve Test Runtime With Pytest — Pytest with Eric](https://pytest-with-eric.com/pytest-advanced/pytest-improve-runtime/)
- [Same Pytest fixtures with different scopes — pawamoy's website](https://pawamoy.github.io/posts/same-pytest-fixtures-with-different-scopes/)
- [Comparing floating point numbers: pytest.approx — O'Reilly (pytest Quick Start Guide)](https://www.oreilly.com/library/view/pytest-quick-start/9781789347562/c2d7be12-0e10-4198-8c7e-84e353113208.xhtml)
- [pytest tmp_path documentation (official)](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [Mark slow tests xarray issue #1309 (real-world adoption)](https://github.com/pydata/xarray/issues/1309)

result: Comprehensive 2024-2026 pytest best practices report covering test layout, markers (mark-slow doctrine), fixtures (scope/factory/parametrize/tmp_path), speed tiers, brittle-test avoidance (pytest.approx, seeding, mock discipline), and pyproject.toml addopts — with concrete configs and 22 cited sources.
