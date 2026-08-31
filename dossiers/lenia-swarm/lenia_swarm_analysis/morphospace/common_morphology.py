from __future__ import annotations

import base64
import csv
import heapq
import itertools
import json
import math
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import robust_center_scale, zscore

from .ingest_dryad_fish import SOURCE_ID as DRYAD_FISH_SOURCE_ID
from .ingest_embryomaker import (
    OBSERVATION_KIND as EMBRYOMAKER_OBSERVATION_KIND,
)
from .ingest_embryomaker import (
    SOURCE_ID as EMBRYOMAKER_SOURCE_ID,
)
from .ingest_embryomaker import (
    load_embryomaker_node_points,
)
from .warehouse import (
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
    json_text,
    mark_derived_artifact_state,
    normalize_optional_timestamp,
    register_context,
    register_feature_calibration,
    replace_feature_axes,
    stable_id,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_specimen_feature_vectors,
    validate_dense_feature_space,
)

LENIA_SOURCE_ID = "lenia_swarm"
FEATURE_SPACE_ID = "common_morphology_v3_balanced_distribution"
FEATURE_SPACE_LABEL = "Common point-distribution morphology"
OBSERVATION_KIND = "common_point_cloud_morphology"
_EPSILON = 1.0e-6
_MAX_SYMMETRY_POINTS = 512
_RASTER_GRID_SIZE = 32
_LENIA_FETCH_BATCH_SIZE = 8192
_WRITE_BATCH_SIZE = 8192
_MAX_CALIBRATION_ROWS_PER_SOURCE = 8192
_LANDMARK_COLUMN_RE = re.compile(r"^LM\s+(\d+)_(X|Y|Z)$")

POINT_CLOUD_AXIS_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "elongation",
        "label": "Principal elongation",
        "positiveMeaning": "points lie much farther along the main axis than across it",
        "formula": "sqrt((lambda_1 + eps) / (lambda_2 + eps))",
    },
    {
        "id": "anisotropy",
        "label": "Principal anisotropy",
        "positiveMeaning": "one principal direction explains most of the shape variance",
        "formula": "(lambda_1 - lambda_2) / (lambda_1 + lambda_2 + eps)",
    },
    {
        "id": "compactness",
        "label": "Radial compactness",
        "positiveMeaning": "points sit closer to the centroid instead of only on the rim",
        "formula": "1 - weighted_mean(radius / max_radius)",
    },
    {
        "id": "polarity",
        "label": "Axial polarity",
        "positiveMeaning": "more mass or landmarks sit on one end of the main axis",
        "formula": "abs(weight on +PC1 - weight on -PC1) / total_weight",
    },
    {
        "id": "bilateral_symmetry",
        "label": "Principal reflection symmetry",
        "positiveMeaning": "the shape matches its reflection across the principal axis",
        "formula": "1 - mean nearest reflected distance / diameter",
    },
    {
        "id": "radial_symmetry",
        "label": "Radial evenness",
        "positiveMeaning": "points sit at similar distances from the centroid",
        "formula": "1 / (1 + coefficient_of_variation(radius))",
    },
    {
        "id": "component_count",
        "label": "Raster component count",
        "positiveMeaning": "the occupied footprint splits into multiple disconnected parts",
        "formula": "count_8_connected_components(rasterized_projected_shape)",
        "axisFamily": "rasterized_shape_anatomy",
    },
    {
        "id": "largest_component_fraction",
        "label": "Largest component fraction",
        "positiveMeaning": "most occupied mass lies in one connected body",
        "formula": "mass(largest_component) / total_raster_mass",
        "axisFamily": "rasterized_shape_anatomy",
    },
    {
        "id": "largest_component_anisotropy",
        "label": "Largest component anisotropy",
        "positiveMeaning": "the dominant body is stretched along one principal direction",
        "formula": "(lambda_1 - lambda_2) / (lambda_1 + lambda_2 + eps)",
        "axisFamily": "rasterized_shape_anatomy",
    },
    {
        "id": "coverage",
        "label": "Raster coverage",
        "positiveMeaning": "the projected shape occupies more of the normalized footprint window",
        "formula": "occupied_raster_cells / raster_cell_count",
        "axisFamily": "rasterized_shape_anatomy",
    },
    {
        "id": "boundary_complexity",
        "label": "Boundary complexity",
        "positiveMeaning": "the occupied footprint has a longer exposed boundary for its area",
        "formula": "exposed_4_neighbor_edges / (4 * sqrt(occupied_raster_cells) + eps)",
        "axisFamily": "rasterized_shape_anatomy",
    },
    {
        "id": "enclosure",
        "label": "Enclosure score",
        "positiveMeaning": "the projected footprint surrounds interior empty regions",
        "formula": "min(interior_background_component_count, 4) / 4",
        "axisFamily": "rasterized_shape_anatomy",
    },
)
CROSS_SOURCE_AXIS_IDS = (
    "elongation",
    "anisotropy",
    "compactness",
    "polarity",
    "bilateral_symmetry",
    "radial_symmetry",
)
AXIS_SPECS = tuple(spec for spec in POINT_CLOUD_AXIS_SPECS if spec["id"] in CROSS_SOURCE_AXIS_IDS)
AXIS_IDS = tuple(str(spec["id"]) for spec in AXIS_SPECS)


@dataclass(frozen=True)
class _CommonMorphologyRow:
    observation_id: str
    specimen_id: str
    study_id: str
    source_id: str
    context_id: str
    observed_at: Any
    source_ref: str | None
    values: dict[str, float]
    payload_json: dict[str, Any]


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: expected finite float, got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}: expected finite float, got {value!r}")
    return result


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _weighted_nearest_reflection_score(
    projected_points: np.ndarray,
    weights: np.ndarray,
) -> float:
    if projected_points.shape[0] < 2:
        return 1.0
    points = projected_points
    point_weights = weights
    if points.shape[0] > _MAX_SYMMETRY_POINTS:
        indices = np.linspace(
            0,
            points.shape[0] - 1,
            num=_MAX_SYMMETRY_POINTS,
            dtype=np.int64,
        )
        points = points[indices]
        point_weights = point_weights[indices]

    reflected = points.copy()
    reflected[:, 1] *= -1.0
    nearest: list[np.ndarray] = []
    chunk_size = 256
    for start in range(0, points.shape[0], chunk_size):
        chunk = points[start : start + chunk_size]
        deltas = chunk[:, None, :] - reflected[None, :, :]
        distances_sq = np.sum(deltas * deltas, axis=2)
        nearest.append(np.sqrt(np.min(distances_sq, axis=1)))
    nearest_distances = np.concatenate(nearest)
    mean_distance = float(np.average(nearest_distances, weights=point_weights))
    return _clamp_unit(1.0 - mean_distance / 2.0)


