from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.imgep.hotspot_export import build_imgep_hotspot_export_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_imgep_hotspot_export_packet_materializes_strict_replay_bundles(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run-medium"
    _write_json(
        run_dir / "config.json",
        {
            "params": {
                "mode": "explicit",
                "seed": 0,
                "ranges": {"m": [0.0, 1.0]},
                "r": [0.1],
                "b": [[0.2]],
                "w": [[0.3]],
                "a": [[0.4]],
                "m": [0.5],
                "s": [0.6],
                "h": [0.7],
                "R": 5.0,
            },
            "init": {"seed": 50000, "patches": [{"center": [64, 64], "size": 40}]},
        },
    )
    _write_json(
        run_dir / "search.json",
        {"seed_start": 0, "seed_stride": 1, "init_seed_offset": 50000, "count": 1},
    )
    _write_json(
        run_dir / "top.json",
        [
            {
                "seed": 7,
                "init_seed": 50007,
                "filters_passed": True,
                "initial_condition_family": "initfam:test",
                "descriptor_bundle": {"terminal": {"isStable": False}},
                "params": {
                    "r": [0.15],
                    "b": [[0.21]],
                    "w": [[0.31]],
                    "a": [[0.41]],
                    "m": [0.51],
                    "s": [0.61],
                    "h": [0.71],
                    "R": 5.5,
                },
                "score": 0.0,
                "score_weights": {},
                "metrics": {"gyration": 123.0},
            }
        ],
    )
    report = tmp_path / "report.json"
    _write_json(
        report,
        {
            "selectedCandidates": [
                {
                    "candidateId": "specimen-mh-medium-01",
                    "controlGroup": "specimen-mh",
                    "specimen": "specimen",
                    "scale": "medium",
                    "sourceRunDir": str(run_dir),
                    "sourceConfigPath": str(run_dir / "config.json"),
                    "sourceSearchPath": str(run_dir / "search.json"),
                    "sourceIndex": 0,
                    "sourceSeed": 7,
                    "sourceInitSeed": 50007,
                }
            ]
        },
    )

    packet = build_imgep_hotspot_export_packet(
        report_path=report,
        output_root=tmp_path / "exports-out",
        owner_id="test-owner",
        run_id="test-run",
    )

    assert packet["packetKind"] == "imgep_hotspot_export_packet_v1"
    assert packet["exportCount"] == 1
    index_path = Path(packet["exportIndexPath"])
    lines = index_path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["bundleKind"] == "strict_replay_bundle_v1"
    bundle_dir = Path(record["exportDir"])
    assert (bundle_dir / "base.json").exists()
    assert (bundle_dir / "search.json").exists()
    meta = json.loads((bundle_dir / "meta.json").read_text())
    assert meta["creature"]["genotype"]["R"] == 5.5
    assert meta["creature"]["phenotype"]["seed"] == 50007
