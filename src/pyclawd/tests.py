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

import argparse
import datetime
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import repo
from .logs import category_dir, run_id, tee
from .project import Project
from .run import (
    has_target,
    has_xdist,
    load_project_or_exit,
    python_prefix,
    repo_root_or_exit,
    run,
)


def _root_hash(root: Path) -> str:
    """Short, stable hash of the project root — namespaces per-project test logs."""
    return hashlib.sha1(str(root).encode()).hexdigest()[:10]


def _log_dir(project: Project) -> Path:
    """Per-project test-log directory: ``<work_dir>/logs/tests/<roothash>/``.

    Namespacing by the project root keeps ``test timings`` in one repo from ever
    reading another repo's last run (the global pointer used to leak across
    projects).
    """
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
    applies no ``-m`` filter — flexible and never crashing.
    """
    return project.test.markers.get(tier, "")


def _pretty_nodeid(classname: str, name: str, prefix: str, tests_dir: str) -> str:
    """Junit gives dotted classnames; turn them back into path-ish nodeids.

    For example, ``tests.algorithms.test_nsga2`` becomes
    ``tests/algorithms/test_nsga2.py::name``.

    *prefix* is the dotted classname prefix and *tests_dir* is the matching
    root-relative dir, both sourced from the project config.
    """
    if classname.startswith(prefix):
        path = classname[len(prefix) :].replace(".", "/")
        return f"{tests_dir}{path}.py::{name}"
    return f"{classname}::{name}" if classname else name


# ---- summary / views --------------------------------------------------------


def _summary_lines(junit: Path, rc: int, project: Project, top: int = 15) -> list[str]:
    """Parse the junit xml and BUILD the timing + failure tables and verdict line.

    Returns the report as a list of lines (caller emits to console and/or log) so the
    structured summary is identical in both places — like the docs run/render logs.
    """
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
        # Only parallelize when pytest-xdist is actually importable — otherwise
        # `-n` makes pytest hard-fail with "unrecognized arguments: -n". A missing
        # plugin degrades to a serial run with a one-line WARN, never a crash.
        if has_xdist(project):
            cmd += ["-n", jobs]
        else:
            print(
                "⚠ pytest-xdist not installed — running serial. "
                'Install it (`pip install pytest-xdist`) or set TestConfig.jobs="" '
                "to silence this warning."
            )
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
    `pyclawd test fix`).
    """
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
            f"\nnote: {len(integ)} stale entr(ies) from deselected integration suites "
            f"(re-run the tier/category that owns them — see TestConfig.markers — to refresh)."
        )
    return 1 if unit else 0


def print_timings(project: Project, top: int = 25, slow_threshold: float | None = None) -> int:
    """Print slowest tests from the most recent junit (for THIS project only).

    When *slow_threshold* is set, only tests taking longer than that many seconds
    are shown (with a hint to add ``@pytest.mark.slow``), and *top* is ignored.
    When *slow_threshold* is ``None``, the existing top-N behaviour is used.
    """
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
    if slow_threshold is not None:
        filtered = [(t, nid) for t, nid in rows if t > slow_threshold]
        if not filtered:
            print(f"No tests over {slow_threshold}s found.")
        else:
            print(
                f"⏱  {len(filtered)} tests over {slow_threshold}s"
                " (consider adding @pytest.mark.slow):"
            )
            for t, nid in filtered:
                print(f"   {t:6.2f}s  {nid}")
    else:
        shown = rows if top <= 0 else rows[:top]
        print(f"⏱  {len(rows)} tests · total {total:.1f}s cpu (slowest first)")
        for t, nid in shown:
            print(f"   {t:6.2f}s  {nid}")
    return 0


def fix(extra_args: list[str], project: Project) -> int:
    """Rerun only last-failed tests, stop on the first, stream straight to the console.

    No log, no junit. Mirrors `pyclawd docs exec`.

    Scoped to the default unit tier unless the caller passes their own ``-m`` — this
    keeps ``--lf`` from re-running stale `examples`/`docs` cache entries.
    """
    root = repo_root_or_exit()
    cmd = [*python_prefix(project), "-m", "pytest", "--lf", "-x", "-q", "-rfE"]
    if not has_target(extra_args):
        cmd.append(project.test.tests_dir)
    if "-m" not in extra_args:
        cmd += ["-m", tier_markers(project, "default")]
    cmd += extra_args
    print("$ " + " ".join(map(str, cmd)) + "\n")
    return run(cmd, root)


# ---- changed: impact-scoped test selection ----------------------------------


def _coverage_db(root: Path) -> Path:
    """The default coverage data file pytest-cov writes at the repo root."""
    return root / ".coverage"


def _source_changed_lines(project: Project, root: Path, against: str) -> dict[str, set[int]]:
    """Changed-line map restricted to source files (by ``descriptions.include``).

    Reuses ``project.descriptions.include`` (default ``.py``/``.pyx``) as the
    definition of "source file", so changes to ``.md``/``.toml`` never enter the
    impact query.
    """
    includes = [re.compile(p) for p in project.descriptions.include]
    changed = repo.changed_line_map(root, against)
    if not includes:
        return changed
    return {f: lines for f, lines in changed.items() if any(p.search(f) for p in includes)}


