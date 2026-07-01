"""Locate the project repository root and query git for changed files."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .discovery import load_project


def find_repo_root(start: str | Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) to the project repo root.

    The root is the directory containing the project's ``.pyclawd/config.py``; this
    delegates to :func:`pyclawd.discovery.load_project`, returning the loaded
    project's :attr:`~pyclawd.project.Project.root` (or ``None`` if not found).
    """
    project = load_project(start)
    return project.root if project is not None else None


def changed_files(root: Path, against: str = "HEAD") -> list[str]:
    """List repo-relative paths changed versus *against*, plus untracked files.

    Combines ``git diff --name-only <against>`` (tracked modifications) with
    ``git ls-files --others --exclude-standard`` (new untracked files), keeps only
    paths that still exist on disk (so deletions are dropped), and de-duplicates
    while preserving order. Used by ``pyclawd check --changed`` to scope the gate
    to the working set.

    Args:
        root: The repository root to run git in.
        against: The git ref to diff against (e.g. ``"HEAD"``, ``"main"``).

    Returns:
        De-duplicated repo-relative paths that changed and still exist. Empty when
        git is unavailable or nothing changed.
    """
    names: list[str] = []
    for cmd in (
        ["git", "diff", "--name-only", against],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            names += proc.stdout.split()
    return [n for n in dict.fromkeys(names) if (root / n).exists()]


def _parse_unified0_hunks(diff_text: str) -> dict[str, set[int]]:
    """Parse ``git diff --unified=0`` output into ``{path: {new-side line numbers}}``.

    Reads the ``+++ b/<path>`` file headers and the ``@@ -a,b +c,d @@`` hunk headers,
    accumulating the added/modified line numbers on the **new** side (``c .. c+d-1``).
    A ``+++ /dev/null`` header (a deletion) contributes no lines.

    Args:
        diff_text: The raw stdout of ``git diff --unified=0``.

    Returns:
        Map of repo-relative path to the set of changed new-side line numbers.
    """
    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = None
            else:
                current = target[2:] if target.startswith("b/") else target
        elif line.startswith("@@") and current is not None:
            # @@ -old_start,old_count +new_start,new_count @@
            plus = line.split("+", 1)[1].split(" ", 1)[0]
            start_s, _, count_s = plus.partition(",")
            try:
                start = int(start_s)
                count = int(count_s) if count_s else 1
            except ValueError:
                continue
            if count > 0:
                result.setdefault(current, set()).update(range(start, start + count))
    return result


def changed_line_map(root: Path, against: str = "HEAD") -> dict[str, set[int]]:
    """Map each changed source file to the set of new-side line numbers that changed.

    Combines ``git diff --unified=0 <against>`` (tracked edits, with per-line
    granularity) with ``git ls-files --others --exclude-standard`` (new untracked
    files). A brand-new file is entirely new, so **all** its lines are recorded — that
    way a new file already exercised by tests maps to them, while a genuinely untested
    new file still surfaces as uncovered. Only paths that still exist are kept.

    Args:
        root: The repository root to run git in.
        against: The git ref to diff against (e.g. ``"HEAD"``, ``"main"``).

    Returns:
        Map of repo-relative path to changed new-side line numbers. Empty when git is
        unavailable or nothing changed.
    """
    diff = subprocess.run(
        ["git", "diff", "--unified=0", against],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    result = _parse_unified0_hunks(diff.stdout) if diff.returncode == 0 else {}

    others = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if others.returncode == 0:
        for name in others.stdout.split():
            result.setdefault(name, set()).update(_all_line_numbers(root / name))

    return {path: lines for path, lines in result.items() if (root / path).exists()}


def _all_line_numbers(path: Path) -> set[int]:
    """Every 1-indexed line number in *path* (an untracked file is entirely new).

    Args:
        path: The file to count lines for.

    Returns:
        ``{1, …, N}`` for an N-line file; empty when the file cannot be read as text.
    """
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return set()
    return set(range(1, len(text.splitlines()) + 1))
