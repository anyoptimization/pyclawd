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
import json
import xml.etree.ElementTree as ET
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
# run.python_prefix — interpreter resolution: env var > python_cmd > sys.executable.
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
# quality command layer — unconfigured self-report + check run-all behaviour.
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


def _check(**overrides):
    """Call ``quality_cmd.check`` with every flag defaulted, applying *overrides*.

    Keeps these direct-call tests resilient to new ``check()`` parameters — a new
    flag only needs a default added here, not a change at every call site.
    """
    kwargs = {
        "fix": False,
        "skip": None,
        "fail_fast": False,
        "save_logs": False,
        "json_output": False,
        "changed": False,
        "against": "HEAD",
        "with_test": False,
        "paths": None,
    }
    kwargs.update(overrides)
    return quality_cmd.check(**kwargs)


def test_check_runs_all_quality_steps_and_passes(monkeypatch):
    calls: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    # save_logs=False → run.run() is called, not _tee — patch the right function.
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (calls.append(cmd[0]), 0)[1])

    with pytest.raises(typer.Exit) as exc:
        _check()
    assert exc.value.exit_code == 0
    assert calls == ["ruff", "ruff", "mypy"]  # format-check, lint, typecheck — all ran


def test_check_runs_all_quality_steps_then_skips_test_on_failure(monkeypatch):
    """All quality steps run even when one fails; the test step is skipped."""
    ran: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)

    def fake_run(cmd, root):
        ran.append(cmd[0])
        return 1 if cmd[:2] == ["ruff", "check"] else 0  # lint fails

    # save_logs=False → run.run() is called, not _tee — patch the right function.
    monkeypatch.setattr(quality_cmd.run, "run", fake_run)
    with pytest.raises(typer.Exit) as exc:
        _check()
    assert exc.value.exit_code == 1
    # All three quality steps ran (format-check, lint, typecheck); test was skipped.
    assert ran == ["ruff", "ruff", "mypy"]


def test_check_skip_omits_step(monkeypatch):
    """``--skip typecheck`` drops that step from the sequence."""
    ran: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (ran.append(cmd[0]), 0)[1])
    with pytest.raises(typer.Exit) as exc:
        _check(skip=["typecheck"])
    assert exc.value.exit_code == 0
    assert ran == ["ruff", "ruff"]  # mypy step omitted


def test_check_fail_fast_stops_at_first_failure(monkeypatch):
    """``--fail-fast`` stops after the first failing step."""
    ran: list[str] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    # format-check fails first.
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (ran.append(cmd[0]), 1)[1])
    with pytest.raises(typer.Exit) as exc:
        _check(fail_fast=True)
    assert exc.value.exit_code == 1
    assert ran == ["ruff"]  # stopped after the first (format-check) failure


def test_check_fix_uses_fix_commands(monkeypatch):
    """``--fix`` routes format/lint steps to the write-in-place variants."""
    captured: list[list[str]] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        format_cmd=["ruff", "format"],
        lint_cmd=["ruff", "check"],
        lint_fix_cmd=["ruff", "check", "--fix"],
        typecheck_cmd=["mypy"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (captured.append(cmd), 0)[1])
    with pytest.raises(typer.Exit) as exc:
        _check(fix=True)
    assert exc.value.exit_code == 0
    assert ["ruff", "format"] in captured  # format_cmd, not format_check_cmd
    assert ["ruff", "check", "--fix"] in captured  # lint_fix_cmd, not lint_cmd


def test_check_paths_are_quality_only_by_default(monkeypatch):
    """Path-scoped check drops the whole-suite test step unless --test is given."""
    ran_quality: list[str] = []
    test_ran: list[bool] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(
        quality_cmd.run, "run", lambda cmd, root: (ran_quality.append(cmd[0]), 0)[1]
    )
    monkeypatch.setattr(
        quality_cmd.tests, "run_suite", lambda *a, **k: (test_ran.append(True), 0)[1]
    )
    with pytest.raises(typer.Exit) as exc:
        _check(paths=["src/foo.py"])
    assert exc.value.exit_code == 0
    assert ran_quality == ["ruff", "ruff", "mypy"]
    assert test_ran == []  # test auto-skipped when path-scoped


