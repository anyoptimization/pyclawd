"""Unit tests for the ``pyclawd skills`` command group (:mod:`pyclawd.commands.skills`).

These exercise the bundled-skill discovery and the copy/symlink installer against
a temporary directory — no network, no installed project required. They double as
the contract for what ``pyclawd skills install`` (and the ``pyclawd new``
auto-install) lands into a project's ``.claude/skills/``.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

from pathlib import Path

from pyclawd.commands.skills import (
    SKILL_PREFIX,
    bundled_skill_names,
    install_skills,
    skill_description,
)

#: The skills pyclawd ships with — the umbrella ``pyclawd`` plus the focused four.
EXPECTED = ["pyclawd", "pyclawd-docs", "pyclawd-doctor", "pyclawd-quality", "pyclawd-tests"]


def test_bundled_skill_names_lists_the_shipped_skills() -> None:
    assert bundled_skill_names() == EXPECTED
    # Every name is either the umbrella skill or a prefixed focused skill.
    assert all(name == "pyclawd" or name.startswith(SKILL_PREFIX) for name in EXPECTED)


def test_every_bundled_skill_has_a_description() -> None:
    for name in bundled_skill_names():
        desc = skill_description(name)
        assert desc, f"{name} has an empty frontmatter description"
        # The description should mention the tool it wraps.
        assert "pyclawd" in desc.lower()


def test_install_copies_each_skill_with_its_skill_md(tmp_path: Path) -> None:
    target = tmp_path / ".claude" / "skills"
    installed, skipped = install_skills(target)

    assert sorted(installed) == EXPECTED
    assert skipped == []
    for name in EXPECTED:
        assert (target / name / "SKILL.md").is_file()
    # A real copy, not a symlink, by default.
    assert not (target / EXPECTED[0]).is_symlink()


def test_install_skips_existing_unless_force(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)

    # A second run skips everything (already present) and changes nothing.
    installed, skipped = install_skills(target)
    assert installed == []
    assert sorted(skipped) == EXPECTED

    # Mark one skill, then force-reinstall: the marker is gone (dir replaced).
    marker = target / EXPECTED[0] / "MARKER"
    marker.write_text("stale", encoding="utf-8")
    installed, skipped = install_skills(target, force=True)
    assert sorted(installed) == EXPECTED
    assert skipped == []
    assert not marker.exists()


def test_install_symlink_mode_creates_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    installed, _ = install_skills(target, symlink=True)

    assert sorted(installed) == EXPECTED
    for name in EXPECTED:
        link = target / name
        assert link.is_symlink()
        # The symlink resolves to a real dir holding the SKILL.md.
        assert (link / "SKILL.md").is_file()


def test_install_creates_missing_target_dir(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "skills"
    assert not target.exists()
    install_skills(target)
    assert target.is_dir()
    assert (target / EXPECTED[0] / "SKILL.md").is_file()