def run_changed(project: Project, args: list[str], against: str, list_only: bool) -> int:
    """Run only the tests whose coverage intersects the working diff (impact selection).

    Reads the per-test coverage contexts (built with ``--cov-context=test``) and
    reverse-maps the changed source lines to the tests that cover them. Files whose
    changed lines no test covers — brand-new or genuinely untested code — are reported
    loudly rather than silently skipped. With *list_only* the impacted node ids are
    printed and nothing is run.

    Args:
        project: The loaded project.
        args: Extra pytest args forwarded to the run (ignored under *list_only*).
        against: The git ref to diff against.
        list_only: When True, print the impacted node ids and run nothing.

    Returns:
        A process exit code: pytest's own when tests run, else ``0`` (nothing to run)
        or ``2`` (no usable coverage map — actionable message printed).
    """
    from .impact import CoverageUnavailable, has_test_contexts, impacted_tests

    root = repo_root_or_exit()
    db = _coverage_db(root)
    if not db.exists():
        print(
            "✗ no coverage map found (.coverage). Build it once with\n"
            "    pyclawd coverage --context\n"
            "then edit and re-run `pyclawd test changed`.",
            file=sys.stderr,
        )
        return 2
    if not has_test_contexts(db):
        print(
            "✗ coverage map has no per-test contexts. Rebuild it with\n"
            "    pyclawd coverage --context\n"
            "(the plain `pyclawd coverage` does not record contexts).",
            file=sys.stderr,
        )
        return 2

    changed = _source_changed_lines(project, root, against)
    if not changed:
        print(f"✅ no changed source files vs {against} — nothing to run.")
        return 0

    try:
        result = impacted_tests(db, root, changed)
    except CoverageUnavailable as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if result.uncovered:
        print(
            f"⚠ {len(result.uncovered)} changed file(s) have NO covering test in the map "
            "(new or untested code — the impact set cannot verify them):"
        )
        for path in sorted(result.uncovered):
            print(f"     {path}")
        print(
            "  rebuild the map (`pyclawd coverage --context`) if it is merely stale, "
            "or add tests for genuinely new code."
        )

    nodeids = sorted(result.nodeids)
    if not nodeids:
        print(
            "• no impacted tests found for the changed lines "
            "(see the uncovered note above, if any)."
        )
        return 0

    print(f"→ {len(nodeids)} impacted test(s) from {len(result.covered)} changed file(s):")
    for nid in nodeids:
        print(f"     {nid}")
    if list_only:
        return 0

    cmd = [*python_prefix(project), "-m", "pytest", "-q", "-rfE", *nodeids, *args]
    print()
    return run(cmd, root)


# ---- dispatch ---------------------------------------------------------------


class _TimingsArgError(Exception):
    """Raised by :class:`_TimingsParser` instead of exiting the process."""


class _TimingsParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` that raises rather than calling ``sys.exit``.

    The default ``ArgumentParser.error`` prints usage and calls ``sys.exit(2)``,
    which would escape :func:`dispatch` as a ``SystemExit``. We want a plain
    return-code-2 so the verb dispatch stays a normal function call.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        """Surface the parse error as an exception instead of exiting."""
        raise _TimingsArgError(message)


def _parse_timings_args(args: list[str]) -> tuple[int, float | None]:
    """Parse the ``timings`` verb's ``--top`` / ``--slow-threshold`` flags.

    Accepts both the space form (``--top 10``) and the equals form
    (``--top=10``); same for ``--slow-threshold``. Defaults match the
    :func:`print_timings` signature (``top=25``, ``slow_threshold=None``).

    Args:
        args: The argument tokens after the ``timings`` verb.

    Returns:
        The parsed ``(top, slow_threshold)`` pair.

    Raises:
        _TimingsArgError: If a value cannot be coerced to the expected type.
    """

    def _as_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--top expects an integer, got {value!r}") from None

    def _as_float(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"--slow-threshold expects a float, got {value!r}"
            ) from None

    parser = _TimingsParser(prog="pyclawd test timings", add_help=False)
    parser.add_argument("--top", type=_as_int, default=25)
    parser.add_argument("--slow-threshold", type=_as_float, default=None)
    ns = parser.parse_args(args)
    return ns.top, ns.slow_threshold


def _parse_changed_args(args: list[str]) -> tuple[str, bool, list[str]]:
    """Parse the ``changed`` verb's ``--against`` / ``--list`` flags.

    Unrecognised tokens are returned as *extra* pytest args (forwarded to the run),
    so ``pyclawd test changed -x`` still works. Accepts both ``--against main`` and
    ``--against=main``.

    Args:
        args: The tokens after the ``changed`` verb.

    Returns:
        The parsed ``(against, list_only, extra_pytest_args)`` triple.

    Raises:
        _TimingsArgError: If a flag is malformed.
    """
    parser = _TimingsParser(prog="pyclawd test changed", add_help=False)
    parser.add_argument("--against", default="HEAD")
    parser.add_argument("--list", dest="list_only", action="store_true")
    ns, extra = parser.parse_known_args(args)
    return ns.against, ns.list_only, extra


def dispatch(verb: str, args: list[str]) -> int:
    """Route a test sub-command verb (run/fast/all/changed/failures/timings/fix) to its handler."""
    project = load_project_or_exit()
    jobs = project.test.jobs
    if verb == "changed":
        try:
            against, list_only, extra = _parse_changed_args(args)
        except _TimingsArgError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        return run_changed(project, extra, against, list_only)
    if verb == "run":
        return run_suite(args, tier_markers(project, "default"), "run", project, jobs=jobs)
    if verb == "fast":
        return run_suite(args, tier_markers(project, "fast"), "fast", project, jobs=jobs)
    if verb == "all":
        return run_suite(args, tier_markers(project, "all"), "all", project, jobs=jobs)
    if verb == "failures":
        return print_failures(project)
    if verb == "timings":
        try:
            top, slow_threshold = _parse_timings_args(args)
        except _TimingsArgError as exc:
            print(f"✗ {exc}", file=sys.stderr)
            return 2
        return print_timings(project, top, slow_threshold)
    if verb == "fix":
        return fix(args, project)
    raise ValueError(f"unknown test verb: {verb}")
