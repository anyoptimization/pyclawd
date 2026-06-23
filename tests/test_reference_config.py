"""Guard: the documented reference config (``examples/config.reference.py``) must
stay a valid, loadable :class:`pyclawd.Project`.

This is a doc-rot guard — if the config surface changes in a way that breaks the
worked example we ship, this test fails instead of users discovering it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyclawd import DocsConfig, Project, QualityConfig, discovery, load_project

REFERENCE = Path(__file__).resolve().parent.parent / "examples" / "config.reference.py"


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    monkeypatch.setattr(discovery, "_CACHE", {})
    monkeypatch.setattr(discovery, "_OVERRIDE", None)


def test_reference_example_exists():
    assert REFERENCE.is_file(), "the documented reference config went missing"


def test_reference_example_loads_as_a_valid_project():
    project = load_project(config=REFERENCE)
    assert isinstance(project, Project)
    assert project.name == "acme"
    # It exercises the full surface — the powerful, easy-to-miss knobs:
    assert isinstance(project.docs, DocsConfig)
    assert isinstance(project.quality, QualityConfig)
    assert project.compile_cmd  # has a build step
    assert project.clean_ext_globs  # has a --ext clean
    assert callable(project.extra_doctor_checks)  # custom doctor hook
    # 5-tier markers incl. the integration suites.
    assert set(project.test.markers) == {"default", "fast", "all", "examples", "docs"}
    assert project.test.integration_files
