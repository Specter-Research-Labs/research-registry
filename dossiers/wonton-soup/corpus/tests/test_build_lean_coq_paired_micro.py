from __future__ import annotations

import json
from pathlib import Path

import corpus.pipeline.build as build_mod


def test_build_lean_coq_paired_micro_uses_typed_benchmark_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setattr(build_mod, "resolve_corpus_artifact_root", lambda: artifacts_root)

    pairs_path = tmp_path / "pairs.json"
    pairs_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "benchmark_id": "paired-micro-test",
                "description": "test",
                "gate": {"min_recall_at_10": 0.3},
                "pairs": [
                    {
                        "pair_id": "pair_one",
                        "lean_item_id": "coq_pair_one",
                        "lean_display_name": "pair_one",
                        "lean_statement": "theorem {name} : True := by\n  sorry",
                        "coq_theorem": "pair_one",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    built = build_mod.build_lean_coq_paired_micro(
        corpus_id="coq-paired-micro-test",
        pairs_path=pairs_path,
    )

    manifest = json.loads((built.build_dir / "manifest.json").read_text(encoding="utf-8"))
    items = (built.build_dir / "items.jsonl").read_text(encoding="utf-8").splitlines()

    assert manifest["build_config"]["benchmark_id"] == "paired-micro-test"
    assert manifest["build_config"]["pairs_total"] == 1
    assert len(items) == 1
    assert "coq_pair_one" in items[0]
