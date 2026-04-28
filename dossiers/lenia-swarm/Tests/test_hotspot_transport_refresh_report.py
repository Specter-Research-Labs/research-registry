from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.hotspot.refresh_report import (
    build_hotspot_transport_refresh_report,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_hotspot_transport_refresh_report_compares_to_atlas_baseline(
    tmp_path: Path,
) -> None:
    atlas = tmp_path / "atlas.json"
    _write_json(
        atlas,
        {
            "runs": [
                {
                    "name": "crystal-m0-open",
                    "coordinate": "m.0",
                    "transportToPhenotypeRatio": 20.0,
                    "endpointTransportedStateDistance": 0.0014,
                },
                {
                    "name": "crystal-h0-open",
                    "coordinate": "h.0",
                    "transportToPhenotypeRatio": 30.0,
                    "endpointTransportedStateDistance": 0.0013,
                },
            ]
        },
    )
    refresh = tmp_path / "refresh.json"
    _write_json(
        refresh,
        {
            "runs": [
                {
                    "name": "crystal-mh-medium-01-m0-small-open",
                    "packetPath": "/tmp/packet-a.json",
                    "transportToPhenotypeRatio": 22.5,
                    "endpointTransportedStateDistance": 0.0016,
                    "tags": {
                        "controlGroup": "crystal-mh",
                        "candidateId": "crystal-mh-medium-01",
                        "profile": "small",
                        "coordinate": "m.0",
                        "specimen": "crystal",
                    },
                },
                {
                    "name": "crystal-mh-medium-01-h0-small-open",
                    "packetPath": "/tmp/packet-b.json",
                    "transportToPhenotypeRatio": 29.0,
                    "endpointTransportedStateDistance": 0.00125,
                    "tags": {
                        "controlGroup": "crystal-mh",
                        "candidateId": "crystal-mh-medium-01",
                        "profile": "small",
                        "coordinate": "h.0",
                        "specimen": "crystal",
                    },
                },
            ]
        },
    )

    report = build_hotspot_transport_refresh_report(
        refresh_batch_packet_path=refresh,
        baseline_atlas_packet_path=atlas,
    )

    assert report["packetKind"] == "hotspot_transport_refresh_report_v1"
    assert report["groupCount"] == 1
    group = report["groups"][0]
    assert group["controlGroup"] == "crystal-mh"
    assert group["positiveRatioDeltaCount"] == 1
    assert group["positiveStateDeltaCount"] == 1
    assert group["bestByRatioDelta"]["coordinate"] == "m.0"
    assert group["bestByRatioDelta"]["deltaRatioVsBaseline"] == 2.5