def _adaptive_splat_radius(cell_points: np.ndarray) -> int:
    if cell_points.shape[0] < 2:
        return 1
    sample = cell_points
    if sample.shape[0] > _MAX_SYMMETRY_POINTS:
        indices = np.linspace(
            0,
            sample.shape[0] - 1,
            num=_MAX_SYMMETRY_POINTS,
            dtype=np.int64,
        )
        sample = sample[indices]
    deltas = sample[:, None, :] - sample[None, :, :]
    distances = np.sqrt(np.sum(deltas * deltas, axis=2))
    np.fill_diagonal(distances, np.inf)
    finite_nearest = np.min(distances, axis=1)
    finite_nearest = finite_nearest[np.isfinite(finite_nearest)]
    if finite_nearest.size == 0:
        return 1
    median_nearest = float(np.median(finite_nearest))
    return int(max(1, min(4, math.ceil(0.6 * median_nearest))))


def _convex_hull(points: np.ndarray) -> list[tuple[float, float]]:
    unique_points = sorted({(float(point[0]), float(point[1])) for point in points})
    if len(unique_points) <= 1:
        return unique_points

    def cross(
        origin: tuple[float, float],
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (
            right[0] - origin[0]
        )

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _point_in_polygon(
    *,
    x: float,
    y: float,
    polygon: list[tuple[float, float]],
) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x_i, y_i = current
        x_j, y_j = previous
        if (y_i > y) != (y_j > y):
            x_intersect = (x_j - x_i) * (y - y_i) / (y_j - y_i + _EPSILON) + x_i
            if x <= x_intersect:
                inside = not inside
        previous = current
    return inside


def _fill_convex_hull(
    raster: np.ndarray,
    *,
    cell_points: np.ndarray,
    weights: np.ndarray,
) -> None:
    hull = _convex_hull(cell_points)
    if len(hull) < 3:
        return
    fill_value = float(np.mean(weights))
    if fill_value <= 0.0:
        fill_value = 1.0
    y_min = max(0, int(math.floor(min(point[1] for point in hull))))
    y_max = min(_RASTER_GRID_SIZE - 1, int(math.ceil(max(point[1] for point in hull))))
    x_min = max(0, int(math.floor(min(point[0] for point in hull))))
    x_max = min(_RASTER_GRID_SIZE - 1, int(math.ceil(max(point[0] for point in hull))))
    for y in range(y_min, y_max + 1):
        for x in range(x_min, x_max + 1):
            if _point_in_polygon(x=float(x), y=float(y), polygon=hull):
                raster[y, x] = max(raster[y, x], fill_value)


def _rasterized_projected_shape(
    projected_points: np.ndarray,
    weights: np.ndarray,
    *,
    fill_convex_hull: bool,
) -> np.ndarray:
    cells = (projected_points + 1.0) * (0.5 * float(_RASTER_GRID_SIZE - 1))
    cells = np.clip(cells, 0.0, float(_RASTER_GRID_SIZE - 1))
    radius = _adaptive_splat_radius(cells)
    raster = np.zeros((_RASTER_GRID_SIZE, _RASTER_GRID_SIZE), dtype=np.float64)
    for point, weight in zip(cells, weights, strict=True):
        center_x = int(round(float(point[0])))
        center_y = int(round(float(point[1])))
        y_min = max(0, center_y - radius)
        y_max = min(_RASTER_GRID_SIZE - 1, center_y + radius)
        x_min = max(0, center_x - radius)
        x_max = min(_RASTER_GRID_SIZE - 1, center_x + radius)
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                dx = x - center_x
                dy = y - center_y
                if (dx * dx) + (dy * dy) <= radius * radius:
                    raster[y, x] += float(weight)
    if fill_convex_hull:
        _fill_convex_hull(raster, cell_points=cells, weights=weights)
    return raster


def _component_cells(mask: np.ndarray) -> list[np.ndarray]:
    visited = np.zeros(mask.shape, dtype=bool)
    components: list[np.ndarray] = []
    height, width = mask.shape
    neighbor_offsets = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )
    for start_y, start_x in np.argwhere(mask):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        cells: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            cells.append((y, x))
            for dy, dx in neighbor_offsets:
                next_y = y + dy
                next_x = x + dx
                if (
                    next_y < 0
                    or next_x < 0
                    or next_y >= height
                    or next_x >= width
                    or visited[next_y, next_x]
                    or not mask[next_y, next_x]
                ):
                    continue
                visited[next_y, next_x] = True
                stack.append((next_y, next_x))
        components.append(np.asarray(cells, dtype=np.int64))
    return components


def _interior_background_component_count(mask: np.ndarray) -> int:
    background = ~mask
    visited = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    count = 0
    neighbor_offsets = ((-1, 0), (0, -1), (0, 1), (1, 0))
    for start_y, start_x in np.argwhere(background):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        touches_border = False
        while stack:
            y, x = stack.pop()
            touches_border = touches_border or y == 0 or x == 0 or y == height - 1 or x == width - 1
            for dy, dx in neighbor_offsets:
                next_y = y + dy
                next_x = x + dx
                if (
                    next_y < 0
                    or next_x < 0
                    or next_y >= height
                    or next_x >= width
                    or visited[next_y, next_x]
                    or not background[next_y, next_x]
                ):
                    continue
                visited[next_y, next_x] = True
                stack.append((next_y, next_x))
        if not touches_border:
            count += 1
    return count


def _boundary_edge_count(mask: np.ndarray) -> int:
    height, width = mask.shape
    count = 0
    for y, x in np.argwhere(mask):
        for dy, dx in ((-1, 0), (0, -1), (0, 1), (1, 0)):
            next_y = int(y) + dy
            next_x = int(x) + dx
            if (
                next_y < 0
                or next_x < 0
                or next_y >= height
                or next_x >= width
                or not mask[next_y, next_x]
            ):
                count += 1
    return count


def _weighted_cell_anisotropy(cells: np.ndarray, raster: np.ndarray) -> float:
    if cells.shape[0] < 2:
        return 0.0
    coordinates = np.column_stack([cells[:, 1], cells[:, 0]]).astype(np.float64)
    weights = raster[cells[:, 0], cells[:, 1]].astype(np.float64)
    total_weight = float(np.sum(weights))
    if total_weight <= _EPSILON:
        return 0.0
    centroid = np.average(coordinates, axis=0, weights=weights)
    centered = coordinates - centroid
    covariance = (centered * weights[:, None]).T @ centered / total_weight
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    lambda_1 = float(eigenvalues[-1])
    lambda_2 = float(eigenvalues[-2]) if eigenvalues.size > 1 else 0.0
    return _clamp_unit((lambda_1 - lambda_2) / (lambda_1 + lambda_2 + _EPSILON))