def test_check_paths_with_test_flag_runs_suite(monkeypatch):
    """--test forces the whole-suite test step back on even when path-scoped."""
    test_ran: list[bool] = []
    q = QualityConfig(
        lint_cmd=["ruff", "check"],
        format_check_cmd=["ruff", "format", "--check"],
        typecheck_cmd=["mypy"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: 0)
    monkeypatch.setattr(
        quality_cmd.tests, "run_suite", lambda *a, **k: (test_ran.append(True), 0)[1]
    )
    with pytest.raises(typer.Exit):
        _check(paths=["src/foo.py"], with_test=True)
    assert test_ran == [True]


def test_check_json_emits_machine_readable(monkeypatch, capsys):
    """--json prints one parseable object with per-step status and is quality-only."""
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    # --json routes quality steps through run_logged; lint fails.
    monkeypatch.setattr(
        quality_cmd,
        "_run_logged",
        lambda cmd, log, root: 1 if cmd[:2] == ["ruff", "check"] else 0,
    )
    with pytest.raises(typer.Exit) as exc:
        _check(json_output=True)
    assert exc.value.exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["passed"] is False
    steps = {s["verb"]: s for s in payload["steps"]}
    assert steps["format-check"]["status"] == "ok"
    assert steps["lint"]["status"] == "fail"
    assert steps["lint"]["exit_code"] == 1
    assert steps["test"]["status"] == "skipped"  # --json is quality-only
    assert steps["test"]["reason"] == "quality-only"


def test_check_changed_scopes_to_git_source_files(monkeypatch):
    """--changed feeds git-changed source files (only .py/.pyx) as paths, quality-only."""
    captured: list[list[str]] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(
        quality_cmd.repo,
        "changed_files",
        lambda root, against: ["src/a.py", "README.md", "src/b.pyx"],
    )
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (captured.append(cmd), 0)[1])
    with pytest.raises(typer.Exit) as exc:
        _check(changed=True)
    assert exc.value.exit_code == 0
    # README.md filtered out by the descriptions include (.py/.pyx); test step skipped.
    assert captured[0] == ["ruff", "format", "--check", "src/a.py", "src/b.pyx"]


def test_check_changed_no_files_exits_0(monkeypatch, capsys):
    """--changed with nothing changed reports cleanly and exits 0."""
    q = QualityConfig(lint_cmd=["ruff", "check"], check_sequence=["lint"])
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.repo, "changed_files", lambda root, against: [])
    with pytest.raises(typer.Exit) as exc:
        _check(changed=True)
    assert exc.value.exit_code == 0
    assert "no changed source files" in capsys.readouterr().out


def test_lint_appends_paths_to_cmd(monkeypatch):
    """Paths passed to lint are appended to the configured lint_cmd."""
    captured: list[list[str]] = []
    q = QualityConfig(lint_cmd=["ruff", "check"])
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (captured.append(cmd), 0)[1])
    with pytest.raises(typer.Exit) as exc:
        quality_cmd.lint(fix=False, paths=["src/mypkg/foo.py"])
    assert exc.value.exit_code == 0
    assert captured == [["ruff", "check", "src/mypkg/foo.py"]]


def test_typecheck_appends_paths_to_cmd(monkeypatch):
    """Paths passed to typecheck are appended to the configured typecheck_cmd."""
    captured: list[list[str]] = []
    q = QualityConfig(typecheck_cmd=["mypy", "src"])
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    monkeypatch.setattr(quality_cmd.run, "run", lambda cmd, root: (captured.append(cmd), 0)[1])
    with pytest.raises(typer.Exit) as exc:
        quality_cmd.typecheck(paths=["src/mypkg/bar.py"])
    assert exc.value.exit_code == 0
    assert captured == [["mypy", "src", "src/mypkg/bar.py"]]


def test_check_propagates_paths_to_quality_steps(monkeypatch):
    """check() appends paths to each quality-step command; test step ignores paths."""
    captured_cmds: list[list[str]] = []
    q = QualityConfig(
        format_check_cmd=["ruff", "format", "--check"],
        lint_cmd=["ruff", "check"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck"],
    )
    p = _project(root=Path("/tmp/repo"), quality=q)
    monkeypatch.setattr(quality_cmd.run, "load_project_or_exit", lambda: p)
    # save_logs=False → run.run() is called, not _tee — patch the right function.
    monkeypatch.setattr(
        quality_cmd.run,
        "run",
        lambda cmd, root: (captured_cmds.append(cmd), 0)[1],
    )
    with pytest.raises(typer.Exit) as exc:
        _check(paths=["src/mypkg/foo.py"])
    assert exc.value.exit_code == 0
    assert captured_cmds == [
        ["ruff", "format", "--check", "src/mypkg/foo.py"],
        ["ruff", "check", "src/mypkg/foo.py"],
        ["mypy", "src", "src/mypkg/foo.py"],
    ]


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


# --------------------------------------------------------------------------- #
# tests.print_timings — --slow-threshold filtering.
# --------------------------------------------------------------------------- #


def _write_junit(path: Path, testcases: list[tuple[str, str, float]]) -> Path:
    """Write a minimal junit XML with (classname, name, time) entries."""
    root_el = ET.Element("testsuite")
    for classname, name, time_s in testcases:
        tc = ET.SubElement(root_el, "testcase")
        tc.set("classname", classname)
        tc.set("name", name)
        tc.set("time", str(time_s))
    ET.ElementTree(root_el).write(str(path))
    return path


def test_print_timings_slow_threshold_filters(tmp_path, monkeypatch, capsys):
    """Only tests above the threshold appear; the slow-marker hint is printed."""
    from pyclawd import tests as tests_mod

    junit = _write_junit(
        tmp_path / "run.junit.xml",
        [
            ("tests.test_heavy", "test_expensive", 3.2),
            ("tests.test_db", "test_query", 1.5),
            ("tests.test_model", "test_train", 1.1),
            ("tests.test_fast", "test_quick", 0.3),
        ],
    )
    ptr = tmp_path / "latest-junit.txt"
    ptr.write_text(str(junit))

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "_junit_ptr", lambda _proj: ptr)

    rc = tests_mod.print_timings(p, slow_threshold=1.0)
    assert rc == 0
    out = capsys.readouterr().out
    assert "3 tests over 1.0s" in out
    assert "consider adding @pytest.mark.slow" in out
    assert "test_expensive" in out
    assert "test_query" in out
    assert "test_train" in out
    assert "test_quick" not in out


