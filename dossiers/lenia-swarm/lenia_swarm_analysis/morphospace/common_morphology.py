from __future__ import annotations

import base64
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import robust_center_scale, zscore

from .ingest_dryad_fish import SOURCE_ID as DRYAD_FISH_SOURCE_ID
from .warehouse import (
    json_text,
    register_context,
    replace_feature_axes,
    replace_feature_values,
    stable_id,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_observation,
)

LENIA_SOURCE_ID = "lenia_swarm"
FEATURE_SPACE_ID = "common_morphology_v1"
FEATURE_SPACE_LABEL = "Common point-cloud morphology"
OBSERVATION_KIND = "common_point_cloud_morphology"
_EPSILON = 1.0e-6
_MAX_SYMMETRY_POINTS = 2048
_LANDMARK_COLUMN_RE = re.compile(r"^LM\s+(\d+)_(X|Y|Z)$")

AXIS_SPECS: tuple[dict[str, Any], ...] = (
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
)
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


def point_cloud_shape_features(
    points: np.ndarray,
    *,
    weights: np.ndarray | None = None,
) -> dict[str, float]:
    coordinates = np.asarray(points, dtype=np.float64)
    if coordinates.ndim != 2 or coordinates.shape[0] < 2:
        raise ValueError("point cloud must be a two-dimensional array with at least two points")
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
        values = np.asarray(
            [_finite_float(value, label=f"{specimen_id}.fingerprintU8") for value in raw],
            dtype=np.float64,
        )
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


def _terminal_from_payloads(
    *,
    provenance_json: Any,
    specimen_manifest_json: Any,
) -> dict[str, Any] | None:
    provenance = _json_dict(provenance_json)
    terminal = provenance.get("terminal")
    if isinstance(terminal, dict):
        return terminal
    bundle = provenance.get("descriptorBundle")
    if isinstance(bundle, dict) and isinstance(bundle.get("terminal"), dict):
        return bundle["terminal"]

    manifest = _json_dict(specimen_manifest_json)
    snapshots = manifest.get("snapshots")
    if isinstance(snapshots, dict):
        descriptor_bundle = snapshots.get("descriptorBundle")
        if isinstance(descriptor_bundle, dict) and isinstance(
            descriptor_bundle.get("terminal"),
            dict,
        ):
            return descriptor_bundle["terminal"]
    descriptor_bundle = manifest.get("descriptorBundle")
    if isinstance(descriptor_bundle, dict) and isinstance(descriptor_bundle.get("terminal"), dict):
        return descriptor_bundle["terminal"]
    return None


