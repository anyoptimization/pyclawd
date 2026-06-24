"""Engine tests for numpy-aware canonicalization in the golden oracle.

These cover the *inline numpy* path of :mod:`pyclawd.golden`: arrays canonicalize
to nested lists with float rounding, numpy scalars reduce to plain python types,
NaN/Inf inside arrays round-trip stably, the tolerant value fallback survives a
sub-tolerance hash flip on an ndarray, and a genuinely unsupported type still
raises loudly. numpy is optional, so the numpy tests skip when it is absent.
"""

from __future__ import annotations

import pytest

from pyclawd.golden import GoldenError, canonicalize, compare, make_entry

np = pytest.importorskip("numpy")


def test_ndarray_1d_canonicalizes_to_rounded_list() -> None:
    """A 1d array becomes a plain list with floats rounded to precision."""
    canon = canonicalize(np.array([1.123456789, 2.0, 3.5]), precision=3)
    assert canon == [1.123, 2.0, 3.5]
    assert all(isinstance(x, float) for x in canon)


def test_ndarray_2d_canonicalizes_to_nested_lists() -> None:
    """A 2d array becomes nested lists, mirroring ``.tolist()``."""
    canon = canonicalize(np.array([[1.0, 2.0], [3.0, 4.0]]), precision=10)
    assert canon == [[1.0, 2.0], [3.0, 4.0]]


def test_ndarray_roundtrip_passes_on_faithful_rerun() -> None:
    """make_entry + compare passes (fast path) when the array is reproduced."""
    arr = np.array([0.1, 0.2, 0.3])
    entry = make_entry(arr)
    result = compare(np.array([0.1, 0.2, 0.3]), entry)
    assert result.ok and result.fast_path


def test_ndarray_beyond_tolerance_change_is_caught() -> None:
    """A real drift in an array value fails the gate."""
    entry = make_entry(np.array([0.1, 0.2, 0.3]), rtol=1e-9, atol=1e-12)
    result = compare(np.array([0.1, 0.25, 0.3]), entry)
    assert not result.ok
    assert "beyond tolerance" in result.detail


def test_numpy_float_scalar_canonicalizes_to_python_float() -> None:
    """An ``np.floating`` reduces to a rounded python float."""
    canon = canonicalize(np.float64(3.14159), precision=2)
    assert canon == 3.14
    assert isinstance(canon, float)


def test_numpy_int_scalar_canonicalizes_to_python_int() -> None:
    """An ``np.integer`` reduces to a python int."""
    canon = canonicalize(np.int64(42), precision=10)
    assert canon == 42
    assert isinstance(canon, int) and not isinstance(canon, bool)


def test_numpy_bool_scalar_canonicalizes_to_python_bool() -> None:
    """An ``np.bool_`` reduces to a python bool (not an int)."""
    canon = canonicalize(np.bool_(True), precision=10)
    assert canon is True
    assert isinstance(canon, bool)


def test_numpy_bool_does_not_fall_through_to_integer() -> None:
    """``np.bool_`` is handled as bool — never coerced to 0/1 ints."""
    assert canonicalize(np.bool_(False), precision=10) is False


def test_ndarray_subtolerance_jitter_passes_via_value_fallback() -> None:
    """A BLAS-sized perturbation flips the hash but passes the tolerant compare."""
    entry = make_entry(np.array([1.0, 2.0, 3.0]), rtol=1e-6, atol=1e-9)
    jittered = np.array([1.0 + 1e-9, 2.0 - 1e-9, 3.0 + 1e-9])
    result = compare(jittered, entry)
    assert result.ok and not result.fast_path  # passed, but NOT on the hash


def test_ndarray_with_nan_and_inf_round_trip() -> None:
    """NaN/Inf inside an array canonicalize stably and compare equal to themselves."""
    arr = np.array([np.nan, np.inf, -np.inf, 1.0])
    entry = make_entry(arr)
    assert entry["value"] == ["NaN", "Infinity", "-Infinity", 1.0]
    result = compare(np.array([np.nan, np.inf, -np.inf, 1.0]), entry)
    assert result.ok and result.fast_path


def test_unsupported_type_still_raises_loud() -> None:
    """A genuinely unserializable type still raises, honoring no-silent-pickle."""
    with pytest.raises(GoldenError, match="no canonical form"):
        canonicalize(object(), precision=10)
