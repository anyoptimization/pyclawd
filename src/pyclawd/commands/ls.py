"""The ``pyclawd ls`` command — a code map of the project's files, each with its description.

pyclawd promotes a tiny "good Python code" convention: **every source file opens
with a one-line description**. For a ``.py`` file the canonical place is the
**module docstring's first line** (PEP 257); the fallback is a leading ``#``
comment. For other text files it is the first leading comment (``#``, ``//``, or
``<!-- ... -->``). ``pyclawd ls`` surfaces that convention as a skimmable,
agent-friendly map of the repository, and ``pyclawd ls --missing`` finds the
gaps still to fill.

File source
-----------
Files come from ``git ls-files`` run at the listed directory, so ``.gitignore`` is
respected for free. When the project is not a git repository (or git is
unavailable) it falls back to walking the tree, skipping the usual noise
(``.git``, ``__pycache__``, ``*.pyc``, the various tool caches, ``build``/``dist``,
``*.egg-info``). By default the listing includes **both tracked and
untracked-but-not-ignored** files; ``--tracked`` restricts it to git-tracked files.

Listed directory
-----------------
``pyclawd ls`` takes an optional ``PATH`` directory to list. Given a ``PATH`` it
lists that directory (resolved against the current working directory; absolute
paths accepted); omitted, it defaults to the project's ``src_dir`` (the code
root, configurable in ``.pyclawd/config.py``) when that exists, otherwise the
repo root. Output paths are shown **relative to the listed directory**, under a
header naming the root being listed.

The command never crashes on a single bad file: anything that fails to read or
parse is simply treated as having no description.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import typer

from .. import run
from ..project import Project

#: Maximum number of characters a description is truncated to (for clean columns).
_MAX_DESC = 100

#: Directory names skipped by the non-git walk fallback.
_NOISE_DIRS = {
    ".git",
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}


# --------------------------------------------------------------------------- #
# Description extraction.
# --------------------------------------------------------------------------- #


def _truncate(text: str) -> str:
    """Strip *text* and clamp it to :data:`_MAX_DESC` characters (with an ellipsis)."""
    text = text.strip()
    if len(text) > _MAX_DESC:
        text = text[: _MAX_DESC - 1].rstrip() + "…"
    return text


def _read_text(path: Path) -> str | None:
    """Return *path*'s decoded text, or ``None`` if it looks binary / can't be read.

    A NUL byte in the first chunk is treated as the binary signal; decoding uses a
    permissive ``errors="replace"`` so an odd encoding never raises.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


def _strip_comment_markers(line: str) -> str | None:
    """Return the text of a leading comment *line*, or ``None`` if it is not a comment.

    Recognises ``#`` (Python/shell/toml/yaml), ``//`` (C-style), and
    ``<!-- ... -->`` (HTML/Markdown) comment markers.
    """
    if line.startswith("<!--"):
        body = line[4:]
        if body.endswith("-->"):
            body = body[:-3]
        return body.strip()
    if line.startswith("//"):
        return line.lstrip("/").strip()
    if line.startswith("#"):
        return line.lstrip("#").strip()
    return None


def _leading_comment(text: str) -> str:
    """Return the first leading comment line in *text*, or ``""`` if none.

    Blank lines and a shebang (``#!``) are skipped; the **first** non-blank,
    non-shebang line decides the answer — if it is a comment its body is returned,
    otherwise the file opens with code and has no leading description.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#!"):
            continue
        body = _strip_comment_markers(line)
        return _truncate(body) if body else ""
    return ""


def _describe_py(text: str) -> str:
    """Return the description of a Python file: module docstring first, then a ``#`` comment."""
    try:
        module = ast.parse(text)
        doc = ast.get_docstring(module)
    except (SyntaxError, ValueError):
        doc = None
    if doc:
        for line in doc.splitlines():
            if line.strip():
                return _truncate(line)
    return _leading_comment(text)


def describe_file(path: Path) -> str:
    """Return the one-line description carried at the top of *path* (``""`` if none).

    ``.py`` and ``.pyx`` files use :func:`ast.get_docstring` (first non-empty line),
    falling back to a leading ``#`` comment. Other text files use the first leading
    comment. Binary/unreadable files — and anything that fails to parse — yield
    ``""``; this function is deliberately total and never raises.

    Args:
        path: Absolute path to the file to describe.

    Returns:
        The extracted description, stripped and truncated, or ``""``.
    """
    try:
        text = _read_text(path)
        if text is None:
            return ""
        if path.suffix in {".py", ".pyx"}:
            return _describe_py(text)
        return _leading_comment(text)
    except (OSError, ValueError, UnicodeError):
        return ""


# --------------------------------------------------------------------------- #
# File source — git first, walk fallback.
# --------------------------------------------------------------------------- #


def _git_files(root: Path, include_untracked: bool) -> list[str] | None:
    """Return root-relative tracked file paths via ``git ls-files``, or ``None``.

    ``None`` means "not a git repo / git unavailable" — the caller then walks the
    tree. With *include_untracked* the untracked-but-not-ignored files are added.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    files = [line for line in out.stdout.splitlines() if line]
    if include_untracked:
        try:
            extra = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            )
            files += [line for line in extra.stdout.splitlines() if line]
        except (OSError, subprocess.SubprocessError):
            pass
    return files


def _walk_files(root: Path) -> list[str]:
    """Return root-relative file paths by walking *root*, skipping the usual noise."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _NOISE_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            files.append(str((Path(dirpath) / name).relative_to(root)))
    return files


