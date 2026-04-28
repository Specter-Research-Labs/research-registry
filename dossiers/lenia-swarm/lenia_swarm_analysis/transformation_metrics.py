from __future__ import annotations

import base64
import math
from statistics import mean, median
from typing import Any

import numpy as np

TERMINAL_AXIS_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "spread",
        "label": "Spatial spread",
        "source": "terminal.finalGyration",
        "transform": "log1p",
        "positiveMeaning": "larger terminal spatial extent",
    },
    {
        "id": "coverage",
        "label": "Lattice coverage",
        "source": "terminal.finalOccupancy",
        "transform": "identity",
        "positiveMeaning": "occupies more of the field",
    },
    {
        "id": "compactness",
        "label": "Mass compactness",
        "source": "terminal.finalMass / terminal.finalGyration",
        "transform": "log1p",
        "positiveMeaning": "packs more mass into a smaller radius",
    },
    {
        "id": "elongation",
        "label": "Elongation",
        "source": "fingerprint principal-axis ratio",
        "transform": "log1p",
        "positiveMeaning": "is more elongated along one axis",
    },
    {
        "id": "boundary_complexity",
        "label": "Boundary complexity",
        "source": "fingerprint perimeter / sqrt(area)",
        "transform": "log1p",
        "positiveMeaning": "shows a more folded or irregular boundary",
    },
    {
        "id": "cavity_count",
        "label": "Cavity count",
        "source": "fingerprint enclosed background components",
        "transform": "identity",
        "positiveMeaning": "contains more enclosed voids",
    },
    {
        "id": "fragmentation",
        "label": "Fragmentation",
        "source": "fingerprint connected component count",
        "transform": "identity",
        "positiveMeaning": "breaks into more disconnected parts",
    },
    {
        "id": "bilateral_symmetry",
        "label": "Bilateral symmetry",
        "source": "recentered fingerprint mirror similarity around the dominant axis",
        "transform": "identity",
        "positiveMeaning": "shows stronger approximate mirror symmetry",
    },
    {
        "id": "radial_symmetry",
        "label": "Radial symmetry",
        "source": "recentered fingerprint similarity to a radial profile",
        "transform": "identity",
        "positiveMeaning": "shows stronger radial organization",
    },
    {
        "id": "rotational_symmetry",
        "label": "Rotational symmetry",
        "source": "recentered fingerprint similarity to its 180-degree rotation",
        "transform": "identity",
        "positiveMeaning": "shows stronger rotational self-similarity",
    },
    {
        "id": "left_right_asymmetry",
        "label": "Left-right asymmetry",
        "source": "minor-axis mass imbalance in the body frame",
        "transform": "identity",
        "positiveMeaning": "shows stronger lateral asymmetry",
    },
    {
        "id": "center_offset",
        "label": "Center offset",
        "source": "normalized centroid distance from lattice center",
        "transform": "identity",
        "positiveMeaning": "sits farther from the lattice center",
    },
    {
        "id": "axial_polarity",
        "label": "Axial polarity",
        "source": "major-axis mass imbalance in the body frame",
        "transform": "identity",
        "positiveMeaning": "shows a stronger head-tail style polarity",
    },
    {
        "id": "locomotion",
        "label": "Locomotion",
        "source": "trajectory.centerVelocity",
        "transform": "log1p",
        "positiveMeaning": "translates faster across the field",
    },
    {
        "id": "meander",
        "label": "Path meander",
        "source": "trajectory.pathTortuosity",
        "transform": "log1p",
        "positiveMeaning": "takes a more circuitous path",
    },
    {
        "id": "symmetry_focus",
        "label": "Symmetry focus",
        "source": "1 - terminal.angularSymmetry.normalizedEntropy",
        "transform": "identity",
        "positiveMeaning": "shows a stronger dominant angular order",
    },
)

