from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.hotspot.packet import build_hotspot_packet


def test_build_hotspot_packet_merges_cycle_and_transport_sources(tmp_path: Path) -> None:
    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(
        json.dumps(
            {
                "packetKind": "cycle_lift_packet_v1",
                "representation": "fingerprint_plus_symmetry",
                "generators": [
                    {
                        "generatorId": "g0",
                        "persistence": 0.1,
                        "reentryEdgeCount": 2,
                        "nonEndpointRepresentativeEdgeCount": 3,
                        "maxEscapeRatio": 1.5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    transport_path = tmp_path / "transport.json"
    transport_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_scale_report_v1",
                "groups": [
                    {
                        "controlGroup": "crystal-mh",
                        "bestScaleByStateClosure": {"scale": "small", "deltaStateClosure": 0.001},
                        "bestScaleByRatio": {"scale": "small", "deltaRatio": 1.25},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    packet = build_hotspot_packet(
        cycle_lift_packet=cycle_path,
        transport_scale_report=transport_path,
    )

    assert packet["packetKind"] == "morphospace_hotspot_packet_v1"
    assert packet["hotspotCount"] == 2
    assert packet["topHotspots"][0]["kind"] == "cycle_generator"


def test_build_hotspot_packet_accepts_transport_winner_packet(tmp_path: Path) -> None:
    transport_path = tmp_path / "winner.json"
    transport_path.write_text(
        json.dumps(
            {
                "packetKind": "transport_winner_packet_v1",
                "groups": [
                    {
                        "controlGroup": "crystal-mixed",
                        "bestScaleByStateClosure": {
                            "scale": "medium",
                            "deltaStateClosure": 0.00018,
                        },
                        "bestScaleByRatio": {
                            "scale": "medium-wide",
                            "deltaRatio": 1.58,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    packet = build_hotspot_packet(cycle_lift_packet=None, transport_scale_report=transport_path)

    assert packet["hotspotCount"] == 1
    assert packet["topHotspots"][0] == {
        "kind": "transport_group",
        "id": "crystal-mixed",
    }
