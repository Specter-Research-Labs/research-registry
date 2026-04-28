from __future__ import annotations

import json
from pathlib import Path

from corpus.artifacts import list_corpora


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_list_corpora_reports_current_build_and_derived(tmp_path: Path) -> None:
    root = tmp_path / "corpora"
    build_id = "b" * 64
    derived_id = "d" * 64

    corpus_root = root / "lean" / "mathlib4"
    corpus_root.mkdir(parents=True, exist_ok=True)
    (corpus_root / "CURRENT").write_text(build_id + "\n", encoding="utf-8")

    build_dir = corpus_root / build_id
    build_dir.mkdir(parents=True)
    _write_json(
        build_dir / "manifest.json",
        {
            "backend": "lean",
            "corpus_id": "mathlib4",
            "build_id": build_id,
            "counts": {"items_total": 123},
        },
    )

    derived_root = build_dir / "derived" / "valid"
    derived_root.mkdir(parents=True, exist_ok=True)
    (derived_root / "CURRENT").write_text(derived_id + "\n", encoding="utf-8")
    (derived_root / derived_id).mkdir(parents=True)

    entries = list_corpora(root)
    assert [(e.backend, e.corpus_id) for e in entries] == [("lean", "mathlib4")]
    entry = entries[0]
    assert entry.current_build_id == build_id
    assert entry.items_total == 123
    assert entry.derived_current == {"valid": derived_id}
    assert entry.problems == []


def test_list_corpora_handles_missing_current(tmp_path: Path) -> None:
    root = tmp_path / "corpora"
    build_id = "b" * 64
    corpus_root = root / "lean" / "mathlib4"
    build_dir = corpus_root / build_id
    build_dir.mkdir(parents=True)
    _write_json(build_dir / "manifest.json", {"counts": {"items_total": 1}})

    entries = list_corpora(root)
    assert len(entries) == 1
    assert entries[0].current_build_id is None
    assert entries[0].build_ids == [build_id]
