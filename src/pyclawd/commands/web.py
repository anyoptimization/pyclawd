"""The ``pyclawd web`` command group — serve and manage the diff/review dashboard.

``pyclawd web`` is an **optional extra**: the web stack (FastAPI, uvicorn,
``watchfiles``) is not a base dependency, so this module imports it *lazily* inside
the commands. When the extra is missing, the user gets a one-line install hint
(``pip install 'pyclawd[web]'``) instead of an ``ImportError`` traceback — and
``pyclawd --help`` keeps working with no web deps present.

The dashboard watches many repos at once, so its project registry is independent
of the ambient ``.pyclawd/config.py``: ``pyclawd web serve`` auto-discovers repos
under the configured roots (default ``~/workspace``) and ``add``/``list``/
``remove`` curate that set. ``--repo`` registers and pre-selects one repo for a
quick single-project session.
"""

from __future__ import annotations

from pathlib import Path

import typer

from pyclawd.web.git import GitRepo
from pyclawd.web.registry import Registry

#: Default port for the dashboard (one above the gateway's, by convention).
DEFAULT_PORT = 8801

#: Shown when the optional web dependencies are not installed.
_MISSING_EXTRA = (
    "pyclawd web needs the optional web dependencies.\n"
    "Install them with:  pip install 'pyclawd[web]'"
)

web_app = typer.Typer(no_args_is_help=True, help="Live multi-project diff & review dashboard.")


def _registry() -> Registry:
    """Return the dashboard's on-disk project registry (no web deps required)."""
    return Registry.default()


def _require_web_stack() -> None:
    """Exit cleanly with an install hint if the optional web stack is absent."""
    import importlib.util

    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("uvicorn") is None:
        typer.secho(_MISSING_EXTRA, fg="yellow", err=True)
        raise typer.Exit(2)


def _assert_repo(path: str) -> str:
    """Resolve *path*, ensuring it is a git work tree; exit 2 otherwise."""
    resolved = str(Path(path).expanduser().resolve())
    if not GitRepo(root=Path(resolved)).is_repo():
        typer.secho(f"error: {resolved} is not a git work tree.", fg="red", err=True)
        raise typer.Exit(2)
    return resolved


@web_app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address (0.0.0.0 to expose on the LAN)."),
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="Port to listen on."),
    repo: str = typer.Option(
        None, "--repo", "-r", help="Register this repo and pre-select it on load."
    ),
) -> None:
    """Serve the multi-project diff dashboard.

    Auto-discovers git repos under the configured roots (default ``~/workspace``;
    edit them in the dashboard's settings). Pass ``--repo`` to register and
    pre-select a single repo for this session.
    """
    _require_web_stack()
    import uvicorn

    from pyclawd.web.app import _STATIC_DIR, create_app

    if not _STATIC_DIR.is_dir():
        typer.secho(
            "warning: the built frontend is missing — only the JSON API will be served, "
            "the dashboard UI will not load.\n"
            "In a source checkout, build it with:  "
            "cd src/pyclawd/web_frontend && npm install && npm run build",
            fg="yellow",
            err=True,
        )

    reg = _registry()
    default = None
    if repo:
        default = reg.add(_assert_repo(repo))

    projects = reg.projects()
    if not projects:
        typer.secho(
            "No projects found. Add one with 'pyclawd web add <path>' or set roots "
            "in the dashboard settings.",
            fg="yellow",
            err=True,
        )
    default = default or _first_starred(projects)
    typer.secho(
        f"pyclawd web → http://{host}:{port}  ({len(projects)} projects, default: {default})",
        fg="cyan",
    )
    uvicorn.run(create_app(default, reg), host=host, port=port)


def _first_starred(projects: dict) -> str | None:
    """Return a sensible default project: the first starred one, else the first by name."""
    names = sorted(projects)
    starred = [n for n in names if projects[n].starred]
    return starred[0] if starred else (names[0] if names else None)


@web_app.command("add")
def add(
    path: str = typer.Argument(..., help="Path to a git repository."),
    name: str = typer.Option(None, "--name", "-n", help="Override the project name."),
) -> None:
    """Register a project so it appears in the dashboard."""
    resolved = _assert_repo(path)
    registered = _registry().add(resolved, name)
    typer.secho(f"Added project '{registered}' → {resolved}", fg="green")


@web_app.command("list")
def list_projects() -> None:
    """List all dashboard projects (discovered + registered)."""
    projects = _registry().projects()
    if not projects:
        typer.echo("No projects. Add one with 'pyclawd web add <path>'.")
        return
    for name in sorted(projects, key=lambda n: (not projects[n].starred, n.lower())):
        entry = projects[name]
        star = "★" if entry.starred else " "
        tag = "" if entry.discovered else "  (registered)"
        typer.echo(f"{star} {name:24} {entry.path}{tag}")


@web_app.command("remove")
def remove(name: str = typer.Argument(..., help="Project name to unregister.")) -> None:
    """Unregister a manually-added project."""
    removed = _registry().remove(name)
    typer.echo(f"Removed '{name}'" if removed else f"'{name}' was not registered.")


def register(app: typer.Typer) -> None:
    """Attach the ``web`` command group to *app*."""
    app.add_typer(web_app, name="web")