def test_print_timings_slow_threshold_no_results(tmp_path, monkeypatch, capsys):
    """When nothing exceeds the threshold, 'No tests over Xs found.' is printed."""
    from pyclawd import tests as tests_mod

    junit = _write_junit(
        tmp_path / "run.junit.xml",
        [
            ("tests.test_fast", "test_quick", 0.3),
            ("tests.test_fast", "test_other", 0.5),
        ],
    )
    ptr = tmp_path / "latest-junit.txt"
    ptr.write_text(str(junit))

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "_junit_ptr", lambda _proj: ptr)

    rc = tests_mod.print_timings(p, slow_threshold=1.0)
    assert rc == 0
    assert "No tests over 1.0s found." in capsys.readouterr().out


def test_print_timings_no_threshold_uses_top(tmp_path, monkeypatch, capsys):
    """Without a threshold, top=N slicing still works as before."""
    from pyclawd import tests as tests_mod

    junit = _write_junit(
        tmp_path / "run.junit.xml",
        [
            ("tests.test_a", "test_1", 3.0),
            ("tests.test_b", "test_2", 2.0),
            ("tests.test_c", "test_3", 1.0),
        ],
    )
    ptr = tmp_path / "latest-junit.txt"
    ptr.write_text(str(junit))

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "_junit_ptr", lambda _proj: ptr)

    rc = tests_mod.print_timings(p, top=2)
    assert rc == 0
    out = capsys.readouterr().out
    assert "3 tests" in out  # header shows the total count
    assert "test_1" in out
    assert "test_2" in out
    assert "test_3" not in out  # top=2 excludes the third


def test_dispatch_timings_slow_threshold_space_form(tmp_path, monkeypatch):
    """dispatch() correctly parses `--slow-threshold 1.5` (space-separated form)."""
    from pyclawd import tests as tests_mod

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)

    captured: dict[str, object] = {}

    def fake_print_timings(proj: object, top: int = 25, slow_threshold: float | None = None) -> int:
        captured["top"] = top
        captured["slow_threshold"] = slow_threshold
        return 0

    monkeypatch.setattr(tests_mod, "print_timings", fake_print_timings)
    rc = tests_mod.dispatch("timings", ["--slow-threshold", "1.5"])
    assert rc == 0
    assert captured["slow_threshold"] == 1.5


def test_dispatch_timings_slow_threshold_equals_form(tmp_path, monkeypatch):
    """dispatch() correctly parses `--slow-threshold=2.0` (equals form)."""
    from pyclawd import tests as tests_mod

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)

    captured: dict[str, object] = {}

    def fake_print_timings(proj: object, top: int = 25, slow_threshold: float | None = None) -> int:
        captured["slow_threshold"] = slow_threshold
        return 0

    monkeypatch.setattr(tests_mod, "print_timings", fake_print_timings)
    rc = tests_mod.dispatch("timings", ["--slow-threshold=2.0"])
    assert rc == 0
    assert captured["slow_threshold"] == 2.0


def test_dispatch_timings_slow_threshold_invalid(tmp_path, monkeypatch, capsys):
    """dispatch() returns exit code 2 and prints an error for a non-float threshold."""
    from pyclawd import tests as tests_mod

    p = _project(root=tmp_path)
    monkeypatch.setattr(tests_mod, "load_project_or_exit", lambda: p)
    rc = tests_mod.dispatch("timings", ["--slow-threshold", "fast"])
    assert rc == 2
    assert "--slow-threshold expects a float" in capsys.readouterr().err
