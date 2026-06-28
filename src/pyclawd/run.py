"""Subprocess helpers — every pyclawd command that runs Python goes through here.

How the interpreter is resolved (the one place it is decided) is
:func:`python_prefix`, with this precedence:

1. ``$PYCLAWD_PYTHON`` — a runtime override, ``shlex``-split so it can be a full
   command (e.g. ``PYCLAWD_PYTHON="conda run -n env python"``). Lets you swap
   interpreters per-invocation without touching config.
2. :attr:`Project.python_cmd` — the project's declared argv prefix (a venv path,
   ``conda run -n env python``, ``uv run python``, …).
3. ``sys.executable`` — the default: the Python pyclawd is installed under (so the
   contract is "install pyclawd into the env you develop in").

Whatever the prefix, the repo root is prepended to ``PYTHONPATH`` so in-tree source
imports. ``conda_env`` in config does **not** select the interpreter — it is only a
``pyclawd doctor`` WARN when the active env differs.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import typer

from .discovery import ConfigError, load_project
from .project import Project
from .repo import find_repo_root

#: Environment variable that overrides the launch command for the project Python.
PYTHON_ENV = "PYCLAWD_PYTHON"


def _exit_config_error(exc: Exception) -> NoReturn:
    """Print a clean one-line config error to stderr and exit 2 (no traceback)."""
    typer.secho(f"✗ {exc}", fg="red", err=True)
    raise typer.Exit(2)


def repo_root_or_exit() -> Path:
    """Return the repo root, or exit(2) with a clear error if not inside a project."""
    root = find_repo_root()
    if root is None:
        typer.secho(
            "Not inside a pyclawd project (no .pyclawd/config.py). Run `pyclawd new` here to "
            "adopt this repo (see the pyclawd-adopt skill), or cd into an existing project.",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return root


def load_project_or_exit() -> Project:
    """Return the loaded project config, or exit(2) with a clear error if none.

    A broken ``.pyclawd/config.py`` surfaces as a clean one-line message and exit
    ``2`` — never a raw traceback. This covers both a config that fails to import
    (:class:`~pyclawd.discovery.ConfigError`) and one that imports but is invalid —
    no module-level ``project`` / wrong type (``TypeError``), or an unloadable spec
    (``ImportError``) — all of which ``load_project`` may raise.
    """
    try:
        project = load_project()
    except (ConfigError, TypeError, ImportError) as exc:
        _exit_config_error(exc)
    if project is None:
        typer.secho(
            "Not inside a pyclawd project (no .pyclawd/config.py). Run `pyclawd new` here to "
            "adopt this repo (see the pyclawd-adopt skill), or cd into an existing project.",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project


def repo_env(root: Path) -> dict[str, str]:
    """Return the process env with *root* prepended to ``PYTHONPATH``.

    Public (no leading underscore) because the ``logs`` and ``tests`` pipelines
    build subprocess environments from it too — it is shared package API, not a
    private helper.
    """
    env = dict(os.environ)
    parts = [str(root), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    return env


def run(cmd: list[str], root: Path | None = None) -> int:
    """Run a command from the repo root with PYTHONPATH set. Returns exit code."""
    root = root or repo_root_or_exit()
    return subprocess.call(cmd, cwd=str(root), env=repo_env(root))


def python_prefix(project: Project | None = None) -> list[str]:
    """Resolve the argv prefix that launches the project's Python.

    Precedence (see the module docstring): ``$PYCLAWD_PYTHON`` →
    :attr:`Project.python_cmd` → ``sys.executable``. *project* is used for the
    config layer; if not given it is discovered (and a broken config is ignored
    here, falling through to the default — command boundaries report config errors
    separately).
    """
    override = os.environ.get(PYTHON_ENV)
    if override:
        return shlex.split(override)
    if project is None:
        try:
            project = load_project()
        except ConfigError:
            project = None
    if project is not None and project.python_cmd:
        return list(project.python_cmd)
    return [sys.executable]


def python(args: list[str]) -> int:
    """Run the project's Python (see :func:`python_prefix`) with extra args."""
    return run([*python_prefix(), *args])


def has_xdist(project: Project | None = None) -> bool:
    """True if ``pytest-xdist`` is importable in the project's Python env.

    Probed in a subprocess against :func:`python_prefix` because the project
    interpreter may differ from the one running pyclawd. Callers use this to inject
    ``-n`` only when xdist is present: a missing plugin must degrade to a serial run
    (pyclawd's "commands degrade, never crash" contract), not hard-fail pytest with
    ``error: unrecognized arguments: -n``.
    """
    try:
        return (
            subprocess.run(
                [*python_prefix(project), "-c", "import xdist"],
                capture_output=True,
            ).returncode
            == 0
        )
    except OSError:
        return False


#: pytest options whose *following token* is a value (an expression, not a target).
_VALUE_OPTS = {"-k", "-m", "-p", "-c", "--rootdir", "--junit-xml", "-n", "--durations"}


def has_target(args: list[str]) -> bool:
    """Return True if *args* contains an explicit test target (a path, file, or nodeid).

    When an explicit target is present we must NOT also prepend the default ``tests/``
    (which would collect the whole suite alongside it).

    The token immediately after a value-taking option (e.g. the expression after
    ``-k``/``-m``) is skipped, so a keyword expression like ``-k "a or b.py"`` is
    never mistaken for a file path.
    """
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in _VALUE_OPTS:
            skip = True  # the next token is this option's value, not a target
            continue
        if not a.startswith("-") and ("/" in a or a.endswith(".py") or "::" in a):
            return True
    return False


def pytest(
    args: list[str], default_markers: str | None = None, tests_dir: str | None = None
) -> int:
    """Run pytest over the project's tests dir (or an explicit target in *args*).

    ``default_markers`` is applied only when the caller did not pass their own ``-m``
    expression. ``tests_dir`` is the default collection target used when *args* names
    no explicit target; it falls back to the loaded project's ``test.tests_dir``.
    """
    cmd = [*python_prefix(), "-m", "pytest", "-v"]
    if not has_target(args):
        cmd.append(tests_dir or load_project_or_exit().test.tests_dir)
    if default_markers and "-m" not in args:
        cmd += ["-m", default_markers]
    cmd += args
    return run(cmd)
