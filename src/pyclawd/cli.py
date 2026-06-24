"""pyclawd — a project-generic Python dev toolkit & agent toolbox.

A single CLI for working on any Python project: run code in the right env, run
tiered tests, build/clean artifacts, build cached docs, and health-check the
setup — all driven by a per-project ``.pyclawd/config.py``.

This module is a **thin assembler**: it builds the Typer app, defines the global
``--config`` option and the small meta commands (``doctor``, ``root``,
``version``), and registers the command groups from :mod:`pyclawd.commands`. The
real logic lives in the sibling modules (``run``, ``tests``, ``doctor``, …) and
in those command modules. Claude Code skills and slash commands shell out to
these commands rather than reimplementing them.
"""

from __future__ import annotations

import typer

from . import __version__, run
from .commands import _PASSTHROUGH
from .commands import build as build_cmd
from .commands import changelog as changelog_cmd
from .commands import config as config_cmd
from .commands import coverage as coverage_cmd
from .commands import docs as docs_cmd
from .commands import golden as golden_cmd
from .commands import ls as ls_cmd
from .commands import new as new_cmd
from .commands import quality as quality_cmd
from .commands import skills as skills_cmd
from .commands import test as test_cmd
from .discovery import ConfigError, load_project, set_config_override
from .doctor import dump_json, run_doctor

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="pyclawd — a project-generic Python dev toolkit & agent toolbox "
    "(run code, test, lint, build, doctor).",
)


@app.callback()
def main(
    config: str = typer.Option(
        None,
        "--config",
        help="Path to a config.py FILE or a DIRECTORY containing one "
        "(or a .pyclawd/config.py under it). Overrides PYCLAWD_CONFIG and "
        "walk-up discovery.",
        metavar="PATH",
    ),
) -> None:
    """Pyclawd — run code, test, build, and document any Python project."""
    if config:
        set_config_override(config)


# --------------------------------------------------------------------------- run


@app.command(context_settings=_PASSTHROUGH)
def python(ctx: typer.Context) -> None:
    """Run Python in the dev env with the repo on PYTHONPATH.

    e.g. `pyclawd python script.py`, `pyclawd python -m module`, `pyclawd python -c "import mypkg"`.
    """
    raise typer.Exit(run.python(ctx.args))


# -------------------------------------------------------------------------- meta


@app.command()
def doctor(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of rich table."),
) -> None:
    """Health-check the dev env (conda, deps, build, tools, git)."""
    if json_output:
        raise typer.Exit(dump_json())
    raise typer.Exit(run_doctor())


@app.command()
def root() -> None:
    """Print the detected project repo root (via the .pyclawd/config.py loader)."""
    project = run.load_project_or_exit()  # clean exit 2 on no/broken config
    typer.echo(str(project.root))


def _major_minor(v: str) -> tuple[int, int] | None:
    """Parse a ``major.minor`` tuple from a version string, or ``None`` if unparseable."""
    parts = v.strip().split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return None


@app.command()
def version(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON instead of text."),
) -> None:
    """Show the pyclawd version AND the version the local config was built against.

    Reports the running pyclawd (with its install location) and, when run inside a
    project, the ``pyclawd_version`` recorded in its ``.pyclawd/config.py`` — plus
    whether they share a ``major.minor`` (drift means the config may need migrating).
    """
    import json as _json
    import os

    import pyclawd as _pkg

    running = __version__
    location = os.path.dirname(_pkg.__file__)
    editable = f"{os.sep}site-packages{os.sep}" not in location

    config_version: str | None = None
    in_project = False
    try:
        project = load_project()
    except ConfigError:
        project = None
    if project is not None:
        in_project = True
        config_version = project.pyclawd_version or None

    match: bool | None = None
    if config_version is not None:
        rm, cm = _major_minor(running), _major_minor(config_version)
        match = rm is not None and cm is not None and rm == cm

    if json_output:
        payload = {
            "pyclawd": running,
            "location": location,
            "editable": editable,
            "in_project": in_project,
            "config_version": config_version,
            "match": match,
        }
        typer.echo(_json.dumps(payload, indent=2))
        raise typer.Exit(0)

    kind = "editable" if editable else "installed"
    typer.echo(f"pyclawd {running}  ({kind} — {location})")
    if not in_project:
        typer.secho("config   (not inside a pyclawd project)", fg="bright_black")
    elif config_version is None:
        typer.secho("config   (no pyclawd_version recorded in .pyclawd/config.py)", fg="yellow")
    elif match:
        typer.secho(f"config   built on {config_version}  ✓ matches", fg="green")
    else:
        typer.secho(
            f"config   built on {config_version}  ! drift from {running} — "
            f"see `pyclawd changelog --since {config_version}` then the `pyclawd-upgrade` skill",
            fg="yellow",
        )


# --------------------------------------------------------------------- registration

# All command groups are ALWAYS registered (no project load at import time). The
# global ``--config`` override is applied in the callback above, so command-time
# discovery — not import-time discovery — drives every command. Groups whose
# config block is optional (e.g. ``docs``) self-report cleanly at run time when
# the loaded project does not configure them.
build_cmd.register(app)
changelog_cmd.register(app)
config_cmd.register(app)
coverage_cmd.register(app)
test_cmd.register(app)
quality_cmd.register(app)
new_cmd.register(app)
skills_cmd.register(app)
docs_cmd.register(app)
golden_cmd.register(app)
ls_cmd.register(app)


if __name__ == "__main__":
    app()