def _collect_files(root: Path, include_untracked: bool) -> list[str]:
    """Return the sorted, de-duplicated root-relative file list for *root*."""
    files = _git_files(root, include_untracked)
    if files is None:
        files = _walk_files(root)
    return sorted(set(files))


# --------------------------------------------------------------------------- #
# The command.
# --------------------------------------------------------------------------- #


def ls(
    path: str = typer.Argument(
        None,
        help="Directory to list (relative to cwd, or absolute). "
        "Defaults to the project's src_dir, then the repo root.",
    ),
    missing: bool = typer.Option(
        False, "--missing", help="Show ONLY files that have no description (the gaps to fill)."
    ),
    py: bool = typer.Option(False, "--py", help="Limit the listing to .py and .pyx files."),
    tracked: bool = typer.Option(
        False,
        "--tracked",
        help="Only git-tracked files (default also lists untracked, non-ignored files).",
    ),
) -> None:
    """List a directory's files with the one-line description from the top of each.

    With a ``PATH`` argument lists that directory; without one it defaults to the
    project's ``src_dir`` (the code root) when present, else the repo root. Files
    come from ``git ls-files`` (respecting ``.gitignore``), or a tree walk when the
    directory is not in a git repo. Paths are shown relative to the listed
    directory, sorted, followed by an ``N files · M described · K missing`` footer.
    A non-existent ``PATH`` exits ``2``; otherwise it always exits ``0`` — use
    ``--missing`` to review the gaps.
    """
    project = run.load_project_or_exit()
    root = project.root
    assert root is not None  # load_project_or_exit always sets root

    if path is not None:
        listdir = Path(path).expanduser().resolve()
        if not listdir.is_dir():
            typer.secho(f"✗ not a directory: {path}", fg="red", err=True)
            raise typer.Exit(2)
    else:
        candidate = project.path(project.src_dir)
        listdir = candidate if candidate.is_dir() else root

    try:
        header = str(listdir.resolve().relative_to(root.resolve())) or "."
    except ValueError:
        header = str(listdir)
    typer.secho(f"Listing {header}", fg="cyan", bold=True)

    files = _collect_files(listdir, include_untracked=not tracked)
    if py:
        files = [f for f in files if f.endswith(".py") or f.endswith(".pyx")]

    rows = [(rel, describe_file(listdir / rel)) for rel in files]
    total = len(rows)
    described = sum(1 for _, desc in rows if desc)

    shown = [(rel, desc) for rel, desc in rows if not desc] if missing else rows

    if shown:
        width = min(max(len(rel) for rel, _ in shown), 60)
        for rel, desc in shown:
            typer.echo(f"{rel.ljust(width)}  ", nl=False)
            typer.secho(desc, fg="bright_black")
    elif missing:
        typer.secho("no gaps — every file has a description.", fg="green")
    else:
        typer.secho("no files found.", fg="yellow")

    typer.secho(
        f"\n{total} files · {described} described · {total - described} missing",
        bold=True,
    )
    raise typer.Exit(0)


def _descriptions_filter(rel: str, project: Project) -> bool:
    """Return True when *rel* should be checked for a description.

    Applies ``project.descriptions_include`` (must match ≥1) then
    ``project.descriptions_exclude`` (skip if any matches).
    """
    includes = [re.compile(p) for p in project.descriptions_include]
    excludes = [re.compile(p) for p in project.descriptions_exclude]
    if includes and not any(pat.search(rel) for pat in includes):
        return False
    return not any(pat.search(rel) for pat in excludes)


def check_descriptions(project: Project, paths: list[str] | None = None) -> int:
    """Check that every source file in *project*'s ``src_dir`` has a description.

    Used by ``pyclawd check`` when ``"descriptions"`` is in
    ``quality.check_sequence``. Prints the missing files and a summary line.
    Returns ``0`` when all files are described, ``1`` when any are missing.

    Args:
        project: The loaded project config.
        paths: Optional list of specific files to check. When given, only those
            files are checked instead of the full ``src_dir``. The include/exclude
            filters still apply.
    """
    root = project.root
    assert root is not None
    candidate = project.path(project.src_dir)
    listdir = candidate if candidate.is_dir() else root

    if paths:
        eligible = [p for p in paths if _descriptions_filter(p, project)]
        rows = [
            (p, describe_file(Path(p) if Path(p).is_absolute() else root / p)) for p in eligible
        ]
    else:
        all_files = _collect_files(listdir, include_untracked=False)
        eligible = [f for f in all_files if _descriptions_filter(f, project)]
        rows = [(rel, describe_file(listdir / rel)) for rel in eligible]
    missing = [rel for rel, desc in rows if not desc]

    if missing:
        width = min(max(len(r) for r in missing), 60)
        for rel in missing:
            typer.secho(f"  {rel.ljust(width)}  ", nl=False)
            typer.secho("(no description)", fg="yellow")
        typer.secho(
            f"\n✗ {len(missing)}/{len(rows)} files lack a top-of-file description"
            " — add a module docstring or leading # comment.",
            fg="red",
        )
        return 1

    typer.secho(f"✓ all {len(rows)} files have descriptions", fg="green")
    return 0


def register(app: typer.Typer) -> None:
    """Attach the ``ls`` command to *app*."""
    app.command(name="ls")(ls)
