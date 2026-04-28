from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.imgep.hotspot_report import build_imgep_hotspot_report


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_imgep_hotspot_report_prefers_medium_when_it_has_retained_diversity(
    tmp_path: Path,
) -> None:
    batch = tmp_path / "batch.json"
    seed = tmp_path / "seed.json"
    _write_json(
        seed,
        [
            {
                "embedding": [100.0, 0.001, 0.5, 0.8],
                "metrics": {},
                "params": {},
                "score": 0.0,
                "seed": 17,
            }
        ],
    )
    small = tmp_path / "run-small"
    medium = tmp_path / "run-medium"
    _write_json(small / "summary.json", {"iterations": 4, "top_count": 1})
    _write_jsonl(
        small / "history.jsonl",
        [
            {"embedding": [101.0, 0.0011, 0.51, 0.81], "metrics": {}, "params": {}, "score": 0.0},
            {"embedding": [102.0, 0.0012, 0.52, 0.82], "metrics": {}, "params": {}, "score": 0.0},
        ],
    )
    _write_json(
        small / "top.json",
        [
            {
                "seed": 0,
                "init_seed": 50000,
                "filters_passed": True,
                "initial_condition_family": "initfam:test",
                "descriptor_bundle": {},
                "params": {
                    "r": [0.1],
                    "b": [[0.2]],
                    "w": [[0.3]],
                    "a": [[0.4]],
                    "m": [0.5],
                    "s": [0.6],
                    "h": [0.7],
                    "R": 5.0,
                },
                "score": 0.0,
                "score_weights": {},
                "metrics": {
                    "gyration": 101.0,
                    "center_velocity": 0.0011,
                    "moment_anisotropy": 0.51,
                    "largest_component_anisotropy": 0.81,
                },
            }
        ],
    )
    _write_json(medium / "summary.json", {"iterations": 4, "top_count": 3})
    _write_jsonl(
        medium / "history.jsonl",
        [
            {"embedding": [120.0, 0.0011, 0.55, 0.84], "metrics": {}, "params": {}, "score": 0.0},
            {"embedding": [140.0, 0.0012, 0.60, 0.88], "metrics": {}, "params": {}, "score": 0.0},
        ],
    )
    _write_json(
        medium / "top.json",
        [
            {
                "seed": 1,
                "init_seed": 50001,
                "filters_passed": True,
                "initial_condition_family": "initfam:test",
                "descriptor_bundle": {},
                "params": {
                    "r": [0.1],
                    "b": [[0.2]],
                    "w": [[0.3]],
                    "a": [[0.4]],
                    "m": [0.5],
                    "s": [0.6],
                    "h": [0.7],
                    "R": 5.0,
                },
                "score": 0.0,
                "score_weights": {},
                "metrics": {
                    "gyration": 120.0,
                    "center_velocity": 0.0011,
                    "moment_anisotropy": 0.55,
                    "largest_component_anisotropy": 0.84,
                },
            },
            {
                "seed": 2,
                "init_seed": 50002,
                "filters_passed": True,
                "initial_condition_family": "initfam:test",
                "descriptor_bundle": {},
                "params": {
                    "r": [0.11],
                    "b": [[0.2]],
                    "w": [[0.3]],
                    "a": [[0.4]],
                    "m": [0.5],
                    "s": [0.6],
                    "h": [0.7],
                    "R": 5.0,
                },
                "score": 0.0,
                "score_weights": {},
                "metrics": {
                    "gyration": 140.0,
                    "center_velocity": 0.0012,
                    "moment_anisotropy": 0.60,
                    "largest_component_anisotropy": 0.88,
                },
            },
            {
                "seed": 3,
                "init_seed": 50003,
                "filters_passed": True,
                "initial_condition_family": "initfam:test",
                "descriptor_bundle": {},
                "params": {
                    "r": [0.12],
                    "b": [[0.2]],
                    "w": [[0.3]],
                    "a": [[0.4]],
                    "m": [0.5],
                    "s": [0.6],
                    "h": [0.7],
                    "R": 5.0,
                },
                "score": 0.0,
                "score_weights": {},
                "metrics": {
                    "gyration": 100.5,
                    "center_velocity": 0.00105,
                    "moment_anisotropy": 0.50,
                    "largest_component_anisotropy": 0.80,
                },
            },
        ],
    )
    _write_json(
        batch,
        {
            "features": [
                "gyration",
                "center_velocity",
                "moment_anisotropy",
                "largest_component_anisotropy",
            ],
            "runs": [
                {
                    "name": "specimen-targeted-imgep-small",
                    "specimen": "specimen",
                    "controlGroup": "specimen-mh",
                    "output": str(small),
                    "config": str(tmp_path / "config.json"),
                    "search": str(tmp_path / "search.json"),
                    "historySeed": str(seed),
                    "recommendedBecause": {
                        "bestScaleByStateClosure": {"scale": "small"},
                        "bestScaleByRatio": {"scale": "medium"},
                    },
                },
                {
                    "name": "specimen-targeted-imgep-medium",
                    "specimen": "specimen",
                    "controlGroup": "specimen-mh",
                    "output": str(medium),
                    "config": str(tmp_path / "config.json"),
                    "search": str(tmp_path / "search.json"),
                    "historySeed": str(seed),
                    "recommendedBecause": {
                        "bestScaleByStateClosure": {"scale": "small"},
                        "bestScaleByRatio": {"scale": "medium"},
                    },
                },
            ],
        },
    )

    report = build_imgep_hotspot_report(batch_packet_path=batch, replay_limit=2)

    assert report["packetKind"] == "imgep_hotspot_report_v1"
    assert report["groupCount"] == 1
    row = report["groups"][0]
    assert row["recommendedReplayScale"] == "medium"
    assert row["followupScales"] == ["small"]
    assert len(row["selectedCandidateIds"]) == 2
    assert report["selectedCandidateCount"] == 2
