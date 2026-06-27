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
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from rich.console import Console
from rich.table import Table

from .discovery import ConfigError, load_project
from .project import FAIL, OK, WARN, Check, Project
from .skills_install import (
    drifted_installed_skills,
    orphaned_installed_skills,
    user_skills_dir,
)

_MARK = {OK: "[green]✓[/green]", WARN: "[yellow]![/yellow]", FAIL: "[red]✗[/red]"}


def _module_version(mod: ModuleType) -> str:
    v = getattr(mod, "__version__", None)
    if v:
        return str(v)
    try:
        from importlib.metadata import version

        return version(mod.__name__.split(".")[0])
    except Exception:
        return "?"


def _check_pyclawd() -> Check:
    """Report which pyclawd is operating on this project — version and source.

    When a single (often editable) pyclawd drives many repos, this answers "what
    version is running here, and from where?" The location distinguishes an
    editable dev checkout (``…/src/pyclawd``) from an installed wheel
    (``…/site-packages/pyclawd``).
    """
    import pyclawd

    version = getattr(pyclawd, "__version__", "?")
    location = os.path.dirname(pyclawd.__file__)
    editable = " (editable)" if f"{os.sep}site-packages{os.sep}" not in location else ""
    return Check(OK, "pyclawd", f"{version}{editable} — {location}")


def _mm(version: str) -> tuple[int, int] | None:
    """Parse a ``major.minor`` tuple from a version string, or ``None`` if unparseable."""
    parts = version.strip().split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return None


def _check_pyclawd_compat(declared: str) -> Check | None:
    """Compare the config's declared pyclawd version to the running one.

    Returns ``None`` when the project declares no ``pyclawd_version`` (check
    disabled). Otherwise OK on a matching ``major.minor``, else WARN that the
    project was built on a different pyclawd and may need migration.
    """
    if not declared:
        return None
    import pyclawd

    running = getattr(pyclawd, "__version__", "?")
    want, have = _mm(declared), _mm(running)
    if want is None or have is None:
        return Check(
            WARN, "pyclawd compat", f"built on {declared}, running {running} (unparseable)"
        )
    if want == have:
        return Check(OK, "pyclawd compat", f"config built on {declared} matches running {running}")
    return Check(
        WARN,
        "pyclawd compat",
        f"config built on pyclawd {declared}, running {running} — "
        f"`pyclawd changelog --since {declared}`, then the `pyclawd-upgrade` skill",
    )


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
    """Report whether a configured dependency is present (FAIL/WARN otherwise).

    A dependency may be listed by its **distribution** name (the PyPI package, e.g.
    ``pytest-xdist``) or by its **import** name (e.g. ``rich``); these often differ
    (``pytest-xdist`` imports as ``xdist``, ``pytest-cov`` as ``pytest_cov``). So we
    detect presence two ways, in order:

    1. ``importlib.metadata.version(name)`` — finds it by distribution name without
       importing the module, and normalizes ``-``/``_``/case. This handles PyPI
       names whose import name differs.
    2. ``importlib.import_module(<normalized>)`` — for names given as import names
       (stdlib modules, or deps named by their import name) and to surface the
       module ``__version__`` when metadata had nothing.

    Args:
        name: The dependency as listed in :class:`~pyclawd.project.DoctorConfig`.
        required: When True a missing dep is FAIL (core dep); else WARN (dev dep).

    Returns:
        An OK check with a version detail when present, else FAIL/WARN.
    """
    from importlib.metadata import PackageNotFoundError, version

    # 1. Try by distribution name — handles PyPI names with a differing import name.
    try:
        return Check(OK, name, version(name))
    except PackageNotFoundError:
        pass
    except Exception:
        pass

    # 2. Fall back to importing (names given as import names, e.g. stdlib modules).
    try:
        mod = importlib.import_module(name.replace("-", "_"))
        return Check(OK, name, _module_version(mod))
    except Exception as exc:
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

    # root_markers are a sanity check: files that should exist at the detected root.
    if project.root_markers:
        missing = [m for m in project.root_markers if not (root / m).exists()]
        if missing:
            checks.append(Check(WARN, "root markers", f"missing at root: {', '.join(missing)}"))
        else:
            checks.append(Check(OK, "root markers", f"{len(project.root_markers)} present"))

    for tool in project.doctor.tool_files:
        p = root / tool
        if not p.exists():
            checks.append(Check(FAIL, tool, "missing"))
        elif not os.access(p, os.X_OK):
            checks.append(Check(WARN, tool, "not executable — `chmod +x`"))
        else:
            checks.append(Check(OK, tool, "ok"))
    return checks


