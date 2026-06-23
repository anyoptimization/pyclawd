"""pyclawd — the pymoo developer toolkit.

A single CLI for working on the pymoo codebase: run Python in the dev env, run
tests by category, build/clean Cython extensions, and health-check the setup.

Thin command surface — real logic lives in sibling modules. Claude Code skills and
slash commands shell out to these commands rather than reimplementing them.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import typer

from . import __version__, logs, run
from . import tests
from .doctor import run_doctor
from .project import load_project

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="pyclawd — the pymoo developer toolkit (run code, test, build, doctor).",
)

# Commands that forward unknown args/options straight to a subprocess.
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


# --------------------------------------------------------------------------- run

@app.command(context_settings=_PASSTHROUGH)
def python(ctx: typer.Context) -> None:
    """Run Python in the dev env with the repo on PYTHONPATH.

    e.g. `pyclawd python script.py`, `pyclawd python -m module`, `pyclawd python -c "import pymoo"`.
    """
    raise typer.Exit(run.python(ctx.args))


# -------------------------------------------------------------------------- tests

@app.command(context_settings=_PASSTHROUGH)
def pytest(ctx: typer.Context) -> None:
    """Run pytest over tests/ (excludes `long` unless you pass your own `-m`)."""
    project = run.load_project_or_exit()
    raise typer.Exit(run.pytest(
        ctx.args,
        default_markers=project.test.markers["default"],
        tests_dir=project.test.tests_dir,
    ))


@app.command(context_settings=_PASSTHROUGH)
def test(ctx: typer.Context) -> None:
    """Run tests. Verbs mirror `pyclawd docs`; otherwise run a category/pytest passthrough.

    Pipeline verbs (logged, instrumented):
      pyclawd test run            full default suite (not long) → run-id log + timing/failure tables
      pyclawd test fast           the <30s smoke tier (not slow, not long), under xdist (-n auto)
      pyclawd test all            everything, including `long`
      pyclawd test failures       the fix-list (pytest lastfailed cache)
      pyclawd test timings [--top N]   slowest tests from the last run
      pyclawd test fix            debug primitive: rerun --lf -x, stream the next failure

    Legacy/passthrough:
      pyclawd test                default suite (not examples/docs/long)
      pyclawd test examples|docs  that category   ·   pyclawd test -k nsga2   ·   pyclawd test path::name -x
    """
    args = list(ctx.args)
    verb = args[0] if args else None

    if verb in {"run", "fast", "all", "failures", "timings", "fix"}:
        raise typer.Exit(tests.dispatch(verb, args[1:]))

    project = run.load_project_or_exit()
    tier_markers = project.test.markers

    category = "default"
    if verb in {"default", "examples", "docs"}:
        category = args.pop(0)

    markers = tier_markers[category]
    raise typer.Exit(run.pytest(
        args, default_markers=markers, tests_dir=project.test.tests_dir))


# -------------------------------------------------------------------------- build

@app.command()
def compile() -> None:  # noqa: A001 - intentional command name
    """Build the project's extensions in place (project.compile_cmd)."""
    project = run.load_project_or_exit()
    raise typer.Exit(run.python(project.compile_cmd))


@app.command()
def dist() -> None:
    """Build a source distribution (project.dist_cmd)."""
    project = run.load_project_or_exit()
    raise typer.Exit(run.python(project.dist_cmd))


@app.command()
def clean(
    ext: bool = typer.Option(False, "--ext", help="Also remove compiled extension artifacts."),
) -> None:
    """Remove the project's build artifacts (and with --ext, compiled extensions)."""
    project = run.load_project_or_exit()
    removed: list[str] = []

    for name in project.clean_targets:
        p = project.path(name)
        if p.exists():
            shutil.rmtree(p)
            removed.append(name)

    if ext:
        compiled = project.path(project.clean_ext_dir)
        for pattern in project.clean_ext_globs:
            for f in compiled.glob(pattern):
                f.unlink()
                removed.append(str(f.relative_to(project.root)))

    typer.echo("removed: " + (", ".join(removed) if removed else "nothing to clean"))


# -------------------------------------------------------------------------- meta

@app.command()
def doctor() -> None:
    """Health-check the dev env (conda, deps, Cython build, tools, git)."""
    raise typer.Exit(run_doctor())


@app.command()
def root() -> None:
    """Print the detected project repo root (via the .pyclawd/config.py loader)."""
    project = load_project()
    if project is None or project.root is None:
        typer.secho("not inside a project (no .pyclawd/config.py found)", fg="red", err=True)
        raise typer.Exit(2)
    typer.echo(str(project.root))


@app.command()
def version() -> None:
    """Print the pyclawd version."""
    typer.echo(f"pyclawd {__version__}")


# --------------------------------------------------------------------------- docs

docs_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Docs: cached, parallel notebook builds via the isolated ./docs env.",
)
app.add_typer(docs_app, name="docs")


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
    """Fail fast (before any expensive execution) if the HTML render toolchain
    is missing. nbsphinx shells out to the `pandoc` system binary."""
    if not shutil.which("pandoc"):
        typer.secho(
            "✗ pandoc not found — nbsphinx needs it to render HTML.\n"
            "  Install:  conda install -c conda-forge pandoc",
            fg="red", err=True,
        )
        raise typer.Exit(3)


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
        capture_output=True, text=True,
    )
    return [line[len(prefix):] for line in out.stdout.splitlines() if line.endswith(".md")]


