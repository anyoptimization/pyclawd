"""Test commands: ``test`` (the pipeline verbs) and ``pytest`` (passthrough).

The heavy pipeline logic lives in :mod:`pyclawd.tests`; these functions are only
the Typer wiring that parses the verb/category and forwards to it.
"""

from __future__ import annotations

import typer

from .. import run, tests

# Commands that forward unknown args/options straight to a subprocess.
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


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
      pyclawd test run            full default suite (not long) → run-id log + timing/failure tables
      pyclawd test fast           the <30s smoke tier (not slow, not long), under xdist (-n auto)
      pyclawd test all            everything, including `long`
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

    if verb in {"run", "fast", "all", "failures", "timings", "fix"}:
        raise typer.Exit(tests.dispatch(verb, args[1:]))

    project = run.load_project_or_exit()
    tier_markers = project.test.markers

    # A leading arg is a category iff the project actually defines that marker tier —
    # so recognised categories are config-driven, not a hardcoded examples/docs set.
    category = "default"
    if verb in tier_markers:
        category = args.pop(0)

    markers = tier_markers.get(category, "")
    raise typer.Exit(run.pytest(args, default_markers=markers, tests_dir=project.test.tests_dir))


def register(app: typer.Typer) -> None:
    """Attach the test commands to *app*."""
    app.command(context_settings=_PASSTHROUGH)(pytest)
    app.command(context_settings=_PASSTHROUGH)(test)