def _check_interpreter(project: Project) -> Check:
    """Report the command ``pyclawd python`` / ``test`` will actually launch.

    Surfaces the resolved :func:`pyclawd.run.python_prefix` (``$PYCLAWD_PYTHON`` →
    ``Project.python_cmd`` → ``sys.executable``) so a misconfigured interpreter is
    visible here rather than only at run time. WARNs if a configured launcher's
    binary is not on PATH.
    """
    from .run import PYTHON_ENV, python_prefix

    prefix = python_prefix(project)
    shown = " ".join(prefix)
    if os.environ.get(PYTHON_ENV):
        return Check(OK, "python exec", f"{shown}  (via ${PYTHON_ENV})")
    if not project.python_cmd:
        return Check(OK, "python exec", f"{shown}  (sys.executable)")
    # A configured launcher (venv path / conda run / uv run): check the binary.
    launcher = prefix[0] if prefix else ""
    if launcher and (shutil.which(launcher) or os.path.exists(launcher)):
        return Check(OK, "python exec", shown)
    return Check(WARN, "python exec", f"{shown}  — {launcher!r} not found on PATH")


def _check_workdir(project: Project) -> Check:
    """Report where pyclawd writes this project's transient files (logs, junit)."""
    from .logs import WORK_ENV, work_root

    root = work_root(project)
    if os.environ.get(WORK_ENV):
        source = f"via ${WORK_ENV}"
    elif project.work_dir:
        source = "config: work_dir"
    else:
        source = "default tmpdir"
    return Check(OK, "work dir", f"{root}  ({source})")


def _check_docs(project: Project) -> list[Check]:
    """Docs prerequisites, surfaced only when the project configures docs.

    Checks the two things that bite first: that the docs *runner* binary is on
    PATH (else every ``pyclawd docs build/run`` fails), and that ``jupyter-cache``
    is importable in this env (``pyclawd docs failures`` reads the cache
    in-process). Both are WARNs, not FAILs — docs are optional and the build verbs
    self-report — but they make the prerequisites visible before the first failure.
    """
    if project.docs is None:
        return []
    checks: list[Check] = []

    runner = project.docs.runner
    binary = runner[0] if runner else ""
    if not binary:
        checks.append(Check(WARN, "docs runner", "no runner configured (project.docs.runner)"))
    elif shutil.which(binary):
        checks.append(Check(OK, "docs runner", " ".join(runner)))
    else:
        checks.append(
            Check(WARN, "docs runner", f"{binary!r} not on PATH — `pyclawd docs build` will fail")
        )

    try:
        importlib.import_module("jupyter_cache")
        checks.append(Check(OK, "jupyter-cache", "available (enables `pyclawd docs failures`)"))
    except Exception:
        checks.append(
            Check(
                WARN,
                "jupyter-cache",
                "not importable — `pyclawd docs failures` needs it (pip install jupyter-cache)",
            )
        )
    return checks


def _check_golden(project: Project) -> list[Check]:
    """Golden-oracle config + baseline inventory, surfaced only when configured.

    Emits nothing when the project configures no golden suite (golden is optional,
    exactly like docs). When configured it reports the marker + baseline directory
    and a count of recorded baseline files, WARNing when none exist yet so the
    bless step (``pyclawd golden update``) is discoverable.

    Args:
        project: The loaded project config.

    Returns:
        Zero rows when ``project.golden is None``; otherwise 1-2 summary rows.
    """
    if project.golden is None:
        return []
    from .golden import iter_baseline_files

    g = project.golden
    checks: list[Check] = [Check(OK, "golden", f"marker {g.marker!r}, baseline {g.baseline_dir}")]

    if project.root is None:
        checks.append(
            Check(WARN, "golden baselines", "repo root unknown — cannot scan baseline dir")
        )
        return checks

    n = len(iter_baseline_files(project.path(g.baseline_dir)))
    if n:
        checks.append(Check(OK, "golden baselines", f"{n} module file(s)"))
    else:
        checks.append(
            Check(WARN, "golden baselines", "none recorded yet — run `pyclawd golden update`")
        )
    return checks


