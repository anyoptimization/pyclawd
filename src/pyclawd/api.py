"""Public-API surface oracle: extract a package's public surface and prove it unchanged.

This is a sibling of :mod:`pyclawd.golden`. golden proves an observable *value* is
unchanged; api proves the *public surface* is unchanged, catching an **accidental**
breaking change (a removed function, a renamed or reordered parameter, a changed
return annotation) that an edit did not intend.

Design:

- **Static extraction, never import.** The surface is read with :mod:`ast`, so it is
  deterministic across environments and has zero import side effects. The tradeoff:
  a dynamically generated export (built at import time, not visible in the source
  AST) is not seen — declare those in ``__all__`` if they matter, or accept that api
  covers the statically declared surface.
- **Public = ``__all__`` when present, else non-underscore.** A module that defines
  ``__all__`` owns its surface exactly; otherwise every top-level name not starting
  with ``_`` (plus a class's ``__init__``) is public.
- **One flat, sorted text baseline.** Each symbol renders to one line
  (``pkg.module:Name(signature)``); a ``git diff`` of the baseline then reads like an
  API changelog. Removals/changes are breaking (fail); pure additions pass with a
  note unless the project opts into strict mode.

The module is **dependency-free** (stdlib ``ast`` only) — the engine behind the
:mod:`pyclawd.commands.api` command layer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


def module_qualname(py_file: Path, package_dir: Path) -> str:
    """Derive a dotted module name for *py_file* under *package_dir*.

    The package's own directory name is included so two packages with a same-named
    submodule never collide (``pkg_a.util`` vs ``pkg_b.util``). An ``__init__.py``
    maps to its package (the directory), not a ``.__init__`` submodule.

    Args:
        py_file: The ``.py`` source file.
        package_dir: The walked package root (its name is the top of the dotted path).

    Returns:
        The dotted module name (e.g. ``"pyclawd.commands.api"``).
    """
    rel = py_file.relative_to(package_dir.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _render_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render a function/method signature as ``(args) -> return`` from its AST node.

    Uses :func:`ast.unparse` on the ``arguments`` node so positional-only, keyword-only,
    defaults, ``*args``/``**kwargs``, and annotations all render canonically. An
    ``async def`` is suffixed with ``[async]`` so changing sync↔async shows as drift.

    Args:
        node: The function or method definition node.

    Returns:
        The signature text, e.g. ``"(self, *rel: str) -> Path"``.
    """
    args = ast.unparse(node.args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    suffix = " [async]" if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"({args}){ret}{suffix}"


def _is_public(name: str) -> bool:
    """Whether *name* is public (non-underscore); ``__init__`` is special-cased by callers."""
    return not name.startswith("_")


def _class_bases(node: ast.ClassDef) -> str:
    """Render a class's base list as ``(Base1, Base2)`` (empty string when there are none)."""
    bases = [ast.unparse(b) for b in node.bases]
    return f"({', '.join(bases)})" if bases else ""


def _public_names_from_all(module: ast.Module) -> set[str] | None:
    """Return the names listed in a module-level ``__all__``, or ``None`` if absent.

    Args:
        module: The parsed module.

    Returns:
        The set of string literals assigned to ``__all__`` at module level, or
        ``None`` when the module defines no ``__all__`` (fall back to the
        non-underscore rule).
    """
    for stmt in module.body:
        targets = (
            stmt.targets
            if isinstance(stmt, ast.Assign)
            else [stmt.target]
            if isinstance(stmt, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                value = stmt.value if isinstance(stmt, (ast.Assign, ast.AnnAssign)) else None
                if isinstance(value, (ast.List, ast.Tuple)):
                    return {
                        el.value
                        for el in value.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    }
    return None


def extract_module(source: str, qualname: str) -> list[str]:
    """Extract the public-surface lines for one module's *source*.

    Args:
        source: The module's Python source text.
        qualname: The dotted module name used as the ``pkg.module`` line prefix.

    Returns:
        Surface lines (unsorted), one per public function/class/method/constant.
    """
    module = ast.parse(source)
    allowed = _public_names_from_all(module)

    def public(name: str) -> bool:
        return name in allowed if allowed is not None else _is_public(name)

    lines: list[str] = []
    for stmt in module.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if public(stmt.name):
                lines.append(f"{qualname}:{stmt.name}{_render_signature(stmt)}")
        elif isinstance(stmt, ast.ClassDef):
            if not public(stmt.name):
                continue
            lines.append(f"{qualname}:{stmt.name}{_class_bases(stmt)}")
            for member in stmt.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                # A class's methods are surface if public, plus __init__ (its
                # constructor signature is API even though it is dunder).
                if _is_public(member.name) or member.name == "__init__":
                    lines.append(f"{qualname}:{stmt.name}.{member.name}{_render_signature(member)}")
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and public(target.id):
                    lines.append(f"{qualname}:{target.id}")
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and public(stmt.target.id)
        ):
            lines.append(f"{qualname}:{stmt.target.id}: {ast.unparse(stmt.annotation)}")
    return lines


def extract_surface(package_dirs: list[Path]) -> list[str]:
    """Extract the sorted, de-duplicated public surface across *package_dirs*.

    Args:
        package_dirs: Package root directories to walk for ``.py`` files.

    Returns:
        The full surface as sorted unique lines. Files that fail to parse are
        skipped (a syntax error is a separate concern for lint/typecheck to catch).
    """
    lines: set[str] = set()
    for package_dir in package_dirs:
        if not package_dir.is_dir():
            continue
        for py_file in sorted(package_dir.rglob("*.py")):
            try:
                source = py_file.read_text()
            except OSError:
                continue
            try:
                lines.update(extract_module(source, module_qualname(py_file, package_dir)))
            except SyntaxError:
                continue
    return sorted(lines)


def _symbol_key(line: str) -> str:
    """The identity of a surface *line* (everything up to the signature parens).

    Two lines with the same key but different text are a **signature change**; a key
    present on only one side is an add or a removal.

    Args:
        line: A surface line from :func:`extract_module`.

    Returns:
        The symbol key, e.g. ``"pyclawd.project:Project.path"``.
    """
    qualname, rest = line.split(":", 1)
    # Strip the signature: callables/classes-with-bases carry a ``(...)``; an
    # annotated constant carries a ``: annotation``. Everything else is the bare name.
    symbol = rest.split("(", 1)[0] if "(" in rest else rest.split(":", 1)[0]
    return f"{qualname}:{symbol.strip()}"


@dataclass(frozen=True)
class SurfaceDiff:
    """The difference between a current surface and a committed baseline.

    Args:
        added: Surface lines present now but not in the baseline (new symbols).
        removed: Surface lines in the baseline but gone now (breaking).
        changed: ``(baseline_line, current_line)`` pairs sharing a symbol key whose
            signature differs (breaking).
    """

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[tuple[str, str]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Whether the surface is identical to the baseline (no add/remove/change)."""
        return not (self.added or self.removed or self.changed)

    def is_breaking(self) -> bool:
        """Whether the diff removes or changes a symbol (an addition alone is not breaking)."""
        return bool(self.removed or self.changed)


def diff_surface(current: list[str], baseline: list[str]) -> SurfaceDiff:
    """Compare a *current* surface against a *baseline* surface.

    A symbol key on both sides with differing text is a **changed** signature; a key
    on one side only is an **added** or **removed** symbol.

    Args:
        current: The freshly extracted surface lines.
        baseline: The committed baseline surface lines.

    Returns:
        A :class:`SurfaceDiff` categorising every difference.
    """
    cur = {_symbol_key(line): line for line in current}
    base = {_symbol_key(line): line for line in baseline}
    added = [cur[k] for k in cur if k not in base]
    removed = [base[k] for k in base if k not in cur]
    changed = [(base[k], cur[k]) for k in cur if k in base and cur[k] != base[k]]
    return SurfaceDiff(
        added=sorted(added),
        removed=sorted(removed),
        changed=sorted(changed),
    )


def read_baseline(path: Path) -> list[str]:
    """Read a committed surface baseline file into a list of non-empty lines.

    Args:
        path: The baseline file path.

    Returns:
        The baseline surface lines (empty when the file does not exist).
    """
    if not path.exists():
        return []
    return [ln for ln in path.read_text().splitlines() if ln.strip()]


def write_baseline(path: Path, surface: list[str]) -> None:
    """Write *surface* to the baseline *path* as sorted, newline-terminated text.

    Args:
        path: The baseline file to write (parent dirs are created).
        surface: The surface lines to record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(surface)) + "\n" if surface else "")
