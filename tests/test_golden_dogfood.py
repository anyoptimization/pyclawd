"""Dogfood golden tests — lock real pyclawd behavior against accidental drift.

pyclawd dogfoods its own behavior oracle. These ``@pytest.mark.golden`` tests
``return`` a fully deterministic value that the golden plugin snapshots to a committed
baseline:

- the rendered ``.pyclawd/config.py`` text from
  :func:`pyclawd.commands.new._render_config` for a FIXED set of inputs (locks the
  scaffold output a fresh ``pyclawd new`` produces), and
- the resolved test-tier marker mapping for a fixed :class:`~pyclawd.TestConfig`
  (locks the ``fast`` / ``default`` / ``all`` tier semantics).

Both values are deterministic — no tmp paths, no timestamps, no dict-ordering
nondeterminism (the marker mapping is sorted). They are marked ``golden`` so they are
collected by ``pyclawd golden`` and EXCLUDED from the unit tiers (the dogfood markers
say ``not golden``). A plain, non-golden sanity test asserts the captured values are
stable across repeated calls so the snapshot itself can never flake.
"""

from __future__ import annotations

import pytest

from pyclawd import Project, TestConfig
from pyclawd.commands.new import _render_config
from pyclawd.project import DoctorConfig
from pyclawd.tests import tier_markers

# Fixed inputs for the scaffolded config — no environment-derived values, so the
# rendered text is identical on every machine (the pyclawd version is the only
# moving part, and a version bump is an *intended* change a human re-blesses).
_SCAFFOLD_KWARGS = {
    "name": "acme-tool",
    "pkg": "acme_tool",
    "conda_env": None,
    "tests_dir": "tests/",
    "docs": False,
    "compile_step": False,
}


def _tier_map() -> dict[str, str]:
    """Resolve pyclawd's documented tier markers from a fixed TestConfig (sorted)."""
    project = Project(
        name="demo",
        conda_env=None,
        root_markers=["pyproject.toml"],
        test=TestConfig(
            tests_dir="tests/",
            classname_prefix="tests.",
            integration_files=[],
            markers={
                "fast": "not slow and not integration and not golden",
                "default": "not slow and not golden",
                "all": "not golden",
            },
        ),
        doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),
    )
    return {tier: tier_markers(project, tier) for tier in sorted(project.test.markers)}


@pytest.mark.golden
def test_scaffold_config_render() -> None:
    """Snapshot the rendered scaffold config text for fixed inputs."""
    return _render_config(**_SCAFFOLD_KWARGS)


@pytest.mark.golden
def test_tier_marker_mapping() -> None:
    """Snapshot the resolved fast/default/all tier marker expressions."""
    return _tier_map()


def test_dogfood_values_are_deterministic() -> None:
    """Non-golden sanity: the snapshotted values are stable across calls."""
    assert _render_config(**_SCAFFOLD_KWARGS) == _render_config(**_SCAFFOLD_KWARGS)
    assert _tier_map() == _tier_map()
    # The render is meaningful — it really is a config module body.
    assert "project = Project(" in _render_config(**_SCAFFOLD_KWARGS)
    assert _tier_map()["all"] == "not golden"
