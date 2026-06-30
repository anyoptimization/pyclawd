"""Unit tests for server-side syntax highlighting (:mod:`pyclawd.web.highlight`).

These cover the pure highlighter (line alignment, lexer selection, graceful
fallback) and that :meth:`GitRepo.file_view` threads HTML onto its diff lines.
They need a real ``git`` on PATH but nothing else — no FastAPI, no network.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pyclawd.web.git import GitRepo, LineKind
from pyclawd.web.highlight import highlight_lines


def _run(repo: Path, *args: str) -> None:
    """Run a git command in *repo*, raising on failure."""
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# The pure highlighter.
# --------------------------------------------------------------------------- #


def test_returns_one_fragment_per_source_line() -> None:
    src = ["def f(x):", "    return x + 1"]
    out = highlight_lines("m.py", src)
    assert out is not None
    assert len(out) == len(src)


def test_keywords_get_token_spans() -> None:
    out = highlight_lines("m.py", ["def f():", "    return 1"])
    assert out is not None
    assert 'class="pl-k">def' in out[0]
    assert 'class="pl-k">return' in out[1]


def test_multiline_docstring_coloured_on_every_line() -> None:
    src = ["def f():", '    """Doc.', "", "    more.", '    """', "    return 1"]
    out = highlight_lines("m.py", src)
    assert out is not None
    # Each non-blank docstring line carries the string-doc class, not just the first.
    assert 'class="pl-sd"' in out[1]
    assert 'class="pl-sd"' in out[3]
    assert 'class="pl-sd"' in out[4]


def test_html_is_escaped() -> None:
    out = highlight_lines("m.py", ['x = "<b>"'])
    assert out is not None
    assert "<b>" not in out[0]
    assert "&lt;b&gt;" in out[0]


def test_unknown_extension_returns_none() -> None:
    assert highlight_lines("data.unknownext", ["nothing here"]) is None


def test_empty_source_returns_none() -> None:
    assert highlight_lines("m.py", []) is None


# --------------------------------------------------------------------------- #
# Integration: file_view attaches html.
# --------------------------------------------------------------------------- #


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    """A fresh git repo with one committed Python module."""
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "t@t")
    _run(tmp_path, "config", "user.name", "tester")
    _run(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "m.py").write_text("def f(x):\n    return x\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "init")
    return GitRepo(root=tmp_path)


def test_file_view_attaches_html_to_python(repo: GitRepo) -> None:
    (repo.root / "m.py").write_text("def f(x):\n    return x + 1\n")
    view = repo.file_view("HEAD", "m.py")
    lines = [ln for h in view.hunks for ln in h.lines]
    changed = [ln for ln in lines if ln.kind in (LineKind.ADD, LineKind.DEL)]
    assert changed and all(ln.html and 'class="pl-' in ln.html for ln in changed)


def test_file_view_leaves_non_code_plain(repo: GitRepo) -> None:
    (repo.root / "notes.txt").write_text("hello world\n")
    _run(repo.root, "add", "-A")
    _run(repo.root, "commit", "-qm", "txt")
    (repo.root / "notes.txt").write_text("hello there\n")
    view = repo.file_view("HEAD", "notes.txt")
    lines = [ln for h in view.hunks for ln in h.lines]
    assert lines and all(ln.html is None for ln in lines)
