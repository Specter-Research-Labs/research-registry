from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.attractor_packet import build_attractor_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(
    specimen_id: str,
    run_id: str,
    campaign_id: str,
    fingerprint: list[int],
) -> dict[str, object]:
    return {
        "specimenId": specimen_id,
        "runId": run_id,
        "campaignId": campaign_id,
        "genotype": {
            "canonicalizer": "demo",
            "vector": [0.0, 0.0],
        },
        "terminal": {
            "fingerprintResolution": 2,
            "fingerprintU8": fingerprint,
            "fingerprintHash12": specimen_id[-4:],
            "finalMass": 1.0,
            "finalOccupancy": 0.5,
            "finalGyration": 0.25,
            "angularSymmetry": {
                "dominantOrder": 2,
            },
        },
        "trajectory": {},
    }


def test_build_attractor_packet_lifts_h0_scales_into_components(tmp_path: Path) -> None:
    analysis_root = tmp_path / "analysis"
    rows_path = analysis_root / "rows.jsonl"
    _write_jsonl(
        rows_path,
        [
            _row("s0", "r0", "c0", [255, 0, 0, 0]),
            _row("s1", "r0", "c1", [250, 5, 0, 0]),
            _row("s2", "r1", "c2", [0, 0, 255, 0]),
            _row("s3", "r1", "c3", [0, 0, 250, 5]),
        ],
    )
    _write_json(
        analysis_root / "summary.json",
        {
            "spaces": {
                "phenotype": {
                    "ripser": [
                        {
                            "featureCount": 4,
                            "essentialCount": 1,
                            "topPersistence": [1.2, 0.1, 0.1],
                        }
                    ]
                }
            }
        },
    )
    _write_json(
        analysis_root / "diagrams.json",
        {
            "phenotype": [
                [
                    {"birth": 0.0, "death": 0.025, "persistence": 0.025},
                    {"birth": 0.0, "death": 0.025, "persistence": 0.025},
                    {"birth": 0.0, "death": 1.2, "persistence": 1.2},
                    {"birth": 0.0, "death": None, "persistence": None},
                ]
            ]
        },
    )
    _write_json(
        analysis_root / "analysis-manifest.json",
        {
            "rowsPath": str(rows_path),
            "summaryPath": "summary.json",
            "diagramsPath": "diagrams.json",
        },
    )

    packet = build_attractor_packet(
        analysis_manifest_path=analysis_root / "analysis-manifest.json",
        top_scales=2,
        top_components_per_scale=4,
    )

    assert packet["packetKind"] == "attractor_packet_v1"
    assert packet["specimenCount"] == 4
    assert packet["h0"]["selectedMergeScales"] == [1.2, 0.025]
    assert packet["scales"][0]["componentCount"] == 2
    component_sizes = sorted(
        component["specimenCount"] for component in packet["scales"][0]["components"]
    )
    assert component_sizes == [2, 2]
    assert packet["scales"][0]["components"][0]["representative"]["specimenId"] in {
        "s0",
        "s1",
        "s2",
        "s3",
    }
