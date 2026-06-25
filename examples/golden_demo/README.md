# golden — worked example

A runnable, end-to-end demonstration of pyclawd's **behavior-regression oracle**.
The static gate (`pyclawd check`: format/lint/typecheck/test) proves code is
*clean*; golden proves behavior is *unchanged*.

The model is dead simple: **tag a test `@pytest.mark.golden` and `return` a value.**
The pytest plugin captures the return value and either compares it against a
committed baseline (the default) or records a new one (`--golden-update`).

**No fixture. No imports. No `.pyclawd/config.py`.** The plugin auto-registers via a
`pytest11` entry point — install pyclawd and the `golden` marker just works in bare
`pytest`. Tests never import pyclawd.

## The files

| File | Role |
|---|---|
| `test_optimize.py` | golden tests — each returns a value the plugin snapshots |
| `golden/test_optimize.json` | the **committed baseline** — readable values + a fast-path hash |
| `pytest.ini` | one line: `golden_dir = golden` (baselines sit adjacent to the tests) |

## The workflow

**1. Compare (the default — fail on drift):**

```
pytest examples/golden_demo
```

**2. Bless (record baselines after an _intentional_ behavior change):**

```
pytest examples/golden_demo --golden-update
git diff examples/golden_demo/golden/   # review the value changes, then commit
```

Blessing is a **human-run, human-reviewed, human-committed** act — never wired into
an autonomous loop's self-gate. The PR diff of the baseline file *is* the record of
what behavior changed and when. **Agents compare; humans bless.**

## A test is just a return value

```python
@pytest.mark.golden
def test_indicator() -> float:
    f = optimize("sphere", seed=7)
    return math.sqrt(float(f @ f))          # a float → a readable number


@pytest.mark.golden
@pytest.mark.parametrize("problem", ["sphere", "rosenbrock"], ids=["sphere", "rosenbrock"])
def test_front(problem: str) -> np.ndarray:
    return optimize(problem, seed=42)        # an np.array → a readable nested list
```

## What a committed baseline looks like

The plugin renders each return value by type — a `float` as a readable rounded
number, an `np.ndarray` as a readable nested list — so a `git diff` shows exactly
which numbers moved. There is no `blessed_on` field; provenance is git's job.

```jsonc
{
  "test_indicator":        { "hash": "sha256:a4ff…", "value": 0.4653799416 },
  "test_front[sphere]":    { "hash": "sha256:82b1…", "value": [0.925444, 0.001444] },
  "test_front[rosenbrock]":{ "hash": "sha256:77ee…", "value": [0.001444, 0.1336341136] }
}
```

The parametrized test produces **one baseline entry per case**, keyed by the pytest
node id (`test_front[sphere]`, `test_front[rosenbrock]`). The inline `value` is what
makes the diff readable; the `hash` is only a fast path in front of the tolerant
comparison.

## The failure transcript (regression caught)

Inject a "clean" edit that changes behavior (e.g. `seed=42 → seed=43`) and the
default run fails with **what** drifted — the changed numbers, not just that
something did:

```
GoldenError: golden: test_front[sphere]
  value drifted beyond tolerance (rtol=1e-09, atol=1e-12)
  baseline: [0.925444, 0.001444]
  actual:   [0.522729, 0.076729]
```

Revert the edit → the run is green again. No baseline was touched.
