"""The ``pyclawd changelog`` command — show pyclawd's changelog, optionally since a version.

This is the data half of the agent-driven upgrade flow. When a project's
``.pyclawd/config.py`` was authored against an older pyclawd (``pyclawd version``
shows the drift), ``pyclawd changelog --since <that-version>`` prints exactly what
changed so an agent can migrate the config. With no ``--since`` inside a project it
defaults to the config's own ``pyclawd_version``, so a bare ``pyclawd changelog``
answers "what changed since this repo was set up?".

The CHANGELOG ships inside the wheel (see ``force-include`` in ``pyproject.toml``),
so it is available wherever pyclawd is pip-installed — PyPI included — with a
fallback to the repo-root file for editable dev checkouts.
"""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

import typer

from ..discovery import ConfigError, load_project

#: Matches a Keep-a-Changelog version header, e.g. ``## [0.1.0] - 2026-06-24``.
_VERSION_HEADER = re.compile(r"^##\s*\[([^\]]+)\]")


def _changelog_text() -> str | None:
    """Return the CHANGELOG text from the installed package, or the repo root, or ``None``.

    Tries the packaged copy first (present in any pip-installed wheel), then falls
    back to the repo-root ``CHANGELOG.md`` two levels above ``src/pyclawd`` (editable
    dev checkouts, where ``force-include`` does not place the file).
    """
    try:
        res = files("pyclawd") / "CHANGELOG.md"
        if res.is_file():
            return res.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        pass

    import pyclawd

    candidate = Path(pyclawd.__file__).resolve().parents[2] / "CHANGELOG.md"
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return None


def _version_tuple(token: str) -> tuple[int, ...] | None:
    """Parse a dotted version token into an int tuple, or ``None`` if not numeric.

    Non-numeric tokens (e.g. ``"Unreleased"``) return ``None`` and are treated by
    the caller as newer than any released version.
    """
    try:
        return tuple(int(x) for x in token.strip().split("."))
    except ValueError:
        return None


def _sections(text: str) -> list[tuple[str, str]]:
    """Split the changelog into ``(version_token, body)`` sections in document order.

    Args:
        text: The full changelog markdown.

    Returns:
        One ``(token, body)`` pair per ``## [..]`` header, body including the header
        line. The preamble before the first header is ignored.
    """
    sections: list[tuple[str, str]] = []
    token: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = _VERSION_HEADER.match(line)
        if match:
            if token is not None:
                sections.append((token, "\n".join(body).strip()))
            token = match.group(1)
            body = [line]
        elif token is not None:
            body.append(line)
    if token is not None:
        sections.append((token, "\n".join(body).strip()))
    return sections


def _newer_sections(text: str, since: str) -> list[tuple[str, str]]:
    """Return changelog sections strictly newer than *since* (``Unreleased`` always wins)."""
    base = _version_tuple(since)
    out: list[tuple[str, str]] = []
    for token, body in _sections(text):
        version = _version_tuple(token)
        if version is None or base is None or version > base:
            out.append((token, body))
    return out


def changelog(
    since: str = typer.Option(
        None,
        "--since",
        metavar="VERSION",
        help="Only entries newer than VERSION (default: the config's pyclawd_version).",
    ),
    full: bool = typer.Option(False, "--full", help="Print the entire changelog (ignore --since)."),
) -> None:
    """Show what changed in pyclawd — by default since this project's config was authored.

    Run it after upgrading pyclawd to see what a config migration needs to cover.
    Pairs with ``pyclawd version`` (which flags the drift) and the ``pyclawd-upgrade``
    skill (which drives the migration).
    """
    text = _changelog_text()
    if text is None:
        typer.secho("✗ no CHANGELOG found for this pyclawd install", fg="red", err=True)
        raise typer.Exit(2)

    if full:
        typer.echo(text.strip())
        raise typer.Exit(0)

    if since is None:
        try:
            project = load_project()
        except ConfigError:
            project = None
        if project is not None and project.pyclawd_version:
            since = project.pyclawd_version

    if not since:
        typer.echo(text.strip())
        raise typer.Exit(0)

    newer = _newer_sections(text, since)
    if not newer:
        typer.secho(f"✓ nothing newer than {since} — config is current.", fg="green")
        raise typer.Exit(0)

    typer.secho(f"Changes in pyclawd since {since}:\n", bold=True)
    typer.echo("\n\n".join(body for _, body in newer))
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``changelog`` command to *app*."""
    app.command()(changelog)
