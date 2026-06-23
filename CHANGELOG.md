# Changelog

All notable changes to pyclawd are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and pyclawd aims to follow
[Semantic Versioning](https://semver.org/) once it reaches 1.0.

While pyclawd is pre-1.0, **a `0.x` minor bump may include breaking changes** to
the config model (`Project` and the nested `*Config`s). A project records the
pyclawd it was built on via `Project.pyclawd_version`; `pyclawd doctor` WARNs when
the running pyclawd has a different `major.minor`, pointing here for what changed.

## [Unreleased]

### Added
- `Project.work_dir` (+ `$PYCLAWD_WORK_DIR`) — a configurable per-project working
  directory for pyclawd's transient files; run logs live under
  `<work_dir>/logs/<category>/` instead of a hardcoded `/tmp/pyclawd`. `pyclawd
  doctor` shows the resolved **work dir** row. A docs example lives in `docs/`.
- `Project.pyclawd_version` — the pyclawd a config was authored against (stamped by
  `pyclawd new`); `pyclawd doctor` reports a **pyclawd compat** row and WARNs on a
  `major.minor` mismatch so migrations are visible, not silent.
- `Project.python_cmd` + the `PYCLAWD_PYTHON` env var — a configurable interpreter
  (venv / `conda run` / `uv run` / `sys.executable`); `pyclawd doctor` shows the
  resolved **python exec** row.
- `pyclawd doctor` now reports a **pyclawd** row (version + install location, with
  an `(editable)` marker) so you can tell which pyclawd is driving a project.

### Changed
- The version is now single-sourced from `src/pyclawd/__init__.py::__version__`
  (hatchling `dynamic = ["version"]`), removing the duplicated `pyproject` string.

## [0.1.0]

- Initial generic core: config model + discovery, and the `test` / `quality`
  (`check`) / `build` / `docs` / `doctor` / `new` / `skills` / `ls` commands.
