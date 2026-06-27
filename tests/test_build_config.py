"""Unit tests for ``BuildConfig`` and the ``Project.build`` command wiring.

Covers the grouping of the build pipeline (compile / dist / clean) into the
:class:`pyclawd.BuildConfig` dataclass reached via ``Project.build``, including the
exit-2 "not configured" degradation when ``project.build`` is ``None``.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import typer

from pyclawd import BuildConfig, DoctorConfig, Project, TestConfig
from pyclawd.commands import build as build_cmd


def _project(root: Path | None = None, **overrides) -> Project:
    """A minimal, valid Project for the build-command tests."""
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
# BuildConfig — the dataclass itself.
# --------------------------------------------------------------------------- #


def test_build_config_defaults_are_empty():
    b = BuildConfig()
    assert b.compile_cmd == []
    assert b.dist_cmd == []
    assert b.clean_targets == []
    assert b.clean_ext_dir == ""
    assert b.clean_ext_globs == []


def test_build_config_independent_default_lists():
    a, b = BuildConfig(), BuildConfig()
    assert a.compile_cmd is not b.compile_cmd
    assert a.clean_targets is not b.clean_targets


def test_build_config_is_frozen():
    b = BuildConfig(compile_cmd=["setup.py", "build_ext"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.compile_cmd = []  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Project.build — the optional nested group.
# --------------------------------------------------------------------------- #


def test_project_build_defaults_to_none():
    assert _project().build is None


def test_project_accepts_build_config():
    b = BuildConfig(compile_cmd=["setup.py", "build_ext", "--inplace"])
    proj = _project(build=b)
    assert proj.build is b
    assert proj.build.compile_cmd == ["setup.py", "build_ext", "--inplace"]


# --------------------------------------------------------------------------- #
# compile / dist — exit 2 when unconfigured (None build OR empty cmd).
# --------------------------------------------------------------------------- #


def test_compile_exits_2_when_build_is_none(monkeypatch, capsys):
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: _project())  # build None
    with pytest.raises(typer.Exit) as exc:
        build_cmd.compile()
    assert exc.value.exit_code == 2
    assert "not configured" in capsys.readouterr().out


def test_compile_exits_2_when_compile_cmd_empty(monkeypatch, capsys):
    project = _project(build=BuildConfig())  # build present but compile_cmd empty
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        build_cmd.compile()
    assert exc.value.exit_code == 2
    assert "not configured" in capsys.readouterr().out


def test_dist_exits_2_when_build_is_none(monkeypatch, capsys):
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: _project())
    with pytest.raises(typer.Exit) as exc:
        build_cmd.dist()
    assert exc.value.exit_code == 2
    assert "not configured" in capsys.readouterr().out


def test_compile_runs_configured_cmd(monkeypatch):
    project = _project(build=BuildConfig(compile_cmd=["setup.py", "build_ext", "--inplace"]))
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)
    captured: dict[str, list[str]] = {}

    def fake_python(args: list[str]) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(build_cmd.run, "python", fake_python)
    with pytest.raises(typer.Exit) as exc:
        build_cmd.compile()
    assert exc.value.exit_code == 0
    assert captured["args"] == ["setup.py", "build_ext", "--inplace"]


# --------------------------------------------------------------------------- #
# clean — tolerates a None build (nothing to clean), no crash.
# --------------------------------------------------------------------------- #


def test_clean_with_none_build_removes_nothing(tmp_path, monkeypatch, capsys):
    project = _project(root=tmp_path)  # build is None
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)
    build_cmd.clean(ext=False)
    assert "nothing to clean" in capsys.readouterr().out


def test_clean_ext_with_none_build_self_reports(tmp_path, monkeypatch, capsys):
    project = _project(root=tmp_path)  # build is None
    monkeypatch.setattr(build_cmd.run, "load_project_or_exit", lambda: project)
    build_cmd.clean(ext=True)
    out = capsys.readouterr().out
    assert "not configured" in out
    assert "nothing to clean" in out
