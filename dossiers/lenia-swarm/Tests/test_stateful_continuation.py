from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from lenia_swarm_analysis.fiber.continuation import (
    build_open_path_loop_spec,
    summarize_stateful_continuation,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _encoded_fingerprint(values: list[int]) -> str:
    return base64.b64encode(bytes(values)).decode("ascii")


def _encoded_state(values: list[float]) -> dict[str, object]:
    data = np.asarray(values, dtype="<f4").tobytes()
    return {
        "center": [0, 0],
        "channels": 1,
        "data": base64.b64encode(data).decode("ascii"),
        "encoding": "f32le",
        "height": 1,
        "width": len(values),
    }


def test_build_open_path_loop_spec_from_values() -> None:
    spec = build_open_path_loop_spec(
        coordinate="m.0",
        values=[0.1, 0.2, 0.3],
        name="demo",
    )

    assert spec["closed"] is False
    assert spec["coordinates"] == ["m.0"]
    assert spec["vertices"] == [[0.1], [0.2], [0.3]]
    assert spec["samples_per_segment"] == 1


def test_summarize_stateful_continuation_reads_holonomy_outputs(tmp_path: Path) -> None:
    root = tmp_path / "holonomy"
    campaign1 = root / "campaigns" / "0001"
    campaign2 = root / "campaigns" / "0002"
    _write_json(
        root / "summary.json",
        {
            "campaign_count": 2,
        },
    )
    _write_json(
        root / "holonomy-manifest.json",
        {
            "run_id": "stateful-demo",
            "bundle_path": "/tmp/bundle",
            "loop_path": "/tmp/loop.json",
            "coordinate_paths": ["m.0"],
            "config_topology_hash": "abc123",
            "summary_path": str((root / "summary.json").resolve()),
            "step_manifest_paths": [
                str((campaign1 / "holonomy-step.json").resolve()),
                str((campaign2 / "holonomy-step.json").resolve()),
            ],
        },
    )
    _write_json(
        campaign1 / "holonomy-step.json",
        {
            "sequence_index": 0,
            "segment_index": 0,
            "segment_t": 0.0,
            "coordinate_values": {"m.0": 0.1},
            "results_path": str((campaign1 / "results.jsonl").resolve()),
        },
    )
    _write_json(
        campaign2 / "holonomy-step.json",
        {
            "sequence_index": 1,
            "segment_index": 0,
            "segment_t": 1.0,
            "coordinate_values": {"m.0": 0.2},
            "results_path": str((campaign2 / "results.jsonl").resolve()),
        },
    )
    campaign1_result = {
        "descriptor_bundle": {
            "terminal": {
                "fingerprintU8": _encoded_fingerprint([0, 255]),
            }
        }
    }
    campaign2_result = {
        "descriptor_bundle": {
            "terminal": {
                "fingerprintU8": _encoded_fingerprint([255, 255]),
            }
        }
    }
    (campaign1 / "results.jsonl").write_text(
        json.dumps(campaign1_result) + "\n",
        encoding="utf-8",
    )
    (campaign2 / "results.jsonl").write_text(
        json.dumps(campaign2_result) + "\n",
        encoding="utf-8",
    )
    _write_json(campaign1 / "terminal-state.json", _encoded_state([0.0, 0.0]))
    _write_json(campaign2 / "terminal-state.json", _encoded_state([1.0, 0.0]))

    packet = summarize_stateful_continuation(root / "holonomy-manifest.json")

    assert packet["packetKind"] == "stateful_continuation_packet_v1"
    assert packet["pointCount"] == 2
    assert packet["coordinatePaths"] == ["m.0"]
    assert packet["rows"][1]["phenotypeStepDelta"] > 0.0
    assert packet["rows"][1]["transportedStateStepDelta"] > 0.0
