---
name: pyclawd-docs
description: Drive pyclawd's documentation pipeline — build/render docs, debug a failing doc page, and reason about the execute-vs-render split and notebook caching. Covers `pyclawd docs build|run|render|status|failures|exec <page>|serve`. Only relevant when the project configures docs (`DocsConfig`). Use when building docs or a doc page fails to execute.
when_to_use: Building or serving documentation, a doc notebook fails to execute or render, or editing doc sources — and the project has docs configured (`pyclawd docs` is registered).
---

# pyclawd-docs

Cached documentation pipeline. The `pyclawd docs` group is only registered when the project sets `DocsConfig` in `.pyclawd/config.py`; if it's absent, the project has no docs and this skill does not apply.

## Commands

| Task | Command |
|---|---|
| Build everything (cached) | `pyclawd docs build` |
| What would re-run | `pyclawd docs status` |
| Execute notebooks only (no HTML) | `pyclawd docs run [pages…]` |
| Render HTML only (no execute) | `pyclawd docs render` |
| Debug ONE page (direct stacktrace, no cache) | `pyclawd docs exec <page>` |
| What failed + why | `pyclawd docs failures` |
| Slowest notebooks | `pyclawd docs timings` |
| Serve built HTML | `pyclawd docs serve` |
| Compile / clean docs artifacts | `pyclawd docs compile` · `pyclawd docs clean` |

## Execute vs render

`build` = **run** (execute notebooks) + **render** (Sphinx HTML). They're separate because **execution is cached**: fix a render-only problem and re-`render` in seconds without re-executing. Caching is keyed on code cells — prose-only edits never re-execute; only changed code re-runs.

## The fix-loop

The cache stores **only successes**, so a failed page stays uncached and the next `build` re-runs only it.

1. `pyclawd docs build` — see what fails.
2. `pyclawd docs failures` — the fix-list with reasons.
3. `pyclawd docs exec <page>` — run that one page directly for the full stacktrace.
4. Fix the source (edit the `.md`/source — never a generated `.ipynb`), `exec` again, move to the next.
5. `pyclawd docs build` — re-run; only the still-broken pages execute.

## Common fixes

| Symptom | Fix |
|---|---|
| Missing dependency in a notebook | Add it to the docs env declared in `DocsConfig.runner`. |
| Per-cell timeout | Raise the timeout (e.g. the project's docs timeout env var). |
| Render fails but execution was fine | Re-`render` only — don't pay re-execution. |
| Edited the wrong file | Edit the source (`.md`), never the generated notebook. |
| **Edited the runner but `uvx` runs stale code** (`invalid choice`, old behavior persists after edits) | `uvx --from ./docs` caches the built wheel **by version, not content**. Bump the runner's version, run with `--refresh-package <name>`, or use a non-uvx `runner` (e.g. `["python", "docs/cli.py"]`) while iterating. |
