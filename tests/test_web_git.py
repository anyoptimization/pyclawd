"""Unit tests for the web dashboard's pure git layer (:mod:`pyclawd.web.git`).

These exercise the layer against throwaway scratch repositories built per test, so
they need a real ``git`` on PATH but nothing else — no FastAPI, no network. Run
them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini -k web_git
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pyclawd.web.git import (
    WORKING_TREE,
    ChangeStatus,
    GitRepo,
    LineKind,
    _diff_revisions,
    is_working_tree,
    numstat_path,
    parse_hunks,
)

# --------------------------------------------------------------------------- #
# Scratch-repo fixture.
# --------------------------------------------------------------------------- #


def _run(repo: Path, *args: str) -> None:
    """Run a git command in *repo*, raising on failure."""
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    """A fresh git repo with one commit: ``a.txt`` (two lines) and ``keep.txt``."""
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "t@t")
    _run(tmp_path, "config", "user.name", "tester")
    _run(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "a.txt").write_text("line1\nline2\n")
    (tmp_path / "keep.txt").write_text("unchanged\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "init")
    return GitRepo(root=tmp_path)


# --------------------------------------------------------------------------- #
# Pure helpers — no git needed.
# --------------------------------------------------------------------------- #


def test_is_working_tree_normalises_blank_and_sentinel() -> None:
    assert is_working_tree(None)
    assert is_working_tree("")
    assert is_working_tree(WORKING_TREE)
    assert not is_working_tree("HEAD")
    assert not is_working_tree("main")


@pytest.mark.parametrize(
    "rest, expected",
    [
        ("src/app.py", "src/app.py"),
        ("old.py => new.py", "new.py"),
        ("src/{a => b}/x.py", "src/b/x.py"),
        ("{old => new}/x.py", "new/x.py"),
    ],
)
def test_numstat_path_resolves_renames(rest: str, expected: str) -> None:
    assert numstat_path(rest) == expected


def test_diff_revisions_covers_every_side_combination() -> None:
    assert _diff_revisions(WORKING_TREE, WORKING_TREE) is None  # nothing to diff
    assert _diff_revisions("HEAD", WORKING_TREE) == ["HEAD"]  # ref → worktree
    assert _diff_revisions(WORKING_TREE, "HEAD") == ["-R", "HEAD"]  # worktree → ref
    assert _diff_revisions("main", "dev") == ["main", "dev"]  # ref → ref


def test_parse_hunks_tracks_line_numbers() -> None:
    diff = (
        "diff --git a/f b/f\n"
        "--- a/f\n"
        "+++ b/f\n"
        "@@ -1,3 +1,3 @@ ctx header\n"
        " keep\n"
        "-gone\n"
        "+added\n"
        " tail\n"
    )
    hunks = parse_hunks(diff)
    assert hunks is not None and len(hunks) == 1
    kinds = [(ln.kind, ln.old, ln.new) for ln in hunks[0].lines]
    assert kinds == [
        (LineKind.CONTEXT, 1, 1),
        (LineKind.DEL, 2, None),
        (LineKind.ADD, None, 2),
        (LineKind.CONTEXT, 3, 3),
    ]


def test_parse_hunks_returns_none_for_binary() -> None:
    assert parse_hunks("Binary files a/x and b/x differ\n") is None


# --------------------------------------------------------------------------- #
# Change lists against the working tree.
# --------------------------------------------------------------------------- #


def test_changes_reports_modified_with_counts(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("line1\nCHANGED\nadded\n")
    (changed,) = [c for c in repo.changes("HEAD") if c.path == "a.txt"]
    assert changed.status is ChangeStatus.MODIFIED
    assert changed.additions == 2 and changed.deletions == 1
    assert not changed.untracked


def test_changes_includes_untracked_as_added(repo: GitRepo) -> None:
    (repo.root / "new.txt").write_text("one\ntwo\n")
    by_path = {c.path: c for c in repo.changes("HEAD")}
    assert by_path["new.txt"].status is ChangeStatus.ADDED
    assert by_path["new.txt"].untracked
    assert by_path["new.txt"].additions == 2


def test_changes_detects_deletion(repo: GitRepo) -> None:
    (repo.root / "a.txt").unlink()
    by_path = {c.path: c for c in repo.changes("HEAD")}
    assert by_path["a.txt"].status is ChangeStatus.DELETED


def test_changes_detects_rename(repo: GitRepo) -> None:
    _run(repo.root, "mv", "a.txt", "renamed.txt")
    by_path = {c.path: c for c in repo.changes("HEAD")}
    assert by_path["renamed.txt"].status is ChangeStatus.RENAMED
    assert by_path["renamed.txt"].old_path == "a.txt"


def test_changes_empty_when_both_sides_worktree(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("dirty\n")
    assert repo.changes(WORKING_TREE, WORKING_TREE) == []


def test_all_files_marks_unchanged_with_none_status(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("edited\n")
    by_path = {c.path: c for c in repo.all_files("HEAD")}
    assert by_path["a.txt"].status is ChangeStatus.MODIFIED
    assert by_path["keep.txt"].status is None


def test_tracked_paths_includes_untracked(repo: GitRepo) -> None:
    (repo.root / "untracked.txt").write_text("x\n")
    paths = repo.tracked_paths()
    assert paths == sorted(["a.txt", "keep.txt", "untracked.txt"])


# --------------------------------------------------------------------------- #
# Single-file view.
# --------------------------------------------------------------------------- #


def test_file_view_diff_mode_returns_hunks(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("line1\nCHANGED\n")
    view = repo.file_view("HEAD", "a.txt", mode="diff")
    assert not view.binary and view.mode == "diff" and view.hunks
    assert any(ln.kind is LineKind.ADD for h in view.hunks for ln in h.lines)


def test_file_view_full_mode_highlights_added_lines(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("line1\nline2\nappended\n")
    view = repo.file_view("HEAD", "a.txt", mode="full")
    assert view.mode == "full" and len(view.lines) == 3
    assert view.lines[2].kind is LineKind.ADD
    assert view.lines[0].kind is LineKind.CONTEXT


def test_file_view_deleted_file_shows_old_content(repo: GitRepo) -> None:
    (repo.root / "a.txt").unlink()
    view = repo.file_view("HEAD", "a.txt", mode="full")
    assert view.status is ChangeStatus.DELETED
    assert [ln.content for ln in view.lines] == ["line1", "line2"]
    assert all(ln.kind is LineKind.DEL for ln in view.lines)


def test_file_view_untracked_new_file(repo: GitRepo) -> None:
    (repo.root / "fresh.txt").write_text("brand\nnew\n")
    view = repo.file_view("HEAD", "fresh.txt", mode="diff")
    assert view.status is ChangeStatus.ADDED and not view.binary
    assert any(ln.kind is LineKind.ADD for h in view.hunks for ln in h.lines)


def test_file_view_unchanged_file_is_plain_content(repo: GitRepo) -> None:
    view = repo.file_view("HEAD", "keep.txt", mode="diff")
    assert view.unchanged and view.mode == "full"
    assert [ln.content for ln in view.lines] == ["unchanged"]


def test_file_view_binary_file(repo: GitRepo) -> None:
    (repo.root / "blob.bin").write_bytes(bytes(range(256)))
    view = repo.file_view("HEAD", "blob.bin", mode="diff")
    assert view.binary


# --------------------------------------------------------------------------- #
# Metadata + liveness.
# --------------------------------------------------------------------------- #


def test_status_counts_dirty_files(repo: GitRepo) -> None:
    (repo.root / "a.txt").write_text("dirty\n")
    (repo.root / "x.txt").write_text("new\n")
    status = repo.status()
    assert status.branch in {"main", "master"}
    assert status.dirty == 2


def test_refs_lists_current_branch_and_commits(repo: GitRepo) -> None:
    refs = repo.refs()
    assert refs.current in {"main", "master"}
    assert len(refs.commits) == 1
    assert refs.commits[0].subject == "init"


def test_state_token_changes_on_repeated_edits_to_same_file(repo: GitRepo) -> None:
    """The regression the porcelain fingerprint missed: editing an already-dirty file."""
    (repo.root / "a.txt").write_text("line1\nedit-one\n")
    first = repo.state_token("HEAD")
    (repo.root / "a.txt").write_text("line1\nedit-two-totally-different\nextra\n")
    second = repo.state_token("HEAD")
    assert first != second


def test_state_token_stable_when_nothing_changes(repo: GitRepo) -> None:
    assert repo.state_token("HEAD") == repo.state_token("HEAD")


def test_state_token_tracks_ref_side(repo: GitRepo) -> None:
    before = repo.state_token("HEAD", WORKING_TREE)
    (repo.root / "b.txt").write_text("second\n")
    _run(repo.root, "add", "-A")
    _run(repo.root, "commit", "-qm", "second")
    assert repo.state_token("HEAD", WORKING_TREE) != before
