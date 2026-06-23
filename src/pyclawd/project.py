"""Generic project configuration model + loader for pyclawd.

This module is the **configuration surface** of the pyclawd toolkit. pyclawd ships as a
project-agnostic framework: every project-specific knob (paths, commands, conda
env, test-tier markers, doctor checks, …) is captured by the :class:`Project`
model defined here, and each adopting project supplies a concrete instance in a
``.pyclawd/config.py`` file at its repository root.

The toolkit discovers that file by walking up from the current working
directory (:func:`find_config_file`), imports it, and reads its module-level
``project`` object (:func:`load_project`). Nothing in this module is specific to
any particular project — the worked example lives in pymoo's own
``.pyclawd/config.py``, which downstream templates copy and edit.

The model is a tree of frozen dataclasses so a loaded :class:`Project` is
immutable and safe to share. Grouped concerns live in nested configs
(:class:`DocsConfig`, :class:`TestConfig`, :class:`DoctorConfig`).

Doctor primitives (:class:`Check` and the :data:`OK` / :data:`WARN` /
:data:`FAIL` status constants) live here too, in the generic core, because a
project's :attr:`Project.extra_doctor_checks` hook builds :class:`Check` objects.
``doctor.py`` re-imports them.
"""

from __future__ import annotations

import dataclasses
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
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

    Parameters
    ----------
    runner : list of str
        Argv prefix that invokes the project's documentation toolchain, e.g.
        ``["uvx", "--from", "./docs", "mydocs"]``. Sub-commands are appended.
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
    source_dir: str
    cache_dir: str
    cache_db: str
    build_html: str
    branch: str


@dataclass(frozen=True)
class TestConfig:
    """Test-suite settings and tier marker expressions for ``pyclawd test``.

    The tier marker expressions are stored in :attr:`markers`, keyed by tier
    name, so the test runner can look them up without hardcoding values:

    - ``"default"`` — the comprehensive default gate (everything but ``long``).
    - ``"fast"`` — the <30s smoke tier (also excludes ``slow``).
    - ``"all"`` — everything, including ``long``.
    - ``"examples"`` / ``"docs"`` — the per-category integration suites.

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
        Tier name → pytest ``-m`` marker expression (see above).
    """

    tests_dir: str
    classname_prefix: str
    integration_files: list[str]
    markers: dict[str, str]


@dataclass(frozen=True)
class DoctorConfig:
    """Health-check settings for ``pyclawd doctor``.

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
    """Immutable description of a project that pyclawd operates on.

    An adopting project supplies one of these as the module-level ``project``
    object in its ``.pyclawd/config.py``. The loader fills in :attr:`root` (the
    discovered repository root) after import; the user never sets it.

    Parameters
    ----------
    name : str
        Project name (e.g. ``"myproject"``).
    conda_env : str or None
        Conda env pyclawd expects to run in, or ``None`` if env-agnostic.
    root_markers : list of str
        Root-relative files that should exist at the repository root, used as a
        sanity check (e.g. ``["mypkg/__init__.py", "setup.py"]``).
    compile_cmd : list of str
        Args passed to the dev Python for ``pyclawd compile``
        (e.g. ``["setup.py", "build_ext", "--inplace"]``).
    dist_cmd : list of str
        Args passed to the dev Python for ``pyclawd dist`` (e.g. ``["setup.py", "sdist"]``).
    clean_targets : list of str
        Root-relative paths removed by ``pyclawd clean``
        (e.g. ``["build", "dist", "mypkg.egg-info"]``).
    clean_ext_dir : str
        Root-relative directory holding compiled artifacts
        (e.g. ``"mypkg/_compiled"``).
    clean_ext_globs : list of str
        Globs removed under :attr:`clean_ext_dir` when ``pyclawd clean --ext`` runs
        (e.g. ``["*.c", "*.cpp", "*.so", "*.html"]``).
    docs : DocsConfig
        Documentation-build settings.
    test : TestConfig
        Test-suite settings and tier markers.
    doctor : DoctorConfig
        Health-check settings.
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

    compile_cmd: list[str]
    dist_cmd: list[str]

    clean_targets: list[str]
    clean_ext_dir: str
    clean_ext_globs: list[str]

    docs: DocsConfig
    test: TestConfig
    doctor: DoctorConfig

    extra_doctor_checks: Callable[..., list[Check]] | None = None
    root: Path | None = None

    def path(self, *rel: str) -> Path:
        """Resolve a root-relative path against the discovered repository root.

        Parameters
        ----------
        *rel : str
            Path components relative to :attr:`root`.

        Returns
        -------
        pathlib.Path
            ``self.root`` joined with ``rel``.

        Raises
        ------
        ValueError
            If :attr:`root` has not been set (i.e. the project was not loaded
            through :func:`load_project`).
        """
        if self.root is None:
            raise ValueError("Project.root is not set — load via load_project().")
        return self.root.joinpath(*rel)


