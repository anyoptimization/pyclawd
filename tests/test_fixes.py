"""Regression tests for the reviewer-found defect fixes.

Covers: the ``clean`` path-escape guard (L5), the ``test timings --top`` parse
guard (L6), the always-registered ``docs`` group self-report (H1), the clean
``ConfigError`` for a broken config + the doctor-hook wrap (M3), and the
per-project namespacing of test-log junit pointers (M2).

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import typer

from pyclawd import ConfigError, DoctorConfig, Project, TestConfig, load_project
from pyclawd.commands import build as build_cmd
from pyclawd.commands import docs as docs_cmd
from pyclawd.project import FAIL, Check


def _project(root: Path | None = None, **overrides) -> Project:
    """A minimal, valid Project for the command-layer tests."""
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
        root=root,
    )
    return dataclasses.replace(base, **overrides)


# --------------------------------------------------------------------------- #
# L5 — `pyclawd clean` must never delete outside the repo root.
# --------------------------------------------------------------------------- #


def test_clean_skips_targets_outside_root(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("important")

    project = _project(root=repo, clean_targets=["../victim"])
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)

    build_cmd.clean(ext=False)

    assert victim.exists(), "clean escaped the repo root and deleted a sibling dir"
    assert (victim / "keep.txt").exists()
    err = capsys.readouterr().err
    assert "outside the repo root" in err


def test_clean_removes_targets_inside_root(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "build").mkdir(parents=True)
    (repo / "build" / "x.o").write_text("artifact")

    project = _project(root=repo, clean_targets=["build"])
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)

    build_cmd.clean(ext=False)
    assert not (repo / "build").exists()


def test_under_root_guard():
    root = Path("/tmp/repo")
    assert build_cmd._under_root(Path("/tmp/repo/build"), root)
    assert not build_cmd._under_root(Path("/tmp/victim"), root)
    assert not build_cmd._under_root(Path("/tmp/repo/../victim"), root)


# --------------------------------------------------------------------------- #
# H1 — docs subcommands self-report when the project does not configure docs.
# --------------------------------------------------------------------------- #


def test_docs_self_reports_when_unconfigured(monkeypatch, capsys):
    project = _project(root=Path("/tmp/repo"))  # docs is None
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)

    with pytest.raises(typer.Exit) as exc:
        docs_cmd._docs_project_or_exit()
    assert exc.value.exit_code == 2
    assert "docs not configured" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# M3 — broken config surfaces a clean ConfigError; a raising doctor hook is a row.
# --------------------------------------------------------------------------- #


def test_broken_config_raises_config_error(tmp_path):
    pyclawd_dir = tmp_path / ".pyclawd"
    pyclawd_dir.mkdir()
    (pyclawd_dir / "config.py").write_text("def oops(:\n")  # syntax error
    with pytest.raises(ConfigError) as exc:
        load_project(tmp_path)
    assert "failed to load" in str(exc.value)


def test_config_import_error_raises_config_error(tmp_path):
    pyclawd_dir = tmp_path / ".pyclawd"
    pyclawd_dir.mkdir()
    (pyclawd_dir / "config.py").write_text("import this_module_does_not_exist_xyz\n")
    with pytest.raises(ConfigError):
        load_project(tmp_path)


def test_doctor_hook_failure_is_a_check_row_not_a_crash():
    from pyclawd import doctor

    def boom() -> list[Check]:
        raise RuntimeError("kaboom")

    project = _project(root=Path("/tmp/repo"), extra_doctor_checks=boom)
    checks = doctor.collect(project)
    rows = [c for c in checks if c.status == FAIL and "kaboom" in c.detail]
    assert rows, "raising doctor hook should produce a FAIL row, not crash"
    assert rows[0].name == "boom"


# --------------------------------------------------------------------------- #
# M2 — test-log junit pointers are namespaced per project root (no cross-talk).
# --------------------------------------------------------------------------- #


def test_junit_pointers_are_per_project():
    from pyclawd import tests as tests_mod

    a = _project(root=Path("/tmp/projA"))
    b = _project(root=Path("/tmp/projB"))
    assert tests_mod._junit_ptr(a) != tests_mod._junit_ptr(b)
    # Same root → same pointer (stable).
    assert tests_mod._junit_ptr(a) == tests_mod._junit_ptr(_project(root=Path("/tmp/projA")))


# --------------------------------------------------------------------------- #
# L6 — `test timings --top <non-int>` is a clean error, not an uncaught crash.
# --------------------------------------------------------------------------- #


def test_timings_top_non_int_is_clean_exit(monkeypatch, capsys):
    from pyclawd import tests as tests_mod

    project = _project(root=Path("/tmp/repo"))
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: project)

    rc = tests_mod.dispatch("timings", ["--top", "notanint"])
    assert rc == 2
    assert "--top expects an integer" in capsys.readouterr().err


def test_timings_top_valid_int_parses(monkeypatch):
    from pyclawd import tests as tests_mod

    project = _project(root=Path("/tmp/repo"))
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: project)
    captured = {}

    def fake_print_timings(proj, top):
        captured["top"] = top
        return 0

    monkeypatch.setattr(tests_mod, "print_timings", fake_print_timings)
    assert tests_mod.dispatch("timings", ["--top", "7"]) == 0
    assert captured["top"] == 7