def _raster_shape_features(
    projected_points: np.ndarray,
    weights: np.ndarray,
    *,
    fill_convex_hull: bool,
) -> dict[str, float]:
    raster = _rasterized_projected_shape(
        projected_points,
        weights,
        fill_convex_hull=fill_convex_hull,
    )
    mask = raster > 0.0
    occupied_count = int(np.count_nonzero(mask))
    if occupied_count == 0:
        return {
            "component_count": 0.0,
            "largest_component_fraction": 0.0,
            "largest_component_anisotropy": 0.0,
            "coverage": 0.0,
            "boundary_complexity": 0.0,
            "enclosure": 0.0,
        }

    components = _component_cells(mask)
    component_masses = [
        float(np.sum(raster[component[:, 0], component[:, 1]])) for component in components
    ]
    largest_index = int(np.argmax(component_masses))
    largest_component = components[largest_index]
    total_mass = float(np.sum(component_masses))
    boundary_edges = _boundary_edge_count(mask)
    hole_count = _interior_background_component_count(mask)
    return {
        "component_count": float(len(components)),
        "largest_component_fraction": component_masses[largest_index] / max(total_mass, _EPSILON),
        "largest_component_anisotropy": _weighted_cell_anisotropy(largest_component, raster),
        "coverage": occupied_count / float(_RASTER_GRID_SIZE * _RASTER_GRID_SIZE),
        "boundary_complexity": boundary_edges / (4.0 * math.sqrt(occupied_count) + _EPSILON),
        "enclosure": _clamp_unit(float(hole_count) / 4.0),
    }


def point_cloud_shape_features(
    points: np.ndarray,
    *,
    weights: np.ndarray | None = None,
) -> dict[str, float]:
    coordinates = np.asarray(points, dtype=np.float64)
    if coordinates.ndim != 2 or coordinates.shape[0] < 2:
        raise ValueError("point cloud must be a two-dimensional array with at least two points")
    has_explicit_weights = weights is not None
    if weights is None:
        point_weights = np.ones(coordinates.shape[0], dtype=np.float64)
    else:
        point_weights = np.asarray(weights, dtype=np.float64)
        if point_weights.shape != (coordinates.shape[0],):
            raise ValueError("weights must have one value per point")

    valid = (
        np.all(np.isfinite(coordinates), axis=1)
        & np.isfinite(point_weights)
        & (point_weights > 0.0)
    )
    coordinates = coordinates[valid]
    point_weights = point_weights[valid]
    if coordinates.shape[0] < 2:
        raise ValueError("point cloud must have at least two finite positive-weight points")
    fill_sparse_landmark_footprint = not has_explicit_weights and coordinates.shape[0] <= 64

    total_weight = float(np.sum(point_weights))
    centroid = np.average(coordinates, axis=0, weights=point_weights)
    centered = coordinates - centroid
    radii = np.linalg.norm(centered, axis=1)
    max_radius = float(np.max(radii))
    if max_radius <= _EPSILON:
        return {
            "elongation": 1.0,
            "anisotropy": 0.0,
            "compactness": 1.0,
            "polarity": 0.0,
            "bilateral_symmetry": 1.0,
            "radial_symmetry": 1.0,
            "component_count": 1.0,
            "largest_component_fraction": 1.0,
            "largest_component_anisotropy": 0.0,
            "coverage": 1.0 / float(_RASTER_GRID_SIZE * _RASTER_GRID_SIZE),
            "boundary_complexity": 1.0,
            "enclosure": 0.0,
        }

    scaled = centered / max_radius
    scaled_radii = radii / max_radius
    covariance = (scaled * point_weights[:, None]).T @ scaled / total_weight
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    ordered_values = np.maximum(eigenvalues[order], 0.0)
    ordered_vectors = eigenvectors[:, order]
    lambda_1 = float(ordered_values[0])
    lambda_2 = float(ordered_values[1]) if ordered_values.shape[0] > 1 else 0.0
    elongation = math.sqrt((lambda_1 + _EPSILON) / (lambda_2 + _EPSILON))
    anisotropy = (lambda_1 - lambda_2) / (lambda_1 + lambda_2 + _EPSILON)
    compactness = _clamp_unit(1.0 - float(np.average(scaled_radii, weights=point_weights)))

    projected = scaled @ ordered_vectors[:, : min(2, ordered_vectors.shape[1])]
    if projected.shape[1] == 1:
        projected = np.column_stack([projected[:, 0], np.zeros(projected.shape[0])])
    major_projection = projected[:, 0]
    positive = float(np.sum(point_weights[major_projection >= 0.0]))
    negative = float(np.sum(point_weights[major_projection < 0.0]))
    polarity = abs(positive - negative) / total_weight

    mean_radius = float(np.average(scaled_radii, weights=point_weights))
    radius_variance = float(np.average((scaled_radii - mean_radius) ** 2, weights=point_weights))
    radius_cv = math.sqrt(radius_variance) / max(mean_radius, _EPSILON)

    return {
        "elongation": elongation,
        "anisotropy": _clamp_unit(anisotropy),
        "compactness": compactness,
        "polarity": _clamp_unit(polarity),
        "bilateral_symmetry": _weighted_nearest_reflection_score(projected, point_weights),
        "radial_symmetry": _clamp_unit(1.0 / (1.0 + radius_cv)),
        **_raster_shape_features(
            projected,
            point_weights,
            fill_convex_hull=fill_sparse_landmark_footprint,
        ),
    }


