"""Config inspection command — ``pyclawd config``.

Shows the resolved effective configuration: what every pyclawd command will
actually run, after env-var overrides. This is the agent's orientation command —
run it once at the start of a session to know exactly what ``pyclawd test fast``,
``pyclawd lint``, etc. will invoke.
"""

from __future__ import annotations

import os

import typer
from rich.console import Console
from rich.table import Table

from ..discovery import ENV_VAR as CONFIG_ENV
from ..discovery import ConfigError, load_project
from ..logs import WORK_ENV, work_root
from ..run import PYTHON_ENV, python_prefix


def config() -> None:
    """Show the resolved effective configuration — what every command will actually run."""
    console = Console()
    try:
        project = load_project()
    except ConfigError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(2) from None
    if project is None:
        console.print("[red]✗ no .pyclawd/config.py found — run pyclawd inside a project[/red]")
        raise typer.Exit(2)

    console.print(f"\n[bold]pyclawd — {project.name}[/bold]")

    # Source + root
    if project.root is not None:
        config_path = project.root / ".pyclawd" / "config.py"
        config_source = f"  [dim](via ${CONFIG_ENV})[/dim]" if os.environ.get(CONFIG_ENV) else ""
        console.print(f"  [dim]config[/dim]  {config_path}{config_source}")
        console.print(f"  [dim]root  [/dim]  {project.root}")

    # Always show all PYCLAWD_* knobs with their current effective value so the
    # agent knows what levers exist and what's actually running right now.
    prefix = python_prefix(project)
    python_shown = " ".join(prefix)
    python_source = (
        "sys.executable" if not project.python_cmd and not os.environ.get(PYTHON_ENV) else ""
    )

    wdir = work_root(project)
    wdir_source = (
        "default tmpdir"
        if not project.work_dir and not os.environ.get(WORK_ENV)
        else ("config: work_dir" if project.work_dir else "")
    )

    config_source = "walk-up from cwd" if not os.environ.get(CONFIG_ENV) else ""

    et = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    et.add_column("", min_width=20)
    et.add_column("", style="dim", min_width=10)
    et.add_column("", style="dim")

    def _env_row(var: str, desc: str, effective: str, source: str) -> None:
        val = os.environ.get(var)
        cur = f"{effective}  ({source})" if source else effective
        if val:
            et.add_row(f"[yellow]${var}[/yellow]", f"[yellow]{val}[/yellow]", desc)
        else:
            et.add_row(f"[dim]${var}[/dim]", "[dim](not set)[/dim]", f"{desc}  →  {cur}")

    _env_row(
        CONFIG_ENV,
        "config file to load",
        str(project.root / ".pyclawd" / "config.py") if project.root else "?",
        config_source,
    )
    _env_row(PYTHON_ENV, "Python command for all verbs", python_shown, python_source)
    _env_row(WORK_ENV, "log/work directory", str(wdir), wdir_source)

    console.print()
    console.print("[bold]Env vars[/bold]")
    console.print(et)
    console.print()

    # ---------------------------------------------------------------- Test tiers
    console.print("[bold]Tests[/bold]")
    t = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    t.add_column("", style="dim", min_width=14)
    t.add_column("")
    t.add_row("dir", project.test.tests_dir)
    t.add_row("jobs", project.test.jobs or "serial")

    prefix_str = python_shown
    tests_dir = project.test.tests_dir
    jobs = project.test.jobs
    jobs_flag = f" -n {jobs}" if jobs else ""

    for tier, marker in project.test.markers.items():
        # "default" key maps to `pyclawd test run` / `pyclawd test` (no verb)
        label = "run (default)" if tier == "default" else tier
        m_part = f' -m "{marker}"' if marker else ""
        tier_cmd = f"{prefix_str} -m pytest -v {tests_dir}{m_part}{jobs_flag}"
        t.add_row(label, tier_cmd)

    console.print(t)
    console.print()

    # -------------------------------------------------------------- Quality gate
    if project.quality:
        q = project.quality
        console.print("[bold]Quality[/bold]")
        qt = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        qt.add_column("", style="dim", min_width=14)
        qt.add_column("")
        pairs = [
            ("lint", q.lint_cmd),
            ("lint --fix", q.lint_fix_cmd),
            ("format", q.format_cmd),
            ("format --check", q.format_check_cmd),
            ("typecheck", q.typecheck_cmd),
        ]
        for name, cmd in pairs:
            if cmd:
                qt.add_row(name, " ".join(cmd))
        qt.add_row("check", " → ".join(q.check_sequence))
        console.print(qt)
        console.print()
    else:
        console.print("[bold]Quality[/bold]  [dim](not configured)[/dim]\n")

    # -------------------------------------------------------------------- Docs
    if project.docs:
        d = project.docs
        console.print("[bold]Docs[/bold]")
        dt = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        dt.add_column("", style="dim", min_width=14)
        dt.add_column("")
        dt.add_row("runner", " ".join(d.runner) if d.runner else "(none)")
        dt.add_row("source", d.source_dir)
        dt.add_row("cache", d.cache_dir)
        dt.add_row("html", d.build_html)
        console.print(dt)
        console.print()


def register(app: typer.Typer) -> None:
    """Attach the config command to *app*."""
    app.command()(config)
