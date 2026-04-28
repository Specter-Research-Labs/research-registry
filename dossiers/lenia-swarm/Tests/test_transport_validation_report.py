from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.validation_report import (
    build_transport_validation_report,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_transport_validation_report_compares_validation_to_sparse_winner(
    tmp_path: Path,
) -> None:
    winner_packet = tmp_path / "winner.json"
    validation_packet = tmp_path / "validation.json"

    _write_json(
        winner_packet,
        {
            "groups": [
                {
                    "controlGroup": "crystal-mixed",
                    "winnerByCompositeScore": {
                        "controlGroup": "crystal-mixed-medium-wide",
                        "deltaStateClosure": 0.2,
                        "deltaRatio": 1.5,
                        "packetLabel": "refine",
                    },
                }
            ]
        },
    )
    _write_json(
        validation_packet,
        {
            "groups": [
                {
                    "controlGroup": "crystal-mixed-medium-wide-validation",
                    "topLoop": {"name": "loop-a"},
                    "bestControl": {"name": "zeroarea-a", "kind": "zeroarea-mh-dense"},
                    "loopMinusBestControlStateClosure": 0.05,
                    "loopMinusBestControlRatio": 0.25,
                },
                {
                    "controlGroup": "mystic-mixed-xsmall-validation",
                    "topLoop": {"name": "loop-b"},
                    "bestControl": {"name": "zeroarea-b", "kind": "zeroarea-mh-dense"},
                    "loopMinusBestControlStateClosure": 0.01,
                    "loopMinusBestControlRatio": 0.02,
                }
            ]
        },
    )

    report = build_transport_validation_report(
        transport_winner_packet_path=winner_packet,
        labeled_validation_packets=[("validation", validation_packet)],
    )

    assert report["packetKind"] == "transport_validation_report_v1"
    assert report["survivesValidationStronglyCount"] == 1
    assert report["skippedGroupCount"] == 1
    row = report["groups"][0]
    assert row["winnerControlGroup"] == "crystal-mixed-medium-wide"
    assert row["validationBestControlKind"] == "zeroarea-mh-dense"
    assert row["validationMinusWinnerDeltaState"] == -0.15000000000000002
    assert row["survivesValidationStrongly"] is True
