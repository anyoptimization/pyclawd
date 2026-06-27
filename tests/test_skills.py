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

from typer.testing import CliRunner

from pyclawd.commands.skills import (
    SKILL_PREFIX,
    bundled_skill_names,
    drifted_installed_skills,
    install_skills,
    orphaned_installed_skills,
    prune_installed_skills,
    skill_description,
)

#: The skills pyclawd ships with — the umbrella ``pyclawd`` router plus four focused
#: standalone skills. Kept sorted (``bundled_skill_names`` returns sorted order).
EXPECTED = [
    "pyclawd",
    "pyclawd-adopt",
    "pyclawd-doctor",
    "pyclawd-golden",
    "pyclawd-upgrade",
]


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
    installed, refreshed, skipped = install_skills(target)

    assert sorted(installed) == EXPECTED
    assert refreshed == []
    assert skipped == []
    for name in EXPECTED:
        assert (target / name / "SKILL.md").is_file()
    # A real copy, not a symlink, by default.
    assert not (target / EXPECTED[0]).is_symlink()


def test_install_skips_identical_existing(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)

    # A second run with no changes skips everything (already current).
    installed, refreshed, skipped = install_skills(target)
    assert installed == []
    assert refreshed == []
    assert sorted(skipped) == EXPECTED


def test_install_auto_refreshes_drifted_skill(tmp_path: Path) -> None:
    """A drifted installed skill is re-copied without --force (the upgrade path)."""
    target = tmp_path / "skills"
    install_skills(target)

    # Simulate an older install whose content has since changed in the package.
    drifted_md = target / EXPECTED[0] / "SKILL.md"
    drifted_md.write_text("stale content from an older pyclawd\n", encoding="utf-8")

    installed, refreshed, skipped = install_skills(target)
    assert installed == []
    assert refreshed == [EXPECTED[0]]  # only the drifted one is refreshed
    assert sorted(skipped) == sorted(EXPECTED[1:])
    # The drifted file was restored from the bundled source.
    assert "stale content" not in drifted_md.read_text(encoding="utf-8")


def test_force_refreshes_even_identical(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    marker = target / EXPECTED[0] / "MARKER"
    marker.write_text("x", encoding="utf-8")  # extra file → also counts as drift
    installed, refreshed, skipped = install_skills(target, force=True)
    assert installed == []
    assert sorted(refreshed) == EXPECTED  # force re-copies all existing
    assert skipped == []
    assert not marker.exists()


def test_drifted_installed_skills_detects_and_clears(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    assert drifted_installed_skills(target) == []  # fresh install → no drift

    (target / EXPECTED[0] / "SKILL.md").write_text("old\n", encoding="utf-8")
    assert drifted_installed_skills(target) == [EXPECTED[0]]

    install_skills(target)  # auto-refresh
    assert drifted_installed_skills(target) == []


def test_install_symlink_mode_creates_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    installed, _refreshed, _skipped = install_skills(target, symlink=True)

    assert sorted(installed) == EXPECTED
    for name in EXPECTED:
        link = target / name
        assert link.is_symlink()
        # The symlink resolves to a real dir holding the SKILL.md.
        assert (link / "SKILL.md").is_file()
    # A symlink always tracks the source, so it never registers as drifted.
    assert drifted_installed_skills(target) == []


def test_install_creates_missing_target_dir(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "skills"
    assert not target.exists()
    install_skills(target)
    assert target.is_dir()
    assert (target / EXPECTED[0] / "SKILL.md").is_file()


def _make_skill_dir(target: Path, name: str) -> Path:
    """Create a minimal skill directory ``<target>/<name>/SKILL.md`` and return it."""
    d = target / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")
    return d


def test_orphaned_installed_skills_detects_only_bundled_orphans(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)  # the current bundle
    # An orphan: a pyclawd-* skill no longer in the bundle.
    _make_skill_dir(target, "pyclawd-bogus")
    # A non-pyclawd skill that must never be touched.
    _make_skill_dir(target, "some-other-skill")

    orphans = orphaned_installed_skills(target)
    assert orphans == ["pyclawd-bogus"]
    # Current bundled names are not orphans, and the user's own skill is excluded.
    for name in EXPECTED:
        assert name not in orphans
    assert "some-other-skill" not in orphans


def test_orphaned_installed_skills_ignores_dirs_without_skill_md(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    (target / "pyclawd-nomd").mkdir()  # pyclawd-named but not actually a skill
    assert orphaned_installed_skills(target) == []


def test_orphaned_installed_skills_missing_target(tmp_path: Path) -> None:
    assert orphaned_installed_skills(tmp_path / "does-not-exist") == []


def test_prune_removes_only_orphans(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    install_skills(target)
    _make_skill_dir(target, "pyclawd-bogus")
    other = _make_skill_dir(target, "some-other-skill")

    removed = prune_installed_skills(target)
    assert removed == ["pyclawd-bogus"]
    assert not (target / "pyclawd-bogus").exists()
    # Bundled skills and the non-pyclawd skill survive.
    for name in EXPECTED:
        assert (target / name / "SKILL.md").is_file()
    assert (other / "SKILL.md").is_file()
    # A second prune is a no-op.
    assert prune_installed_skills(target) == []


def test_prune_removes_symlinked_orphan(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    target.mkdir()
    real = _make_skill_dir(tmp_path / "real", "pyclawd-bogus")
    link = target / "pyclawd-bogus"
    link.symlink_to(real, target_is_directory=True)

    removed = prune_installed_skills(target)
    assert removed == ["pyclawd-bogus"]
    assert not link.exists() and not link.is_symlink()
    # The symlink target itself is untouched (only the link was removed).
    assert (real / "SKILL.md").is_file()


def test_cli_prune_dry_run_lists_without_deleting(tmp_path: Path) -> None:
    from pyclawd.commands.skills import register

    target = tmp_path / "skills"
    install_skills(target)
    _make_skill_dir(target, "pyclawd-bogus")

    import typer

    app = typer.Typer()
    register(app)
    result = CliRunner().invoke(app, ["skills", "prune", "--target", str(target), "--dry-run"])
    assert result.exit_code == 0
    assert "pyclawd-bogus" in result.stdout
    # Dry run removes nothing.
    assert (target / "pyclawd-bogus" / "SKILL.md").is_file()
