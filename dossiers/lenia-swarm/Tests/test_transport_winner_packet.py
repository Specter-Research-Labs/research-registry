from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.winner import (
    _parse_control_group,
    build_transport_winner_packet,
)


def test_parse_control_group_handles_refined_and_variant_names() -> None:
    assert _parse_control_group("crystal-mixed-mh-medium") == (
        "crystal-mixed",
        "medium",
        "mh",
    )
    assert _parse_control_group("mystic-mixed-mbias-small") == (
        "mystic-mixed",
        "small",
        "mbias",
    )
    assert _parse_control_group("crystal-mixed-medium-wide") == (
        "crystal-mixed",
        "medium-wide",
        "mh",
    )


def test_build_transport_winner_packet_selects_composite_winner(tmp_path: Path) -> None:
    packet_a = tmp_path / "medium.json"
    packet_b = tmp_path / "refine.json"
    packet_a.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "controlGroup": "crystal-mixed-mh-medium",
                        "topLoop": {"name": "square-forward-medium"},
                        "bestControl": {"name": "outback-h-medium"},
                        "loopMinusBestControlStateClosure": 0.0002,
                        "loopMinusBestControlRatio": -1.75,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    packet_b.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "controlGroup": "crystal-mixed-medium-wide",
                        "topLoop": {"name": "square-reverse-medium-wide"},
                        "bestControl": {"name": "outback-m-medium-wide"},
                        "loopMinusBestControlStateClosure": 0.00018,
                        "loopMinusBestControlRatio": 1.58,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    packet = build_transport_winner_packet(
        [
            ("medium", packet_a),
            ("refine", packet_b),
        ]
    )

    assert packet["packetKind"] == "transport_winner_packet_v1"
    assert packet["groupCount"] == 1
    group = packet["groups"][0]
    assert group["controlGroup"] == "crystal-mixed"
    assert group["winnerByCompositeScore"]["scale"] == "medium-wide"
    assert group["bestScaleByStateClosure"]["scale"] == "medium"
    assert group["bestScaleByRatio"]["scale"] == "medium-wide"
