"""Unit tests for the ``pyclawd ls`` command (:mod:`pyclawd.commands.ls`).

These cover the two halves of the command in isolation: description extraction
(module docstring, leading ``#`` comment, other-language comments, binary/empty)
and the file-source layer (``git ls-files`` vs the walk fallback). Everything runs
against a temporary directory tree — no installed project required.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pyclawd import discovery
from pyclawd.cli import app
from pyclawd.commands.ls import _collect_files, describe_file

runner = CliRunner()

# --------------------------------------------------------------------------- #
# Description extraction.
# --------------------------------------------------------------------------- #


def test_py_description_from_module_docstring(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text('"""First line is the description.\n\nMore prose below.\n"""\n\nx = 1\n')
    assert describe_file(f) == "First line is the description."


def test_py_description_skips_blank_docstring_lines(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text('"""\n\nDescription after blank lines.\n"""\n')
    assert describe_file(f) == "Description after blank lines."


def test_py_description_falls_back_to_leading_hash_comment(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("# a leading comment description\nimport os\n")
    assert describe_file(f) == "a leading comment description"


def test_py_description_skips_shebang_for_comment_fallback(tmp_path: Path) -> None:
    f = tmp_path / "script.py"
    f.write_text("#!/usr/bin/env python\n# real description here\nimport os\n")
    assert describe_file(f) == "real description here"


def test_py_description_empty_when_neither_docstring_nor_comment(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("import os\n\nx = 1\n")
    assert describe_file(f) == ""


def test_py_syntax_error_is_treated_as_empty(tmp_path: Path) -> None:
    f = tmp_path / "broken.py"
    f.write_text("def oops(:\n    pass\n")
    # No docstring parses, but a leading comment would still be found; here there
    # is none, so the result is empty — and crucially it does NOT raise.
    assert describe_file(f) == ""


def test_py_syntax_error_with_leading_comment(tmp_path: Path) -> None:
    f = tmp_path / "broken.py"
    f.write_text("# still has a description\ndef oops(:\n    pass\n")
    assert describe_file(f) == "still has a description"


def test_markdown_hash_heading_description(tmp_path: Path) -> None:
    f = tmp_path / "README.md"
    f.write_text("# pyclawd\n\nbody text\n")
    assert describe_file(f) == "pyclawd"


def test_html_comment_description(tmp_path: Path) -> None:
    f = tmp_path / "page.html"
    f.write_text("<!-- a page description -->\n<html></html>\n")
    assert describe_file(f) == "a page description"


def test_double_slash_comment_description(tmp_path: Path) -> None:
    f = tmp_path / "script.js"
    f.write_text("// js description\nconst x = 1;\n")
    assert describe_file(f) == "js description"


def test_other_text_without_leading_comment_is_empty(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}\n')
    assert describe_file(f) == ""


def test_binary_file_is_empty_and_does_not_crash(tmp_path: Path) -> None:
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01\x02\x03binary\x00stuff")
    assert describe_file(f) == ""


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert describe_file(tmp_path / "does-not-exist.py") == ""


def test_long_description_is_truncated(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text('"""' + "x" * 200 + '"""\n')
    desc = describe_file(f)
    assert len(desc) <= 100
    assert desc.endswith("…")


# --------------------------------------------------------------------------- #
# File source — git ls-files vs walk fallback.
# --------------------------------------------------------------------------- #


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "a.py").write_text('"""a."""\n')
    (root / "src" / "b.py").write_text('"""b."""\n')
    (root / "ignored.log").write_text("noise\n")


def test_walk_fallback_lists_files_and_skips_noise(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    # Noise that must be skipped by the walk.
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("compiled")
    (tmp_path / "stale.pyc").write_text("compiled")

    files = _collect_files(tmp_path, include_untracked=False)
    assert "a.py" in files
    assert str(Path("src") / "b.py") in files
    assert "ignored.log" in files  # walk has no .gitignore knowledge
    assert not any(f.endswith(".pyc") for f in files)
    assert not any("__pycache__" in f for f in files)


def test_git_source_respects_gitignore(tmp_path: Path) -> None:
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not available")
    _make_tree(tmp_path)
    (tmp_path / ".gitignore").write_text("*.log\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "a.py", "src/b.py", ".gitignore"], cwd=tmp_path, check=True)

    tracked = _collect_files(tmp_path, include_untracked=False)
    assert "a.py" in tracked
    assert str(Path("src") / "b.py") in tracked
    assert "ignored.log" not in tracked  # gitignored
    # ignored.log is untracked AND gitignored, so including untracked must still not surface it.
    with_untracked = _collect_files(tmp_path, include_untracked=True)
    assert "ignored.log" not in with_untracked


# --------------------------------------------------------------------------- #
# The command — PATH argument + src_dir default (end-to-end via the CLI).
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_discovery():
    """``--config`` override + load cache are process-wide; isolate each test."""
    discovery.set_config_override(None)
    discovery._CACHE.clear()
    yield
    discovery.set_config_override(None)
    discovery._CACHE.clear()


def _write_project(root: Path, *, src_dir: str = "src") -> None:
    """Write a minimal ``.pyclawd/config.py`` setting *src_dir* at *root*."""
    pyclawd_dir = root / ".pyclawd"
    pyclawd_dir.mkdir(parents=True, exist_ok=True)
    (pyclawd_dir / "config.py").write_text(
        "from pyclawd import Project, TestConfig, DoctorConfig\n"
        "project = Project(\n"
        f"    name='demo', conda_env=None, root_markers=[], src_dir={src_dir!r},\n"
        "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
        "                    integration_files=[], markers={'default': ''}),\n"
        "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
        ")\n"
    )


def test_ls_path_argument_lists_only_that_subdir(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text('"""a."""\n')
    (tmp_path / "src" / "sub" / "b.py").write_text('"""b."""\n')
    (tmp_path / "top.py").write_text('"""top."""\n')

    result = runner.invoke(app, ["--config", str(tmp_path), "ls", str(tmp_path / "src" / "sub")])
    assert result.exit_code == 0
    # Header names the listed root (relative to the repo root); paths are dir-relative.
    assert "Listing" in result.stdout and str(Path("src") / "sub") in result.stdout
    assert "b.py" in result.stdout
    assert "a.py" not in result.stdout
    assert "top.py" not in result.stdout


def test_ls_defaults_to_src_dir_when_present(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text('"""a."""\n')
    (tmp_path / "src" / "sub" / "b.py").write_text('"""b."""\n')
    (tmp_path / "top.py").write_text('"""top."""\n')

    result = runner.invoke(app, ["--config", str(tmp_path), "ls"])
    assert result.exit_code == 0
    assert "Listing src" in result.stdout
    assert "a.py" in result.stdout
    assert str(Path("sub") / "b.py") in result.stdout
    assert "top.py" not in result.stdout  # outside src/ — not listed


def test_ls_falls_back_to_root_when_src_dir_missing(tmp_path: Path) -> None:
    _write_project(tmp_path)  # src_dir='src', but no src/ directory exists
    (tmp_path / "top.py").write_text('"""top."""\n')

    result = runner.invoke(app, ["--config", str(tmp_path), "ls"])
    assert result.exit_code == 0
    assert "Listing ." in result.stdout  # the repo root
    assert "top.py" in result.stdout


def test_ls_nonexistent_path_exits_2(tmp_path: Path) -> None:
    _write_project(tmp_path)
    missing = tmp_path / "does-not-exist-xyz"

    result = runner.invoke(app, ["--config", str(tmp_path), "ls", str(missing)])
    assert result.exit_code == 2
    assert "not a directory" in result.stderr
    assert "Traceback" not in result.stderr  # clean error, no traceback
