"""Run-id + logging primitives shared by the ``docs`` and ``test`` pipelines.

Both pipelines run long subprocesses and want the same three things: a unique
**run id**, a per-run **log file** under a single root, and a way to **stream or
capture** the subprocess output. This module is the one home for all of that, so
``cli.py`` (docs) and ``tests.py`` build on identical primitives instead of two
parallel copies.

Two output strategies live here, deliberately distinct:

- :func:`tee` — stream combined output to **both** the console and the log. Used
  by the test runner, where you watch progress live.
- :func:`run_logged` — run **quietly**, appending output to the log only. Used by
  the docs runner, whose banners (:func:`run_start` / :func:`run_finish`) frame a
  long, silent build you tail separately.

Run ids are ``"%Y%m%d-%H%M%S-<hex4>"`` (timestamp + 2 random bytes) so concurrent
runs never collide on a log filename. Logs live under :data:`LOG_ROOT`, one
sub-directory per category (``docs``, ``tests``, …).
"""

from __future__ import annotations

import secrets
import subprocess
import sys
import time
from pathlib import Path

import typer

from .run import _env

#: Root for every pyclawd run log; each pipeline gets a ``LOG_ROOT/<category>`` dir.
LOG_ROOT = Path("/tmp/pyclawd/logs")


# ---- run ids & log paths ----------------------------------------------------

def run_id() -> str:
    """Return a unique run id: a timestamp plus 2 random bytes of hex.

    Returns
    -------
    str
        An id like ``"20260622-031245-a3f9"``. The trailing hex makes the id
        (and the log filename built from it) collision-resistant when runs start
        within the same second.
    """
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def category_dir(category: str) -> Path:
    """Return the log directory for *category* (``LOG_ROOT/<category>``).

    Parameters
    ----------
    category : str
        The pipeline name, e.g. ``"docs"`` or ``"tests"``.

    Returns
    -------
    pathlib.Path
        The directory path. It is **not** created here; the run helpers
        ``mkdir`` it on first write.
    """
    return LOG_ROOT / category


def new_run(category: str) -> tuple[str, Path]:
    """Mint a run id and its default log path under *category*.

    Parameters
    ----------
    category : str
        The pipeline name (see :func:`category_dir`).

    Returns
    -------
    tuple of (str, pathlib.Path)
        The run id and ``LOG_ROOT/<category>/<run_id>.log``.
    """
    rid = run_id()
    return rid, category_dir(category) / f"{rid}.log"


# ---- banner helpers (docs style) --------------------------------------------

def run_start(label: str, category: str) -> tuple[str, Path, float]:
    """Begin a logged run: write a header to the log and print the start banner.

    Parameters
    ----------
    label : str
        Human-readable run name, e.g. ``"docs build"``.
    category : str
        The pipeline name; selects the log sub-directory.

    Returns
    -------
    tuple of (str, pathlib.Path, float)
        The run id, the log path, and a :func:`time.monotonic` start mark to pass
        back to :func:`run_finish`.
    """
    rid, log = new_run(category)
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log, "a") as fh:
        fh.write(f"=== {label} · run {rid} · STARTED {started} ===\n\n")
    typer.secho(f"{label} · run {rid} · started {started}", fg="cyan")
    typer.echo(f"  log:    {log}\n  follow: tail -f {log}")
    return rid, log, time.monotonic()


def run_finish(rid: str, log: Path, code: int, t0: float) -> None:
    """Close a logged run: write a footer, print the status line, then exit.

    Parameters
    ----------
    rid : str
        The run id from :func:`run_start`.
    log : pathlib.Path
        The run's log file; a status/elapsed footer is appended to it.
    code : int
        The subprocess exit code; also becomes this process's exit code.
    t0 : float
        The :func:`time.monotonic` start mark from :func:`run_start`.

    Raises
    ------
    typer.Exit
        Always — with *code* — so a command can ``run_finish(...)`` as its last act.
    """
    dur = time.monotonic() - t0
    elapsed = f"{int(dur // 60)}m{int(dur % 60):02d}s"
    ended = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if code == 0 else f"FAILED (exit {code})"
    with open(log, "a") as fh:
        fh.write(f"\n=== run {rid} · {status} · ENDED {ended} · elapsed {elapsed} ===\n")
    typer.secho(
        f"{'✅ done' if code == 0 else f'❌ failed (exit {code})'} · {elapsed} · run {rid} · {log}",
        fg="green" if code == 0 else "red",
    )
    raise typer.Exit(code)


# ---- subprocess runners -----------------------------------------------------

def _open_log(log: Path, cmd: list[str], mode: str, header: str):
    """Open *log* (creating parents), write the *header* + ``$ cmd`` line, return the handle.

    *header* is a literal prefix (e.g. ``""`` to truncate-and-start, ``"\\n"`` to
    visually separate when appending another command to an existing log).
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, mode)
    fh.write(header + "$ " + " ".join(map(str, cmd)) + "\n")
    fh.flush()
    return fh


def tee(cmd: list[str], log: Path, root: Path,
        env: dict[str, str] | None = None) -> int:
    """Run *cmd*, streaming combined stdout+stderr to **both** console and *log*.

    Parameters
    ----------
    cmd : list of str
        The command to run.
    log : pathlib.Path
        Log file (truncated); receives a ``$ cmd`` header then the live output.
    root : pathlib.Path
        Working directory for the subprocess.
    env : dict of str to str, optional
        Environment for the subprocess. Defaults to the repo-aware env from
        :func:`pyclawd.run._env` (repo root on ``PYTHONPATH``).

    Returns
    -------
    int
        The subprocess exit code.
    """
    with _open_log(log, cmd, "w", "") as lf:
        proc = subprocess.Popen(
            cmd, cwd=str(root), env=env or _env(root),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            lf.write(line)
        proc.wait()
    return proc.returncode


def run_logged(cmd: list[str], log: Path, root: Path,
               env: dict[str, str] | None = None) -> int:
    """Run *cmd* **quietly**, appending stdout+stderr to *log* (nothing streams).

    Tail the log for progress. Used by the docs runner, whose start/finish banners
    frame the otherwise-silent build.

    Parameters
    ----------
    cmd : list of str
        The command to run.
    log : pathlib.Path
        Log file (appended); receives a ``$ cmd`` header then the captured output.
    root : pathlib.Path
        Working directory for the subprocess.
    env : dict of str to str, optional
        Environment for the subprocess. Defaults to the repo-aware env from
        :func:`pyclawd.run._env`.

    Returns
    -------
    int
        The subprocess exit code.
    """
    with _open_log(log, cmd, "a", "\n") as fh:
        return subprocess.call(
            cmd, cwd=str(root), env=env or _env(root),
            stdout=fh, stderr=subprocess.STDOUT,
        )
