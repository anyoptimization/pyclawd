# Packaging + build doctrine

The packaging opinion and the build/dist/clean verbs. For the exact commands see
`AGENTS.md`; this file is the *why*.

## The layout opinion

- **Always `src/` layout** — `src/my_package/` with `tests/` outside it. This
  forces tests to run against the installed package, not the working tree, catching
  packaging mistakes early.
- **Always `pip install -e .`** (editable) during development.
- **Always add `src/my_package/py.typed`** — without it, type checkers ignore your
  annotations downstream.
- **Version via `hatch-vcs`** (git tags → version), exposed via
  `importlib.metadata.version(__name__)`. The scaffold default build backend is
  **hatchling**.

These are defaults, not law — like every pyclawd opinion they live in config and
can be swapped. The verbs stay the same.

## Build / dist / clean — driven by BuildConfig

`pyclawd compile`, `pyclawd dist`, and `pyclawd clean` are configured by a
`BuildConfig | None` at `Project.build`. When `build` is `None`, these verbs
self-report as not-configured and exit 2 — most pure-Python projects need no build
step at all.

`BuildConfig` fields:

| Field | Drives | Meaning |
|---|---|---|
| `compile_cmd` | `pyclawd compile` | Args passed to the dev Python to build in place (e.g. compile Cython/C extensions). |
| `dist_cmd` | `pyclawd dist` | Args passed to the dev Python to build a wheel/sdist. |
| `clean_targets` | `pyclawd clean` | Root-relative paths removed by a normal clean. |
| `clean_ext_dir` | `pyclawd clean --ext` | Root-relative directory holding compiled artifacts. |
| `clean_ext_globs` | `pyclawd clean --ext` | Globs removed under `clean_ext_dir` when `--ext` is passed. |

## `pyclawd clean --ext` is destructive — ask first

A plain `pyclawd clean` removes `clean_targets` (build caches, dist artifacts).
`pyclawd clean --ext` additionally wipes compiled extensions under `clean_ext_dir`
and **forces a full recompile** on the next build — slow, and not something to do
silently in someone's working tree. Confirm with the user before running it.
