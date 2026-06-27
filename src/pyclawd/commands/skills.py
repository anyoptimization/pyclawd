"""The ``pyclawd skills`` command group — list and install the bundled skills.

pyclawd ships a small set of agent-facing Claude Code skills (the umbrella
``pyclawd`` plus ``pyclawd-doctor``, ``pyclawd-tests``, ``pyclawd-quality``,
``pyclawd-golden``, ``pyclawd-docs``, ``pyclawd-upgrade``) as packaged data under
:mod:`pyclawd.skills`.
They are thin wrappers over the real CLI — they tell an AI agent *what to run and
when*. This module is the thin Typer wrapper that exposes them to projects:

- ``pyclawd skills list`` — show the bundled skills with their one-line
  descriptions (parsed from each ``SKILL.md`` frontmatter).
- ``pyclawd skills install`` — copy (default) or symlink each bundled skill
  directory into a target (default ``~/.claude/skills/`` — **user scope**, since the
  skills are generic), so your agent picks them up across every project.

The generic, project-agnostic install/drift engine lives in
:mod:`pyclawd.skills_install` (so core modules like :mod:`pyclawd.doctor` can use it
without importing the command layer). This module re-exports the helpers it builds
on — :func:`install_skills` is also called by ``pyclawd new`` to make new/adopted
projects agent-ready automatically.

Exit-code contract (deterministic, agent-native):

- ``0`` — success (skills listed, or at least one installed / all already present).
- ``1`` — nothing was installable (no bundled skills found, or a real I/O error).
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..skills_install import (
    SKILL_PREFIX,
    bundled_skill_names,
    drifted_installed_skills,
    install_skills,
    orphaned_installed_skills,
    prune_installed_skills,
    skill_description,
    user_skills_dir,
)

__all__ = [
    "SKILL_PREFIX",
    "bundled_skill_names",
    "drifted_installed_skills",
    "install",
    "install_skills",
    "list_",
    "orphaned_installed_skills",
    "prune",
    "prune_installed_skills",
    "register",
    "skill_description",
    "user_skills_dir",
]


def _resolve_target(target: str | None) -> Path:
    """Resolve the install target: explicit *target*, else user scope.

    When *target* is given it is used as-is (``~`` expanded). Otherwise the
    generic skills install to user scope (:func:`user_skills_dir`).
    """
    if target is not None:
        return Path(target).expanduser()
    return user_skills_dir()


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
        help="Install destination (default: ~/.claude/skills — user scope).",
    ),
    symlink: bool = typer.Option(
        False, "--symlink", help="Symlink each skill dir instead of copying it."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing destination instead of skipping it."
    ),
    prune: bool = typer.Option(
        False,
        "--prune",
        help="After installing, also remove orphaned skills dropped from this bundle.",
    ),
) -> None:
    """Install the bundled skills into the user-scope ``~/.claude/skills/`` directory.

    Defaults to user scope (not per-project) because the skills are generic — shared
    across every pyclawd project and not committed into any one repo. Pass ``--target``
    to install elsewhere. Pass ``--prune`` to also remove orphaned skills left behind
    by a previous pyclawd (those no longer in this bundle).
    """
    dest = _resolve_target(target)
    installed, refreshed, skipped = install_skills(dest, symlink=symlink, force=force)

    verb = "symlinked" if symlink else "copied"
    for name in installed:
        typer.secho(f"  ✓ {verb} {name}", fg="green")
    for name in refreshed:
        typer.secho(f"  ↻ refreshed {name} (drifted from this pyclawd)", fg="cyan")
    for name in skipped:
        typer.secho(f"  · {name} (already current — pass --force to re-copy)", fg="bright_black")

    pruned: list[str] = []
    if prune:
        pruned = prune_installed_skills(dest)
        for name in pruned:
            typer.secho(f"  🗑 pruned {name} (orphan — not in this bundle)", fg="yellow")

    if not installed and not refreshed and not skipped:
        typer.secho("no bundled skills found to install", fg="red", err=True)
        raise typer.Exit(1)
    summary = f"{len(installed)} installed, {len(refreshed)} refreshed, {len(skipped)} skipped"
    if prune:
        summary += f", {len(pruned)} pruned"
    typer.secho(f"\n{summary} → {dest}", fg="green" if installed or refreshed else "yellow")
    raise typer.Exit(0)


def prune(
    target: str = typer.Option(
        None,
        "--target",
        metavar="DIR",
        help="Directory to prune (default: ~/.claude/skills — user scope).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List the orphans that would be removed without deleting them."
    ),
) -> None:
    """Remove orphaned pyclawd skills left behind when a skill is dropped from the bundle.

    An orphan is a ``pyclawd``/``pyclawd-*`` skill installed in the target whose name
    is no longer in the current bundle. Only such stale copies of *our own* skills are
    touched — a user's own skills are never removed. ``--dry-run`` reports without
    deleting.
    """
    dest = _resolve_target(target)

    if dry_run:
        orphans = orphaned_installed_skills(dest)
        if not orphans:
            typer.secho(f"no orphaned skills in {dest}", fg="green")
            raise typer.Exit(0)
        typer.secho("Would prune:", bold=True)
        for name in orphans:
            typer.secho(f"  🗑 {name}", fg="yellow")
        typer.secho(
            f"\n{len(orphans)} orphan(s) in {dest} (dry run — nothing removed)", fg="yellow"
        )
        raise typer.Exit(0)

    pruned = prune_installed_skills(dest)
    if not pruned:
        typer.secho(f"no orphaned skills to prune in {dest}", fg="green")
        raise typer.Exit(0)
    for name in pruned:
        typer.secho(f"  🗑 pruned {name}", fg="yellow")
    typer.secho(f"\n{len(pruned)} pruned → {dest}", fg="green")
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``skills`` command group (``list``, ``install``, ``prune``) to *app*."""
    group = typer.Typer(
        no_args_is_help=True,
        help="List, install, and prune the bundled pyclawd agent skills.",
    )
    group.command(name="list")(list_)
    group.command()(install)
    group.command()(prune)
    app.add_typer(group, name="skills")
