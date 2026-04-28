from __future__ import annotations

import base64
from statistics import mean, pstdev
from typing import Any

import numpy as np

from lenia_swarm_analysis.transformation_metrics import (
    compute_center_velocity_trace,
    extract_terminal_raw_axes_from_descriptors,
)

from .derive_anatomy import (
    _arrangement_class,
    _assembly_class,
    _enclosure_class,
    _symmetry_class,
)

CREATURE_SIGNAL_AXIS_IDS: tuple[str, ...] = (
    "largest_component_share_final",
    "coherence_mean",
    "coherence_min",
    "fragmentation_peak",
    "fragmentation_variability",
    "part_persistence_score",
    "shape_persistence_score",
    "symmetry_stability_score",
    "polarity_stability_score",
    "enclosure_persistence_score",
    "whole_body_motion_score",
    "deformation_without_dissolution_score",
)

BODY_PLAN_ERROR_AXIS_IDS: tuple[str, ...] = (
    "largest_component_share_final",
    "fragmentation",
    "cavity_count",
    "axial_polarity",
    "center_offset",
    "elongation",
    "whole_body_motion_score",
)


def _fingerprint_array(terminal: dict[str, Any], *, specimen_id: str) -> np.ndarray:
    resolution_value = terminal.get("fingerprintResolution")
    if not isinstance(resolution_value, (int, float)):
        raise SystemExit(f"{specimen_id}: missing fingerprintResolution")
    resolution = int(resolution_value)
    payload = terminal.get("fingerprintU8")
    if isinstance(payload, list):
        if len(payload) != resolution * resolution or any(
            not isinstance(value, int) for value in payload
        ):
            raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
        values = np.asarray(payload, dtype=np.float32)
    elif isinstance(payload, str):
        values = np.frombuffer(base64.b64decode(payload), dtype=np.uint8).astype(np.float32)
        if values.size != resolution * resolution:
            raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
    else:
        raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
    return values.reshape(resolution, resolution)


def _component_masks(mask: np.ndarray) -> list[np.ndarray]:
    height, width = mask.shape
    visited = np.zeros((height, width), dtype=bool)
    components: list[np.ndarray] = []
    for y in range(height):
        for x in range(width):
            if visited[y, x] or not bool(mask[y, x]):
                continue
            frontier = [(y, x)]
            visited[y, x] = True
            component = np.zeros_like(mask, dtype=bool)
            while frontier:
                cy, cx = frontier.pop()
                component[cy, cx] = True
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny = cy + dy
                    nx = cx + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and bool(mask[ny, nx])
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        frontier.append((ny, nx))
            components.append(component)
    return components


def _largest_component_share(mask: np.ndarray) -> tuple[float, np.ndarray]:
    if not np.any(mask):
        return 0.0, np.zeros_like(mask, dtype=bool)
    components = _component_masks(mask)
    if not components:
        return 0.0, np.zeros_like(mask, dtype=bool)
    dominant = max(components, key=lambda component: int(np.count_nonzero(component)))
    occupied = float(np.count_nonzero(mask))
    return float(np.count_nonzero(dominant)) / occupied, dominant


