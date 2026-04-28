from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.dense_report import build_transport_dense_report


def test_build_transport_dense_report_links_dense_runs_to_winners(tmp_path: Path) -> None:
    dense_path = tmp_path / "dense.json"
    dense_path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "name": "mystic-dense-forward",
                        "pointCount": 17,
                        "endpointTransportedStateDistance": 0.002,
                        "transportToPhenotypeRatio": 20.0,
                        "maxTransportedStateDistanceFromStart": 0.0025,
                        "tags": {
                            "controlGroup": "mystic-mixed-small-wide",
                            "role": "loop",
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    winner_path = tmp_path / "winner.json"
    winner_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "controlGroup": "mystic-mixed",
                        "winnerByCompositeScore": {
                            "controlGroup": "mystic-mixed-mh-small",
                            "deltaStateClosure": 0.00025,
                            "deltaRatio": 3.0,
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_transport_dense_report(
        dense_batch_packet_path=dense_path,
        transport_winner_packet_path=winner_path,
    )

    assert report["packetKind"] == "transport_dense_report_v1"
    assert report["groupCount"] == 1
    group = report["groups"][0]
    assert group["controlGroup"] == "mystic-mixed-small-wide"
    assert group["canonicalGroup"] == "mystic-mixed"
    assert group["sparseWinnerControlGroup"] == "mystic-mixed-mh-small"
    assert group["denseTopLoopName"] == "mystic-dense-forward"
