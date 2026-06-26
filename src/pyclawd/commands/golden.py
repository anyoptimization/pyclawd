"""Golden command group — ``pyclawd golden`` (the behavior-regression oracle).

The static gate (``pyclawd check``) proves code is *clean*; ``golden`` proves
behavior is *unchanged* by comparing each ``@pytest.mark.golden`` test's **return
value** against a committed snapshot baseline. The engine lives in
:mod:`pyclawd.golden` and the standalone, auto-registered pytest plugin
(:mod:`pyclawd.pytest_plugin`); this module is only the optional CLI wrapper that
drives them and translates :class:`~pyclawd.project.GoldenConfig` into the plugin's
pytest options. The plugin works in bare ``pytest`` with no pyclawd project at all;
these commands are a convenience for projects that *do* use pyclawd.

Subcommands (driven by :class:`~pyclawd.project.GoldenConfig`):

- ``pyclawd golden [-k EXPR]`` (default) — **compare**: run the golden suite as a
  gate, optionally narrowed to matching tests.
- ``pyclawd golden update [-k EXPR]`` — **bless**: re-record baselines (humans
  bless, agents only compare — never wire this into an autonomous self-gate).
- ``pyclawd golden status`` — inventory the committed baselines (+ orphan hint).
- ``pyclawd golden prune`` — drop orphaned baseline entries whose test is gone.
- ``pyclawd golden vendor <file>`` — copy the engine + plugin into a single
  self-contained file so a project runs golden with **zero pyclawd dependency**.

Exit-code contract (agent-native, deterministic):

- ``0`` — success.
- ``2`` — golden not configured for this project.
- otherwise — pytest's own exit code (snapshot drift, collection error, …).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from .. import run
from ..golden import GoldenStore, iter_baseline_files
from ..project import GoldenConfig, Project


def _golden_or_exit(project: Project) -> GoldenConfig:
    """Return ``project.golden`` or exit ``2`` with a clear, actionable message.

    Args:
        project: The loaded project config.

    Returns:
        The project's golden configuration.
    """
    if project.golden is None:
        typer.secho(
            "golden not configured — add GoldenConfig to .pyclawd/config.py",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)
    return project.golden


def _golden_opts(golden: GoldenConfig) -> list[str]:
    """Translate :class:`GoldenConfig` into the plugin's pytest ``-o`` overrides.

    Feeds the auto-registered plugin the project's baseline dir / marker /
    tolerances, so a pyclawd project drives golden from ``.pyclawd/config.py`` while
    the plugin itself stays config-via-pytest-ini for bare-pytest projects.

    Args:
        golden: The golden configuration.

    Returns:
        A list of ``-o key=value`` argv pairs.
    """
    return [
        "-o",
        f"golden_dir={golden.baseline_dir}",
        "-o",
        f"golden_marker={golden.marker}",
        "-o",
        f"golden_precision={golden.precision}",
        "-o",
        f"golden_rtol={golden.rtol}",
        "-o",
        f"golden_atol={golden.atol}",
    ]


def _pytest_cmd(project: Project, golden: GoldenConfig) -> list[str]:
    """Build the base pytest argv that selects the golden suite.

    The plugin is auto-registered via its ``pytest11`` entry point, so it is **not**
    passed with ``-p`` (that would double-register and crash).

    Args:
        project: The loaded project (provides the env prefix + tests dir).
        golden: The golden configuration (provides the marker + tolerances).

    Returns:
        The argv ``<python> -m pytest <tests_dir> -o golden_*=… -m <marker>``.
    """
    prefix = run.python_prefix(project)
    return [
        *prefix,
        "-m",
        "pytest",
        project.test.tests_dir,
        *_golden_opts(golden),
        "-m",
        golden.marker,
    ]


def orphan_keys(store_keys: list[str], collected_nodeids: set[str]) -> list[str]:
    """Return baseline keys whose test case no longer exists among collected node ids.

    A snapshot key is the test node id's last ``::``-segment (e.g.
    ``test_minimize[sphere]``) with an optional ``::label`` suffix (e.g.
    ``test_minimize[sphere]::F``). A key is an **orphan** when its part *before*
    the ``::label`` is not among the last ``::``-segments of the collected node
    ids — i.e. the test that would record it is gone.

    Args:
        store_keys: All recorded baseline keys (across the relevant stores).
        collected_nodeids: Test node ids pytest currently collects for the marker.

    Returns:
        The orphaned keys, in input order.
    """
    live = {nodeid.rsplit("::", 1)[-1] for nodeid in collected_nodeids}
    return [key for key in store_keys if key.split("::", 1)[0] not in live]


def _parse_nodeids(text: str) -> set[str]:
    """Parse test node ids from ``pytest --collect-only -q`` output (best-effort).

    Args:
        text: The captured stdout of a collect-only run.

    Returns:
        The set of node-id lines (those containing ``::``).
    """
    nodeids: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if "::" in line and not line.startswith(("<", "=", "no tests")):
            nodeids.add(line)
    return nodeids


def _collect_nodeids(project: Project, golden: GoldenConfig) -> set[str] | None:
    """Collect the golden suite's node ids, or ``None`` if collection fails.

    Runs ``pytest --collect-only -q -m <marker>`` (the plugin is auto-registered)
    and parses the node-id lines. Returns ``None`` (so callers skip orphan detection
    gracefully) when pytest cannot be launched or exits non-zero.

    Args:
        project: The loaded project (provides the env + root).
        golden: The golden configuration (provides the marker).

    Returns:
        The collected node ids, or ``None`` on any collection failure.
    """
    prefix = run.python_prefix(project)
    cmd = [
        *prefix,
        "-m",
        "pytest",
        project.test.tests_dir,
        *_golden_opts(golden),
        "--collect-only",
        "-q",
        "-m",
        golden.marker,
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
    # pytest exit 5 = "no tests collected" — a valid empty result (e.g. every golden
    # test was removed), NOT a collection failure. Treat it as an empty set so prune
    # can drop the now-orphaned baselines instead of refusing.
    no_tests_collected = 5
    if proc.returncode not in (0, no_tests_collected):
        return None
    return _parse_nodeids(proc.stdout)


# --------------------------------------------------------------------------- #
# Subcommands.
# --------------------------------------------------------------------------- #


def _compare(expr: str | None = None) -> None:
    """Run the golden suite as a gate (the default ``pyclawd golden`` action).

    Args:
        expr: Optional pytest ``-k`` keyword expression to select a subset of
            golden tests to compare.
    """
    project = run.load_project_or_exit()
    golden = _golden_or_exit(project)
    cmd = _pytest_cmd(project, golden)
    if expr:
        cmd += ["-k", expr]
    raise typer.Exit(run.run(cmd, project.root))


def update(
    expr: str = typer.Option(
        None,
        "-k",
        metavar="EXPR",
        help="Only bless tests matching this keyword expression (pytest -k).",
    ),
) -> None:
    """Bless baselines — re-record the golden suite (humans bless; agents compare).

    Passes ``--golden-update`` so the plugin records fresh baselines instead of
    gating. With ``-k EXPR`` only the matched cases are re-blessed, leaving the rest
    untouched. After it runs, **review** ``git diff`` of the baseline dir and commit
    deliberately — never auto-bless in an autonomous loop.
    """
    project = run.load_project_or_exit()
    golden = _golden_or_exit(project)
    cmd = [*_pytest_cmd(project, golden), "--golden-update"]
    if expr:
        cmd += ["-k", expr]
    code = run.run(cmd, project.root)
    typer.secho(
        f"\nReview `git diff {golden.baseline_dir}` and commit the blessed baselines.",
        fg="yellow",
    )
    raise typer.Exit(code)


def status() -> None:
    """Show the committed-baseline inventory (per file + grand total) and orphans.

    Reads every baseline file under ``golden.baseline_dir`` and prints its entry
    count, then a grand total. Best-effort: it also collects the live golden node
    ids and flags any orphaned entries (a test that no longer exists); if
    collection fails it still prints the snapshot inventory.
    """
    project = run.load_project_or_exit()
    golden = _golden_or_exit(project)
    baseline_dir = project.path(golden.baseline_dir)
    files = iter_baseline_files(baseline_dir)

    if not files:
        typer.secho(
            f"no baselines under {baseline_dir} (run `pyclawd golden update`).", fg="yellow"
        )
        raise typer.Exit(0)

    typer.secho(f"Golden baselines under {baseline_dir}:", bold=True)
    total = 0
    all_keys: list[str] = []
    for path in files:
        keys = GoldenStore(path).keys()
        total += len(keys)
        all_keys += keys
        typer.echo(f"  {path.name}  ({len(keys)} snapshot{'s' if len(keys) != 1 else ''})")
    typer.secho(f"  total: {total} snapshot{'s' if total != 1 else ''}", fg="green")

    collected = _collect_nodeids(project, golden)
    if collected is None:
        typer.secho(
            "  (orphan check skipped — could not collect the golden suite)",
            fg="bright_black",
        )
        raise typer.Exit(0)

    orphans = orphan_keys(all_keys, collected)
    if orphans:
        typer.secho(
            f"\n  {len(orphans)} orphaned entr{'ies' if len(orphans) != 1 else 'y'}:", fg="yellow"
        )
        for key in orphans:
            typer.secho(f"    ⚠ {key}", fg="yellow")
        typer.secho("  run `pyclawd golden prune` to remove them.", fg="bright_black")
    else:
        typer.secho("  no orphaned entries.", fg="bright_black")
    raise typer.Exit(0)


def prune() -> None:
    """Remove orphaned baseline entries (test gone) and delete emptied files.

    Collects the live golden node ids, drops every orphaned entry from its store,
    saves modified stores, and deletes any file that becomes empty. Every removal
    is printed — nothing is removed silently. If the suite cannot be collected,
    pruning is refused (exit ``1``) rather than guessing what is orphaned.
    """
    project = run.load_project_or_exit()
    golden = _golden_or_exit(project)
    baseline_dir = project.path(golden.baseline_dir)
    files = iter_baseline_files(baseline_dir)

    if not files:
        typer.secho(f"no baselines under {baseline_dir} — nothing to prune.", fg="yellow")
        raise typer.Exit(0)

    collected = _collect_nodeids(project, golden)
    if collected is None:
        typer.secho(
            "prune refused — could not collect the golden suite to determine orphans.",
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
            f"— review `git diff {golden.baseline_dir}` and commit.",
            fg="yellow",
        )
    raise typer.Exit(0)


def _strip_preamble(src: str, *, drop_future: bool = False, drop_module: str | None = None) -> str:
    """Return *src* with its module docstring (and optionally ``__future__`` / one import) removed.

    Used to splice the engine and plugin into one module: only the merged file's
    leading docstring and single ``from __future__`` survive, and the plugin's
    ``from pyclawd.golden import …`` is dropped because the engine is now inline.

    Args:
        src: Python source.
        drop_future: Also remove the ``from __future__ import annotations`` line.
        drop_module: Also remove a ``from <drop_module> import …`` line.

    Returns:
        The source with those leading lines removed.
    """
    import ast

    tree = ast.parse(src)
    drop: set[int] = set()
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        drop.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    for node in body:
        if not isinstance(node, ast.ImportFrom):
            continue
        is_future = drop_future and node.module == "__future__"
        is_drop_mod = drop_module is not None and node.module == drop_module
        if is_future or is_drop_mod:
            drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return "".join(line for i, line in enumerate(src.splitlines(keepends=True), 1) if i not in drop)


def vendor(
    target: str = typer.Argument(
        ...,
        help="File to vendor the self-contained golden plugin into, e.g. tests/golden_plugin.py.",
    ),
) -> None:
    """Vendor golden as a single self-contained file — zero pyclawd dependency.

    golden's engine (``pyclawd.golden``) is stdlib-only (numpy lazy/optional) and the
    plugin imports only the engine, so the two splice into **one module**. After
    vendoring, a framework runs ``@pytest.mark.golden`` return-capture tests with
    **its own pytest** — pyclawd is never imported, installed, or a dependency.
    Commit the file + your baselines; re-run this to update it.

    Writes one ``<target>.py`` (engine + plugin spliced together) and prints the one
    ``conftest.py`` line to register it.
    """
    import pyclawd

    pkg_root = Path(__file__).resolve().parent.parent  # the installed src/pyclawd/
    version = pyclawd.__version__

    dest = Path(target)
    if dest.suffix != ".py":
        dest = dest.with_suffix(".py")
    dest.parent.mkdir(parents=True, exist_ok=True)
    modpath = ".".join(dest.with_suffix("").parts)

    engine = (pkg_root / "golden.py").read_text()
    plugin = (pkg_root / "pytest_plugin.py").read_text()
    docstring = (
        f'"""Vendored golden (engine + pytest plugin) from pyclawd {version} — do not edit.\n\n'
        f"Self-contained, dependency-free. Register it in your top-level conftest.py with\n"
        f'``pytest_plugins = ["{modpath}"]``, then write ``@pytest.mark.golden`` tests that\n'
        f"``return`` a value. Regenerate with ``pyclawd golden vendor {target}``.\n"
        f'"""\n'
    )
    merged = (
        docstring
        + _strip_preamble(engine)
        + "\n\n# === pytest plugin (spliced from pyclawd.pytest_plugin) ===\n\n"
        + _strip_preamble(plugin, drop_future=True, drop_module="pyclawd.golden")
    )
    dest.write_text(merged)

    typer.secho(
        f"✓ vendored golden into {dest} (one file — dependency-free, no pyclawd)", fg="green"
    )
    typer.echo("\nRegister it in your top-level conftest.py:")
    typer.secho(f'    pytest_plugins = ["{modpath}"]', fg="cyan")
    typer.echo("\nWrite @pytest.mark.golden tests that `return` a value, then bless with:")
    typer.secho("    pytest -m golden --golden-update", fg="cyan")
    typer.secho(
        "\nNote: only vendor in projects that do NOT install pyclawd — running both the "
        "vendored plugin and pyclawd's entry-point plugin double-registers and errors.",
        fg="yellow",
    )
    raise typer.Exit(0)


def register(app: typer.Typer) -> None:
    """Attach the ``golden`` command group to *app*.

    The default invocation (``pyclawd golden``) compares; ``update`` / ``status`` /
    ``prune`` / ``vendor`` are subcommands. Always registered — each self-reports and
    exits ``2`` when the loaded project does not configure golden (``vendor`` needs no
    project).
    """
    golden_app = typer.Typer(
        help="Behavior-regression oracle: compare observable outputs to committed baselines.",
    )

    @golden_app.callback(invoke_without_command=True)
    def _default(
        ctx: typer.Context,
        expr: str = typer.Option(
            None,
            "-k",
            metavar="EXPR",
            help="Only compare golden tests matching this keyword expression (pytest -k).",
        ),
    ) -> None:
        """Compare the golden suite against committed baselines (the default action).

        ``pyclawd golden -k <expr>`` narrows the gate to matching golden tests.
        """
        if ctx.invoked_subcommand is not None:
            return
        _compare(expr)

    golden_app.command()(update)
    golden_app.command()(status)
    golden_app.command()(prune)
    golden_app.command()(vendor)
    app.add_typer(golden_app, name="golden")