# --------------------------------------------------------------------------- #
# Discovery + loading.
# --------------------------------------------------------------------------- #

#: Directory name (under the repo root) that holds the project config.
CONFIG_DIR = ".pyclawd"
#: Config module file name within :data:`CONFIG_DIR`.
CONFIG_FILE = "config.py"

# Private module name the config file is imported under.
_LOADED_MODULE = "pyclawd._loaded_config"

# Cache of loaded projects, keyed by the resolved config-file path.
_CACHE: dict[Path, Project] = {}


def find_config_file(start: str | Path | None = None) -> Path | None:
    """Walk up from *start* looking for a ``.pyclawd/config.py``.

    Parameters
    ----------
    start : str or pathlib.Path or None, optional
        Directory to start searching from. Defaults to the current working
        directory.

    Returns
    -------
    pathlib.Path or None
        The resolved path to the discovered ``.pyclawd/config.py``, or ``None`` if
        none is found walking up to the filesystem root.
    """
    here = Path(start or Path.cwd()).resolve()
    for cand in (here, *here.parents):
        config = cand / CONFIG_DIR / CONFIG_FILE
        if config.is_file():
            return config
    return None


def load_project(start: str | Path | None = None) -> Project | None:
    """Discover, import, and return the project's :class:`Project` config.

    Walks up from *start* to find ``.pyclawd/config.py`` (:func:`find_config_file`),
    imports it, reads its module-level ``project`` object, validates it, and sets
    :attr:`Project.root` to the directory containing ``.pyclawd/``. Results are cached
    by config-file path, so repeated calls do not re-import.

    Parameters
    ----------
    start : str or pathlib.Path or None, optional
        Directory to start searching from. Defaults to the current working
        directory.

    Returns
    -------
    Project or None
        The loaded project with :attr:`Project.root` populated, or ``None`` if no
        ``.pyclawd/config.py`` is found.

    Raises
    ------
    ImportError
        If the config file cannot be imported.
    TypeError
        If the config module has no ``project`` attribute or it is not a
        :class:`Project` instance.
    """
    config_file = find_config_file(start)
    if config_file is None:
        return None

    if config_file in _CACHE:
        return _CACHE[config_file]

    spec = importlib.util.spec_from_file_location(_LOADED_MODULE, config_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load config spec from {config_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    project = getattr(module, "project", None)
    if project is None:
        raise TypeError(
            f"{config_file} defines no module-level `project` object "
            f"(expected a pyclawd.Project instance)."
        )
    if not isinstance(project, Project):
        raise TypeError(
            f"`project` in {config_file} must be a pyclawd.Project instance, "
            f"got {type(project).__name__}."
        )

    # The repo root is the directory containing the `.pyclawd/` dir.
    root = config_file.parent.parent
    project = dataclasses.replace(project, root=root)
    _CACHE[config_file] = project
    return project
