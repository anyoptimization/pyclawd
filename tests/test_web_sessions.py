"""Unit tests for tmux pane discovery and sending (:mod:`pyclawd.web.sessions`).

tmux is not assumed present, so these stub the module's ``_run`` helper to feed
canned ``tmux`` output and to record the commands a send would issue.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyclawd.web import sessions


def test_list_panes_keeps_only_claude_and_maps_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    output = (
        "main:0.0\tclaude\t/home/u/work/alpha\t1\tedit\n"
        "main:0.1\tzsh\t/home/u/work/alpha\t0\tshell\n"  # not claude → dropped
        "main:1.0\tclaude\t/home/u/work/beta\t0\treview\n"
    )
    monkeypatch.setattr(sessions, "_run", lambda *a: (0, output))

    mapping = {str(Path("/home/u/work/alpha").resolve()): "Alpha"}
    panes = sessions.list_panes(mapping)

    assert [p.target for p in panes] == ["main:0.0", "main:1.0"]
    assert panes[0].project == "Alpha"  # from the mapping
    assert panes[0].active is True
    assert panes[1].project == "beta"  # fallback to directory name
    assert panes[0].window == "main:0"


def test_list_panes_empty_when_tmux_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions, "_run", lambda *a: (1, ""))
    assert sessions.list_panes() == []


def test_send_refuses_unknown_target() -> None:
    assert sessions.send_to_pane("nope:0.0", "hi", known_targets=set()) is False


def test_send_issues_paste_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(sessions, "_run", lambda *a: calls.append(a) or (0, ""))

    ok = sessions.send_to_pane(
        "main:0.0", "please fix", submit=True, focus=True, known_targets={"main:0.0"}
    )
    assert ok is True
    verbs = [c[1] for c in calls]
    assert verbs == ["select-window", "set-buffer", "paste-buffer", "send-keys"]
    assert calls[-1][-1] == "Enter"  # submit pressed Enter


def test_send_without_submit_or_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(sessions, "_run", lambda *a: calls.append(a) or (0, ""))

    sessions.send_to_pane("main:0.0", "note", known_targets={"main:0.0"})
    verbs = [c[1] for c in calls]
    assert verbs == ["set-buffer", "paste-buffer"]  # no select-window, no send-keys
