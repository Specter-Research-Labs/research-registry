from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.transformation_metrics import (
    TERMINAL_AXIS_IDS,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _read_first_jsonl(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                value = json.loads(stripped)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}: first JSONL row is not an object")
                return value
    raise ValueError(f"{path}: no JSONL rows")


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def terminal_vector(axis_values: dict[str, float]) -> np.ndarray:
    return np.asarray([float(axis_values[axis]) for axis in TERMINAL_AXIS_IDS], dtype=np.float64)


def l2(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right))


def _top_axis_deltas(
    *,
    left: dict[str, float],
    right: dict[str, float],
    limit: int = 6,
) -> list[dict[str, Any]]:
    rows = [
        {
            "axisId": axis,
            "left": _finite_or_none(float(left[axis])),
            "right": _finite_or_none(float(right[axis])),
            "delta": _finite_or_none(float(right[axis] - left[axis])),
            "absoluteDelta": _finite_or_none(abs(float(right[axis] - left[axis]))),
        }
        for axis in TERMINAL_AXIS_IDS
    ]
    return sorted(rows, key=lambda row: float(row["absoluteDelta"] or 0.0), reverse=True)[:limit]


def _terminal_axes_from_result_row(row: dict[str, Any], specimen_id: str) -> dict[str, float]:
    descriptor_bundle = row.get("descriptor_bundle")
    if not isinstance(descriptor_bundle, dict):
        raise ValueError(f"{specimen_id}: missing descriptor_bundle")
    terminal = descriptor_bundle.get("terminal")
    trajectory = descriptor_bundle.get("trajectory")
    if not isinstance(terminal, dict):
        raise ValueError(f"{specimen_id}: missing terminal descriptor")
    if not isinstance(trajectory, dict):
        raise ValueError(f"{specimen_id}: missing trajectory descriptor")
    raw_axes = extract_terminal_raw_axes_from_descriptors(
        terminal=terminal,
        trajectory=trajectory,
        specimen_id=specimen_id,
    )
    return transform_axes(raw_axes)


def load_terminal_trace(holonomy_manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(holonomy_manifest_path)
    step_paths = [
        Path(path).expanduser().resolve()
        for path in manifest.get("step_manifest_paths", [])
    ]
    if not step_paths:
        raise ValueError(f"{holonomy_manifest_path}: no step manifests")
    rows = []
    previous_vector: np.ndarray | None = None
    first_vector: np.ndarray | None = None
    previous_axes: dict[str, float] | None = None
    first_axes: dict[str, float] | None = None
    for step_path in step_paths:
        step = _read_json(step_path)
        result_path = Path(str(step["results_path"])).expanduser().resolve()
        result_row = _read_first_jsonl(result_path)
        specimen_id = f"{manifest['run_id']}:{step['sequence_index']}"
        axes = _terminal_axes_from_result_row(result_row, specimen_id)
        vector = terminal_vector(axes)
        if first_vector is None:
            first_vector = vector
            first_axes = axes
        terminal_distance_from_start = l2(vector, first_vector)
        terminal_step_delta = None if previous_vector is None else l2(vector, previous_vector)
        rows.append(
            {
                "sequenceIndex": int(step["sequence_index"]),
                "segmentIndex": int(step["segment_index"]),
                "segmentT": float(step["segment_t"]),
                "coordinateValues": dict(step["coordinate_values"]),
                "terminalAxes": axes,
                "terminalDistanceFromStart": _finite_or_none(terminal_distance_from_start),
                "terminalStepDelta": (
                    _finite_or_none(terminal_step_delta)
                    if terminal_step_delta is not None
                    else None
                ),
                "topTerminalAxisDeltasFromStart": (
                    _top_axis_deltas(left=first_axes, right=axes) if first_axes else []
                ),
            }
        )
        previous_vector = vector
        previous_axes = axes
    assert first_vector is not None and previous_vector is not None
    assert first_axes is not None and previous_axes is not None
    return {
        "packetKind": "fiber_terminal_trace_v1",
        "runId": str(manifest["run_id"]),
        "bundlePath": str(manifest["bundle_path"]),
        "loopPath": str(manifest["loop_path"]),
        "coordinatePaths": list(manifest["coordinate_paths"]),
        "pointCount": len(rows),
        "endpointTerminalDistance": _finite_or_none(l2(previous_vector, first_vector)),
        "maxTerminalDistanceFromStart": _finite_or_none(
            max(float(row["terminalDistanceFromStart"]) for row in rows)
        ),
        "maxTerminalStepDelta": _finite_or_none(
            max(
                (
                    float(row["terminalStepDelta"])
                    for row in rows
                    if row["terminalStepDelta"] is not None
                ),
                default=0.0,
            )
        ),
        "topEndpointAxisDeltas": _top_axis_deltas(left=first_axes, right=previous_axes),
        "rows": rows,
    }


def score_role_pair(
    *,
    nearest_trace: dict[str, Any],
    farthest_trace: dict[str, Any],
) -> dict[str, Any]:
    nearest_start = nearest_trace["rows"][0]["terminalAxes"]
    nearest_end = nearest_trace["rows"][-1]["terminalAxes"]
    farthest_start = farthest_trace["rows"][0]["terminalAxes"]
    farthest_end = farthest_trace["rows"][-1]["terminalAxes"]
    start_distance = l2(terminal_vector(nearest_start), terminal_vector(farthest_start))
    end_distance = l2(terminal_vector(nearest_end), terminal_vector(farthest_end))
    return {
        "startTerminalSeparation": _finite_or_none(start_distance),
        "endTerminalSeparation": _finite_or_none(end_distance),
        "survivalRatio": _finite_or_none(end_distance / start_distance)
        if start_distance > 0
        else None,
        "topStartAxisDeltas": _top_axis_deltas(left=nearest_start, right=farthest_start),
        "topEndAxisDeltas": _top_axis_deltas(left=nearest_end, right=farthest_end),
    }