DEVELOPMENTAL_AXIS_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "expansion_gain",
        "label": "Expansion gain",
        "source": "max(coverage_t) - coverage_0",
        "transform": "identity",
        "positiveMeaning": "expands over development",
    },
    {
        "id": "condensation_gain",
        "label": "Condensation gain",
        "source": "compactness_final - compactness_0",
        "transform": "identity",
        "positiveMeaning": "condenses mass into tighter forms",
    },
    {
        "id": "elongation_gain",
        "label": "Elongation gain",
        "source": "max(elongation_t) - elongation_0",
        "transform": "identity",
        "positiveMeaning": "develops stronger axial elongation",
    },
    {
        "id": "folding_gain",
        "label": "Folding gain",
        "source": "max(boundary_complexity_t) - boundary_complexity_0",
        "transform": "identity",
        "positiveMeaning": "develops more folded or irregular boundaries",
    },
    {
        "id": "cavity_birth",
        "label": "Cavity birth",
        "source": "max(cavity_count_t)",
        "transform": "identity",
        "positiveMeaning": "creates enclosed cavities during development",
    },
    {
        "id": "fragmentation_gain",
        "label": "Fragmentation gain",
        "source": "max(fragmentation_t) - fragmentation_0",
        "transform": "identity",
        "positiveMeaning": "splits into more disconnected components",
    },
    {
        "id": "locomotion_onset_step",
        "label": "Locomotion onset step",
        "source": "first sampled step with center_velocity >= 1e-3",
        "transform": "identity",
        "positiveMeaning": "starts translating later in development",
    },
    {
        "id": "meander_final",
        "label": "Final meander",
        "source": "trajectory.pathTortuosity",
        "transform": "log1p",
        "positiveMeaning": "ends with more circuitous movement",
    },
)

TERMINAL_AXIS_IDS = tuple(spec["id"] for spec in TERMINAL_AXIS_SPECS)
DEVELOPMENTAL_AXIS_IDS = tuple(spec["id"] for spec in DEVELOPMENTAL_AXIS_SPECS)
TRANSFORMATION_SIGNATURE_AXIS_IDS = (
    "coverage",
    "compactness",
    "elongation",
    "boundary_complexity",
    "fragmentation",
    "bilateral_symmetry",
    "radial_symmetry",
    "rotational_symmetry",
    "left_right_asymmetry",
    "center_offset",
    "axial_polarity",
    "expansion_gain",
    "condensation_gain",
    "elongation_gain",
    "folding_gain",
    "cavity_birth",
    "fragmentation_gain",
    "locomotion_onset_step",
    "meander_final",
)



def coarse_family_kind(raw: str | dict[str, Any] | None) -> str:
    if isinstance(raw, str):
        value = raw
    elif isinstance(raw, dict):
        value = raw.get("initialConditionFamily")
    else:
        value = None
    if not isinstance(value, str) or not value:
        return "unknown"
    parts = value.split(":")
    if len(parts) >= 3:
        return ":".join(parts[:3])
    return value


def preferred_family_kind(record: dict[str, Any]) -> str:
    canonical_family = record.get("canonicalFamily")
    if isinstance(canonical_family, str) and canonical_family:
        return canonical_family
    geometry_family = record.get("geometryFamily")
    if isinstance(geometry_family, str) and geometry_family:
        return geometry_family
    return coarse_family_kind(record)


def require_float(value: Any, *, name: str, specimen_id: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SystemExit(f"{specimen_id}: missing finite {name}")
    return float(value)


def axis_transform_value(axis_id: str, value: float) -> float:
    if axis_id in {
        "spread",
        "compactness",
        "elongation",
        "boundary_complexity",
        "locomotion",
        "meander",
        "meander_final",
    }:
        return math.log1p(max(value, 0.0))
    return value


def axis_spec(axis_id: str) -> dict[str, str]:
    for spec in TERMINAL_AXIS_SPECS + DEVELOPMENTAL_AXIS_SPECS:
        if spec["id"] == axis_id:
            return spec
    raise KeyError(axis_id)


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        raise SystemExit("cannot compute quantiles for an empty series")
    count = len(ordered)

    def pick(position: float) -> float:
        index = min(count - 1, max(0, round((count - 1) * position)))
        return float(ordered[index])

    return {
        "min": float(ordered[0]),
        "p25": pick(0.25),
        "median": pick(0.5),
        "p75": pick(0.75),
        "max": float(ordered[-1]),
        "mean": float(mean(ordered)),
    }


def robust_center_scale(values: list[float]) -> tuple[float, float]:
    center = float(median(values))
    deviations = [abs(value - center) for value in values]
    mad = float(median(deviations)) * 1.4826
    if mad > 0:
        return center, mad
    if len(values) <= 1:
        return center, 1.0
    mean_value = float(mean(values))
    variance = float(sum((value - mean_value) ** 2 for value in values) / len(values))
    scale = math.sqrt(variance)
    return center, scale if scale > 0 else 1.0


def zscore(value: float, *, center: float, scale: float) -> float:
    return (value - center) / max(scale, 1.0e-9)


def _component_cells(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    occupied_visited = np.zeros((height, width), dtype=bool)
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if occupied_visited[y, x] or not bool(mask[y, x]):
                continue
            frontier = [(y, x)]
            occupied_visited[y, x] = True
            component: list[tuple[int, int]] = []
            while frontier:
                cy, cx = frontier.pop()
                component.append((cy, cx))
                for dy, dx in neighbors:
                    ny = cy + dy
                    nx = cx + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and bool(mask[ny, nx])
                        and not occupied_visited[ny, nx]
                    ):
                        occupied_visited[ny, nx] = True
                        frontier.append((ny, nx))
            components.append(component)
    return components


def _hole_count(mask: np.ndarray, *, min_size: int) -> int:
    height, width = mask.shape
    background_visited = np.zeros((height, width), dtype=bool)
    neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    hole_count = 0
    background = ~mask
    for y in range(height):
        for x in range(width):
            if background_visited[y, x] or not bool(background[y, x]):
                continue
            frontier = [(y, x)]
            background_visited[y, x] = True
            touches_border = y == 0 or x == 0 or y == height - 1 or x == width - 1
            size = 0
            while frontier:
                cy, cx = frontier.pop()
                size += 1
                for dy, dx in neighbors:
                    ny = cy + dy
                    nx = cx + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and bool(background[ny, nx])
                        and not background_visited[ny, nx]
                    ):
                        background_visited[ny, nx] = True
                        if ny == 0 or nx == 0 or ny == height - 1 or nx == width - 1:
                            touches_border = True
                        frontier.append((ny, nx))
            if not touches_border and size >= min_size:
                hole_count += 1
    return hole_count


