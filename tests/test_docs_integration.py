"""Integration test: the scaffolded ``docs/`` actually builds HTML end-to-end.

This goes beyond the structural check in ``test_new`` — it scaffolds a project
with ``--docs``, then runs the generated runner's ``compile`` (jupytext .md → .ipynb)
and ``build`` (sphinx + nbsphinx render) and asserts real HTML is produced.

It needs the docs toolchain (sphinx/nbsphinx/jupytext) + the ``pandoc`` binary, so
the whole module skips when they are absent (e.g. a CI job without docs deps), and
it is marked ``slow`` so the fast/default tiers (``-m "not slow"``) exclude it.
Rendering uses ``nbsphinx_execute = "never"``, so the sample notebook's cell is
rendered but **not executed** — no need to install the scaffolded package.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

pytest.importorskip("sphinx")
pytest.importorskip("nbsphinx")
pytest.importorskip("jupytext")

from pyclawd.commands.new import _new_project


@pytest.mark.slow
def test_scaffolded_docs_builds_html(tmp_path, monkeypatch):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc not installed — nbsphinx cannot render")

    monkeypatch.chdir(tmp_path)
    _new_project(
        name="docbuild",
        force=False,
        pkg=None,
        author="A Dev",
        email="a@b.c",
        docs=True,
        no_agent=True,
        no_skills=True,
    )
    root = tmp_path / "docbuild"
    cli = root / "docs" / "cli.py"
    assert cli.is_file()

    def run(*verb: str, timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(cli), *verb],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    # compile: .md -> .ipynb (jupytext, no execution).
    r_compile = run("compile", timeout=120)
    assert r_compile.returncode == 0, f"compile failed:\n{r_compile.stdout}\n{r_compile.stderr}"
    assert (root / "docs" / "source" / "example.ipynb").is_file()

    # build: render HTML (sphinx + nbsphinx). The runner chdir's into docs/.
    r_build = run("build", timeout=300)
    assert r_build.returncode == 0, f"build failed:\n{r_build.stdout}\n{r_build.stderr}"

    html = root / "docs" / "build" / "html"
    assert (html / "index.html").is_file(), "no index.html produced"
    assert (html / "example.html").is_file(), "the executed example page did not render"
    # The page actually rendered the source notebook's code.
    assert "import docbuild" in (html / "example.html").read_text()
