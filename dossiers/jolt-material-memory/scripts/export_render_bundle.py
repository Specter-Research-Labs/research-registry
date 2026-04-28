from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BODY_HALF_EXTENTS = [0.23, 0.23, 0.23]
FLOOR_POSITION = [0.0, -0.5, 0.0]
FLOOR_HALF_EXTENTS = [40.0, 0.5, 10.0]
SPACING = 0.55
STAGGER_X_OFFSET = 0.12
STAGGER_Y_OFFSET = 0.18


def _normalize_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return ROOT / path


def _load_ndjson(ndjson_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    meta: dict[str, object] | None = None
    steps: list[dict[str, object]] = []
    with ndjson_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            record = json.loads(raw)
            if record.get("record_type") == "meta" and meta is None:
                meta = record
            elif record.get("record_type") == "step":
                steps.append(record)
    if meta is None:
        raise ValueError(f"No meta record found in {ndjson_path}")
    if not steps:
        raise ValueError(f"No step records found in {ndjson_path}")
    return meta, steps


def _positions_from_step(step: dict[str, object]) -> np.ndarray:
    values = step.get("body_positions")
    if not isinstance(values, list):
        raise ValueError("step record missing body_positions")
    positions = np.asarray(values, dtype=np.float32)
    if positions.size % 3 != 0:
        raise ValueError("body_positions length must be divisible by 3")
    return positions.reshape((-1, 3))


def _vector_field(step: dict[str, object], key: str, *, expected_size: int) -> np.ndarray:
    values = step.get(key)
    if not isinstance(values, list):
        raise ValueError(f"step record missing {key}")
    array = np.asarray(values, dtype=np.float32)
    if array.shape != (expected_size,):
        raise ValueError(f"{key} must have length {expected_size}")
    return array


def _float_field(step: dict[str, object], key: str) -> float:
    value = step.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"step record missing numeric {key}")
    return float(value)


def _int_field(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"record missing integer-like {key}")
    return int(float(value))


def _float_like(value: object, *, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int | float | str):
        return float(value)
    return fallback


def _compute_rest_positions(layout: str, body_count: int) -> list[list[float]]:
    center = float(body_count - 1) * 0.5
    positions: list[list[float]] = []
    for index in range(body_count):
        x = (float(index) - center) * SPACING
        y = 0.45
        if layout == "staggered":
            x += -STAGGER_X_OFFSET if index % 2 == 0 else STAGGER_X_OFFSET
            if index % 2 == 1:
                y += STAGGER_Y_OFFSET
        positions.append([x, y, 0.0])
    return positions


def _event_windows(meta: dict[str, object]) -> dict[str, int]:
    params_value = meta.get("scenario_params")
    if not isinstance(params_value, dict):
        return {}
    params: dict[str, object] = {str(key): value for key, value in params_value.items()}
    out: dict[str, int] = {}
    for key in (
        "pulse_start_step",
        "pulse_end_step",
        "second_pulse_start_step",
        "second_pulse_end_step",
        "damage_step",
    ):
        value = params.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        out[key] = int(value)
    return out


