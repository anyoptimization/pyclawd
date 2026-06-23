"""Reference ``.pyclawd/config.py`` — every knob, annotated.

This is the **kitchen-sink** example: a fictional compiled-extension project
("acme") that also builds docs, so it exercises the *full* :class:`pyclawd.Project`
surface — compile/dist/clean, a `DocsConfig`, tiered + integration test markers,
scoped quality commands, and a custom ``extra_doctor_checks`` hook.

Most projects need far less. For the minimal end of the spectrum see pyclawd's own
``.pyclawd/config.py`` (env-agnostic, no compile, no docs). Copy whichever is
closer and delete what you don't use — unset groups disable their commands cleanly.

This file is **documentation, not a live config**: it lives under ``examples/`` so
pyclawd never auto-discovers it (walk-up only looks for ``.pyclawd/config.py``). A
unit test loads it via ``--config`` to guarantee it stays valid.
"""

from __future__ import annotations

from pyclawd import (
    FAIL,
    OK,
    WARN,
    Check,
    DocsConfig,
    DoctorConfig,
    Project,
    QualityConfig,
    TestConfig,
)


# --------------------------------------------------------------------------- #
# Optional: project-specific doctor checks.
#
# `extra_doctor_checks` is a zero-arg callable returning a list of `Check`s that
# `pyclawd doctor` appends to its report. Use it for anything generic probes can't
# express — here, "is the package importable?" and "are the C extensions built?".
# A raising hook is caught and shown as a single FAIL row, never a crash.
# --------------------------------------------------------------------------- #
def acme_doctor_checks() -> list[Check]:
    """Return acme-specific health checks (import status + compiled extensions)."""
    import importlib
    import os

    try:
        acme = importlib.import_module("acme")
    except Exception as exc:  # noqa: BLE001 - report any import failure as a row
        return [Check(FAIL, "acme", f"not importable ({type(exc).__name__})")]

    where = os.path.dirname(acme.__file__)
    checks = [Check(OK, "acme", f"{getattr(acme, '__version__', '?')} @ {where}")]
    try:
        from acme.functions import is_compiled  # type: ignore[import-not-found]

        active = is_compiled()
        checks.append(
            Check(OK, "compiled ext", "Cython extensions active")
            if active
            else Check(WARN, "compiled ext", "pure-Python (slow) — run `pyclawd compile`")
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(Check(WARN, "compiled ext", f"undetermined ({type(exc).__name__})"))
    return checks


project = Project(
    # --- identity --------------------------------------------------------- #
    name="acme",
    # Conda env pyclawd expects to run in. `None` = env-agnostic (runs in whatever
    # env pyclawd is installed into). `pyclawd doctor` WARNs on a mismatch.
    conda_env="acme-dev",
    # Files that should exist at the repo root — a sanity check for `pyclawd doctor`.
    root_markers=["acme/__init__.py", "setup.py"],
    # How `pyclawd python` / `test` / `compile` launch Python. One argv spans every
    # backend; the PYCLAWD_PYTHON env var overrides it at runtime. Leave as [] to use
    # pyclawd's own interpreter (install pyclawd into the env you develop in). Examples:
    #   []                                       -> sys.executable (default)
    #   [".venv/bin/python"]                     -> a project venv
    #   ["conda", "run", "-n", "acme-dev", "python"]  -> one pyclawd, many conda envs
    #   ["uv", "run", "python"]                  -> uv-managed env
    python_cmd=[],
    # --- build / dist / clean (omit any for a pure-Python project) --------- #
    # Args handed to the dev Python: `pyclawd compile` → `python setup.py build_ext ...`.
    compile_cmd=["setup.py", "build_ext", "--inplace"],
    dist_cmd=["setup.py", "sdist"],
    # `pyclawd clean` removes these root-relative paths (guarded to stay in-repo).
    clean_targets=["build", "dist", "acme.egg-info"],
    # `pyclawd clean --ext` removes these globs under this dir (forces a recompile).
    clean_ext_dir="acme/functions/compiled",
    clean_ext_globs=["*.c", "*.cpp", "*.so", "*.html"],
    # Default directory `pyclawd ls` lists (the code/source root), relative to root.
    src_dir="acme",
    # --- code quality (lint / format / typecheck / check) ----------------- #
    # Each verb is an explicit argv, so the toolchain is fully project-driven.
    # Scope the args (e.g. "acme") to avoid linting vendored/build dirs.
    quality=QualityConfig(
        lint_cmd=["ruff", "check", "acme"],
        lint_fix_cmd=["ruff", "check", "--fix", "acme"],
        format_cmd=["ruff", "format", "acme"],
        format_check_cmd=["ruff", "format", "--check", "acme"],
        typecheck_cmd=["mypy", "acme"],
        # `pyclawd check` runs these verbs in order, fail-fast (this is the default).
        check_sequence=["format-check", "lint", "typecheck", "test"],
    ),
    # --- tests ------------------------------------------------------------- #
    test=TestConfig(
        tests_dir="tests/",
        # junit emits dotted classnames (tests.algorithms.test_x); this prefix lets
        # pyclawd rebuild path-ish nodeids (tests/algorithms/test_x.py::name).
        classname_prefix="tests.",
        # Files that are their own integration suites; the unit tiers deselect them
        # and `pyclawd test failures` lists their stale cache entries separately.
        integration_files=["tests/test_examples.py", "tests/test_docs.py"],
        # Tier name → pytest -m expression. Only the tiers you define exist; an
        # undefined tier simply applies no -m filter (it is not an error to omit one).
        markers={
            "default": "not examples and not docs and not long",
            "fast": "not examples and not docs and not long and not slow",
            "all": "not examples and not docs",
            "examples": "examples",
            "docs": "docs",
        },
    ),
    # --- docs (set to None — the default — for a project with no docs) ----- #
    # `runner` is delegated to for build/run/compile/exec/clean. The timings/failures
    # views additionally assume a jupyter-cache backend at `cache_db` (see DocsConfig).
    docs=DocsConfig(
        runner=["uvx", "--from", "./docs", "acme-docs"],
        source_dir="docs/source",
        cache_dir="docs/.jupyter_cache",
        cache_db="docs/.jupyter_cache/global.db",
        build_html="docs/build/html",
        branch="main",
    ),
    # --- doctor (env health-check) ---------------------------------------- #
    doctor=DoctorConfig(
        # Imports that MUST succeed (a missing one is a FAIL).
        core_deps=["numpy", "scipy"],
        # Dev/docs imports (a missing one only WARNs).
        dev_deps=["pytest", "nbformat"],
        # Root-relative files that must exist and be executable (wrapper shims, etc.).
        tool_files=[],
        # System binaries probed via shutil.which, as (name, install-hint) pairs.
        binaries=[("pandoc", "conda install -c conda-forge pandoc")],
    ),
    # Wire the custom hook from the top of this file.
    extra_doctor_checks=acme_doctor_checks,
)
