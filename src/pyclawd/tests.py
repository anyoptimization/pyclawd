"""Test pipeline for pyclawd — the `pyclawd test` verbs, mirroring `pyclawd docs`.

The mental model is the same as docs: a logged, instrumented runner that emits
per-item **timing** and **failure** tables, a **failures** fix-list (read from
pytest's own ``lastfailed`` cache), a **timings** view, and a single-shot **fix**
debug primitive that streams the next failure to the console.

Tiers come from the loaded project's ``test.markers`` config (keyed ``fast`` /
``default`` / ``all``): ``fast`` is the <30s smoke tier (run under xdist),
``default`` is the comprehensive gate, and ``all`` is everything. No tier marker
expression is hardcoded here — they all live in ``.pyclawd/config.py``.

Logs land under ``<work_dir>/logs/tests/<label>-<run-id>.log`` (the work dir is
project-configurable — see :func:`pyclawd.logs.work_root`) with a sibling
``.junit.xml`` that the timing/summary views parse. Pytest keeps the authoritative
last-failed set in ``.pytest_cache/v/cache/lastfailed`` — ``failures`` reads that, so
it is never stale relative to the runner.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .logs import category_dir, run_id, tee
from .project import Project
from .run import has_target, load_project_or_exit, python_prefix, repo_env, repo_root_or_exit


def _root_hash(root: Path) -> str:
    """Short, stable hash of the project root — namespaces per-project test logs."""
    return hashlib.sha1(str(root).encode()).hexdigest()[:10]


def _log_dir(project: Project) -> Path:
    """Per-project test-log directory: ``<work_dir>/logs/tests/<roothash>/``.

    Namespacing by the project root keeps ``test timings`` in one repo from ever
    reading another repo's last run (the global pointer used to leak across
    projects)."""
    return category_dir("tests", project) / _root_hash(project.root if project.root else Path.cwd())


def _junit_ptr(project: Project) -> Path:
    """The 'latest junit' pointer file for *project* (inside its namespaced dir)."""
    return _log_dir(project) / "latest-junit.txt"


# ---- low-level helpers ------------------------------------------------------


def tier_markers(project: Project, tier: str) -> str:
    """Marker expression for a named test tier, or ``""`` if the project omits it.

    The tier set (``default`` / ``fast`` / ``all`` / …) is project-defined config,
    so a project is free to drop or rename tiers. Looking the value up with a
    plain ``markers[tier]`` would raise an uncaught :class:`KeyError` (a raw
    traceback) the moment someone runs ``pyclawd test fast`` against a config that
    only defines ``default``. Falling back to ``""`` means an undefined tier simply
    applies no ``-m`` filter — flexible and never crashing."""
    return project.test.markers.get(tier, "")


def _pretty_nodeid(classname: str, name: str, prefix: str, tests_dir: str) -> str:
    """junit gives dotted classnames (tests.algorithms.test_nsga2); turn that back
    into the path-ish nodeid (tests/algorithms/test_nsga2.py::name).

    *prefix* is the dotted classname prefix and *tests_dir* is the matching
    root-relative dir, both sourced from the project config."""
    if classname.startswith(prefix):
        path = classname[len(prefix) :].replace(".", "/")
        return f"{tests_dir}{path}.py::{name}"
    return f"{classname}::{name}" if classname else name


# ---- summary / views --------------------------------------------------------


def _summary_lines(junit: Path, rc: int, project: Project, top: int = 15) -> list[str]:
    """Parse the junit xml and BUILD the timing + failure tables and verdict line.

    Returns the report as a list of lines (caller emits to console and/or log) so the
    structured summary is identical in both places — like the docs run/render logs."""
    if not junit.exists():
        return [f"\ntests · no junit produced (collection error?) · exit {rc}"]
    prefix, tests_dir = project.test.classname_prefix, project.test.tests_dir
    rows: list[tuple[float, str]] = []
    fails: list[tuple[str, str]] = []
    npass = nfail = nerr = nskip = 0
    total = 0.0
    for c in ET.parse(junit).getroot().iter("testcase"):
        t = float(c.get("time") or 0.0)
        total += t
        nid = _pretty_nodeid(c.get("classname", ""), c.get("name", ""), prefix, tests_dir)
        rows.append((t, nid))
        failure, error, skipped = c.find("failure"), c.find("error"), c.find("skipped")
        if failure is not None:
            nfail += 1
            fails.append((nid, (failure.get("message") or "").strip()))
        elif error is not None:
            nerr += 1
            fails.append((nid, (error.get("message") or "").strip()))
        elif skipped is not None:
            nskip += 1
        else:
            npass += 1

    rows.sort(reverse=True)
    out = ["", "⏱  slowest tests:"]
    out += [f"   {t:6.2f}s  {nid}" for t, nid in rows[:top]]

    if fails:
        out += ["", f"❌ {len(fails)} failing test(s):"]
        for nid, msg in fails[:40]:
            head = msg.splitlines()[0][:120] if msg else ""
            out.append(f"   {nid}  {head}")
        if len(fails) > 40:
            out.append(f"   … and {len(fails) - 40} more")

    ok = nfail == 0 and nerr == 0
    verdict = "✅ all passed" if ok else f"❌ {nfail} failed · {nerr} error"
    out += [
        "",
        (
            f"tests · {npass} passed · {nfail} failed · {nerr} error · "
            f"{nskip} skipped · {total:.1f}s cpu · {verdict}"
        ),
    ]
    return out


def run_suite(
    extra_args: list[str], markers: str, label: str, project: Project, jobs: str | None = None
) -> int:
    """Run the suite, tee to a run-id log, then print timing + failure tables."""
    root = repo_root_or_exit()
    log_dir = _log_dir(project)
    log_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id()
    log = log_dir / f"{label}-{rid}.log"
    junit = log_dir / f"{label}-{rid}.junit.xml"

    cmd = [
        *python_prefix(project),
        "-m",
        "pytest",
        "-q",
        f"--junit-xml={junit}",
        "--durations=25",
        "-rfE",
    ]
    if not has_target(extra_args):
        cmd.append(project.test.tests_dir)
    if jobs and "-n" not in extra_args:  # explicit -n in the caller's args wins
        cmd += ["-n", jobs]
    if "-m" not in extra_args and markers:
        cmd += ["-m", markers]
    cmd += extra_args

    started = datetime.datetime.now()
    header = f"tests · {label} · run {rid} · started {started:%Y-%m-%d %H:%M:%S}"
    print(header)
    print(f"  log:   {log}")
    rc = tee(cmd, log, root)
    _junit_ptr(project).write_text(str(junit))

    # Build the structured summary once, then emit it to BOTH the console and the log
    # so the log file is self-contained (matches the docs run/render logs).
    elapsed = (datetime.datetime.now() - started).total_seconds()
    report = _summary_lines(junit, rc, project)
    report.append(f"\nwall {elapsed:.1f}s · exit {rc} · junit {junit.name}")
    text = "\n".join(report)
    print(text)
    with open(log, "a") as lf:
        lf.write(f"\n{'=' * 72}\n{header}\n{text}\n")
    return rc


# Integration suites that the unit tiers deselect (from `project.test.integration_files`).
# pytest's lastfailed cache never clears entries for *deselected* tests (they never
# re-run to "pass"), so these linger and inflate the count — separate them from the
# live unit fix-list.


def _is_integration(nodeid: str, integration_files: list[str]) -> bool:
    return nodeid.split("::", 1)[0] in integration_files


def print_failures(project: Project) -> int:
    """Print the fix-list: pytest's lastfailed cache, unit failures first.

    A project's integration suites (``TestConfig.integration_files``) are deselected by
    the unit tiers, so their stale cache entries are listed separately (they don't block
    `pyclawd test fix`)."""
    root = repo_root_or_exit()
    lf = root / ".pytest_cache" / "v" / "cache" / "lastfailed"
    if not lf.exists():
        print("✅ no lastfailed cache — run `pyclawd test run` first (or all green).")
        return 0
    data = json.loads(lf.read_text() or "{}")
    integration_files = project.test.integration_files
    nodes = sorted(data)
    unit = [n for n in nodes if not _is_integration(n, integration_files)]
    integ = [n for n in nodes if _is_integration(n, integration_files)]

    if not unit:
        print("✅ no failing unit tests recorded (default tier is clean).")
    else:
        by_file: dict[str, list[str]] = {}
        for nid in unit:
            by_file.setdefault(nid.split("::", 1)[0], []).append(nid)
        print(f"❌ {len(unit)} failing unit test(s) in {len(by_file)} file(s):")
        for f in sorted(by_file):
            print(f"\n  {f}  ({len(by_file[f])})")
            for nid in by_file[f]:
                print(f"     {nid.split('::', 1)[1]}")
        print("\nDebug the next one:  pyclawd test fix        (runs --lf -x within the tier)")

    if integ:
        print(
            f"\nℹ️  {len(integ)} stale entr(ies) from deselected integration suites "
            f"(re-run the tier/category that owns them — see TestConfig.markers — to refresh)."
        )
    return 1 if unit else 0


def print_timings(project: Project, top: int = 25) -> int:
    """Print slowest tests from the most recent junit (for THIS project only)."""
    junit_ptr = _junit_ptr(project)
    if not junit_ptr.exists():
        print("No timings yet — run `pyclawd test run` (or `fast`) first.")
        return 0
    junit = Path(junit_ptr.read_text().strip())
    if not junit.exists():
        print("No timings yet — last junit is gone; re-run `pyclawd test run`.")
        return 0
    prefix, tests_dir = project.test.classname_prefix, project.test.tests_dir
    rows: list[tuple[float, str]] = []
    total = 0.0
    for c in ET.parse(junit).getroot().iter("testcase"):
        t = float(c.get("time") or 0.0)
        total += t
        rows.append(
            (t, _pretty_nodeid(c.get("classname", ""), c.get("name", ""), prefix, tests_dir))
        )
    rows.sort(reverse=True)
    shown = rows if top <= 0 else rows[:top]
    print(f"⏱  {len(rows)} tests · total {total:.1f}s cpu (slowest first)")
    for t, nid in shown:
        print(f"   {t:6.2f}s  {nid}")
    return 0


def fix(extra_args: list[str], project: Project) -> int:
    """The debug primitive: rerun only last-failed, stop on the first, stream it
    straight to the console (no log, no junit). Mirrors `pyclawd docs exec`.

    Scoped to the default unit tier unless the caller passes their own ``-m`` — this
    keeps ``--lf`` from re-running stale `examples`/`docs` cache entries."""
    root = repo_root_or_exit()
    cmd = [*python_prefix(project), "-m", "pytest", "--lf", "-x", "-q", "-rfE"]
    if not has_target(extra_args):
        cmd.append(project.test.tests_dir)
    if "-m" not in extra_args:
        cmd += ["-m", tier_markers(project, "default")]
    cmd += extra_args
    print("$ " + " ".join(map(str, cmd)) + "\n")
    return subprocess.call(cmd, cwd=str(root), env=repo_env(root))


# ---- dispatch ---------------------------------------------------------------


def dispatch(verb: str, args: list[str]) -> int:
    project = load_project_or_exit()
    jobs = project.test.jobs
    if verb == "run":
        return run_suite(args, tier_markers(project, "default"), "run", project, jobs=jobs)
    if verb == "fast":
        return run_suite(args, tier_markers(project, "fast"), "fast", project, jobs=jobs)
    if verb == "all":
        return run_suite(args, tier_markers(project, "all"), "all", project, jobs=jobs)
    if verb == "failures":
        return print_failures(project)
    if verb == "timings":
        top = 25
        for i, a in enumerate(args):
            raw: str | None = None
            if a == "--top" and i + 1 < len(args):
                raw = args[i + 1]
            elif a.startswith("--top="):
                raw = a.split("=", 1)[1]
            if raw is None:
                continue
            try:
                top = int(raw)
            except ValueError:
                print(f"✗ --top expects an integer, got {raw!r}", file=sys.stderr)
                return 2
        return print_timings(project, top)
    if verb == "fix":
        return fix(args, project)
    raise ValueError(f"unknown test verb: {verb}")
