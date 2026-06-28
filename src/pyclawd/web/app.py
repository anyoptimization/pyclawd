"""The FastAPI application behind ``pyclawd web`` — REST + live SSE.

This is the only module in the package that imports the web stack (FastAPI,
``watchfiles``); it is reached lazily from the CLI so pyclawd's core install stays
``typer`` + ``rich``. It is a thin HTTP skin over the pure layers: it never
formats a diff or talks to git directly — it delegates to :mod:`pyclawd.web.git`,
:mod:`pyclawd.web.registry`, and :mod:`pyclawd.web.sessions`, then serialises the
typed value objects those return.

Live updates use Server-Sent Events backed by a filesystem watch
(:func:`watchfiles.awatch`): a client subscribes to ``/api/events`` for a given
comparison and is pushed the new :meth:`~pyclawd.web.git.GitRepo.state_token`
whenever either side moves. This replaces the old fixed-interval polling and — via
the content-aware token — reacts even to repeated edits of one already-modified
file (an agent iterating), which interval polling on ``git status`` missed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .git import WORKING_TREE, GitRepo, Ref
from .registry import Registry
from .sessions import list_panes, send_to_pane

#: Directory holding the built frontend (populated by the Vite build; may be absent
#: in a source checkout, in which case the SPA is simply not mounted).
_STATIC_DIR = Path(__file__).parent / "static"


# --------------------------------------------------------------------------- #
# Request bodies (responses reuse the git/registry dataclasses via FastAPI's encoder).
# --------------------------------------------------------------------------- #


class StarBody(BaseModel):
    """Body of ``POST /api/projects/star`` — pin or unpin a project."""

    name: str
    starred: bool = False


class AddBody(BaseModel):
    """Body of ``POST /api/projects/add`` — register a repo by path."""

    path: str
    name: str | None = None


class RemoveBody(BaseModel):
    """Body of ``POST /api/projects/remove`` — unregister a project by name."""

    name: str


class SendBody(BaseModel):
    """Body of ``POST /api/send`` — paste review text into a tmux pane."""

    target: str
    text: str
    submit: bool = False
    focus: bool = False


class ConfigBody(BaseModel):
    """Body of ``POST /api/config`` — replace the discovery roots."""

    roots: list[str]


class RunBody(BaseModel):
    """Body of ``POST /api/run`` — run a pyclawd verb in the project."""

    project: str
    verb: str


class AgentBody(BaseModel):
    """Body of ``POST /api/agent/run`` — dispatch a headless ``claude -p`` agent.

    ``full_access`` chooses the permission mode: ``True`` lets the agent run commands
    as well as edit files (``bypassPermissions``); ``False`` is edits-only
    (``acceptEdits``) — safer, but it can't run shell commands.
    """

    project: str
    prompt: str
    full_access: bool = False


#: The pyclawd verbs the dashboard can launch, mapped to their argv. An allowlist —
#: the frontend sends a key, never a raw command, so nothing arbitrary is run.
_RUN_VERBS: dict[str, list[str]] = {
    "check": ["check"],
    "test": ["test", "run"],
    "test-fast": ["test", "fast"],
    "golden": ["golden"],
    "lint": ["lint"],
    "typecheck": ["typecheck"],
    "format-check": ["format", "--check"],
    "doctor": ["doctor"],
}


def _norm_base(value: str | None) -> Ref:
    """Normalise the ``base`` (old side) query param, defaulting to ``HEAD``."""
    return value or "HEAD"


def _norm_target(value: str | None) -> Ref:
    """Normalise the ``target`` (new side) query param, defaulting to the working tree."""
    return value or WORKING_TREE


def create_app(default_project: str | None = None, registry: Registry | None = None) -> FastAPI:
    """Build the dashboard's FastAPI application.

    Args:
        default_project: Project pre-selected when a request omits ``?project=``.
        registry: Project registry to use; defaults to the on-disk one. Tests pass a
            registry pointed at a scratch config.

    Returns:
        The configured :class:`fastapi.FastAPI` app (not yet served).
    """
    reg = registry or Registry.default()
    app = FastAPI(title="pyclawd web", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def repo_for(project: str | None) -> GitRepo:
        """Resolve *project* (or the default) to a :class:`GitRepo`, or 404."""
        path = reg.resolve(project or default_project)
        if not path:
            raise HTTPException(status_code=404, detail="unknown project")
        return GitRepo(root=Path(path))

    # -- projects ---------------------------------------------------------- #

    @app.get("/api/projects")
    def get_projects() -> dict:
        """List every known project with its branch/dirty/ahead-behind status."""
        out = []
        for entry in reg.projects().values():
            status = GitRepo(root=Path(entry.path)).status()
            out.append({**entry.__dict__, **status.__dict__})
        out.sort(key=lambda p: (not p["starred"], p["name"].lower()))
        return {"projects": out, "default": default_project}

    @app.post("/api/projects/star")
    def star_project(body: StarBody) -> dict:
        """Pin or unpin a project in the switcher."""
        reg.set_star(body.name, body.starred)
        return {"ok": True}

    @app.post("/api/projects/add")
    def add_project(body: AddBody) -> dict:
        """Register a git repo by path; 400 if it is not a work tree."""
        resolved = str(Path(body.path).expanduser().resolve())
        if not GitRepo(root=Path(resolved)).is_repo():
            raise HTTPException(status_code=400, detail=f"{resolved} is not a git work tree")
        return {"name": reg.add(resolved, body.name)}

    @app.post("/api/projects/remove")
    def remove_project(body: RemoveBody) -> dict:
        """Unregister a manually-added project."""
        return {"ok": reg.remove(body.name)}

    # -- refs / files ------------------------------------------------------ #

    @app.get("/api/refs")
    def get_refs(project: str | None = None) -> dict:
        """Return branches, tags, recent commits, and the current branch."""
        return repo_for(project).refs().__dict__

    @app.get("/api/files")
    def get_files(project: str | None = None) -> dict:
        """Return all tracked + untracked paths (fuel for the quick-open palette)."""
        return {"files": repo_for(project).tracked_paths()}

    # -- changes / diff ---------------------------------------------------- #

    @app.get("/api/changes")
    def get_changes(
        project: str | None = None,
        base: str | None = None,
        target: str | None = None,
        all: bool = False,
    ) -> dict:
        """List changed files (or every file with ``all=true``) between two sides."""
        repo = repo_for(project)
        b, t = _norm_base(base), _norm_target(target)
        files = repo.all_files(b, t) if all else repo.changes(b, t)
        return {
            "project": project or default_project,
            "base": b,
            "target": t,
            "all": all,
            "files": files,
            "token": repo.state_token(b, t),
        }

    @app.get("/api/diff")
    def get_diff(
        path: str,
        project: str | None = None,
        base: str | None = None,
        target: str | None = None,
        mode: str = "diff",
    ) -> object:
        """Return a renderable view of one file (``mode`` is ``diff`` or ``full``)."""
        repo = repo_for(project)
        if not repo.contains(path):
            raise HTTPException(status_code=400, detail="invalid path")
        return repo.file_view(_norm_base(base), path, mode, _norm_target(target))

    @app.get("/api/state")
    def get_state(
        project: str | None = None, base: str | None = None, target: str | None = None
    ) -> dict:
        """Return the current state token for a comparison (a one-shot liveness probe)."""
        return {"token": repo_for(project).state_token(_norm_base(base), _norm_target(target))}

    @app.get("/api/events")
    async def events(
        project: str | None = None, base: str | None = None, target: str | None = None
    ) -> StreamingResponse:
        """Stream the comparison's state token over SSE, pushed on every filesystem change."""
        repo = repo_for(project)
        b, t = _norm_base(base), _norm_target(target)
        return StreamingResponse(_token_stream(repo, b, t), media_type="text/event-stream")

    # -- sessions ---------------------------------------------------------- #

    @app.get("/api/sessions")
    def get_sessions() -> dict:
        """List interactive ``claude`` tmux panes, labelled with their project."""
        path_to_name = {e.path: e.name for e in reg.projects().values()}
        return {"sessions": [p.__dict__ for p in list_panes(path_to_name)]}

    @app.post("/api/send")
    def post_send(body: SendBody) -> dict:
        """Paste assembled review text into a running ``claude`` tmux pane."""
        ok = send_to_pane(body.target, body.text, submit=body.submit, focus=body.focus)
        if not ok:
            raise HTTPException(status_code=400, detail="target is not a running claude session")
        return {"ok": True}

    # -- headless claude agent --------------------------------------------- #

    @app.get("/api/agent")
    def agent_available() -> dict:
        """Report whether a headless ``claude`` agent can be launched (CLI on PATH)."""
        return {"available": shutil.which("claude") is not None}

    @app.post("/api/agent/run")
    def agent_run(body: AgentBody) -> StreamingResponse:
        """Run a one-shot ``claude -p`` agent in the project, streaming its progress.

        The agent runs headless in the repo with edits auto-accepted, so it can act
        on the staged review directly. Progress is streamed over SSE as it works.
        """
        path = reg.resolve(body.project or default_project)
        if not path:
            raise HTTPException(status_code=404, detail="unknown project")
        if shutil.which("claude") is None:
            raise HTTPException(status_code=400, detail="the 'claude' CLI is not on PATH")
        return StreamingResponse(
            _agent_stream(Path(path), body.prompt, body.full_access),
            media_type="text/event-stream",
        )

    # -- pyclawd verb runner ----------------------------------------------- #

    @app.get("/api/run")
    def run_available(project: str | None = None) -> dict:
        """Report whether pyclawd verbs can run here (CLI present + project configured)."""
        repo = repo_for(project)
        return {
            "pyclawd": shutil.which("pyclawd") is not None,
            "configured": (repo.root / ".pyclawd" / "config.py").exists(),
            "verbs": list(_RUN_VERBS),
        }

    @app.post("/api/run")
    def run_verb(body: RunBody) -> StreamingResponse:
        """Run a pyclawd verb in the project and stream its output over SSE."""
        path = reg.resolve(body.project or default_project)
        if not path:
            raise HTTPException(status_code=404, detail="unknown project")
        argv = _RUN_VERBS.get(body.verb)
        if argv is None:
            raise HTTPException(status_code=400, detail=f"unknown verb: {body.verb}")
        if shutil.which("pyclawd") is None:
            raise HTTPException(status_code=400, detail="the 'pyclawd' CLI is not on PATH")
        return StreamingResponse(_run_stream(Path(path), argv), media_type="text/event-stream")

    # -- config ------------------------------------------------------------ #

    @app.get("/api/config")
    def get_config() -> dict:
        """Return the configured discovery roots."""
        return {"roots": [str(r) for r in reg.roots()]}

    @app.post("/api/config")
    def set_config(body: ConfigBody) -> dict:
        """Replace the discovery roots."""
        return {"ok": True, "roots": reg.set_roots(body.roots)}

    # -- static SPA (only when built) -------------------------------------- #

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="spa")

    return app


