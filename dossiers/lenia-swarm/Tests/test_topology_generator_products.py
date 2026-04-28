from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any, cast

from lenia_swarm_analysis.generators.analysis import run_generator_analysis
from lenia_swarm_analysis.generators.pilot import analyze_generator_runs
from lenia_swarm_analysis.generators.sheets import render_generator_sheets
from lenia_swarm_analysis.generators.targets import build_generator_targets


def _fingerprint(theta: float) -> list[int]:
    values = [
        1.0 + math.cos(theta),
        1.0 + math.sin(theta),
        1.0 - math.cos(theta),
        1.0 - math.sin(theta),
    ]
    total = sum(values)
    return [round(value / total * 255) for value in values]


def _row(theta: float, index: int) -> dict[str, object]:
    return {
        "specimenId": f"specimen-{index}",
        "runId": "test-run",
        "campaignId": f"campaign-{index:02d}",
        "seed": index,
        "genotype": {
            "canonicalizer": "flow_lenia_params_v1",
            "vector": [math.cos(theta), math.sin(theta)],
        },
        "terminal": {
            "fingerprintResolution": 2,
            "fingerprintU8": _fingerprint(theta),
            "angularSymmetry": {
                "harmonics": [0.0] * 8,
                "dominantAmplitude": 0.25 + 0.01 * index,
                "dominantOrder": 2 + (index % 2),
                "maxOrder": 8,
                "normalizedEntropy": 0.5,
            },
            "finalMass": 1.0 + 0.1 * index,
            "finalOccupancy": 0.25,
            "finalGyration": 2.0 + 0.05 * index,
        },
        "trajectory": {
            "pathTortuosity": 1.0 + 0.2 * index,
            "movementEfficiency": 0.5,
            "headingCircularVariance": 0.1,
            "accumulatedTurnAbs": 0.2,
        },
    }


def _pilot_result(row: dict[str, object], seed: int) -> dict[str, object]:
    terminal = row["terminal"]
    trajectory = row["trajectory"]
    return {
        "seed": seed,
        "init_seed": seed,
        "backend": "mlx-swift",
        "implementation": {"mode": "flowlenia_2022_paper_equations"},
        "initial_condition_family": "test-family",
        "descriptor_bundle": {
            "descriptorVersion": 1,
            "genotype": row["genotype"],
            "terminal": terminal,
            "trajectory": trajectory,
        },
        "filters_passed": True,
        "filters": {},
        "metrics": {},
        "params": {"seed": seed},
        "score": 1.0,
        "score_weights": {},
        "sweep": {},
    }


def _pilot_result_for_goal(
    row: dict[str, Any],
    seed: int,
    goal: dict[str, float],
) -> dict[str, Any]:
    result = _pilot_result(row, seed)
    bundle = cast(dict[str, Any], result["descriptor_bundle"])
    terminal = cast(dict[str, Any], bundle["terminal"])
    trajectory = cast(dict[str, Any], bundle["trajectory"])
    angular = cast(dict[str, Any], terminal["angularSymmetry"])
    terminal["finalMass"] = goal["terminal_final_mass"]
    terminal["finalGyration"] = goal["terminal_final_gyration"]
    terminal["finalOccupancy"] = goal["terminal_final_occupancy"]
    angular["dominantAmplitude"] = goal["symmetry_dominant_amplitude"]
    angular["normalizedEntropy"] = goal["symmetry_entropy"]
    trajectory["pathTortuosity"] = goal["trajectory_path_tortuosity"]
    return result


def _encode_result_fingerprint_base64(result: dict[str, Any]) -> dict[str, Any]:
    bundle = cast(dict[str, Any], result["descriptor_bundle"])
    terminal = cast(dict[str, Any], bundle["terminal"])
    payload = cast(list[int], terminal["fingerprintU8"])
    raw = bytes(payload)
    terminal["fingerprintU8"] = base64.b64encode(raw).decode("ascii")
    return result


