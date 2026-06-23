"""Locate the project repository root from the current working directory."""

from __future__ import annotations

import os
from pathlib import Path

from .project import load_project


def find_repo_root(start: str | os.PathLike | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) to the project repo root.

    The root is the directory containing the project's ``.pyclawd/config.py``; this
    delegates to :func:`pyclawd.project.load_project`, returning the loaded project's
    :attr:`~pyclawd.project.Project.root` (or ``None`` if no project is found).
    """
    project = load_project(start)
    return project.root if project is not None else None
