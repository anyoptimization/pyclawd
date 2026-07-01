"""API-surface command group — ``pyclawd api`` (the public-surface oracle).

golden proves a *value* is unchanged; ``api`` proves the *public surface* is
unchanged — it catches an **accidental** breaking change (a removed function, a
renamed or reordered parameter) an edit did not intend. The engine lives in
:mod:`pyclawd.api`; this module is the CLI wrapper that reads
:class:`~pyclawd.project.ApiConfig`, extracts the current surface statically, and
diffs it against the committed baseline.

Subcommands (driven by :class:`~pyclawd.project.ApiConfig`):

- ``pyclawd api`` (default) — **compare**: fail on a removed or changed symbol
  (breaking); a pure addition passes with a note unless ``strict``.
- ``pyclawd api update`` — **bless**: re-record the baseline (humans bless, agents
  compare — review the ``git diff`` and commit deliberately).
- ``pyclawd api status`` — show the surface size and any drift.

Exit-code contract (agent-native, deterministic):

- ``0`` — surface matches (or only non-breaking additions in non-strict mode).
- ``1`` — surface drift that fails the gate.
- ``2`` — api not configured for this project.
"""

from __future__ import annotations

import typer

from .. import run
from ..api import SurfaceDiff, diff_surface, extract_surface, read_baseline, write_baseline
from ..project import ApiConfig, Project


def _api_or_exit(project: Project) -> ApiConfig:
    """Return ``project.api`` or exit ``2`` with a clear, actionable message.

    Args:
        project: The loaded project config.

    Returns:
        The project's api configuration.
    """
    if project.api is None:
        typer.secho(
            "api not configured — add ApiConfig(packages=[...]) to .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project.api


def _current_surface(project: Project, api: ApiConfig) -> list[str]:
    """Extract the current public surface for the configured packages.

    Args:
        project: The loaded project (provides the repo root for path resolution).
        api: The api configuration (provides the package directories).

    Returns:
        The sorted, de-duplicated surface lines.
    """
    return extract_surface([project.path(pkg) for pkg in api.packages])


def _print_diff(diff: SurfaceDiff) -> None:
    """Print a :class:`~pyclawd.api.SurfaceDiff` as ``+``/``-``/``~`` lines."""
    for line in diff.removed:
        typer.secho(f"  - {line}", fg="red")
    for before, after in diff.changed:
        typer.secho(f"  ~ {before}", fg="yellow")
        typer.secho(f"      → {after}", fg="yellow")
    for line in diff.added:
        typer.secho(f"  + {line}", fg="green")


def _compare() -> None:
    """Compare the current surface against the committed baseline (the default action)."""
    project = run.load_project_or_exit()
    api = _api_or_exit(project)
    baseline_path = project.path(api.baseline)
    baseline = read_baseline(baseline_path)

    if not baseline:
        typer.secho(
            f"no API baseline at {baseline_path} — record it with `pyclawd api update` "
            "and commit it.",
            fg="red",
            err=True,
        )
        raise typer.Exit(1)

    diff = diff_surface(_current_surface(project, api), baseline)
    if diff.is_empty():
        typer.secho("✅ api: public surface matches the baseline.", fg="green")
        raise typer.Exit(0)

    _print_diff(diff)
    breaking = diff.is_breaking()
    additions_only = not breaking and diff.added
    if breaking or (additions_only and api.strict):
        why = "breaking change" if breaking else "additions (strict mode)"
        typer.secho(
            f"\n❌ api: public surface drifted ({why}). If intended, re-bless with "
            f"`pyclawd api update` and commit `git diff {api.baseline}`.",
            fg="red",
        )
        raise typer.Exit(1)
    typer.secho(
        "\n✅ api: only non-breaking additions — re-bless with `pyclawd api update` "
        "when you are ready to record them.",
        fg="green",
    )
    raise typer.Exit(0)


def update() -> None:
    """Bless the baseline — re-record the public surface (humans bless; agents compare).

    Overwrites the committed baseline with the current surface. Afterwards **review**
    ``git diff`` of the baseline file and commit deliberately — never auto-bless in an
    autonomous loop.
    """
    project = run.load_project_or_exit()
    api = _api_or_exit(project)
    baseline_path = project.path(api.baseline)
    surface = _current_surface(project, api)
    write_baseline(baseline_path, surface)
    typer.secho(f"✓ recorded {len(surface)} symbols to {baseline_path}", fg="green")
    typer.secho(f"\nReview `git diff {api.baseline}` and commit the blessed surface.", fg="yellow")
    raise typer.Exit(0)


def status() -> None:
    """Show the surface size and any drift from the committed baseline."""
    project = run.load_project_or_exit()
    api = _api_or_exit(project)
    baseline_path = project.path(api.baseline)
    current = _current_surface(project, api)
    baseline = read_baseline(baseline_path)

    typer.secho(f"API surface for {', '.join(api.packages)}:", bold=True)
    typer.echo(f"  current:  {len(current)} symbols")
    if not baseline:
        typer.secho(
            f"  baseline: (none at {baseline_path} — run `pyclawd api update`)", fg="yellow"
        )
        raise typer.Exit(0)
    typer.echo(f"  baseline: {len(baseline)} symbols  ({baseline_path})")
    diff = diff_surface(current, baseline)
    if diff.is_empty():
        typer.secho("  ✓ in sync", fg="green")
        raise typer.Exit(0)
    typer.secho(
        f"  drift: {len(diff.removed)} removed · {len(diff.changed)} changed · "
        f"{len(diff.added)} added",
        fg="yellow",
    )
    _print_diff(diff)
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``api`` command group to *app*.

    The default invocation (``pyclawd api``) compares; ``update`` / ``status`` are
    subcommands. Always registered — each self-reports and exits ``2`` when the loaded
    project does not configure api.
    """
    api_app = typer.Typer(
        help="Public-API surface oracle: prove the public surface has not drifted.",
    )

    @api_app.callback(invoke_without_command=True)
    def _default(ctx: typer.Context) -> None:
        """Compare the current public surface against the committed baseline."""
        if ctx.invoked_subcommand is not None:
            return
        _compare()

    api_app.command()(update)
    api_app.command()(status)
    app.add_typer(api_app, name="api")