def _write_generator_fixture(tmp_path: Path) -> Path:
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "export.manifest.json"
    analysis_dir = tmp_path / "generators"

    rows = []
    for index in range(12):
        theta = 2.0 * math.pi * index / 12.0
        rows.append(_row(theta, index))
    rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps({"rowsPath": rows_path.name}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    run_generator_analysis(
        manifest_path,
        analysis_dir,
        representation="fingerprint_only",
        maxdim=1,
        top_h1=2,
        coeff=2,
    )
    return analysis_dir


def test_render_generator_sheets_writes_png_and_index(tmp_path: Path) -> None:
    analysis_dir = _write_generator_fixture(tmp_path)
    output_dir = tmp_path / "sheets"

    summary = render_generator_sheets(analysis_dir, output_dir)

    assert summary["sheetCount"] >= 1
    assert (output_dir / "index.html").is_file()
    image_path = output_dir / summary["sheets"][0]["imageName"]
    assert image_path.is_file()


def test_build_generator_targets_writes_imgep_configs(tmp_path: Path) -> None:
    analysis_dir = _write_generator_fixture(tmp_path)
    output_dir = tmp_path / "targets"
    base_imgep = tmp_path / "base-imgep.json"
    base_imgep.write_text(
        json.dumps(
            {
                "iterations": 64,
                "warmupIterations": 16,
                "batchSize": 2,
                "seedsPerCandidate": 2,
                "goal": {"features": [], "boundsMode": "auto", "bounds": None},
                "mutation": {"std": 0.1, "clip": True},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    packet = build_generator_targets(
        analysis_dir,
        output_dir,
        features=(
            "terminal_final_mass",
            "terminal_final_gyration",
            "symmetry_dominant_amplitude",
            "symmetry_entropy",
            "trajectory_path_tortuosity",
        ),
        edge_alphas=(0.5,),
        bounds_margin=0.1,
        base_imgep_config_path=base_imgep,
    )

    assert len(packet["generators"]) >= 1
    first = packet["generators"][0]
    assert first["specimenGoals"]
    assert first["edgeGoals"]
    config_path = output_dir / first["imgepConfigPath"]
    assert config_path.is_file()


def test_analyze_generator_runs_reports_edge_preference_and_cycle_distance(tmp_path: Path) -> None:
    analysis_dir = _write_generator_fixture(tmp_path)
    targets_dir = tmp_path / "targets"
    base_imgep = tmp_path / "base-imgep.json"
    base_imgep.write_text(
        json.dumps(
            {
                "iterations": 64,
                "warmupIterations": 16,
                "batchSize": 2,
                "seedsPerCandidate": 2,
                "goal": {"features": [], "boundsMode": "auto", "bounds": None},
                "mutation": {"std": 0.1, "clip": True},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    packet = build_generator_targets(
        analysis_dir,
        targets_dir,
        features=(
            "terminal_final_mass",
            "terminal_final_gyration",
            "terminal_final_occupancy",
            "symmetry_dominant_amplitude",
            "symmetry_entropy",
            "trajectory_path_tortuosity",
        ),
        edge_alphas=(0.5,),
        bounds_margin=0.1,
        base_imgep_config_path=base_imgep,
    )

    generator = packet["generators"][0]
    run_dir = tmp_path / generator["generatorId"]
    run_dir.mkdir()
    source_rows = {
        row["specimenId"]: row
        for row in (
            json.loads(line)
            for line in (tmp_path / "rows.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    first_specimen = source_rows[generator["representativeSpecimenIds"][0]]
    second_specimen = source_rows[generator["representativeSpecimenIds"][1]]
    edge_goal = generator["edgeGoals"][0]["goal"]
    results = [
        _encode_result_fingerprint_base64(_pilot_result(first_specimen, 1)),
        _pilot_result_for_goal(first_specimen, 2, edge_goal),
        _pilot_result(second_specimen, 3),
    ]
    (run_dir / "results.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in results),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps(
            {"history_count": 3, "top_count": 3, "duration_seconds": 12.0},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    summary = analyze_generator_runs(
        targets_dir / "targets.json",
        [run_dir],
        tmp_path / "pilot-analysis",
    )

    assert summary["generatorCount"] == 1
    run = summary["runs"][0]
    assert run["keptResultCount"] == 3
    assert run["boundsHitRate"] > 0.0
    assert run["nearestGoalKindCounts"]["edge"] >= 1
    assert run["representativePhenotypeDistance"]["min"] == 0.0
