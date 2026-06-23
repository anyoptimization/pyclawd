"""The ``pyclawd skills`` command group — list and install the bundled skills.

pyclawd ships a small set of agent-facing Claude Code skills (``pyclawd-doctor``,
``pyclawd-tests``, ``pyclawd-quality``, ``pyclawd-docs``) as packaged data under
:mod:`pyclawd.skills`. They are thin wrappers over the real CLI — they tell an AI
agent *what to run and when*. This module exposes them to projects:

- ``pyclawd skills list`` — show the bundled skills with their one-line
  descriptions (parsed from each ``SKILL.md`` frontmatter).
- ``pyclawd skills install`` — copy (default) or symlink each ``pyclawd-*`` skill
  directory into a target (default ``<project-root>/.claude/skills/``), so the
  adopting project's agent picks them up.

Everything is discovered through :func:`importlib.resources.files`, so it works
identically from a source checkout or an installed wheel — no ``__file__`` path
hacks. The reusable :func:`install_skills` helper is also called by
``pyclawd new`` to make new/adopted projects agent-ready automatically.

Exit-code contract (deterministic, agent-native):

- ``0`` — success (skills listed, or at least one installed / all already present).
- ``1`` — nothing was installable (no bundled skills found, or a real I/O error).
"""

from __future__ import annotations

import os
import shutil
from importlib.resources import as_file, files
from pathlib import Path

import typer

from ..discovery import load_project

#: Directory-name prefix that marks a bundled skill (``pyclawd-doctor`` etc.).
SKILL_PREFIX = "pyclawd-"
#: Default install location, relative to the resolved project (or current) root.
DEFAULT_TARGET = Path(".claude") / "skills"


# --------------------------------------------------------------------------- #
# Discovery + frontmatter parsing.
# --------------------------------------------------------------------------- #


def _skills_pkg():  # type: ignore[no-untyped-def]
    """Return the packaged ``pyclawd.skills`` directory as an importlib Traversable."""
    return files("pyclawd.skills")


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the leading ``--- ... ---`` YAML frontmatter into a flat dict.

    Only simple top-level ``key: value`` lines are read (which is all the skills
    use); anything else is ignored. Returns an empty dict if there is no
    frontmatter block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def _is_bundled_skill(name: str) -> bool:
    """True for the umbrella ``pyclawd`` skill or any ``pyclawd-*`` skill directory."""
    return name == "pyclawd" or name.startswith(SKILL_PREFIX)


def bundled_skill_names() -> list[str]:
    """Return the sorted names of the bundled skills.

    A skill is a sub-directory of :mod:`pyclawd.skills` that contains a ``SKILL.md``
    and is either the umbrella ``pyclawd`` skill or starts with :data:`SKILL_PREFIX`.
    """
    root = _skills_pkg()
    names = [
        entry.name
        for entry in root.iterdir()
        if _is_bundled_skill(entry.name) and entry.is_dir() and (entry / "SKILL.md").is_file()
    ]
    return sorted(names)


def skill_description(name: str) -> str:
    """Return the one-line ``description`` from a bundled skill's frontmatter."""
    text = (_skills_pkg() / name / "SKILL.md").read_text(encoding="utf-8")
    return _parse_frontmatter(text).get("description", "")


# --------------------------------------------------------------------------- #
# Install (reused by ``pyclawd new``).
# --------------------------------------------------------------------------- #


def install_skills(
    target: Path,
    *,
    symlink: bool = False,
    force: bool = False,
) -> tuple[list[str], list[str]]:
    """Install the bundled skills into *target*, returning ``(installed, skipped)``.

    Each ``pyclawd-*`` skill directory is copied (default) or symlinked into
    *target* (created if missing). An existing destination is skipped unless
    *force* is set, in which case it is replaced.

    Parameters
    ----------
    target : pathlib.Path
        Destination directory (e.g. ``<root>/.claude/skills``).
    symlink : bool, optional
        Symlink each skill dir instead of copying it. Defaults to ``False``.
    force : bool, optional
        Replace an existing destination instead of skipping it. Defaults to
        ``False``.

    Returns
    -------
    tuple of (list of str, list of str)
        ``(installed, skipped)`` skill names.
    """
    target.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    skipped: list[str] = []

    # ``as_file`` yields a concrete filesystem path for the packaged dir (a no-op
    # for a normal installed/editable layout; only zipped resources are extracted).
    with as_file(_skills_pkg()) as src_root:
        for name in bundled_skill_names():
            dest = target / name
            if (dest.exists() or dest.is_symlink()) and not force:
                skipped.append(name)
                continue
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)

            src = src_root / name
            if symlink:
                os.symlink(src.resolve(), dest, target_is_directory=True)
            else:
                shutil.copytree(src, dest)
            installed.append(name)

    return installed, skipped


def _resolve_target(target: str | None) -> Path:
    """Resolve the install target: explicit *target*, else ``<root>/.claude/skills``.

    When *target* is given it is taken relative to the current directory (or used
    as-is if absolute). Otherwise the destination is :data:`DEFAULT_TARGET` under
    the discovered project root, falling back to the current working directory
    when not inside a pyclawd project.
    """
    if target is not None:
        return Path(target).expanduser()
    project = load_project()
    base = project.root if (project is not None and project.root is not None) else Path.cwd()
    return base / DEFAULT_TARGET


# --------------------------------------------------------------------------- #
# Commands.
# --------------------------------------------------------------------------- #


def list_() -> None:
    """List the bundled ``pyclawd-*`` skills with their one-line descriptions."""
    names = bundled_skill_names()
    if not names:
        typer.secho("no bundled skills found", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho("Bundled pyclawd skills:", bold=True)
    for name in names:
        typer.echo(f"  {name}")
        desc = skill_description(name)
        if desc:
            typer.secho(f"    {desc}", fg="bright_black")
    raise typer.Exit(0)


def install(
    target: str = typer.Option(
        None,
        "--target",
        metavar="DIR",
        help="Install destination (default: <project-root>/.claude/skills).",
    ),
    symlink: bool = typer.Option(
        False, "--symlink", help="Symlink each skill dir instead of copying it."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing destination instead of skipping it."
    ),
) -> None:
    """Install the bundled skills into a project's ``.claude/skills/`` directory."""
    dest = _resolve_target(target)
    installed, skipped = install_skills(dest, symlink=symlink, force=force)

    verb = "symlinked" if symlink else "copied"
    for name in installed:
        typer.secho(f"  ✓ {verb} {name}", fg="green")
    for name in skipped:
        typer.secho(f"  · {name} (exists — pass --force to replace)", fg="bright_black")

    if not installed and not skipped:
        typer.secho("no bundled skills found to install", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho(
        f"\n{len(installed)} installed, {len(skipped)} skipped → {dest}",
        fg="green" if installed else "yellow",
    )
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``skills`` command group (``list``, ``install``) to *app*."""
    group = typer.Typer(
        no_args_is_help=True,
        help="List and install the bundled pyclawd agent skills.",
    )
    group.command(name="list")(list_)
    group.command()(install)
    app.add_typer(group, name="skills")
