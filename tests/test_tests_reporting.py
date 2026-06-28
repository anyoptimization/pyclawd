"""Unit tests for the junit-parsing / summary reporting glue in :mod:`pyclawd.tests`.

The pure logic that turns a junit XML file back into a human report — ``_pretty_nodeid``
(dotted-classname → path-ish nodeid), ``_summary_lines`` (counts + slowest + failures +
verdict), ``print_timings`` (reads the per-project junit pointer), and the per-project
log-namespacing helpers (``_root_hash`` / ``_log_dir`` / ``_junit_ptr``) — only had
incidental coverage through the subprocess runner. These drive each directly with crafted
junit shapes in ``tmp_path``, with no subprocess and no network.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from pyclawd import Project, TestConfig
from pyclawd.project import DoctorConfig
from pyclawd.tests import (
    _junit_ptr,
    _log_dir,
    _pretty_nodeid,
    _root_hash,
    _summary_lines,
    print_timings,
)


def _project(root: Path, **overrides) -> Project:
    """Minimal project rooted at *root* with its work dir inside it."""
    base = Project(
        name="demo",
        conda_env=None,
        root_markers=["pyproject.toml"],
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=[],
            markers={"default": "not slow", "fast": "not slow", "all": ""},
        ),
        doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),
        work_dir=str(root / "work"),
        root=root,
    )
    return dataclasses.replace(base, **overrides)


# --------------------------------------------------------------------------- #
# _pretty_nodeid — dotted classname → path-ish nodeid.
# --------------------------------------------------------------------------- #


def test_pretty_nodeid_strips_prefix_and_dots_to_path() -> None:
    """A classname under the prefix becomes ``<tests_dir><path>.py::name``."""
    out = _pretty_nodeid("tests.algorithms.test_nsga2", "test_run", "tests.", "tests/")
    assert out == "tests/algorithms/test_nsga2.py::test_run"


def test_pretty_nodeid_top_level_module() -> None:
    """A single-segment module under the prefix maps to one path component."""
    out = _pretty_nodeid("tests.test_core", "test_x", "tests.", "tests/")
    assert out == "tests/test_core.py::test_x"


def test_pretty_nodeid_classname_without_prefix_falls_back() -> None:
    """A classname NOT under the prefix is left as ``classname::name`` (no path)."""
    out = _pretty_nodeid("pkg.module.TestThing", "test_y", "tests.", "tests/")
    assert out == "pkg.module.TestThing::test_y"


def test_pretty_nodeid_empty_classname_is_just_name() -> None:
    """An empty classname (no class) yields the bare test name."""
    assert _pretty_nodeid("", "test_z", "tests.", "tests/") == "test_z"


def test_pretty_nodeid_respects_custom_prefix_and_dir() -> None:
    """The prefix/dir come from config, not hardcoded — a custom pair is honored."""
    out = _pretty_nodeid("suite.unit.test_a", "test_b", "suite.", "src/tests/")
    assert out == "src/tests/unit/test_a.py::test_b"


# --------------------------------------------------------------------------- #
# Synthetic junit fixtures.
# --------------------------------------------------------------------------- #


def _write_junit(path: Path, body: str) -> Path:
    """Write a ``<testsuite>``-wrapped junit XML *body* to *path*."""
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<testsuite>{body}</testsuite>\n')
    return path


_MIXED = (
    '<testcase classname="tests.test_a" name="test_pass" time="0.10"/>'
    '<testcase classname="tests.test_a" name="test_slow" time="2.50"/>'
    '<testcase classname="tests.test_b" name="test_fail" time="0.20">'
    '<failure message="assert 1 == 2">long traceback\nsecond line</failure></testcase>'
    '<testcase classname="tests.test_b" name="test_err" time="0.05">'
    '<error message="boom">err trace</error></testcase>'
    '<testcase classname="tests.test_c" name="test_skip" time="0.00">'
    "<skipped/></testcase>"
)


# --------------------------------------------------------------------------- #
# _summary_lines — counts, slowest table, failures, verdict.
# --------------------------------------------------------------------------- #


def test_summary_lines_counts_each_outcome(tmp_path: Path) -> None:
    """passed/failed/error/skipped are tallied from the testcase children."""
    junit = _write_junit(tmp_path / "j.xml", _MIXED)
    lines = _summary_lines(junit, rc=1, project=_project(tmp_path))
    verdict = next(line for line in lines if line.startswith("tests ·"))
    assert "2 passed" in verdict  # test_pass + test_slow
    assert "1 failed" in verdict
    assert "1 error" in verdict
    assert "1 skipped" in verdict
    # total cpu time = 0.10 + 2.50 + 0.20 + 0.05 + 0.00 = 2.85 -> "2.9s cpu"
    assert "2.9s cpu" in verdict


def test_summary_lines_slowest_first_and_pretty_nodeids(tmp_path: Path) -> None:
    """The slowest table is sorted descending and uses reconstructed nodeids."""
    junit = _write_junit(tmp_path / "j.xml", _MIXED)
    lines = _summary_lines(junit, rc=1, project=_project(tmp_path))
    body = "\n".join(lines)
    assert "⏱  slowest tests:" in body
    slow_rows = [line for line in lines if line.strip().endswith(".py::test_slow")]
    assert slow_rows and "2.50s" in slow_rows[0]
    # The slowest (2.50s) must appear before the next-slowest (0.20s test_fail).
    idx_slow = next(i for i, line in enumerate(lines) if "test_slow" in line)
    idx_fail = next(i for i, line in enumerate(lines) if "test_fail" in line)
    assert idx_slow < idx_fail
    assert "tests/test_a.py::test_slow" in body


def test_summary_lines_lists_failures_with_first_message_line(tmp_path: Path) -> None:
    """Failures + errors are listed; only the first message line is shown."""
    junit = _write_junit(tmp_path / "j.xml", _MIXED)
    lines = _summary_lines(junit, rc=1, project=_project(tmp_path))
    body = "\n".join(lines)
    assert "❌ 2 failing test(s):" in body
    assert "tests/test_b.py::test_fail" in body
    assert "assert 1 == 2" in body
    assert "second line" not in body  # only the first line of the message
    assert "tests/test_b.py::test_err" in body


def test_summary_lines_all_passed_verdict(tmp_path: Path) -> None:
    """An all-pass junit reports the green verdict and no failure section."""
    body = (
        '<testcase classname="tests.test_a" name="test_one" time="0.01"/>'
        '<testcase classname="tests.test_a" name="test_two" time="0.02"/>'
    )
    junit = _write_junit(tmp_path / "j.xml", body)
    lines = _summary_lines(junit, rc=0, project=_project(tmp_path))
    text = "\n".join(lines)
    assert "✅ all passed" in text
    assert "2 passed" in text
    assert "failing test(s)" not in text


def test_summary_lines_missing_junit_reports_collection_error(tmp_path: Path) -> None:
    """No junit file at all → a single 'no junit produced' line carrying the rc."""
    lines = _summary_lines(tmp_path / "missing.xml", rc=3, project=_project(tmp_path))
    assert len(lines) == 1
    assert "no junit produced" in lines[0]
    assert "exit 3" in lines[0]


# --------------------------------------------------------------------------- #
# print_timings — reads the per-project junit pointer.
# --------------------------------------------------------------------------- #


def test_print_timings_no_pointer(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """With no pointer file, print_timings nudges the user to run first (rc 0)."""
    rc = print_timings(_project(tmp_path))
    assert rc == 0
    assert "No timings yet" in capsys.readouterr().out


def test_print_timings_pointer_to_missing_junit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pointer to a since-deleted junit reports the stale-junit message."""
    project = _project(tmp_path)
    ptr = _junit_ptr(project)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(str(tmp_path / "gone.xml"))
    rc = print_timings(project)
    assert rc == 0
    assert "last junit is gone" in capsys.readouterr().out


