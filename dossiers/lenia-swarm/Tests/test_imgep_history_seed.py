from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.imgep.history_seed import build_history_seed


def test_build_history_seed_reads_bundle_meta(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "meta.json").write_text(
        json.dumps(
            {
                "creature": {
                    "score": 1.25,
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
                    "metrics": {"gyration": 2.0, "center_velocity": 3.0},
                    "phenotype": {"seed": 17},
                }
            }
        ),
        encoding="utf-8",
    )

    entries = build_history_seed([bundle], ["gyration", "center_velocity"])

    assert len(entries) == 1
    assert entries[0]["seed"] == 17
    assert entries[0]["embedding"] == [2.0, 3.0]
    assert entries[0]["score"] == 1.25
