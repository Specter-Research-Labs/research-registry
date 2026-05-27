from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.morphospace_cli import main as morphospace_main


def test_summarize_track1_raw_uses_summary_count_and_writes_candidates(
    tmp_path: Path,
    capsys,
) -> None:
    run_root = tmp_path / "runs"
    run_id = "track1b-2c20-harvest-8192-s4000000"
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"count": 8192, "resultsCount": 8192, "durationSeconds": 12.0}),
        encoding="utf-8",
    )
    rows = [_row(1, displacement=12.0, efficiency=0.8, components=1, largest=1.0)]
    rows.extend(
        _row(seed, displacement=1.0, efficiency=0.5, components=7, largest=0.5)
        for seed in range(2, 8193)
    )
    rows.append(_row(99999, displacement=99.0, efficiency=1.0, components=1, largest=1.0))
    _write_jsonl(run_dir / "results.jsonl", rows)

    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "candidates.json"
    assert morphospace_main(
        [
            "summarize-track1-raw",
            "--run-root",
            str(run_root),
            "--output",
            str(summary_path),
            "--candidate-manifest",
            str(manifest_path),
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["completedRunCount"] == 1
    assert payload["candidateCount"] == manifest["candidateCount"]
    assert summary["completedResultCount"] == 8192
    assert summary["lineCountAnomalies"] == [
        {
            "runId": run_id,
            "summaryResultsCount": 8192,
            "actualResultLines": 8193,
            "usedResultLines": 8192,
        }
    ]
    family = summary["families"]["2c20_paper_random"]
    assert family["counts"]["moving"] == 1
    assert family["counts"]["compactMoving"] == 1
    assert family["counts"]["coherentMover"] == 1
    assert family["candidates"]["topDisplacement"][0]["seed"] == 1
    assert manifest["candidates"][0]["seed"] == 1


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
        "init_seed": 1000 + seed,
        "score": displacement,
        "filters_passed": True,
        "metrics": {
            "displacement": displacement,
            "component_count": components,
            "largest_component_fraction": largest,
            "path_length": displacement / efficiency,
            "center_velocity": displacement / 525.0,
            "gyration": 100.0,
            "occupancy_mean": 0.1,
            "is_stable": False,
        },
        "descriptor_bundle": {
            "genotype": {"hash12": f"genotype-{seed}"},
            "terminal": {"fingerprintHash12": f"fingerprint-{seed}"},
            "trajectory": {"movementEfficiency": efficiency},
        },
    }
