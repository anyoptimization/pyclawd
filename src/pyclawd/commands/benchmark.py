"""Benchmark command group — ``pyclawd benchmark`` (the performance-regression oracle).

golden proves an observable *value* is unchanged; ``benchmark`` proves the code did not get
*slower*. It times each ``@pytest.mark.benchmark`` test (best-of-N) and gates it against a
baseline. The engine lives in :mod:`pyclawd.benchmark` and the standalone,
auto-registered plugin :mod:`pyclawd.benchmark_plugin`; this module is the CLI wrapper that
translates :class:`~pyclawd.project.BenchmarkConfig` into the plugin's pytest options.

Baselines are **never committed** — a time is hardware-specific, so they live under the
project's gitignored ``work_dir`` (see :func:`_baseline_dir`) and ``benchmark`` compares
against *your* last blessed run on *this* machine.

Subcommands (driven by :class:`~pyclawd.project.BenchmarkConfig`):

- ``pyclawd benchmark [-k EXPR]`` (default) — **compare**: run the benchmark suite as a gate.
- ``pyclawd benchmark update [-k EXPR]`` — **bless**: re-record local baselines (agents compare).
- ``pyclawd benchmark status`` — inventory the local baselines (+ orphan hint).
- ``pyclawd benchmark prune`` — drop orphaned baseline entries whose test is gone.

Exit-code contract (agent-native, deterministic):

- ``0`` — success.
- ``2`` — benchmark not configured for this project.
- otherwise — pytest's own exit code (timing regression, collection error, …).
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import typer

from .. import run
from ..golden import GoldenStore, iter_baseline_files
from ..logs import work_root
from ..project import BenchmarkConfig, Project
from .golden import orphan_keys


def _baseline_dir(project: Project) -> Path:
    """The gitignored, per-machine directory holding this project's benchmark baselines.

    A benchmark baseline is a *time*, which is hardware-specific, so it is **never
    committed**: it lives under the project's ``work_dir`` (the same transient scratch
    root as the test logs), namespaced by a hash of the repo root so baselines from
    different checkouts never collide.

    Args:
        project: The loaded project (resolves ``work_dir`` and the repo root).

    Returns:
        ``<work_root>/benchmark/<roothash>``.
    """
    root = project.root or Path.cwd()
    digest = hashlib.sha1(str(root).encode()).hexdigest()[:10]
    return work_root(project) / "benchmark" / digest


def _bench_or_exit(project: Project) -> BenchmarkConfig:
    """Return ``project.benchmark`` or exit ``2`` with a clear, actionable message.

    Args:
        project: The loaded project config.

    Returns:
        The project's benchmark configuration.
    """
    if project.benchmark is None:
        typer.secho(
            "benchmark not configured — add BenchmarkConfig to .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project.benchmark


def _bench_opts(project: Project, benchmark: BenchmarkConfig) -> list[str]:
    """Translate :class:`BenchmarkConfig` into the plugin's pytest ``-o`` overrides.

    ``benchmark_dir`` is the **absolute**, gitignored work-dir location (see
    :func:`_baseline_dir`), so the plugin records/reads baselines in exactly the
    directory ``status`` / ``prune`` read — and never inside the committed tree.

    Args:
        project: The loaded project (provides the work dir + repo root).
        benchmark: The benchmark configuration.

    Returns:
        A list of ``-o key=value`` argv pairs.
    """
    return [
        "-o",
        f"benchmark_dir={_baseline_dir(project)}",
        "-o",
        f"benchmark_marker={benchmark.marker}",
        "-o",
        f"benchmark_warmup={benchmark.warmup}",
        "-o",
        f"benchmark_repeat={benchmark.repeat}",
        "-o",
        f"benchmark_rtol={benchmark.rtol}",
    ]


def _pytest_cmd(project: Project, benchmark: BenchmarkConfig) -> list[str]:
    """Build the base pytest argv that selects the benchmark suite.

    The plugin is auto-registered via its ``pytest11`` entry point, so it is **not**
    passed with ``-p`` (that would double-register and crash).

    Args:
        project: The loaded project (provides the env prefix + tests dir).
        benchmark: The benchmark configuration (provides the marker + settings).

    Returns:
        The argv ``<python> -m pytest <tests_dir> -o bench_*=… -m <marker>``.
    """
    prefix = run.python_prefix(project)
    return [
        *prefix,
        "-m",
        "pytest",
        project.test.tests_dir,
        *_bench_opts(project, benchmark),
        "-m",
        benchmark.marker,
    ]


def _parse_nodeids(text: str) -> set[str]:
    """Parse test node ids from ``pytest --collect-only -q`` output (best-effort)."""
    nodeids: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if "::" in line and not line.startswith(("<", "=", "no tests")):
            nodeids.add(line)
    return nodeids


def _collect_nodeids(project: Project, benchmark: BenchmarkConfig) -> set[str] | None:
    """Collect the benchmark suite's node ids, or ``None`` if collection fails."""
    cmd = [
        *run.python_prefix(project),
        "-m",
        "pytest",
        project.test.tests_dir,
        *_bench_opts(project, benchmark),
        "--collect-only",
        "-q",
        "-m",
        benchmark.marker,
    ]
    assert project.root is not None
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project.root),
            env=run.repo_env(project.root),
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    no_tests_collected = 5
    if proc.returncode not in (0, no_tests_collected):
        return None
    return _parse_nodeids(proc.stdout)


