from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.transport.scale_report import build_transport_scale_report


def _write_packet(path: Path, group: str, delta_state: float, delta_ratio: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "packetKind": "loop_transport_packet_v1",
                "version": 1,
                "groups": [
                    {
                        "controlGroup": group,
                        "topLoop": {"name": f"{group}-loop"},
                        "bestControl": {"name": f"{group}-control"},
                        "loopMinusBestControlStateClosure": delta_state,
                        "loopMinusBestControlPhenotypeClosure": 0.0,
                        "loopMinusBestControlRatio": delta_ratio,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_build_transport_scale_report_tracks_best_scale(tmp_path: Path) -> None:
    small = _write_packet(tmp_path / "small.json", "crystal-mh", 0.1, 2.0)
    medium = _write_packet(tmp_path / "medium.json", "crystal-mh", 0.2, 1.0)

    packet = build_transport_scale_report([("small", small), ("medium", medium)])

    assert packet["packetKind"] == "transport_scale_report_v1"
    assert packet["groupCount"] == 1
    group = packet["groups"][0]
    assert group["bestScaleByStateClosure"]["scale"] == "medium"
    assert group["bestScaleByRatio"]["scale"] == "small"
