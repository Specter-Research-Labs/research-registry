from __future__ import annotations

import json
from pathlib import Path

from lenia_swarm_analysis.fiber.survival_scoring import (
    load_terminal_trace,
    score_role_pair,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_result(path: Path, *, final_mass: float, component_count: int) -> None:
    row = {
        "descriptor_bundle": {
            "terminal": {
                "angularSymmetry": {"normalizedEntropy": 0.5},
                "componentCount": component_count,
                "finalGyration": 4.0,
                "finalMass": final_mass,
                "finalOccupancy": 0.25,
                "fingerprintResolution": 4,
                "fingerprintU8": [
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    0,
                    0,
                    1,
                ],
            },
            "trajectory": {
                "centerVelocity": 0.1,
                "pathTortuosity": 0.2,
            },
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _trace_fixture(root: Path, name: str, masses: list[float]) -> Path:
    step_paths = []
    for index, mass in enumerate(masses):
        step_dir = root / name / f"{index:04d}"
        result_path = step_dir / "results.jsonl"
        _write_result(result_path, final_mass=mass, component_count=index + 1)
        step_path = step_dir / "holonomy-step.json"
        _write_json(
            step_path,
            {
                "sequence_index": index,
                "segment_index": 0,
                "segment_t": float(index),
                "coordinate_values": {"m.0": mass / 100.0},
                "results_path": str(result_path),
            },
        )
        step_paths.append(str(step_path))
    manifest_path = root / name / "holonomy-manifest.json"
    _write_json(
        manifest_path,
        {
            "run_id": name,
            "bundle_path": str(root / "bundle"),
            "loop_path": str(root / "loop.json"),
            "coordinate_paths": ["m.0"],
            "step_manifest_paths": step_paths,
        },
    )
    return manifest_path


def test_load_terminal_trace_scores_endpoint_terminal_motion(tmp_path: Path) -> None:
    manifest = _trace_fixture(tmp_path, "nearest", [4.0, 8.0])

    trace = load_terminal_trace(manifest)

    assert trace["pointCount"] == 2
    assert trace["endpointTerminalDistance"] > 0.0
    assert trace["rows"][1]["terminalStepDelta"] == trace["endpointTerminalDistance"]


def test_score_role_pair_reports_survival_ratio(tmp_path: Path) -> None:
    nearest = load_terminal_trace(_trace_fixture(tmp_path, "nearest", [4.0, 5.0]))
    farthest = load_terminal_trace(_trace_fixture(tmp_path, "farthest", [12.0, 13.0]))

    score = score_role_pair(nearest_trace=nearest, farthest_trace=farthest)

    assert score["startTerminalSeparation"] > 0.0
    assert score["endTerminalSeparation"] > 0.0
    assert score["survivalRatio"] > 0.0
