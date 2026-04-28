from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.validation_batch import (
    build_transport_validation_batch_spec,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_transport_validation_batch_spec_rehydrates_dense_validation_runs(
    tmp_path: Path,
) -> None:
    source_spec = tmp_path / "source-spec.json"
    source_batch = tmp_path / "source-batch.json"
    source_loop = tmp_path / "source-loop.json"
    winner_packet = tmp_path / "winner.json"
    bundle = tmp_path / "bundle"
    bundle.mkdir(parents=True)

    _write_json(
        source_spec,
        {
            "cliBinary": "/tmp/LeniaCLI",
        },
    )
    _write_json(
        source_batch,
        {
            "sourceSpec": str(source_spec),
            "runs": [
                {
                    "name": "crystal-forward",
                    "bundle": str(bundle),
                    "coordinate": None,
                    "values": None,
                    "loopSpec": {
                        "name": "crystal-forward",
                        "closed": True,
                        "coordinates": ["m.0", "h.0"],
                        "vertices": [
                            [1.0, 2.0],
                            [3.0, 2.0],
                            [3.0, 5.0],
                            [1.0, 5.0],
                            [1.0, 2.0],
                        ],
                    },
                    "tags": {
                        "specimen": "crystal-mixed",
                        "controlGroup": "crystal-mixed-medium-wide",
                        "kind": "square-forward-medium-wide",
                        "role": "loop",
                    },
                },
                {
                    "name": "crystal-reverse",
                    "bundle": str(bundle),
                    "coordinate": None,
                    "values": None,
                    "loopSpec": {
                        "name": "crystal-reverse",
                        "closed": True,
                        "coordinates": ["m.0", "h.0"],
                        "vertices": [
                            [1.0, 2.0],
                            [1.0, 5.0],
                            [3.0, 5.0],
                            [3.0, 2.0],
                            [1.0, 2.0],
                        ],
                    },
                    "tags": {
                        "specimen": "crystal-mixed",
                        "controlGroup": "crystal-mixed-medium-wide",
                        "kind": "square-reverse-medium-wide",
                        "role": "loop",
                    },
                },
                {
                    "name": "crystal-m-outback",
                    "bundle": str(bundle),
                    "coordinate": "m.0",
                    "values": [1.0, 3.0, 1.0],
                    "loopSpec": None,
                    "tags": {
                        "specimen": "crystal-mixed",
                        "controlGroup": "crystal-mixed-medium-wide",
                        "kind": "outback-m-medium-wide",
                        "role": "control",
                    },
                },
                {
                    "name": "crystal-h-outback",
                    "bundle": str(bundle),
                    "coordinate": "h.0",
                    "values": [2.0, 5.0, 2.0],
                    "loopSpec": None,
                    "tags": {
                        "specimen": "crystal-mixed",
                        "controlGroup": "crystal-mixed-medium-wide",
                        "kind": "outback-h-medium-wide",
                        "role": "control",
                    },
                },
            ],
        },
    )
    _write_json(
        source_loop,
        {
            "sourceBatchPacket": str(source_batch),
            "groups": [
                {
                    "controlGroup": "crystal-mixed-medium-wide",
                    "topLoop": {"name": "crystal-forward"},
                    "bestControl": {"name": "crystal-m-outback"},
                }
            ],
        },
    )
    _write_json(
        winner_packet,
        {
            "packetKind": "transport_winner_packet_v1",
            "sourcePackets": [
                {"label": "refine", "path": str(source_loop)},
            ],
            "groups": [
                {
                    "controlGroup": "crystal-mixed",
                    "winnerByCompositeScore": {
                        "packetLabel": "refine",
                        "controlGroup": "crystal-mixed-medium-wide",
                        "deltaStateClosure": 0.1,
                        "deltaRatio": 2.0,
                    },
                }
            ],
        },
    )

    spec = build_transport_validation_batch_spec(
        transport_winner_packet_path=winner_packet,
        groups=["crystal-mixed"],
        output_root=tmp_path / "out",
        samples_per_segment=4,
    )

    assert spec["cliBinary"].endswith("/tmp/LeniaCLI")
    assert len(spec["runs"]) == 6
    assert spec["runs"][0]["samplesPerSegment"] == 4
    assert spec["runs"][0]["tags"]["controlGroup"] == "crystal-mixed-medium-wide-validation"
    zeroarea = [row for row in spec["runs"] if "zeroarea" in row["name"]]
    assert len(zeroarea) == 2
    assert zeroarea[0]["vertices"][-1] == [1.0, 2.0]