def _sse(token: str) -> str:
    """Format *token* as a single Server-Sent Event frame."""
    return f"data: {json.dumps({'token': token})}\n\n"


async def _token_stream(repo: GitRepo, base: Ref, target: Ref) -> AsyncIterator[str]:
    """Yield an SSE frame with the state token initially and on every change.

    Watches the repo's working tree with :func:`watchfiles.awatch`; on each batch of
    filesystem events it recomputes the (content-aware) state token and emits a frame
    only when it actually moved, so a client redraws exactly when the diff would.
    """
    from watchfiles import awatch

    last = repo.state_token(base, target)
    yield _sse(last)
    try:
        async for _changes in awatch(repo.root):
            token = await asyncio.to_thread(repo.state_token, base, target)
            if token != last:
                last = token
                yield _sse(token)
    except asyncio.CancelledError:  # client disconnected
        raise


def _agent_event(kind: str, text: str) -> str:
    """Format one agent-progress line as an SSE frame (``kind`` ∈ log/tool/result/done/error)."""
    return f"data: {json.dumps({'kind': kind, 'text': text})}\n\n"


def _clip(text: str, limit: int = 160) -> str:
    """Collapse whitespace in *text* and clip it to *limit* characters."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _describe_tool(block: dict) -> str:
    """Render a one-line summary of a tool call: name + its most relevant argument."""
    name = block.get("name", "tool")
    args = block.get("input", {}) or {}
    detail = ""
    if name in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
        detail = args.get("file_path") or args.get("notebook_path") or ""
    elif name == "Bash":
        detail = args.get("command", "")
    elif name in ("Grep", "Glob"):
        detail = args.get("pattern", "")
        if args.get("path"):
            detail += f"  ({args['path']})"
    elif name == "Task":
        detail = args.get("description", "")
    elif name == "WebFetch":
        detail = args.get("url", "")
    elif name == "TodoWrite":
        detail = f"{len(args.get('todos', []))} todos"
    else:
        detail = next((v for v in args.values() if isinstance(v, str)), "")
    detail = _clip(detail)
    return f"🔧 {name}" + (f" · {detail}" if detail else "")


def _summarise_agent_json(line: str) -> list[tuple[str, str]]:
    """Turn one ``--output-format stream-json`` event into ``(kind, text)`` frames.

    Assistant narration and each tool call become separate frames (so the UI can
    style them differently); the terminal ``result`` event carries the summary plus
    cost/turn stats. Events with nothing worth showing yield an empty list.
    """
    try:
        event = json.loads(line)
    except ValueError:
        return []
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        model = event.get("model", "")
        return [("log", f"● session started{f' ({model})' if model else ''}")]
    if etype == "assistant":
        frames: list[tuple[str, str]] = []
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                frames.append(("text", block["text"].strip()))
            elif block.get("type") == "tool_use":
                frames.append(("tool", _describe_tool(block)))
        return frames
    if etype == "result":
        result = (event.get("result") or "").strip() or "(no textual result)"
        stats = []
        if event.get("num_turns"):
            stats.append(f"{event['num_turns']} turns")
        if event.get("total_cost_usd"):
            stats.append(f"${event['total_cost_usd']:.3f}")
        if event.get("duration_ms"):
            stats.append(f"{event['duration_ms'] / 1000:.1f}s")
        suffix = f"\n\n— {' · '.join(stats)}" if stats else ""
        return [("result", result + suffix)]
    return []


async def _agent_stream(cwd: Path, prompt: str, full_access: bool) -> AsyncIterator[str]:
    """Run ``claude -p`` headless in *cwd* and stream a readable progress log over SSE.

    With *full_access* the agent runs under ``bypassPermissions`` (edits files AND
    runs commands unattended); otherwise ``acceptEdits`` (edits only — safer, but it
    cannot run shell commands). Structured ``stream-json`` events are distilled to
    readable frames; a final ``done`` frame carries the exit code.
    """
    mode = "bypassPermissions" if full_access else "acceptEdits"
    proc = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        mode,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    access = "full access" if full_access else "edits only"
    yield _agent_event("log", f"$ claude -p (headless · {access}) in {cwd.name}")
    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            for kind, text in _summarise_agent_json(raw.decode(errors="replace")):
                yield _agent_event(kind, text)
        code = await proc.wait()
        yield _agent_event("done", f"agent finished (exit {code})")
    except asyncio.CancelledError:  # client disconnected — stop the agent
        proc.terminate()
        raise


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences so streamed CLI output renders cleanly."""
    return _ANSI_RE.sub("", text)


async def _run_stream(cwd: Path, argv: list[str]) -> AsyncIterator[str]:
    """Run ``pyclawd *argv`` in *cwd* and stream its (ANSI-stripped) output over SSE.

    Each stdout line is an ``out`` frame; a final ``done`` frame reports pass/fail
    by exit code. Colour is disabled so the log is plain text.
    """
    proc = await asyncio.create_subprocess_exec(
        "pyclawd",
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )
    yield _agent_event("log", f"$ pyclawd {' '.join(argv)} in {cwd.name}")
    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            yield _agent_event("out", _strip_ansi(raw.decode(errors="replace").rstrip("\n")))
        code = await proc.wait()
        verdict = "✓ passed" if code == 0 else f"✗ failed (exit {code})"
        yield _agent_event("done", verdict)
    except asyncio.CancelledError:  # client disconnected — stop the run
        proc.terminate()
        raise
