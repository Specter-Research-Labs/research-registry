from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.morphospace.finite_size_validation import (
    build_finite_size_validation_packet,
)


def test_build_finite_size_validation_packet_compares_common_seeds(tmp_path: Path) -> None:
    run128 = tmp_path / "run128"
    run256 = tmp_path / "run256"
    run128.mkdir()
    run256.mkdir()
    _write_jsonl(
        run128 / "results.jsonl",
        [
            _row(1, displacement=10.0, efficiency=0.8, components=1, largest=1.0),
            _row(2, displacement=20.0, efficiency=0.1, components=1, largest=1.0),
            _row(3, displacement=8.0, efficiency=0.7, components=6, largest=0.6),
        ],
    )
    _write_jsonl(
        run256 / "results.jsonl",
        [
            _row(1, displacement=9.0, efficiency=0.7, components=2, largest=0.98),
            _row(2, displacement=7.0, efficiency=0.6, components=1, largest=1.0),
            _row(3, displacement=2.0, efficiency=0.7, components=2, largest=0.98),
        ],
    )

    packet = build_finite_size_validation_packet(
        {"128": run128, "256": run256},
        generated_at="2026-05-21T00:00:00+00:00",
    )

    assert packet["packetKind"] == "fl2c20_motion_finite_size_validation_v1"
    assert packet["seedCount"] == 3
    assert packet["summary"]["perRun"]["128"] == {
        "moving": 2,
        "compactConnected": 2,
        "compactMoving": 1,
    }
    assert packet["summary"]["perRun"]["256"] == {
        "moving": 2,
        "compactConnected": 3,
        "compactMoving": 2,
    }
    transition = packet["summary"]["pairwise"]["128->256"]
    assert transition["movingSurvivalCount"] == 1
    assert transition["compactMovingSurvivalCount"] == 1
    assert packet["summary"]["stableMoverSeeds"] == [1]
    assert packet["summary"]["stableCompactMoverSeeds"] == [1]
    assert packet["summary"]["genotypeHashMismatchCount"] == 0


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _row(
    seed: int,
    *,
    displacement: float,
    efficiency: float,
    components: int,
    largest: float,
) -> dict[str, object]:
    return {
        "seed": seed,
        "score": displacement,
        "metrics": {
            "displacement": displacement,
            "component_count": components,
            "largest_component_fraction": largest,
            "path_length": displacement / efficiency,
            "gyration": 100.0,
            "occupancy_mean": 0.1,
        },
        "descriptor_bundle": {
            "genotype": {
                "hash12": f"hash-{seed}",
            },
        },
    }
