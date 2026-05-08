from __future__ import annotations

import json
from pathlib import Path

import pytest

from lenia_tribe_overlay.manifest import load_manifest


def _touch(path: Path) -> None:
    path.write_bytes(b"")


def test_load_manifest_resolves_paths_relative_to_file(tmp_path: Path) -> None:
    (tmp_path / "videos").mkdir()
    a = tmp_path / "videos" / "a.mp4"
    b = tmp_path / "videos" / "b.mp4"
    _touch(a)
    _touch(b)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {"name": "a", "mp4": "videos/a.mp4", "specimen_id": "spec-1"},
                {"name": "b", "mp4": "videos/b.mp4", "notes": "no warehouse linkage"},
            ]
        )
    )
    entries = load_manifest(manifest)
    assert [e.name for e in entries] == ["a", "b"]
    assert entries[0].mp4_path == a.resolve()
    assert entries[0].specimen_id == "spec-1"
    assert entries[0].notes is None
    assert entries[1].specimen_id is None
    assert entries[1].notes == "no warehouse linkage"


def test_load_manifest_rejects_missing_video(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"name": "ghost", "mp4": "ghost.mp4"}]))
    with pytest.raises(FileNotFoundError, match="ghost.mp4"):
        load_manifest(manifest)


def test_load_manifest_rejects_duplicate_name(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    _touch(a)
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            [
                {"name": "x", "mp4": "a.mp4"},
                {"name": "x", "mp4": "a.mp4"},
            ]
        )
    )
    with pytest.raises(ValueError, match="duplicate name"):
        load_manifest(manifest)


def test_load_manifest_rejects_empty_array(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text("[]")
    with pytest.raises(ValueError, match="empty"):
        load_manifest(manifest)


def test_load_manifest_rejects_non_array(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"name": "x", "mp4": "a.mp4"}))
    with pytest.raises(ValueError, match="JSON array"):
        load_manifest(manifest)
