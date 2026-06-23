"""Bundled Claude Code skills that ship with pyclawd.

This package holds the ``pyclawd-*`` agent skill directories (each a
``SKILL.md`` with YAML frontmatter) plus a ``README.md``. They are packaged
data, not importable modules, and are discovered at runtime via
``importlib.resources.files("pyclawd.skills")`` — so they work identically
whether pyclawd runs from a source checkout or an installed wheel.

The ``pyclawd skills`` command group (:mod:`pyclawd.commands.skills`) lists and
installs them into a project's ``.claude/skills/`` directory; ``pyclawd new``
installs them automatically.
"""

from __future__ import annotations
