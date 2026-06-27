"""End-to-end tests of the actual Typer app (:mod:`pyclawd.cli`).

These invoke the assembled CLI through Typer's :class:`CliRunner`, so they cover
the wiring the unit tests skip: the global ``--config`` override, the meta
commands (``version`` / ``root``), and that unconfigured command groups
self-report with the documented exit codes instead of crashing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pyclawd import discovery
from pyclawd.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_discovery():
    """The ``--config`` override and load cache are process-wide; isolate each test."""
    discovery.set_config_override(None)
    discovery._CACHE.clear()
    yield
    discovery.set_config_override(None)
    discovery._CACHE.clear()


def _write_config(dir_path: Path, *, name: str = "demo", quality: bool = False, body=None) -> Path:
    pyclawd_dir = dir_path / ".pyclawd"
    pyclawd_dir.mkdir(parents=True, exist_ok=True)
    if body is None:
        quality_block = (
            "    quality=QualityConfig(lint_cmd=['ruff', 'check']),\n" if quality else ""
        )
        imports = "Project, TestConfig, DoctorConfig" + (", QualityConfig" if quality else "")
        body = (
            f"from pyclawd import {imports}\n"
            "project = Project(\n"
            f"    name={name!r}, conda_env=None, root_markers=[],\n"
            f"{quality_block}"
            "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
            "                    integration_files=[], markers={'default': ''}),\n"
            "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
            ")\n"
        )
    (pyclawd_dir / "config.py").write_text(body)
    return dir_path


# ---- meta commands ----------------------------------------------------------


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "pyclawd" in result.stdout


def test_root_prints_resolved_root(tmp_path):
    _write_config(tmp_path, name="rooted")
    result = runner.invoke(app, ["--config", str(tmp_path), "root"])
    assert result.exit_code == 0
    assert str(tmp_path.resolve()) in result.stdout


def test_root_exits_2_without_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # an isolated dir with no .pyclawd above it
    result = runner.invoke(app, ["root"])
    assert result.exit_code == 2


def test_broken_config_is_clean_exit_not_traceback(tmp_path):
    _write_config(tmp_path, body="def oops(:\n")  # syntax error
    result = runner.invoke(app, ["--config", str(tmp_path), "root"])
    assert result.exit_code == 2
    assert "✗" in result.stderr
    assert "Traceback" not in result.stderr  # never a raw traceback at the boundary


# ---- unconfigured groups self-report with documented exit codes -------------


def test_lint_exits_2_when_quality_unconfigured(tmp_path):
    _write_config(tmp_path, quality=False)
    result = runner.invoke(app, ["--config", str(tmp_path), "lint"])
    assert result.exit_code == 2
    assert "quality not configured" in result.stderr


def test_docs_status_exits_2_when_docs_unconfigured(tmp_path):
    _write_config(tmp_path)  # docs is None
    result = runner.invoke(app, ["--config", str(tmp_path), "docs", "status"])
    assert result.exit_code == 2
    assert "docs not configured" in result.stderr


def test_compile_exits_2_when_no_compile_step(tmp_path):
    _write_config(tmp_path)  # no build config → project.build is None
    result = runner.invoke(app, ["--config", str(tmp_path), "compile"])
    # 0/2 contract: a command that exists but isn't configured exits 2.
    assert result.exit_code == 2
    assert "not configured" in result.stdout


def test_skills_list_runs():
    result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0
    assert "pyclawd-doctor" in result.stdout


def _config_with_markers(dir_path: Path, markers: dict) -> Path:
    return _write_config(
        dir_path,
        body=(
            "from pyclawd import Project, TestConfig, DoctorConfig\n"
            "project = Project(\n"
            "    name='demo', conda_env=None, root_markers=[],\n"
            "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
            f"                    integration_files=[], markers={markers!r}),\n"
            "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
            ")\n"
        ),
    )


def test_test_category_is_config_driven(tmp_path, monkeypatch):
    """`pyclawd test <key>` is a category iff the project defines that marker tier."""
    from pyclawd import run as run_mod

    captured = {}

    def fake_pytest(args, default_markers=None, tests_dir=None):
        captured["args"] = list(args)
        captured["markers"] = default_markers
        return 0

    monkeypatch.setattr(run_mod, "pytest", fake_pytest)

    # Project DEFINES "examples" → it is consumed as the category, its marker applied.
    proj_a = tmp_path / "a"
    _config_with_markers(proj_a, {"default": "not slow", "examples": "examples"})
    assert runner.invoke(app, ["--config", str(proj_a), "test", "examples"]).exit_code == 0
    assert captured["args"] == []  # "examples" consumed, not passed to pytest
    assert captured["markers"] == "examples"

    # Project does NOT define "examples" → a bare unknown word is treated as a
    # mistyped category and fails clean (exit 2), instead of being silently handed
    # to pytest (which would emit a confusing "file or directory not found").
    proj_b = tmp_path / "b"
    _config_with_markers(proj_b, {"default": "not slow"})
    result = runner.invoke(app, ["--config", str(proj_b), "test", "examples"])
    assert result.exit_code == 2

    # Genuine pytest passthrough (a flag / path / nodeid) still works and uses the
    # default tier marker (no hardcoded examples/docs assumption).
    captured.clear()
    assert runner.invoke(app, ["--config", str(proj_b), "test", "-k", "examples"]).exit_code == 0
    assert captured["args"] == ["-k", "examples"]
    assert captured["markers"] == "not slow"
