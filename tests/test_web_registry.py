"""Unit tests for the dashboard project registry (:mod:`pyclawd.web.registry`).

The registry is bound to a JSON config file, so these point it at ``tmp_path`` and
build fake git repos (a bare ``.git`` directory is enough for discovery) under a
scratch root. No network, no real git.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyclawd.web.registry import Registry


def _make_repo(parent: Path, name: str) -> Path:
    """Create ``parent/name`` looking like a git repo (has a ``.git`` dir)."""
    repo = parent / name
    (repo / ".git").mkdir(parents=True)
    return repo


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Registry:
    """A registry backed by a config file under *tmp_path*.

    ``HOME`` is redirected into *tmp_path* so the default ``~/workspace`` discovery
    root resolves to an empty (nonexistent) directory — discovery then only sees
    repos a test explicitly creates under a root it sets.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return Registry(config_path=tmp_path / "web.json")


def test_discovers_repos_under_roots(registry: Registry, tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _make_repo(root, "alpha")
    _make_repo(root, "beta")
    (root / "not-a-repo").mkdir()  # no .git → ignored
    registry.set_roots([str(root)])

    projects = registry.projects()
    assert set(projects) == {"alpha", "beta"}
    assert all(p.discovered for p in projects.values())


def test_add_registers_project_outside_roots(registry: Registry, tmp_path: Path) -> None:
    elsewhere = _make_repo(tmp_path / "other", "gamma")
    registry.set_roots([str(tmp_path / "workspace")])  # gamma is not under it

    name = registry.add(str(elsewhere))
    assert name == "gamma"
    entry = registry.projects()["gamma"]
    assert entry.path == str(elsewhere.resolve())
    assert not entry.discovered


def test_add_honours_custom_name(registry: Registry, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "repo")
    assert registry.add(str(repo), name="custom") == "custom"
    assert "custom" in registry.projects()


def test_remove_unregisters(registry: Registry, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "repo")
    registry.add(str(repo))
    assert registry.remove("repo") is True
    assert registry.remove("repo") is False  # already gone


def test_star_persists_for_discovered_project(registry: Registry, tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _make_repo(root, "alpha")
    registry.set_roots([str(root)])

    registry.set_star("alpha", True)
    assert registry.projects()["alpha"].starred is True
    registry.set_star("alpha", False)
    assert registry.projects()["alpha"].starred is False


def test_resolve_returns_path_then_none(registry: Registry, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "repo")
    registry.add(str(repo))
    assert registry.resolve("repo") == str(repo.resolve())
    assert registry.resolve("missing") is None
    assert registry.resolve(None) is None


def test_corrupt_config_is_tolerated(registry: Registry) -> None:
    registry.config_path.write_text("{ not json")
    assert registry.projects() == {}  # falls back to empty, no crash


def test_star_for_vanished_project_is_skipped(registry: Registry, tmp_path: Path) -> None:
    registry.set_roots([str(tmp_path / "empty")])
    # Hand-write a star for a project with no path and no discovery.
    registry.config_path.write_text('{"projects": {"ghost": {"starred": true}}}')
    assert "ghost" not in registry.projects()
