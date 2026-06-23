"""Locate the project repository root from the current working directory."""

from __future__ import annotations

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