def _compare(expr: str | None = None) -> None:
    """Run the benchmark suite as a gate (the default ``pyclawd benchmark`` action)."""
    project = run.load_project_or_exit()
    benchmark = _bench_or_exit(project)
    cmd = _pytest_cmd(project, benchmark)
    if expr:
        cmd += ["-k", expr]
    code = run.run(cmd, project.root)
    # pytest exit 5 = "no tests collected" — a project can configure benchmark before
    # writing any @pytest.mark.benchmark tests. That is not a gate failure; report it
    # cleanly instead of surfacing pytest's bare exit 5.
    no_tests_collected = 5
    if code == no_tests_collected:
        typer.secho("no benchmark tests collected — nothing to gate.", fg="yellow")
        raise typer.Exit(0)
    raise typer.Exit(code)


def update(
    expr: str = typer.Option(
        None,
        "-k",
        metavar="EXPR",
        help="Only bless benchmark tests matching this keyword expression (pytest -k).",
    ),
) -> None:
    """Bless baselines — re-record measured timings on THIS machine (agents only compare).

    Passes ``--benchmark-update`` so the plugin records fresh timings instead of gating.
    Baselines are hardware-specific and **gitignored** — bless them on a quiet machine;
    there is nothing to commit. Never wire this into an autonomous loop.
    """
    project = run.load_project_or_exit()
    benchmark = _bench_or_exit(project)
    cmd = [*_pytest_cmd(project, benchmark), "--benchmark-update"]
    if expr:
        cmd += ["-k", expr]
    code = run.run(cmd, project.root)
    typer.secho(
        f"\nRecorded local benchmark baselines under {_baseline_dir(project)} "
        "(gitignored, machine-specific — nothing to commit).",
        fg="yellow",
    )
    raise typer.Exit(code)


def status() -> None:
    """Show the local-baseline inventory (per file + grand total) and orphans."""
    project = run.load_project_or_exit()
    benchmark = _bench_or_exit(project)
    baseline_dir = _baseline_dir(project)
    files = iter_baseline_files(baseline_dir)

    if not files:
        typer.secho(
            f"no baselines under {baseline_dir} (run `pyclawd benchmark update` on this "
            "machine to record them).",
            fg="yellow",
        )
        raise typer.Exit(0)

    typer.secho(f"Benchmark baselines under {baseline_dir}:", bold=True)
    total = 0
    all_keys: list[str] = []
    for path in files:
        keys = GoldenStore(path).keys()
        total += len(keys)
        all_keys += keys
        typer.echo(f"  {path.name}  ({len(keys)} benchmark{'s' if len(keys) != 1 else ''})")
    typer.secho(f"  total: {total} benchmark{'s' if total != 1 else ''}", fg="green")

    collected = _collect_nodeids(project, benchmark)
    if collected is None:
        typer.secho(
            "  (orphan check skipped — could not collect the benchmark suite)", fg="bright_black"
        )
        raise typer.Exit(0)

    orphans = orphan_keys(all_keys, collected)
    if orphans:
        typer.secho(
            f"\n  {len(orphans)} orphaned entr{'ies' if len(orphans) != 1 else 'y'}:", fg="yellow"
        )
        for key in orphans:
            typer.secho(f"    ⚠ {key}", fg="yellow")
        typer.secho("  run `pyclawd benchmark prune` to remove them.", fg="bright_black")
    else:
        typer.secho("  no orphaned entries.", fg="bright_black")
    raise typer.Exit(0)


def prune() -> None:
    """Remove orphaned baseline entries (test gone) and delete emptied files."""
    project = run.load_project_or_exit()
    benchmark = _bench_or_exit(project)
    baseline_dir = _baseline_dir(project)
    files = iter_baseline_files(baseline_dir)

    if not files:
        typer.secho(f"no baselines under {baseline_dir} — nothing to prune.", fg="yellow")
        raise typer.Exit(0)

    collected = _collect_nodeids(project, benchmark)
    if collected is None:
        typer.secho(
            "prune refused — could not collect the benchmark suite to determine orphans.",
            fg="red",
            err=True,
        )
        raise typer.Exit(1)

    removed = 0
    for path in files:
        store = GoldenStore(path)
        orphans = orphan_keys(store.keys(), collected)
        if not orphans:
            continue
        for key in orphans:
            store.remove(key)
            removed += 1
            typer.secho(f"  ✗ removed {path.name} :: {key}", fg="red")
        if store.is_empty():
            path.unlink()
            typer.secho(f"  ✗ deleted empty {path.name}", fg="red")
        else:
            store.save()

    if removed == 0:
        typer.secho("no orphaned entries — nothing pruned.", fg="green")
    else:
        typer.secho(
            f"\npruned {removed} orphaned entr{'ies' if removed != 1 else 'y'} "
            f"from the local baselines under {baseline_dir}.",
            fg="yellow",
        )
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``benchmark`` command group to *app*.

    The default invocation (``pyclawd benchmark``) compares; ``update`` / ``status`` /
    ``prune`` are subcommands. Always registered — each self-reports and exits ``2``
    when the loaded project does not configure benchmark.
    """
    bench_app = typer.Typer(
        help="Performance-regression oracle: prove the code did not get slower.",
    )

    @bench_app.callback(invoke_without_command=True)
    def _default(
        ctx: typer.Context,
        expr: str = typer.Option(
            None,
            "-k",
            metavar="EXPR",
            help="Only compare benchmark tests matching this keyword expression (pytest -k).",
        ),
    ) -> None:
        """Compare the benchmark suite against the local baselines (the default action)."""
        if ctx.invoked_subcommand is not None:
            return
        _compare(expr)

    bench_app.command()(update)
    bench_app.command()(status)
    bench_app.command()(prune)
    app.add_typer(bench_app, name="benchmark")
