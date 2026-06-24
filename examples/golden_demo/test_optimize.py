"""Worked golden example — snapshotting an optimizer's observable output.

This stands in for a pymoo-style ``minimize(problem, algorithm, seed=...)`` run:
a deterministic, seeded computation that returns an objective vector. The golden
oracle proves that *refactoring the code never changes that vector* — the exact
gap the static gate (lint/format/typecheck) cannot see.

Run the gate (compare against committed baselines):

    pyclawd python -m pytest examples/golden_demo -m golden

Re-record baselines after an *intentional* behavior change (the bless step):

    PYCLAWD_GOLDEN_UPDATE=1 pyclawd python -m pytest examples/golden_demo -m golden
    git diff examples/golden_demo/golden/   # review, then commit
"""

from __future__ import annotations

import math

import pytest


def minimize(problem: str, *, seed: int) -> dict[str, object]:
    """A tiny deterministic stand-in for a seeded optimization run.

    Returns a structured result resembling pymoo's: an objective vector ``F``, a
    scalar hypervolume-like ``indicator``, and the evaluation count. Pure and
    seed-deterministic so its snapshot is stable.

    Args:
        problem: Problem name (selects the analytic objective).
        seed: Random seed (shifts the sampled point deterministically).

    Returns:
        A result dict with ``F``, ``indicator``, and ``n_eval``.
    """
    # A fixed, seed-perturbed point in [0, 1] — deterministic, no RNG import.
    x = ((seed * 2654435761) % 1000) / 1000.0
    if problem == "sphere":
        f = [x * x, (1.0 - x) * (1.0 - x)]
    elif problem == "rosenbrock":
        f = [(1.0 - x) ** 2, 100.0 * (x - x * x) ** 2]
    else:  # pragma: no cover - guard for an unknown problem
        raise ValueError(f"unknown problem {problem!r}")
    indicator = math.sqrt(sum(v * v for v in f))
    return {"F": f, "indicator": round(indicator, 12), "n_eval": 100}


@pytest.mark.golden
@pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
def test_minimize(golden, problem: str) -> None:
    """The objective vector of a seeded run must never drift across refactors.

    The parametrization gives one stable per-case key (``test_minimize[sphere]``,
    ``test_minimize[rosenbrock]``) — each with its own committed baseline entry.
    """
    result = minimize(problem, seed=42)
    golden(result["F"], label="F", rtol=1e-9)
    golden(result["indicator"], label="indicator", rtol=1e-9)


@pytest.mark.golden
def test_scalar_metric(golden) -> None:
    """A scalar baseline is stored inline so ``git diff`` shows the number move."""
    golden(minimize("sphere", seed=7)["indicator"])