def _shift_image(image: np.ndarray, *, shift_x: int, shift_y: int) -> np.ndarray:
    height, width = image.shape
    shifted = np.zeros_like(image, dtype=np.float64)
    src_x0 = max(0, -shift_x)
    src_x1 = min(width, width - shift_x) if shift_x >= 0 else width
    dst_x0 = max(0, shift_x)
    dst_x1 = min(width, width + shift_x) if shift_x <= 0 else width
    src_y0 = max(0, -shift_y)
    src_y1 = min(height, height - shift_y) if shift_y >= 0 else height
    dst_y0 = max(0, shift_y)
    dst_y1 = min(height, height + shift_y) if shift_y <= 0 else height
    if src_x0 >= src_x1 or src_y0 >= src_y1:
        return shifted
    shifted[dst_y0:dst_y1, dst_x0:dst_x1] = image[src_y0:src_y1, src_x0:src_x1]
    return shifted


def _similarity_score(lhs: np.ndarray, rhs: np.ndarray) -> float:
    lhs_f = lhs.astype(np.float64, copy=False)
    rhs_f = rhs.astype(np.float64, copy=False)
    total = float(np.sum(np.abs(lhs_f)) + np.sum(np.abs(rhs_f)))
    if total <= 1.0e-9:
        return 1.0
    score = 1.0 - float(np.sum(np.abs(lhs_f - rhs_f))) / total
    return max(0.0, min(1.0, score))


def _radial_model(image: np.ndarray) -> np.ndarray:
    height, width = image.shape
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    ys, xs = np.indices(image.shape, dtype=np.float64)
    radii = np.rint(np.hypot(xs - center_x, ys - center_y)).astype(np.int32)
    flat_radii = radii.ravel()
    flat_values = image.astype(np.float64, copy=False).ravel()
    max_radius = int(np.max(flat_radii)) if flat_radii.size else 0
    sums = np.bincount(flat_radii, weights=flat_values, minlength=max_radius + 1)
    counts = np.bincount(flat_radii, minlength=max_radius + 1)
    means = np.divide(
        sums,
        np.maximum(counts, 1),
        out=np.zeros_like(sums, dtype=np.float64),
        where=counts > 0,
    )
    return means[radii]


def _aligned_image(
    image: np.ndarray,
    *,
    xs: np.ndarray,
    ys: np.ndarray,
    weights: np.ndarray,
    x_center: float,
    y_center: float,
    major_vector: np.ndarray,
    minor_vector: np.ndarray,
) -> np.ndarray:
    height, width = image.shape
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    dx = xs.astype(np.float64) - x_center
    dy = ys.astype(np.float64) - y_center
    u = dx * float(major_vector[0]) + dy * float(major_vector[1])
    v = dx * float(minor_vector[0]) + dy * float(minor_vector[1])
    aligned_x = np.rint(center_x + u).astype(np.int32)
    aligned_y = np.rint(center_y + v).astype(np.int32)
    valid = (
        (aligned_x >= 0)
        & (aligned_x < width)
        & (aligned_y >= 0)
        & (aligned_y < height)
    )
    aligned = np.zeros_like(image, dtype=np.float64)
    np.add.at(aligned, (aligned_y[valid], aligned_x[valid]), weights[valid])
    return aligned


