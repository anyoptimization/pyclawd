"""Unit tests for the previously-uncovered core logic.

These fill the gaps left by ``test_project`` / ``test_new`` / ``test_skills`` /
``test_fixes``: the pytest-argv heuristics in :mod:`pyclawd.run`, the
test-tier marker resolution in :mod:`pyclawd.tests`, the quality command layer in
:mod:`pyclawd.commands.quality`, and the config-discovery overrides
(``--config`` / ``PYCLAWD_CONFIG``) in :mod:`pyclawd.discovery`.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import typer

from pyclawd import Project, QualityConfig, TestConfig, discovery
from pyclawd.commands import quality as quality_cmd
from pyclawd.project import DoctorConfig
from pyclawd.run import PYTHON_ENV, has_target, python_prefix

# --------------------------------------------------------------------------- #
# Shared minimal project.
# --------------------------------------------------------------------------- #


def _project(root: Path | None = None, **overrides) -> Project:
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
# run.has_target — decides whether pytest already names an explicit target.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "args, expected",
    [
        (["-k", "foo"], False),  # keyword expression — not a path
        (["-m", "not slow"], False),  # marker expression — not a path
        (["--maxfail=1"], False),  # a flag with a value
        ([], False),  # nothing
        (["tests/test_x.py"], True),  # a file path
        (["tests/test_x.py::test_y"], True),  # a nodeid
        (["pkg/sub"], True),  # a directory path
        (["test_mod.py"], True),  # a bare file
    ],
)
def test_has_target(args, expected):
    assert has_target(args) is expected


# --------------------------------------------------------------------------- #
# run.python_prefix — interpreter resolution: env var › python_cmd › sys.executable.
# --------------------------------------------------------------------------- #


def test_python_prefix_defaults_to_sys_executable(monkeypatch):
    import sys

    monkeypatch.delenv(PYTHON_ENV, raising=False)
    assert python_prefix(_project()) == [sys.executable]


def test_python_prefix_uses_configured_python_cmd(monkeypatch):
    monkeypatch.delenv(PYTHON_ENV, raising=False)
    p = _project(python_cmd=["conda", "run", "-n", "myenv", "python"])
    assert python_prefix(p) == ["conda", "run", "-n", "myenv", "python"]


def test_python_prefix_env_var_overrides_config(monkeypatch):
    monkeypatch.setenv(PYTHON_ENV, "uv run python")
    p = _project(python_cmd=["conda", "run", "-n", "myenv", "python"])
    # The env var wins and is shlex-split into argv.
    assert python_prefix(p) == ["uv", "run", "python"]


def test_python_prefix_env_var_handles_quoted_paths(monkeypatch):
    monkeypatch.setenv(PYTHON_ENV, "'/opt/my env/bin/python'")
    assert python_prefix(_project()) == ["/opt/my env/bin/python"]


# --------------------------------------------------------------------------- #
# logs.work_root — configurable per-project work directory.
# --------------------------------------------------------------------------- #


def test_work_root_defaults_to_tmpdir(monkeypatch):
    import tempfile

    from pyclawd import logs

    monkeypatch.delenv(logs.WORK_ENV, raising=False)
    assert logs.work_root(_project()) == Path(tempfile.gettempdir()) / "pyclawd"


def test_work_root_uses_absolute_config_value(monkeypatch):
    from pyclawd import logs

    monkeypatch.delenv(logs.WORK_ENV, raising=False)
    p = _project(work_dir="/var/run/myproj", root=Path("/repo"))
    assert logs.work_root(p) == Path("/var/run/myproj")


def test_work_root_resolves_relative_config_against_root(monkeypatch):
    from pyclawd import logs

    monkeypatch.delenv(logs.WORK_ENV, raising=False)
    p = _project(work_dir=".pyclawd/work", root=Path("/repo"))
    assert logs.work_root(p) == Path("/repo/.pyclawd/work")


def test_work_root_env_var_overrides_config(monkeypatch):
    from pyclawd import logs

    monkeypatch.setenv(logs.WORK_ENV, "/override/here")
    p = _project(work_dir="/config/value", root=Path("/repo"))
    assert logs.work_root(p) == Path("/override/here")


def test_category_dir_is_under_work_root(monkeypatch):
    from pyclawd import logs

    monkeypatch.delenv(logs.WORK_ENV, raising=False)
    p = _project(work_dir="/w", root=Path("/repo"))
    assert logs.category_dir("tests", p) == Path("/w/logs/tests")


# --------------------------------------------------------------------------- #
# tests.tier_markers — undefined tiers must degrade, never KeyError-crash.
# --------------------------------------------------------------------------- #


def test_tier_markers_returns_configured_value():
    from pyclawd import tests as tests_mod

    p = _project()
    assert tests_mod.tier_markers(p, "default") == "not slow"
    assert tests_mod.tier_markers(p, "all") == ""


def test_tier_markers_missing_tier_is_empty_not_keyerror():
    from pyclawd import tests as tests_mod

    # A project that customises the tier set down to just "default".
    p = _project(
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=[],
            markers={"default": "not slow"},
        )
    )
    # Both of these used to raise a raw KeyError before the fix.
    assert tests_mod.tier_markers(p, "fast") == ""
    assert tests_mod.tier_markers(p, "all") == ""


def test_dispatch_fast_and_all_do_not_crash_on_minimal_markers(monkeypatch):
    """`pyclawd test fast` / `all` must run even when only `default` is defined."""
    from pyclawd import tests as tests_mod

    p = _project(
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=[],
            markers={"default": "not slow"},
        ),
        root=Path("/tmp/repo"),
    )
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)

    captured = {}

    def fake_run_suite(extra_args, markers, label, project, jobs=None):
        captured[label] = markers
        return 0

    monkeypatch.setattr(tests_mod, "run_suite", fake_run_suite)
    assert tests_mod.dispatch("fast", []) == 0
    assert tests_mod.dispatch("all", []) == 0
    assert captured == {"fast": "", "all": ""}


def test_all_tiers_parallelize_with_config_jobs(monkeypatch):
    """run / fast / all all forward TestConfig.jobs (xdist), not just fast."""
    from pyclawd import tests as tests_mod

    p = _project(
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=[],
            markers={"default": "", "fast": "", "all": ""},
            jobs="3",
        ),
        root=Path("/tmp/repo"),
    )
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)
    seen = {}

    def fake_run_suite(extra_args, markers, label, project, jobs=None):
        seen[label] = jobs
        return 0

    monkeypatch.setattr(tests_mod, "run_suite", fake_run_suite)
    for verb in ("run", "fast", "all"):
        tests_mod.dispatch(verb, [])
    assert seen == {"run": "3", "fast": "3", "all": "3"}


def test_test_config_jobs_defaults_to_auto():
    assert (
        TestConfig(tests_dir="t/", classname_prefix="t.", integration_files=[], markers={}).jobs
        == "auto"
    )


# --------------------------------------------------------------------------- #
# quality command layer — unconfigured self-report + check fail-fast.
# --------------------------------------------------------------------------- #


def test_lint_exits_2_when_quality_unconfigured(monkeypatch, capsys):
    p = _project(root=Path("/tmp/repo"))  # quality is None
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    with pytest.raises(typer.Exit) as exc:
        quality_cmd.lint(fix=False)
    assert exc.value.exit_code == 2
    assert "quality not configured" in capsys.readouterr().err


def test_lint_exits_2_when_specific_cmd_empty(monkeypatch, capsys):
    # quality exists, but lint_cmd is empty → exit 2 with an actionable message.
    p = _project(root=Path("/tmp/repo"), quality=QualityConfig(typecheck_cmd=["mypy", "src"]))
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    with pytest.raises(typer.Exit) as exc:
        quality_cmd.lint(fix=False)
    assert exc.value.exit_code == 2
    assert "lint not configured" in capsys.readouterr().err


def test_check_runs_sequence_in_order_and_passes(monkeypatch):
    calls: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (calls.append(cmd[0]), 0)[1])

    with pytest.raises(typer.Exit) as exc:
        quality_cmd.check()
    assert exc.value.exit_code == 0
    assert calls == ["ruff", "ruff", "mypy"]  # format-check, lint, typecheck — in order


def test_check_is_fail_fast(monkeypatch):
    """A failing step stops the sequence — later steps never run."""
    ran: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)

    def fake_run(cmd, root):
        ran.append(cmd[0])
        return 1 if cmd[:2] == ["ruff", "check"] else 0  # lint fails

    monkeypatch.setattr(quality_cmd.run, "run", fake_run)
    with pytest.raises(typer.Exit) as exc:
        quality_cmd.check()
    assert exc.value.exit_code == 1
    # format-check ran, lint ran (and failed), typecheck was NOT reached.
    assert ran == ["ruff", "ruff"]


# --------------------------------------------------------------------------- #
# discovery — explicit override + PYCLAWD_CONFIG env var precedence.
# --------------------------------------------------------------------------- #


def _write_config(dir_path: Path, name: str) -> Path:
    pyclawd_dir = dir_path / ".pyclawd"
    pyclawd_dir.mkdir(parents=True, exist_ok=True)
    (pyclawd_dir / "config.py").write_text(
        "from pyclawd import Project, TestConfig, DoctorConfig\n"
        "project = Project(\n"
        f"    name={name!r}, conda_env=None, root_markers=[],\n"
        "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
        "                    integration_files=[], markers={'default': ''}),\n"
        "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
        ")\n"
    )
    return dir_path


def test_explicit_config_override_wins_over_walkup(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_CACHE", {})
    a = _write_config(tmp_path / "a", "proj_a")
    b = _write_config(tmp_path / "b", "proj_b")
    # cwd is inside a, but the explicit override points at b → b wins.
    proj = discovery.load_project(start=a, config=b)
    assert proj is not None and proj.name == "proj_b"
    assert proj.root == (b).resolve()


def test_config_override_accepts_a_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_CACHE", {})
    root = _write_config(tmp_path / "proj", "dir_proj")
    # Passing the repo dir (not the file) resolves <dir>/.pyclawd/config.py.
    assert discovery.find_config_file(config=root) == (root / ".pyclawd" / "config.py").resolve()


def test_pyclawd_config_env_var_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_CACHE", {})
    monkeypatch.setattr(discovery, "_OVERRIDE", None)
    root = _write_config(tmp_path / "envproj", "env_proj")
    monkeypatch.setenv(discovery.ENV_VAR, str(root / ".pyclawd" / "config.py"))
    # Walk-up starts somewhere with no config, but the env var resolves it.
    other = tmp_path / "elsewhere"
    other.mkdir()
    proj = discovery.load_project(start=other)
    assert proj is not None and proj.name == "env_proj"


def test_set_config_override_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_CACHE", {})
    root = _write_config(tmp_path / "ov", "ov_proj")
    discovery.set_config_override(str(root))
    try:
        proj = discovery.load_project(start=tmp_path / "nope")
        assert proj is not None and proj.name == "ov_proj"
    finally:
        discovery.set_config_override(None)
    assert discovery._OVERRIDE is None
