"""Unit tests for the ``pyclawd new`` scaffolder (:mod:`pyclawd.commands.new`).

These exercise the scaffolder against a temporary directory — no network, no
installed project required — and double as the contract for what a freshly
scaffolded project looks like.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from pyclawd.commands.new import _adopt, _new_project, _render, _render_config


def test_render_substitutes_known_keys_and_leaves_others() -> None:
    out = _render("hi {{name}} ${{ matrix.x }}", {"name": "demo"})
    # Known placeholder replaced; the GitHub-Actions-style span is untouched.
    assert out == "hi demo ${{ matrix.x }}"


def test_new_project_creates_expected_tree(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="myproj", force=False, pkg=None, author="A Dev", email="a@b.c")

    root = tmp_path / "myproj"
    expected = [
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        ".gitignore",
        ".python-version",
        ".github/workflows/ci.yml",
        "src/myproj/__init__.py",
        "src/myproj/py.typed",
        "tests/test_smoke.py",
        ".pyclawd/config.py",
    ]
    for rel in expected:
        assert (root / rel).is_file(), f"missing scaffolded file: {rel}"

    # __version__ is rendered and the package name is substituted everywhere.
    assert '__version__ = "0.0.1"' in (root / "src/myproj/__init__.py").read_text()
    assert "import myproj" in (root / "tests/test_smoke.py").read_text()
    pyproject = (root / "pyproject.toml").read_text()
    assert 'name = "myproj"' in pyproject
    assert 'packages = ["src/myproj"]' in pyproject
    # No unrendered placeholders leak into output.
    assert "{{" not in pyproject
    assert "{{" not in (root / "LICENSE").read_text()


def test_new_project_pkg_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="my-proj", force=False, pkg="myproj", author="A", email="a@b.c")
    assert (tmp_path / "my-proj" / "src" / "myproj" / "__init__.py").is_file()


def test_new_project_lands_agent_readiness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="agentic", force=False, pkg=None, author="A Dev", email="a@b.c")

    root = tmp_path / "agentic"
    # AGENTS.md + CLAUDE.md are written and tailored to the project.
    agents = root / "AGENTS.md"
    assert agents.is_file()
    assert "working in agentic" in agents.read_text()
    assert (root / "CLAUDE.md").read_text().strip() == "@AGENTS.md"

    # The bundled skills are auto-installed into .claude/skills/.
    skills_dir = root / ".claude" / "skills"
    for name in ("pyclawd-doctor", "pyclawd-tests", "pyclawd-quality", "pyclawd-docs"):
        assert (skills_dir / name / "SKILL.md").is_file(), f"missing installed skill: {name}"


def test_new_project_opt_out_of_agent_readiness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(
        name="bare",
        force=False,
        pkg=None,
        author="A",
        email="a@b.c",
        no_agent=True,
        no_skills=True,
    )
    root = tmp_path / "bare"
    assert not (root / "AGENTS.md").exists()
    assert not (root / "CLAUDE.md").exists()
    assert not (root / ".claude").exists()
    # The core skeleton is still scaffolded.
    assert (root / "pyproject.toml").is_file()


def test_adopt_yes_lands_agent_readiness(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _adopt(
        force=False,
        name="adopted",
        pkg="adopted",
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
    )
    assert (tmp_path / "AGENTS.md").is_file()
    assert (tmp_path / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
    assert (tmp_path / ".claude" / "skills" / "pyclawd-doctor" / "SKILL.md").is_file()


def test_adopt_does_not_clobber_existing_agents_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("KEEP ME", encoding="utf-8")
    _adopt(
        force=False,
        name="adopted",
        pkg="adopted",
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
    )
    # Existing agent doc is preserved untouched.
    assert (tmp_path / "AGENTS.md").read_text() == "KEEP ME"
    # Skills still get installed.
    assert (tmp_path / ".claude" / "skills" / "pyclawd-tests" / "SKILL.md").is_file()


def test_render_config_basic_shape() -> None:
    text = _render_config(
        name="demo", pkg="demo", conda_env=None, tests_dir="tests/", docs=False, compile_step=False
    )
    assert "project = Project(" in text
    assert "name='demo'" in text
    assert "conda_env=None" in text
    assert "QualityConfig(" in text and "TestConfig(" in text
    # No optional blocks when docs/compile are off.
    assert "DocsConfig" not in text
    assert "compile_cmd" not in text


def test_render_config_with_docs_and_compile() -> None:
    text = _render_config(
        name="d", pkg="d", conda_env="myenv", tests_dir="tests/", docs=True, compile_step=True
    )
    assert "from pyclawd import DocsConfig" in text
    assert "conda_env='myenv'" in text
    assert "compile_cmd=" in text
    assert "docs=DocsConfig(" in text


def test_adopt_writes_config_and_refuses_overwrite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _adopt(
        force=False,
        name="adopted",
        pkg="adopted",
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
    )
    config = tmp_path / ".pyclawd" / "config.py"
    assert config.is_file()
    assert "name='adopted'" in config.read_text()

    # A second run without --force must refuse.
    with pytest.raises(typer.Exit):
        _adopt(
            force=False,
            name="adopted",
            pkg="adopted",
            conda_env="",
            tests_dir="tests/",
            docs=False,
            compile_step=False,
            yes=True,
        )
