"""Unit tests for the generic pyclawd core (config model + loader).

These exercise only the project-agnostic toolkit in ``pyclawd`` — never pymoo — so
they double as the reference for adopters.

Run them (from the repo root) with::

    pyclawd python -m pytest .claude/tests -c .claude/tests/pytest.ini

The dedicated ``-c`` config keeps these tests from inheriting pymoo's root
``pytest.ini`` (``--strict-markers`` + project markers).
"""

from __future__ import annotations

import dataclasses
import textwrap
from pathlib import Path

import pytest

from pyclawd import (
    DocsConfig,
    DoctorConfig,
    Project,
    TestConfig,
    find_config_file,
    load_project,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def make_project(name: str = "demo") -> Project:
    """Build a minimal, valid Project using only the generic toolkit."""
    return Project(
        name=name,
        conda_env=None,
        root_markers=["pyproject.toml"],
        compile_cmd=["setup.py", "build_ext", "--inplace"],
        dist_cmd=["setup.py", "sdist"],
        clean_targets=["build", "dist"],
        clean_ext_dir="src/_compiled",
        clean_ext_globs=["*.so"],
        docs=DocsConfig(
            runner=["uvx", "--from", "./docs", "mydocs"],
            source_dir="docs/source",
            cache_dir="docs/.jupyter_cache",
            cache_db="docs/.jupyter_cache/global.db",
            build_html="docs/build/html",
            branch="main",
        ),
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=["tests/test_examples.py"],
            markers={"default": "not long", "fast": "not long and not slow"},
        ),
        doctor=DoctorConfig(
            core_deps=["numpy"],
            dev_deps=["pytest"],
            tool_files=["tools/python"],
            binaries=[("pandoc", "install pandoc")],
        ),
    )


def write_config(dir_path: Path, *, name: str = "demo", body: str | None = None) -> Path:
    """Write a ``.pyclawd/config.py`` under *dir_path* and return the repo root."""
    pyclawd_dir = dir_path / ".pyclawd"
    pyclawd_dir.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = textwrap.dedent(
            f"""
            from pyclawd import (
                DocsConfig, DoctorConfig, Project, TestConfig,
            )

            project = Project(
                name={name!r},
                conda_env=None,
                root_markers=["pyproject.toml"],
                compile_cmd=["setup.py", "build_ext", "--inplace"],
                dist_cmd=["setup.py", "sdist"],
                clean_targets=["build", "dist"],
                clean_ext_dir="src/_compiled",
                clean_ext_globs=["*.so"],
                docs=DocsConfig(
                    runner=["uvx", "--from", "./docs", "mydocs"],
                    source_dir="docs/source",
                    cache_dir="docs/.jupyter_cache",
                    cache_db="docs/.jupyter_cache/global.db",
                    build_html="docs/build/html",
                    branch="main",
                ),
                test=TestConfig(
                    tests_dir="tests/",
                    classname_prefix="tests.",
                    integration_files=[],
                    markers={{"default": "not long"}},
                ),
                doctor=DoctorConfig(
                    core_deps=["numpy"],
                    dev_deps=["pytest"],
                    tool_files=[],
                    binaries=[],
                ),
            )
            """
        )
    (pyclawd_dir / "config.py").write_text(body)
    return dir_path


# --------------------------------------------------------------------------- #
# Construction + immutability
# --------------------------------------------------------------------------- #


def test_project_and_nested_configs_construct():
    proj = make_project()
    assert proj.name == "demo"
    assert isinstance(proj.docs, DocsConfig)
    assert isinstance(proj.test, TestConfig)
    assert isinstance(proj.doctor, DoctorConfig)
    assert proj.root is None
    assert proj.extra_doctor_checks is None


def test_project_is_frozen():
    proj = make_project()
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.name = "other"  # type: ignore[misc]


def test_nested_configs_are_frozen():
    proj = make_project()
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.docs.branch = "dev"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.test.tests_dir = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        proj.doctor.core_deps = []  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Project.path
# --------------------------------------------------------------------------- #


def test_path_raises_when_root_unset():
    proj = make_project()
    with pytest.raises(ValueError):
        proj.path("a", "b")


def test_path_joins_when_root_set(tmp_path):
    proj = dataclasses.replace(make_project(), root=tmp_path)
    assert proj.path("a", "b") == tmp_path / "a" / "b"
    assert proj.path() == tmp_path


# --------------------------------------------------------------------------- #
# find_config_file
# --------------------------------------------------------------------------- #


def test_find_config_walks_up_parents(tmp_path):
    root = write_config(tmp_path)
    nested = root / "src" / "pkg" / "deep"
    nested.mkdir(parents=True)
    found = find_config_file(nested)
    assert found == (root / ".pyclawd" / "config.py").resolve()


def test_find_config_returns_none_when_absent(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_config_file(nested) is None


# --------------------------------------------------------------------------- #
# load_project
# --------------------------------------------------------------------------- #


def test_load_project_sets_root_and_returns_project(tmp_path):
    root = write_config(tmp_path, name="loaded")
    nested = root / "deep" / "dir"
    nested.mkdir(parents=True)
    proj = load_project(nested)
    assert isinstance(proj, Project)
    assert proj.name == "loaded"
    # root is the dir CONTAINING `.pyclawd/`.
    assert proj.root == root.resolve()


def test_load_project_caches_by_path(tmp_path):
    write_config(tmp_path)
    first = load_project(tmp_path)
    second = load_project(tmp_path)
    assert first is second


def test_load_project_none_when_no_config(tmp_path):
    assert load_project(tmp_path) is None


def test_load_project_missing_project_raises(tmp_path):
    write_config(tmp_path, body="x = 1\n")
    with pytest.raises(TypeError):
        load_project(tmp_path)


def test_load_project_wrong_type_raises(tmp_path):
    write_config(tmp_path, body="project = 'not a Project'\n")
    with pytest.raises(TypeError):
        load_project(tmp_path)
