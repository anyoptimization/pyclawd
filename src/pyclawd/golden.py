"""Behavior-regression oracle: record observable outputs and prove they don't change.

This is the *missing half* of ``pyclawd check``. The static quality gate
(format/lint/typecheck/test) proves code is **clean**; it cannot prove behavior
is **unchanged**. ``golden`` closes that gap by snapshotting an observable value
to a committed baseline and failing when a future run drifts from it.

Design (as ratified by the council review, with the hash *demoted to an
optimization*):

- **Tolerance is the semantic gate; the hash is only a fast path.** A hash
  mismatch never fails a snapshot on its own — it falls back to a tolerant
  value comparison. This is what makes committed baselines survive cross-platform
  float jitter (BLAS ±1 ULP) instead of flaking on it.
- **Values are stored inline and human-readable.** A ``float`` baseline literally
  shows ``3.141 → 3.150`` in a ``git diff``; that readability is the whole point of
  committing baselines. Provenance — *when/what release* changed a number — is
  git's job (the commit that edits a baseline), not a stored field.
- **No pickle.** The canonical form is JSON-serializable; an unsupported type is
  a loud error asking for an explicit serializer, never a silent pickle.
- **numpy values are accepted inline.** When numpy is installed, an ``np.ndarray``
  is canonicalized to nested lists (via ``.tolist()``, so float rounding and
  NaN/Inf handling still apply) and numpy scalars (``np.floating`` /
  ``np.integer`` / ``np.bool_``) reduce to plain ``float`` / ``int`` / ``bool``.
  numpy is an *optional* dependency imported lazily — absent it, behavior is the
  unchanged pure-python path.

This module is **dependency-free** (stdlib + lazy numpy) — the engine behind the
standalone :mod:`pyclawd.pytest_plugin`, which captures a ``@pytest.mark.golden``
test's **return value** and either **records** it (``pytest --golden-update``) or
**compares** it to the committed baseline (the default).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: JSON-serializable canonical form of a snapshot value.
Canonical = Any


def _as_numpy(value: object) -> Any:
    """Return the ``numpy`` module if *value* is a numpy array/scalar, else ``None``.

    numpy is an **optional** dependency: it is imported lazily here so the engine
    works unchanged (pure-python path) when numpy is absent. The module handle is
    returned (rather than a bool) so the caller can reuse it for ``isinstance``
    checks against ``np.floating`` / ``np.integer`` / ``np.bool_``.

    Args:
        value: The candidate snapshot value to classify.

    Returns:
        The imported ``numpy`` module when *value* is an ``np.ndarray`` or
        ``np.generic`` scalar, otherwise ``None`` (including when numpy is not
        installed).
    """
    try:
        import numpy as np
    except ImportError:
        return None
    return np if isinstance(value, (np.ndarray, np.generic)) else None


class GoldenError(AssertionError):
    """A snapshot drifted from its committed baseline beyond tolerance.

    Subclasses :class:`AssertionError` so a failed ``golden`` comparison reads as
    an ordinary test failure to pytest.
    """


def canonicalize(value: Any, precision: int) -> Canonical:
    """Reduce *value* to a stable, JSON-serializable form with floats rounded.

    Rounding to *precision* decimals is what makes the fast-path hash stable
    across runs and platforms; the un-rounded value is never what we compare
    against semantically (that is the tolerant comparison's job).

    Args:
        value: The snapshot value — a float, int, bool, str, ``None``, or a
            (possibly nested) list/tuple/dict of those. When numpy is installed,
            an ``np.ndarray`` (canonicalized via ``.tolist()``) and numpy scalars
            (``np.floating`` / ``np.integer`` / ``np.bool_``) are also accepted.
        precision: Number of decimal places to round floats to.

    Returns:
        A canonical structure safe to ``json.dumps`` deterministically.

    Raises:
        GoldenError: If *value* contains a type with no JSON-safe canonical form
            (the "no silent pickle" rule — ask for an explicit serializer).
    """
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        # Normalise -0.0 to 0.0 so the hash doesn't flip on sign of zero.
        rounded = round(value, precision)
        return rounded + 0.0
    if isinstance(value, (list, tuple)):
        return [canonicalize(v, precision) for v in value]
    if isinstance(value, dict):
        return {str(k): canonicalize(value[k], precision) for k in sorted(value, key=str)}
    np = _as_numpy(value)
    if np is not None:
        if isinstance(value, np.ndarray):
            # Recurse on the nested-list form so rounding + NaN/Inf handling apply.
            return canonicalize(value.tolist(), precision)
        # numpy scalars (np.generic). Order matters: np.bool_ is NOT an np.integer,
        # but check it first so a boolean never falls through to the integer branch.
        if isinstance(value, np.bool_):
            return canonicalize(bool(value), precision)
        if isinstance(value, np.integer):
            return canonicalize(int(value), precision)
        if isinstance(value, np.floating):
            return canonicalize(float(value), precision)
    raise GoldenError(
        f"golden: no canonical form for type {type(value).__name__!r}. "
        "Pass a float/int/str/bool/None or a nested list/dict of those, "
        "or provide an explicit serializer (the sidecar path)."
    )


def digest(canonical: Canonical) -> str:
    """Return the ``sha256:`` hash of a canonical value's deterministic JSON.

    Args:
        canonical: A structure returned by :func:`canonicalize`.

    Returns:
        A string ``"sha256:<hex>"`` — the fast-path equality key.
    """
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def values_close(a: Canonical, b: Canonical, rtol: float, atol: float) -> bool:
    """Compare two canonical values structurally with a numeric tolerance.

    Numbers compare within ``atol + rtol * |b|`` (the ``numpy.allclose`` rule);
    everything else compares for exact structural equality. This is the
    **semantic gate** — the hash is only an optimization in front of it.

    Args:
        a: The freshly computed canonical value.
        b: The committed baseline canonical value.
        rtol: Relative tolerance for numeric leaves.
        atol: Absolute tolerance for numeric leaves.

    Returns:
        ``True`` if *a* matches *b* within tolerance, else ``False``.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= atol + rtol * abs(float(b))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            values_close(x, y, rtol, atol) for x, y in zip(a, b, strict=True)
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(values_close(a[k], b[k], rtol, atol) for k in a)
    return a == b


@dataclass(frozen=True)
class Comparison:
    """Outcome of comparing a new value against a committed baseline entry.

    Args:
        ok: Whether the value matches the baseline (fast-path or tolerant).
        fast_path: ``True`` if the hash matched and no tolerant compare was needed.
        detail: Human-readable explanation (empty on a fast-path pass).
    """

    ok: bool
    fast_path: bool
    detail: str


def compare(new_value: Any, entry: dict[str, Any]) -> Comparison:
    """Compare *new_value* against a stored baseline *entry*.

    The two-speed gate:

    1. Canonicalize + hash *new_value*. If the hash equals the stored hash →
       **pass** immediately (the fast path; no tolerant compare).
    2. Otherwise fall back to a tolerant value comparison against the stored
       inline ``value``. Within tolerance → **pass** (the hash only flipped from
       sub-tolerance jitter). Outside → **fail** with a diff. This fallback is
       why the hash is an optimization, not the gate.

    Args:
        new_value: The freshly computed snapshot value.
        entry: The committed baseline entry (``value``/``hash``/``rtol``/``atol``/
            ``precision``).

    Returns:
        A :class:`Comparison` describing the outcome.
    """
    precision = int(entry.get("precision", 10))
    rtol = float(entry.get("rtol", 1e-9))
    atol = float(entry.get("atol", 1e-12))
    new_canon = canonicalize(new_value, precision)
    new_hash = digest(new_canon)

    if new_hash == entry.get("hash"):
        return Comparison(ok=True, fast_path=True, detail="")

    if "value" not in entry:
        return Comparison(
            ok=False,
            fast_path=False,
            detail=f"hash changed and no inline value stored to fall back on\n  stored: "
            f"{entry.get('hash')}\n  actual: {new_hash}",
        )

    if values_close(new_canon, entry["value"], rtol, atol):
        return Comparison(
            ok=True,
            fast_path=False,
            detail="within tolerance (hash differed by sub-tolerance jitter)",
        )

    return Comparison(
        ok=False,
        fast_path=False,
        detail=(
            f"value drifted beyond tolerance (rtol={rtol:g}, atol={atol:g})\n"
            f"  baseline: {json.dumps(entry['value'])}\n"
            f"  actual:   {json.dumps(new_canon)}"
        ),
    )


def make_entry(
    value: Any,
    *,
    precision: int = 10,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> dict[str, Any]:
    """Build a committed-baseline entry from a value (the record/bless path).

    Stores the inline canonical ``value`` (readable, tolerant-comparable) plus a
    ``hash`` (the fast path). Per-snapshot ``rtol``/``atol``/``precision`` travel
    *in the entry*, not in a central config, so each snapshot owns its tolerance.
    Provenance (when/what release changed a number) is git's job — the commit that
    edits a baseline records it better than any self-reported field could.

    Args:
        value: The snapshot value to record.
        precision: Decimal places floats are rounded to before hashing.
        rtol: Relative tolerance stored for future comparisons.
        atol: Absolute tolerance stored for future comparisons.

    Returns:
        A JSON-serializable baseline entry.
    """
    canon = canonicalize(value, precision)
    entry: dict[str, Any] = {"value": canon, "hash": digest(canon)}
    if precision != 10:
        entry["precision"] = precision
    if rtol != 1e-9:
        entry["rtol"] = rtol
    if atol != 1e-12:
        entry["atol"] = atol
    return entry


class GoldenStore:
    """A per-test-module baseline file (``key → entry``) on disk.

    One JSON file per test module keeps git diffs surgical and avoids the
    merge-conflict storm a single global manifest would cause under a fleet of
    agents editing different modules.

    Args:
        path: Path to the module's baseline JSON (created on first write).
    """

    def __init__(self, path: Path) -> None:
        """Load the baseline file at *path* (empty store if it does not exist)."""
        self.path = path
        self._data: dict[str, Any] = {}
        if path.exists():
            self._data = json.loads(path.read_text())

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the baseline entry for *key*, or ``None`` if unrecorded."""
        return self._data.get(key)

    def set(self, key: str, entry: dict[str, Any]) -> None:
        """Merge-record *entry* under *key*, leaving every other key untouched."""
        self._data[key] = entry

    def keys(self) -> list[str]:
        """Return all recorded snapshot keys in this store."""
        return list(self._data)

    def remove(self, key: str) -> bool:
        """Drop *key* if present; return whether anything was removed."""
        return self._data.pop(key, None) is not None

    def is_empty(self) -> bool:
        """Whether the store holds no entries (used to prune empty files)."""
        return not self._data

    def save(self) -> None:
        """Write the store back to disk as stable, diff-friendly JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self._data, indent=2, sort_keys=True) + "\n"
        self.path.write_text(text)


def module_baseline_path(baseline_dir: Path, module_stem: str) -> Path:
    """Resolve the baseline JSON path for a test module under *baseline_dir*.

    The single source of truth shared by the pytest plugin (which records/reads a
    module's baseline) and the ``pyclawd golden`` command layer (which scans them),
    so the two can never disagree on where a baseline lives.

    Args:
        baseline_dir: The configured baseline directory (``GoldenConfig.baseline_dir``).
        module_stem: The test module's file stem (e.g. ``"test_minimize"``).

    Returns:
        ``<baseline_dir>/<module_stem>.json``.
    """
    return baseline_dir / f"{module_stem}.json"


def iter_baseline_files(baseline_dir: Path) -> list[Path]:
    """List the baseline JSON files under *baseline_dir* (sorted, empty if absent).

    Args:
        baseline_dir: The configured baseline directory.

    Returns:
        Sorted ``*.json`` paths directly under *baseline_dir*.
    """
    if not baseline_dir.is_dir():
        return []
    return sorted(baseline_dir.glob("*.json"))
