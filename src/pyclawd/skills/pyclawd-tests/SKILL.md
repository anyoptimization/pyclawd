---
name: pyclawd-tests
description: Run pyclawd's tiered test suites and drive the `--lf` fix-loop until green. Covers `pyclawd test fast|run|all`, keyword/nodeid selection, and the failures → fix → fix-the-cause → run doctrine, plus a failure taxonomy (float-equality, unseeded stochastic, mass import errors). Use when running tests, when a test fails, when adding or adjusting tests, or for a quick smoke check.
when_to_use: Running tests, a test is failing, adding/changing tests or markers, or you need a fast confidence check before declaring work done.
---

# pyclawd-tests

Tiered test pipeline with a fix-loop. Tiers are marker expressions defined in the project's `.pyclawd/config.py` (`TestConfig.markers`); the runner logs and instruments each run.

## Commands

| Task | Command |
|---|---|
| Fast smoke tier (<30s, xdist `-n auto`, excludes slow+integration) | `pyclawd test fast` |
| Default gate (everything but `slow`) | `pyclawd test run` |
| Everything, including `slow` | `pyclawd test all` |
| The fix-list (pytest lastfailed cache) | `pyclawd test failures` |
| Debug the next failure (rerun `--lf -x`, stream it) | `pyclawd test fix` |
| Slowest tests from the last run | `pyclawd test timings [--top N] [--slow-threshold S]` (S secs → `slow` candidates) |
| Select by keyword | `pyclawd test -k <name>` |
| Select a file / node / dir | `pyclawd test tests/path::name -x` · `pyclawd test tests/sub/` |

## The fix-loop doctrine

Stop-early to fix, full run to verify:

1. `pyclawd test run` — find what's red.
2. `pyclawd test failures` — see the fix-list.
3. `pyclawd test fix` — rerun only last-failed, stop at the first, full traceback.
4. Fix the **cause**, then `pyclawd test fix` again. Repeat until it passes.
5. `pyclawd test run` — full re-run to confirm nothing else regressed.

## Failure taxonomy

| Failure | Fix |
|---|---|
| Float-equality assertion flaps | Use tolerances — `np.testing.assert_allclose(..., rtol=, atol=)`, not `==`. |
| Unseeded stochastic test | Pin the `seed` so the run is deterministic. |
| Mass import / collection errors | An env problem, not a test bug — run `pyclawd doctor`, fix the FAILs. |
| Only `fast` is green, `run` red | A `slow` test broke — run `pyclawd test run` (or `all`) and fix it. |

## Tiering

Two orthogonal marker axes: **speed** (`slow`, >1s) and **scope** (`integration`, needs a live DB/network/filesystem). Unmarked tests are fast units and run in every tier. Exclude a heavy module from `fast` by marking the tests themselves (`pytestmark = pytest.mark.slow` at module top) — a real marker, not a hardcoded list. `fast` excludes `slow`+`integration`; `run` (default) excludes `slow`; `all` includes everything. (For a nightly-only third expense tier, add your own `long` marker + a `default = "not long"` tier — it's not in the default set.) Use `pytest.importorskip` for tests that should skip themselves when an optional dependency is absent — orthogonal to tier markers.
