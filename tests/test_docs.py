"""Unit tests for the ``pyclawd docs`` command group (:mod:`pyclawd.commands.docs`).

Exercises the testable logic without standing up a real Sphinx/jupyter-cache
toolchain: the unconfigured self-report, the changed-pages git parsing, the
render preflight, the sqlite-backed timings view, and the serve guard.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import typer

from pyclawd.commands import docs as docs_cmd
from pyclawd.project import DocsConfig, DoctorConfig, Project, TestConfig


def _docs_config(root: Path) -> DocsConfig:
    return DocsConfig(
        runner=["true"],
        source_dir="docs/source",
        cache_dir="docs/.jupyter_cache",
        cache_db="docs/.jupyter_cache/global.db",
        build_html="docs/build/html",
        branch="main",
    )


def _project(root: Path, with_docs: bool = True) -> Project:
    base = Project(
        name="demo",
        conda_env=None,
        root_markers=[],
        test=TestConfig(
            tests_dir="tests/", classname_prefix="tests.", integration_files=[], markers={}
        ),
        doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),
        root=root,
        docs=_docs_config(root) if with_docs else None,
    )
    return base


# ---- self-report ------------------------------------------------------------


def test_docs_project_or_exit_returns_configured(monkeypatch, tmp_path):
    project = _project(tmp_path, with_docs=True)
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    assert docs_cmd._docs_project_or_exit() is project


def test_docs_project_or_exit_self_reports(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path, with_docs=False)
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd._docs_project_or_exit()
    assert exc.value.exit_code == 2
    assert "docs not configured" in capsys.readouterr().err


# ---- _changed_docs git parsing ----------------------------------------------


def test_changed_docs_filters_md_and_strips_prefix(monkeypatch, tmp_path):
    project = _project(tmp_path)

    class FakeProc:
        stdout = "docs/source/intro.md\ndocs/source/api.rst\ndocs/source/guide/x.md\n"

    monkeypatch.setattr(docs_cmd.subprocess, "run", lambda *a, **k: FakeProc())
    pages = docs_cmd._changed_docs(project)
    # Only .md files, with the leading "docs/" component stripped.
    assert pages == ["source/intro.md", "source/guide/x.md"]


# ---- render preflight -------------------------------------------------------


def test_preflight_render_passes_when_pandoc_present(monkeypatch):
    monkeypatch.setattr(docs_cmd.shutil, "which", lambda name: "/usr/bin/pandoc")
    docs_cmd._preflight_render()  # must not raise


def test_preflight_render_exits_when_pandoc_missing(monkeypatch, capsys):
    monkeypatch.setattr(docs_cmd.shutil, "which", lambda name: None)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd._preflight_render()
    assert exc.value.exit_code == 3
    assert "pandoc not found" in capsys.readouterr().err


# ---- timings (sqlite-backed) ------------------------------------------------


def test_docs_timings_reads_cache(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path)
    db = project.path(project.docs.cache_db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE nbcache (uri TEXT, data TEXT)")
    con.executemany(
        "INSERT INTO nbcache VALUES (?, ?)",
        [
            ("docs/source/slow.ipynb", json.dumps({"execution_seconds": 12.5})),
            ("docs/source/fast.ipynb", json.dumps({"execution_seconds": 0.5})),
            ("docs/source/none.ipynb", json.dumps({})),  # no timing → skipped
        ],
    )
    con.commit()
    con.close()

    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    docs_cmd.docs_timings(top=0)
    out = capsys.readouterr().out
    assert "2 notebooks" in out  # the untimed one is excluded
    # Slowest first.
    assert out.index("slow.ipynb") < out.index("fast.ipynb")


def test_docs_timings_no_cache(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path)
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd.docs_timings(top=0)
    assert exc.value.exit_code == 0
    assert "No jupyter-cache database" in capsys.readouterr().out


# ---- failures (jupyter-cache backed) ----------------------------------------


def test_docs_failures_no_cache(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path)
    # cache_dir/global.db does not exist → degrade cleanly.
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd.docs_failures(full=False)
    assert exc.value.exit_code == 0
    assert "No cache yet" in capsys.readouterr().out


def test_docs_failures_missing_backend(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path)
    # The cache DB exists, so we get past the no-cache guard...
    db = project.path(project.docs.cache_dir) / "global.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.touch()
    # ...but the jupyter-cache backend can't be imported → exit 2 (not configured).
    monkeypatch.setitem(sys.modules, "nbformat", None)
    monkeypatch.setitem(sys.modules, "jupyter_cache", None)
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd.docs_failures(full=False)
    assert exc.value.exit_code == 2
    assert "jupyter-cache" in capsys.readouterr().err


# ---- serve guard ------------------------------------------------------------


def test_docs_serve_requires_a_build(monkeypatch, tmp_path, capsys):
    project = _project(tmp_path)
    monkeypatch.setattr(docs_cmd.run, "load_project_or_exit", lambda: project)
    with pytest.raises(typer.Exit) as exc:
        docs_cmd.docs_serve(port=8000, background=False, bind="0.0.0.0")
    assert exc.value.exit_code == 1
    assert "No built docs" in capsys.readouterr().out


def test_lan_ip_returns_str_or_none():
    ip = docs_cmd._lan_ip()
    assert ip is None or isinstance(ip, str)


# ---- output guardrail (validate) --------------------------------------------


def _write_ipynb(path: Path, n_outputs: int) -> None:
    """Write a minimal notebook with one code cell carrying *n_outputs* outputs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cell = {
        "cell_type": "code",
        "source": ["1 + 1"],
        "outputs": [{"output_type": "execute_result"} for _ in range(n_outputs)],
    }
    path.write_text(json.dumps({"cells": [cell]}))


def _write_html(path: Path, *, with_output: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "<div class='nbinput'>code</div>"
    if with_output:
        body += "<div class='nboutput'>result</div>"
    path.write_text(f"<html>{body}</html>")


def test_validate_outputs_passes_when_outputs_rendered(tmp_path):
    project = _project(tmp_path)
    src = project.path(project.docs.source_dir)
    html = project.path(project.docs.build_html)
    _write_ipynb(src / "algorithms" / "page.ipynb", n_outputs=3)
    _write_html(html / "algorithms" / "page.html", with_output=True)
    assert docs_cmd._validate_outputs(project) == 0


def test_validate_outputs_flags_executed_but_blank_page(tmp_path, capsys):
    project = _project(tmp_path)
    src = project.path(project.docs.source_dir)
    html = project.path(project.docs.build_html)
    _write_ipynb(src / "algorithms" / "page.ipynb", n_outputs=4)
    _write_html(html / "algorithms" / "page.html", with_output=False)  # the incident
    assert docs_cmd._validate_outputs(project) == 1
    assert "rendered blank" in capsys.readouterr().err


def test_validate_outputs_ignores_output_free_page(tmp_path):
    project = _project(tmp_path)
    src = project.path(project.docs.source_dir)
    html = project.path(project.docs.build_html)
    _write_ipynb(src / "intro.ipynb", n_outputs=0)  # legitimately output-free
    _write_html(html / "intro.html", with_output=False)
    assert docs_cmd._validate_outputs(project) == 0


def test_validate_outputs_skips_unrendered_pages(tmp_path):
    project = _project(tmp_path)
    src = project.path(project.docs.source_dir)
    _write_ipynb(src / "only_executed.ipynb", n_outputs=2)  # no HTML rendered (e.g. --changed)
    assert docs_cmd._validate_outputs(project) == 0
