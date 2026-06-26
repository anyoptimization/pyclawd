"""Unit tests for the ``pyclawd golden`` command layer (:mod:`pyclawd.commands.golden`).

These exercise the **pure** logic only — the ``orphan_keys`` snapshot/node-id
matcher and the self-report-exit-2 path when a project does not configure golden.
No real pytest is shelled out; orphan detection is fed a synthetic node-id set.

Run them (from the repo root) with::

    pyclawd python -m pytest tests/test_golden_cmd.py -c tests/pytest.ini
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import typer

from pyclawd import Project, TestConfig
from pyclawd.commands import golden as golden_cmd
from pyclawd.commands.golden import orphan_keys
from pyclawd.project import DoctorConfig, GoldenConfig


def _project(root: Path | None = None, **overrides) -> Project:
    """Build a minimal loaded :class:`Project` (golden is ``None`` by default)."""
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
# orphan_keys — the pure snapshot/node-id matcher.
# --------------------------------------------------------------------------- #


def test_orphan_keys_flags_missing_test_keeps_live() -> None:
    collected = {
        "tests/test_minimize.py::test_minimize[sphere]",
        "tests/test_minimize.py::test_minimize[rosenbrock]",
    }
    keys = ["test_minimize[sphere]", "test_minimize[ackley]"]
    # [sphere] is live; [ackley] no longer collected → orphan.
    assert orphan_keys(keys, collected) == ["test_minimize[ackley]"]


def test_orphan_keys_strips_label_suffix() -> None:
    collected = {"tests/test_opt.py::test_run[a]"}
    # A "::label" suffix is part of the key, not the node id — strip it before matching.
    keys = ["test_run[a]::F", "test_run[a]::X", "test_gone::F"]
    assert orphan_keys(keys, collected) == ["test_gone::F"]


def test_orphan_keys_all_live_returns_empty() -> None:
    collected = {"tests/t.py::test_a", "tests/t.py::test_b"}
    assert orphan_keys(["test_a", "test_b::label"], collected) == []


def test_orphan_keys_empty_collection_makes_everything_orphan() -> None:
    keys = ["test_a", "test_b::F"]
    assert orphan_keys(keys, set()) == ["test_a", "test_b::F"]


def test_orphan_keys_matches_last_nodeid_segment() -> None:
    # Class-based test: only the LAST ``::`` segment is the live key prefix.
    collected = {"tests/t.py::TestSuite::test_method[1]"}
    assert orphan_keys(["test_method[1]"], collected) == []
    assert orphan_keys(["TestSuite"], collected) == ["TestSuite"]


# --------------------------------------------------------------------------- #
# Exit-2 when golden is unconfigured (every subcommand self-reports).
# --------------------------------------------------------------------------- #


def test_golden_or_exit_returns_config_when_present() -> None:
    cfg = GoldenConfig()
    project = _project(golden=cfg)
    assert golden_cmd._golden_or_exit(project) is cfg


def test_golden_or_exit_exits_2_when_unconfigured(capsys) -> None:
    project = _project()  # golden is None
    with pytest.raises(typer.Exit) as exc:
        golden_cmd._golden_or_exit(project)
    assert exc.value.exit_code == 2
    assert "golden not configured" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["update", "status", "prune"])
def test_subcommands_exit_2_when_unconfigured(monkeypatch, capsys, command) -> None:
    project = _project(root=Path("/tmp/repo"))  # golden is None
    monkeypatch.setattr(golden_cmd.run, "load_project_or_exit", lambda: project)
    func = getattr(golden_cmd, command)
    with pytest.raises(typer.Exit) as exc:
        func()
    assert exc.value.exit_code == 2
    assert "golden not configured" in capsys.readouterr().err


def test_compare_exits_2_when_unconfigured(monkeypatch, capsys) -> None:
    project = _project(root=Path("/tmp/repo"))  # golden is None
    monkeypatch.setattr(golden_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        golden_cmd._compare()
    assert exc.value.exit_code == 2
    assert "golden not configured" in capsys.readouterr().err


def test_vendor_copies_engine_and_plugin(tmp_path: Path) -> None:
    """`pyclawd golden vendor` writes a dependency-free, import-rewritten copy."""
    dest = tmp_path / "_golden"
    with pytest.raises(typer.Exit) as exc:
        golden_cmd.vendor(target=str(dest))
    assert exc.value.exit_code == 0
    for name in ("golden.py", "plugin.py", "__init__.py"):
        assert (dest / name).is_file(), f"vendor should write {name}"
    plugin = (dest / "plugin.py").read_text()
    # the engine import is rewritten to the vendored copy
    assert "from .golden import" in plugin
    assert "from pyclawd.golden import" not in plugin
    # provenance header stamped
    assert "Vendored from pyclawd" in (dest / "golden.py").read_text()
