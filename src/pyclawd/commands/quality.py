"""Code-quality commands: ``lint``, ``format``, ``typecheck``, and the aggregate ``check``.

This is pyclawd's "good Python code" layer. Each command is driven entirely by
the loaded :class:`~pyclawd.project.QualityConfig` (``project.quality``) — the
concrete toolchain (ruff, mypy, …) lives in the project's ``.pyclawd/config.py``,
not here. When quality is unconfigured a command self-reports and exits ``2``
rather than crashing, so the commands are always safe to register and
``pyclawd --help`` always works.

The aggregate :func:`check` is the canonical daily loop and CI gate: it runs
all quality verbs (format-check, lint, typecheck) regardless of individual
failures so the full picture is visible in one run, then runs the ``test`` step
only if quality passed. Each quality step is tee'd to a log file. Prints a
per-step ✓/✗ summary and propagates a non-zero exit code if any step failed.

Exit-code contract (agent-native, deterministic):

- ``0`` — success.
- ``2`` — quality not configured for the requested command.
- otherwise — the underlying tool's own exit code (lint/type errors, etc.).
"""

from __future__ import annotations

from pathlib import Path

import typer

from .. import run, tests
from ..logs import category_dir, run_id
from ..logs import tee as _tee
from ..project import Project, QualityConfig
from . import ls as ls_cmd

# Exit code used when a command is invoked but quality (or its specific argv)
# is not configured for the project.
_UNCONFIGURED = 2


