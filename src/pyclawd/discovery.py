"""Config discovery + loading for pyclawd — with explicit overrides.

This module locates a project's ``.pyclawd/config.py``, imports it, and returns
the module-level :class:`~pyclawd.project.Project` instance with its
:attr:`~pyclawd.project.Project.root` filled in.

Resolution precedence
---------------------
A config file is resolved by trying these sources in order; the first hit wins:

1. **An explicit config path** — passed directly to :func:`find_config_file` /
   :func:`load_project` as ``config=``, or set process-wide via
   :func:`set_config_override` (which the CLI's global ``--config`` option uses).
2. **The ``PYCLAWD_CONFIG`` environment variable.**
3. **Walk-up discovery** — from *start* (default: the current working directory)
   up to the filesystem root, looking for a ``.pyclawd/config.py``.

For (1) and (2) the value may be either a **file** (a ``config.py``) or a
**directory**. A directory is resolved by looking for ``<dir>/.pyclawd/config.py``
first, then a bare ``<dir>/config.py``.

Repo root rule
--------------
:attr:`Project.root` is derived from the resolved config file:

- if the config file lives in a ``.pyclawd/`` directory (the canonical layout),
  the root is that directory's **parent** (the dir that *contains* ``.pyclawd/``);
- otherwise (a loose ``config.py`` pointed at directly), the root is simply the
  directory **containing** the config file.

This keeps ``project.root`` correct for walk-up, ``--config`` and
``PYCLAWD_CONFIG`` alike.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
from pathlib import Path

from .project import Project

#: Directory name (under the repo root) that holds the project config.
CONFIG_DIR = ".pyclawd"
#: Config module file name within :data:`CONFIG_DIR`.
CONFIG_FILE = "config.py"
#: Environment variable that points at a config file or directory (override #2).
ENV_VAR = "PYCLAWD_CONFIG"

# Private module name the config file is imported under.
_LOADED_MODULE = "pyclawd._loaded_config"

# Cache of loaded projects, keyed by the resolved config-file path.
_CACHE: dict[Path, Project] = {}

# Process-wide explicit override (set by the CLI's global --config option).
_OVERRIDE: str | Path | None = None


class ConfigError(Exception):
    """A discovered ``.pyclawd/config.py`` could not be imported/executed.

    Raised by :func:`load_project` when importing the config module fails (syntax
    error, import error, exception at module scope, …). The CLI boundary
    (``load_project_or_exit`` / ``doctor`` / ``root``) catches this and prints a
    single clean ``✗`` line instead of dumping a rich traceback. Kept as a plain
    exception (not ``typer.Exit``) so the loader stays usable programmatically and
    in unit tests.
    """


def set_config_override(target: str | Path | None) -> None:
    """Set (or clear) the process-wide explicit config override.

    The CLI's global ``--config`` callback calls this so that every later
    ``load_project()`` / ``find_config_file()`` — including the ones inside the
    command implementations — resolves to *target*. Pass ``None`` to clear it.
    """
    global _OVERRIDE
    _OVERRIDE = target


def _resolve_target(target: str | Path) -> Path | None:
    """Resolve an explicit file-or-directory *target* to a ``config.py`` path.

    A file is used as-is; a directory is searched for ``.pyclawd/config.py`` then
    a bare ``config.py``. Returns ``None`` if nothing usable is found.
    """
    p = Path(target).expanduser()
    if p.is_file():
        return p.resolve()
    if p.is_dir():
        for cand in (p / CONFIG_DIR / CONFIG_FILE, p / CONFIG_FILE):
            if cand.is_file():
                return cand.resolve()
    return None


def _walk_up(start: str | Path | None) -> Path | None:
    """Walk up from *start* (default: cwd) looking for ``.pyclawd/config.py``."""
    here = Path(start or Path.cwd()).resolve()
    for cand in (here, *here.parents):
        config = cand / CONFIG_DIR / CONFIG_FILE
        if config.is_file():
            return config
    return None


def find_config_file(
    start: str | Path | None = None,
    *,
    config: str | Path | None = None,
) -> Path | None:
    """Resolve the project's ``.pyclawd/config.py`` using the precedence above.

    Parameters
    ----------
    start : str or pathlib.Path or None, optional
        Directory the walk-up fallback starts from. Defaults to the current
        working directory.
    config : str or pathlib.Path or None, optional
        An explicit config file or directory (precedence #1). When ``None``, the
        process-wide override from :func:`set_config_override` is used instead, if
        set.

    Returns
    -------
    pathlib.Path or None
        The resolved config-file path, or ``None`` if none is found.
    """
    explicit = config if config is not None else _OVERRIDE
    if explicit is not None:
        return _resolve_target(explicit)

    env = os.environ.get(ENV_VAR)
    if env:
        return _resolve_target(env)

    return _walk_up(start)


def _root_for(config_file: Path) -> Path:
    """Derive the repo root from a resolved config file (see module docstring)."""
    parent = config_file.parent
    if parent.name == CONFIG_DIR:
        return parent.parent
    return parent


def load_project(
    start: str | Path | None = None,
    *,
    config: str | Path | None = None,
) -> Project | None:
    """Discover, import, and return the project's :class:`Project` config.

    Resolves the config file via :func:`find_config_file` (honouring the
    ``config=`` / override / ``PYCLAWD_CONFIG`` / walk-up precedence), imports it,
    reads its module-level ``project`` object, validates it, and sets
    :attr:`Project.root`. Results are cached by config-file path.

    Parameters
    ----------
    start : str or pathlib.Path or None, optional
        Directory the walk-up fallback starts from. Defaults to the current
        working directory.
    config : str or pathlib.Path or None, optional
        An explicit config file or directory (see :func:`find_config_file`).

    Returns
    -------
    Project or None
        The loaded project with :attr:`Project.root` populated, or ``None`` if no
        config is found.

    Raises
    ------
    ImportError
        If the config file's import spec cannot be created.
    ConfigError
        If importing/executing the config module fails (syntax error, import
        error, exception at module scope, …). The CLI turns this into a clean
        one-line message; programmatic callers can catch it.
    TypeError
        If the config module has no ``project`` attribute or it is not a
        :class:`Project` instance.
    """
    config_file = find_config_file(start, config=config)
    if config_file is None:
        return None

    if config_file in _CACHE:
        return _CACHE[config_file]

    spec = importlib.util.spec_from_file_location(_LOADED_MODULE, config_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load config spec from {config_file}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - surface any config import failure cleanly
        raise ConfigError(f"failed to load {config_file}: {type(exc).__name__}: {exc}") from exc

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

    project = dataclasses.replace(project, root=_root_for(config_file))
    _CACHE[config_file] = project
    return project
