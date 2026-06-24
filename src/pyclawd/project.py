"""Generic project configuration model + loader for pyclawd.

This module is the **configuration surface** of the pyclawd toolkit. pyclawd ships as a
project-agnostic framework: every project-specific knob (paths, commands, conda
env, test-tier markers, doctor checks, …) is captured by the :class:`Project`
model defined here, and each adopting project supplies a concrete instance in a
``.pyclawd/config.py`` file at its repository root.

The toolkit discovers that file (see :mod:`pyclawd.discovery`'s
``find_config_file`` / ``load_project``), imports it, and reads its module-level
``project`` object. Nothing in this module is specific to any particular
project — an adopting project's ``.pyclawd/config.py`` provides the concrete
instance, which downstream templates copy and edit.

The model is a tree of frozen dataclasses so a loaded :class:`Project` is
immutable and safe to share. Grouped concerns live in nested configs
(:class:`DocsConfig`, :class:`TestConfig`, :class:`DoctorConfig`).

Doctor primitives (:class:`Check` and the :data:`OK` / :data:`WARN` /
:data:`FAIL` status constants) live here too, in the generic core, because a
project's :attr:`Project.extra_doctor_checks` hook builds :class:`Check` objects.
``doctor.py`` re-imports them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Doctor primitives — generic, so config hooks can build checks.
# --------------------------------------------------------------------------- #

#: Health-check passed.
OK = "ok"
#: Health-check passed with a caveat (non-fatal).
WARN = "warn"
#: Health-check failed (fatal — gates dependent workflows).
FAIL = "fail"


@dataclass
class Check:
    """The result of a single environment health check.

    Parameters
    ----------
    status : str
        One of :data:`OK`, :data:`WARN`, or :data:`FAIL`.
    name : str
        Short label for the thing being checked (e.g. ``"pandoc"``).
    detail : str, optional
        Human-readable detail, such as a version string or a remediation hint.
    """

    status: str
    name: str
    detail: str = ""


# --------------------------------------------------------------------------- #
# Nested configuration groups.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DocsConfig:
    """Documentation-build settings for ``pyclawd docs``.

    Only :attr:`runner` is required; the path fields default to the conventional
    ``docs/...`` layout, so ``DocsConfig(runner=[...])`` just works.

    Runner contract
    ---------------
    ``pyclawd docs`` is a thin orchestrator — it appends a sub-verb to
    :attr:`runner` and runs it. A runner **must** implement these verbs (note the
    pyclawd verb ≠ runner verb in two cases):

    ===================== ============================ ==================================
    pyclawd command       runner invocation            does
    ===================== ============================ ==================================
    ``docs compile``      ``compile [pages]``          ``.md`` → ``.ipynb`` (no exec)
    ``docs run``          ``compile`` then ``run``     execute notebooks, cache results
    ``docs build``        ``all [--continue]``         compile → run → render HTML
    ``docs build --fast`` ``build --fast``             render only (no notebooks)
    ``docs render``       ``build``                    render HTML from cached notebooks
    ``docs exec <page>``  ``exec <page>``              execute ONE, stream the error
    ``docs clean``        ``clean``                    drop build + generated ``.ipynb``
    ===================== ============================ ==================================

    See ``pyclawd``'s own ``docs/`` for a ~150-line reference runner.

    Backend assumption
    ------------------
    The build verbs (``build`` / ``run`` / ``compile`` / ``render`` / ``exec`` /
    ``clean``) are **delegated** to :attr:`runner` and impose nothing — plug in any
    toolchain that understands those verbs. The two *introspection* views are the
    exception: ``pyclawd docs timings`` and ``pyclawd docs failures`` read the
    runner's execution cache **directly**, and they assume a `jupyter-cache
    <https://jupyter-cache.readthedocs.io>`_ SQLite cache at :attr:`cache_db`
    (tables ``nbcache`` / ``nbproject``). ``timings`` needs only stdlib ``sqlite3``;
    ``failures`` additionally imports ``jupyter_cache`` + ``nbformat`` **in
    pyclawd's own env** (it self-reports cleanly if they are absent). So: a
    non-jupyter-cache runner can still ``build``/``run``, but ``timings``/``failures``
    will show nothing / report the missing backend. ``pyclawd doctor`` surfaces this
    when docs are configured.

    Parameters
    ----------
    runner : list of str
        Argv prefix that invokes the project's documentation toolchain, e.g.
        ``["uvx", "--from", "./docs", "mydocs"]``. Sub-commands are appended.
        Heavy docs deps (sphinx/nbsphinx/jupyter-cache) live in that isolated
        toolchain, not the project env.
    source_dir : str
        Root-relative directory holding the documentation sources
        (e.g. ``"docs/source"``).
    cache_dir : str
        Root-relative jupyter-cache directory (e.g. ``"docs/.jupyter_cache"``).
    cache_db : str
        Root-relative path to the jupyter-cache SQLite database
        (e.g. ``"docs/.jupyter_cache/global.db"``).
    build_html : str
        Root-relative directory where rendered HTML is written
        (e.g. ``"docs/build/html"``).
    branch : str
        Git branch the ``--changed`` build diffs against (e.g. ``"main"``).
    """

    runner: list[str]
    source_dir: str = "docs/source"
    cache_dir: str = "docs/.jupyter_cache"
    cache_db: str = "docs/.jupyter_cache/global.db"
    build_html: str = "docs/build/html"
    branch: str = "main"


@dataclass(frozen=True)
class TestConfig:
    """Test-suite settings and tier marker expressions for ``pyclawd test``.

    The tier marker expressions are stored in :attr:`markers`, keyed by tier
    name, so the test runner can look them up without hardcoding values. The
    pipeline verbs use three well-known keys; any *other* key you add becomes a
    ``pyclawd test <key>`` category (nothing is assumed — define only what you use):

    - ``"default"`` — the comprehensive default gate (e.g. everything but ``long``).
    - ``"fast"`` — the <30s smoke tier (e.g. also excludes ``slow``).
    - ``"all"`` — everything.
    - any extra key (e.g. ``"examples"`` / ``"docs"``) — a per-category suite,
      runnable as ``pyclawd test examples`` / ``pyclawd test docs``.

    Parameters
    ----------
    tests_dir : str
        Root-relative directory containing the unit tests (e.g. ``"tests/"``).
    classname_prefix : str
        Dotted prefix junit assigns to test classnames, used to reconstruct
        path-ish node ids (e.g. ``"tests."``).
    integration_files : list of str
        Root-relative test files that are their own integration suites and are
        deselected by the unit tiers (e.g. ``["tests/test_examples.py", ...]``).
    markers : dict of str to str
        Tier name → pytest ``-m`` marker expression (see above). A tier the
        project does not define simply applies no ``-m`` filter (it is **not** an
        error to omit ``fast`` or ``all``), so the tier set is fully customisable.
    jobs : str, optional
        pytest-xdist worker count applied to the logged tiers (``run`` / ``fast`` /
        ``all`` and the ``check`` test step). ``"auto"`` (the default) runs every
        tier in parallel across all cores; ``""`` runs serial; an integer string
        (e.g. ``"4"``) pins the worker count. Requires ``pytest-xdist`` (in the
        scaffold's dev group). An explicit ``-n`` in the command always wins.
    """

    tests_dir: str
    classname_prefix: str
    integration_files: list[str]
    markers: dict[str, str]
    jobs: str = "auto"


@dataclass(frozen=True)
class QualityConfig:
    """Code-quality settings for ``pyclawd lint`` / ``format`` / ``typecheck`` / ``check``.

    Each command maps to an explicit argv so the toolchain is fully
    project-driven — nothing about ruff/mypy/etc. is hardcoded in the command
    layer. The aggregate ``pyclawd check`` gate runs the verbs named in
    :attr:`check_sequence`, in order, fail-fast.

    Parameters
    ----------
    lint_cmd : list of str
        Argv that lints without mutating files (e.g. ``["ruff", "check"]``).
    lint_fix_cmd : list of str
        Argv that lints and applies autofixes (e.g. ``["ruff", "check", "--fix"]``).
    format_cmd : list of str
        Argv that rewrites files to the canonical format
        (e.g. ``["ruff", "format"]``).
    format_check_cmd : list of str
        Non-mutating format check, suitable as a CI gate
        (e.g. ``["ruff", "format", "--check"]``).
    typecheck_cmd : list of str
        Argv that type-checks the project (e.g. ``["mypy", "src"]``).
    check_sequence : list of str
        Ordered verbs the aggregate ``pyclawd check`` runs. Recognised verbs are
        ``"format-check"``, ``"lint"``, ``"typecheck"``, and ``"test"`` (which
        maps to the default test tier). Defaults to
        ``["format-check", "lint", "typecheck", "test"]``.
    """

    lint_cmd: list[str] = field(default_factory=list)
    lint_fix_cmd: list[str] = field(default_factory=list)
    format_cmd: list[str] = field(default_factory=list)
    format_check_cmd: list[str] = field(default_factory=list)
    typecheck_cmd: list[str] = field(default_factory=list)
    check_sequence: list[str] = field(
        default_factory=lambda: ["format-check", "lint", "typecheck", "test"]
    )


@dataclass(frozen=True)
class CoverageConfig:
    """Coverage measurement settings for ``pyclawd coverage``.

    Parameters
    ----------
    source : list of str
        Packages or directories to measure, passed as ``--cov=<src>`` to
        pytest-cov (e.g. ``["src/mypkg"]``). At least one entry is required.
    threshold : int
        Minimum acceptable coverage percentage used by ``pyclawd coverage
        --check`` (``--cov-fail-under=<threshold>``). Defaults to ``80``.
    branch : bool
        Enable branch coverage (``--cov-branch``). Defaults to ``True``.
    """

    source: list[str]
    threshold: int = 80
    branch: bool = True


@dataclass(frozen=True)
class DescriptionConfig:
    r"""File-description checking settings (``pyclawd ls --missing`` / ``"descriptions"`` step).

    Controls which files the descriptions check considers. Applied by
    ``check_descriptions`` in :mod:`pyclawd.commands.ls` and the
    ``"descriptions"`` step in ``pyclawd check`` when it appears in
    ``quality.check_sequence``.

    Args:
        include: Regex patterns (``re.search``) matched against each file's
            repo-relative path. A file is checked only when it matches **at
            least one** pattern. Defaults to ``[r"\.pyx?$"]`` — Python and
            Cython source only. To add extension types:
            ``[r"\.pyx?$", r"\.pxd$"]``.
        exclude: Regex patterns (``re.search``) matched against each file's
            repo-relative path. A file is skipped when it matches **any**
            pattern. Defaults to ``[]``. Use to exclude vendored or generated
            Python, e.g. ``[r"vendor/", r"_generated/"]``.
    """

    include: list[str] = field(default_factory=lambda: [r"\.pyx?$"])
    exclude: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DoctorConfig:
    r"""Health-check settings for ``pyclawd doctor``.

    Parameters
    ----------
    core_deps : list of str
        Runtime imports that must succeed; a missing one is a :data:`FAIL`.
    dev_deps : list of str
        Dev/docs imports; a missing one only :data:`WARN`\\ s.
    tool_files : list of str
        Root-relative files that must exist and be executable
        (e.g. ``["tools/python", ...]``).
    binaries : list of tuple of (str, str)
        System binaries to probe via ``shutil.which`` as
        ``(name, install_hint)`` pairs (e.g. ``[("pandoc", "conda install …")]``).
    """

    core_deps: list[str]
    dev_deps: list[str]
    tool_files: list[str]
    binaries: list[tuple[str, str]]


# --------------------------------------------------------------------------- #
# The project model.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Project:
    r"""Immutable description of a project that pyclawd operates on.

    An adopting project supplies one of these as the module-level ``project``
    object in its ``.pyclawd/config.py``. The loader fills in :attr:`root` (the
    discovered repository root) after import; the user never sets it.

    Parameters
    ----------
    name : str
        Project name (e.g. ``"myproject"``).
    conda_env : str or None
        Conda env pyclawd expects to run in, or ``None`` if env-agnostic. This is
        **advisory** — it does not select the interpreter (see :attr:`python_cmd`);
        ``pyclawd doctor`` only WARNs when the active env differs.
    root_markers : list of str
        Root-relative files that should exist at the repository root, used as a
        sanity check (e.g. ``["mypkg/__init__.py", "setup.py"]``).
    test : TestConfig
        Test-suite settings and tier markers.
    doctor : DoctorConfig
        Health-check settings.
    python_cmd : list of str, optional
        The argv prefix used to launch the project's Python — this is *how* every
        ``pyclawd python`` / ``test`` / ``compile`` invocation runs code, so it
        makes the interpreter fully project-defined and extensible. One field
        spans every backend:

        - ``[]`` (the default) → pyclawd's own ``sys.executable`` (install pyclawd
          into the env you develop in);
        - explicit venv → ``["/path/.venv/bin/python"]``;
        - conda (one pyclawd driving many envs) → ``["conda", "run", "-n", "env", "python"]``;
        - uv → ``["uv", "run", "python"]``.

        The ``PYCLAWD_PYTHON`` environment variable overrides this at runtime
        (``shlex``-split, so it may be a full command) for one-off interpreter
        swaps without editing config.
    pyclawd_version : str, optional
        The pyclawd version this config was authored against — stamped
        automatically by ``pyclawd new`` (the running ``pyclawd.__version__``).
        ``pyclawd doctor`` compares it to the installed pyclawd and WARNs on a
        ``major.minor`` mismatch, so a project built on an older pyclawd surfaces a
        "migration may be needed" signal instead of silently drifting. Empty (the
        default) disables the check.
    work_dir : str, optional
        Base directory for pyclawd's transient per-project files — run logs, junit
        xml, and other scratch artifacts. Empty (the default) uses
        ``<tempdir>/pyclawd`` (honouring ``$TMPDIR``); set it to keep a project's
        artifacts somewhere predictable (e.g. ``"/tmp/myproject"`` or
        ``".pyclawd/work"``). Relative paths resolve against the repo root. The
        ``PYCLAWD_WORK_DIR`` environment variable overrides it at runtime. Logs live
        under ``<work_dir>/logs/<category>/``.
    compile_cmd : list of str, optional
        Args passed to the dev Python for ``pyclawd compile``
        (e.g. ``["setup.py", "build_ext", "--inplace"]``). Empty (the default)
        means the project has no compile step — ``pyclawd compile`` reports that
        and exits cleanly.
    dist_cmd : list of str, optional
        Args passed to the dev Python for ``pyclawd dist`` (e.g.
        ``["setup.py", "sdist"]``). Empty (the default) means no dist step.
    clean_targets : list of str, optional
        Root-relative paths removed by ``pyclawd clean``
        (e.g. ``["build", "dist", "mypkg.egg-info"]``). Defaults to empty.
    clean_ext_dir : str, optional
        Root-relative directory holding compiled artifacts
        (e.g. ``"mypkg/_compiled"``). Empty (the default) disables ``--ext``.
    clean_ext_globs : list of str, optional
        Globs removed under :attr:`clean_ext_dir` when ``pyclawd clean --ext`` runs
        (e.g. ``["*.c", "*.cpp", "*.so", "*.html"]``). Defaults to empty.
    src_dir : str, optional
        Default directory ``pyclawd ls`` lists (the code/source root), relative to
        the repo root. Defaults to ``src``.
    descriptions : DescriptionConfig, optional
        Controls which files the ``"descriptions"`` step (and ``pyclawd ls
        --missing``) checks for a top-of-file description. Defaults to
        ``DescriptionConfig()`` — Python/Cython only, no exclusions. See
        :class:`DescriptionConfig` for the ``include`` / ``exclude`` regex knobs.
    docs : DocsConfig or None, optional
        Documentation-build settings, or ``None`` (the default) when the project
        has no docs. When ``None`` the ``pyclawd docs`` command group is not even
        registered.
    quality : QualityConfig or None, optional
        Code-quality settings for ``pyclawd lint`` / ``format`` / ``typecheck`` /
        ``check``, or ``None`` (the default) when the project configures no
        quality toolchain. When ``None`` (or a given command's argv is empty) the
        affected command self-reports that quality is unconfigured and exits 2
        rather than crashing.
    extra_doctor_checks : callable or None, optional
        Optional hook returning a list of extra :class:`Check` objects, appended
        to the doctor report (e.g. project import + compiled-extension status).
        Defaults to ``None``.
    root : pathlib.Path or None, optional
        The discovered repository root. **Not set by the user** — the loader
        fills it in. Defaults to ``None``.
    """

    name: str
    conda_env: str | None
    root_markers: list[str]

    test: TestConfig
    doctor: DoctorConfig

    python_cmd: list[str] = field(default_factory=list)
    pyclawd_version: str = ""
    work_dir: str = ""

    compile_cmd: list[str] = field(default_factory=list)
    dist_cmd: list[str] = field(default_factory=list)

    clean_targets: list[str] = field(default_factory=list)
    clean_ext_dir: str = ""
    clean_ext_globs: list[str] = field(default_factory=list)

    src_dir: str = "src"
    descriptions: DescriptionConfig = field(default_factory=DescriptionConfig)

    docs: DocsConfig | None = None
    quality: QualityConfig | None = None
    coverage: CoverageConfig | None = None

    extra_doctor_checks: Callable[..., list[Check]] | None = None
    root: Path | None = None

    def path(self, *rel: str) -> Path:
        """Resolve a root-relative path against the discovered repository root.

        Args:
            *rel: Path components relative to :attr:`root`.

        Returns:
            ``self.root`` joined with ``rel``.

        Raises:
            ValueError: If :attr:`root` has not been set (i.e. the project was not loaded
                through :func:`load_project`).
        """
        if self.root is None:
            raise ValueError("Project.root is not set — load via load_project().")
        return self.root.joinpath(*rel)
