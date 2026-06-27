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

from pyclawd import skills_install as skills_install_mod
from pyclawd.commands import new as new_mod
from pyclawd.commands import skills as skills_mod
from pyclawd.commands.new import (
    _adopt,
    _detect_package,
    _infer_root_markers,
    _new_project,
    _render,
    _render_config,
    _scaffold_pyproject,
)


@pytest.fixture(autouse=True)
def user_skills(tmp_path, monkeypatch):
    """Redirect the user-scope skills dir to a tmp dir (no test touches real ~/.claude)."""
    dest = tmp_path / "home" / ".claude" / "skills"
    # install_skills() lives in pyclawd.skills_install and resolves user_skills_dir()
    # from that module's namespace; commands.skills/commands.new only hold re-exported
    # bindings. Patch all three so no test touches the real ~/.claude.
    monkeypatch.setattr(skills_install_mod, "user_skills_dir", lambda: dest)
    monkeypatch.setattr(skills_mod, "user_skills_dir", lambda: dest)
    monkeypatch.setattr(new_mod, "user_skills_dir", lambda: dest)
    return dest


def test_interactive_requires_a_tty_and_no_yes(monkeypatch):
    # A human at a terminal (TTY, no --yes) gets prompts...
    monkeypatch.setattr(new_mod.sys.stdin, "isatty", lambda: True)
    assert new_mod._interactive(yes=False) is True
    assert new_mod._interactive(yes=True) is False  # --yes always wins
    # ...an agent / CI / pipe (no TTY) never prompts → uses flags + defaults.
    monkeypatch.setattr(new_mod.sys.stdin, "isatty", lambda: False)
    assert new_mod._interactive(yes=False) is False


def test_new_project_dry_run_writes_nothing(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(
        name="previewed",
        force=False,
        pkg=None,
        author="A",
        email="a@b.c",
        docs=True,
        compile_step=True,
        dry_run=True,
    )
    assert not (tmp_path / "previewed").exists()  # nothing written
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "docs/ runner" in out  # the plan lists the chosen components
    assert "build/compile step" in out


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
    assert "line-length = 100" in pyproject  # scaffolded default
    # No unrendered placeholders leak into output.
    assert "{{" not in pyproject
    assert "{{" not in (root / "LICENSE").read_text()


def test_new_project_with_docs_scaffolds_a_working_runner(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(
        name="withdocs",
        force=False,
        pkg=None,
        author="A Dev",
        email="a@b.c",
        docs=True,
        no_agent=True,
        no_skills=True,
    )
    root = tmp_path / "withdocs"
    for rel in (
        "docs/cli.py",
        "docs/pyproject.toml",
        "docs/source/conf.py",
        "docs/source/index.rst",
        "docs/source/example.md",
    ):
        assert (root / rel).is_file(), f"missing scaffolded docs file: {rel}"
    cfg = (root / ".pyclawd" / "config.py").read_text()
    assert "docs=DocsConfig(" in cfg
    assert 'runner=["python", "docs/cli.py"]' in cfg  # python-in-env default
    # The docs project's console script is named <pkg>-docs (for the uvx alternative).
    docs_pyproject = (root / "docs" / "pyproject.toml").read_text()
    assert "withdocs-docs" in docs_pyproject
    # Templates fully rendered — no leaked placeholders.
    assert "{{" not in docs_pyproject
    assert "{{" not in (root / "docs" / "source" / "example.md").read_text()


def test_new_project_without_docs_has_no_docs_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="nodocs", force=False, pkg=None, author="A", email="a@b.c", no_skills=True)
    assert not (tmp_path / "nodocs" / "docs").exists()


def test_new_project_pkg_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="my-proj", force=False, pkg="myproj", author="A", email="a@b.c")
    assert (tmp_path / "my-proj" / "src" / "myproj" / "__init__.py").is_file()


def test_new_project_lands_agent_readiness(tmp_path: Path, monkeypatch, user_skills) -> None:
    monkeypatch.chdir(tmp_path)
    _new_project(name="agentic", force=False, pkg=None, author="A Dev", email="a@b.c")

    root = tmp_path / "agentic"
    # AGENTS.md + CLAUDE.md are written and tailored to the project.
    agents = root / "AGENTS.md"
    assert agents.is_file()
    assert "working in agentic" in agents.read_text()
    assert (root / "CLAUDE.md").read_text().strip() == "@AGENTS.md"

    # Skills install to USER scope, not vendored into the repo.
    assert not (root / ".claude" / "skills").exists()
    for name in ("pyclawd", "pyclawd-adopt", "pyclawd-doctor", "pyclawd-golden", "pyclawd-upgrade"):
        assert (user_skills / name / "SKILL.md").is_file(), f"missing installed skill: {name}"


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