def _recenter_mask(mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return np.zeros_like(mask, dtype=bool)
    ys, xs = np.nonzero(mask)
    src_center_y = int(round(float(np.mean(ys))))
    src_center_x = int(round(float(np.mean(xs))))
    dst_center_y = (mask.shape[0] - 1) // 2
    dst_center_x = (mask.shape[1] - 1) // 2
    shift_y = dst_center_y - src_center_y
    shift_x = dst_center_x - src_center_x
    shifted = np.zeros_like(mask, dtype=bool)
    src_y0 = max(0, -shift_y)
    src_y1 = min(mask.shape[0], mask.shape[0] - shift_y) if shift_y >= 0 else mask.shape[0]
    dst_y0 = max(0, shift_y)
    dst_y1 = min(mask.shape[0], mask.shape[0] + shift_y) if shift_y <= 0 else mask.shape[0]
    src_x0 = max(0, -shift_x)
    src_x1 = min(mask.shape[1], mask.shape[1] - shift_x) if shift_x >= 0 else mask.shape[1]
    dst_x0 = max(0, shift_x)
    dst_x1 = min(mask.shape[1], mask.shape[1] + shift_x) if shift_x <= 0 else mask.shape[1]
    if src_y0 < src_y1 and src_x0 < src_x1:
        shifted[dst_y0:dst_y1, dst_x0:dst_x1] = mask[src_y0:src_y1, src_x0:src_x1]
    return shifted


def _overlap_score(lhs: np.ndarray, rhs: np.ndarray) -> float:
    lhs_count = int(np.count_nonzero(lhs))
    rhs_count = int(np.count_nonzero(rhs))
    if lhs_count == 0 and rhs_count == 0:
        return 1.0
    denominator = lhs_count + rhs_count
    if denominator <= 0:
        return 0.0
    return float(2 * np.count_nonzero(lhs & rhs)) / float(denominator)


def _sample_snapshot(sample: dict[str, Any], *, specimen_id: str) -> dict[str, Any]:
    terminal = sample.get("terminal")
    if not isinstance(terminal, dict):
        raise SystemExit(f"{specimen_id}: developmental sample missing terminal descriptor")
    raw_axes = extract_terminal_raw_axes_from_descriptors(
        terminal=terminal,
        trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0},
        specimen_id=specimen_id,
    )
    mask = _fingerprint_array(terminal, specimen_id=specimen_id) > 0
    largest_component_share, dominant_component = _largest_component_share(mask)
    return {
        "raw_axes": raw_axes,
        "mask": mask,
        "dominant_component": dominant_component,
        "largest_component_share": largest_component_share,
        "symmetry_class": _symmetry_class(raw_axes),
        "arrangement_class": _arrangement_class(raw_axes),
        "enclosure_class": _enclosure_class(raw_axes),
        "assembly_class": _assembly_class(raw_axes),
    }


def derive_creature_signal_axes(
    *,
    specimen_id: str,
    trace_samples: list[dict[str, Any]],
) -> dict[str, float]:
    ordered = sorted(trace_samples, key=lambda row: int(row["step"]))
    if not ordered:
        raise SystemExit(f"{specimen_id}: creature signals require replay samples")
    snapshots = [_sample_snapshot(sample, specimen_id=specimen_id) for sample in ordered]
    coherence_series = [float(snapshot["largest_component_share"]) for snapshot in snapshots]
    fragmentation_series = [
        float(snapshot["raw_axes"].get("fragmentation", 0.0)) for snapshot in snapshots
    ]
    shape_overlaps = [
        _overlap_score(
            _recenter_mask(cast_snapshot["mask"]),
            _recenter_mask(next_snapshot["mask"]),
        )
        for cast_snapshot, next_snapshot in zip(snapshots, snapshots[1:], strict=False)
    ]
    part_overlaps = [
        _overlap_score(
            _recenter_mask(cast_snapshot["dominant_component"]),
            _recenter_mask(next_snapshot["dominant_component"]),
        )
        for cast_snapshot, next_snapshot in zip(snapshots, snapshots[1:], strict=False)
    ]
    symmetry_classes = [str(snapshot["symmetry_class"]) for snapshot in snapshots]
    enclosure_classes = [str(snapshot["enclosure_class"]) for snapshot in snapshots]
    polarity_values = [
        float(snapshot["raw_axes"].get("axial_polarity", 0.0)) for snapshot in snapshots
    ]
    center_velocity_trace = compute_center_velocity_trace(ordered)
    locomotion_mean = float(mean(center_velocity_trace)) if center_velocity_trace else 0.0
    deformation_steps: list[float] = []
    for previous_snapshot, current_snapshot in zip(snapshots, snapshots[1:], strict=False):
        previous_axes = previous_snapshot["raw_axes"]
        current_axes = current_snapshot["raw_axes"]
        deformation_steps.append(
            float(
                mean(
                    [
                        abs(
                            float(current_axes.get("elongation", 0.0))
                            - float(previous_axes.get("elongation", 0.0))
                        ),
                        abs(
                            float(current_axes.get("boundary_complexity", 0.0))
                            - float(previous_axes.get("boundary_complexity", 0.0))
                        ),
                        abs(
                            float(current_axes.get("coverage", 0.0))
                            - float(previous_axes.get("coverage", 0.0))
                        ),
                    ]
                )
            )
        )
    fragmentation_peak = max(fragmentation_series)
    fragmentation_min = min(fragmentation_series)
    fragmentation_variability = fragmentation_peak - fragmentation_min
    coherence_mean = float(mean(coherence_series))
    deformation_signal = float(mean(deformation_steps)) if deformation_steps else 0.0
    fragmentation_pressure = 1.0 + max(0.0, fragmentation_peak - 1.0) + fragmentation_variability
    modal_symmetry_class = max(set(symmetry_classes), key=symmetry_classes.count)
    modal_enclosure_class = max(set(enclosure_classes), key=enclosure_classes.count)
    return {
        "largest_component_share_final": float(coherence_series[-1]),
        "coherence_mean": coherence_mean,
        "coherence_min": float(min(coherence_series)),
        "fragmentation_peak": float(fragmentation_peak),
        "fragmentation_variability": float(fragmentation_variability),
        "part_persistence_score": float(mean(part_overlaps)) if part_overlaps else 1.0,
        "shape_persistence_score": float(mean(shape_overlaps)) if shape_overlaps else 1.0,
        "symmetry_stability_score": float(
            sum(1 for value in symmetry_classes if value == modal_symmetry_class)
        )
        / float(len(symmetry_classes)),
        "polarity_stability_score": 1.0 / (1.0 + float(pstdev(polarity_values))),
        "enclosure_persistence_score": float(
            sum(1 for value in enclosure_classes if value == modal_enclosure_class)
        )
        / float(len(enclosure_classes)),
        "whole_body_motion_score": locomotion_mean * coherence_mean,
        "deformation_without_dissolution_score": (
            coherence_mean * deformation_signal / fragmentation_pressure
        ),
    }


