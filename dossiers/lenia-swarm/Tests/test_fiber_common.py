from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.fiber._common import load_specimen
from lenia_swarm_analysis.fiber.experiments.continuation_sweep import (
    load_generator_specimen,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_fiber_readers_prefer_manifest_source_export_dir(tmp_path: Path) -> None:
    replay_root = tmp_path / "replay"
    campaign_dir = replay_root / "run-a" / "campaigns" / "campaign-a"
    manifest_export_dir = tmp_path / "exports" / "manifest"
    stale_export_dir = tmp_path / "exports" / "stale"

    _write_json(manifest_export_dir / "meta.json", {"source": "manifest"})
    _write_json(manifest_export_dir / "payload.json", {"elite": {"cell": 17}})
    _write_json(stale_export_dir / "meta.json", {"source": "stale"})
    _write_json(stale_export_dir / "payload.json", {"elite": {"cell": 99}})

    _write_jsonl(
        campaign_dir / "library" / "index.jsonl",
        [
            {
                "run_id": "run-a",
                "campaign_id": "campaign-a",
                "research_metadata": {
                    "source_export_dir": str(stale_export_dir),
                },
                "specimen_manifest": {
                    "researchMetadata": {
                        "source_export_dir": str(manifest_export_dir),
                    },
                    "replay": {
                        "exportDir": str(manifest_export_dir),
                    },
                },
            }
        ],
    )
    _write_jsonl(
        campaign_dir / "results.jsonl",
        [
            {
                "descriptor_bundle": {
                    "terminal": {
                        "fingerprintU8": [0, 1, 0, 0] * 4,
                        "angularSymmetry": {
                            "dominantOrder": 2,
                            "dominantAmplitude": 0.75,
                        },
                    }
                }
            }
        ],
    )

    specimen = load_specimen(
        {
            "specimenId": "specimen-a",
            "runId": "run-a",
            "campaignId": "campaign-a",
            "seed": 7,
        },
        replay_root,
    )
    generator = load_generator_specimen(
        "replay:run-a|campaign-a|specimen-a",
        replay_root,
    )

    assert specimen.source_export_dir == manifest_export_dir
    assert specimen.source_meta["source"] == "manifest"
    assert specimen.seed == 7
    assert generator.source_export_dir == manifest_export_dir
    assert generator.source_meta["source"] == "manifest"
    assert generator.seed == 17
