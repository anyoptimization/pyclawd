"""The ``pyclawd web`` dashboard — a live, multi-project diff & review UI.

This package is an **optional extra** (``pip install pyclawd[web]``): it serves a
small web app for watching changes across your repos while agents work, reviewing
diffs, staging line comments, and driving the pyclawd verb contract (test / check
/ golden) from the browser.

The package is layered so the heavy, web-only dependencies stay quarantined:

* :mod:`pyclawd.web.git` — a pure, typed git layer (no web deps). Diffs, change
  lists, ref/commit metadata, and a content-aware state token. Fully unit-tested
  in isolation.
* :mod:`pyclawd.web.registry` — the multi-project registry (discover under roots,
  star, add/remove), persisted to ``~/.pyclawd``.
* :mod:`pyclawd.web.sessions` — discovery of local ``claude`` tmux panes and
  pasting review text into them.
* ``pyclawd.web.app`` (added in a later phase) — the FastAPI application; the only
  module that imports FastAPI/uvicorn/watchfiles.

Importing this package never pulls in FastAPI: the CLI command imports the web
stack lazily so ``pyclawd`` itself stays a tiny ``typer`` + ``rich`` install.
"""

from __future__ import annotations