def export_render_bundle(
    ndjson_path: Path,
    out_dir: Path,
    *,
    stride: int,
) -> Path:
    if stride <= 0:
        raise ValueError("--stride must be positive")

    meta, steps = _load_ndjson(ndjson_path)
    sampled_steps = steps[::stride]
    body_translation = np.stack([_positions_from_step(step) for step in sampled_steps], axis=0)
    body_count = int(body_translation.shape[1])
    body_strain = np.stack(
        [_vector_field(step, "body_strain", expected_size=body_count) for step in sampled_steps],
        axis=0,
    )
    body_contact = np.stack(
        [
            _vector_field(step, "body_contact", expected_size=body_count)
            for step in sampled_steps
        ],
        axis=0,
    )
    body_friction = np.stack(
        [
            _vector_field(step, "body_friction", expected_size=body_count)
            for step in sampled_steps
        ],
        axis=0,
    )
    body_stiffness = np.stack(
        [
            _vector_field(step, "body_stiffness", expected_size=body_count)
            for step in sampled_steps
        ],
        axis=0,
    )
    body_plasticity = np.stack(
        [
            _vector_field(step, "body_plasticity", expected_size=body_count)
            for step in sampled_steps
        ],
        axis=0,
    )
    goal_x = np.asarray([_float_field(step, "goal_x") for step in sampled_steps], dtype=np.float32)
    drive_signal = np.asarray(
        [_float_field(step, "drive_signal") for step in sampled_steps],
        dtype=np.float32,
    )
    com_translation = body_translation.mean(axis=1)

    body_count = _int_field(meta, "body_count")
    layout = str(meta.get("layout", "line"))
    raw_memory_params = meta.get("memory_params")
    memory_params: dict[str, object]
    if not isinstance(raw_memory_params, dict):
        memory_params = {}
    else:
        memory_params = {str(key): value for key, value in raw_memory_params.items()}
    run = {
        "scenario": str(meta.get("scenario", "")),
        "policy": str(meta.get("policy", "")),
        "memory_mode": str(meta.get("memory_mode", "")),
        "backend": str(meta.get("backend", "")),
        "layout": layout,
        "memory_variant": str(meta.get("memory_variant", "")),
    }
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "source": {
            "run_id": str(meta.get("run_id", ndjson_path.stem)),
            "ndjson_path": str(ndjson_path),
            "exporter": "export_render_bundle.py",
        },
        "run": run,
        "timeline": {
            "dt": _float_like(meta.get("dt"), fallback=0.0),
            "step_count": _int_field(meta, "steps"),
            "frame_count": len(sampled_steps),
            "stride": stride,
        },
        "scene": {
            "body_count": body_count,
            "body_primitive": "box",
            "body_half_extents": BODY_HALF_EXTENTS,
            "floor_position": FLOOR_POSITION,
            "floor_half_extents": FLOOR_HALF_EXTENTS,
        },
        "rest_positions": _compute_rest_positions(layout, body_count),
        "links": [[index, index + 1] for index in range(body_count - 1)],
        "goal_markers": {
            "axis": "x",
            "scenario_params": meta.get("scenario_params", {}),
        },
        "event_windows": _event_windows(meta),
        "channels": {
            "body_plasticity": {
                "display": "Memory trace",
                "range": [0.0, _float_like(memory_params.get("max_plastic"), fallback=1.0)],
            },
            "body_stiffness": {
                "display": "Local stiffness",
                "range": [
                    _float_like(memory_params.get("min_stiffness"), fallback=0.0),
                    _float_like(memory_params.get("max_stiffness"), fallback=1.0),
                ],
            },
            "body_friction": {
                "display": "Local friction",
                "range": [
                    _float_like(memory_params.get("min_friction"), fallback=0.0),
                    _float_like(memory_params.get("max_friction"), fallback=1.0),
                ],
            },
            "body_contact": {
                "display": "Ground contact",
                "range": [0.0, 1.0],
            },
            "body_strain": {
                "display": "Local strain",
                "range": [0.0, max(1.0e-6, float(np.max(body_strain)))],
            },
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    np.savez_compressed(
        out_dir / "tracks.npz",
        body_translation=body_translation,
        body_strain=body_strain,
        body_contact=body_contact,
        body_friction=body_friction,
        body_stiffness=body_stiffness,
        body_plasticity=body_plasticity,
        goal_x=goal_x,
        drive_signal=drive_signal,
        com_translation=com_translation.astype(np.float32),
    )
    return out_dir


def main() -> int:
    from paths import resolve_artifact_dir

    parser = argparse.ArgumentParser(description="Export a Blender render bundle from run NDJSON")
    parser.add_argument("--ndjson", required=True)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--stride", type=int, default=2)
    args = parser.parse_args()

    ndjson_path = _normalize_path(args.ndjson)
    bundle_name = args.name or ndjson_path.stem
    out_root = (
        _normalize_path(args.out_dir)
        if args.out_dir
        else resolve_artifact_dir("render-bundles", ROOT / "data" / "render-bundles")
    )
    bundle_dir = out_root / bundle_name
    export_render_bundle(ndjson_path, bundle_dir, stride=args.stride)
    print(f"Exported render bundle to {bundle_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
