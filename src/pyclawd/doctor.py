"""`pyclawd doctor` — quick health check of the dev environment.

Runs in-process (so it must be installed into the same conda env you develop
in). Each check returns a status; the command exits non-zero if any check FAILs
so it can gate other workflows.

Every project-specific value (conda env, dependency lists, tool files, system
binaries, project import + compiled-extension status) comes from the loaded
:class:`~pyclawd.project.Project` config — this module hardcodes nothing about any
particular project.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys

from rich.console import Console
from rich.table import Table

from .project import FAIL, OK, WARN, Check, Project, load_project

_MARK = {OK: "[green]✓[/green]", WARN: "[yellow]![/yellow]", FAIL: "[red]✗[/red]"}


def _module_version(mod) -> str:
    v = getattr(mod, "__version__", None)
    if v:
        return str(v)
    try:
        from importlib.metadata import version

        return version(mod.__name__.split(".")[0])
    except Exception:  # noqa: BLE001
        return "?"


def _check_python() -> Check:
    v = sys.version_info
    s = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 10):
        return Check(OK, "python", s)
    return Check(FAIL, "python", f"{s} (need >= 3.10)")


def _check_conda_env(expected: str | None) -> Check:
    env = os.environ.get("CONDA_DEFAULT_ENV")
    if expected is None:
        # Env-agnostic project: just report what we're in, no expectation.
        return Check(OK, "conda env", env or "not in a conda env")
    if env == expected:
        return Check(OK, "conda env", env)
    if env:
        return Check(WARN, "conda env", f"{env} (expected '{expected}')")
    return Check(WARN, "conda env", f"not in a conda env (expected '{expected}')")


def _check_import(name: str, required: bool) -> Check:
    try:
        mod = importlib.import_module(name)
        return Check(OK, name, _module_version(mod))
    except Exception as exc:  # noqa: BLE001 - report any import failure
        return Check(FAIL if required else WARN, name, f"not importable ({type(exc).__name__})")


def _check_binary(name: str, install_hint: str) -> Check:
    p = shutil.which(name)
    if p:
        return Check(OK, name, p)
    detail = f"not found — {install_hint}" if install_hint else "not found"
    return Check(WARN, name, detail)


def _check_repo(project: Project) -> list[Check]:
    root = project.root
    if root is None:
        return [Check(WARN, "repo root", "not found — run pyclawd from inside the project repo")]

    checks = [Check(OK, "repo root", str(root))]
    for tool in project.doctor.tool_files:
        p = root / tool
        if not p.exists():
            checks.append(Check(FAIL, tool, "missing"))
        elif not os.access(p, os.X_OK):
            checks.append(Check(WARN, tool, "not executable — `chmod +x`"))
        else:
            checks.append(Check(OK, tool, "ok"))
    return checks


def _check_git(root) -> Check:
    if root is None:
        return Check(WARN, "git branch", "n/a")
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return Check(OK, "git branch", out.stdout.strip())
        return Check(WARN, "git branch", "not a git work tree")
    except Exception as exc:  # noqa: BLE001
        return Check(WARN, "git branch", f"unavailable ({type(exc).__name__})")


def collect(project: Project | None = None) -> list[Check]:
    """Build the list of health checks from the loaded project config.

    Parameters
    ----------
    project : Project or None, optional
        The loaded project. If ``None``, it is discovered via
        :func:`~pyclawd.project.load_project`; when no project is found the generic
        checks still run and a WARN is added pointing at the missing config.
    """
    if project is None:
        project = load_project()

    # Degrade gracefully when run outside any project.
    if project is None:
        return [
            _check_python(),
            Check(WARN, "project config", "no .pyclawd/config.py found — run pyclawd inside a project"),
            _check_git(None),
        ]

    checks: list[Check] = [_check_python(), _check_conda_env(project.conda_env)]

    # Project import + compiled-extension status come from the config hook.
    if project.extra_doctor_checks is not None:
        checks += list(project.extra_doctor_checks())

    checks += [_check_import(d, required=True) for d in project.doctor.core_deps]
    checks += [_check_import(d, required=False) for d in project.doctor.dev_deps]
    checks += [_check_binary(name, hint) for name, hint in project.doctor.binaries]
    checks += _check_repo(project)
    checks.append(_check_git(project.root))
    return checks


def run_doctor() -> int:
    """Render the report and return a process exit code (0 ok, 1 if any FAIL)."""
    console = Console()
    project = load_project()
    checks = collect(project)

    name = project.name if project is not None else "unknown project"
    table = Table(
        title=f"pyclawd doctor — {name} dev environment",
        title_style="bold", show_lines=False,
    )
    table.add_column("", justify="center", width=3)
    table.add_column("check", style="bold")
    table.add_column("detail", overflow="fold")
    for c in checks:
        table.add_row(_MARK[c.status], c.name, c.detail)
    console.print(table)

    n_fail = sum(c.status == FAIL for c in checks)
    n_warn = sum(c.status == WARN for c in checks)
    if n_fail:
        console.print(f"[red]✗ {n_fail} failed[/red], [yellow]{n_warn} warning(s)[/yellow]")
        return 1
    if n_warn:
        console.print(f"[yellow]! all critical checks passed, {n_warn} warning(s)[/yellow]")
        return 0
    console.print(f"[green]✓ platform {platform.system()} — all checks passed[/green]")
    return 0
