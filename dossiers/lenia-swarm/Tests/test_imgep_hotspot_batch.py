from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.imgep.hotspot_batch import build_imgep_hotspot_batch


def test_build_imgep_hotspot_batch_emits_targeted_runs(tmp_path: Path) -> None:
    hotspot_packet = tmp_path / "hotspot.json"
    hotspot_packet.write_text(
        json.dumps(
            {
                "hotspots": [
                    {
                        "kind": "transport_group",
                        "id": "crystal-mh",
                        "score": 1.0,
                        "bestScaleByStateClosure": {"scale": "medium", "deltaStateClosure": 0.1},
                        "bestScaleByRatio": {"scale": "small", "deltaRatio": 2.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    export_root = tmp_path / "exports"
    bundle = export_root / "crystal-cell-example"
    bundle.mkdir(parents=True)
    (export_root.parent / "config.json").write_text(
        json.dumps({"params": {"ranges": {"m": [0.0, 1.0]}}}),
        encoding="utf-8",
    )
    (bundle / "base.json").write_text(
        json.dumps(
            {
                "params": {
                    "m": [0.1],
                    "h": [0.2],
                    "r": [0.3],
                    "s": [0.4],
                    "R": 5.0,
                    "a": [[0.5]],
                    "b": [[0.6]],
                    "w": [[0.7]],
                }
            }
        ),
        encoding="utf-8",
    )
    (bundle / "search.json").write_text("{}", encoding="utf-8")
    (bundle / "meta.json").write_text(
        json.dumps(
            {
                "creature": {
                    "score": 0.0,
                    "genotype": {
                        "m": [0.1],
                        "h": [0.2],
                        "r": [0.3],
                        "s": [0.4],
                        "R": 5.0,
                        "a": [[0.5]],
                        "b": [[0.6]],
                        "w": [[0.7]],
                    },
                    "metrics": {
                        "gyration": 2.0,
                        "center_velocity": 3.0,
                        "moment_anisotropy": 4.0,
                        "largest_component_anisotropy": 5.0,
                    },
                    "phenotype": {"seed": 17},
                }
            }
        ),
        encoding="utf-8",
    )

    packet = build_imgep_hotspot_batch(
        hotspot_packet_path=hotspot_packet,
        export_root=export_root,
        output_root=tmp_path / "out",
        features=[
            "gyration",
            "center_velocity",
            "moment_anisotropy",
            "largest_component_anisotropy",
        ],
    )

    assert packet["runCount"] == 2
    names = [row["name"] for row in packet["runs"]]
    assert "crystal-targeted-imgep-small" in names
    assert "crystal-targeted-imgep-medium" in names
    search_payload = json.loads((tmp_path / "out" / "crystal" / "search.json").read_text())
    assert search_payload["top_k"] == 32
    assert search_payload["collection"]["enabled"] is True
    assert search_payload["collection"]["export_enabled"] is True
