"""Minimal `pyclawd docs` runner — the worked example of a docs toolchain.

`pyclawd docs <verb>` delegates to this CLI (via `uvx --from ./docs pyclawd-docs`).
It implements the contract `pyclawd/commands/docs.py` expects, using the standard
notebook-docs stack so `pyclawd docs timings` / `failures` work too:

    compile [pages]   .md  -> .ipynb            (jupytext, no execution)
    run     [pages]   .ipynb execute + cache    (jupyter-cache; only stale run)
    build   [--fast]  .ipynb -> HTML            (sphinx + nbsphinx; --fast drops notebooks)
    all     [--force] [--continue]              (compile -> run -> build)
    exec    <page>    execute ONE, stream error (the debug loop)
    clean             remove build/ + generated .ipynb (keep the cache)

Paths the pipeline relies on (all under the docs dir): sources in `source/`, the
jupyter-cache at `.jupyter_cache/global.db`, and rendered HTML in `build/html/`.
Invoked from the repo root, this chdir's into `docs/` so those relative paths hold.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import time
from pathlib import Path

SOURCE = "source"
CACHE = ".jupyter_cache"
HTML_OUT = "build/html"
EXEC_TIMEOUT = 120


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _chdir_to_docs() -> None:
    """chdir into the docs dir (the one holding `source/`), as the contract expects."""
    if Path(SOURCE).is_dir():
        return
    for cand in (Path("docs"), Path("../docs"), Path("../../docs")):
        if (cand / SOURCE).is_dir():
            os.chdir(cand)
            return
    sys.exit("✗ could not find a docs directory containing 'source/'")


def _md_sources(files: list[str] | None) -> list[str]:
    """The .md sources to act on: an explicit list, else every page under source/."""
    if files:
        return [f if f.endswith(".md") else f"{f}.md" for f in files]
    return sorted(glob.glob(f"{SOURCE}/**/*.md", recursive=True))


def _normalize_kernel(nb_path: Path) -> None:
    """Force the notebook's kernel to `python3` so execution never hits NoSuchKernel."""
    import nbformat

    nb = nbformat.read(nb_path, 4)
    if nb.metadata.get("kernelspec", {}).get("name") != "python3":
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3"}
        nbformat.write(nb, nb_path)


# --------------------------------------------------------------------------- #
# Verbs.
# --------------------------------------------------------------------------- #


def compile_notebooks(files: list[str] | None = None, force: bool = False) -> int:
    """Convert .md sources to .ipynb (no execution). Only changed pages unless --force."""
    todo = []
    for md in _md_sources(files):
        nb = Path(md).with_suffix(".ipynb")
        if force or not nb.exists() or Path(md).stat().st_mtime > nb.stat().st_mtime:
            todo.append(md)
    if not todo:
        print("✓ notebooks up to date (use --force to rebuild all)")
        return 0
    print(f"📝 compiling {len(todo)} page(s) → .ipynb")
    subprocess.run([sys.executable, "-m", "jupytext", "--to", "notebook", *todo], check=True)
    for md in todo:
        _normalize_kernel(Path(md).with_suffix(".ipynb"))
    return 0


def run_notebooks(files: list[str] | None = None, force: bool = False) -> int:
    """Execute notebooks and cache successes (jupyter-cache); only stale ones run.

    Returns the number of failures (0 = all good). A failed notebook is left
    uncached, so `pyclawd docs failures` reports it as not-passing.
    """
    from jupyter_cache import get_cache
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError
    import nbformat

    nbs = [
        str(Path(md).with_suffix(".ipynb").resolve())
        for md in _md_sources(files)
        if Path(md).with_suffix(".ipynb").exists()
    ]
    if not nbs:
        print("no notebooks to execute (run 'compile' first)")
        return 0

    cache = get_cache(CACHE)
    stale = []
    for nb in nbs:
        if force:
            stale.append(nb)
            continue
        try:
            cache.match_cache_file(nb)  # cached → skip
        except KeyError:
            stale.append(nb)

    print(f"⚙  executing {len(stale)} stale · {len(nbs) - len(stale)} cached")
    failures = 0
    for nb in stale:
        name = os.path.relpath(nb, Path(SOURCE).resolve())
        node = nbformat.read(nb, 4)
        node.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3"}
        t0 = time.monotonic()
        try:
            NotebookClient(
                node,
                timeout=EXEC_TIMEOUT,
                kernel_name="python3",
                resources={"metadata": {"path": str(Path(nb).parent)}},
            ).execute()
            nbformat.write(node, nb)
            cache.cache_notebook_file(nb, data={"execution_seconds": time.monotonic() - t0}, overwrite=True)
            print(f"  [{name}] ok · {time.monotonic() - t0:.1f}s")
        except (CellExecutionError, Exception) as exc:  # noqa: BLE001 - any failure is reported
            nbformat.write(node, nb)
            failures += 1
            print(f"  [{name}] FAILED · {str(exc).splitlines()[-1][:100]}")

    # Hydrate every notebook from the cache so nbsphinx renders outputs.
    for nb in nbs:
        try:
            cache.merge_match_into_file(nb)
        except Exception:  # noqa: BLE001 - uncached (a failure) → leave as-is
            pass
    return failures


