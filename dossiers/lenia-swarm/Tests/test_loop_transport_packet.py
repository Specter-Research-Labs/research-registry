from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.loop import build_loop_transport_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_loop_transport_packet_compares_square_loop_to_controls(
    tmp_path: Path,
) -> None:
    batch_packet_path = tmp_path / "batch-packet.json"
    _write_json(
        batch_packet_path,
        {
            "runs": [
                {
                    "name": "crystal-square",
                    "bundle": "/tmp/crystal",
                    "pointCount": 5,
                    "endpointPhenotypeDistance": 0.02,
                    "endpointTransportedStateDistance": 0.5,
                    "tags": {"controlGroup": "crystal-mh", "kind": "square", "role": "loop"},
                },
                {
                    "name": "crystal-square-reverse",
                    "bundle": "/tmp/crystal",
                    "pointCount": 5,
                    "endpointPhenotypeDistance": 0.021,
                    "endpointTransportedStateDistance": 0.45,
                    "tags": {
                        "controlGroup": "crystal-mh",
                        "kind": "square-reverse",
                        "role": "loop",
                    },
                },
                {
                    "name": "crystal-m-outback",
                    "bundle": "/tmp/crystal",
                    "pointCount": 3,
                    "endpointPhenotypeDistance": 0.01,
                    "endpointTransportedStateDistance": 0.2,
                    "tags": {
                        "controlGroup": "crystal-mh",
                        "kind": "outback-m",
                        "role": "control",
                    },
                },
                {
                    "name": "crystal-h-outback",
                    "bundle": "/tmp/crystal",
                    "pointCount": 3,
                    "endpointPhenotypeDistance": 0.015,
                    "endpointTransportedStateDistance": 0.25,
                    "tags": {
                        "controlGroup": "crystal-mh",
                        "kind": "outback-h",
                        "role": "control",
                    },
                },
            ]
        },
    )

    packet = build_loop_transport_packet(batch_packet_path)

    assert packet["packetKind"] == "loop_transport_packet_v1"
    assert packet["groupCount"] == 1
    group = packet["groups"][0]
    assert group["controlGroup"] == "crystal-mh"
    assert group["topLoop"]["name"] == "crystal-square"
    assert [row["name"] for row in group["loops"]] == [
        "crystal-square",
        "crystal-square-reverse",
    ]
    assert group["bestControl"]["name"] == "crystal-h-outback"
    assert group["loopMinusBestControlStateClosure"] == 0.25
