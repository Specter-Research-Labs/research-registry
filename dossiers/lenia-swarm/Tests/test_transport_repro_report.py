from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.repro_report import build_transport_repro_report


def test_build_transport_repro_report_groups_repeat_runs(tmp_path: Path) -> None:
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "name": "crystal-forward-rep01",
                        "endpointPhenotypeDistance": 0.1,
                        "endpointTransportedStateDistance": 0.4,
                        "transportToPhenotypeRatio": 4.0,
                        "tags": {
                            "controlGroup": "crystal-mixed-medium-wide",
                            "kind": "square-forward-medium-wide",
                            "role": "loop",
                        },
                    },
                    {
                        "name": "crystal-forward-rep02",
                        "endpointPhenotypeDistance": 0.1,
                        "endpointTransportedStateDistance": 0.4,
                        "transportToPhenotypeRatio": 4.0,
                        "tags": {
                            "controlGroup": "crystal-mixed-medium-wide",
                            "kind": "square-forward-medium-wide",
                            "role": "loop",
                        },
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_transport_repro_report(batch_path)

    assert report["packetKind"] == "transport_repro_report_v1"
    assert report["groupCount"] == 1
    kind = report["groups"][0]["kinds"][0]
    assert kind["repeatCount"] == 2
    assert kind["stateStable"] is True
    assert kind["ratioRange"] == 0.0

