"""Test commands: ``test`` (the pipeline verbs) and ``pytest`` (passthrough).

The heavy pipeline logic lives in :mod:`pyclawd.tests`; these functions are only
the Typer wiring that parses the verb/category and forwards to it.
"""

from __future__ import annotations

import typer

from .. import run, tests
from . import _PASSTHROUGH

# The built-in pipeline sub-verbs (logged/instrumented runners + views). Anything
# else leading the args is either a config-defined category tier or pytest passthrough.
_SUB_VERBS = ("run", "fast", "all", "changed", "failures", "timings", "fix")


def _looks_like_pytest_arg(token: str) -> bool:
    """True if *token* is a pytest target/flag rather than a category name.

    Paths (``tests/foo.py``), nodeids (``...::name``), and flags (``-k``, ``-x``,
    ``-m``) must pass straight through to pytest. A bare word with none of these
    markers is treated as a (possibly mistyped) category instead.
    """
    return token.startswith("-") or "/" in token or "::" in token or ".py" in token


def pytest(ctx: typer.Context) -> None:
    """Run pytest over tests/ (excludes `long` unless you pass your own `-m`)."""
    project = run.load_project_or_exit()
    raise typer.Exit(
        run.pytest(
            ctx.args,
            default_markers=project.test.markers.get("default"),
            tests_dir=project.test.tests_dir,
        )
    )


def test(ctx: typer.Context) -> None:
    """Run tests. Verbs mirror `pyclawd docs`; otherwise run a category/pytest passthrough.

    Pipeline verbs (logged, instrumented):
      pyclawd test run            full default suite (not slow) → run-id log + timing/failure tables
      pyclawd test fast           the <30s smoke tier (not slow/integration), xdist (-n auto)
      pyclawd test all            everything, including `slow`
      pyclawd test changed        only tests whose coverage hits the working diff
                                  (impact selection; --against REF, --list to preview)
      pyclawd test failures       the fix-list (pytest lastfailed cache)
      pyclawd test timings [--top N]   slowest tests from the last run
      pyclawd test fix            debug primitive: rerun --lf -x, stream the next failure

    Category / passthrough:
      pyclawd test                the default tier
      pyclawd test <category>     any tier defined in TestConfig.markers (e.g. a
                                  project's "examples"/"docs" integration suites)
      pyclawd test -k name   ·   pyclawd test path::name -x
    """
    args = list(ctx.args)
    verb = args[0] if args else None

    if verb in _SUB_VERBS:
        raise typer.Exit(tests.dispatch(verb, args[1:]))

    project = run.load_project_or_exit()
    tier_markers = project.test.markers

    # A leading arg is a category iff the project actually defines that marker tier —
    # so recognised categories are config-driven, not a hardcoded examples/docs set.
    category = "default"
    if verb in tier_markers:
        category = args.pop(0)
    elif verb is not None and not _looks_like_pytest_arg(verb):
        # A bare leading word that is neither a known category/sub-verb nor a pytest
        # target (path/nodeid/flag) is almost certainly a mistyped category. Fail
        # clean at the pyclawd level instead of letting pytest emit a confusing
        # "file or directory not found: <word>".
        categories = sorted(set(tier_markers) | set(_SUB_VERBS))
        typer.echo(
            f"pyclawd test: unknown category {verb!r}.\n"
            f"Valid categories: {', '.join(categories)}.\n"
            f"For pytest passthrough pass a path, nodeid, or flag "
            f"(e.g. `pyclawd test -k EXPR` or `pyclawd test tests/foo.py::name`).",
            err=True,
        )
        raise typer.Exit(2)

    markers = tier_markers.get(category, "")
    raise typer.Exit(run.pytest(args, default_markers=markers, tests_dir=project.test.tests_dir))


def register(app: typer.Typer) -> None:
    """Attach the test commands to *app*."""
    app.command(context_settings=_PASSTHROUGH)(pytest)
    app.command(context_settings=_PASSTHROUGH)(test)
