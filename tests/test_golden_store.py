"""In-process disk round-trip tests for :class:`pyclawd.golden.GoldenStore`.

GoldenStore is the per-test-module baseline file (``key → entry``) on disk. It had
only subprocess-e2e coverage; these drive load/save/set/remove/keys directly in
``tmp_path``. The load-bearing case is the documented **merge** invariant: ``set()``
must merge a new key into the existing file, never wipe the keys recorded for other
tests in the same module (that is what makes ``golden update`` safe under a fleet of
agents). No subprocess, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from pyclawd.golden import GoldenStore, make_entry, module_baseline_path


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    """Opening a store whose file does not exist yields an empty store."""
    store = GoldenStore(tmp_path / "test_mod.json")
    assert store.is_empty()
    assert store.keys() == []
    assert store.get("anything") is None


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    """Entries survive a save → fresh-load cycle byte-for-byte."""
    path = tmp_path / "test_mod.json"
    store = GoldenStore(path)
    entry = make_entry(2.5)
    store.set("test_a", entry)
    store.save()

    reloaded = GoldenStore(path)
    assert reloaded.keys() == ["test_a"]
    assert reloaded.get("test_a") == entry
    assert reloaded.get("test_a")["value"] == 2.5


def test_set_merges_does_not_wipe_existing(tmp_path: Path) -> None:
    """The critical invariant: set() MERGES — writing B keeps A on disk.

    Simulates two separate `golden update` runs against the same module file:
    record A, persist, then a fresh store records B. Both must end up in the file.
    """
    path = tmp_path / "test_mod.json"

    first = GoldenStore(path)
    first.set("test_a", make_entry(1.0))
    first.save()

    # A *new* store re-loads the existing file, then records a second key.
    second = GoldenStore(path)
    second.set("test_b", make_entry(2.0))
    second.save()

    final = GoldenStore(path)
    assert sorted(final.keys()) == ["test_a", "test_b"]
    assert final.get("test_a")["value"] == 1.0
    assert final.get("test_b")["value"] == 2.0


def test_set_same_key_overwrites_in_place(tmp_path: Path) -> None:
    """Re-blessing the same key replaces its entry but leaves siblings intact."""
    path = tmp_path / "test_mod.json"
    store = GoldenStore(path)
    store.set("test_a", make_entry(1.0))
    store.set("test_b", make_entry(2.0))
    store.save()

    again = GoldenStore(path)
    again.set("test_a", make_entry(9.0))  # re-bless test_a only
    again.save()

    final = GoldenStore(path)
    assert final.get("test_a")["value"] == 9.0
    assert final.get("test_b")["value"] == 2.0  # sibling untouched


def test_remove_drops_only_named_key(tmp_path: Path) -> None:
    """remove() drops the given key and returns True; others remain."""
    path = tmp_path / "test_mod.json"
    store = GoldenStore(path)
    store.set("test_a", make_entry(1.0))
    store.set("test_b", make_entry(2.0))

    assert store.remove("test_a") is True
    assert store.keys() == ["test_b"]
    # Removing an absent key is a no-op that returns False.
    assert store.remove("test_a") is False
    assert store.remove("never") is False


def test_remove_persists_after_save(tmp_path: Path) -> None:
    """A removal is durable once saved."""
    path = tmp_path / "test_mod.json"
    store = GoldenStore(path)
    store.set("test_a", make_entry(1.0))
    store.set("test_b", make_entry(2.0))
    store.save()
    store.remove("test_b")
    store.save()

    assert GoldenStore(path).keys() == ["test_a"]


def test_save_writes_sorted_diff_friendly_json(tmp_path: Path) -> None:
    """Saved JSON is indented, key-sorted, and newline-terminated for clean diffs."""
    path = tmp_path / "test_mod.json"
    store = GoldenStore(path)
    store.set("test_b", make_entry(2.0))
    store.set("test_a", make_entry(1.0))
    store.save()

    text = path.read_text()
    assert text.endswith("\n")
    assert text.index('"test_a"') < text.index('"test_b"')  # keys sorted
    # Round-trips as valid JSON with both entries.
    assert set(json.loads(text)) == {"test_a", "test_b"}


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    """save() creates a missing baseline directory on first write."""
    path = tmp_path / "nested" / "deeper" / "test_mod.json"
    store = GoldenStore(path)
    store.set("test_a", make_entry(1.0))
    store.save()
    assert path.is_file()


def test_one_file_per_module_naming(tmp_path: Path) -> None:
    """module_baseline_path names one ``<stem>.json`` per module under the dir."""
    p = module_baseline_path(tmp_path, "test_minimize")
    assert p == tmp_path / "test_minimize.json"
    # Distinct modules never share a file.
    assert module_baseline_path(tmp_path, "test_a") != module_baseline_path(tmp_path, "test_b")