def build_html(fast: bool = False) -> int:
    """Render HTML with sphinx + nbsphinx. --fast excludes notebooks (smoke render)."""
    env = dict(os.environ)
    if fast:
        env["PYCLAWD_DOCS_FAST"] = "1"
    print(f"🔨 sphinx-build → {HTML_OUT}" + (" (fast: no notebooks)" if fast else ""))
    return subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "html", SOURCE, HTML_OUT], env=env, check=False
    ).returncode


def exec_single(page: str) -> int:
    """Compile + execute ONE page directly, streaming its error (the debug loop)."""
    name = page.removesuffix(".ipynb").removesuffix(".md")
    md = name if name.startswith(f"{SOURCE}/") else f"{SOURCE}/{name}"
    md = f"{md}.md"
    if not Path(md).exists():
        sys.exit(f"✗ source not found: {md}")
    subprocess.run([sys.executable, "-m", "jupytext", "--to", "notebook", md], check=True)
    nb = Path(md).with_suffix(".ipynb")
    _normalize_kernel(nb)
    rc = subprocess.run(
        [sys.executable, "-m", "jupyter", "execute", "--kernel_name=python3", str(nb)], check=False
    ).returncode
    return rc


def clean() -> int:
    """Remove build/ and generated .ipynb (the execution cache is kept)."""
    import shutil

    shutil.rmtree("build", ignore_errors=True)
    removed = 0
    for nb in glob.glob(f"{SOURCE}/**/*.ipynb", recursive=True):
        Path(nb).unlink()
        removed += 1
    print(f"🧹 removed build/ and {removed} generated .ipynb (cache kept)")
    return 0


def build_all(force: bool = False, cont: bool = False) -> int:
    """compile → run → build. A run failure stops before render unless --continue."""
    compile_notebooks(force=force)
    failures = run_notebooks(force=force)
    if failures and not cont:
        print(f"✗ {failures} notebook(s) failed — not rendering (use --continue to render anyway)")
        return 1
    return build_html()


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #


def main() -> None:
    """Parse the verb and dispatch. Mirrors what `pyclawd docs` forwards."""
    parser = argparse.ArgumentParser(prog="pyclawd-docs", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help=".md -> .ipynb")
    p_compile.add_argument("pages", nargs="*")
    p_compile.add_argument("--force", action="store_true")

    p_run = sub.add_parser("run", help="execute notebooks (cached)")
    p_run.add_argument("pages", nargs="*")
    p_run.add_argument("--force", action="store_true")

    p_build = sub.add_parser("build", help="render HTML")
    p_build.add_argument("--fast", action="store_true")

    p_all = sub.add_parser("all", help="compile + run + build")
    p_all.add_argument("--force", action="store_true")
    p_all.add_argument("--continue", dest="cont", action="store_true")

    p_exec = sub.add_parser("exec", help="execute ONE page, stream its error")
    p_exec.add_argument("page")

    sub.add_parser("clean", help="remove build/ + generated .ipynb")

    args = parser.parse_args()
    _chdir_to_docs()

    if args.command == "compile":
        rc = compile_notebooks(args.pages or None, args.force)
    elif args.command == "run":
        rc = run_notebooks(args.pages or None, args.force)
    elif args.command == "build":
        rc = build_html(args.fast)
    elif args.command == "all":
        rc = build_all(args.force, args.cont)
    elif args.command == "exec":
        rc = exec_single(args.page)
    elif args.command == "clean":
        rc = clean()
    else:  # pragma: no cover - argparse guards this
        rc = 2
    sys.exit(rc)


if __name__ == "__main__":
    main()
