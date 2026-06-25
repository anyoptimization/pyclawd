"""Unit tests for the ``PYCLAWD_DISCOVERY`` config-dir search path (:mod:`pyclawd.discovery`).

Cover the relative, per-cwd discovery that lets an **uncommitted** config live at
``<repo>/.local/.pyclawd/config.py`` while ``Project.root`` still resolves to the
repo — and the default (``.pyclawd`` only) staying byte-identical.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

from pathlib import Path

from pyclawd import discovery

_CONFIG_BODY = (
    "from pyclawd import Project, TestConfig, DoctorConfig\n"
    "project = Project(\n"
    "    name={name!r}, conda_env=None, root_markers=[],\n"
    "    test=TestConfig(tests_dir='tests/', classname_prefix='tests.',\n"
    "                    integration_files=[], markers={{'default': ''}}),\n"
    "    doctor=DoctorConfig(core_deps=[], dev_deps=[], tool_files=[], binaries=[]),\n"
    ")\n"
)


def _write(dir_path: Path, rel: str, name: str) -> Path:
    """Write a config at ``dir_path/rel/config.py`` and return the config file path."""
    cfg = dir_path / rel / "config.py"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(_CONFIG_BODY.format(name=name))
    return cfg


def _reset(monkeypatch) -> None:
    monkeypatch.setattr(discovery, "_CACHE", {})
    monkeypatch.setattr(discovery, "_OVERRIDE", None)
    monkeypatch.delenv(discovery.ENV_VAR, raising=False)


# --- _discovery_entries ------------------------------------------------------


def test_default_discovery_is_pyclawd_only(monkeypatch):
    monkeypatch.delenv(discovery.DISCOVERY_ENV, raising=False)
    assert discovery._discovery_entries() == [".pyclawd"]


def test_discovery_env_parses_pathsep_list(monkeypatch):
    import os

    monkeypatch.setenv(discovery.DISCOVERY_ENV, os.pathsep.join([".local/.pyclawd", ".pyclawd"]))
    assert discovery._discovery_entries() == [".local/.pyclawd", ".pyclawd"]


# --- walk-up + root for the uncommitted-local pattern ------------------------


def test_walkup_finds_local_pyclawd_and_root_is_repo(tmp_path, monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv(discovery.DISCOVERY_ENV, ".local/.pyclawd")
    repo = tmp_path / "repo"
    _write(repo, ".local/.pyclawd", "local_proj")
    nested = repo / "src" / "pkg"
    nested.mkdir(parents=True)

    proj = discovery.load_project(start=nested)
    assert proj is not None and proj.name == "local_proj"
    # root strips the whole `.local/.pyclawd` wrapper back to the repo.
    assert proj.root == repo.resolve()


def test_local_override_wins_over_committed(tmp_path, monkeypatch):
    import os

    _reset(monkeypatch)
    monkeypatch.setenv(discovery.DISCOVERY_ENV, os.pathsep.join([".local/.pyclawd", ".pyclawd"]))
    repo = tmp_path / "repo"
    _write(repo, ".pyclawd", "committed")
    _write(repo, ".local/.pyclawd", "local")

    proj = discovery.load_project(start=repo)
    assert proj is not None and proj.name == "local"  # first entry wins
    assert proj.root == repo.resolve()


def test_default_behavior_unchanged(tmp_path, monkeypatch):
    _reset(monkeypatch)
    monkeypatch.delenv(discovery.DISCOVERY_ENV, raising=False)
    repo = tmp_path / "repo"
    _write(repo, ".pyclawd", "plain")
    proj = discovery.load_project(start=repo)
    assert proj is not None and proj.name == "plain"
    assert proj.root == repo.resolve()


def test_explicit_dir_target_honors_search_path(tmp_path, monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv(discovery.DISCOVERY_ENV, ".local/.pyclawd")
    repo = tmp_path / "repo"
    _write(repo, ".local/.pyclawd", "via_dir")
    # Pointing --config at the repo dir resolves the local config + repo root.
    proj = discovery.load_project(config=repo)
    assert proj is not None and proj.name == "via_dir"
    assert proj.root == repo.resolve()


def test_root_for_strips_nested_entry(tmp_path, monkeypatch):
    monkeypatch.setenv(discovery.DISCOVERY_ENV, ".local/.pyclawd")
    cfg = tmp_path / "repo" / ".local" / ".pyclawd" / "config.py"
    assert discovery._root_for(cfg) == tmp_path / "repo"
