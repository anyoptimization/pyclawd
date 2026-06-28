"""Discovery of local ``claude`` tmux panes and pasting review text into them.

The dashboard's review flow stages line comments and then hands them to an agent.
When that agent is an interactive ``claude`` session running in tmux on the same
host, this module finds those panes and pastes the assembled review straight into
one — closing the loop without copy/paste.

It is host-local by design: the dashboard and tmux always run on the same machine,
so these are plain ``tmux`` subprocess calls with no remote hop. Importing this
module adds no dependency beyond the standard library.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

#: Name of the tmux buffer used as a scratch space when pasting (kept off the stack).
_PASTE_BUFFER = "pyclawd-web"

#: tmux ``list-panes`` format: target, command, cwd, active flag, window name.
_PANE_FORMAT = (
    "#{session_name}:#{window_index}.#{pane_index}\t#{pane_current_command}"
    "\t#{pane_current_path}\t#{pane_active}\t#{window_name}"
)


@dataclass(frozen=True)
class Pane:
    """An interactive ``claude`` pane discovered in local tmux.

    Attributes:
        target: tmux target address (``session:window.pane``) used to send keys.
        window: The ``session:window`` portion (what the picker shows).
        cwd: The pane's current working directory.
        project: Best-effort project name for ``cwd`` (registry name, else dir name).
        name: The tmux window name.
        active: Whether this is the active pane in its window.
    """

    target: str
    window: str
    cwd: str
    project: str
    name: str
    active: bool


def _run(*args: str) -> tuple[int, str]:
    """Run a command and return ``(returncode, stdout)`` (stderr discarded)."""
    proc = subprocess.run(args, capture_output=True, text=True, errors="replace")
    return proc.returncode, proc.stdout


def list_panes(path_to_project: Mapping[str, str] | None = None) -> list[Pane]:
    """List interactive ``claude`` panes in local tmux, mapped to projects.

    Args:
        path_to_project: Optional map from absolute repo path to project name, used
            to label a pane with its registered project (falls back to the
            directory name). Pass the dashboard registry's path→name map.

    Returns:
        The discovered ``claude`` panes; empty if tmux is not running.
    """
    mapping = path_to_project or {}
    code, out = _run("tmux", "list-panes", "-a", "-F", _PANE_FORMAT)
    if code != 0:
        return []
    panes: list[Pane] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or parts[1] != "claude":
            continue
        target, _cmd, cwd, active, window_name = parts[:5]
        resolved = str(Path(cwd).resolve())
        panes.append(
            Pane(
                target=target,
                window=target.rsplit(".", 1)[0],
                cwd=cwd,
                project=mapping.get(resolved, Path(cwd).name),
                name=window_name,
                active=active == "1",
            )
        )
    return panes


def send_to_pane(
    target: str,
    text: str,
    *,
    submit: bool = False,
    focus: bool = False,
    known_targets: set[str] | None = None,
) -> bool:
    """Paste *text* into tmux pane *target* (bracketed paste preserves newlines).

    Args:
        target: tmux target address of the destination pane.
        text: The text to paste into the pane's input.
        submit: Press Enter after pasting (submit the prompt).
        focus: Select the pane's window first (bring it to the foreground).
        known_targets: Allowed targets; defaults to the current ``claude`` panes.
            The send is refused unless *target* is among them.

    Returns:
        ``True`` if the paste was issued, ``False`` if *target* is not a live pane.
    """
    valid = known_targets if known_targets is not None else {p.target for p in list_panes()}
    if target not in valid:
        return False
    if focus:
        _run("tmux", "select-window", "-t", target)
    _run("tmux", "set-buffer", "-b", _PASTE_BUFFER, text)
    _run("tmux", "paste-buffer", "-b", _PASTE_BUFFER, "-p", "-t", target)
    if submit:
        _run("tmux", "send-keys", "-t", target, "Enter")
    return True
