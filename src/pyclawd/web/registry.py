"""The multi-project registry behind the dashboard's project switcher.

The dashboard watches *many* repos at once. The registry answers "which projects
exist?" by overlaying two sources:

* **Discovery** — every git repo directly under a set of *roots* (default
  ``~/workspace``), surfaced automatically so a fresh checkout just appears.
* **The manual registry** — projects explicitly added (perhaps outside the roots)
  plus per-project state (stars), persisted as JSON under ``~/.pyclawd``.

State is intentionally stored as JSON via the standard library so this module —
like :mod:`pyclawd.web.git` — adds no dependency to pyclawd's core. A
:class:`Registry` is bound to one config file; tests point it at a ``tmp_path``.
The default location honours ``$PYCLAWD_WEB_CONFIG`` then falls back to
``~/.pyclawd/web.json``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: Default roots scanned for git repos when the config names none.
DEFAULT_ROOTS: tuple[str, ...] = ("~/workspace",)


@dataclass(frozen=True)
class ProjectEntry:
    """One project known to the dashboard.

    Attributes:
        name: Display name (defaults to the directory name; unique within a registry).
        path: Absolute path to the git work tree.
        starred: Whether the user pinned it to the top of the switcher.
        discovered: ``True`` if found by root discovery, ``False`` if added manually.
    """

    name: str
    path: str
    starred: bool = False
    discovered: bool = False


def _default_config_path() -> Path:
    """Return the registry's JSON path from ``$PYCLAWD_WEB_CONFIG`` or ``~/.pyclawd``."""
    override = os.environ.get("PYCLAWD_WEB_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".pyclawd" / "web.json"


@dataclass(frozen=True)
class Registry:
    """A view over the dashboard's project registry, bound to one JSON config file."""

    config_path: Path

    @classmethod
    def default(cls) -> Registry:
        """Return a registry backed by the default config path."""
        return cls(config_path=_default_config_path())

    # -- persistence ------------------------------------------------------- #

    def _load(self) -> dict:
        """Return the parsed config, or an empty dict if absent/corrupt."""
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text()) or {}
        except (OSError, ValueError):
            return {}

    def _save(self, config: dict) -> None:
        """Write *config* back to disk, creating the parent directory as needed."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config, indent=2, sort_keys=True))

    # -- roots ------------------------------------------------------------- #

    def roots(self) -> list[Path]:
        """Return the configured discovery roots (expanded), or the defaults."""
        configured = self._load().get("roots") or list(DEFAULT_ROOTS)
        return [Path(r).expanduser() for r in configured]

    def set_roots(self, roots: list[str]) -> list[str]:
        """Replace the discovery roots and return the cleaned list that was stored."""
        config = self._load()
        cleaned = [r.strip() for r in roots if r.strip()]
        config["roots"] = cleaned
        self._save(config)
        return cleaned

    # -- project listing --------------------------------------------------- #

    def _discover(self) -> dict[str, ProjectEntry]:
        """Return git repos directly under the configured roots, keyed by name."""
        found: dict[str, ProjectEntry] = {}
        for root in self.roots():
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if (child / ".git").exists():
                    found[child.name] = ProjectEntry(
                        name=child.name, path=str(child.resolve()), discovered=True
                    )
        return found

    def projects(self) -> dict[str, ProjectEntry]:
        """Return all known projects: discovered repos overlaid with the manual registry.

        Manual entries supply a path (for projects outside the roots) and the
        starred flag; a discovered project keeps its path if the registry only
        records a star for it.
        """
        projects = self._discover()
        for name, meta in (self._load().get("projects") or {}).items():
            raw_path = meta.get("path")
            path = (
                str(Path(raw_path).expanduser().resolve())
                if raw_path
                else (projects[name].path if name in projects else None)
            )
            if path is None:
                continue  # a star for a project that no longer exists anywhere
            discovered = projects[name].discovered if name in projects else False
            projects[name] = ProjectEntry(
                name=name,
                path=path,
                starred=bool(meta.get("starred", False)),
                discovered=discovered,
            )
        return projects

    def resolve(self, name: str | None) -> str | None:
        """Return the absolute path for project *name*, or ``None`` if unknown."""
        if not name:
            return None
        entry = self.projects().get(name)
        return entry.path if entry else None

    # -- mutation ---------------------------------------------------------- #

    def add(self, path: str, name: str | None = None) -> str:
        """Register a project at *path* (named *name*, else its directory name).

        Returns:
            The name under which the project was registered.
        """
        resolved = str(Path(path).expanduser().resolve())
        name = name or Path(resolved).name
        config = self._load()
        projects = config.setdefault("projects", {})
        previous = projects.get(name, {})
        projects[name] = {"path": resolved, "starred": previous.get("starred", False)}
        self._save(config)
        return name

    def remove(self, name: str) -> bool:
        """Unregister a manually-added project; return ``True`` if it existed."""
        config = self._load()
        if name in (config.get("projects") or {}):
            del config["projects"][name]
            self._save(config)
            return True
        return False

    def set_star(self, name: str, starred: bool) -> None:
        """Pin or unpin project *name*, persisting its path so a discovered repo keeps the star."""
        config = self._load()
        projects = config.setdefault("projects", {})
        entry = projects.setdefault(name, {})
        if "path" not in entry:
            known = self.projects().get(name)
            if known:
                entry["path"] = known.path
        entry["starred"] = bool(starred)
        self._save(config)