def _fingerprint_array(terminal: dict[str, Any], *, specimen_id: str) -> np.ndarray | None:
    resolution_value = terminal.get("fingerprintResolution")
    if not isinstance(resolution_value, (int, float)):
        return None
    resolution = int(resolution_value)
    if resolution <= 0:
        return None
    raw = terminal.get("fingerprintU8")
    if isinstance(raw, str):
        values = np.frombuffer(base64.b64decode(raw, validate=True), dtype=np.uint8).astype(
            np.float64
        )
    elif isinstance(raw, list):
        try:
            values = np.asarray(raw, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{specimen_id}.fingerprintU8 must be numeric") from exc
        if values.ndim != 1 or not np.isfinite(values).all():
            raise ValueError(f"{specimen_id}.fingerprintU8 must be a finite flat array")
        if np.any(values < 0.0) or np.any(values > 255.0) or np.any(values != np.floor(values)):
            raise ValueError(f"{specimen_id}.fingerprintU8 must contain uint8 values")
    else:
        return None
    expected = resolution * resolution
    if values.size != expected:
        raise ValueError(
            f"{specimen_id}: fingerprint length {values.size} does not match "
            f"resolution {resolution}"
        )
    return values.reshape((resolution, resolution))


def _fingerprint_point_cloud(
    terminal: dict[str, Any],
    *,
    specimen_id: str,
) -> tuple[np.ndarray, np.ndarray] | None:
    fingerprint = _fingerprint_array(terminal, specimen_id=specimen_id)
    if fingerprint is None:
        return None
    ys, xs = np.nonzero(fingerprint > 0.0)
    if xs.size < 2:
        return None
    points = np.column_stack([xs.astype(np.float64), ys.astype(np.float64)])
    weights = fingerprint[ys, xs].astype(np.float64)
    return points, weights


def _lenia_study_ids(connection: DuckDBPyConnection, study_id: str | None) -> list[str]:
    if study_id is not None:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM specimens
            JOIN studies ON studies.study_id = specimens.study_id
            JOIN specimen_axes USING (specimen_id)
            WHERE specimens.study_id = ?
              AND specimen_axes.axis_family = 'terminal'
              AND specimens.descriptor_version = ?
              AND specimens.terminal_version = ?
              AND specimens.normalization_policy = ?
              AND EXISTS (
                  SELECT 1 FROM study_specimens
                  WHERE study_specimens.study_id = specimens.study_id
                    AND study_specimens.specimen_id = specimens.specimen_id
              )
            """,
            [study_id, DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY],
        ).fetchone()
        return [study_id] if row is not None and int(row[0]) > 0 else []
    rows = connection.execute(
        """
        SELECT DISTINCT specimens.study_id
        FROM specimens
        JOIN studies ON studies.study_id = specimens.study_id
        JOIN specimen_axes USING (specimen_id)
        WHERE specimen_axes.axis_family = 'terminal'
          AND specimens.descriptor_version = ?
          AND specimens.terminal_version = ?
          AND specimens.normalization_policy = ?
          AND EXISTS (
              SELECT 1 FROM study_specimens
              WHERE study_specimens.study_id = specimens.study_id
                AND study_specimens.specimen_id = specimens.specimen_id
          )
        ORDER BY specimens.study_id
        """,
        [DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY],
    ).fetchall()
    return [str(row[0]) for row in rows]


def _iter_lenia_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
    missing_common_only: bool = False,
    selected_specimen_ids: dict[str, list[str]] | None = None,
) -> Iterator[_CommonMorphologyRow]:
    for resolved_study_id in _lenia_study_ids(connection, study_id):
        selected_ids = (
            selected_specimen_ids.get(resolved_study_id)
            if selected_specimen_ids is not None
            else None
        )
        if selected_specimen_ids is not None and not selected_ids:
            continue
        context_id = register_context(
            connection,
            study_id=resolved_study_id,
            context_kind="baseline",
            label="common_morphology",
            metadata_json={"sourceId": LENIA_SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
        )
        missing_clause = ""
        params: list[Any] = [resolved_study_id]
        if missing_common_only:
            missing_clause = """
                  AND NOT EXISTS (
                      SELECT 1
                      FROM observations
                      WHERE observations.study_id = ?
                        AND observations.observation_kind = ?
                        AND observations.specimen_id = specimens.specimen_id
                  )
            """
            params.extend([resolved_study_id, OBSERVATION_KIND])
        selection_clause = (
            "AND specimens.specimen_id IN (SELECT unnest(?::VARCHAR[]))"
            if selected_ids is not None
            else ""
        )
        last_specimen_id: str | None = None
        while True:
            specimen_rows = connection.execute(
                f"""
                SELECT DISTINCT
                    specimens.specimen_id,
                    specimens.recorded_at,
                    specimens.results_path,
                    specimens.export_dir,
                    specimens.activity_path,
                    specimens.fingerprint_path,
                    specimen_descriptors.terminal_descriptor_json
                FROM specimens
                JOIN specimen_descriptors USING (specimen_id)
                WHERE specimens.study_id = ?
                  AND specimens.descriptor_version = ?
                  AND specimens.terminal_version = ?
                  AND specimens.normalization_policy = ?
                  AND (? IS NULL OR specimens.specimen_id > ?)
                  {selection_clause}
                  AND EXISTS (
                      SELECT 1 FROM study_specimens
                      WHERE study_specimens.study_id = specimens.study_id
                        AND study_specimens.specimen_id = specimens.specimen_id
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM specimen_axes
                      WHERE specimen_axes.specimen_id = specimens.specimen_id
                        AND specimen_axes.axis_family = 'terminal'
                  )
                  {missing_clause}
                ORDER BY specimens.specimen_id
                LIMIT ?
                """,
                [
                    params[0],
                    DESCRIPTOR_VERSION,
                    TERMINAL_VERSION,
                    NORMALIZATION_POLICY,
                    last_specimen_id,
                    last_specimen_id,
                    *([selected_ids] if selected_ids is not None else []),
                    *params[1:],
                    _LENIA_FETCH_BATCH_SIZE,
                ],
            ).fetchall()
            if not specimen_rows:
                break
            last_specimen_id = str(specimen_rows[-1][0])
            for specimen_row in specimen_rows:
                (
                    specimen_id,
                    recorded_at,
                    results_path,
                    export_dir,
                    activity_path,
                    fingerprint_path,
                    terminal_descriptor_json,
                ) = specimen_row
                terminal = _json_dict(terminal_descriptor_json)
                point_cloud = _fingerprint_point_cloud(terminal, specimen_id=str(specimen_id))
                if point_cloud is None:
                    continue
                points, weights = point_cloud
                source_ref = results_path or export_dir or activity_path or fingerprint_path
                observation_id = stable_id(
                    LENIA_SOURCE_ID,
                    "common-observation",
                    resolved_study_id,
                    specimen_id,
                    FEATURE_SPACE_ID,
                )
                yield _CommonMorphologyRow(
                    observation_id=observation_id,
                    specimen_id=str(specimen_id),
                    study_id=resolved_study_id,
                    source_id=LENIA_SOURCE_ID,
                    context_id=context_id,
                    observed_at=recorded_at,
                    source_ref=str(source_ref) if source_ref is not None else None,
                    values=point_cloud_shape_features(points, weights=weights),
                    payload_json={
                        "featureSpaceId": FEATURE_SPACE_ID,
                        "pointCloudSource": "terminal.fingerprintU8",
                        "pointCount": int(points.shape[0]),
                        "fingerprintResolution": terminal.get("fingerprintResolution"),
                    },
                )


def _iter_valid_lenia_calibration_candidates(
    connection: DuckDBPyConnection,
) -> Iterator[tuple[str, str, str]]:
    for resolved_study_id in _lenia_study_ids(connection, None):
        last_specimen_id: str | None = None
        while True:
            rows = connection.execute(
                """
                SELECT DISTINCT
                    specimens.specimen_id,
                    specimen_descriptors.terminal_descriptor_json
                FROM specimens
                JOIN specimen_descriptors USING (specimen_id)
                WHERE specimens.study_id = ?
                  AND specimens.descriptor_version = ?
                  AND specimens.terminal_version = ?
                  AND specimens.normalization_policy = ?
                  AND (? IS NULL OR specimens.specimen_id > ?)
                  AND EXISTS (
                      SELECT 1 FROM study_specimens
                      WHERE study_specimens.study_id = specimens.study_id
                        AND study_specimens.specimen_id = specimens.specimen_id
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM specimen_axes
                      WHERE specimen_axes.specimen_id = specimens.specimen_id
                        AND specimen_axes.axis_family = 'terminal'
                  )
                ORDER BY specimens.specimen_id
                LIMIT ?
                """,
                [
                    resolved_study_id,
                    DESCRIPTOR_VERSION,
                    TERMINAL_VERSION,
                    NORMALIZATION_POLICY,
                    last_specimen_id,
                    last_specimen_id,
                    _LENIA_FETCH_BATCH_SIZE,
                ],
            ).fetchall()
            if not rows:
                break
            last_specimen_id = str(rows[-1][0])
            for specimen_id, terminal_descriptor_json in rows:
                resolved_specimen_id = str(specimen_id)
                terminal = _json_dict(terminal_descriptor_json)
                if (
                    _fingerprint_point_cloud(
                        terminal,
                        specimen_id=resolved_specimen_id,
                    )
                    is None
                ):
                    continue
                yield (
                    resolved_study_id,
                    resolved_specimen_id,
                    stable_id(
                        LENIA_SOURCE_ID,
                        "common-observation",
                        resolved_study_id,
                        resolved_specimen_id,
                        FEATURE_SPACE_ID,
                    ),
                )


def valid_lenia_common_specimen_count(connection: DuckDBPyConnection) -> int:
    return sum(1 for _ in _iter_valid_lenia_calibration_candidates(connection))


def _fish_studies(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
    dataset_root: Path | None,
) -> list[tuple[str, Path]]:
    rows = connection.execute(
        """
        SELECT study_id, metadata_json
        FROM studies
        WHERE study_kind = 'biological_morphospace'
        ORDER BY study_id
        """
    ).fetchall()
    studies: list[tuple[str, Path]] = []
    for row_study_id, metadata_json in rows:
        if study_id is not None and str(row_study_id) != study_id:
            continue
        metadata = _json_dict(metadata_json)
        if metadata.get("sourceId") != DRYAD_FISH_SOURCE_ID:
            continue
        metadata_root = metadata.get("datasetRoot")
        root_value = (
            dataset_root
            if dataset_root is not None
            else Path(metadata_root)
            if isinstance(metadata_root, str)
            else None
        )
        if root_value is None:
            continue
        studies.append((str(row_study_id), root_value.resolve()))
    return studies


def _read_dryad_fish_landmarks(dataset_root: Path) -> list[dict[str, Any]]:
    output_path = dataset_root / "extracted/gpa/Slicer_GPA_output/OutputData.csv"
    if not output_path.exists():
        raise FileNotFoundError(output_path)
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        landmark_axes: dict[int, set[str]] = {}
        for fieldname in fieldnames:
            match = _LANDMARK_COLUMN_RE.fullmatch(fieldname)
            if match is None:
                continue
            landmark_axes.setdefault(int(match.group(1)), set()).add(match.group(2))
        landmark_ids = [
            landmark_id
            for landmark_id, axes in sorted(landmark_axes.items())
            if {"X", "Y", "Z"}.issubset(axes)
        ]
        if not landmark_ids:
            raise ValueError(f"{output_path}: no complete LM n_X/LM n_Y/LM n_Z landmarks found")

        rows: list[dict[str, Any]] = []
        for source_row_index, row in enumerate(reader):
            sample_name = row.get("Sample_name")
            if not sample_name:
                raise ValueError(f"{output_path}: row {source_row_index + 2} missing Sample_name")
            points = np.asarray(
                [
                    [
                        _finite_float(
                            row.get(f"LM {landmark_id}_{axis}"),
                            label=f"{sample_name}.LM {landmark_id}_{axis}",
                        )
                        for axis in ("X", "Y", "Z")
                    ]
                    for landmark_id in landmark_ids
                ],
                dtype=np.float64,
            )
            rows.append(
                {
                    "sample_name": sample_name,
                    "source_row_index": source_row_index,
                    "point_count": len(landmark_ids),
                    "points": points,
                    "output_path": output_path,
                }
            )
    return rows


def _fish_specimen_observed_at(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> Any:
    row = connection.execute(
        "SELECT recorded_at FROM specimens WHERE specimen_id = ?",
        [specimen_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"{specimen_id}: missing imported Dryad fish specimen")
    return row[0]


def _collect_fish_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
    dataset_root: Path | None,
) -> list[_CommonMorphologyRow]:
    rows: list[_CommonMorphologyRow] = []
    for resolved_study_id, root in _fish_studies(
        connection,
        study_id=study_id,
        dataset_root=dataset_root,
    ):
        context_id = register_context(
            connection,
            study_id=resolved_study_id,
            context_kind="baseline",
            label="common_morphology",
            metadata_json={"sourceId": DRYAD_FISH_SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
        )
        for landmark_row in _read_dryad_fish_landmarks(root):
            sample_name = str(landmark_row["sample_name"])
            specimen_id = stable_id(DRYAD_FISH_SOURCE_ID, "specimen", sample_name)
            observed_at = _fish_specimen_observed_at(connection, specimen_id=specimen_id)
            observation_id = stable_id(
                DRYAD_FISH_SOURCE_ID,
                "common-observation",
                resolved_study_id,
                sample_name,
                FEATURE_SPACE_ID,
            )
            rows.append(
                _CommonMorphologyRow(
                    observation_id=observation_id,
                    specimen_id=specimen_id,
                    study_id=resolved_study_id,
                    source_id=DRYAD_FISH_SOURCE_ID,
                    context_id=context_id,
                    observed_at=observed_at,
                    source_ref=(
                        f"{landmark_row['output_path']}#{landmark_row['source_row_index'] + 2}"
                    ),
                    values=point_cloud_shape_features(landmark_row["points"]),
                    payload_json={
                        "featureSpaceId": FEATURE_SPACE_ID,
                        "pointCloudSource": "Dryad OutputData.csv GPA landmarks",
                        "sampleName": sample_name,
                        "sourceRowIndex": landmark_row["source_row_index"],
                        "pointCount": landmark_row["point_count"],
                    },
                )
            )
    return rows


def _embryomaker_study_ids(
    connection: DuckDBPyConnection,
    study_id: str | None,
) -> list[str]:
    if study_id is not None:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM observations
            WHERE study_id = ?
              AND source_id = ?
              AND observation_kind = ?
            """,
            [study_id, EMBRYOMAKER_SOURCE_ID, EMBRYOMAKER_OBSERVATION_KIND],
        ).fetchone()
        return [study_id] if row is not None and int(row[0]) > 0 else []
    rows = connection.execute(
        """
        SELECT DISTINCT study_id
        FROM observations
        WHERE source_id = ?
          AND observation_kind = ?
        ORDER BY study_id
        """,
        [EMBRYOMAKER_SOURCE_ID, EMBRYOMAKER_OBSERVATION_KIND],
    ).fetchall()
    return [str(row[0]) for row in rows]


