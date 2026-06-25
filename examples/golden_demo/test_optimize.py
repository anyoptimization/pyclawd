"""Worked golden example — a marked test returns its value and the plugin snapshots it."""

from __future__ import annotations

import math

import numpy as np
import pytest


def optimize(problem: str, *, seed: int) -> np.ndarray:
    """Deterministic stand-in for a seeded optimizer, returning an objective vector.

    Args:
        problem: Problem name selecting the analytic objective.
        seed: Seed that deterministically shifts the sampled point (no RNG import).

    Returns:
        The two-element objective vector for the seeded run.
    """
    x = ((seed * 2654435761) % 1000) / 1000.0
    if problem == "sphere":
        return np.array([x * x, (1.0 - x) * (1.0 - x)])
    if problem == "rosenbrock":
        return np.array([(1.0 - x) ** 2, 100.0 * (x - x * x) ** 2])
    raise ValueError(f"unknown problem {problem!r}")


@pytest.mark.golden
def test_indicator() -> float:
    """Return a float — stored as a readable rounded number in the baseline."""
    f = optimize("sphere", seed=7)
    return math.sqrt(float(f @ f))


@pytest.mark.golden
@pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
def test_front(problem: str) -> np.ndarray:
    """Return an np.array — stored as a readable nested list, one entry per case."""
    return optimize(problem, seed=42)
