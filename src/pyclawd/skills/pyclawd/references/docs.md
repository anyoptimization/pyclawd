# Docs pipeline doctrine

> **Gated on `DocsConfig`.** The `pyclawd docs` group is only registered when the
> project sets `DocsConfig` in `.pyclawd/config.py`. If it's absent, the project
> has no docs and this file does not apply — `pyclawd docs` self-reports and exits
> 2. For most projects this is N/A.

A cached documentation pipeline. For the command list
(`pyclawd docs build|run|render|status|failures|exec <page>|timings|serve|compile|clean`)
see `AGENTS.md`; this file is the model and the debug loop.

## Execute vs render — the central split

`build` = **run** (execute notebooks) + **render** (Sphinx HTML). They are separate
steps because **execution is cached** and rendering is cheap:

- `pyclawd docs run [pages…]` — execute notebooks only, no HTML.
- `pyclawd docs render` — render HTML only, no execution.
- `pyclawd docs build` — both.

Fix a render-only problem and re-`render` in seconds without paying re-execution.

## Notebook caching (jupyter-cache)

Caching is keyed on **code cells**: prose-only edits never re-execute; only changed
code re-runs. The cache (at `DocsConfig.cache_db`) stores **only successes**, so a
failed page stays uncached and the next `build` re-runs only it. `pyclawd docs
status` shows what *would* re-run; `pyclawd docs timings` shows the slowest
notebooks.

## The runner contract

Execution + render are delegated to a `./docs` runner declared in
`DocsConfig.runner` (e.g. sphinx + nbsphinx via uvx or an installed CLI).
`render` additionally needs the `pandoc` system binary. `pyclawd docs failures`
imports `jupyter_cache` + `nbformat` in this env.

## The fix-loop

1. `pyclawd docs build` — see what fails.
2. `pyclawd docs failures` — the fix-list with reasons.
3. `pyclawd docs exec <page>` — run that one page directly for the full stacktrace
   (no cache).
4. Fix the **source** (`.md`/source — never a generated `.ipynb`), `exec` again,
   move to the next.
5. `pyclawd docs build` — re-run; only the still-broken pages execute.

## Common fixes

| Symptom | Fix |
|---|---|
| Missing dependency in a notebook | Add it to the docs env declared in `DocsConfig.runner`. |
| Per-cell timeout | Raise the timeout (e.g. the project's docs timeout env var). |
| Render fails but execution was fine | Re-`render` only — don't pay re-execution. |
| Edited the wrong file | Edit the source (`.md`), never the generated notebook. |
| **Edited the runner but `uvx` runs stale code** (`invalid choice`, old behavior persists after edits) | `uvx --from ./docs` caches the built wheel **by version, not content**. Bump the runner's version, run with `--refresh-package <name>`, or use a non-uvx `runner` (e.g. `["python", "docs/cli.py"]`) while iterating. |
