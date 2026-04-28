from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.hotspot.refresh_batch import (
    build_hotspot_transport_refresh_spec,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_hotspot_transport_refresh_spec_expands_selected_candidates(
    tmp_path: Path,
) -> None:
    neighborhood = tmp_path / "neighborhood.json"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _write_json(
        neighborhood,
        {
            "groups": [
                {
                    "controlGroup": "crystal-mh",
                    "specimen": "crystal",
                    "selectedCandidates": [
                        {"candidateId": "crystal-mh-medium-01", "exportDir": str(bundle)},
                        {"candidateId": "crystal-mh-medium-02", "exportDir": str(bundle)},
                    ],
                }
            ]
        },
    )

    spec = build_hotspot_transport_refresh_spec(
        neighborhood_packet_path=neighborhood,
        cli_binary=tmp_path / "LeniaCLI",
        output_root=tmp_path / "outputs",
        per_group_limit=1,
        profiles=["small", "medium"],
    )

    assert spec["packetKind"] == "hotspot_transport_refresh_batch_spec_v1"
    assert spec["runCount"] == 4
    names = [row["name"] for row in spec["runs"]]
    assert names == [
        "crystal-mh-medium-01-m0-small-open",
        "crystal-mh-medium-01-h0-small-open",
        "crystal-mh-medium-01-m0-medium-open",
        "crystal-mh-medium-01-h0-medium-open",
    ]
    assert spec["runs"][0]["offsets"] == [-0.001, -0.0005, 0.0, 0.0005, 0.001]
