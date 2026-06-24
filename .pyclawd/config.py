"""pyclawd's own project config — pyclawd dogfooding pyclawd.

This makes the toolkit runnable on its own repo: ``pyclawd doctor``, ``pyclawd
test fast``, ``pyclawd root``, etc. all operate on pyclawd itself. It is also a
worked, minimal example of a ``.pyclawd/config.py`` for an env-agnostic,
pure-Python project with no compile step and no docs.
"""

from pyclawd import CoverageConfig, DocsConfig, DoctorConfig, Project, QualityConfig, TestConfig

project = Project(
    name="pyclawd",
    conda_env=None,  # env-agnostic — runs in whatever env it's installed into
    root_markers=["pyproject.toml", "src/pyclawd/__init__.py"],
    # The pyclawd this config targets; `pyclawd doctor` WARNs on a minor mismatch.
    pyclawd_version="0.1.0",
    # Pure-python: no compile or dist step, nothing project-specific to clean.
    compile_cmd=[],
    dist_cmd=[],
    clean_targets=["build", "dist"],
    clean_ext_dir="",
    clean_ext_globs=[],
    # Default directory `pyclawd ls` lists (the code/source root) — src-layout repo.
    src_dir="src",
    # Dogfood the docs pipeline on pyclawd itself: the worked ./docs runner builds
    # this repo's docs (install once: `pip install -e ./docs`). Paths default to docs/...
    docs=DocsConfig(runner=["python", "docs/cli.py"]),
    # Dogfood pyclawd's own quality layer: ruff (lint+format) + mypy (typecheck).
    quality=QualityConfig(
        lint_cmd=["ruff", "check"],
        lint_fix_cmd=["ruff", "check", "--fix"],
        format_cmd=["ruff", "format"],
        format_check_cmd=["ruff", "format", "--check", "--quiet"],
        typecheck_cmd=["mypy", "src"],
        check_sequence=["format-check", "lint", "typecheck", "test"],
    ),
    test=TestConfig(
        tests_dir="tests/",
        classname_prefix="tests.",
        integration_files=[],
        # No slow/long tests here, so every tier collects the same suite.
        markers={"fast": "not slow and not integration", "default": "not slow", "all": ""},
    ),
    coverage=CoverageConfig(source=["src/pyclawd"]),
    doctor=DoctorConfig(
        core_deps=["typer", "rich"],
        dev_deps=["pytest", "pytest-xdist", "pytest-cov"],
        tool_files=[],
        # Quality toolchain — probed via `shutil.which` (WARN if absent).
        binaries=[
            ("ruff", "pip install ruff"),
            ("mypy", "pip install mypy"),
        ],
    ),
)
