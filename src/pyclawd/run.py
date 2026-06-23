"""Subprocess helpers — every pyclawd command that runs Python goes through here.

`pyclawd` is installed into the project's dev env (e.g. a conda env), so ``sys.executable``
is exactly the interpreter that ``tools/python`` used to activate. We just add the
repo root to ``PYTHONPATH`` and run from there, mirroring the old wrapper.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

from .project import Project, load_project
from .repo import find_repo_root


def repo_root_or_exit() -> Path:
    root = find_repo_root()
    if root is None:
        typer.secho(
            "Not inside a project (no .pyclawd/config.py found). cd into the repo first.",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return root


def load_project_or_exit() -> Project:
    """Return the loaded project config, or exit(2) with a clear error if none."""
    project = load_project()
    if project is None:
        typer.secho(
            "Not inside a project (no .pyclawd/config.py found). cd into the repo first.",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project


def _env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(root), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    return env


def run(cmd: list[str], root: Path | None = None) -> int:
    """Run a command from the repo root with PYTHONPATH set. Returns exit code."""
    root = root or repo_root_or_exit()
    return subprocess.call(cmd, cwd=str(root), env=_env(root))


def python(args: list[str]) -> int:
    """Run the dev interpreter (= conda ``default``) with extra args."""
    return run([sys.executable, *args])


def has_target(args: list[str]) -> bool:
    """True if *args* contains an explicit test target (a path, file, or nodeid) — so
    we must NOT also prepend the default ``tests/`` (which would collect the whole suite
    alongside it). ``-k``/``-m`` values never look like paths, so they're safe."""
    return any(
        not a.startswith("-") and ("/" in a or a.endswith(".py") or "::" in a)
        for a in args
    )


def pytest(args: list[str], default_markers: str | None = None,
           tests_dir: str | None = None) -> int:
    """Run pytest over the project's tests dir (or an explicit target in *args*).

    ``default_markers`` is applied only when the caller did not pass their own ``-m``
    expression. ``tests_dir`` is the default collection target used when *args* names
    no explicit target; it falls back to the loaded project's ``test.tests_dir``."""
    cmd = [sys.executable, "-m", "pytest", "-v"]
    if not has_target(args):
        cmd.append(tests_dir or load_project_or_exit().test.tests_dir)
    if default_markers and "-m" not in args:
        cmd += ["-m", default_markers]
    cmd += args
    return run(cmd)
