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
