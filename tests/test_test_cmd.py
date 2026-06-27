"""Tests for the `pyclawd test` command layer: category dispatch + timings parsing.

Covers two behaviours:
  * A2 — a mistyped category (a bare leading word that is neither a known
    category/sub-verb nor a pytest target) fails clean with exit 2, while genuine
    pytest passthrough (paths, nodeids, ``-k``/``-x``/``-m`` flags) still works.
  * B4 — the ``timings`` verb's ``--top`` / ``--slow-threshold`` flags are parsed
    via argparse, accepting both the space and ``=`` forms with the historic
    defaults and exit-2-on-bad-value behaviour.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pyclawd import discovery
from pyclawd.cli import app
from pyclawd.commands import test as test_cmd

runner = CliRunner()


def _all_output(result) -> str:
    """Combined stdout+stderr from a CliRunner result, across Click versions.

    Click may keep stderr separate (``mix_stderr=False`` / Click 8.2+), so the
    ``err=True`` message lands in ``result.stderr`` rather than ``stdout``.
    """
    out = result.stdout or ""
    with contextlib.suppress(ValueError, AttributeError):
        out += result.stderr or ""
    return out


@pytest.fixture(autouse=True)
def _reset_discovery():
    """The ``--config`` override and load cache are process-wide; isolate each test."""
    discovery.set_config_override(None)
    discovery._CACHE.clear()
    yield
    discovery.set_config_override(None)
    discovery._CACHE.clear()


def _write_config(dir_path: Path, markers: dict) -> Path:
    pyclawd_dir = dir_path / ".pyclawd"
    pyclawd_dir.mkdir(parents=True, exist_ok=True)
    (pyclawd_dir / "config.py").write_text(
        "from pyclawd import Project, TestConfig, DoctorConfig\n"
        "project = Project(\n"
        "    name='demo', conda_env=None, root_markers=[],\n"
        "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
        f"                    integration_files=[], markers={markers!r}),\n"
        "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
        ")\n"
    )
    return dir_path


# --------------------------------------------------------------------------- #
# A2 — _looks_like_pytest_arg heuristic (the pure predicate).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "token",
    ["-k", "-x", "-m", "--lf", "tests/foo.py", "tests/foo.py::name", "pkg::name", "a.py"],
)
def test_looks_like_pytest_arg_true(token):
    assert test_cmd._looks_like_pytest_arg(token)


@pytest.mark.parametrize("token", ["examples", "integraton", "docs", "slowtests"])
def test_looks_like_pytest_arg_false(token):
    assert not test_cmd._looks_like_pytest_arg(token)


# --------------------------------------------------------------------------- #
# A2 — end-to-end category / passthrough behaviour through the real CLI.
# --------------------------------------------------------------------------- #


def test_unknown_category_exits_2_with_helpful_message(tmp_path, monkeypatch):
    """A mistyped category fails clean (exit 2) and lists the valid categories."""
    from pyclawd import run as run_mod

    monkeypatch.setattr(
        run_mod, "pytest", lambda *a, **k: pytest.fail("pytest must not run for a bad category")
    )
    proj = _write_config(tmp_path, {"default": "not slow", "examples": "examples"})

    result = runner.invoke(app, ["--config", str(proj), "test", "integraton"])
    assert result.exit_code == 2
    err = _all_output(result)
    assert "unknown category" in err
    assert "integraton" in err
    # Categories from markers AND the built-in sub-verbs are listed.
    assert "examples" in err
    assert "timings" in err
    assert "fix" in err


def test_known_category_is_consumed(tmp_path, monkeypatch):
    """A defined marker tier is consumed as the category and its marker applied."""
    from pyclawd import run as run_mod

    captured: dict[str, object] = {}

    def fake_pytest(args, default_markers=None, tests_dir=None):
        captured["args"] = list(args)
        captured["markers"] = default_markers
        return 0

    monkeypatch.setattr(run_mod, "pytest", fake_pytest)
    proj = _write_config(tmp_path, {"default": "not slow", "examples": "examples"})

    assert runner.invoke(app, ["--config", str(proj), "test", "examples"]).exit_code == 0
    assert captured["args"] == []
    assert captured["markers"] == "examples"


def test_real_path_passes_through(tmp_path, monkeypatch):
    """A path-looking arg is handed to pytest, not flagged as an unknown category."""
    from pyclawd import run as run_mod

    captured: dict[str, object] = {}

    def fake_pytest(args, default_markers=None, tests_dir=None):
        captured["args"] = list(args)
        captured["markers"] = default_markers
        return 0

    monkeypatch.setattr(run_mod, "pytest", fake_pytest)
    proj = _write_config(tmp_path, {"default": "not slow"})

    assert runner.invoke(app, ["--config", str(proj), "test", "tests/foo.py"]).exit_code == 0
    assert captured["args"] == ["tests/foo.py"]
    assert captured["markers"] == "not slow"


def test_nodeid_and_dash_k_pass_through(tmp_path, monkeypatch):
    """nodeids and ``-k EXPR`` both keep passing straight through to pytest."""
    from pyclawd import run as run_mod

    captured: dict[str, object] = {}

    def fake_pytest(args, default_markers=None, tests_dir=None):
        captured["args"] = list(args)
        return 0

    monkeypatch.setattr(run_mod, "pytest", fake_pytest)
    proj = _write_config(tmp_path, {"default": "not slow"})

    assert runner.invoke(app, ["--config", str(proj), "test", "tests/x.py::name"]).exit_code == 0
    assert captured["args"] == ["tests/x.py::name"]

    assert runner.invoke(app, ["--config", str(proj), "test", "-k", "name"]).exit_code == 0
    assert captured["args"] == ["-k", "name"]


def test_bare_test_uses_default_tier(tmp_path, monkeypatch):
    """`pyclawd test` with no args still runs the default tier (unchanged)."""
    from pyclawd import run as run_mod

    captured: dict[str, object] = {}

    def fake_pytest(args, default_markers=None, tests_dir=None):
        captured["args"] = list(args)
        captured["markers"] = default_markers
        return 0

    monkeypatch.setattr(run_mod, "pytest", fake_pytest)
    proj = _write_config(tmp_path, {"default": "not slow"})

    assert runner.invoke(app, ["--config", str(proj), "test"]).exit_code == 0
    assert captured["args"] == []
    assert captured["markers"] == "not slow"


# --------------------------------------------------------------------------- #
# B4 — the argparse-based timings flag parser.
# --------------------------------------------------------------------------- #


def test_parse_timings_defaults():
    from pyclawd import tests as tests_mod

    assert tests_mod._parse_timings_args([]) == (25, None)


@pytest.mark.parametrize(
    "args, expected",
    [
        (["--top", "7"], (7, None)),
        (["--top=7"], (7, None)),
        (["--slow-threshold", "1.5"], (25, 1.5)),
        (["--slow-threshold=2.0"], (25, 2.0)),
        (["--top", "3", "--slow-threshold=0.5"], (3, 0.5)),
    ],
)
def test_parse_timings_valid(args, expected):
    from pyclawd import tests as tests_mod

    assert tests_mod._parse_timings_args(args) == expected


def test_parse_timings_bad_top_raises():
    from pyclawd import tests as tests_mod

    with pytest.raises(tests_mod._TimingsArgError) as exc:
        tests_mod._parse_timings_args(["--top", "notanint"])
    assert "--top expects an integer" in str(exc.value)


def test_parse_timings_bad_threshold_raises():
    from pyclawd import tests as tests_mod

    with pytest.raises(tests_mod._TimingsArgError) as exc:
        tests_mod._parse_timings_args(["--slow-threshold=fast"])
    assert "--slow-threshold expects a float" in str(exc.value)


def test_dispatch_timings_bad_value_returns_2(tmp_path, monkeypatch, capsys):
    """The dispatch wrapper turns a parse error into a clean exit-2 (no traceback)."""
    from pyclawd import tests as tests_mod

    p = _make_minimal_project(tmp_path)
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)

    rc = tests_mod.dispatch("timings", ["--top", "oops"])
    assert rc == 2
    assert "--top expects an integer" in capsys.readouterr().err


def _make_minimal_project(root: Path):
    from pyclawd import DoctorConfig, Project, TestConfig

    return Project(
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