def _lenia_study_ids(connection: DuckDBPyConnection, study_id: str | None) -> list[str]:
    if study_id is not None:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM study_specimens
            JOIN specimen_axes USING (specimen_id)
            WHERE study_specimens.study_id = ?
              AND specimen_axes.axis_family = 'terminal'
            """,
            [study_id],
        ).fetchone()
        return [study_id] if row is not None and int(row[0]) > 0 else []
    rows = connection.execute(
        """
        SELECT DISTINCT study_specimens.study_id
        FROM study_specimens
        JOIN specimen_axes USING (specimen_id)
        WHERE specimen_axes.axis_family = 'terminal'
        ORDER BY study_specimens.study_id
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _collect_lenia_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> list[_CommonMorphologyRow]:
    rows: list[_CommonMorphologyRow] = []
    for resolved_study_id in _lenia_study_ids(connection, study_id):
        context_id = register_context(
            connection,
            study_id=resolved_study_id,
            context_kind="baseline",
            label="common_morphology",
            metadata_json={"sourceId": LENIA_SOURCE_ID, "featureSpaceId": FEATURE_SPACE_ID},
        )
        specimen_rows = connection.execute(
            """
            SELECT DISTINCT
                specimens.specimen_id,
                specimens.recorded_at,
                specimens.results_path,
                specimens.export_dir,
                specimens.activity_path,
                specimens.fingerprint_path,
                specimens.provenance_json,
                specimens.specimen_manifest_json
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            WHERE study_specimens.study_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM specimen_axes
                  WHERE specimen_axes.specimen_id = specimens.specimen_id
                    AND specimen_axes.axis_family = 'terminal'
              )
            ORDER BY specimens.specimen_id
            """,
            [resolved_study_id],
        ).fetchall()
        for specimen_row in specimen_rows:
            (
                specimen_id,
                recorded_at,
                results_path,
                export_dir,
                activity_path,
                fingerprint_path,
                provenance_json,
                specimen_manifest_json,
            ) = specimen_row
            terminal = _terminal_from_payloads(
                provenance_json=provenance_json,
                specimen_manifest_json=specimen_manifest_json,
            )
            if terminal is None:
                continue
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
            rows.append(
                _CommonMorphologyRow(
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
            )
    return rows


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
                        f"{landmark_row['output_path']}"
                        f"#{landmark_row['source_row_index'] + 2}"
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


def _clear_existing_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> None:
    if study_id is None:
        connection.execute(
            "DELETE FROM feature_values WHERE feature_space_id = ?",
            [FEATURE_SPACE_ID],
        )
        connection.execute(
            "DELETE FROM observations WHERE observation_kind = ?",
            [OBSERVATION_KIND],
        )
        return
    connection.execute(
        """
        DELETE FROM feature_values
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


def derive_common_morphology(
    connection: DuckDBPyConnection,
    *,
    dryad_fish_root: Path | None = None,
    study_id: str | None = None,
) -> dict[str, Any]:
    all_rows = [
        *_collect_lenia_rows(connection, study_id=None),
        *_collect_fish_rows(
            connection,
            study_id=None,
            dataset_root=dryad_fish_root,
        ),
    ]
    if not all_rows:
        raise ValueError("no Lenia fingerprints or Dryad fish landmarks available")
    rows = (
        all_rows
        if study_id is None
        else [row for row in all_rows if row.study_id == study_id]
    )
    if not rows:
        raise ValueError(
            "no Lenia fingerprints or Dryad fish landmarks available "
            f"for study_id={study_id}"
        )

    stats = _axis_stats(all_rows)
    source_counts: dict[str, int] = {}
    for row in all_rows:
        source_counts[row.source_id] = source_counts.get(row.source_id, 0) + 1

    upsert_morphospace_source(
        connection,
        source_id=LENIA_SOURCE_ID,
        source_kind="synthetic_cellular_automaton",
        label="Lenia synthetic morphospace",
        version_label="v1",
        metadata_json={"system": "lenia-swarm"},
    )
    upsert_feature_space(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        feature_space_kind="cross_source_shape_descriptor",
        label=FEATURE_SPACE_LABEL,
        version_label="v1",
        coordinate_policy=(
            "raw_value is a scale-normalized point-cloud descriptor; normalized_value "
            "is robust z-score across the derived common-morphology corpus"
        ),
        metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        metadata_json={
            "axisCount": len(AXIS_IDS),
            "sourceCounts": dict(sorted(source_counts.items())),
            "normalization": "per-axis robust z-score across all derived observations",
        },
    )
    replace_feature_axes(
        connection,
        feature_space_id=FEATURE_SPACE_ID,
        axis_rows=[
            {
                "axis_id": str(spec["id"]),
                "axis_index": index,
                "axis_family": "common_point_cloud_morphology",
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

    _clear_existing_rows(connection, study_id=study_id)
    for row in rows:
        upsert_observation(
            connection,
            observation_id=row.observation_id,
            specimen_id=row.specimen_id,
            study_id=row.study_id,
            source_id=row.source_id,
            context_id=row.context_id,
            observation_kind=OBSERVATION_KIND,
            observed_at=row.observed_at,
            source_ref=row.source_ref,
            payload_json=row.payload_json,
        )
        replace_feature_values(
            connection,
            observation_id=row.observation_id,
            feature_space_id=FEATURE_SPACE_ID,
            value_rows=[
                {
                    "axis_id": axis_id,
                    "raw_value": row.values[axis_id],
                    "normalized_value": zscore(
                        row.values[axis_id],
                        center=stats[axis_id]["center"],
                        scale=stats[axis_id]["scale"],
                    ),
                    "metadata_json": {"normalization": "robust_zscore"},
                }
                for axis_id in AXIS_IDS
            ],
        )

    return {
        "featureSpaceId": FEATURE_SPACE_ID,
        "observationKind": OBSERVATION_KIND,
        "observationCount": len(rows),
        "axisCount": len(AXIS_IDS),
        "featureValueCount": len(rows) * len(AXIS_IDS),
        "sourceCounts": dict(sorted(source_counts.items())),
        "axisStats": json.loads(json_text(stats)),
    }
