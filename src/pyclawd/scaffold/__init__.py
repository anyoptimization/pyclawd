"""Project-scaffold templates for ``pyclawd new``.

This is a *data* package: the ``templates/`` subdirectory holds ``*.tmpl`` files
that :mod:`pyclawd.commands.new` reads (via :func:`importlib.resources.files`) and
renders with ``{{placeholder}}`` substitution to scaffold a fresh, best-practice
Python project. Keeping the templates as packaged data (rather than inline
strings) means they ship in the wheel alongside the code and stay easy to edit.
"""

from __future__ import annotations
