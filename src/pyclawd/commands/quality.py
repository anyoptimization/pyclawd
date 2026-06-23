"""Code-quality commands: ``lint``, ``format``, ``typecheck``, and the aggregate ``check``.

This is pyclawd's "good Python code" layer. Each command is driven entirely by
the loaded :class:`~pyclawd.project.QualityConfig` (``project.quality``) — the
concrete toolchain (ruff, mypy, …) lives in the project's ``.pyclawd/config.py``,
not here. When quality is unconfigured a command self-reports and exits ``2``
rather than crashing, so the commands are always safe to register and
``pyclawd --help`` always works.

The aggregate :func:`check` is the canonical daily loop and CI gate: it runs the
verbs in ``project.quality.check_sequence`` in order, **fail-fast** (stop at the
first failure), prints a per-step ✓/✗ summary, and propagates a non-zero exit
code if any step failed.

Exit-code contract (agent-native, deterministic):

- ``0`` — success.
- ``2`` — quality not configured for the requested command.
- otherwise — the underlying tool's own exit code (lint/type errors, etc.).
"""

from __future__ import annotations

import typer

from .. import run, tests
from ..project import Project, QualityConfig

# Exit code used when a command is invoked but quality (or its specific argv)
# is not configured for the project.
_UNCONFIGURED = 2


def _quality_or_exit(project: Project) -> QualityConfig:
    """Return ``project.quality`` or exit ``2`` with a clear, actionable message.

    Parameters
    ----------
    project : Project
        The loaded project config.

    Returns
    -------
    QualityConfig
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


def _run_cmd(project: Project, cmd: list[str], what: str) -> int:
    """Run a configured quality *cmd* from the repo root, or exit ``2`` if empty.

    Parameters
    ----------
    project : Project
        The loaded project (provides the repo root + env).
    cmd : list of str
        The argv to run (e.g. ``["ruff", "check"]``). Empty means unconfigured.
    what : str
        Human label for the missing-config message (e.g. ``"lint"``).

    Returns
    -------
    int
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
    return run.run(list(cmd), project.root)


def lint(
    fix: bool = typer.Option(False, "--fix", help="Apply autofixes (lint_fix_cmd)."),
) -> None:
    """Lint the project (``quality.lint_cmd``; with ``--fix``, ``lint_fix_cmd``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    cmd = quality.lint_fix_cmd if fix else quality.lint_cmd
    raise typer.Exit(_run_cmd(project, cmd, "lint-fix" if fix else "lint"))


def format(  # noqa: A001 - intentional command name (`pyclawd format`)
    check: bool = typer.Option(
        False, "--check", help="Check formatting without writing (format_check_cmd)."
    ),
) -> None:
    """Format the project (``quality.format_cmd``; with ``--check``, ``format_check_cmd``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    cmd = quality.format_check_cmd if check else quality.format_cmd
    raise typer.Exit(_run_cmd(project, cmd, "format-check" if check else "format"))


def typecheck() -> None:
    """Type-check the project (``quality.typecheck_cmd``, e.g. ``mypy src``)."""
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    raise typer.Exit(_run_cmd(project, quality.typecheck_cmd, "typecheck"))


# --- the aggregate gate ------------------------------------------------------


# Maps a check_sequence verb to the (label, argv) a non-test step runs. The
# special verb "test" is handled separately (it runs the default test tier).
def _step_cmd(verb: str, quality: QualityConfig) -> list[str]:
    """Resolve a non-``test`` check verb to its configured argv."""
    return {
        "format-check": quality.format_check_cmd,
        "lint": quality.lint_cmd,
        "typecheck": quality.typecheck_cmd,
    }.get(verb, [])


def _run_step(verb: str, project: Project, quality: QualityConfig) -> int:
    """Run one ``check`` step and return its exit code.

    ``"test"`` maps to the existing **default** test tier (the comprehensive gate
    `pyclawd test run` uses — ``project.test.markers["default"]``). Every other
    verb resolves to a configured argv via :func:`_step_cmd`. An unknown verb is a
    configuration error (exit ``2``).
    """
    if verb == "test":
        markers = project.test.markers.get("default", "")
        return tests.run_suite([], markers, "check", project)

    cmd = _step_cmd(verb, quality)
    if not cmd:
        typer.secho(
            f"check: step '{verb}' is unknown or unconfigured — "
            "fix Project.quality.check_sequence / *_cmd in .pyclawd/config.py",
            fg="red",
            err=True,
        )
        return _UNCONFIGURED
    return run.run(list(cmd), project.root)


def check() -> None:
    """Aggregate quality gate: run ``quality.check_sequence`` in order, fail-fast.

    Runs each verb (``format-check`` → ``lint`` → ``typecheck`` → ``test`` by
    default), **stopping at the first failure**. Prints a per-step ✓/✗ summary and
    a final verdict line, and exits non-zero if any step failed. This is the
    canonical daily loop and CI-parity gate.
    """
    project = run.load_project_or_exit()
    quality = _quality_or_exit(project)
    sequence = quality.check_sequence

    results: list[tuple[str, int]] = []
    failed = False
    for verb in sequence:
        typer.secho(f"\n── check: {verb} ───────────────────────────────", fg="cyan")
        rc = _run_step(verb, project, quality)
        results.append((verb, rc))
        if rc != 0:
            failed = True
            break  # fail-fast — don't run later steps

    # Per-step summary: ✓ for run-and-passed, ✗ for the failing step, · for skipped.
    typer.echo("\ncheck summary:")
    ran = {v for v, _ in results}
    for verb in sequence:
        if verb not in ran:
            typer.secho(f"  ·  {verb}  (skipped)", fg="bright_black")
            continue
        rc = dict(results)[verb]
        if rc == 0:
            typer.secho(f"  ✓  {verb}", fg="green")
        else:
            typer.secho(f"  ✗  {verb}  (exit {rc})", fg="red")

    if failed:
        last_verb, last_rc = results[-1]
        typer.secho(f"\n❌ check FAILED at '{last_verb}' (exit {last_rc})", fg="red")
        raise typer.Exit(last_rc)
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