def test_print_timings_top_n(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Default mode lists slowest-first with the reconstructed nodeids."""
    project = _project(tmp_path)
    junit = _write_junit(tmp_path / "run.junit.xml", _MIXED)
    ptr = _junit_ptr(project)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(str(junit))
    rc = print_timings(project, top=2)
    out = capsys.readouterr().out
    assert rc == 0
    assert "slowest first" in out
    assert "tests/test_a.py::test_slow" in out
    assert "2.50s" in out
    # top=2 limits the listed rows: only the two slowest nodeids appear.
    listed = [line for line in out.splitlines() if line.strip().endswith(".py::test_slow")]
    assert listed and "test_pass" not in out


def test_print_timings_slow_threshold_filters(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With --slow-threshold only tests slower than the bound are shown."""
    project = _project(tmp_path)
    junit = _write_junit(tmp_path / "run.junit.xml", _MIXED)
    ptr = _junit_ptr(project)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(str(junit))
    rc = print_timings(project, slow_threshold=1.0)
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 tests over 1.0s" in out
    assert "test_slow" in out
    assert "test_pass" not in out  # 0.10s is under the threshold


def test_print_timings_slow_threshold_none_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A threshold above every test prints the explicit 'none found' message."""
    project = _project(tmp_path)
    junit = _write_junit(tmp_path / "run.junit.xml", _MIXED)
    ptr = _junit_ptr(project)
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(str(junit))
    print_timings(project, slow_threshold=99.0)
    assert "No tests over 99.0s found." in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Per-project log namespacing — two roots never collide.
# --------------------------------------------------------------------------- #


def test_root_hash_is_stable_and_short() -> None:
    """The root hash is deterministic and a 10-char hex slug."""
    h = _root_hash(Path("/some/repo"))
    assert h == _root_hash(Path("/some/repo"))
    assert len(h) == 10
    assert all(c in "0123456789abcdef" for c in h)


def test_distinct_roots_get_distinct_log_dirs(tmp_path: Path) -> None:
    """Two different project roots namespace to different test-log dirs / pointers."""
    a = _project(tmp_path / "a")
    b = _project(tmp_path / "b")
    assert _root_hash(tmp_path / "a") != _root_hash(tmp_path / "b")
    assert _log_dir(a) != _log_dir(b)
    assert _junit_ptr(a) != _junit_ptr(b)
    # The namespaced dir ends with the root's hash slug.
    assert _log_dir(a).name == _root_hash(tmp_path / "a")


# --------------------------------------------------------------------------- #
# run_suite — `-n` (xdist) injection degrades gracefully when xdist is absent.
# --------------------------------------------------------------------------- #


def _capture_run_suite_cmd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, xdist: bool, jobs: str | None
) -> list[str]:
    """Run :func:`run_suite` with all subprocess work stubbed, return the pytest argv.

    ``tee`` is replaced with a capturing stub (no real pytest run) and ``has_xdist``
    is pinned to *xdist* so the test never depends on the host's installed plugins.
    """
    from pyclawd import tests as tests_mod

    project = _project(tmp_path)
    captured: list[str] = []

    def fake_tee(cmd, log, root):  # type: ignore[no-untyped-def]
        captured.extend(str(c) for c in cmd)
        return 0

    monkeypatch.setattr(tests_mod, "repo_root_or_exit", lambda: tmp_path)
    monkeypatch.setattr(tests_mod, "python_prefix", lambda _p: ["python"])
    monkeypatch.setattr(tests_mod, "has_xdist", lambda _p: xdist)
    monkeypatch.setattr(tests_mod, "tee", fake_tee)
    rc = tests_mod.run_suite([], "not slow", "run", project, jobs=jobs)
    assert rc == 0
    return captured


def test_run_suite_injects_n_when_xdist_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With xdist importable, ``-n <jobs>`` is added to the pytest command."""
    cmd = _capture_run_suite_cmd(tmp_path, monkeypatch, xdist=True, jobs="auto")
    assert "-n" in cmd
    assert cmd[cmd.index("-n") + 1] == "auto"


def test_run_suite_degrades_to_serial_when_xdist_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing xdist must NOT inject ``-n`` (which would crash pytest) — warn and run serial."""
    cmd = _capture_run_suite_cmd(tmp_path, monkeypatch, xdist=False, jobs="auto")
    assert "-n" not in cmd
    assert "pytest-xdist not installed" in capsys.readouterr().out


def test_run_suite_serial_jobs_never_probes_or_injects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``jobs=""`` (serial by config) injects nothing and emits no xdist warning."""
    cmd = _capture_run_suite_cmd(tmp_path, monkeypatch, xdist=False, jobs="")
    assert "-n" not in cmd
    assert "pytest-xdist" not in capsys.readouterr().out