def test_adopt_yes_lands_agent_readiness(tmp_path: Path, monkeypatch, user_skills) -> None:
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
    # Skills land in user scope, not the adopted repo.
    assert not (tmp_path / ".claude" / "skills").exists()
    assert (user_skills / "pyclawd-doctor" / "SKILL.md").is_file()


def test_adopt_does_not_clobber_existing_agents_md(
    tmp_path: Path, monkeypatch, user_skills
) -> None:
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
    # Skills still get installed — to user scope.
    assert (user_skills / "pyclawd-golden" / "SKILL.md").is_file()


def test_render_config_basic_shape() -> None:
    text = _render_config(
        name="demo", pkg="demo", conda_env=None, tests_dir="tests/", docs=False, compile_step=False
    )
    assert "project = Project(" in text
    assert "name='demo'" in text
    assert "conda_env=None" in text
    assert "QualityConfig(" in text and "TestConfig(" in text
    # The scaffold stamps the pyclawd version it was built on (for the compat check).
    import pyclawd

    assert f"pyclawd_version={pyclawd.__version__!r}" in text
    # The generated check gate enforces the file-description code-map doctrine.
    assert 'check_sequence=["format-check", "lint", "typecheck", "descriptions", "test"]' in text
    # No optional blocks when docs/compile are off.
    assert "DocsConfig" not in text
    assert "BuildConfig" not in text
    assert "compile_cmd" not in text


def test_render_config_with_docs_and_compile() -> None:
    text = _render_config(
        name="d", pkg="d", conda_env="myenv", tests_dir="tests/", docs=True, compile_step=True
    )
    assert "DocsConfig" in text
    assert "conda_env='myenv'" in text
    # The build pipeline is grouped into a BuildConfig reached via Project.build.
    assert "build=BuildConfig(" in text
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


# --------------------------------------------------------------------------- #
# Layout / marker detection (ADOPT).
# --------------------------------------------------------------------------- #


def test_detect_package_src_layout(tmp_path: Path) -> None:
    (tmp_path / "src" / "foo").mkdir(parents=True)
    (tmp_path / "src" / "foo" / "__init__.py").write_text("")
    assert _detect_package(tmp_path) == ("src", "foo")


def test_detect_package_flat_layout(tmp_path: Path) -> None:
    (tmp_path / "bar").mkdir()
    (tmp_path / "bar" / "__init__.py").write_text("")
    assert _detect_package(tmp_path) == ("bar", "bar")


def test_detect_package_ignores_non_pkg_dirs(tmp_path: Path) -> None:
    # tests/docs/.git all have __init__.py but must never be picked as the package.
    for d in ("tests", "docs", ".git"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "__init__.py").write_text("")
    (tmp_path / "realpkg").mkdir()
    (tmp_path / "realpkg" / "__init__.py").write_text("")
    assert _detect_package(tmp_path) == ("realpkg", "realpkg")


def test_detect_package_fallback_when_no_package(tmp_path: Path) -> None:
    assert _detect_package(tmp_path) == ("src", "src")
    assert _detect_package(tmp_path, hint="myhint") == ("src", "myhint")


def test_detect_package_hint_disambiguates(tmp_path: Path) -> None:
    for name in ("aaa", "zzz"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "__init__.py").write_text("")
    # Without a hint the first sorted candidate wins; the hint overrides it.
    assert _detect_package(tmp_path) == ("aaa", "aaa")
    assert _detect_package(tmp_path, hint="zzz") == ("zzz", "zzz")


def test_infer_root_markers_legacy_no_pyproject(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("")
    (tmp_path / "pysamoo").mkdir()
    (tmp_path / "pysamoo" / "__init__.py").write_text("")
    markers = _infer_root_markers(tmp_path, "pysamoo", "pysamoo")
    assert "setup.py" in markers
    assert "pysamoo/__init__.py" in markers
    assert "pyproject.toml" not in markers


def test_infer_root_markers_with_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "src" / "foo").mkdir(parents=True)
    (tmp_path / "src" / "foo" / "__init__.py").write_text("")
    markers = _infer_root_markers(tmp_path, "src", "foo")
    assert "pyproject.toml" in markers
    assert "src/foo/__init__.py" in markers


def test_infer_root_markers_always_nonempty(tmp_path: Path) -> None:
    # No markers and no package init exist → falls back to pyproject.toml.
    assert _infer_root_markers(tmp_path, "src", "nope") == ["pyproject.toml"]


# --------------------------------------------------------------------------- #
# ADOPT on a flat / legacy repo (the pysamoo case).
# --------------------------------------------------------------------------- #


