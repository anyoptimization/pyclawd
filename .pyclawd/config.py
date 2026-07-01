"""pyclawd's own project config — pyclawd dogfooding pyclawd.

This makes the toolkit runnable on its own repo: ``pyclawd doctor``, ``pyclawd
test fast``, ``pyclawd root``, etc. all operate on pyclawd itself. It is also a
worked, minimal example of a ``.pyclawd/config.py`` for an env-agnostic,
pure-Python project with no compile step and no docs.
"""

from pyclawd import (
    ApiConfig,
    BenchmarkConfig,
    BuildConfig,
    CoverageConfig,
    DocsConfig,
    DoctorConfig,
    GoldenConfig,
    Project,
    QualityConfig,
    TestConfig,
)

project = Project(
    name="pyclawd",
    conda_env=None,  # env-agnostic — runs in whatever env it's installed into
    root_markers=["pyproject.toml", "src/pyclawd/__init__.py"],
    # The pyclawd this config targets; `pyclawd doctor` WARNs on a minor mismatch.
    pyclawd_version="0.1.0",
    # Pure-python: no compile or dist step, just the build/dist dirs to clean.
    build=BuildConfig(clean_targets=["build", "dist"]),
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
        typecheck_cmd=["mypy"],  # target-less: mypy reads files=["src"] from pyproject.toml
        check_sequence=["format-check", "lint", "typecheck", "descriptions", "test"],
    ),
    test=TestConfig(
        tests_dir="tests/",
        classname_prefix="tests.",
        integration_files=[],
        # golden + benchmark are their own gates (`pyclawd golden` / `pyclawd
        # benchmark`), excluded from the unit tiers.
        markers={
            "fast": "not slow and not integration and not golden and not benchmark",
            "default": "not slow and not golden and not benchmark",
            "all": "not golden and not benchmark",
        },
    ),
    coverage=CoverageConfig(source=["src/pyclawd"]),
    # Dogfood the behavior oracle: `pyclawd golden` gates `@pytest.mark.golden` tests.
    golden=GoldenConfig(),
    # Dogfood the performance oracle: `pyclawd benchmark` times `@pytest.mark.benchmark`
    # tests (best-of-N) and fails on a slow-down. Baselines are hardware-specific, so they
    # live in the gitignored work dir and are never committed — bless locally with
    # `pyclawd benchmark update`.
    benchmark=BenchmarkConfig(),
    # Dogfood the public-API surface oracle: `pyclawd api` proves the exported surface
    # of src/pyclawd/ has not drifted from the committed baseline (tests/api_surface.txt).
    api=ApiConfig(packages=["src/pyclawd"]),
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