def fingerprint_metrics(fingerprint: np.ndarray) -> dict[str, float]:
    mask = fingerprint > 0
    if not np.any(mask):
        return {
            "elongation": 1.0,
            "boundaryComplexity": 0.0,
            "componentCount": 0.0,
            "cavityCount": 0.0,
            "bilateralSymmetry": 0.0,
            "radialSymmetry": 0.0,
            "rotationalSymmetry": 0.0,
            "leftRightAsymmetry": 0.0,
            "centerOffset": 0.0,
            "axialPolarity": 0.0,
        }
    raw_area = int(np.count_nonzero(mask))
    min_component_size = max(2, int(round(raw_area * 0.02)))
    filtered_mask = np.zeros_like(mask, dtype=bool)
    retained_components = 0
    for component in _component_cells(mask):
        if len(component) < min_component_size:
            continue
        retained_components += 1
        for y, x in component:
            filtered_mask[y, x] = True
    if not np.any(filtered_mask):
        filtered_mask = mask
        retained_components = len(_component_cells(mask))

    ys, xs = np.nonzero(filtered_mask)
    weights = fingerprint[ys, xs].astype(np.float64)
    total_weight = float(np.sum(weights))
    x_center = float(np.sum(xs * weights) / total_weight)
    y_center = float(np.sum(ys * weights) / total_weight)
    dx = xs.astype(np.float64) - x_center
    dy = ys.astype(np.float64) - y_center
    covariance = np.asarray(
        [
            [np.sum(weights * dx * dx), np.sum(weights * dx * dy)],
            [np.sum(weights * dx * dy), np.sum(weights * dy * dy)],
        ],
        dtype=np.float64,
    ) / total_weight
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    largest = float(max(eigenvalues[-1], 0.0))
    smallest = float(max(eigenvalues[0], 0.0))
    elongation = math.sqrt((largest + 1.0e-9) / (smallest + 1.0e-9))
    major_vector = eigenvectors[:, 1]
    minor_vector = eigenvectors[:, 0]

    up = np.pad(filtered_mask[1:, :], ((0, 1), (0, 0)), constant_values=False)
    down = np.pad(filtered_mask[:-1, :], ((1, 0), (0, 0)), constant_values=False)
    left = np.pad(filtered_mask[:, 1:], ((0, 0), (0, 1)), constant_values=False)
    right = np.pad(filtered_mask[:, :-1], ((0, 0), (1, 0)), constant_values=False)
    boundary = filtered_mask & ~(up & down & left & right)
    perimeter = float(np.count_nonzero(boundary))
    area = float(np.count_nonzero(filtered_mask))
    boundary_complexity = perimeter / math.sqrt(area)
    cavity_count = _hole_count(filtered_mask, min_size=min_component_size)
    weighted = np.zeros_like(fingerprint, dtype=np.float64)
    weighted[ys, xs] = weights
    image_center_x = (fingerprint.shape[1] - 1) / 2.0
    image_center_y = (fingerprint.shape[0] - 1) / 2.0
    recentered = _shift_image(
        weighted,
        shift_x=int(round(image_center_x - x_center)),
        shift_y=int(round(image_center_y - y_center)),
    )
    aligned = _aligned_image(
        weighted,
        xs=xs,
        ys=ys,
        weights=weights,
        x_center=x_center,
        y_center=y_center,
        major_vector=major_vector,
        minor_vector=minor_vector,
    )
    bilateral_symmetry = _similarity_score(aligned, np.flipud(aligned))
    rotational_symmetry = _similarity_score(recentered, np.rot90(recentered, 2))
    radial_symmetry = _similarity_score(recentered, _radial_model(recentered))
    center_offset = math.hypot(x_center - image_center_x, y_center - image_center_y)
    max_offset = math.hypot(image_center_x, image_center_y)
    center_offset /= max(max_offset, 1.0e-9)
    major_projection = dx * float(major_vector[0]) + dy * float(major_vector[1])
    minor_projection = dx * float(minor_vector[0]) + dy * float(minor_vector[1])
    positive_major = float(np.sum(weights[major_projection >= 0.0]))
    negative_major = float(np.sum(weights[major_projection < 0.0]))
    positive_minor = float(np.sum(weights[minor_projection >= 0.0]))
    negative_minor = float(np.sum(weights[minor_projection < 0.0]))
    axial_polarity = abs(positive_major - negative_major) / total_weight
    left_right_asymmetry = abs(positive_minor - negative_minor) / total_weight
    return {
        "elongation": elongation,
        "boundaryComplexity": boundary_complexity,
        "componentCount": float(retained_components),
        "cavityCount": float(cavity_count),
        "bilateralSymmetry": bilateral_symmetry,
        "radialSymmetry": radial_symmetry,
        "rotationalSymmetry": rotational_symmetry,
        "leftRightAsymmetry": left_right_asymmetry,
        "centerOffset": center_offset,
        "axialPolarity": axial_polarity,
    }