def _check_quality_targets(project: Project) -> list[Check]:
    """Warn when a quality command hardcodes a target path, breaking single-file scoping.

    ``pyclawd check <file>`` scopes the gate to one file by *appending* the path to
    each configured quality command. That only works when the commands are
    *target-less* (e.g. ``["mypy"]``, ``["ruff", "check"]``) so each tool reads its
    own default scope from ``pyproject.toml``. A command that hardcodes a target
    (e.g. ``["mypy", "pymoo"]`` or ``["ruff", "check", "src"]``) turns
    ``pyclawd check foo.py`` into ``mypy pymoo foo.py`` (duplicate-module error) or
    ``ruff check src foo.py`` (scans the whole package) — a confusing silent failure.

    The heuristic is deliberately low-false-positive: for each command, skip the
    tool name at index 0 and inspect the remaining positional tokens (those not
    starting with ``-``); a token is a hardcoded target only when it resolves to an
    existing path under the repo root. So ``["ruff", "check", "src"]`` flags (``src/``
    exists) while ``["ruff", "check"]`` does not (``check`` is not a path).

    Args:
        project: The loaded project config.

    Returns:
        Zero rows when quality is unconfigured; a single WARN if the repo root is
        unknown (targets cannot be verified); one WARN per offending command;
        otherwise a single OK row confirming all commands are target-less.
    """
    if project.quality is None:
        return []
    if project.root is None:
        return [
            Check(
                WARN,
                "quality targets",
                "repo root unknown — cannot verify quality command targets",
            )
        ]

    q = project.quality
    commands = [
        ("lint_cmd", q.lint_cmd),
        ("lint_fix_cmd", q.lint_fix_cmd),
        ("format_cmd", q.format_cmd),
        ("format_check_cmd", q.format_check_cmd),
        ("typecheck_cmd", q.typecheck_cmd),
    ]

    checks: list[Check] = []
    for label, cmd in commands:
        if not cmd:
            continue
        for token in cmd[1:]:
            if token.startswith("-"):
                continue
            if project.path(token).exists():
                checks.append(
                    Check(
                        WARN,
                        "quality targets",
                        f"{label} {cmd!r} hardcodes target {token!r} — make it target-less so "
                        "`pyclawd check <file>` can scope to one file "
                        "(let pyproject.toml set the default scope)",
                    )
                )
                break

    if not checks:
        return [Check(OK, "quality targets", "all quality commands are target-less")]
    return checks


def _check_skills() -> list[Check]:
    """WARN when user-scope pyclawd skills have drifted from, or are orphaned by, this pyclawd.

    Skills are **copied** into ``~/.claude/skills`` (so they ship with the project's
    agent setup), which means a pyclawd upgrade neither refreshes them nor removes the
    ones it dropped. This surfaces both staleness conditions:

    - **drift** — an installed skill whose content lags the bundled version; fix with
      ``pyclawd skills install`` (auto-refreshes drifted skills).
    - **orphans** — a ``pyclawd``/``pyclawd-*`` skill no longer in this bundle, left
      behind from an older pyclawd; fix with ``pyclawd skills prune``.

    Returns no rows when nothing is installed (the user opted out) so it never nags a
    skill-free project; both rows can appear together.
    """
    try:
        drifted = drifted_installed_skills()
        orphaned = orphaned_installed_skills()
    except Exception:
        return []
    target = user_skills_dir()
    checks: list[Check] = []
    if drifted:
        checks.append(
            Check(
                WARN,
                "skills",
                f"{len(drifted)} stale in {target}: {', '.join(drifted)} — "
                "run `pyclawd skills install`",
            )
        )
    if orphaned:
        checks.append(
            Check(
                WARN,
                "skills",
                f"{len(orphaned)} orphaned in {target}: {', '.join(orphaned)} — "
                "run `pyclawd skills prune`",
            )
        )
    return checks


