"""Typer command groups for the pyclawd CLI.

Each module here owns one slice of the command surface and exposes a thin
``register(app)`` (or ``register(app, project)``) hook that wires its commands
onto the main :class:`typer.Typer` app. The heavy logic lives in the sibling
top-level modules (``run``, ``tests``, ``logs``, ``doctor``); these modules are
just the CLI wiring so ``cli.py`` stays a thin assembler.
"""