def extract_terminal_raw_axes_from_descriptors(
    *,
    terminal: dict[str, Any],
    trajectory: dict[str, Any],
    specimen_id: str,
) -> dict[str, float]:
    angular = terminal.get("angularSymmetry")
    if not isinstance(angular, dict):
        raise SystemExit(f"{specimen_id}: missing angular symmetry descriptor")
    gyration = require_float(
        terminal.get("finalGyration"),
        name="terminal.finalGyration",
        specimen_id=specimen_id,
    )
    occupancy = require_float(
        terminal.get("finalOccupancy"),
        name="terminal.finalOccupancy",
        specimen_id=specimen_id,
    )
    mass = require_float(
        terminal.get("finalMass"),
        name="terminal.finalMass",
        specimen_id=specimen_id,
    )
    center_velocity = require_float(
        trajectory.get("centerVelocity"),
        name="trajectory.centerVelocity",
        specimen_id=specimen_id,
    )
    path_tortuosity = require_float(
        trajectory.get("pathTortuosity"),
        name="trajectory.pathTortuosity",
        specimen_id=specimen_id,
    )
    symmetry_entropy = require_float(
        angular.get("normalizedEntropy"),
        name="terminal.angularSymmetry.normalizedEntropy",
        specimen_id=specimen_id,
    )
    fingerprint_resolution = int(
        require_float(
            terminal.get("fingerprintResolution"),
            name="terminal.fingerprintResolution",
            specimen_id=specimen_id,
        )
    )
    fingerprint_payload = terminal.get("fingerprintU8")
    if isinstance(fingerprint_payload, list):
        if len(fingerprint_payload) != fingerprint_resolution * fingerprint_resolution or any(
            not isinstance(value, int) for value in fingerprint_payload
        ):
            raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
        fingerprint = np.asarray(fingerprint_payload, dtype=np.float32)
    elif isinstance(fingerprint_payload, str):
        fingerprint = np.frombuffer(base64.b64decode(fingerprint_payload), dtype=np.uint8).astype(
            np.float32
        )
        if fingerprint.size != fingerprint_resolution * fingerprint_resolution:
            raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
    else:
        raise SystemExit(f"{specimen_id}: invalid fingerprintU8 payload")
    metrics = fingerprint_metrics(
        fingerprint.reshape(
            fingerprint_resolution, fingerprint_resolution
        )
    )
    return {
        "spread": gyration,
        "coverage": occupancy,
        "compactness": mass / max(gyration, 1.0e-6),
        "elongation": metrics["elongation"],
        "boundary_complexity": metrics["boundaryComplexity"],
        "cavity_count": metrics["cavityCount"],
        "fragmentation": metrics["componentCount"],
        "bilateral_symmetry": metrics["bilateralSymmetry"],
        "radial_symmetry": metrics["radialSymmetry"],
        "rotational_symmetry": metrics["rotationalSymmetry"],
        "left_right_asymmetry": metrics["leftRightAsymmetry"],
        "center_offset": metrics["centerOffset"],
        "axial_polarity": metrics["axialPolarity"],
        "locomotion": center_velocity,
        "meander": path_tortuosity,
        "symmetry_focus": 1.0 - symmetry_entropy,
    }


