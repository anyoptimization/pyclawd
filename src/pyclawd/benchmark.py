"""Performance-regression oracle engine: record best-of-N timings, prove no slow-down.

The sibling of :mod:`pyclawd.golden`. golden proves an observable *value* is
unchanged; benchmark proves the code did not get *slower*. A ``@pytest.mark.benchmark`` test's
body is timed — a few warm-up calls, then several timed calls, and the **minimum**
wall-clock is the metric (the min is the least-noisy estimator of the true cost, least
polluted by scheduler/GC hiccups). That metric is compared to a committed baseline with
a **relative** tolerance: a run fails only when it is slower than
``baseline * (1 + rtol)``. A speed-up never fails — it is reported so a human can
re-bless a new, faster baseline.

Timing is inherently noisy and machine-specific, which is why:

- the tolerance defaults generously (25%) and travels *in* the baseline entry, and
- the comparison is one-sided (only slow-downs fail).

This module reuses :class:`pyclawd.golden.GoldenStore` for the on-disk baseline (a
generic ``key → entry`` JSON store), and is otherwise dependency-free stdlib — the
engine behind the standalone :mod:`pyclawd.benchmarkmark_plugin`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BenchmarkError(AssertionError):
    """A benchmark timing regressed beyond tolerance (or has no baseline yet).

    Subclasses :class:`AssertionError` so a failed benchmark reads as an ordinary test
    failure to pytest.
    """


@dataclass(frozen=True)
class BenchmarkComparison:
    """Outcome of comparing a fresh timing against a committed baseline entry.

    Args:
        ok: Whether the new timing is within tolerance (not a regression).
        ratio: ``new / baseline`` — ``>1`` is slower, ``<1`` is faster.
        detail: Human-readable explanation.
    """

    ok: bool
    ratio: float
    detail: str


def make_entry(seconds: float, *, rtol: float = 0.25) -> dict[str, Any]:
    """Build a committed-baseline entry from a measured *seconds* (the bless path).

    Stores the inline ``seconds`` (readable — a ``git diff`` shows ``0.0021 → 0.0035``)
    plus the per-snapshot ``rtol`` when it differs from the default, so each benchmark
    owns its own tolerance.

    Args:
        seconds: The recorded best-of-N wall-clock time, in seconds.
        rtol: Relative slow-down tolerance stored for future comparisons.

    Returns:
        A JSON-serializable baseline entry.
    """
    entry: dict[str, Any] = {"seconds": seconds}
    if rtol != 0.25:
        entry["rtol"] = rtol
    return entry


def compare_time(new_seconds: float, entry: dict[str, Any]) -> BenchmarkComparison:
    """Compare a fresh timing against a stored baseline *entry*.

    The gate is one-sided: a regression (slower than ``baseline * (1 + rtol)``) fails;
    a same-or-faster timing passes. A speed-up is flagged in the detail so a human can
    choose to re-bless a tighter baseline.

    Args:
        new_seconds: The freshly measured best-of-N time, in seconds.
        entry: The committed baseline entry (``seconds`` + optional ``rtol``).

    Returns:
        A :class:`BenchmarkComparison` describing the outcome.
    """
    baseline = float(entry["seconds"])
    rtol = float(entry.get("rtol", 0.25))
    ratio = new_seconds / baseline if baseline > 0 else float("inf")
    limit = baseline * (1 + rtol)
    if new_seconds > limit:
        return BenchmarkComparison(
            ok=False,
            ratio=ratio,
            detail=(
                f"slower by {(ratio - 1) * 100:.0f}% (rtol={rtol:.0%})\n"
                f"  baseline: {baseline:.6g}s\n"
                f"  actual:   {new_seconds:.6g}s  (limit {limit:.6g}s)"
            ),
        )
    if ratio < 1 - rtol:
        return BenchmarkComparison(
            ok=True,
            ratio=ratio,
            detail=f"faster by {(1 - ratio) * 100:.0f}% — consider re-blessing the baseline",
        )
    return BenchmarkComparison(ok=True, ratio=ratio, detail="")


def measure(call: Any, warmup: int, repeat: int) -> float:
    """Time *call* (a zero-arg callable): *warmup* untimed calls, then *repeat* timed.

    Args:
        call: A zero-argument callable to time.
        warmup: Number of untimed warm-up invocations.
        repeat: Number of timed invocations; the minimum is returned.

    Returns:
        The minimum wall-clock time across the timed runs, in seconds.
    """
    import time

    for _ in range(max(0, warmup)):
        call()
    best = float("inf")
    for _ in range(max(1, repeat)):
        start = time.perf_counter()
        call()
        best = min(best, time.perf_counter() - start)
    return best