@docs_app.command("status")
def docs_status() -> None:
    """Show which doc pages changed vs main (what a `--changed` build would run)."""
    project = run.load_project_or_exit()
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
    cont: bool = typer.Option(False, "--continue", help="Render HTML even if notebooks fail (default: stop early)."),
    fast: bool = typer.Option(False, "--fast", help="Exclude all notebooks — fast smoke render (no execution)."),
) -> None:
    """Compile → execute (cached, parallel) → render HTML.

    By default a notebook failure STOPS the build before the (expensive) HTML
    render, so you find out early. Pass --continue to render anyway. `--fast`
    skips execution and renders only non-notebook pages (smoke test).
    """
    project = run.load_project_or_exit()
    _preflight_render()  # fail in seconds if pandoc is missing, not after executing
    run_id, log, t0 = logs.run_start("docs build", "docs")
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

    logs.run_finish(run_id, log, code, t0)


@docs_app.command("run", context_settings=_PASSTHROUGH)
def docs_run(ctx: typer.Context) -> None:
    """Execute notebooks only — compile + run, NO HTML (cached, parallel).

    Extra args = specific pages. This is the expensive step; render is separate.
    """
    project = run.load_project_or_exit()
    run_id, log, t0 = logs.run_start("docs run", "docs")
    _docs_run(project, ["compile", *ctx.args], log)
    code = _docs_run(project, ["run", *ctx.args], log)
    logs.run_finish(run_id, log, code, t0)


@docs_app.command("render")
def docs_render(
    fast: bool = typer.Option(
        False, "--fast",
        help="Exclude all notebooks — a fast smoke-render of the Sphinx pipeline (seconds).",
    ),
) -> None:
    """Render HTML only (Sphinx) from already-executed notebooks — no execution.

    Fast and repeatable: fix a render issue (e.g. pandoc) and re-run without
    re-executing a single notebook. `--fast` drops every notebook from the
    render (toctree warnings expected) to validate render config/logging quickly.
    """
    project = run.load_project_or_exit()
    _preflight_render()
    run_id, log, t0 = logs.run_start("docs render", "docs")
    code = _docs_run(project, ["build", "--fast"] if fast else ["build"], log)
    logs.run_finish(run_id, log, code, t0)


@docs_app.command("compile", context_settings=_PASSTHROUGH)
def docs_compile(ctx: typer.Context) -> None:
    """Convert changed .md sources to .ipynb (no execution)."""
    raise typer.Exit(_docs_run(run.load_project_or_exit(), ["compile", *ctx.args]))


@docs_app.command("exec")
def docs_exec(
    page: str = typer.Argument(..., help="One page, e.g. visualization/pcp"),
) -> None:
    """Execute ONE notebook directly and show its error — the debug loop.

    No cache, no parallel pool, NO log file: the full traceback streams straight
    to the console. Run one → read the error → fix the .md → run again → next.
    """
    project = run.load_project_or_exit()
    raise typer.Exit(_docs_run(project, ["exec", page]))  # streams to console, not a log


@docs_app.command("timings")
def docs_timings(
    top: int = typer.Option(0, "--top", help="Show only the slowest N (0 = all)."),
) -> None:
    """Per-notebook execution times from the cache — slowest first (the bottlenecks)."""
    project = run.load_project_or_exit()
    db = project.path(project.docs.cache_db)
    if not db.exists():
        typer.echo("No cache yet — run `pyclawd docs build` first.")
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
    project = run.load_project_or_exit()
    cache_dir = project.path(project.docs.cache_dir)
    src = project.path(project.docs.source_dir)
    if not (cache_dir / "global.db").exists():
        typer.echo("No cache yet — run `pyclawd docs build` first.")
        raise typer.Exit(0)

    try:
        import nbformat
        from jupyter_cache import get_cache
    except ImportError:
        typer.secho("needs jupyter-cache + nbformat in this env "
                    "(pip install jupyter-cache)", fg="red", err=True)
        raise typer.Exit(2)

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
            errs = [l.strip() for l in tb.splitlines() if re.search(r"(Error|Exception|Timeout\w*):", l)]
            line = errs[-1] if errs else (tb.strip().splitlines() or ["(unknown)"])[-1]
            typer.echo(f"  {name}: {line[:140]}")


@docs_app.command("clean")
def docs_clean() -> None:
    """Remove build/ and generated .ipynb (keeps the execution cache)."""
    raise typer.Exit(_docs_run(run.load_project_or_exit(), ["clean"]))


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
    background: bool = typer.Option(False, "--background", "-b", help="Detach and return immediately."),
    bind: str = typer.Option("0.0.0.0", help="Address to bind (0.0.0.0 = reachable over LAN)."),
) -> None:
    """Serve the built HTML (the configured docs build dir).

    Static files are served by the dev env directly — no need to spin up the
    heavy isolated docs env. `--background` detaches the server and prints the PID
    + LAN URL so you can reach it from another machine (e.g. a Mac over the LAN).
    """
    project = run.load_project_or_exit()
    html = project.path(project.docs.build_html)
    if not (html / "index.html").exists():
        typer.echo("❌ No built docs — run `pyclawd docs build` first.")
        raise typer.Exit(1)

    cmd = [sys.executable, "-m", "http.server", str(port),
           "--bind", bind, "--directory", str(html)]
    lan = _lan_ip()
    urls = f"http://localhost:{port}" + (f"  ·  http://{lan}:{port}" if lan and bind == "0.0.0.0" else "")

    if background:
        logp = Path("/tmp/pyclawd/logs/docs")
        logp.mkdir(parents=True, exist_ok=True)
        logf = open(logp / "serve.log", "a")
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT,
                                start_new_session=True)
        typer.echo(f"🌐 serving {html}\n   {urls}\n   pid {proc.pid} · stop: kill {proc.pid}  (or pkill -f 'http.server {port}')")
        return

    typer.echo(f"🌐 serving {html}\n   {urls}\n   Press Ctrl+C to stop")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\n👋 stopped")


if __name__ == "__main__":
    app()
