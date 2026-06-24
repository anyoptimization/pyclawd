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
- **Values are stored inline and human-readable.** A scalar baseline literally
  shows ``3.141 → 3.150`` in a ``git diff``; that readability is the whole point
  of committing baselines. Big arrays would instead carry a hash + a sidecar
  artifact (the designed extension — not exercised by this module's pure-Python
  core).
- **No pickle.** The canonical form is JSON-serializable; an unsupported type is
  a loud error asking for an explicit serializer, never a silent pickle.

The flow: a ``golden`` fixture computes a value, canonicalizes it (rounding floats
to ``precision`` decimals so the fast-path hash is stable), and either **records**
it (update mode) or **compares** it to the committed baseline (gate mode).
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
            (possibly nested) list/tuple/dict of those.
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
    value: Any, *, precision: int = 10, rtol: float = 1e-9, atol: float = 1e-12
) -> dict[str, Any]:
    """Build a committed-baseline entry from a value (the record/bless path).

    Stores the inline canonical ``value`` (readable, tolerant-comparable) plus a
    ``hash`` (the fast path). Per-snapshot ``rtol``/``atol``/``precision`` travel
    *in the entry*, not in a central config, so each snapshot owns its tolerance.

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

    def save(self) -> None:
        """Write the store back to disk as stable, diff-friendly JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self._data, indent=2, sort_keys=True) + "\n"
        self.path.write_text(text)


class Recorder:
    """The object a test receives as the ``golden`` fixture.

    In **gate mode** (default) each call compares against the committed baseline
    and raises :class:`GoldenError` on drift. In **update mode** each call
    records a fresh baseline (the human-run, human-reviewed bless step — never
    wired into an autonomous loop's self-gate).

    Args:
        store: The module's :class:`GoldenStore`.
        node_key: The snapshot key prefix derived from the test node id (for a
            parametrized test this already includes the ``[param]`` suffix).
        update: Whether to record (``True``) or compare (``False``).
    """

    def __init__(self, store: GoldenStore, node_key: str, *, update: bool) -> None:
        """Bind the recorder to a *store* and *node_key* in gate or *update* mode."""
        self._store = store
        self._node_key = node_key
        self._update = update
        self._labels: set[str] = set()

    def __call__(
        self,
        value: Any,
        label: str | None = None,
        *,
        precision: int = 10,
        rtol: float = 1e-9,
        atol: float = 1e-12,
    ) -> None:
        """Snapshot *value* — record it (update mode) or assert it (gate mode).

        Args:
            value: The observable output to snapshot.
            label: Disambiguates multiple snapshots in one test. Required when a
                test calls ``golden`` more than once.
            precision: Decimal places floats are rounded to before hashing.
            rtol: Relative tolerance for the comparison.
            atol: Absolute tolerance for the comparison.

        Raises:
            GoldenError: In gate mode, if the value drifts beyond tolerance — or
                if there is no committed baseline yet (run update mode first).
        """
        key = self._node_key if label is None else f"{self._node_key}::{label}"
        if key in self._labels:
            raise GoldenError(
                f"golden: duplicate snapshot key {key!r} — pass distinct label= values."
            )
        self._labels.add(key)

        if self._update:
            self._store.set(key, make_entry(value, precision=precision, rtol=rtol, atol=atol))
            return

        entry = self._store.get(key)
        if entry is None:
            raise GoldenError(
                f"golden: no baseline for {key!r}. Record it with update mode "
                "(`pyclawd golden update`) and commit the baseline."
            )
        result = compare(value, entry)
        if not result.ok:
            raise GoldenError(f"golden: {key}\n  {result.detail}")
