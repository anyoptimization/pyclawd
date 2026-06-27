# Testing doctrine

The tiered test pipeline + the fix-loop. For the exact command surface
(`pyclawd test fast|run|all|failures|fix|timings`, `-k`, nodeid selection) see
the table in `AGENTS.md` — this file is the *why* and the failure taxonomy.

## Test tiers

| Tier | Marker filter | Wall-time | When to run |
|---|---|---|---|
| `fast` | `not slow and not integration` | <30s | After every file change |
| `run` (default) | `not slow` | <5 min | Before opening a PR |
| `all` | _(no filter)_ | uncapped | Nightly / pre-release |

Tiers are marker expressions defined in `TestConfig.markers` in `.pyclawd/config.py`
— nothing is hardcoded. `fast` runs under xdist (`-n auto`).

## Marking — two orthogonal axes

Mark exceptions only. **Never mark a test `fast` or `unit`** — unmarked tests are
fast units and run in **every** tier.

```python
@pytest.mark.slow         # speed axis: test takes >1s
@pytest.mark.integration  # scope axis: needs a live DB / network / filesystem
```

The axes are independent because a test can be fast-but-needs-a-DB or
slow-but-hermetic. Exclude a heavy module from `fast` by marking the tests
themselves (`pytestmark = pytest.mark.slow` at module top) — a real marker, not a
hardcoded skip list.

Find which tests deserve a `slow` marker with `pyclawd test timings --slow-threshold S`
(lists tests slower than S seconds — the marker candidates); `--top N` shows the N
slowest overall.

`--strict-markers` and `--strict-config` are always on, so a typo'd marker errors
immediately. Need a nightly-only third expense tier? Add your own `long` marker and
a `default = "not long"` tier — it's not in the default set.

Distinct from markers: use `pytest.importorskip` / `skipif` when a test should
**skip itself** because an optional dependency or service is absent. That's
orthogonal to tier deselection — the two can apply to the same test.

### `golden` is a separate tier — keep it out of the unit suite

Behavior-regression snapshot tests (`@pytest.mark.golden`) answer "did a number
move?", not "is this logic correct?", and need committed baselines. Exclude them
from every unit tier and run them as their own gate:

```python
"fast":    "not slow and not integration and not golden",
"default": "not slow and not golden",
"all":     "not golden",
```

Run them with `pyclawd golden` (or `pytest -m golden`), never via `pyclawd test`.
See the **pyclawd-golden** skill.

## The fix-loop doctrine

Stop-early to fix, full run to verify:

1. `pyclawd test run` — find what's red.
2. `pyclawd test failures` — see the fix-list (pytest's lastfailed cache).
3. `pyclawd test fix` — rerun only last-failed, stop at the first, full traceback.
4. Fix the **cause**, not the assertion. Then `pyclawd test fix` again. Repeat
   until it passes.
5. `pyclawd test run` — full re-run to confirm nothing else regressed.

## Failure taxonomy

| Failure | Cause + fix |
|---|---|
| Float-equality assertion flaps | Use tolerances — `pytest.approx(expected)` or `np.testing.assert_allclose(..., rtol=, atol=)`, never `== 0.3`. |
| Unseeded stochastic test | Pin the `seed` (e.g. `seed=42`) in the test body, or use `pytest-randomly`, so the run is deterministic. |
| Mass import / collection errors | An **env** problem, not a test bug — run `pyclawd doctor` and fix the FAILs (see the pyclawd-doctor skill). |
| Only `fast` is green, `run` red | A `slow` test broke — run `pyclawd test run` (or `all`) and fix it. |
| Order-dependent tests | Reset all global state in fixtures; never rely on run order. |

## Existing repos with a quality backlog

If `pyclawd check` is already red when you arrive, the repo has pre-existing
lint/format debt. **Don't reformat files you aren't otherwise touching** — it
balloons your diff. Two options:

- **Preferred:** land a one-commit baseline PR first —
  `pyclawd format && pyclawd lint --fix` — zero logic change, makes the gate live
  going forward.
- **If not yet:** scope to changed files only (`pyclawd lint src/mypkg/myfile.py`)
  and note the pre-existing backlog in your PR description.

## Coverage

`pyclawd coverage` measures the suite with pytest-cov, driven by `CoverageConfig`
(`source`, `threshold`, `branch`) in `.pyclawd/config.py`. It is a separate concern
from the tiers — reach for it to find untested code, not on every edit.

- `pyclawd coverage` — measure + print the report.
- `pyclawd coverage --check` — fail under `CoverageConfig.threshold` (the CI gate).
- `pyclawd coverage --html` — write a browsable HTML report.

Ratchet `threshold` toward (or just below) current coverage to prevent regressions
rather than chasing 100%.

## Never

- Weaken or delete a test to make a suite pass.
- Mock internal functions — mock at system boundaries (HTTP, DB, clock) only.
- Leave `pyclawd test run` red.
