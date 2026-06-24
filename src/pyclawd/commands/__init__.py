"""Typer command groups for the pyclawd CLI.

Each module here owns one slice of the command surface and exposes a thin
``register(app)`` (or ``register(app, project)``) hook that wires its commands
onto the main :class:`typer.Typer` app. The heavy logic lives in the sibling
top-level modules (``run``, ``tests``, ``logs``, ``doctor``); these modules are
just the CLI wiring so ``cli.py`` stays a thin assembler.
"""

from __future__ import annotations

#: Typer ``context_settings`` for commands that forward unknown args/options
#: straight to a subprocess (``pyclawd python``, ``test``, ``docs run/compile``).
_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}
