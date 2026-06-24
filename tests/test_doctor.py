"""Unit tests for the ``pyclawd doctor`` health checks (:mod:`pyclawd.doctor`).

Each individual check is a pure-ish function over the environment; we exercise the
OK/WARN/FAIL branches directly and the ``collect`` / ``run_doctor`` aggregation
with a crafted project (no real env assumptions beyond the running interpreter).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from pyclawd import doctor
from pyclawd.project import (
    FAIL,
    OK,
    WARN,
    DocsConfig,
    DoctorConfig,
    GoldenConfig,
    Project,
    TestConfig,
)


def _docs() -> DocsConfig:
    return DocsConfig(
        runner=["acme-docs", "build"],
        source_dir="docs/source",
        cache_dir="docs/.jupyter_cache",
        cache_db="docs/.jupyter_cache/global.db",
        build_html="docs/build/html",
        branch="main",
    )


def _project(**overrides) -> Project:
    base = Project(
        name="demo",
        conda_env=None,
        root_markers=[],
        test=TestConfig(
            tests_dir="tests/", classname_prefix="tests.", integration_files=[], markers={}
        ),
        doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),
        root=Path("/tmp/repo"),
    )
    return dataclasses.replace(base, **overrides)


# ---- individual checks ------------------------------------------------------


def test_check_python_ok_on_supported_interpreter():
    c = doctor._check_python()
    assert c.status == OK  # the test runner itself requires >= 3.10


def test_check_conda_env_agnostic_is_ok():
    assert doctor._check_conda_env(None).status == OK


def test_check_conda_env_mismatch_warns(monkeypatch):
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "somethingelse")
    c = doctor._check_conda_env("expected_env")
    assert c.status == WARN
    assert "expected" in c.detail


def test_check_conda_env_match_is_ok(monkeypatch):
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "myenv")
    assert doctor._check_conda_env("myenv").status == OK


def test_check_import_present_is_ok():
    assert doctor._check_import("json", required=True).status == OK


def test_check_import_missing_required_fails():
    assert doctor._check_import("no_such_module_xyz", required=True).status == FAIL


def test_check_import_missing_optional_warns():
    assert doctor._check_import("no_such_module_xyz", required=False).status == WARN


def test_check_binary_missing_warns_with_hint():
    c = doctor._check_binary("definitely_not_a_binary_xyz", "install it somehow")
    assert c.status == WARN
    assert "install it somehow" in c.detail


def test_check_binary_present_is_ok(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/" + name)
    assert doctor._check_binary("ruff", "hint").status == OK


# ---- collect / run_doctor aggregation ---------------------------------------


def test_collect_degrades_without_a_project(monkeypatch):
    # collect(None) re-discovers; force "no project found" (the test cwd has one).
    monkeypatch.setattr(doctor, "load_project", lambda: None)
    checks = doctor.collect(None)
    names = {c.name for c in checks}
    assert "python" in names
    assert any("project config" in c.name for c in checks)


def test_collect_reports_missing_core_dep_as_fail():
    project = _project(
        doctor=DoctorConfig(
            core_deps=["no_such_module_xyz"], dev_deps=[], tool_files=[], binaries=[]
        )
    )
    checks = doctor.collect(project)
    assert any(c.status == FAIL and c.name == "no_such_module_xyz" for c in checks)


def test_run_doctor_returns_1_on_failure(monkeypatch):
    project = _project(
        doctor=DoctorConfig(
            core_deps=["no_such_module_xyz"], dev_deps=[], tool_files=[], binaries=[]
        )
    )
    monkeypatch.setattr(doctor, "load_project", lambda: project)
    assert doctor.run_doctor() == 1


def test_run_doctor_returns_0_when_clean(monkeypatch):
    project = _project()  # no core deps, no tool files → nothing can FAIL
    monkeypatch.setattr(doctor, "load_project", lambda: project)
    assert doctor.run_doctor() == 0


# ---- pyclawd version + compatibility ----------------------------------------


def test_check_pyclawd_reports_version_and_location():
    import pyclawd

    c = doctor._check_pyclawd()
    assert c.status == OK
    assert c.name == "pyclawd"
    assert pyclawd.__version__ in c.detail


def test_mm_parses_major_minor():
    assert doctor._mm("0.1.0") == (0, 1)
    assert doctor._mm("2.10.3") == (2, 10)
    assert doctor._mm("nonsense") is None


def test_compat_disabled_when_unset():
    assert doctor._check_pyclawd_compat("") is None


def test_compat_ok_when_matching_running_version():
    import pyclawd

    c = doctor._check_pyclawd_compat(pyclawd.__version__)
    assert c is not None and c.status == OK


def test_compat_warns_on_minor_mismatch():
    c = doctor._check_pyclawd_compat("99.99.0")
    assert c is not None and c.status == WARN
    assert "pyclawd-upgrade" in c.detail  # points at the migration skill


def test_compat_row_appears_in_collect_when_declared():
    project = _project(pyclawd_version="99.99.0")
    rows = {c.name: c for c in doctor.collect(project)}
    assert "pyclawd compat" in rows
    assert rows["pyclawd compat"].status == WARN


# ---- docs prerequisite check ------------------------------------------------


def test_check_docs_empty_when_docs_unconfigured():
    assert doctor._check_docs(_project()) == []  # docs is None → no rows


def test_check_docs_warns_when_runner_not_on_path(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    rows = {c.name: c for c in doctor._check_docs(_project(docs=_docs()))}
    assert rows["docs runner"].status == WARN
    assert "not on PATH" in rows["docs runner"].detail


def test_check_docs_ok_runner_and_reports_jupyter_cache(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/" + name)
    rows = {c.name: c for c in doctor._check_docs(_project(docs=_docs()))}
    assert rows["docs runner"].status == OK
    # jupyter-cache is reported either way (OK if importable here, else WARN).
    assert "jupyter-cache" in rows
    assert rows["jupyter-cache"].status in (OK, WARN)


# ---- golden oracle check ----------------------------------------------------


def test_check_golden_empty_when_unconfigured():
    assert doctor._check_golden(_project()) == []  # golden is None → no rows


def test_check_golden_warns_when_no_baselines(tmp_path):
    project = _project(golden=GoldenConfig(), root=tmp_path)
    rows = {c.name: c for c in doctor._check_golden(project)}
    assert rows["golden"].status == OK
    assert "golden" in rows["golden"].detail
    assert rows["golden baselines"].status == WARN
    assert "pyclawd golden update" in rows["golden baselines"].detail


def test_check_golden_ok_when_baselines_present(tmp_path):
    baseline_dir = tmp_path / "tests" / "golden"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "test_minimize.json").write_text("{}")
    project = _project(golden=GoldenConfig(), root=tmp_path)
    rows = {c.name: c for c in doctor._check_golden(project)}
    assert rows["golden"].status == OK
    assert rows["golden baselines"].status == OK
    assert "1 module file(s)" in rows["golden baselines"].detail


def test_check_golden_warns_when_root_unknown():
    project = _project(golden=GoldenConfig(), root=None)
    rows = {c.name: c for c in doctor._check_golden(project)}
    assert rows["golden"].status == OK
    assert rows["golden baselines"].status == WARN


# ---- dump_json --------------------------------------------------------------


def test_dump_json_emits_valid_json_with_expected_keys(capsys):
    project = _project()
    code = doctor.dump_json(project)
    assert isinstance(code, int)
    data = json.loads(capsys.readouterr().out)
    assert data["project"] == "demo"
    assert isinstance(data["checks"], list)
    assert "ok" in data
    assert "n_fail" in data
    assert "n_warn" in data


def test_dump_json_ok_true_when_no_fails(capsys):
    project = _project()
    doctor.dump_json(project)
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["n_fail"] == 0


def test_dump_json_ok_false_and_returns_1_on_fail(capsys):
    project = _project(
        doctor=DoctorConfig(
            core_deps=["no_such_module_xyz"], dev_deps=[], tool_files=[], binaries=[]
        )
    )
    code = doctor.dump_json(project)
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert data["n_fail"] >= 1
    assert code == 1


def test_dump_json_check_entries_have_required_fields(capsys):
    project = _project()
    doctor.dump_json(project)
    data = json.loads(capsys.readouterr().out)
    for check in data["checks"]:
        assert "name" in check
        assert "status" in check
        assert "detail" in check
