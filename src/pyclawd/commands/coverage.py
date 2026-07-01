"""Coverage command — ``pyclawd coverage``.

Runs the test suite under pytest-cov and prints a term-missing report. Driven
entirely by :class:`~pyclawd.project.CoverageConfig` (``project.coverage``) —
the source packages, threshold, and branch settings live in the project's
``.pyclawd/config.py``, not here. When coverage is unconfigured the command
self-reports and exits ``2`` rather than crashing.

Exit-code contract:

- ``0`` — tests passed (and coverage threshold met, if ``--check`` was given).
- ``2`` — coverage not configured for this project.
- otherwise — pytest's own exit code (test failures, coverage threshold breached, …).
"""

from __future__ import annotations

import typer

from .. import run
from ..project import CoverageConfig, Project


def _coverage_or_exit(project: Project) -> CoverageConfig:
    """Return ``project.coverage`` or exit ``2`` with a clear, actionable message."""
    if project.coverage is None:
        typer.secho(
            "coverage not configured — add CoverageConfig to .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project.coverage


def coverage(
    html: bool = typer.Option(False, "--html", help="Also write an HTML report to htmlcov/."),
    check: bool = typer.Option(
        False,
        "--check",
        help="Fail if coverage is below the configured threshold (CoverageConfig.threshold).",
    ),
    context: bool = typer.Option(
        False,
        "--context",
        help="Record per-test contexts (--cov-context=test) — builds the map "
        "`pyclawd test changed` reverse-maps the diff against.",
    ),
) -> None:
    """Run tests with coverage measurement and print a term-missing report.

    Uses pytest-cov to measure the packages listed in ``coverage.source``.
    Add ``--html`` to also write an HTML report under ``htmlcov/``.
    Add ``--check`` to fail when coverage drops below ``coverage.threshold``.
    Add ``--context`` to record per-test contexts so ``pyclawd test changed`` can
    map the working diff back to the tests that cover it.
    """
    project = run.load_project_or_exit()
    cov = _coverage_or_exit(project)

    prefix = run.python_prefix(project)
    tests_dir = project.test.tests_dir

    cmd: list[str] = [*prefix, "-m", "pytest", tests_dir]

    for src in cov.source:
        cmd += [f"--cov={src}"]

    cmd += ["--cov-report=term-missing"]

    if cov.branch:
        cmd += ["--cov-branch"]

    if context:
        cmd += ["--cov-context=test"]

    if html:
        cmd += ["--cov-report=html"]

    if check:
        cmd += [f"--cov-fail-under={cov.threshold}"]

    raise typer.Exit(run.run(cmd))


def register(app: typer.Typer) -> None:
    """Attach the coverage command to *app*."""
    app.command()(coverage)
