"""Docs commands: the ``pyclawd docs`` sub-Typer.

Cached, parallel notebook builds via the project's isolated docs toolchain
(``project.docs.runner``). The group is ALWAYS registered (so ``--config`` /
``PYCLAWD_CONFIG`` / walk-up all drive it consistently and ``pyclawd --help``
never depends on import-time discovery). Each subcommand self-reports cleanly
when the loaded project does not configure docs — see :func:`_docs_project_or_exit`.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import subprocess
from pathlib import Path

import typer

from .. import logs, run
from . import _PASSTHROUGH

docs_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Docs: cached, parallel notebook builds via the isolated ./docs env.",
)


def _docs_project_or_exit():
    """Load the project and require a configured ``docs`` block, or exit cleanly.

    The ``docs`` group is always registered, so each subcommand calls this to
    self-report when the loaded project leaves ``Project.docs`` as ``None``: it
    prints a clear stderr message and exits ``2`` (rather than crashing or being
    unavailable). When no project is found at all, ``load_project_or_exit``
    handles that with its own clean exit.
    """
    project = run.load_project_or_exit()
    if project.docs is None:
        typer.secho(
            "docs not configured — set Project.docs in .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project


def _docs_run(project, sub: list[str], log: Path | None = None) -> int:
    """Delegate to the project's isolated docs toolchain (``project.docs.runner``).

    Heavy docs deps (sphinx/nbsphinx/viz/jupyter-cache) live in that isolated env,
    never in the project itself. Execution is cached by jupyter-cache — unchanged
    code is skipped. With ``log`` set, output goes to that file (quiet); otherwise
    to the console.
    """
    cmd = [*project.docs.runner, *sub]
    root = project.root
    return logs.run_logged(cmd, log, root) if log else run.run(cmd, root)


def _preflight_render() -> None:
    """Fail fast (before any expensive execution) if the HTML render toolchain is missing.

    nbsphinx shells out to the `pandoc` system binary.
    """
    if not shutil.which("pandoc"):
        typer.secho(
            "✗ pandoc not found — nbsphinx needs it to render HTML.\n"
            "  Install:  conda install -c conda-forge pandoc",
            fg="red",
            err=True,
        )
        raise typer.Exit(3)


def _validate_outputs(project) -> int:
    """Fail if a notebook that executed WITH output rendered to HTML WITHOUT it.

    This is the empty-page failure mode where the Sphinx render races ahead of
    notebook hydration and ships blank cells (``nbsphinx_execute='never'`` renders
    whatever output state is on disk).

    For every executed ``.ipynb`` under ``docs.source_dir`` that produced ≥1
    output cell, the matching rendered page under ``docs.build_html`` must contain
    an nbsphinx output block (``nboutput``). This is false-positive resistant:
    a legitimately output-free page has no outputs in its ``.ipynb`` either, so
    nothing is asserted of it. Pages not rendered in this run (no HTML on disk,
    e.g. a ``--changed`` build) are skipped. Returns the offender count.
    """
    source = project.path(project.docs.source_dir)
    html_root = project.path(project.docs.build_html)
    offenders: list[tuple[Path, int]] = []
    checked = 0
    for ipynb in sorted(source.rglob("*.ipynb")):
        try:
            nb = json.loads(ipynb.read_text())
        except Exception:
            continue
        n_out = sum(
            len(c.get("outputs", [])) for c in nb.get("cells", []) if c.get("cell_type") == "code"
        )
        if n_out == 0:
            continue  # legitimately output-free → assert nothing
        rel = ipynb.relative_to(source).with_suffix(".html")
        html = html_root / rel
        if not html.exists():
            continue  # not rendered in this run (e.g. --changed) → skip
        checked += 1
        if "nboutput" not in html.read_text(errors="ignore"):
            offenders.append((rel, n_out))
    if offenders:
        typer.secho(
            "✗ docs output guardrail FAILED — executed pages rendered blank:",
            fg="red",
            err=True,
        )
        for rel, n in offenders:
            typer.secho(
                f"    {rel}  (executed with {n} output(s), HTML has none)",
                fg="red",
                err=True,
            )
        typer.secho(
            "  Likely a hydration race — re-execute the page(s) then re-render.",
            fg="yellow",
            err=True,
        )
    else:
        typer.echo(f"✓ output guardrail: {checked} page(s) with outputs rendered non-empty")
    return len(offenders)


def _changed_docs(project) -> list[str]:
    """Source `.md` pages changed vs the docs branch, relative to the docs dir.

    Diffs ``project.docs.branch`` over ``project.docs.source_dir`` and strips the
    source dir's leading path component (e.g. ``docs/``) so pages are relative to
    the docs directory, matching what the docs runner expects.
    """
    branch = project.docs.branch
    source_dir = project.docs.source_dir
    prefix = Path(source_dir).parts[0] + "/"
    out = subprocess.run(
        ["git", "-C", str(project.root), "diff", "--name-only", branch, "--", source_dir],
        capture_output=True,
        text=True,
    )
    return [line[len(prefix) :] for line in out.stdout.splitlines() if line.endswith(".md")]


@docs_app.command("status")
def docs_status() -> None:
    """Show which doc pages changed vs main (what a `--changed` build would run)."""
    project = _docs_project_or_exit()
    cache = project.path(project.docs.cache_dir)
    typer.echo(f"cache: {'present' if cache.exists() else 'empty (first build executes all)'}")
    pages = _changed_docs(project)
    if not pages:
        typer.echo("no source .md changed vs main")
        return
    typer.echo(f"{len(pages)} changed page(s) vs main:")
    for p in pages:
        typer.echo(f"  {p}")


@docs_app.command("build")
def docs_build(
    all_: bool = typer.Option(False, "--all", help="Force re-execute every notebook."),
    changed: bool = typer.Option(False, "--changed", help="Only pages changed vs main."),
    cont: bool = typer.Option(
        False, "--continue", help="Render HTML even if notebooks fail (default: stop early)."
    ),
    fast: bool = typer.Option(
        False, "--fast", help="Exclude all notebooks — fast smoke render (no execution)."
    ),
) -> None:
    """Compile → execute (cached, parallel) → render HTML.

    By default a notebook failure STOPS the build before the (expensive) HTML
    render, so you find out early. Pass --continue to render anyway. `--fast`
    skips execution and renders only non-notebook pages (smoke test).
    """
    project = _docs_project_or_exit()
    _preflight_render()  # fail in seconds if pandoc is missing, not after executing
    run_id, log, t0 = logs.run_start("docs build", "docs", project)
    cflag = ["--continue"] if cont else []

    if fast:
        # Notebooks are excluded from the render, so don't execute them.
        code = _docs_run(project, ["build", "--fast"], log)
        logs.run_finish(run_id, log, code, t0)
        return

    if all_:
        code = _docs_run(project, ["all", "--force", *cflag], log)
    elif changed:
        pages = _changed_docs(project)
        if pages:
            typer.echo(f"  scope:  {len(pages)} changed page(s)")
            _docs_run(project, ["compile", *pages], log)
            rc = _docs_run(project, ["run", *pages, *cflag], log)
            if rc != 0:  # notebooks failed → don't pay for the render
                logs.run_finish(run_id, log, rc, t0)
        else:
            typer.echo("  scope:  no changed pages — rendering current state")
        code = _docs_run(project, ["build"], log)
    else:
        code = _docs_run(project, ["all", *cflag], log)

    # Guardrail: a render that dropped executed outputs must fail the build —
    # catches the empty-page race (HTML rendered before notebooks were hydrated).
    if code == 0 and _validate_outputs(project):
        code = 1

    logs.run_finish(run_id, log, code, t0)


@docs_app.command("validate")
def docs_validate() -> None:
    """Fail if any executed notebook rendered to blank HTML (the empty-page guardrail).

    Runs against the already-built HTML — use it as a standalone gate before
    deploying docs (e.g. in a CI deploy workflow) without re-running the build.
    """
    project = _docs_project_or_exit()
    raise typer.Exit(1 if _validate_outputs(project) else 0)


@docs_app.command("run", context_settings=_PASSTHROUGH)
def docs_run(ctx: typer.Context) -> None:
    """Execute notebooks only — compile + run, NO HTML (cached, parallel).

    Extra args = specific pages. This is the expensive step; render is separate.
    """
    project = _docs_project_or_exit()
    run_id, log, t0 = logs.run_start("docs run", "docs", project)
    _docs_run(project, ["compile", *ctx.args], log)
    code = _docs_run(project, ["run", *ctx.args], log)
    logs.run_finish(run_id, log, code, t0)


@docs_app.command("render")
def docs_render(
    fast: bool = typer.Option(
        False,
        "--fast",
        help="Exclude all notebooks — a fast smoke-render of the Sphinx pipeline (seconds).",
    ),
) -> None:
    """Render HTML only (Sphinx) from already-executed notebooks — no execution.

    Fast and repeatable: fix a render issue (e.g. pandoc) and re-run without
    re-executing a single notebook. `--fast` drops every notebook from the
    render (toctree warnings expected) to validate render config/logging quickly.
    """
    project = _docs_project_or_exit()
    _preflight_render()
    run_id, log, t0 = logs.run_start("docs render", "docs", project)
    code = _docs_run(project, ["build", "--fast"] if fast else ["build"], log)
    logs.run_finish(run_id, log, code, t0)


@docs_app.command("compile", context_settings=_PASSTHROUGH)
def docs_compile(ctx: typer.Context) -> None:
    """Convert changed .md sources to .ipynb (no execution)."""
    raise typer.Exit(_docs_run(_docs_project_or_exit(), ["compile", *ctx.args]))


@docs_app.command("exec")
def docs_exec(
    page: str = typer.Argument(..., help="One page, e.g. visualization/pcp"),
) -> None:
    """Execute ONE notebook directly and show its error — the debug loop.

    No cache, no parallel pool, NO log file: the full traceback streams straight
    to the console. Run one → read the error → fix the .md → run again → next.
    """
    project = _docs_project_or_exit()
    raise typer.Exit(_docs_run(project, ["exec", page]))  # streams to console, not a log


@docs_app.command("timings")
def docs_timings(
    top: int = typer.Option(0, "--top", help="Show only the slowest N (0 = all)."),
) -> None:
    """Per-notebook execution times from the cache — slowest first (the bottlenecks)."""
    project = _docs_project_or_exit()
    db = project.path(project.docs.cache_db)
    if not db.exists():
        typer.echo(
            "No jupyter-cache database at "
            f"{project.docs.cache_db} — run `pyclawd docs build` first "
            "(timings read the runner's jupyter-cache backend)."
        )
        raise typer.Exit(0)

    rows: list[tuple[float, str]] = []
    con = sqlite3.connect(str(db))
    try:
        for uri, data in con.execute("SELECT uri, data FROM nbcache"):
            try:
                secs = json.loads(data or "{}").get("execution_seconds")
            except (ValueError, TypeError):
                secs = None
            if secs is not None:
                rows.append((secs, uri))
    finally:
        con.close()

    rows.sort(reverse=True)
    total = sum(s for s, _ in rows)
    shown = rows[:top] if top else rows
    src = str(project.path(project.docs.source_dir)) + "/"
    typer.echo(f"⏱  {len(rows)} notebooks · total {total:.1f}s (slowest first)")
    for secs, uri in shown:
        typer.echo(f"  {secs:7.1f}s  {uri.replace(src, '')}")


@docs_app.command("failures")
def docs_failures(
    full: bool = typer.Option(False, "--full", help="Show full tracebacks."),
) -> None:
    """Every code notebook that is NOT successfully cached — the real fix list.

    Reports both 'excepted' failures (a cell raised → traceback stored) AND
    'errored' ones (kernel/setup failure → no traceback, e.g. an unregistered
    kernel name). A notebook is "passing" only if it has a success cache record.
    """
    project = _docs_project_or_exit()
    cache_dir = project.path(project.docs.cache_dir)
    src = project.path(project.docs.source_dir)
    if not (cache_dir / "global.db").exists():
        typer.echo("No cache yet — run `pyclawd docs build` first.")
        raise typer.Exit(0)

    try:
        import nbformat
        from jupyter_cache import get_cache
    except ImportError:
        typer.secho(
            "needs jupyter-cache + nbformat in this env (pip install jupyter-cache)",
            fg="red",
            err=True,
        )
        raise typer.Exit(2) from None

    cache = get_cache(str(cache_dir))

    # tracebacks (for 'excepted' failures) keyed by absolute uri
    tbs = {}
    con = sqlite3.connect(str(cache_dir / "global.db"))
    try:
        for uri, tb in con.execute(
            "SELECT uri, traceback FROM nbproject WHERE traceback IS NOT NULL AND traceback != ''"
        ):
            tbs[uri] = re.sub(r"\x1b\[[0-9;]*m", "", tb)
    finally:
        con.close()

    # A notebook is "passing" iff its current code matches the cache — exactly
    # how the build decides what to (re)run. (URI comparison was unreliable.)
    rows = []  # (name, traceback-or-None)
    for md in sorted(src.rglob("*.md")):
        nb = md.with_suffix(".ipynb")
        if not nb.exists():
            continue
        try:
            n = nbformat.read(str(nb), 4)
        except Exception:
            continue
        if not any(c.cell_type == "code" and c.source.strip() for c in n.cells):
            continue  # static page — nothing to run
        try:
            cache.match_cache_file(str(nb.resolve()))
            continue  # cached → passing
        except KeyError:
            rows.append((str(nb.relative_to(src)), tbs.get(str(nb.resolve()))))

    if not rows:
        typer.secho("✅ all code notebooks pass (cached)", fg="green")
        raise typer.Exit(0)

    typer.secho(f"❌ {len(rows)} notebook(s) not passing:", fg="red")
    for name, tb in sorted(rows):
        if not tb:
            page = name[:-6] if name.endswith(".ipynb") else name
            typer.echo(f"  {name}: not cached — `pyclawd docs exec {page}` to see the error")
        elif full:
            typer.echo(f"\n=== {name} ===\n{tb.strip()}")
        else:
            errs = [
                ln.strip()
                for ln in tb.splitlines()
                if re.search(r"(Error|Exception|Timeout\w*):", ln)
            ]
            line = errs[-1] if errs else (tb.strip().splitlines() or ["(unknown)"])[-1]
            typer.echo(f"  {name}: {line[:140]}")


@docs_app.command("clean")
def docs_clean() -> None:
    """Remove build/ and generated .ipynb (keeps the execution cache)."""
    raise typer.Exit(_docs_run(_docs_project_or_exit(), ["clean"]))


def _lan_ip() -> str | None:
    """Best-effort outbound LAN IP (no traffic sent) for a remotely-reachable URL."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