def test_adopt_legacy_flat_repo(tmp_path: Path, monkeypatch, capsys, user_skills) -> None:
    monkeypatch.chdir(tmp_path)
    # Fabricate a flat/legacy repo: package dir at root, setup.py, NO pyproject.toml.
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
    (tmp_path / "pysamoo").mkdir()
    (tmp_path / "pysamoo" / "__init__.py").write_text("")

    _adopt(
        force=False,
        name="pysamoo",
        pkg=None,
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
        no_agent=True,
        no_skills=True,
    )

    cfg = (tmp_path / ".pyclawd" / "config.py").read_text()
    # Flat layout is reflected — NOT the hardcoded src/pyproject defaults.
    assert 'src_dir="pysamoo"' in cfg
    assert '"setup.py"' in cfg
    assert '"pysamoo/__init__.py"' in cfg

    out = capsys.readouterr().out
    assert "Phase-0 readiness" in out
    assert "flat" in out
    assert "no pyproject.toml" in out


def test_adopt_dry_run_reports_phase0(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "setup.py").write_text("")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "__init__.py").write_text("")
    _adopt(
        force=False,
        name="legacy",
        pkg=None,
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
        dry_run=True,
    )
    # dry-run writes nothing but still reports detected layout + readiness.
    assert not (tmp_path / ".pyclawd").exists()
    out = capsys.readouterr().out
    assert "Phase-0 readiness" in out
    assert "src_dir='legacy'" in out
    assert "no pyproject.toml" in out


# --------------------------------------------------------------------------- #
# --scaffold-pyproject (opt-in starter config).
# --------------------------------------------------------------------------- #


def test_scaffold_pyproject_creates_when_absent(tmp_path: Path) -> None:
    added, skipped = _scaffold_pyproject(tmp_path, src_dir="pysamoo")
    pp = tmp_path / "pyproject.toml"
    assert pp.is_file()
    text = pp.read_text()
    assert "[tool.ruff]" in text
    assert "line-length = 100" in text
    assert "[tool.ruff.lint.pydocstyle]" in text
    assert 'convention = "google"' in text
    assert "[tool.mypy]" in text
    assert 'files = ["pysamoo"]' in text
    assert "[tool.pytest.ini_options]" in text
    assert "golden:" in text
    assert set(added) == {"[tool.ruff]", "[tool.mypy]", "[tool.pytest.ini_options]"}
    assert skipped == []


def test_scaffold_pyproject_does_not_clobber_existing_sections(tmp_path: Path) -> None:
    pp = tmp_path / "pyproject.toml"
    pp.write_text(
        "[tool.ruff]\nline-length = 88  # KEEP MINE\n",
        encoding="utf-8",
    )
    added, skipped = _scaffold_pyproject(tmp_path, src_dir="src")
    text = pp.read_text()
    # Existing ruff section is preserved verbatim...
    assert "line-length = 88  # KEEP MINE" in text
    # ...and is NOT duplicated.
    assert text.count("[tool.ruff]") == 1
    # Only the missing sections were appended.
    assert "[tool.ruff]" in skipped
    assert set(added) == {"[tool.mypy]", "[tool.pytest.ini_options]"}
    assert "[tool.mypy]" in text


def test_adopt_scaffold_pyproject_flag_makes_gate_ready(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "setup.py").write_text("")
    (tmp_path / "pkgx").mkdir()
    (tmp_path / "pkgx" / "__init__.py").write_text("")
    _adopt(
        force=False,
        name="pkgx",
        pkg=None,
        conda_env="",
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        yes=True,
        no_agent=True,
        no_skills=True,
        scaffold_pyproject=True,
    )
    assert (tmp_path / "pyproject.toml").is_file()
    out = capsys.readouterr().out
    assert "scaffolded pyproject.toml" in out
    # After scaffolding, the Phase-0 report should declare the gate runnable.
    assert "gate is runnable" in out


# --------------------------------------------------------------------------- #
# Guardrail: new-project _render_config output is unchanged.
# --------------------------------------------------------------------------- #


def test_render_config_new_project_defaults_unchanged() -> None:
    # The new-project path passes neither src_dir nor root_markers → the historical
    # hardcoded values must still appear (keeps the golden dogfood baseline stable).
    text = _render_config(
        name="demo", pkg="demo", conda_env=None, tests_dir="tests/", docs=False, compile_step=False
    )
    assert '    src_dir="src",\n' in text
    assert '    root_markers=["pyproject.toml"],\n' in text


def test_render_config_adopt_values_render(tmp_path: Path) -> None:
    text = _render_config(
        name="pysamoo",
        pkg="pysamoo",
        conda_env=None,
        tests_dir="tests/",
        docs=False,
        compile_step=False,
        src_dir="pysamoo",
        root_markers=["setup.py", "pysamoo/__init__.py"],
    )
    assert '    src_dir="pysamoo",\n' in text
    assert '    root_markers=["setup.py", "pysamoo/__init__.py"],\n' in text
