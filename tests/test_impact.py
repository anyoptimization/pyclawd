"""Unit tests for the impact reverse-map (:mod:`pyclawd.impact`, ``pyclawd test changed``).

The reverse-map query is exercised against a **real** coverage database built with
per-test contexts, so the test doubles as an end-to-end check of the feature. It skips
cleanly when ``coverage`` is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyclawd import repo
from pyclawd.impact import impacted_tests, strip_context_phase
from pyclawd.tests import _resolve_nodeids


def test_resolve_nodeids_restores_tests_prefix(tmp_path: Path) -> None:
    # A map built with rootdir=tests/ stores ids WITHOUT the tests/ prefix; re-running
    # from the repo root needs it restored or pytest collects nothing.
    (tmp_path / "tests" / "sub").mkdir(parents=True)
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass\n")
    (tmp_path / "tests" / "sub" / "test_y.py").write_text("def test_b(): pass\n")

    runnable, stale = _resolve_nodeids(
        ["test_x.py::test_a", "sub/test_y.py::test_b", "gone.py::test_c"],
        tmp_path,
        "tests/",
    )
    assert runnable == ["tests/test_x.py::test_a", "tests/sub/test_y.py::test_b"]
    assert stale == ["gone.py::test_c"]


def test_resolve_nodeids_leaves_already_resolvable(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass\n")
    # An id that already resolves from the root (map built with rootdir=root) is kept.
    runnable, stale = _resolve_nodeids(["tests/test_x.py::test_a"], tmp_path, "tests/")
    assert runnable == ["tests/test_x.py::test_a"]
    assert stale == []


def test_strip_context_phase() -> None:
    assert strip_context_phase("tests/test_x.py::test_a|run") == "tests/test_x.py::test_a"
    assert strip_context_phase("tests/test_x.py::test_a") == "tests/test_x.py::test_a"


def test_parse_unified0_hunks_maps_new_side_lines() -> None:
    diff = (
        "diff --git a/pkg/m.py b/pkg/m.py\n"
        "--- a/pkg/m.py\n"
        "+++ b/pkg/m.py\n"
        "@@ -10,0 +11,2 @@\n"
        "+new line\n"
        "+another\n"
        "@@ -20 +22 @@\n"
        "+changed\n"
    )
    got = repo._parse_unified0_hunks(diff)
    assert got == {"pkg/m.py": {11, 12, 22}}


def test_parse_unified0_hunks_ignores_deletions() -> None:
    diff = "--- a/gone.py\n+++ /dev/null\n@@ -1,5 +0,0 @@\n-x\n"
    assert repo._parse_unified0_hunks(diff) == {}


def _init_repo(root: Path) -> None:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")


def test_changed_line_map_tracked_and_untracked(tmp_path: Path) -> None:
    import subprocess

    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("one\ntwo\nthree\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
        env={**__import__("os").environ, "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    (tmp_path / "a.py").write_text("one\nTWO\nthree\n")  # modify line 2
    (tmp_path / "b.py").write_text("brand\nnew\n")  # untracked → all lines are new

    got = repo.changed_line_map(tmp_path, "HEAD")
    assert got["a.py"] == {2}
    assert got["b.py"] == {1, 2}  # untracked file is entirely new


@pytest.fixture
def coverage_db(tmp_path: Path) -> Path:
    """Build a real ``.coverage`` DB with per-test contexts over a scratch package."""
    coverage = pytest.importorskip("coverage")

    src = tmp_path / "lib.py"
    src.write_text(
        "def add(a, b):\n"  # line 1
        "    return a + b\n"  # line 2
        "def mul(a, b):\n"  # line 3
        "    return a * b\n"  # line 4
    )

    cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"), config_file=False)
    import importlib.util

    spec = importlib.util.spec_from_file_location("lib", src)
    assert spec and spec.loader
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)

    # Record two "tests", each touching a different function, as distinct contexts.
    # switch_context must be called while collection is running.
    cov.start()
    cov.switch_context("tests/test_lib.py::test_add|run")
    lib.add(1, 2)
    cov.switch_context("tests/test_lib.py::test_mul|run")
    lib.mul(2, 3)
    cov.stop()

    cov.save()
    return tmp_path / ".coverage"


def test_impacted_tests_maps_changed_lines(coverage_db: Path, tmp_path: Path) -> None:
    # Changing line 2 (inside `add`) should implicate only the add test.
    result = impacted_tests(coverage_db, tmp_path, {"lib.py": {2}})
    assert result.nodeids == {"tests/test_lib.py::test_add"}
    assert result.covered == {"lib.py"}
    assert result.uncovered == set()


def test_impacted_tests_reports_uncovered_new_file(coverage_db: Path, tmp_path: Path) -> None:
    # An unmeasured file (or unmeasured line) is uncovered — surfaced, not silently dropped.
    result = impacted_tests(coverage_db, tmp_path, {"brand_new.py": {1}})
    assert result.nodeids == set()
    assert result.uncovered == {"brand_new.py"}


def test_impacted_tests_line_precision(coverage_db: Path, tmp_path: Path) -> None:
    # Line 4 is inside `mul` → only the mul test is impacted.
    result = impacted_tests(coverage_db, tmp_path, {"lib.py": {4}})
    assert result.nodeids == {"tests/test_lib.py::test_mul"}
