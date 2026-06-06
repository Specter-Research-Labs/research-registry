from __future__ import annotations

import gzip
import json
from pathlib import Path

from experiments.basin_width.analyze import build_summary


def _write_basin(root: Path, theorem: str, structures: dict[str, int]) -> None:
    theorem_dir = root / theorem
    theorem_dir.mkdir(parents=True)
    seeds = []
    seed = 0
    for structure, count in structures.items():
        for _ in range(count):
            seeds.append(
                {
                    "seed": seed,
                    "solved": True,
                    "structure_hash": structure,
                    "iterations_to_solve": 2,
                }
            )
            seed += 1
    payload = {
        "theorem_name": theorem,
        "seeds": list(range(seed)),
        "seed_results": seeds,
        "solve_rate": 1.0,
        "unique_structures": len(structures),
        "dominant_structure_frequency": max(structures.values()) / seed,
        "structure_distribution": structures,
    }
    (theorem_dir / "basin_analysis.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_lesions(root: Path) -> None:
    root.mkdir(parents=True)
    payload = {
        "theorems": [
            {
                "name": "wide",
                "wild_type": {"solved": True, "iterations": 3},
                "interventions": [
                    {
                        "name": "block_intro",
                        "blocked": ["intro"],
                        "baseline_solved": True,
                        "solved": True,
                        "hash_mismatch": True,
                        "ged_search_graph": {"normalized": 0.7},
                    },
                    {
                        "name": "control_null",
                        "blocked": ["simp"],
                        "baseline_solved": True,
                        "solved": True,
                        "is_control": True,
                    },
                ],
            },
            {
                "name": "narrow",
                "wild_type": {"solved": True, "iterations": 5},
                "interventions": [
                    {
                        "name": "block_rw",
                        "blocked": ["rw"],
                        "baseline_solved": True,
                        "solved": False,
                    }
                ],
            },
        ]
    }
    with gzip.open(root / "summary.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_basin_width_summary_separates_controls_and_path_blocks(tmp_path: Path) -> None:
    basin = tmp_path / "basin"
    lesions = tmp_path / "lesions"
    _write_basin(basin, "wide", {"a": 2, "b": 2})
    _write_basin(basin, "narrow", {"a": 4})
    _write_lesions(lesions)

    summary = build_summary(
        basin_dir=basin,
        lesion_dir=lesions,
        provider="heuristic",
        run_id="unit",
    )

    assert summary["joined_theorems"] == 2
    assert summary["path_block_rows"] == 2
    assert summary["controls"]["control_rows"] == 1
    assert summary["bucket_summary"][1]["bucket"] == "1"
    wide = next(row for row in summary["theorems"] if row["theorem"] == "wide")
    assert wide["path_recovery_rate"] == 1.0
    assert wide["path_reroute_rate_among_recovered"] == 1.0
    assert wide["control_recovery_rate"] == 1.0

