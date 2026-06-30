"""Integration tests for the dashboard's FastAPI app (:mod:`pyclawd.web.app`).

These need the optional ``[web]`` stack (FastAPI) and ``httpx`` (FastAPI's
``TestClient``); the whole module skips cleanly when they are absent, so the base
suite stays green without the extra installed. The app is driven against a scratch
git repo registered in a ``tmp_path`` registry — no network, no real ``~/.pyclawd``.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from pyclawd.web.app import _token_stream, create_app
from pyclawd.web.git import WORKING_TREE, GitRepo
from pyclawd.web.registry import Registry


def _git(repo: Path, *args: str) -> None:
    """Run a git command in *repo*, raising on failure."""
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient over an app serving one scratch repo named ``demo``."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo = tmp_path / "demo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "tester")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("line1\nline2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")

    registry = Registry(config_path=tmp_path / "web.json")
    registry.add(str(repo))
    return TestClient(create_app(default_project="demo", registry=registry))


def test_projects_lists_with_status(client: TestClient) -> None:
    body = client.get("/api/projects").json()
    assert body["default"] == "demo"
    (demo,) = body["projects"]
    assert demo["name"] == "demo"
    assert demo["branch"] in {"main", "master"}
    assert demo["dirty"] == 0


def test_changes_reports_edits(client: TestClient) -> None:
    path = client.get("/api/projects").json()["projects"][0]["path"]
    (Path(path) / "a.txt").write_text("line1\nCHANGED\n")
    body = client.get("/api/changes", params={"project": "demo"}).json()
    assert body["base"] == "HEAD" and body["target"] == WORKING_TREE
    (changed,) = [f for f in body["files"] if f["path"] == "a.txt"]
    assert changed["status"] == "M"
    assert "token" in body


def test_diff_returns_hunks(client: TestClient) -> None:
    path = client.get("/api/projects").json()["projects"][0]["path"]
    (Path(path) / "a.txt").write_text("line1\nCHANGED\n")
    view = client.get("/api/diff", params={"project": "demo", "path": "a.txt"}).json()
    assert view["mode"] == "diff" and not view["binary"]
    kinds = [ln["kind"] for h in view["hunks"] for ln in h["lines"]]
    assert "add" in kinds and "del" in kinds


def test_diff_rejects_path_traversal(client: TestClient) -> None:
    r = client.get("/api/diff", params={"project": "demo", "path": "../../etc/passwd"})
    assert r.status_code == 400


def test_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/api/changes", params={"project": "ghost"}).status_code == 404


def test_spa_serves_shell_for_project_path(client: TestClient) -> None:
    # ``/<project>`` (and any non-API client route) must serve the SPA shell so a
    # reload or shared link lands back in the app, not on a 404.
    r = client.get("/demo")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    deep = client.get("/some/deep/client/route")
    assert deep.status_code == 200
    assert "text/html" in deep.headers["content-type"]


def test_spa_does_not_mask_unknown_api(client: TestClient) -> None:
    # An unmatched /api/* path stays a real 404 rather than returning the shell.
    assert client.get("/api/does-not-exist").status_code == 404


def test_refs_and_files(client: TestClient) -> None:
    refs = client.get("/api/refs", params={"project": "demo"}).json()
    assert refs["current"] in {"main", "master"}
    files = client.get("/api/files", params={"project": "demo"}).json()["files"]
    assert files == ["a.txt"]


def test_state_token_endpoint(client: TestClient) -> None:
    assert client.get("/api/state", params={"project": "demo"}).json()["token"]


def test_star_add_remove_roundtrip(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/api/projects/star", json={"name": "demo", "starred": True}).json()["ok"]
    assert client.get("/api/projects").json()["projects"][0]["starred"] is True

    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    added = client.post("/api/projects/add", json={"path": str(other)}).json()
    assert added["name"] == "other"
    assert client.post("/api/projects/remove", json={"name": "other"}).json()["ok"] is True


def test_add_rejects_non_repo(client: TestClient, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert client.post("/api/projects/add", json={"path": str(plain)}).status_code == 400


def test_config_roots_roundtrip(client: TestClient, tmp_path: Path) -> None:
    new_root = str(tmp_path / "ws")
    body = client.post("/api/config", json={"roots": [new_root]}).json()
    assert body["roots"] == [new_root]
    assert client.get("/api/config").json()["roots"] == [new_root]


def test_sessions_endpoint_returns_list(client: TestClient) -> None:
    # No tmux in the test env → empty list, but the endpoint must succeed.
    assert isinstance(client.get("/api/sessions").json()["sessions"], list)


def test_run_availability_reports_verbs(client: TestClient) -> None:
    body = client.get("/api/run", params={"project": "demo"}).json()
    assert "check" in body["verbs"]
    # The scratch repo has no .pyclawd/config.py.
    assert body["configured"] is False
    assert isinstance(body["pyclawd"], bool)


def test_run_rejects_unknown_verb(client: TestClient) -> None:
    r = client.post("/api/run", json={"project": "demo", "verb": "rm-rf"})
    assert r.status_code == 400


def test_agent_availability_endpoint(client: TestClient) -> None:
    assert isinstance(client.get("/api/agent").json()["available"], bool)


def test_event_stream_emits_initial_frame(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")

    async def first_frame() -> str:
        gen = _token_stream(GitRepo(root=repo), "HEAD", WORKING_TREE)
        try:
            return await gen.__anext__()
        finally:
            await gen.aclose()

    frame = asyncio.run(first_frame())
    assert frame.startswith("data: ") and "token" in frame
