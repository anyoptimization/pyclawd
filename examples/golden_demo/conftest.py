"""Wires the ``golden`` fixture into this demo package (the future pytest plugin).

In the shipped feature this lives in a pyclawd-provided pytest plugin so any
adopting project gets the ``golden`` fixture and ``@pytest.mark.golden`` marker
for free. Here it is a local ``conftest.py`` so the worked example runs
self-contained against ``pyclawd.golden``.

Update mode (record/bless baselines) is toggled by ``PYCLAWD_GOLDEN_UPDATE=1`` —
which is what ``pyclawd golden update`` would set. By default the fixture is in
gate mode: it *compares* against the committed baseline and fails on drift.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyclawd.golden import GoldenStore, Recorder


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``golden`` marker so ``-m golden`` selects the oracle tier."""
    config.addinivalue_line("markers", "golden: behavior-regression snapshot test.")


def _node_key(node: pytest.Item) -> str:
    """Derive the snapshot key from a test node id.

    For a parametrized test the id already carries the ``[param]`` suffix
    (e.g. ``test_minimize[zdt1-de]``), which becomes the stable per-case key.

    Args:
        node: The running pytest item.

    Returns:
        The function name plus any parametrization suffix.
    """
    name = node.nodeid.split("::")[-1]
    if "[" in name and not name.split("[", 1)[1].rstrip("]").split("-")[0].isdigit():
        return name
    return name


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> Recorder:
    """Yield the per-test snapshot recorder bound to this module's baseline file.

    Baselines live in ``<module-dir>/golden/<module>.json`` — one file per test
    module for surgical, conflict-free diffs.

    Args:
        request: The pytest fixture request (gives the node id and module path).

    Returns:
        A :class:`~pyclawd.golden.Recorder` in gate mode (or update mode when
        ``PYCLAWD_GOLDEN_UPDATE=1``).
    """
    module_file = Path(request.node.module.__file__)
    store_path = module_file.parent / "golden" / f"{module_file.stem}.json"
    store = GoldenStore(store_path)
    update = os.environ.get("PYCLAWD_GOLDEN_UPDATE") == "1"
    # The shipped feature stamps the project/tool version here (read from config);
    # the demo uses a fixed string so the recorded baseline is deterministic.
    recorder = Recorder(store, _node_key(request.node), update=update, blessed_on="demo-0.1.0")
    yield recorder
    if update:
        store.save()
