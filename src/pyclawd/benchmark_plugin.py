"""Standalone pytest plugin: a ``@pytest.mark.benchmark`` test's body is timed and gated.

Tag a test ``@pytest.mark.benchmark``; its body is run a few times (warm-up + timed
repeats) and the **minimum** wall-clock is recorded to / compared against a baseline.
``pytest --benchmark-update`` (re)records baselines; the default run compares and fails
only on a slow-down beyond tolerance (a speed-up never fails).

A benchmark baseline is a *time*, which is hardware-specific, so it is **never
committed**. When driven by ``pyclawd benchmark`` the baseline directory is the
project's gitignored ``work_dir``; in bare ``pytest`` it defaults to a subdirectory of
the pytest cache (``.pytest_cache``, gitignored by default). Override it with the
``benchmark_dir`` ini option.

Like the golden plugin, this is **standalone** — it depends only on the dependency-free
:mod:`pyclawd.benchmark` engine (plus :class:`pyclawd.golden.GoldenStore` for the JSON
store), never on a ``.pyclawd/config.py``. It registers via a ``pytest11`` entry point,
so ``@pytest.mark.benchmark`` works in bare ``pytest`` with zero config. Settings are
overridable through ini options (``benchmark_dir``, ``benchmark_marker``,
``benchmark_warmup``, ``benchmark_repeat``, ``benchmark_rtol``).

Doctrine (see :mod:`pyclawd.benchmark`): the gate is one-sided (only regressions fail),
tolerance is relative and generous, and *agents compare, humans bless*. A benchmark body
is called multiple times, so it must be idempotent (no accumulating side effects).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pyclawd.benchmark import BenchmarkError, compare_time, make_entry, measure
from pyclawd.golden import GoldenStore, module_baseline_path
from pyclawd.pytest_plugin import derive_node_key

#: Default marker when nothing is configured.
DEFAULT_MARKER = "benchmark"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--benchmark-update`` flag and the ``benchmark_*`` ini settings."""
    parser.addoption(
        "--benchmark-update",
        action="store_true",
        default=False,
        help="Record/bless benchmark baselines from measured timings instead of comparing.",
    )
    parser.addini(
        "benchmark_dir",
        "Directory holding benchmark baselines (empty → a gitignored pytest-cache dir).",
        default="",
    )
    parser.addini("benchmark_marker", "Marker selecting benchmark tests.", default=DEFAULT_MARKER)
    parser.addini("benchmark_warmup", "Untimed warm-up calls before measurement.", default="1")
    parser.addini("benchmark_repeat", "Timed repetitions; the minimum is recorded.", default="5")
    parser.addini("benchmark_rtol", "Default relative slow-down tolerance.", default="0.25")


def _marker(config: pytest.Config) -> str:
    """The configured benchmark marker name (default ``benchmark``)."""
    return str(config.getini("benchmark_marker") or DEFAULT_MARKER)


def _baseline_dir(config: pytest.Config) -> Path:
    """The baseline directory: the ``benchmark_dir`` ini, else a gitignored cache dir.

    An explicit ``benchmark_dir`` is honoured (resolved against the pytest rootdir when
    relative). When it is empty — the bare-``pytest`` default — baselines go under the
    pytest cache (``.pytest_cache``), which is gitignored by default, so a
    hardware-specific timing is never accidentally committed.
    """
    raw = str(config.getini("benchmark_dir") or "").strip()
    if not raw:
        return Path(config.cache.mkdir("pyclawd_benchmark"))
    path = Path(raw)
    return path if path.is_absolute() else config.rootpath / path


def _settings(config: pytest.Config) -> tuple[int, int, float]:
    """The configured ``(warmup, repeat, rtol)`` for measuring + new baselines."""
    return (
        int(config.getini("benchmark_warmup") or 1),
        int(config.getini("benchmark_repeat") or 5),
        float(config.getini("benchmark_rtol") or 0.25),
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the benchmark marker so ``-m <marker>`` selects benchmark tests."""
    config.addinivalue_line(
        "markers",
        f"{_marker(config)}: time the test body (best-of-N) and gate it against a baseline.",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run a benchmark-marked test ourselves, timing its body, and record/compare the result.

    For a test carrying the benchmark marker, this times the function (warm-up + repeats),
    then records the best time (``--benchmark-update``) or compares it against the committed
    baseline (the default), and returns ``True`` so pytest does not call it again.
    Non-benchmark tests are left untouched.

    Args:
        pyfuncitem: The pytest function item about to be called.

    Returns:
        ``True`` when the benchmark test was handled here, else ``None``.

    Raises:
        BenchmarkError: When the timing regresses beyond tolerance, or no baseline exists
            yet in compare mode.
    """
    config = pyfuncitem.config
    if pyfuncitem.get_closest_marker(_marker(config)) is None:
        return None

    testargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    warmup, repeat, rtol = _settings(config)
    best = measure(lambda: pyfuncitem.obj(**testargs), warmup, repeat)
    _snapshot(pyfuncitem, best, rtol)
    return True


def _snapshot(pyfuncitem: pytest.Function, seconds: float, rtol: float) -> None:
    """Record or compare a measured *seconds* against the local baseline."""
    config = pyfuncitem.config
    module_file = pyfuncitem.module.__file__
    assert module_file is not None
    store = GoldenStore(module_baseline_path(_baseline_dir(config), Path(module_file).stem))
    key = derive_node_key(pyfuncitem.nodeid)

    if config.getoption("--benchmark-update"):
        store.set(key, make_entry(seconds, rtol=rtol))
        store.save()
        return

    entry: dict[str, Any] | None = store.get(key)
    if entry is None:
        raise BenchmarkError(
            f"benchmark: no baseline for {key!r} on this machine. Record it with "
            "`pytest --benchmark-update` (baselines are local + gitignored)."
        )
    result = compare_time(seconds, entry)
    if not result.ok:
        raise BenchmarkError(f"benchmark: {key}\n  {result.detail}")