def _collect_embryomaker_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> list[_CommonMorphologyRow]:
    rows: list[_CommonMorphologyRow] = []
    for resolved_study_id in _embryomaker_study_ids(connection, study_id):
        context_id = register_context(
            connection,
            study_id=resolved_study_id,
            context_kind="baseline",
            label="common_morphology",
            metadata_json={
                "sourceId": EMBRYOMAKER_SOURCE_ID,
                "featureSpaceId": FEATURE_SPACE_ID,
            },
        )
        observation_rows = connection.execute(
            """
            SELECT observation_id, specimen_id, source_ref, step, payload_json
            FROM observations
            WHERE study_id = ?
              AND source_id = ?
              AND observation_kind = ?
            ORDER BY source_ref
            """,
            [resolved_study_id, EMBRYOMAKER_SOURCE_ID, EMBRYOMAKER_OBSERVATION_KIND],
        ).fetchall()
        for observation_id, specimen_id, source_ref, step, payload_json in observation_rows:
            if not source_ref:
                continue
            points = np.asarray(
                load_embryomaker_node_points(Path(str(source_ref))),
                dtype=np.float64,
            )
            if points.shape[0] < 2:
                continue
            payload = _json_dict(payload_json)
            rows.append(
                _CommonMorphologyRow(
                    observation_id=stable_id(
                        EMBRYOMAKER_SOURCE_ID,
                        "common-observation",
                        resolved_study_id,
                        observation_id,
                        FEATURE_SPACE_ID,
                    ),
                    specimen_id=str(specimen_id),
                    study_id=resolved_study_id,
                    source_id=EMBRYOMAKER_SOURCE_ID,
                    context_id=context_id,
                    observed_at=None,
                    source_ref=str(source_ref),
                    values=point_cloud_shape_features(points),
                    payload_json={
                        "featureSpaceId": FEATURE_SPACE_ID,
                        "pointCloudSource": "EmbryoMaker legacy node positions",
                        "sourceObservationId": observation_id,
                        "step": step,
                        "family": payload.get("family"),
                        "pointCount": int(points.shape[0]),
                    },
                )
            )
    return rows


