"""Generic, project-agnostic install/drift logic for the bundled pyclawd skills.

This is the *core* of skill management — discovery of the packaged
``pyclawd.skills`` data, copy/symlink installation into a target directory, and
drift detection against the running pyclawd. It lives at top level (not under
``commands/``) so core modules such as :mod:`pyclawd.doctor` can import it without
reaching down into the command layer. The :mod:`pyclawd.commands.skills` module is
the thin Typer wrapper over these helpers.

Everything is discovered through :func:`importlib.resources.files`, so it works
identically from a source checkout or an installed wheel — no ``__file__`` path
hacks.
"""

from __future__ import annotations

import os
import shutil
from importlib.resources import as_file, files
from pathlib import Path

#: Directory-name prefix that marks a bundled skill (``pyclawd-doctor`` etc.).
SKILL_PREFIX = "pyclawd-"


def user_skills_dir() -> Path:
    """User-scope skills directory (``~/.claude/skills``) — the default install target.

    The bundled pyclawd skills are **generic** (nothing project-specific), so they
    belong in user scope — installed once and shared across every repo — rather than
    vendored into each project's ``.claude/skills/`` (and committed by accident).
    """
    return Path.home() / ".claude" / "skills"


# --------------------------------------------------------------------------- #
# Discovery + frontmatter parsing.
# --------------------------------------------------------------------------- #


def _skills_pkg():
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


def _trees_differ(src: Path, dest: Path) -> bool:
    """Return True if the file trees at *src* and *dest* differ in names or content.

    Used to detect a **drifted** installed skill — one copied from an older pyclawd
    whose bundled content has since changed — so it can be auto-refreshed.

    Args:
        src: The bundled skill directory.
        dest: The installed skill directory to compare against.

    Returns:
        True when the set of files differs or any file's bytes differ.
    """
    src_files = {p.relative_to(src) for p in src.rglob("*") if p.is_file()}
    dest_files = {p.relative_to(dest) for p in dest.rglob("*") if p.is_file()}
    if src_files != dest_files:
        return True
    return any((src / rel).read_bytes() != (dest / rel).read_bytes() for rel in src_files)


def install_skills(
    target: Path | None = None,
    *,
    symlink: bool = False,
    force: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """Install the bundled skills into *target*, returning ``(installed, refreshed, skipped)``.

    Each bundled skill directory is copied (default) or symlinked into *target*
    (created if missing). A destination that does not yet exist is **installed**. An
    existing destination that has **drifted** from the bundled content (e.g. it was
    copied from an older pyclawd) is **refreshed** — re-copied in place — so an
    upgrade propagates without ``--force``; pass *force* to refresh even identical
    ones. A destination already identical to the bundled skill is **skipped**, as is
    a symlinked one (a symlink always tracks the source).

    Args:
        target: Destination directory. Defaults to user scope
            (:func:`user_skills_dir`, ``~/.claude/skills``) when ``None``.
        symlink: Symlink each skill dir instead of copying it. Defaults to ``False``.
        force: Refresh an existing destination even when it has not drifted.
            Defaults to ``False``.

    Returns:
        ``(installed, refreshed, skipped)`` skill names.
    """
    if target is None:
        target = user_skills_dir()
    target.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    refreshed: list[str] = []
    skipped: list[str] = []

    # ``as_file`` yields a concrete filesystem path for the packaged dir (a no-op
    # for a normal installed/editable layout; only zipped resources are extracted).
    with as_file(_skills_pkg()) as src_root:
        for name in bundled_skill_names():
            dest = target / name
            src = src_root / name
            exists = dest.exists() or dest.is_symlink()

            # A symlink always reflects the source; an identical copy is current.
            current = dest.is_symlink() or (dest.exists() and not _trees_differ(src, dest))
            if exists and not force and current:
                skipped.append(name)
                continue

            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                shutil.rmtree(dest)

            if symlink:
                os.symlink(src.resolve(), dest, target_is_directory=True)
            else:
                shutil.copytree(src, dest)
            (refreshed if exists else installed).append(name)

    return installed, refreshed, skipped


def drifted_installed_skills(target: Path | None = None) -> list[str]:
    """Return installed skills whose content has drifted from the bundled version.

    Only considers skills that are actually **installed** at *target* (a missing
    skill is treated as an opt-out, not drift) and **copied** (a symlink always
    tracks the source, so it can never drift). Used by ``pyclawd doctor`` to WARN
    when a user-scope skill is stale relative to the running pyclawd.

    Args:
        target: Directory to inspect. Defaults to user scope (:func:`user_skills_dir`).

    Returns:
        The sorted names of installed-but-drifted skills.
    """
    if target is None:
        target = user_skills_dir()
    drifted: list[str] = []
    with as_file(_skills_pkg()) as src_root:
        for name in bundled_skill_names():
            dest = target / name
            if not dest.exists() or dest.is_symlink():
                continue
            if _trees_differ(src_root / name, dest):
                drifted.append(name)
    return sorted(drifted)


# --------------------------------------------------------------------------- #
# Prune (orphans left behind when a skill is dropped from the bundle).
# --------------------------------------------------------------------------- #


def _remove_skill_dest(dest: Path) -> None:
    """Remove an installed skill destination — a symlink, file, or directory tree.

    Mirrors the removal branch in :func:`install_skills` so prune and refresh stay
    consistent.

    Args:
        dest: The installed skill path to remove.
    """
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)


def orphaned_installed_skills(target: Path | None = None) -> list[str]:
    """Return installed pyclawd skills that are no longer part of the current bundle.

    An **orphan** is a directory under *target* that looks like a bundled pyclawd
    skill — its name is the umbrella ``pyclawd`` or starts with :data:`SKILL_PREFIX`
    (per :func:`_is_bundled_skill`) and it contains a ``SKILL.md`` — but whose name
    is not in :func:`bundled_skill_names` (the skills this pyclawd currently ships).
    These are left behind when a skill is dropped from a newer pyclawd; ``pyclawd
    skills install`` refreshes the current bundle but never removes them. Non-pyclawd
    skills (anything not matching the naming) are never listed, so a user's own
    skills are never touched.

    Args:
        target: Directory to inspect. Defaults to user scope (:func:`user_skills_dir`).

    Returns:
        The sorted names of installed-but-orphaned bundled skills (``[]`` when
        *target* does not exist).
    """
    if target is None:
        target = user_skills_dir()
    if not target.is_dir():
        return []
    current = set(bundled_skill_names())
    orphans = [
        entry.name
        for entry in target.iterdir()
        if _is_bundled_skill(entry.name)
        and entry.name not in current
        and (entry / "SKILL.md").is_file()
    ]
    return sorted(orphans)


def prune_installed_skills(target: Path | None = None) -> list[str]:
    """Remove orphaned bundled skills from *target*, returning the names removed.

    Deletes each skill reported by :func:`orphaned_installed_skills` — handling both
    real directory copies and symlinks — and never touches a non-pyclawd skill or a
    still-bundled one. The complement of ``pyclawd golden prune``: agents may run it,
    it only removes stale copies of *our own* skills.

    Args:
        target: Directory to prune. Defaults to user scope (:func:`user_skills_dir`).

    Returns:
        The sorted names of the orphaned skills that were removed.
    """
    if target is None:
        target = user_skills_dir()
    removed = orphaned_installed_skills(target)
    for name in removed:
        _remove_skill_dest(target / name)
    return removed