@docs_app.command("serve")
def docs_serve(
    port: int = typer.Option(8000, help="Port to serve on."),
    background: bool = typer.Option(
        False, "--background", "-b", help="Detach and return immediately."
    ),
    bind: str = typer.Option("0.0.0.0", help="Address to bind (0.0.0.0 = reachable over LAN)."),
) -> None:
    """Serve the built HTML (the configured docs build dir).

    Static files are served by the dev env directly — no need to spin up the
    heavy isolated docs env. `--background` detaches the server and prints the PID
    + LAN URL so you can reach it from another machine (e.g. a Mac over the LAN).
    """
    project = _docs_project_or_exit()
    html = project.path(project.docs.build_html)
    if not (html / "index.html").exists():
        typer.echo("❌ No built docs — run `pyclawd docs build` first.")
        raise typer.Exit(1)

    cmd = [
        *run.python_prefix(project),
        "-m",
        "http.server",
        str(port),
        "--bind",
        bind,
        "--directory",
        str(html),
    ]
    lan = _lan_ip()
    urls = f"http://localhost:{port}" + (
        f"  ·  http://{lan}:{port}" if lan and bind == "0.0.0.0" else ""
    )

    if background:
        logp = logs.category_dir("docs", project)
        logp.mkdir(parents=True, exist_ok=True)
        logf = open(logp / "serve.log", "a")  # noqa: SIM115 - handle outlives this function (detached server)
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
        typer.echo(
            f"🌐 serving {html}\n   {urls}\n   pid {proc.pid} · "
            f"stop: kill {proc.pid}  (or pkill -f 'http.server {port}')"
        )
        return

    typer.echo(f"🌐 serving {html}\n   {urls}\n   Press Ctrl+C to stop")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\n👋 stopped")


def register(app: typer.Typer) -> None:
    """Attach the ``docs`` sub-app — always.

    The group is registered unconditionally so config discovery (``--config`` /
    ``PYCLAWD_CONFIG`` / walk-up) is resolved at command time, not at import time.
    Each subcommand calls :func:`_docs_project_or_exit`, which self-reports cleanly
    when the loaded project leaves ``Project.docs`` as ``None``.
    """
    app.add_typer(docs_app, name="docs")