def _collect_all_fish_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
    dataset_root: Path | None,
) -> list[_CommonMorphologyRow]:
    if study_id is None or dataset_root is None:
        return _collect_fish_rows(
            connection,
            study_id=None,
            dataset_root=dataset_root,
        )

    selected_rows = _collect_fish_rows(
        connection,
        study_id=study_id,
        dataset_root=dataset_root,
    )
    metadata_rows = _collect_fish_rows(
        connection,
        study_id=None,
        dataset_root=None,
    )
    return [row for row in metadata_rows if row.study_id != study_id] + selected_rows


def _axis_stats(rows: list[_CommonMorphologyRow]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for axis_id in AXIS_IDS:
        values = [row.values[axis_id] for row in rows]
        center, scale = robust_center_scale(values)
        stats[axis_id] = {
            "center": center,
            "scale": scale,
            "min": min(values),
            "max": max(values),
        }
    return stats


def _existing_axis_stats(
    connection: DuckDBPyConnection,
) -> dict[str, dict[str, float]] | None:
    rows = connection.execute(
        """
        SELECT axis_id, metadata_json
        FROM feature_axes
        WHERE feature_space_id = ?
        """,
        [FEATURE_SPACE_ID],
    ).fetchall()
    if len(rows) < len(AXIS_IDS):
        return None

    stats: dict[str, dict[str, float]] = {}
    for axis_id, metadata_json in rows:
        axis_id = str(axis_id)
        if axis_id not in AXIS_IDS:
            continue
        metadata = _json_dict(metadata_json)
        try:
            center = float(metadata["robustCenter"])
            scale = float(metadata["robustScale"])
            raw_min = float(metadata["rawMin"])
            raw_max = float(metadata["rawMax"])
        except (KeyError, TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (center, scale, raw_min, raw_max)):
            return None
        stats[axis_id] = {
            "center": center,
            "scale": scale,
            "min": raw_min,
            "max": raw_max,
        }
    return stats if set(stats) == set(AXIS_IDS) else None


def _iter_selected_study_rows(
    connection: DuckDBPyConnection,
    *,
    dryad_fish_root: Path | None,
    study_id: str,
) -> Iterator[_CommonMorphologyRow]:
    yield from _iter_lenia_rows(connection, study_id=study_id)
    yield from _collect_fish_rows(
        connection,
        study_id=study_id,
        dataset_root=dryad_fish_root,
    )
    yield from _collect_embryomaker_rows(connection, study_id=study_id)


def _source_counts_excluding_study(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = connection.execute(
        """
        SELECT observations.source_id, COUNT(*)
        FROM specimen_feature_vectors
        JOIN observations USING (observation_id)
        JOIN feature_spaces
          ON feature_spaces.feature_space_id = specimen_feature_vectors.feature_space_id
        JOIN feature_calibrations
          ON feature_calibrations.calibration_id = specimen_feature_vectors.calibration_id
         AND feature_calibrations.feature_space_id =
             specimen_feature_vectors.feature_space_id
        WHERE specimen_feature_vectors.feature_space_id = ?
          AND specimen_feature_vectors.calibration_id = json_extract_string(
              feature_spaces.metadata_json,
              '$.activeCalibrationId'
          )
          AND feature_calibrations.frozen
          AND observations.observation_kind = ?
          AND observations.study_id != ?
        GROUP BY observations.source_id
        """,
        [FEATURE_SPACE_ID, OBSERVATION_KIND, study_id],
    ).fetchall()
    for source_id, count in rows:
        counts[str(source_id)] = int(count)
    return counts


def _source_counts_after_replace(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    replacement_rows: list[_CommonMorphologyRow],
) -> dict[str, int]:
    counts = _source_counts_excluding_study(connection, study_id=study_id)
    for row in replacement_rows:
        counts[row.source_id] = counts.get(row.source_id, 0) + 1
    return counts


def _row_batches(
    rows: Iterable[_CommonMorphologyRow],
    *,
    batch_size: int = _WRITE_BATCH_SIZE,
) -> Iterator[list[_CommonMorphologyRow]]:
    iterator = iter(rows)
    while batch := list(itertools.islice(iterator, batch_size)):
        yield batch


def _increment_source_counts(
    counts: dict[str, int],
    rows: Iterable[_CommonMorphologyRow],
) -> None:
    for row in rows:
        counts[row.source_id] = counts.get(row.source_id, 0) + 1


def _write_row_batches(
    connection: DuckDBPyConnection,
    *,
    batches: Iterable[list[_CommonMorphologyRow]],
    stats: dict[str, dict[str, float]],
    calibration_id: str,
) -> tuple[int, int, dict[str, int]]:
    observation_count = 0
    feature_value_count = 0
    source_counts: dict[str, int] = {}
    for batch in batches:
        observation_count += len(batch)
        _increment_source_counts(source_counts, batch)
        feature_value_count += _write_rows(
            connection,
            rows=batch,
            stats=stats,
            calibration_id=calibration_id,
        )
    return observation_count, feature_value_count, source_counts


def _clear_existing_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> None:
    if study_id is None:
        connection.execute(
            "DELETE FROM specimen_feature_vectors WHERE feature_space_id = ?",
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            "DELETE FROM sparse_feature_values WHERE feature_space_id = ?",
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            "DELETE FROM observations WHERE observation_kind = ?",
            [OBSERVATION_KIND],
        )
        return
    connection.execute(
        """
        DELETE FROM specimen_feature_vectors
        WHERE feature_space_id = ? AND study_id = ?
        """,
        [FEATURE_SPACE_ID, study_id],
    )
    connection.execute(
        """
        DELETE FROM sparse_feature_values
        WHERE feature_space_id = ?
          AND observation_id IN (
              SELECT observation_id
              FROM observations
              WHERE observation_kind = ? AND study_id = ?
          )
        """,
        [FEATURE_SPACE_ID, OBSERVATION_KIND, study_id],
    )
    connection.execute(
        "DELETE FROM observations WHERE observation_kind = ? AND study_id = ?",
        [OBSERVATION_KIND, study_id],
    )


def _write_rows(
    connection: DuckDBPyConnection,
    *,
    rows: list[_CommonMorphologyRow],
    stats: dict[str, dict[str, float]],
    calibration_id: str,
) -> int:
    if not rows:
        return 0
    connection.execute(
        """
        INSERT OR REPLACE INTO observations (
            observation_id, specimen_id, study_id, source_id, context_id,
            observation_kind, observed_at, step, source_ref, payload_json
        )
        SELECT unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::TIMESTAMP[]), unnest(?::INTEGER[]), unnest(?::VARCHAR[]),
               CAST(unnest(?::VARCHAR[]) AS JSON)
        """,
        [
            [row.observation_id for row in rows],
            [row.specimen_id for row in rows],
            [row.study_id for row in rows],
            [row.source_id for row in rows],
            [row.context_id for row in rows],
            [OBSERVATION_KIND] * len(rows),
            [normalize_optional_timestamp(row.observed_at) for row in rows],
            [None] * len(rows),
            [row.source_ref for row in rows],
            [json_text(row.payload_json) for row in rows],
        ],
    )
    upsert_specimen_feature_vectors(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        calibration_id=calibration_id,
        vector_version="v3",
        axis_count=len(AXIS_IDS),
        rows=[
            (
                row.observation_id,
                row.specimen_id,
                row.study_id,
                [row.values[axis_id] for axis_id in AXIS_IDS],
                [
                    zscore(
                        row.values[axis_id],
                        center=stats[axis_id]["center"],
                        scale=stats[axis_id]["scale"],
                    )
                    for axis_id in AXIS_IDS
                ],
            )
            for row in rows
        ],
    )
    return len(rows) * len(AXIS_IDS)


def _upsert_common_feature_space(
    connection: DuckDBPyConnection,
    *,
    source_counts: dict[str, int],
    reference_counts: dict[str, int],
    calibration_id: str | None,
) -> None:
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="cross_source_shape_descriptor",
        storage_mode="dense_vectors",
        label=FEATURE_SPACE_LABEL,
        version_label="v3",
        coordinate_policy=(
            "raw_value is a scale-normalized point-distribution descriptor; "
            "normalized_value uses a frozen robust transform from an equal-count "
            "reference per source. Raster topology axes are excluded because sparse "
            "landmarks and dense fingerprints do not define equivalent occupancy."
        ),
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "axisCount": len(AXIS_IDS),
            "sourceCounts": dict(sorted(source_counts.items())),
            "referenceCounts": dict(sorted(reference_counts.items())),
            "normalization": "frozen per-axis robust z-score from balanced sources",
            "leniaDescriptorVersion": DESCRIPTOR_VERSION,
            "leniaNormalizationPolicy": NORMALIZATION_POLICY,
            "excludedRepresentationDependentAxes": [
                str(spec["id"])
                for spec in POINT_CLOUD_AXIS_SPECS
                if spec["id"] not in CROSS_SOURCE_AXIS_IDS
            ],
            "activeCalibrationId": calibration_id,
        },
    )


