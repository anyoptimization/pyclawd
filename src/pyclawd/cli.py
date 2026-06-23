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
from .commands import build as build_cmd
from .commands import docs as docs_cmd
from .commands import ls as ls_cmd
from .commands import new as new_cmd
from .commands import quality as quality_cmd
from .commands import skills as skills_cmd
from .commands import test as test_cmd
from .discovery import ConfigError, load_project, set_config_override
from .doctor import run_doctor

# Commands that forward unknown args/options straight to a subprocess.
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}

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
    """pyclawd — run code, test, build, and document any Python project."""
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
def doctor() -> None:
    """Health-check the dev env (conda, deps, build, tools, git)."""
    raise typer.Exit(run_doctor())


@app.command()
def root() -> None:
    """Print the detected project repo root (via the .pyclawd/config.py loader)."""
    try:
        project = load_project()
    except ConfigError as exc:
        typer.secho(f"✗ {exc}", fg="red", err=True)
        raise typer.Exit(2) from None
    if project is None or project.root is None:
        typer.secho("not inside a project (no .pyclawd/config.py found)", fg="red", err=True)
        raise typer.Exit(2)
    typer.echo(str(project.root))


@app.command()
def version() -> None:
    """Print the pyclawd version."""
    typer.echo(f"pyclawd {__version__}")


# --------------------------------------------------------------------- registration

# All command groups are ALWAYS registered (no project load at import time). The
# global ``--config`` override is applied in the callback above, so command-time
# discovery — not import-time discovery — drives every command. Groups whose
# config block is optional (e.g. ``docs``) self-report cleanly at run time when
# the loaded project does not configure them.
build_cmd.register(app)
test_cmd.register(app)
quality_cmd.register(app)
new_cmd.register(app)
skills_cmd.register(app)
docs_cmd.register(app)
ls_cmd.register(app)


if __name__ == "__main__":
    app()
