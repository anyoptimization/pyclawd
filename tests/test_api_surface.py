"""Unit tests for the public-API surface oracle engine (:mod:`pyclawd.api`)."""

from __future__ import annotations

from pathlib import Path

from pyclawd.api import (
    diff_surface,
    extract_module,
    extract_surface,
    module_qualname,
    read_baseline,
    write_baseline,
)

SAMPLE = '''
"""A module."""

CONST = 1
typed: int = 2
_private_const = 3


def public_fn(a, b: int = 0) -> str:
    return ""


def _private_fn():
    pass


class Widget(Base):
    """A widget."""

    def __init__(self, name: str) -> None:
        self.name = name

    def render(self, *, indent: int = 0) -> str:
        return ""

    def _helper(self):
        pass
'''


def test_extract_module_public_surface() -> None:
    lines = set(extract_module(SAMPLE, "pkg.mod"))
    assert "pkg.mod:CONST" in lines
    assert "pkg.mod:typed: int" in lines
    assert "pkg.mod:public_fn(a, b: int=0) -> str" in lines
    assert "pkg.mod:Widget(Base)" in lines
    assert "pkg.mod:Widget.__init__(self, name: str) -> None" in lines
    assert "pkg.mod:Widget.render(self, *, indent: int=0) -> str" in lines
    # Private names and helpers are excluded.
    assert not any("_private" in ln for ln in lines)
    assert "pkg.mod:Widget._helper(self)" not in lines


def test_dunder_all_restricts_surface() -> None:
    src = '__all__ = ["kept"]\n\ndef kept():\n    pass\n\ndef dropped():\n    pass\n'
    lines = set(extract_module(src, "m"))
    assert lines == {"m:kept()"}


def test_module_qualname_uses_package_and_init() -> None:
    pkg = Path("/repo/src/mypkg")
    assert module_qualname(pkg / "sub" / "mod.py", pkg) == "mypkg.sub.mod"
    assert module_qualname(pkg / "__init__.py", pkg) == "mypkg"


def test_diff_surface_classifies_add_remove_change() -> None:
    baseline = [
        "m:f(a) -> int",
        "m:g(x)",
        "m:CONST",
    ]
    current = [
        "m:f(a, b) -> int",  # changed signature
        "m:CONST",  # unchanged
        "m:h()",  # added
    ]
    diff = diff_surface(current, baseline)
    assert diff.removed == ["m:g(x)"]
    assert diff.added == ["m:h()"]
    assert diff.changed == [("m:f(a) -> int", "m:f(a, b) -> int")]
    assert diff.is_breaking()
    assert not diff.is_empty()


def test_diff_surface_additions_only_not_breaking() -> None:
    diff = diff_surface(["m:a()", "m:b()"], ["m:a()"])
    assert diff.added == ["m:b()"]
    assert not diff.is_breaking()


def test_baseline_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "api.txt"
    surface = ["m:b()", "m:a()"]
    write_baseline(path, surface)
    # Written sorted, one per line.
    assert path.read_text() == "m:a()\nm:b()\n"
    assert read_baseline(path) == ["m:a()", "m:b()"]


def test_read_missing_baseline_is_empty(tmp_path: Path) -> None:
    assert read_baseline(tmp_path / "nope.txt") == []


def test_extract_surface_walks_package(tmp_path: Path) -> None:
    pkg = tmp_path / "mypkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("def top():\n    pass\n")
    (pkg / "sub" / "mod.py").write_text("class C:\n    def m(self):\n        pass\n")
    (pkg / "sub" / "broken.py").write_text("def : this is not valid python\n")
    surface = extract_surface([pkg])
    assert "mypkg:top()" in surface
    assert "mypkg.sub.mod:C" in surface
    assert "mypkg.sub.mod:C.m(self)" in surface
    # A syntax-broken file is skipped, not fatal.
    assert surface == sorted(surface)
