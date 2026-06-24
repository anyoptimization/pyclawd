"""Unit tests for the ``pyclawd changelog`` command (:mod:`pyclawd.commands.changelog`).

Exercise the section parser and the ``--since`` filtering against an in-memory
changelog (no packaged file required), plus the command's defaulting to the loaded
project's ``pyclawd_version``.

Run them (from the repo root) with::

    python -m pytest tests -c tests/pytest.ini
"""

from __future__ import annotations

import pytest
import typer

from pyclawd.commands import changelog as cl

_SAMPLE = """\
# Changelog

Preamble that should be ignored.

## [Unreleased]

### Added
- a brand new thing

## [0.2.0] - 2026-06-01

### Changed
- renamed a config field

## [0.1.0] - 2026-05-01

### Added
- the first release
"""


def test_version_tuple_parses_numeric_and_rejects_words():
    assert cl._version_tuple("0.2.0") == (0, 2, 0)
    assert cl._version_tuple("1.10.3") == (1, 10, 3)
    assert cl._version_tuple("Unreleased") is None


def test_sections_splits_on_headers_and_drops_preamble():
    sections = cl._sections(_SAMPLE)
    tokens = [tok for tok, _ in sections]
    assert tokens == ["Unreleased", "0.2.0", "0.1.0"]
    # Each body starts with its own header line.
    assert sections[1][1].startswith("## [0.2.0]")
    assert "renamed a config field" in sections[1][1]


def test_newer_sections_since_release_excludes_equal_and_older():
    newer = cl._newer_sections(_SAMPLE, "0.1.0")
    tokens = [tok for tok, _ in newer]
    # Unreleased (always newest) and 0.2.0 are newer than 0.1.0; 0.1.0 itself is not.
    assert tokens == ["Unreleased", "0.2.0"]


def test_newer_sections_when_current_returns_only_unreleased():
    newer = cl._newer_sections(_SAMPLE, "0.2.0")
    assert [tok for tok, _ in newer] == ["Unreleased"]


def test_changelog_missing_file_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cl, "_changelog_text", lambda: None)
    with pytest.raises(typer.Exit) as exc:
        cl.changelog(since=None, full=False)
    assert exc.value.exit_code == 2
    assert "no CHANGELOG" in capsys.readouterr().err


def test_changelog_full_prints_everything(monkeypatch, capsys):
    monkeypatch.setattr(cl, "_changelog_text", lambda: _SAMPLE)
    with pytest.raises(typer.Exit) as exc:
        cl.changelog(since=None, full=True)
    assert exc.value.exit_code == 0
    out = capsys.readouterr().out
    assert "0.1.0" in out and "Unreleased" in out


def test_changelog_since_filters(monkeypatch, capsys):
    monkeypatch.setattr(cl, "_changelog_text", lambda: _SAMPLE)
    with pytest.raises(typer.Exit) as exc:
        cl.changelog(since="0.1.0", full=False)
    assert exc.value.exit_code == 0
    out = capsys.readouterr().out
    assert "0.2.0" in out
    assert "the first release" not in out  # 0.1.0 body excluded


def test_changelog_defaults_to_config_version(monkeypatch, capsys):
    monkeypatch.setattr(cl, "_changelog_text", lambda: _SAMPLE)

    class _Proj:
        pyclawd_version = "0.2.0"

    monkeypatch.setattr(cl, "load_project", lambda: _Proj())
    with pytest.raises(typer.Exit) as exc:
        cl.changelog(since=None, full=False)
    assert exc.value.exit_code == 0
    out = capsys.readouterr().out
    assert "since 0.2.0" in out  # used the config's pyclawd_version
