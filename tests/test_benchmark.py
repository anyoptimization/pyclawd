"""Tests for the performance-regression oracle (:mod:`pyclawd.benchmark` + its plugin)."""

from __future__ import annotations

import textwrap

import pytest

from pyclawd.benchmark import BenchmarkComparison, compare_time, make_entry, measure

pytest_plugins = ["pytester"]


# --------------------------------------------------------------------------- #
# Engine — make_entry / compare_time / measure.
# --------------------------------------------------------------------------- #


def test_make_entry_omits_default_rtol() -> None:
    assert make_entry(0.5) == {"seconds": 0.5}
    assert make_entry(0.5, rtol=0.1) == {"seconds": 0.5, "rtol": 0.1}


def test_compare_time_within_tolerance_passes() -> None:
    entry = make_entry(1.0)  # rtol default 0.25 → limit 1.25
    assert compare_time(1.0, entry).ok
    assert compare_time(1.2, entry).ok
    assert compare_time(1.25, entry).ok


def test_compare_time_regression_fails() -> None:
    result = compare_time(2.0, make_entry(1.0))
    assert isinstance(result, BenchmarkComparison)
    assert not result.ok
    assert result.ratio == pytest.approx(2.0)
    assert "slower" in result.detail


def test_compare_time_speedup_is_ok_but_noted() -> None:
    result = compare_time(0.4, make_entry(1.0))
    assert result.ok
    assert "faster" in result.detail


def test_compare_time_per_entry_rtol_overrides_default() -> None:
    entry = make_entry(1.0, rtol=1.0)  # tolerate up to 2x
    assert compare_time(1.9, entry).ok
    assert not compare_time(2.5, entry).ok


def test_measure_runs_warmup_plus_repeat_and_returns_float() -> None:
    calls: list[int] = []
    best = measure(lambda: calls.append(1), warmup=2, repeat=3)
    assert len(calls) == 5  # 2 warm-up + 3 timed
    assert isinstance(best, float) and best >= 0.0


# --------------------------------------------------------------------------- #
# Plugin — record then compare, and catch a regression. Relies on the pytest11
# entry-point auto-registration (same harness as the golden plugin tests).
# --------------------------------------------------------------------------- #


def _bench_test_file() -> str:
    return textwrap.dedent(
        """
        import pytest

        @pytest.mark.benchmark
        def test_speed():
            sum(range(1000))
        """
    )


def _args(bench_dir: str, *extra: str) -> tuple[str, ...]:
    return (
        "-p",
        "no:cacheprovider",
        "-o",
        f"benchmark_dir={bench_dir}",
        "-o",
        "benchmark_marker=benchmark",
        "-o",
        "benchmark_warmup=0",
        "-o",
        "benchmark_repeat=2",
        "-m",
        "benchmark",
        *extra,
    )


def test_plugin_records_then_compares(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(test_speed=_bench_test_file())
    bench_dir = pytester.path / "baselines"

    recorded = pytester.runpytest_subprocess(*_args(str(bench_dir), "--benchmark-update"))
    recorded.assert_outcomes(passed=1)
    assert (bench_dir / "test_speed.json").exists()

    compared = pytester.runpytest_subprocess(*_args(str(bench_dir)))
    compared.assert_outcomes(passed=1)


def test_plugin_missing_baseline_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(test_speed=_bench_test_file())
    result = pytester.runpytest_subprocess(*_args(str(pytester.path / "empty")))
    result.assert_outcomes(failed=1)


def test_plugin_flags_regression(pytester: pytest.Pytester) -> None:
    import json

    pytester.makepyfile(test_speed=_bench_test_file())
    bench_dir = pytester.path / "baselines"
    pytester.runpytest_subprocess(*_args(str(bench_dir), "--benchmark-update")).assert_outcomes(
        passed=1
    )
    # Tamper the baseline to an impossibly fast time with zero tolerance → regression.
    baseline = bench_dir / "test_speed.json"
    data = json.loads(baseline.read_text())
    data["test_speed"] = {"seconds": 1e-9, "rtol": 0.0}
    baseline.write_text(json.dumps(data))

    result = pytester.runpytest_subprocess(*_args(str(bench_dir)))
    result.assert_outcomes(failed=1)