def derive_common_morphology(
    connection: DuckDBPyConnection,
    *,
    dryad_fish_root: Path | None = None,
    study_id: str | None = None,
) -> dict[str, Any]:
    stats = _existing_axis_stats(connection) if study_id is not None else None
    new_calibration = stats is None
    calibration_id: str | None = None
    reference_counts: dict[str, int] = {}
    if new_calibration:
        fish_rows = _collect_all_fish_rows(
            connection,
            study_id=study_id,
            dataset_root=dryad_fish_root,
        )
        embryo_rows = _collect_embryomaker_rows(connection, study_id=None)
        source_counts: dict[str, int] = {}
        candidates: dict[str, list[tuple[int, str, object]]] = {}

        def offer_candidate(source_id: str, observation_id: str, payload: object) -> None:
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
            score = int(stable_id("common-calibration", source_id, observation_id), 16)
            entry = (-score, observation_id, payload)
            source_candidates = candidates.setdefault(source_id, [])
            if len(source_candidates) < _MAX_CALIBRATION_ROWS_PER_SOURCE:
                heapq.heappush(source_candidates, entry)
            elif entry[:2] > source_candidates[0][:2]:
                heapq.heapreplace(source_candidates, entry)

        for row in itertools.chain(fish_rows, embryo_rows):
            offer_candidate(row.source_id, row.observation_id, row)
        for (
            candidate_study_id,
            specimen_id,
            observation_id,
        ) in _iter_valid_lenia_calibration_candidates(connection):
            offer_candidate(
                LENIA_SOURCE_ID,
                observation_id,
                (candidate_study_id, specimen_id),
            )
        if not source_counts:
            raise ValueError("no Lenia fingerprints or Dryad fish landmarks available")
        per_source = min(min(source_counts.values()), _MAX_CALIBRATION_ROWS_PER_SOURCE)
        reference_counts = {source_id: per_source for source_id in sorted(source_counts)}
        reference_rows: list[_CommonMorphologyRow] = []
        selected_lenia_specimens: dict[str, list[str]] = {}
        for source_id in sorted(source_counts):
            for _, _, payload in heapq.nlargest(per_source, candidates[source_id]):
                if isinstance(payload, _CommonMorphologyRow):
                    reference_rows.append(payload)
                else:
                    candidate_study_id, specimen_id = cast(tuple[str, str], payload)
                    selected_lenia_specimens.setdefault(candidate_study_id, []).append(specimen_id)
        reference_rows.extend(
            _iter_lenia_rows(
                connection,
                study_id=None,
                selected_specimen_ids=selected_lenia_specimens,
            )
        )
        actual_reference_counts: dict[str, int] = {}
        for row in reference_rows:
            actual_reference_counts[row.source_id] = (
                actual_reference_counts.get(row.source_id, 0) + 1
            )
        if any(
            actual_reference_counts.get(source_id, 0) != expected_count
            for source_id, expected_count in reference_counts.items()
        ):
            raise ValueError(
                "balanced calibration candidates did not produce valid point clouds: "
                f"expected={reference_counts}, actual={actual_reference_counts}"
            )
        stats = _axis_stats(reference_rows)
        row_iterator = (
            itertools.chain(
                _iter_lenia_rows(connection, study_id=None),
                fish_rows,
                embryo_rows,
            )
            if study_id is None
            else itertools.chain(
                _iter_lenia_rows(connection, study_id=study_id),
                (row for row in fish_rows if row.study_id == study_id),
                (row for row in embryo_rows if row.study_id == study_id),
            )
        )
    else:
        assert study_id is not None
        row_iterator = _iter_selected_study_rows(
            connection,
            dryad_fish_root=dryad_fish_root,
            study_id=study_id,
        )
        source_counts = _source_counts_excluding_study(connection, study_id=study_id)
    first_batch = list(itertools.islice(row_iterator, _WRITE_BATCH_SIZE))
    if not first_batch:
        raise ValueError(
            f"no Lenia fingerprints or Dryad fish landmarks available for study_id={study_id}"
        )
    streaming_batches = itertools.chain([first_batch], _row_batches(row_iterator))
    assert stats is not None

    upsert_morphospace_source(
        connection,
        source_id=LENIA_SOURCE_ID,
        source_kind="synthetic_cellular_automaton",
        label="Lenia synthetic morphospace",
        version_label="v2",
        metadata_json={"system": "lenia-swarm"},
    )
    upsert_morphospace_source(
        connection,
        source_id=EMBRYOMAKER_SOURCE_ID,
        source_kind="embryomaker_legacy_snapshot_corpus",
        label="EmbryoMaker legacy artifact morphospace",
        version_label="legacy-output-dat",
        metadata_json={"featureSpaceId": FEATURE_SPACE_ID},
    )
    if new_calibration:
        _upsert_common_feature_space(
            connection,
            source_counts=source_counts,
            reference_counts=reference_counts,
            calibration_id=None,
        )
    replace_feature_axes(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        axis_rows=[
            {
                "axis_id": str(spec["id"]),
                "axis_index": index,
                "axis_family": str(spec.get("axisFamily", "common_point_distribution_morphology")),
                "label": str(spec["label"]),
                "units": "unitless",
                "metadata_json": {
                    "formula": spec["formula"],
                    "positiveMeaning": spec["positiveMeaning"],
                    "robustCenter": stats[str(spec["id"])]["center"],
                    "robustScale": stats[str(spec["id"])]["scale"],
                    "rawMin": stats[str(spec["id"])]["min"],
                    "rawMax": stats[str(spec["id"])]["max"],
                },
            }
            for index, spec in enumerate(AXIS_SPECS)
        ],
    )

    if new_calibration:
        calibration_id = register_feature_calibration(
            connection,
            feature_space_id=FEATURE_SPACE_ID,
            calibration_version="balanced-reference-v3",
            axis_order=AXIS_IDS,
            reference_query={
                "selection": "equal-count-per-source-stable-hash",
                "maximumRowsPerSource": _MAX_CALIBRATION_ROWS_PER_SOURCE,
                "counts": dict(sorted(reference_counts.items())),
            },
            axis_transforms={
                axis_id: {
                    "transform": "robust-zscore",
                    "center": stats[axis_id]["center"],
                    "scale": stats[axis_id]["scale"],
                }
                for axis_id in AXIS_IDS
            },
            metadata_json={"axisOrder": list(AXIS_IDS), "frozen": True},
        )
        _upsert_common_feature_space(
            connection,
            source_counts=source_counts,
            reference_counts=reference_counts,
            calibration_id=calibration_id,
        )
    else:
        calibration_row = connection.execute(
            """
            SELECT feature_calibrations.calibration_id,
                   feature_calibrations.reference_query_json
            FROM feature_spaces
            JOIN feature_calibrations
              ON feature_calibrations.calibration_id = json_extract_string(
                  feature_spaces.metadata_json,
                  '$.activeCalibrationId'
              )
            WHERE feature_spaces.feature_space_id = ?
              AND feature_calibrations.frozen
            """,
            [FEATURE_SPACE_ID],
        ).fetchone()
        if calibration_row is None:
            raise ValueError(
                f"{FEATURE_SPACE_ID}: incremental derivation requires a frozen calibration"
            )
        calibration_id = str(calibration_row[0])
        reference_query = _json_dict(calibration_row[1])
        raw_reference_counts = reference_query.get("counts")
        if isinstance(raw_reference_counts, dict):
            reference_counts = {
                str(source_id): int(count) for source_id, count in raw_reference_counts.items()
            }

    assert calibration_id is not None
    mark_derived_artifact_state(
        connection,
        artifact_kind="feature-space",
        feature_space_id=FEATURE_SPACE_ID,
        descriptor_version=DESCRIPTOR_VERSION,
        normalization_policy=NORMALIZATION_POLICY,
        status="invalid",
        reason="common morphology vectors are being rebuilt",
        metadata_json={"calibrationId": calibration_id, "lifecycle": "building"},
    )
    _clear_existing_rows(connection, study_id=study_id)
    observation_count, feature_value_count, replacement_counts = _write_row_batches(
        connection,
        batches=streaming_batches,
        stats=stats,
        calibration_id=calibration_id,
    )
    if not new_calibration:
        for source_id, count in replacement_counts.items():
            source_counts[source_id] = source_counts.get(source_id, 0) + count
    _upsert_common_feature_space(
        connection,
        source_counts=source_counts,
        reference_counts=reference_counts,
        calibration_id=calibration_id,
    )

    vector_count_row = connection.execute(
        """
        SELECT count(*)
        FROM specimen_feature_vectors
        WHERE feature_space_id = ? AND calibration_id = ?
          AND (? IS NULL OR study_id = ?)
        """,
        [FEATURE_SPACE_ID, calibration_id, study_id, study_id],
    ).fetchone()
    vector_count = int(vector_count_row[0]) if vector_count_row is not None else 0
    validate_dense_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        calibration_id=calibration_id,
        observation_kind=OBSERVATION_KIND,
        axis_count=len(AXIS_IDS),
    )
    mark_derived_artifact_state(
        connection,
        artifact_kind="feature-space",
        feature_space_id=FEATURE_SPACE_ID,
        descriptor_version=DESCRIPTOR_VERSION,
        normalization_policy=NORMALIZATION_POLICY,
        status="valid",
        reason=None,
        metadata_json={"calibrationId": calibration_id, "lifecycle": "complete"},
    )
    return {
        "featureSpaceId": FEATURE_SPACE_ID,
        "observationKind": OBSERVATION_KIND,
        "observationCount": observation_count,
        "axisCount": len(AXIS_IDS),
        "featureValueCount": feature_value_count,
        "vectorCount": vector_count,
        "sourceCounts": dict(sorted(source_counts.items())),
        "axisStats": json.loads(json_text(stats)),
        "calibrationId": calibration_id,
        "referenceCounts": dict(sorted(reference_counts.items())),
    }
