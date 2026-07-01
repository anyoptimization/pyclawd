"""Reverse-map changed source lines to the tests that cover them (``pyclawd test changed``).

The tightest agent feedback loop: after an edit, run *only* the tests that actually
exercise the changed lines instead of the whole suite. The map comes from coverage
**contexts** — a coverage run with ``--cov-context=test`` records, per line, which
test touched it. This module inverts that: given the changed line numbers per file, it
returns the set of test node ids whose coverage intersects them.

Honesty about the blind spot (the "no silent caps" rule): a **brand-new** line has no
coverage row yet, so a naive reverse-map would return nothing and read as a false "all
green". Such files are reported separately as *uncovered* so the caller can warn loudly
and fall back rather than silently skip them.

``coverage`` is imported lazily (it ships wherever ``pytest-cov`` does); absent it, the
caller degrades with a clear message rather than crashing — the same optional-import
contract as numpy in :mod:`pyclawd.golden`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def strip_context_phase(context: str) -> str:
    """Reduce a coverage context to its bare test node id.

    pytest-cov's per-test dynamic context is the test node id with a phase suffix
    (``tests/test_x.py::test_f|run`` / ``|setup`` / ``|teardown``); the reverse map
    only cares about the node id, so the ``|phase`` is stripped.

    Args:
        context: A coverage context string.

    Returns:
        The node id with any ``|phase`` suffix removed.
    """
    return context.split("|", 1)[0]


@dataclass(frozen=True)
class ImpactResult:
    """The outcome of reverse-mapping a changed-line set to impacted tests.

    Args:
        nodeids: Test node ids whose coverage intersects a changed line.
        covered: Changed files that had at least one intersecting context.
        uncovered: Changed files with changed lines but no intersecting context —
            either brand-new (no coverage row) or genuinely untested. The caller must
            surface these rather than treat their absence as "nothing to run".
    """

    nodeids: set[str] = field(default_factory=set)
    covered: set[str] = field(default_factory=set)
    uncovered: set[str] = field(default_factory=set)


class CoverageUnavailable(RuntimeError):
    """The ``coverage`` package is not importable, so the map cannot be read."""


def _load_coverage_data(db_path: Path):  # type: ignore[no-untyped-def]
    """Open and read a coverage SQLite database, or raise :class:`CoverageUnavailable`.

    Args:
        db_path: Path to the ``.coverage`` data file.

    Returns:
        A read :class:`coverage.CoverageData` instance.

    Raises:
        CoverageUnavailable: When the ``coverage`` package is not installed.
    """
    try:
        import coverage
    except ImportError as exc:  # pragma: no cover - exercised via the CLI degrade path
        raise CoverageUnavailable(
            "the `coverage` package is required to read the impact map (it ships with pytest-cov)"
        ) from exc
    data = coverage.CoverageData(basename=str(db_path))
    data.read()
    return data


def has_test_contexts(db_path: Path) -> bool:
    """Whether the coverage DB carries per-test contexts (was built with ``--cov-context=test``).

    A DB measured without contexts has only the single empty context ``""``; the
    reverse map needs real per-test contexts, so the caller uses this to tell the user
    to rebuild the map when it is missing.

    Args:
        db_path: Path to the ``.coverage`` data file.

    Returns:
        ``True`` if at least one non-empty measured context exists.
    """
    try:
        data = _load_coverage_data(db_path)
    except CoverageUnavailable:
        return False
    return any(ctx for ctx in data.measured_contexts())


def impacted_tests(db_path: Path, root: Path, changed: dict[str, set[int]]) -> ImpactResult:
    """Reverse-map *changed* lines to the test node ids that cover them.

    For each changed file, the file's per-line contexts are read from the coverage DB;
    a test is impacted when any of its covered lines is in the changed set. A file that
    is not measured, or whose changed lines no context covers, is reported as
    *uncovered* (see :class:`ImpactResult`).

    Args:
        db_path: Path to the ``.coverage`` data file (built with ``--cov-context=test``).
        root: The repository root, used to resolve repo-relative paths to absolute.
        changed: Map of repo-relative path to changed new-side line numbers.

    Returns:
        An :class:`ImpactResult` with the impacted node ids and the covered/uncovered
        file split.

    Raises:
        CoverageUnavailable: When the ``coverage`` package is not installed.
    """
    data = _load_coverage_data(db_path)
    # coverage stores absolute filenames; index them by realpath so symlinked or
    # relative differences do not cause a spurious miss.
    measured = {os.path.realpath(name): name for name in data.measured_files()}

    result = ImpactResult()
    for rel, lines in changed.items():
        stored = measured.get(os.path.realpath(str(root / rel)))
        if stored is None:
            result.uncovered.add(rel)
            continue
        by_line = data.contexts_by_lineno(stored)
        hit: set[str] = set()
        for lineno in lines:
            for context in by_line.get(lineno, ()):
                node = strip_context_phase(context)
                if node:
                    hit.add(node)
        if hit:
            result.covered.add(rel)
            result.nodeids.update(hit)
        else:
            result.uncovered.add(rel)
    return result
