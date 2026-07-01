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
- **`pyclawd test changed`** — impact-scoped test selection. Reverse-maps the working
  diff to the tests whose coverage intersects the changed lines and runs only those,
  turning a whole-suite gate into a handful of targeted tests. Build the per-test
  context map once with the new **`pyclawd coverage --context`** flag
  (`--cov-context=test`). Changed files with no covering test (new/untested code) are
  reported loudly, never silently skipped. `--against REF` diffs against a ref;
  `--list` prints the impacted node ids without running.
- **`pyclawd benchmark`** — a performance-regression oracle (sibling of `golden`). Tag
  a test `@pytest.mark.benchmark`; its body is timed (warm-up + best-of-N) and gated
  against a baseline at a relative tolerance — only a slow-down fails. Baselines are
  hardware-specific, so they are **never committed**: they live in the gitignored
  `work_dir` and `benchmark` compares against *your* last blessed run on *this*
  machine. Subcommands `update` / `status` / `prune`; standalone pytest plugin
  (`benchmark_plugin`) auto-registers via a `pytest11` entry point. New
  `BenchmarkConfig`.
- **`pyclawd api`** — a public-API surface oracle. Statically extracts (via `ast`, no
  import) each package's public surface — `__all__` or non-underscore
  functions/classes/methods/constants with signatures — and diffs it against a
  committed text baseline. Removals and signature changes fail (breaking); pure
  additions pass unless `strict`. `update` blesses, `status` shows drift. New
  `ApiConfig`; the diff reads like an API changelog.

### Added
- **`pyclawd docs validate`** + an automatic guardrail in `pyclawd docs build` —
  fail the build when a notebook that executed *with* output renders to HTML
  *without* it (the empty-page failure mode, where `nbsphinx_execute='never'`
  renders whatever output state is on disk and a render that races ahead of
  hydration ships blank cells). Compares each executed `.ipynb` under
  `docs.source_dir` against its rendered page under `docs.build_html`; false-
  positive resistant (output-free pages assert nothing) and skips pages not
  rendered in the run (`--changed`). `docs validate` runs the same check against
  an already-built tree, for use as a standalone pre-deploy gate.
- **`pyclawd web`** — an optional live, multi-project **diff & review dashboard**
  (`pip install 'pyclawd[web]'`, then `pyclawd web serve`). Watch changes across all
  your repos while agents work, compare any two refs (working tree ↔ branch/tag/SHA)
  in inline/split/full views, stage line comments and send them straight into a
  running `claude` tmux pane. The core install stays `typer`+`rich`: the web stack
  (FastAPI/uvicorn/watchfiles) is an extra, and the React frontend is **prebuilt
  into the wheel** so end users never need Node. Live updates use SSE backed by a
  filesystem watch (no polling), with a content-aware change token that reacts even
  to repeated edits of one already-modified file. Manage the project set with
  `pyclawd web add/list/remove`.
- **`PYCLAWD_DISCOVERY`** — an `os.pathsep`-separated search path of config
  directories for walk-up discovery (default: `.pyclawd`). Setting
  `".local/.pyclawd:.pyclawd"` lets a project keep its config **uncommitted** at
  `<repo>/.local/.pyclawd/config.py` (gitignore `.local/`) while `Project.root`
  still resolves to the repo. Because the entries are *relative*, one global value
  is safe across many repos and concurrent projects — resolution stays per-cwd
  (unlike pointing `PYCLAWD_CONFIG` at a fixed absolute path). `pyclawd config`
  shows the effective search path.
- **Agent-driven upgrade flow** for when pyclawd itself is updated:
  - `pyclawd version` now also reports the version a project's config was authored
    against (`Project.pyclawd_version`) and whether it matches the running pyclawd —
    with a `--json` form for agents.
  - `pyclawd changelog [--since VERSION] [--full]` prints what changed (defaulting to
    "since this config's `pyclawd_version`"). The CHANGELOG ships inside the wheel, so
    it works from any pip-installed pyclawd.
  - A bundled **`pyclawd-upgrade`** skill drives the migration: read the changelog,
    update `.pyclawd/config.py`, re-stamp the version, refresh skills, verify green.
  - The `pyclawd doctor` compat WARN now points at `pyclawd changelog` + the skill.
- `pyclawd skills install` now **auto-refreshes drifted skills**: an installed
  user-scope skill whose content differs from the running pyclawd's bundled version
  is re-copied without needing `--force` (identical ones are still skipped), so a
  pyclawd upgrade propagates to `~/.claude/skills`. It reports `installed /
  refreshed / skipped` counts. `pyclawd doctor` adds a **skills** row that WARNs
  when an installed skill has gone stale (and stays silent when none are installed).
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
- **Build fields grouped into a new `BuildConfig` (breaking config change).** The
  five loose top-level build knobs — `compile_cmd`, `dist_cmd`, `clean_targets`,
  `clean_ext_dir`, `clean_ext_globs` — have moved off `Project` into a new frozen
  `BuildConfig` dataclass, reached via `Project.build` (a `BuildConfig | None`,
  default `None`). Migrate `Project(compile_cmd=…, clean_targets=…, …)` to
  `Project(build=BuildConfig(compile_cmd=…, clean_targets=…, …))`; `BuildConfig` is
  exported from `pyclawd` alongside the other `*Config`s. When `Project.build` is
  `None` the `compile` / `dist` / `clean` commands self-report and exit 2 (the same
  0/2 contract as before). This is a clean break — there is no compatibility shim.
- **Scaffolded `check_sequence` now includes the `descriptions` step** — `pyclawd
  new` writes `["format-check", "lint", "typecheck", "descriptions", "test"]`, so a
  freshly scaffolded project enforces the file-description code-map doctrine out of
  the box, matching pyclawd's own dogfood config.
- **Test taxonomy aligned to two marker axes** — *speed* (`slow`) and *scope*
  (`integration`) — with a canonical tier ladder (`fast = not slow and not
  integration`, `default = not slow`, `all =` everything). The `long` marker is
  dropped from the default (documented as an opt-in extra tier). All surfaces now
  agree: dogfood `tests/pytest.ini` (now `--strict-markers`/`--strict-config`),
  the scaffold, `AGENTS.md`, `README.md`, and the skills. `TestConfig.integration_files`
  is clarified as a lastfailed-cache helper, not a second "integration" concept.
- **Docstring convention made honest** — the inert `DOC` (pydoclint) ruff selection
  is dropped (it only runs under unstable `preview`); the rule set is now
  `E F I B UP SIM C4 RUF PGH D`, consistent between dogfood and scaffold. The core
  modules' docstrings were converted from NumPy to Google style, and the docs no
  longer claim NumPy "fails lint" (the Google convention is upheld by `D` rules +
  review).
- `pyclawd compile` / `dist` now exit `2` (not `0`) when unconfigured, matching the
  0/2 contract used by every other command group.
- `pyclawd doctor` validates `root_markers` exist at the detected root (previously
  declared but unused), and config-load errors at every CLI boundary surface as a
  clean exit `2` instead of a possible traceback.
- The version is now single-sourced from `src/pyclawd/__init__.py::__version__`
  (hatchling `dynamic = ["version"]`), removing the duplicated `pyproject` string.

## [0.1.0]

- Initial generic core: config model + discovery, and the `test` / `quality`
  (`check`) / `build` / `docs` / `doctor` / `new` / `skills` / `ls` commands.
