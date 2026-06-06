from __future__ import annotations

import json
from pathlib import Path

import corpus.artifacts as artifacts_mod
import corpus.pipeline.build as build_mod


def _jsonl(row: dict) -> str:
    return json.dumps(row, sort_keys=True) + "\n"


def test_build_lean_subset_copies_requested_source_items(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    monkeypatch.setattr(artifacts_mod, "resolve_corpora_root", lambda: artifacts_root)

    source_dir = artifacts_root / "lean" / "source-corpus" / "source-build"
    source_dir.mkdir(parents=True)
    (artifacts_root / "lean" / "source-corpus" / "CURRENT").write_text(
        "source-build",
        encoding="utf-8",
    )
    (source_dir / "items.jsonl").write_text(
        _jsonl(
            {
                "item_id": "alpha",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            }
        )
        + _jsonl(
            {
                "item_id": "beta",
                "payload": {"statement": "theorem {name} : True := by\n  sorry"},
            }
        ),
        encoding="utf-8",
    )
    (source_dir / "manifest.json").write_text(
        json.dumps(
            {
                "backend": "lean",
                "corpus_id": "source-corpus",
                "build_id": "source-build",
                "provenance": [{"kind": "unit"}],
                "build_config": {},
                "counts": {"items_total": 2},
                "items_file": "items.jsonl",
                "items_sha256": "unit",
                "item_id_scheme": "unit",
            }
        ),
        encoding="utf-8",
    )
    requested = tmp_path / "requested.txt"
    requested.write_text("beta\n", encoding="utf-8")

    built = build_mod.build_lean_subset(
        corpus_id="subset-corpus",
        source_ref="lean:source-corpus",
        theorems_path=requested,
    )

    manifest = json.loads((built.build_dir / "manifest.json").read_text(encoding="utf-8"))
    items = (built.build_dir / "items.jsonl").read_text(encoding="utf-8").splitlines()
    assert manifest["build_config"]["requested_count"] == 1
    assert manifest["build_config"]["source_build_id"] == "source-build"
    assert len(items) == 1
    assert json.loads(items[0])["item_id"] == "beta"


def test_build_lean_subset_can_use_named_source_corpus(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)
    requested = tmp_path / "requested.txt"
    requested.write_text("forall_trivial\n", encoding="utf-8")

    built = build_mod.build_lean_subset(
        corpus_id="named-subset",
        source_ref="research",
        theorems_path=requested,
    )

    manifest = json.loads((built.build_dir / "manifest.json").read_text(encoding="utf-8"))
    items = (built.build_dir / "items.jsonl").read_text(encoding="utf-8").splitlines()
    assert manifest["build_config"]["source_ref"] == "research"
    assert len(items) == 1
    assert json.loads(items[0])["item_id"] == "forall_trivial"
