"""A pure, typed git layer for the web dashboard — diffs, change lists, refs.

Everything the dashboard knows about a repository flows through :class:`GitRepo`.
It shells out to ``git`` and returns small, typed value objects
(:class:`FileChange`, :class:`Hunk`, :class:`FileView`, …) rather than the loose
dicts the original prototype passed around — so callers (and the FastAPI layer
that serialises these) get a checked contract, and this module can be unit-tested
with nothing but a scratch repo.

Either side of a comparison may be the live working tree or any committed ref
(branch, tag, or SHA). The working tree is represented by the :data:`WORKING_TREE`
sentinel; a normal ``str`` is any git revision. ``base`` is the *old* (left) side
and ``target`` is the *new* (right) side, mirroring ``git diff OLD NEW``.

This module deliberately imports **no web dependencies** — it is the foundation
the optional ``[web]`` extra builds on, and it stays importable (and testable)
without FastAPI installed.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import subprocess
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Final

#: Sentinel ``ref`` value meaning "the live working tree" (as opposed to a commit).
#: ``None`` and ``""`` are normalised to this by :func:`is_working_tree`.
WORKING_TREE: Final = "WORKING_TREE"

#: A side of a comparison: either a git revision (branch/tag/SHA) or the working tree.
Ref = str


def is_working_tree(ref: Ref | None) -> bool:
    """Return ``True`` when *ref* denotes the working tree rather than a commit."""
    return ref in (None, "", WORKING_TREE)


# --------------------------------------------------------------------------- #
# Value objects.
# --------------------------------------------------------------------------- #


class ChangeStatus(str, Enum):
    """How a file differs between the two sides of a comparison.

    String-valued so it serialises straight to JSON. ``COPIED`` and
    ``TYPE_CHANGED`` are folded into ``MODIFIED`` by the change parser; they are
    not produced as distinct statuses.
    """

    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"


class LineKind(str, Enum):
    """The role of a single line within a diff: added, deleted, or unchanged context."""

    ADD = "add"
    DEL = "del"
    CONTEXT = "ctx"


@dataclass(frozen=True)
class FileChange:
    """One file's change between two sides of a comparison.

    Attributes:
        path: Repo-relative path on the new side (the rename target, if renamed).
        status: How the file changed, or ``None`` when listing *all* files and this
            one is unchanged (see :meth:`GitRepo.all_files`).
        old_path: The previous path for a rename, else ``None``.
        additions: Lines added (``0`` for binary files).
        deletions: Lines removed (``0`` for binary files).
        untracked: ``True`` for a new file not yet known to git.
    """

    path: str
    status: ChangeStatus | None
    old_path: str | None = None
    additions: int = 0
    deletions: int = 0
    untracked: bool = False


@dataclass(frozen=True)
class DiffLine:
    """A single rendered line of a diff or full-file view.

    Attributes:
        kind: Whether the line was added, deleted, or is unchanged context.
        old: 1-based line number on the old side, or ``None`` for an added line.
        new: 1-based line number on the new side, or ``None`` for a deleted line.
        content: The line's text, without the leading ``+``/``-``/`` `` marker.
        html: Syntax-highlighted HTML for :attr:`content` (Pygments), or ``None``
            when the file type is not highlightable — callers render plain text.
    """

    kind: LineKind
    old: int | None
    new: int | None
    content: str
    html: str | None = None


@dataclass(frozen=True)
class Hunk:
    """A contiguous block of changed lines, as delimited by an ``@@`` header."""

    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass(frozen=True)
class FileView:
    """A renderable view of one file, in either ``"diff"`` or ``"full"`` mode.

    Exactly one of :attr:`hunks` / :attr:`lines` is populated for a text file:
    ``"diff"`` mode fills :attr:`hunks`, ``"full"`` mode fills :attr:`lines`. A
    binary file sets :attr:`binary` and leaves both empty.

    Attributes:
        path: Repo-relative path of the viewed file.
        status: How the file changed (``None`` when shown unchanged).
        mode: ``"diff"`` or ``"full"``.
        binary: ``True`` when the file is binary and has no text view.
        unchanged: ``True`` when there is no difference and the plain content is shown.
        hunks: The diff hunks, in ``"diff"`` mode.
        lines: The flat line list, in ``"full"`` mode (or for unchanged content).
    """

    path: str
    status: ChangeStatus | None
    mode: str
    binary: bool = False
    unchanged: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    lines: list[DiffLine] = field(default_factory=list)


@dataclass(frozen=True)
class Commit:
    """A recent commit, for the ref picker."""

    sha: str
    subject: str
    author: str
    date: str


@dataclass(frozen=True)
class RefInfo:
    """Branches, tags, recent commits, and the current branch — fuel for ref pickers."""

    branches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    commits: list[Commit] = field(default_factory=list)
    current: str = ""


@dataclass(frozen=True)
class RepoStatus:
    """Branch, working-tree dirtiness, and ahead/behind — for the project switcher."""

    branch: str
    dirty: int
    ahead: int
    behind: int


# --------------------------------------------------------------------------- #
# Parsing helpers (pure functions — no git, trivially testable).
# --------------------------------------------------------------------------- #

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)")


def numstat_path(rest: str) -> str:
    """Resolve the new path from the trailing field of a ``--numstat`` line.

    ``git`` renders renames either inline (``old.py => new.py``) or with a braced
    common prefix/suffix (``src/{a => b}/x.py``). Both collapse to the new path.

    Args:
        rest: The path field of a numstat line (everything after the two counts).

    Returns:
        The new (post-rename) repo-relative path.
    """
    rest = rest.strip()
    if "=>" not in rest:
        return rest
    if "{" in rest:
        pre, rest2 = rest.split("{", 1)
        mid, post = rest2.split("}", 1)
        new = mid.split("=>")[1].strip()
        return f"{pre}{new}{post}"
    return rest.split("=>")[1].strip()


def parse_hunks(diff_text: str) -> list[Hunk] | None:
    """Parse unified-diff text into :class:`Hunk` objects.

    Tracks old/new line numbers across each hunk so every :class:`DiffLine`
    carries its true position on both sides.

    Args:
        diff_text: The output of ``git diff`` for a single file.

    Returns:
        The parsed hunks, or ``None`` if the file is binary (no text diff exists).
    """
    hunks: list[Hunk] = []
    cur: Hunk | None = None
    old_n = new_n = 0
    for line in diff_text.splitlines():
        if line.startswith("Binary files") or line.startswith("GIT binary patch"):
            return None
        m = _HUNK_RE.match(line)
        if m:
            old_n, new_n = int(m.group(1)), int(m.group(2))
            cur = Hunk(header=(m.group(3) or "").strip())
            hunks.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            cur.lines.append(DiffLine(LineKind.ADD, None, new_n, line[1:]))
            new_n += 1
        elif line.startswith("-"):
            cur.lines.append(DiffLine(LineKind.DEL, old_n, None, line[1:]))
            old_n += 1
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            cur.lines.append(DiffLine(LineKind.CONTEXT, old_n, new_n, line[1:]))
            old_n += 1
            new_n += 1
    return hunks


def _diff_revisions(base: Ref, target: Ref | None) -> list[str] | None:
    """Return the ``git diff`` revision arguments mapping old=*base* → new=*target*.

    Uses ``-R`` so the working tree can sit on the *old* (left) side too — letting
    either side be the working tree, a branch, a tag, or a commit.

    Args:
        base: The old (left) side.
        target: The new (right) side.

    Returns:
        The revision args to splice into a ``git diff`` invocation, or ``None``
        when both sides are the working tree (there is nothing to diff).
    """
    base = base or WORKING_TREE
    target = target or WORKING_TREE
    base_wt, target_wt = is_working_tree(base), is_working_tree(target)
    if base_wt and target_wt:
        return None
    if target_wt:
        return [base]  # base(ref) → working tree
    if base_wt:
        return ["-R", target]  # working tree → target(ref)
    return [base, target]  # ref → ref


# --------------------------------------------------------------------------- #
# The repository.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GitRepo:
    """A git work tree the dashboard can inspect.

    All methods shell out to ``git`` with this :attr:`root` as the working
    directory. Instances are cheap and stateless; create one per request.
    """

    root: Path

    def _git(self, *args: str) -> tuple[int, str, str]:
        """Run ``git *args`` in :attr:`root`; return ``(returncode, stdout, stderr)``."""
        proc = subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    # -- predicates -------------------------------------------------------- #

    def is_repo(self) -> bool:
        """Return ``True`` when :attr:`root` is inside a git work tree."""
        code, out, _ = self._git("rev-parse", "--is-inside-work-tree")
        return code == 0 and out.strip() == "true"

    def contains(self, rel_path: str) -> bool:
        """Return ``True`` when *rel_path* resolves inside :attr:`root`.

        Guards the diff endpoint against path traversal: a crafted ``..`` path
        that escapes the repo is rejected before any git/file access.
        """
        try:
            root = self.root.resolve()
            full = (root / rel_path).resolve()
        except OSError:
            return False
        return full == root or root in full.parents

    def working_text(self, path: str) -> str:
        """Return the working-tree text of *path* (empty string if it is absent)."""
        try:
            return (self.root / path).read_text(errors="replace")
        except OSError:
            return ""

    def save_file(self, path: str, content: str) -> None:
        """Overwrite *path* in the working tree with *content*, creating parents."""
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def delete_file(self, path: str) -> bool:
        """Delete *path* from the working tree; ``False`` if it was already missing."""
        try:
            (self.root / path).unlink()
            return True
        except FileNotFoundError:
            return False

    def _is_untracked(self, path: str) -> bool:
        """Return ``True`` when *path* is not tracked by git."""
        _, out, _ = self._git("ls-files", "--", path)
        return out.strip() == ""

    def _exists_at(self, ref: str, path: str) -> bool:
        """Return ``True`` when *path* exists in committed *ref*."""
        return self._git("cat-file", "-e", f"{ref}:{path}")[0] == 0

    def _side_has(self, ref: Ref | None, path: str) -> bool:
        """Return ``True`` when *path* exists on the side identified by *ref*."""
        if is_working_tree(ref):
            return (self.root / path).exists()
        assert ref is not None  # narrowed by is_working_tree
        return self._exists_at(ref, path)

    # -- change lists ------------------------------------------------------ #

    def changes(self, base: Ref, target: Ref | None = None) -> list[FileChange]:
        """List files that differ between *base* and *target*.

        When *target* is the working tree, untracked files are included as added.

        Args:
            base: The old (left) side.
            target: The new (right) side; defaults to the working tree.

        Returns:
            The changed files, sorted by path.
        """
        revisions = _diff_revisions(base, target)
        if revisions is None:
            return []

        changes: dict[str, FileChange] = {}
        _, out, _ = self._git("diff", "--name-status", "-M", *revisions)
        for line in out.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0]:
                continue
            code = parts[0]
            if code.startswith("R") and len(parts) >= 3:
                status, old, path = ChangeStatus.RENAMED, parts[1], parts[2]
            elif code.startswith("C") and len(parts) >= 3:
                status, old, path = ChangeStatus.MODIFIED, parts[1], parts[2]
            else:
                status, old, path = _status_from_code(code[0]), None, parts[-1]
            changes[path] = FileChange(path=path, status=status, old_path=old)

        _, out, _ = self._git("diff", "--numstat", "-M", *revisions)
        for line in out.splitlines():
            cols = line.split("\t", 2)
            if len(cols) != 3:
                continue
            adds, dels, rest = cols
            path = numstat_path(rest)
            existing = changes.get(path)
            if existing is not None:
                changes[path] = _with_counts(existing, adds, dels)

        if is_working_tree(target):
            self._add_untracked(changes)

        return sorted(changes.values(), key=lambda c: c.path)

    def _add_untracked(self, changes: dict[str, FileChange]) -> None:
        """Add working-tree files unknown to git as ``ADDED`` entries of *changes*."""
        _, out, _ = self._git("ls-files", "--others", "--exclude-standard")
        for path in out.splitlines():
            if not path:
                continue
            try:
                n = len((self.root / path).read_text(errors="replace").splitlines())
            except OSError:
                n = 0
            changes[path] = FileChange(
                path=path, status=ChangeStatus.ADDED, additions=n, untracked=True
            )

    def all_files(self, base: Ref, target: Ref | None = None) -> list[FileChange]:
        """List every file on the new side, annotated with its change status.

        Unchanged files get a ``status`` of ``None``; changed files carry their
        :class:`FileChange` from :meth:`changes`. Powers the "All files" view.
        """
        changed = {c.path: c for c in self.changes(base, target)}
        if is_working_tree(target):
            _, out, _ = self._git("ls-files")
        else:
            assert target is not None  # narrowed by is_working_tree
            _, out, _ = self._git("ls-tree", "-r", "--name-only", target)
        for path in out.splitlines():
            if path and path not in changed:
                changed[path] = FileChange(path=path, status=None)
        return sorted(changed.values(), key=lambda c: c.path)

    def tracked_paths(self) -> list[str]:
        """Return all tracked + untracked-but-not-ignored paths (for the file palette)."""
        _, tracked, _ = self._git("ls-files")
        _, untracked, _ = self._git("ls-files", "--others", "--exclude-standard")
        return sorted({p for p in tracked.splitlines() + untracked.splitlines() if p})

    # -- single-file view -------------------------------------------------- #

    def file_view(
        self, base: Ref, path: str, mode: str = "diff", target: Ref | None = None
    ) -> FileView:
        """Build a renderable view of one file, comparing *base* against *target*.

        Args:
            base: The old (left) side.
            path: Repo-relative path of the file to view.
            mode: ``"diff"`` for hunks, ``"full"`` for the whole file with changes
                highlighted.
            target: The new (right) side; defaults to the working tree.

        Returns:
            A :class:`FileView`. Binary files come back with ``binary=True`` and no
            lines; an unchanged file comes back with its plain content.
        """
        base_wt, target_wt = is_working_tree(base), is_working_tree(target)
        new_ref = WORKING_TREE if target_wt else target
        old_ref = WORKING_TREE if base_wt else base

        if base_wt and target_wt:
            # Both sides are the working tree — nothing to diff; just show the file.
            return self._highlight(self._plain_view(path, WORKING_TREE), WORKING_TREE, WORKING_TREE)

        status = self._derive_status(base, target, path)
        diff = self._raw_diff(base, target, path, target_wt)
        hunks = parse_hunks(diff)
        if hunks is None:
            return FileView(path=path, status=status, mode=mode, binary=True)
        if not hunks:
            return self._highlight(self._plain_view(path, new_ref), old_ref, new_ref)

        if mode == "full":
            return self._highlight(
                self._full_view(path, status, hunks, old_ref, new_ref), old_ref, new_ref
            )
        view = FileView(path=path, status=status, mode="diff", hunks=hunks)
        return self._highlight(view, old_ref, new_ref)

    def _highlight(self, view: FileView, old_ref: Ref | None, new_ref: Ref | None) -> FileView:
        """Attach Pygments HTML to every diff line, using full-file lexer context.

        Each line is coloured from the *whole-file* highlight of the side it lives
        on (deletions from the old side, additions/context from the new), so
        multi-line constructs like docstrings render correctly on every line.
        Returns *view* unchanged when the file type is not highlightable.
        """
        if view.binary:
            return view
        from .highlight import highlight_lines

        old_html = highlight_lines(view.path, self._read_side(old_ref, view.path))
        new_html = highlight_lines(view.path, self._read_side(new_ref, view.path))
        if old_html is None and new_html is None:
            return view

        def hl(line: DiffLine) -> DiffLine:
            if line.kind is LineKind.DEL and line.old is not None and old_html is not None:
                src, idx = old_html, line.old - 1
            elif line.new is not None and new_html is not None:
                src, idx = new_html, line.new - 1
            elif line.old is not None and old_html is not None:
                src, idx = old_html, line.old - 1
            else:
                return line
            return replace(line, html=src[idx]) if 0 <= idx < len(src) else line

        if view.mode == "full":
            return replace(view, lines=[hl(line) for line in view.lines])
        return replace(
            view, hunks=[replace(h, lines=[hl(line) for line in h.lines]) for h in view.hunks]
        )

    def _raw_diff(self, base: Ref, target: Ref | None, path: str, target_wt: bool) -> str:
        """Return raw ``git diff`` text for *path*, handling brand-new untracked files."""
        if target_wt and self._is_untracked(path) and not self._exists_at(base, path):
            # Untracked new file: --no-index exits 1 when files differ but still
            # prints the diff on stdout.
            _, diff, _ = self._git("diff", "--no-color", "--no-index", "--", "/dev/null", path)
            return diff
        revisions = _diff_revisions(base, target) or []
        _, diff, _ = self._git("diff", "--no-color", "-M", *revisions, "--", path)
        return diff

    def _derive_status(self, base: Ref, target: Ref | None, path: str) -> ChangeStatus:
        """Classify *path* as added / deleted / modified from which sides hold it."""
        old_has, new_has = self._side_has(base, path), self._side_has(target, path)
        if new_has and not old_has:
            return ChangeStatus.ADDED
        if old_has and not new_has:
            return ChangeStatus.DELETED
        return ChangeStatus.MODIFIED

    def _plain_view(self, path: str, ref: Ref | None) -> FileView:
        """Return a ``"full"`` view of *path* at *ref* with every line as context."""
        src = self._read_side(ref, path)
        lines = [DiffLine(LineKind.CONTEXT, i + 1, i + 1, text) for i, text in enumerate(src)]
        return FileView(path=path, status=None, mode="full", unchanged=True, lines=lines)

    def _full_view(
        self,
        path: str,
        status: ChangeStatus,
        hunks: list[Hunk],
        old_ref: Ref | None,
        new_ref: Ref | None,
    ) -> FileView:
        """Render the whole file with changed lines highlighted (``"full"`` mode)."""
        if status is ChangeStatus.DELETED:
            src = self._read_side(old_ref, path)
            lines = [DiffLine(LineKind.DEL, i + 1, None, text) for i, text in enumerate(src)]
            return FileView(path=path, status=status, mode="full", lines=lines)

        src = self._read_side(new_ref, path)
        added = {ln.new for h in hunks for ln in h.lines if ln.kind is LineKind.ADD}
        lines = [
            DiffLine(
                LineKind.ADD if (i + 1) in added else LineKind.CONTEXT,
                None,
                i + 1,
                text,
            )
            for i, text in enumerate(src)
        ]
        return FileView(path=path, status=status, mode="full", lines=lines)

    def _read_side(self, ref: Ref | None, path: str) -> list[str]:
        """Return the lines of *path* on the side identified by *ref*."""
        if is_working_tree(ref):
            try:
                return (self.root / path).read_text(errors="replace").splitlines()
            except OSError:
                return []
        assert ref is not None  # narrowed by is_working_tree
        _, content, _ = self._git("show", f"{ref}:{path}")
        return content.splitlines()

    # -- metadata ---------------------------------------------------------- #

    def status(self) -> RepoStatus:
        """Return the branch, dirty-file count, and ahead/behind vs upstream."""
        _, branch, _ = self._git("rev-parse", "--abbrev-ref", "HEAD")
        _, porcelain, _ = self._git("status", "--porcelain")
        dirty = sum(1 for line in porcelain.splitlines() if line.strip())
        ahead = behind = 0
        code, out, _ = self._git("rev-list", "--left-right", "--count", "@{upstream}...HEAD")
        if code == 0 and out.strip():
            with contextlib.suppress(ValueError):
                behind, ahead = (int(x) for x in out.split())
        return RepoStatus(branch=branch.strip(), dirty=dirty, ahead=ahead, behind=behind)

    def refs(self) -> RefInfo:
        """Return branches, tags, recent commits, and the current branch."""
        _, out, _ = self._git(
            "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"
        )
        branches = [b for b in out.splitlines() if b and "->" not in b and b != "origin"]
        _, out, _ = self._git("tag", "--sort=-creatordate")
        tags = [t for t in out.splitlines() if t]
        _, out, _ = self._git("log", "-60", "--pretty=%h%x1f%s%x1f%an%x1f%ad", "--date=short")
        commits = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append(Commit(parts[0], parts[1], parts[2], parts[3]))
        _, current, _ = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return RefInfo(branches=branches, tags=tags, commits=commits, current=current.strip())

    # -- liveness ---------------------------------------------------------- #

    def state_token(self, base: Ref, target: Ref | None = None) -> str:
        """Return a short fingerprint that changes whenever either side moves.

        For a committed ref the fingerprint is its resolved SHA. For the working
        tree it is a hash of the *content* of all pending changes — so repeated
        edits to an already-modified file change the token (the original prototype
        hashed ``git status`` porcelain, which is blind to such edits, the very
        case that matters when watching an agent iterate on one file).
        """
        h = hashlib.sha256()
        h.update(self._fingerprint(base).encode())
        h.update(b"\x01")
        h.update(self._fingerprint(target).encode())
        return h.hexdigest()[:16]

    def _fingerprint(self, ref: Ref | None) -> str:
        """Return a value that changes whenever the side identified by *ref* moves."""
        if not is_working_tree(ref):
            assert ref is not None  # narrowed by is_working_tree
            _, sha, _ = self._git("rev-parse", ref)
            return sha.strip()
        # Working tree: combine staged + unstaged content with untracked file
        # stat signatures. This needs no HEAD (works in an empty repo) and reflects
        # every content edit, not just the set of changed files.
        _, unstaged, _ = self._git("diff")
        _, staged, _ = self._git("diff", "--cached")
        _, others, _ = self._git("ls-files", "--others", "--exclude-standard")
        parts = [unstaged, staged]
        for path in others.splitlines():
            try:
                st = (self.root / path).stat()
                parts.append(f"{path}\x1f{st.st_size}\x1f{st.st_mtime_ns}")
            except OSError:
                parts.append(path)
        return "WT\x00" + "\n".join(parts)


def _status_from_code(code: str) -> ChangeStatus:
    """Map a single ``git diff --name-status`` letter to a :class:`ChangeStatus`."""
    return {
        "A": ChangeStatus.ADDED,
        "M": ChangeStatus.MODIFIED,
        "D": ChangeStatus.DELETED,
        "R": ChangeStatus.RENAMED,
    }.get(code, ChangeStatus.MODIFIED)


def _with_counts(change: FileChange, adds: str, dels: str) -> FileChange:
    """Return *change* with addition/deletion counts filled from numstat fields.

    A numstat count of ``"-"`` marks a binary file; it maps to ``0``.
    """
    from dataclasses import replace

    return replace(
        change,
        additions=0 if adds == "-" else int(adds),
        deletions=0 if dels == "-" else int(dels),
    )
