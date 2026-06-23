# docs/ — the worked example of a `pyclawd docs` toolchain

This directory is an **isolated docs project** (its own `pyproject.toml` + deps),
invoked by pyclawd as `uvx --from ./docs pyclawd-docs <verb>`. It exists so the
`pyclawd docs` pipeline has a real, in-tree example — for humans *and* agents to
see exactly how a docs runner plugs into pyclawd.

## The contract (what pyclawd expects of any runner)

`pyclawd/commands/docs.py` is a thin orchestrator: it forwards verbs to
`project.docs.runner` and reads a few well-known paths. A runner must implement:

| pyclawd command | runner invocation | does |
|---|---|---|
| `pyclawd docs compile` | `pyclawd-docs compile [pages]` | `.md` → `.ipynb` (no execution) |
| `pyclawd docs run` | `pyclawd-docs compile` then `run [pages]` | execute notebooks, cache results |
| `pyclawd docs build` | `pyclawd-docs all [--continue]` | compile → run → render HTML |
| `pyclawd docs build --fast` | `pyclawd-docs build --fast` | render only (no notebooks) |
| `pyclawd docs render` | `pyclawd-docs build` | render HTML from cached notebooks |
| `pyclawd docs exec <page>` | `pyclawd-docs exec <page>` | execute ONE, stream the error |
| `pyclawd docs clean` | `pyclawd-docs clean` | drop `build/` + generated `.ipynb` |

And it must honor the paths declared in `.pyclawd/config.py`'s `DocsConfig`:

- `source_dir` = `docs/source` — the `.md`/`.rst` sources.
- `cache_db` = `docs/.jupyter_cache/global.db` — the **jupyter-cache** store that
  `pyclawd docs timings` / `failures` read directly (this is the one hard
  dependency: those two views assume a jupyter-cache backend).
- `build_html` = `docs/build/html` — where `pyclawd docs serve` looks for `index.html`.

## The stack here

`jupytext` (`.md` → `.ipynb`) → `jupyter-cache` (execute + cache, skip unchanged)
→ `sphinx` + `nbsphinx` (render). `nbsphinx` shells out to the **pandoc** system
binary. All heavy deps live in *this* project's `pyproject.toml`, never in pyclawd.

The whole runner is one file, [`cli.py`](cli.py) (~150 lines) — start there. A real
project would add a theme, its own package, and more pages; the shape stays the same.

## Try it

```bash
pyclawd docs status      # what changed vs main
pyclawd docs build       # compile -> run -> render (first run fetches deps via uvx)
pyclawd docs serve       # http://localhost:8000
pyclawd docs timings     # per-notebook execution times (from the cache)
```
