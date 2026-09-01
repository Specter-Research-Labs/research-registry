from __future__ import annotations

import base64
from statistics import mean, pstdev
from typing import Any

import numpy as np
from scipy import ndimage

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
    "localization_score",
    "extent_stability_score",
    "temporal_individuality_score",
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

TEMPORAL_INDIVIDUALITY_COMPONENT_AXES: tuple[str, ...] = (
    "coherence_min",
    "shape_persistence_score",
    "part_persistence_score",
    "localization_score",
    "extent_stability_score",
)
TEMPORAL_INDIVIDUALITY_MIN_SCORE = 0.70


def temporal_individuality_score(*, creature_axes: dict[str, float]) -> float:
    """Return the weakest temporal persistence measurement on a 0-1 scale."""
    return min(float(creature_axes[axis_id]) for axis_id in TEMPORAL_INDIVIDUALITY_COMPONENT_AXES)


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
                for dy, dx in (
                    (-1, -1), (-1, 0), (-1, 1),
                    (0, -1), (0, 1),
                    (1, -1), (1, 0), (1, 1),
                ):
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


def _largest_component_share(
    mask: np.ndarray,
    *,
    weights: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    if not np.any(mask):
        return 0.0, np.zeros_like(mask, dtype=bool)
    components = _component_masks(mask)
    if not components:
        return 0.0, np.zeros_like(mask, dtype=bool)
    resolved_weights = np.ones_like(mask, dtype=np.float32) if weights is None else weights
    dominant = max(
        components,
        key=lambda component: float(np.sum(resolved_weights[component])),
    )
    total_weight = float(np.sum(resolved_weights[mask]))
    if total_weight <= 0:
        return 0.0, np.zeros_like(mask, dtype=bool)
    return float(np.sum(resolved_weights[dominant])) / total_weight, dominant


def _mass_radius(values: np.ndarray, *, quantile: float) -> float:
    total = float(np.sum(values))
    if total <= 0:
        return 0.0
    ys, xs = np.indices(values.shape, dtype=np.float32)
    center_y = float(np.sum(ys * values) / total)
    center_x = float(np.sum(xs * values) / total)
    distances = np.hypot(xs - center_x, ys - center_y).ravel()
    weights = values.ravel()
    order = np.argsort(distances)
    cumulative = np.cumsum(weights[order])
    index = min(int(np.searchsorted(cumulative, quantile * total)), len(order) - 1)
    return float(distances[order[index]])


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


def _registered_overlap_score(lhs: np.ndarray, rhs: np.ndarray) -> float:
    """Best overlap after removing translation and in-plane rotation."""
    registered_lhs = _recenter_mask(lhs)
    registered_rhs = _recenter_mask(rhs)
    lhs_angle = _principal_axis_angle(registered_lhs)
    rhs_angle = _principal_axis_angle(registered_rhs)
    alignment = lhs_angle - rhs_angle
    return max(
        _overlap_score(
            registered_lhs,
            ndimage.rotate(
                registered_rhs.astype(np.uint8),
                angle,
                reshape=False,
                order=0,
                mode="constant",
                cval=0,
                prefilter=False,
            ).astype(bool),
        )
        for angle in (alignment, alignment + 90.0, alignment + 180.0, alignment + 270.0)
    )


def _principal_axis_angle(mask: np.ndarray) -> float:
    ys, xs = np.nonzero(mask)
    if len(xs) < 2:
        return 0.0
    centered = np.column_stack((xs - np.mean(xs), ys - np.mean(ys)))
    covariance = centered.T @ centered / float(len(xs))
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    return float(np.degrees(np.arctan2(axis[1], axis[0])))


def _persistence_pairs(count: int) -> list[tuple[int, int]]:
    """Cover adjacent behavior and longer lags without an all-pairs expansion."""
    if count < 2:
        return []
    pairs = {(index, index + 1) for index in range(count - 1)}
    for lag in {max(2, count // 4), max(2, count // 2)}:
        if lag < count:
            pairs.update((index, index + lag) for index in range(count - lag))
    pairs.add((0, count - 1))
    return sorted(pairs)


def _fingerprint_snapshot(sample: dict[str, Any], *, specimen_id: str) -> dict[str, Any]:
    terminal = sample.get("terminal")
    if not isinstance(terminal, dict):
        raise SystemExit(f"{specimen_id}: developmental sample missing terminal descriptor")
    fingerprint = _fingerprint_array(terminal, specimen_id=specimen_id)
    occupancy_value = terminal.get("finalOccupancy")
    if not isinstance(occupancy_value, (int, float)):
        raise SystemExit(f"{specimen_id}: missing terminal.finalOccupancy")
    mask = fingerprint > 0
    largest_component_share, dominant_component = _largest_component_share(
        mask,
        weights=fingerprint,
    )
    return {
        "mask": mask,
        "dominant_component": dominant_component,
        "largest_component_share": largest_component_share,
        "mass_radius_95": _mass_radius(fingerprint, quantile=0.95),
        "localization_score": 1.0 - min(max(float(occupancy_value), 0.0), 1.0),
    }


def _sample_snapshot(sample: dict[str, Any], *, specimen_id: str) -> dict[str, Any]:
    terminal = sample.get("terminal")
    if not isinstance(terminal, dict):
        raise SystemExit(f"{specimen_id}: developmental sample missing terminal descriptor")
    raw_axes = extract_terminal_raw_axes_from_descriptors(
        terminal=terminal,
        trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0},
        specimen_id=specimen_id,
    )
    return {
        **_fingerprint_snapshot(sample, specimen_id=specimen_id),
        "raw_axes": raw_axes,
        "symmetry_class": _symmetry_class(raw_axes),
        "arrangement_class": _arrangement_class(raw_axes),
        "enclosure_class": _enclosure_class(raw_axes),
        "assembly_class": _assembly_class(raw_axes),
    }


def _temporal_individuality_axes_from_snapshots(
    snapshots: list[dict[str, Any]],
) -> dict[str, float]:
    coherence_series = [float(snapshot["largest_component_share"]) for snapshot in snapshots]
    persistence_pairs = _persistence_pairs(len(snapshots))
    shape_overlaps = [
        _registered_overlap_score(snapshots[left]["mask"], snapshots[right]["mask"])
        for left, right in persistence_pairs
    ]
    part_overlaps = [
        _registered_overlap_score(
            snapshots[left]["dominant_component"],
            snapshots[right]["dominant_component"],
        )
        for left, right in persistence_pairs
    ]
    radii = [float(snapshot["mass_radius_95"]) for snapshot in snapshots]
    maximum_radius = max(radii)
    axes = {
        "coherence_min": float(min(coherence_series)),
        "shape_persistence_score": float(mean(shape_overlaps)) if shape_overlaps else 1.0,
        "part_persistence_score": float(mean(part_overlaps)) if part_overlaps else 1.0,
        "localization_score": min(
            float(snapshot["localization_score"]) for snapshot in snapshots
        ),
        "extent_stability_score": min(radii) / maximum_radius if maximum_radius > 0 else 0.0,
    }
    return {
        **axes,
        "temporal_individuality_score": temporal_individuality_score(creature_axes=axes),
    }


def derive_temporal_individuality_axes(
    *,
    specimen_id: str,
    trace_samples: list[dict[str, Any]],
) -> dict[str, float]:
    ordered = sorted(trace_samples, key=lambda row: int(row["step"]))
    if not ordered:
        raise SystemExit(f"{specimen_id}: temporal individuality requires replay samples")
    snapshots = [
        _fingerprint_snapshot(sample, specimen_id=specimen_id)
        for sample in ordered
    ]
    return _temporal_individuality_axes_from_snapshots(snapshots)


def derive_creature_signal_axes(
    *,
    specimen_id: str,
    trace_samples: list[dict[str, Any]],
) -> dict[str, float]:
    ordered = sorted(trace_samples, key=lambda row: int(row["step"]))
    if not ordered:
        raise SystemExit(f"{specimen_id}: creature signals require replay samples")
    snapshots = [_sample_snapshot(sample, specimen_id=specimen_id) for sample in ordered]
    individuality_axes = _temporal_individuality_axes_from_snapshots(snapshots)
    coherence_series = [float(snapshot["largest_component_share"]) for snapshot in snapshots]
    fragmentation_series = [
        float(snapshot["raw_axes"].get("fragmentation", 0.0)) for snapshot in snapshots
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
    shape_persistence = individuality_axes["shape_persistence_score"]
    part_persistence = individuality_axes["part_persistence_score"]
    return {
        "largest_component_share_final": float(coherence_series[-1]),
        "coherence_mean": coherence_mean,
        "coherence_min": float(min(coherence_series)),
        "fragmentation_peak": float(fragmentation_peak),
        "fragmentation_variability": float(fragmentation_variability),
        "part_persistence_score": part_persistence,
        "shape_persistence_score": shape_persistence,
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
        "localization_score": individuality_axes["localization_score"],
        "extent_stability_score": individuality_axes["extent_stability_score"],
        "temporal_individuality_score": individuality_axes["temporal_individuality_score"],
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
    if temporal_individuality_class(creature_axes=creature_axes) != "persistent_individual":
        return "diffuse_or_fragmented"
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


def temporal_individuality_class(*, creature_axes: dict[str, float]) -> str:
    score = creature_axes.get("temporal_individuality_score")
    if score is None:
        return "not_temporally_assessed"
    if float(score) >= TEMPORAL_INDIVIDUALITY_MIN_SCORE:
        return "persistent_individual"
    return "transient_or_incoherent"


def creature_labels(
    *,
    raw_axes: dict[str, float],
    creature_axes: dict[str, float],
) -> dict[str, str]:
    resolved_coherence_class = coherence_class(raw_axes=raw_axes, creature_axes=creature_axes)
    resolved_organization_class = organization_class(raw_axes=raw_axes, creature_axes=creature_axes)
    resolved_mobility_class = mobility_class(raw_axes=raw_axes, creature_axes=creature_axes)
    return {
        "individuality_class": temporal_individuality_class(creature_axes=creature_axes),
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