def extract_terminal_raw_axes_from_row(row: dict[str, Any]) -> dict[str, float]:
    specimen_id = str(row.get("specimenId", "unknown"))
    terminal = row.get("terminal")
    trajectory = row.get("trajectory")
    if not isinstance(terminal, dict):
        raise SystemExit(f"{specimen_id}: missing terminal descriptor")
    if not isinstance(trajectory, dict):
        raise SystemExit(f"{specimen_id}: missing trajectory descriptor")
    return extract_terminal_raw_axes_from_descriptors(
        terminal=terminal,
        trajectory=trajectory,
        specimen_id=specimen_id,
    )


def transform_axes(raw_axes: dict[str, float]) -> dict[str, float]:
    return {axis_id: axis_transform_value(axis_id, value) for axis_id, value in raw_axes.items()}


def compute_center_velocity_trace(samples: list[dict[str, Any]]) -> list[float]:
    if not samples:
        return []
    velocities = [0.0]
    for previous, current in zip(samples, samples[1:], strict=False):
        px = require_float(previous.get("centerX"), name="centerX", specimen_id="trace")
        py = require_float(previous.get("centerY"), name="centerY", specimen_id="trace")
        cx = require_float(current.get("centerX"), name="centerX", specimen_id="trace")
        cy = require_float(current.get("centerY"), name="centerY", specimen_id="trace")
        step_prev = int(require_float(previous.get("step"), name="step", specimen_id="trace"))
        step_curr = int(require_float(current.get("step"), name="step", specimen_id="trace"))
        delta_step = max(step_curr - step_prev, 1)
        displacement = math.hypot(cx - px, cy - py)
        velocities.append(displacement / float(delta_step))
    return velocities


def developmental_trace_from_samples(
    *,
    specimen_id: str,
    trace_samples: list[dict[str, Any]],
    meander_final: float,
) -> dict[str, Any]:
    if not trace_samples:
        raise SystemExit(f"{specimen_id}: developmental trace has no samples")
    ordered = sorted(trace_samples, key=lambda row: int(row["step"]))
    steps = [
        int(require_float(row.get("step"), name="step", specimen_id=specimen_id))
        for row in ordered
    ]
    center_velocity_trace = compute_center_velocity_trace(ordered)
    trace_axes: dict[str, list[float]] = {
        "coverage": [],
        "spread": [],
        "compactness": [],
        "elongation": [],
        "boundary_complexity": [],
        "cavity_count": [],
        "fragmentation": [],
        "center_velocity": center_velocity_trace,
    }
    for row in ordered:
        terminal = row.get("terminal")
        if not isinstance(terminal, dict):
            raise SystemExit(f"{specimen_id}: trace row missing terminal descriptor")
        terminal_axes = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal,
            trajectory={"centerVelocity": 0.0, "pathTortuosity": meander_final},
            specimen_id=specimen_id,
        )
        trace_axes["coverage"].append(terminal_axes["coverage"])
        trace_axes["spread"].append(terminal_axes["spread"])
        trace_axes["compactness"].append(terminal_axes["compactness"])
        trace_axes["elongation"].append(terminal_axes["elongation"])
        trace_axes["boundary_complexity"].append(terminal_axes["boundary_complexity"])
        trace_axes["cavity_count"].append(terminal_axes["cavity_count"])
        trace_axes["fragmentation"].append(terminal_axes["fragmentation"])
    locomotion_onset_step = next(
        (steps[index] for index, value in enumerate(center_velocity_trace) if value >= 1.0e-3),
        None,
    )
    developmental_axes = {
        "expansion_gain": max(trace_axes["coverage"]) - trace_axes["coverage"][0],
        "condensation_gain": trace_axes["compactness"][-1] - trace_axes["compactness"][0],
        "elongation_gain": max(trace_axes["elongation"]) - trace_axes["elongation"][0],
        "folding_gain": (
            max(trace_axes["boundary_complexity"])
            - trace_axes["boundary_complexity"][0]
        ),
        "cavity_birth": max(trace_axes["cavity_count"]),
        "fragmentation_gain": max(trace_axes["fragmentation"]) - trace_axes["fragmentation"][0],
        "locomotion_onset_step": (
            float(locomotion_onset_step) if locomotion_onset_step is not None else None
        ),
        "meander_final": meander_final,
    }
    transformed_developmental_axes = {
        axis_id: (
            axis_transform_value(axis_id, float(value))
            if value is not None
            else None
        )
        for axis_id, value in developmental_axes.items()
    }
    return {
        "steps": steps,
        "traceAxes": trace_axes,
        "developmentalAxes": developmental_axes,
        "transformedDevelopmentalAxes": transformed_developmental_axes,
    }
