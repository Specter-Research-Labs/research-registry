from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.local_results_library import build_library_entries


def test_build_library_entries_from_local_top_results(tmp_path: Path) -> None:
    run_dir = tmp_path / "crystal" / "run-medium"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "init": {
                    "seed": 50015,
                    "patches": [{"center": [64, 64], "size": 40}],
                    "a_uniform": {"low": 0, "high": 1},
                    "p_uniform": None,
                    "state_patch": None,
                    "p_state_patch": None,
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "search.json").write_text(
        json.dumps({"top_k": 32, "collection": {"enabled": True}}),
        encoding="utf-8",
    )
    (run_dir / "top.json").write_text(
        json.dumps(
            [
                {
                    "init_seed": 50021,
                    "initial_condition_family": "initfam:v2:single_patch:test",
                    "descriptor_bundle": {
                        "genotype": {"hash12": "abc123"},
                        "terminal": {"fingerprintHash12": "fp123"},
                    },
                    "metrics": {"mass_mean": 1.0},
                    "params": {
                        "r": [0.1],
                        "b": [[0.2, 0.3, 0.4]],
                        "w": [[0.5, 0.6, 0.7]],
                        "a": [[0.8, 0.9, 1.0]],
                        "m": [0.11],
                        "s": [0.12],
                        "h": [0.13],
                        "R": 8.0,
                    },
                    "score": 0,
                    "score_weights": {},
                    "sweep": {},
                }
            ]
        ),
        encoding="utf-8",
    )

    entries = build_library_entries(
        run_dir=run_dir,
        run_id="crystal-targeted-imgep-medium-20260323",
        owner_id="imgep-hotspot",
        source_mode="local-imgep-hotspot",
        source_algorithm="imgep",
        limit=None,
    )

    assert len(entries) == 1
    entry = entries[0]
    assert entry["run_id"] == "crystal-targeted-imgep-medium-20260323"
    assert entry["source_mode"] == "local-imgep-hotspot"
    assert entry["runtime_family"] == "flow_lenia"
    assert entry["runtime_capabilities"] == [
        "archive",
        "topology",
        "warehouse_ingest",
    ]
    creature = entry["creature"]
    assert creature["ownerId"] == "imgep-hotspot"
    assert creature["phenotype"]["seed"] == 50021
    assert creature["phenotype"]["patches"] == [{"center": [64, 64], "size": 40}]
    assert creature["genotype"]["R"] == 8.0
    assert entry["research_metadata"]["morphospace_ready"] is True
    manifest = entry["specimen_manifest"]
    assert manifest["runtimeFamily"] == "flow_lenia"
    assert manifest["runtimeCapabilities"] == [
        "archive",
        "topology",
        "warehouse_ingest",
    ]
    assert manifest["snapshots"]["initialCondition"]["seed"] == 50021
    assert manifest["snapshots"]["genotype"]["R"] == 8.0