def _quality_or_exit(project: Project) -> QualityConfig:
    """Return ``project.quality`` or exit ``2`` with a clear, actionable message.

    Args:
        project: The loaded project config.

    Returns:
        The project's quality configuration.
    """
    if project.quality is None:
        typer.secho(
            "quality not configured — set Project.quality in .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(_UNCONFIGURED)
    return project.quality


def _run_cmd(
    project: Project,
    cmd: list[str],
    what: str,
    paths: list[str] | None = None,
) -> int:
    """Run a configured quality *cmd* from the repo root, or exit ``2`` if empty.

    Args:
        project: The loaded project (provides the repo root + env).
        cmd: The argv to run (e.g. ``["ruff", "check"]``). Empty means unconfigured.
        what: Human label for the missing-config message (e.g. ``"lint"``).
        paths: Optional file/directory paths to scope the command to. When given
            they are appended to *cmd* so the tool operates on those paths only.

    Returns:
        The subprocess exit code.
    """
    if not cmd:
        typer.secho(
            f"{what} not configured — set Project.quality.{what.replace('-', '_')}_cmd "
            "in .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(_UNCONFIGURED)
    return run.run(list(cmd) + list(paths or []), project.root)


def lint(
    fix: bool = typer.Option(False, "--fix", help="Apply autofixes (lint_fix_cmd)."),
    paths: list[str] | None = typer.Argument(
        None, help="Specific files or directories to lint (default: whole project)."
    ),
) -> None:
    """Lint the project (``quality.lint_cmd``; with ``--fix``, ``lint_fix_cmd``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    cmd = quality.lint_fix_cmd if fix else quality.lint_cmd
    raise typer.Exit(_run_cmd(project, cmd, "lint-fix" if fix else "lint", paths=paths))


def format(  # noqa: A001 - intentional command name (`pyclawd format`)
    check: bool = typer.Option(
        False, "--check", help="Check formatting without writing (format_check_cmd)."
    ),
    paths: list[str] | None = typer.Argument(
        None, help="Specific files or directories to format (default: whole project)."
    ),
) -> None:
    """Format the project (``quality.format_cmd``; with ``--check``, ``format_check_cmd``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    cmd = quality.format_check_cmd if check else quality.format_cmd
    raise typer.Exit(_run_cmd(project, cmd, "format-check" if check else "format", paths=paths))


def typecheck(
    paths: list[str] | None = typer.Argument(
        None, help="Specific files or directories to type-check (default: whole project)."
    ),
) -> None:
    """Type-check the project (``quality.typecheck_cmd``, e.g. ``mypy src``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    raise typer.Exit(_run_cmd(project, quality.typecheck_cmd, "typecheck", paths=paths))


# --- the aggregate gate ------------------------------------------------------


# Maps a check_sequence verb to the (label, argv) a non-test step runs. The
# special verb "test" is handled separately (it runs the default test tier).
def _step_cmd(verb: str, quality: QualityConfig, fix: bool = False) -> list[str]:
    """Resolve a non-``test`` check verb to its configured argv.

    When *fix* is True, ``format-check`` maps to the write-in-place formatter and
    ``lint`` maps to the auto-fix linter. ``typecheck`` is always read-only.
    """
    if fix:
        return {
            "format-check": quality.format_cmd,
            "lint": quality.lint_fix_cmd,
            "typecheck": quality.typecheck_cmd,
        }.get(verb, [])
    return {
        "format-check": quality.format_check_cmd,
        "lint": quality.lint_cmd,
        "typecheck": quality.typecheck_cmd,
    }.get(verb, [])


def _run_step(
    verb: str,
    project: Project,
    quality: QualityConfig,
    fix: bool = False,
    log: Path | None = None,
    paths: list[str] | None = None,
) -> int:
    """Run one ``check`` step and return its exit code.

    ``"test"`` maps to the existing **default** test tier. ``"descriptions"``
    runs the in-process description check. Every other verb resolves to a
    configured argv via :func:`_step_cmd`. An unknown verb is a configuration
    error (exit ``2``). When *log* is given the step's output is tee'd to that
    file as well as the console; without it the subprocess streams to the
    console only (used by standalone ``lint`` / ``format`` / ``typecheck``).
    When *fix* is True, format and lint steps run in autofix mode.
    *paths* are appended to the quality-step argv to scope it to specific
    files/directories; they are ignored for ``test`` and ``descriptions``.
    """
    if verb == "test":
        markers = project.test.markers.get("default", "")
        return tests.run_suite([], markers, "check", project, jobs=project.test.jobs)

    if verb == "descriptions":
        return ls_cmd.check_descriptions(project)

    cmd = _step_cmd(verb, quality, fix=fix)
    if not cmd:
        typer.secho(
            f"check: step '{verb}' is unknown or unconfigured — "
            "fix Project.quality.check_sequence / *_cmd in .pyclawd/config.py",
            fg="red",
            err=True,
        )
        return _UNCONFIGURED
    assert project.root is not None
    full_cmd = list(cmd) + list(paths or [])
    if log is not None:
        return _tee(full_cmd, log, project.root)
    return run.run(full_cmd, project.root)


#: Steps that run a subprocess and whose output is tee'd to a log file.
_QUALITY_STEPS = {"format-check", "lint", "typecheck"}


def check(
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Auto-fix format and lint issues before type-checking and testing.",
    ),
    skip: list[str] | None = typer.Option(
        None,
        "--skip",
        help="Skip a step by name (repeatable). e.g. --skip test --skip typecheck.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop at the first failing step instead of running all quality steps.",
    ),
    save_logs: bool = typer.Option(
        False,
        "--log",
        help="Tee each quality step's output to a log file (default: inline only).",
    ),
    paths: list[str] | None = typer.Argument(
        None,
        help=(
            "Specific files or directories to scope quality steps to "
            "(default: whole project). The test step always runs its full suite."
        ),
    ),
) -> None:
    """Aggregate quality gate: run all quality steps, then tests if quality passed.

    Quality steps (``format-check``, ``lint``, ``typecheck``) always all run so
    the agent sees the full picture in one shot, printed inline. The ``test`` step
    (and any subsequent steps) are skipped when any quality step failed; use
    ``pyclawd test failures`` / ``pyclawd test fix`` to iterate on test failures
    once quality is green.

    ``--skip <verb>`` (repeatable) omits a step entirely.
    ``--fail-fast`` stops at the first failure (any step).
    ``--fix`` applies format and lint autofixes in-place before checking.
    ``--log`` tee's each quality step to a log file (useful for CI artifacts).
    Optional positional *paths* scope quality steps to specific files/directories —
    requires **target-less quality cmds** in ``.pyclawd/config.py`` (e.g.
    ``["ruff", "check"]`` not ``["ruff", "check", "src"]``); the tool then reads
    its own target from ``pyproject.toml`` config when no paths are given.
    """
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    skip_set = set(skip or [])
    sequence = [v for v in quality.check_sequence if v not in skip_set]

    log_dir = category_dir("check", project) if save_logs else None
    rid = run_id() if save_logs else ""

    # (verb, exit_code | None-if-skipped, log_path | None)
    results: list[tuple[str, int | None, Path | None]] = []
    quality_failed = False

    for verb in sequence:
        if verb not in _QUALITY_STEPS and quality_failed:
            results.append((verb, None, None))
            continue

        typer.secho(f"\n── check: {verb} ───────────────────────────────", fg="cyan")
        step_log: Path | None = None
        if save_logs and log_dir is not None and verb in _QUALITY_STEPS:
            step_log = log_dir / f"{rid}-{verb}.log"
        rc = _run_step(verb, project, quality, fix=fix, log=step_log, paths=paths)
        results.append((verb, rc, step_log if rc != 0 else None))
        if rc != 0:
            if fail_fast:
                break
            if verb in _QUALITY_STEPS:
                quality_failed = True

    typer.echo("\ncheck summary:")
    any_failed = False
    ran_verbs = {v for v, _, _ in results}
    for step_verb, step_rc, step_log in results:
        if step_rc is None:
            typer.secho(f"  ·  {step_verb}  (skipped — fix quality first)", fg="bright_black")
        elif step_rc == 0:
            typer.secho(f"  ✓  {step_verb}", fg="green")
        else:
            any_failed = True
            suffix = f"  →  {step_log}" if step_log else f"  (exit {step_rc})"
            typer.secho(f"  ✗  {step_verb}{suffix}", fg="red")
    for verb in quality.check_sequence:
        if verb in skip_set:
            typer.secho(f"  ·  {verb}  (--skip)", fg="bright_black")
        elif fail_fast and verb not in ran_verbs:
            typer.secho(f"  ·  {verb}  (skipped — fail-fast)", fg="bright_black")

    if any_failed:
        failed_verbs = {v for v, r, _ in results if r is not None and r != 0}
        if {"format-check", "lint"} & failed_verbs and not fix:
            typer.secho("\n  hint: run `pyclawd check --fix` to apply autofixes.", fg="yellow")
        typer.secho("\n❌ check FAILED", fg="red")
        raise typer.Exit(1)
    typer.secho("\n✅ check PASSED — all steps green", fg="green")
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the quality commands to *app*.

    They are always registered (each self-reports when quality is unconfigured),
    so ``pyclawd --help`` always works regardless of the loaded project.
    """
    app.command()(lint)
    app.command(name="format")(format)
    app.command()(typecheck)
    app.command()(check)
