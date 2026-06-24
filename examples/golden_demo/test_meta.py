"""Meta-tests — prove the golden oracle actually bites (catches planted drift).

The council's demand: a passing golden test does not prove the oracle works.
These tests drive :mod:`pyclawd.golden` directly to show it (a) passes on a
faithful re-run, (b) **fails** on a real regression, (c) tolerates sub-tolerance
float jitter via the value fallback rather than flaking on the hash, and (d)
refuses an unserializable value instead of silently pickling.
"""

from __future__ import annotations

import math

import pytest

from pyclawd.golden import GoldenError, compare, make_entry


def test_faithful_rerun_passes() -> None:
    """An identical value matches on the fast (hash) path."""
    entry = make_entry([0.1, 0.2, 0.3])
    result = compare([0.1, 0.2, 0.3], entry)
    assert result.ok and result.fast_path


def test_planted_regression_is_caught() -> None:
    """The ``X[:, J]`` → ``X[:, np.array(J)]`` class of bug: a real value change fails.

    A change well beyond tolerance must fail even though it is "clean" code.
    """
    entry = make_entry([0.1, 0.2, 0.3], rtol=1e-9, atol=1e-12)
    result = compare([0.1, 0.25, 0.3], entry)  # 0.2 -> 0.25, a genuine drift
    assert not result.ok
    assert "beyond tolerance" in result.detail


def test_subtolerance_jitter_passes_via_value_fallback() -> None:
    """A BLAS-sized perturbation flips the hash but passes the tolerant compare.

    This is the corrected design at work: the hash is only a fast path. When it
    misses by sub-tolerance noise, the value fallback — not a flaky failure —
    decides the outcome.
    """
    entry = make_entry([1.0, 2.0, 3.0], rtol=1e-6, atol=1e-9)
    jittered = [1.0 + 1e-9, 2.0 - 1e-9, 3.0 + 1e-9]
    result = compare(jittered, entry)
    assert result.ok and not result.fast_path  # passed, but NOT on the hash


def test_nan_and_inf_round_trip() -> None:
    """Non-finite floats canonicalize stably and compare equal to themselves."""
    entry = make_entry({"a": math.nan, "b": math.inf, "c": -math.inf})
    result = compare({"a": math.nan, "b": math.inf, "c": -math.inf}, entry)
    assert result.ok and result.fast_path


def test_unserializable_value_is_loud_not_pickled() -> None:
    """An unsupported type raises, honoring the no-silent-pickle rule."""
    with pytest.raises(GoldenError, match="no canonical form"):
        make_entry(object())