def _check_git(root: Path | None) -> Check:
    if root is None:
        return Check(WARN, "git branch", "n/a")
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return Check(OK, "git branch", out.stdout.strip())
        return Check(WARN, "git branch", "not a git work tree")
    except Exception as exc:
        return Check(WARN, "git branch", f"unavailable ({type(exc).__name__})")


def collect(project: Project | None = None) -> list[Check]:
    """Build the list of health checks from the loaded project config.

    Args:
        project: The loaded project. If ``None``, it is discovered via
            :func:`~pyclawd.discovery.load_project`; when no project is found the
            generic checks still run and a WARN is added pointing at the missing
            config.
    """
    if project is None:
        project = load_project()

    # Degrade gracefully when run outside any project.
    if project is None:
        return [
            _check_pyclawd(),
            _check_python(),
            Check(
                WARN,
                "project config",
                "no .pyclawd/config.py — run `pyclawd new` to adopt this repo (pyclawd-adopt)",
            ),
            _check_git(None),
        ]

    checks: list[Check] = [_check_pyclawd()]
    compat = _check_pyclawd_compat(project.pyclawd_version)
    if compat is not None:
        checks.append(compat)
    checks += [
        _check_python(),
        _check_conda_env(project.conda_env),
        _check_interpreter(project),
        _check_workdir(project),
    ]

    # Project import + compiled-extension status come from the config hook. A
    # raising hook must not crash the whole report — turn it into a single FAIL row.
    if project.extra_doctor_checks is not None:
        hook_name = getattr(project.extra_doctor_checks, "__name__", "extra_doctor_checks")
        try:
            checks += list(project.extra_doctor_checks())
        except Exception as exc:
            checks.append(Check(FAIL, hook_name, f"raised {type(exc).__name__}: {exc}"))

    checks += [_check_import(d, required=True) for d in project.doctor.core_deps]
    checks += [_check_import(d, required=False) for d in project.doctor.dev_deps]
    checks += [_check_binary(name, hint) for name, hint in project.doctor.binaries]
    checks += _check_docs(project)
    checks += _check_golden(project)
    checks += _check_quality_targets(project)
    checks += _check_skills()
    checks += _check_repo(project)
    checks.append(_check_git(project.root))
    return checks


def run_doctor() -> int:
    """Render the report and return a process exit code (0 ok, 1 if any FAIL)."""
    console = Console()
    try:
        project = load_project()
    except (ConfigError, TypeError, ImportError) as exc:
        console.print(f"[red]✗ {exc}[/red]")
        return 2
    checks = collect(project)

    name = project.name if project is not None else "unknown project"
    table = Table(
        title=f"pyclawd doctor — {name} dev environment",
        title_style="bold",
        show_lines=False,
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


def dump_json(project: Project | None = None) -> int:
    """Emit doctor results as JSON to stdout and return a process exit code.

    Args:
        project: The loaded project. If ``None``, it is discovered via
            :func:`~pyclawd.discovery.load_project`. On ``ConfigError`` a JSON
            object with a single ``"error"`` key is emitted and exit code 2 is
            returned.

    Returns:
        0 when no check FAILed, 1 if any check FAILed, 2 on config error.
    """
    if project is None:
        try:
            project = load_project()
        except (ConfigError, TypeError, ImportError) as exc:
            json.dump({"error": str(exc)}, sys.stdout)
            sys.stdout.write("\n")
            return 2

    checks = collect(project)
    name = project.name if project is not None else "unknown project"
    n_fail = sum(c.status == FAIL for c in checks)
    n_warn = sum(c.status == WARN for c in checks)

    payload: dict[str, object] = {
        "project": name,
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks],
        "ok": n_fail == 0,
        "n_fail": n_fail,
        "n_warn": n_warn,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if n_fail else 0