def endpoint_creature_axes(
    *,
    specimen_id: str,
    terminal_descriptor: dict[str, Any],
    trajectory_descriptor: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float]]:
    raw_axes = extract_terminal_raw_axes_from_descriptors(
        terminal=terminal_descriptor,
        trajectory=trajectory_descriptor,
        specimen_id=specimen_id,
    )
    mask = _fingerprint_array(terminal_descriptor, specimen_id=specimen_id) > 0
    largest_component_share, _dominant_component = _largest_component_share(mask)
    creature_axes = {
        "largest_component_share_final": largest_component_share,
        "whole_body_motion_score": float(raw_axes.get("locomotion", 0.0)) * largest_component_share,
    }
    return raw_axes, creature_axes


def coherence_class(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> str:
    coherence_mean = float(
        creature_axes.get("coherence_mean", creature_axes.get("largest_component_share_final", 0.0))
    )
    coherence_min = float(
        creature_axes.get("coherence_min", creature_axes.get("largest_component_share_final", 0.0))
    )
    fragmentation_peak = float(
        creature_axes.get("fragmentation_peak", raw_axes.get("fragmentation", 0.0))
    )
    if coherence_min >= 0.82 and fragmentation_peak <= 1.5:
        return "coherent_body"
    if coherence_mean >= 0.6 and fragmentation_peak <= 3.0:
        return "soft_body"
    return "fragmented_pattern"


def organization_class(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> str:
    resolved_coherence_class = coherence_class(raw_axes=raw_axes, creature_axes=creature_axes)
    if resolved_coherence_class == "fragmented_pattern":
        return "diffuse_body"
    if _enclosure_class(raw_axes) == "enclosing":
        return "enclosing_body"
    if _arrangement_class(raw_axes) == "polarized" or raw_axes.get("axial_polarity", 0.0) >= 0.2:
        return "polarized_body"
    symmetry_class = _symmetry_class(raw_axes)
    if symmetry_class == "bilateral_like":
        return "bilateral_body"
    if symmetry_class in {"radial_like", "rotational_like"}:
        return "radial_body"
    return "diffuse_body"


def mobility_class(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> str:
    whole_body_motion = float(
        creature_axes.get(
            "whole_body_motion_score",
            float(raw_axes.get("locomotion", 0.0))
            * float(creature_axes.get("largest_component_share_final", 0.0)),
        )
    )
    resolved_coherence_class = coherence_class(raw_axes=raw_axes, creature_axes=creature_axes)
    locomotion = float(raw_axes.get("locomotion", 0.0))
    if whole_body_motion >= 5.0e-4 and resolved_coherence_class != "fragmented_pattern":
        return "mobile_body"
    if locomotion >= 5.0e-4:
        return "diffuse_motion"
    return "stationary_body"


def creature_bucket(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> str:
    resolved_coherence_class = coherence_class(raw_axes=raw_axes, creature_axes=creature_axes)
    if resolved_coherence_class == "fragmented_pattern":
        return "diffuse_or_fragmented"
    if _assembly_class(raw_axes) == "multipart" or raw_axes.get("fragmentation", 0.0) >= 2.0:
        return "articulated_multipart"
    resolved_organization_class = organization_class(raw_axes=raw_axes, creature_axes=creature_axes)
    if resolved_organization_class == "enclosing_body":
        return "coherent_enclosing"
    if resolved_organization_class in {"polarized_body", "bilateral_body", "radial_body"}:
        return "coherent_polarized"
    if mobility_class(raw_axes=raw_axes, creature_axes=creature_axes) == "mobile_body":
        return "coherent_mobile"
    return "diffuse_or_fragmented"


def creature_labels(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> dict[str, str]:
    resolved_coherence_class = coherence_class(raw_axes=raw_axes, creature_axes=creature_axes)
    resolved_organization_class = organization_class(raw_axes=raw_axes, creature_axes=creature_axes)
    resolved_mobility_class = mobility_class(raw_axes=raw_axes, creature_axes=creature_axes)
    return {
        "coherence_class": resolved_coherence_class,
        "organization_class": resolved_organization_class,
        "mobility_class": resolved_mobility_class,
        "creature_bucket": creature_bucket(raw_axes=raw_axes, creature_axes=creature_axes),
    }


def body_plan_axes(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> dict[str, float]:
    values = {
        "largest_component_share_final": creature_axes.get("largest_component_share_final"),
        "whole_body_motion_score": creature_axes.get("whole_body_motion_score"),
        "fragmentation": raw_axes.get("fragmentation"),
        "cavity_count": raw_axes.get("cavity_count"),
        "axial_polarity": raw_axes.get("axial_polarity"),
        "center_offset": raw_axes.get("center_offset"),
        "elongation": raw_axes.get("elongation"),
    }
    return {
        axis_id: float(value)
        for axis_id, value in values.items()
        if isinstance(value, (int, float))
    }


def organization_score(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> float:
    resolved_organization_class = organization_class(raw_axes=raw_axes, creature_axes=creature_axes)
    if resolved_organization_class == "enclosing_body":
        return 1.0
    if resolved_organization_class in {"polarized_body", "bilateral_body", "radial_body"}:
        return 0.75
    if coherence_class(raw_axes=raw_axes, creature_axes=creature_axes) == "soft_body":
        return 0.35
    return 0.0


def body_plan_class_shift_score(
    baseline_labels: dict[str, str],
    current_labels: dict[str, str],
) -> float:
    comparisons = [
        float(baseline_labels.get("coherence_class") != current_labels.get("coherence_class")),
        float(
            baseline_labels.get("organization_class")
            != current_labels.get("organization_class")
        ),
        float(baseline_labels.get("mobility_class") != current_labels.get("mobility_class")),
    ]
    return float(mean(comparisons))


def body_plan_error_score(
    baseline_axes: dict[str, float],
    current_axes: dict[str, float],
) -> float | None:
    deltas = [
        abs(float(current_axes[axis_id]) - float(baseline_axes[axis_id]))
        for axis_id in BODY_PLAN_ERROR_AXIS_IDS
        if axis_id in baseline_axes and axis_id in current_axes
    ]
    if not deltas:
        return None
    return float(mean(deltas))
