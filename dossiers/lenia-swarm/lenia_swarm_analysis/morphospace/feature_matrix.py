from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

import numpy as np
from duckdb import DuckDBPyConnection
from ripser import ripser

from lenia_swarm_analysis.topology.analysis import (
    _diagram_summary,
    _pairwise_distance_matrix,
    _upper_triangle,
)

ValueColumn = Literal["raw_value", "normalized_value"]
MatrixFilters = dict[str, str | None]


def _validate_value_column(value_column: str) -> ValueColumn:
    if value_column not in {"raw_value", "normalized_value"}:
        raise ValueError("value_column must be raw_value or normalized_value")
    return value_column  # type: ignore[return-value]


def _json_payload(value: Any) -> Any:
    if isinstance(value, str) and value:
        return json.loads(value)
    return value


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _distribution_summary(values: np.ndarray) -> dict[str, Any]:
    if values.size == 0:
        return {"count": 0, "min": None, "mean": None, "median": None, "p90": None, "max": None}
    return {
        "count": int(values.size),
        "min": _finite_or_none(float(np.min(values))),
        "mean": _finite_or_none(float(np.mean(values))),
        "median": _finite_or_none(float(np.median(values))),
        "p90": _finite_or_none(float(np.quantile(values, 0.9))),
        "max": _finite_or_none(float(np.max(values))),
    }


def _feature_space_payload(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT feature_space_id, feature_space_kind, label, version_label,
               coordinate_policy, metric_json, metadata_json
        FROM feature_spaces
        WHERE feature_space_id = ?
        """,
        [feature_space_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown feature_space_id: {feature_space_id}")
    return {
        "featureSpaceId": row[0],
        "featureSpaceKind": row[1],
        "label": row[2],
        "versionLabel": row[3],
        "coordinatePolicy": row[4],
        "metric": _json_payload(row[5]),
        "metadata": _json_payload(row[6]),
    }


def _axis_payloads(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT axis_id, axis_index, axis_family, label, units, metadata_json
        FROM feature_axes
        WHERE feature_space_id = ?
        ORDER BY axis_index, axis_id
        """,
        [feature_space_id],
    ).fetchall()
    if not rows:
        raise ValueError(f"{feature_space_id}: feature space has no axes")
    return [
        {
            "axisId": row[0],
            "axisIndex": int(row[1]),
            "axisFamily": row[2],
            "label": row[3],
            "units": row[4],
            "metadata": _json_payload(row[5]),
        }
        for row in rows
    ]


def _matrix_summary(
    packet: dict[str, Any],
    *,
    label: str,
    filters: MatrixFilters,
) -> dict[str, Any]:
    return {
        "label": label,
        "filters": {key: value for key, value in sorted(filters.items()) if value is not None},
        "observationCount": packet["summary"]["observationCount"],
        "droppedObservationCount": packet["summary"]["droppedObservationCount"],
        "sourceCounts": packet["summary"]["sourceCounts"],
        "studyCounts": packet["summary"]["studyCounts"],
        "runCounts": packet["summary"]["runCounts"],
    }


def _axis_comparisons(
    *,
    axes: list[dict[str, Any]],
    left_matrix: np.ndarray,
    right_matrix: np.ndarray,
) -> list[dict[str, Any]]:
    left_mean = np.mean(left_matrix, axis=0)
    right_mean = np.mean(right_matrix, axis=0)
    left_std = (
        np.std(left_matrix, axis=0, ddof=1)
        if left_matrix.shape[0] > 1
        else np.zeros(left_matrix.shape[1], dtype=np.float64)
    )
    right_std = (
        np.std(right_matrix, axis=0, ddof=1)
        if right_matrix.shape[0] > 1
        else np.zeros(right_matrix.shape[1], dtype=np.float64)
    )
    left_var = left_std * left_std
    right_var = right_std * right_std
    pooled = np.sqrt((left_var + right_var) / 2.0)
    rows: list[dict[str, Any]] = []
    for index, axis in enumerate(axes):
        delta = float(right_mean[index] - left_mean[index])
        effect_size = None if pooled[index] <= 1e-12 else delta / float(pooled[index])
        rows.append(
            {
                "axisId": axis["axisId"],
                "axisIndex": axis["axisIndex"],
                "axisLabel": axis["label"],
                "leftMean": _finite_or_none(float(left_mean[index])),
                "rightMean": _finite_or_none(float(right_mean[index])),
                "deltaRightMinusLeft": _finite_or_none(delta),
                "absoluteDelta": _finite_or_none(abs(delta)),
                "leftStandardDeviation": _finite_or_none(float(left_std[index])),
                "rightStandardDeviation": _finite_or_none(float(right_std[index])),
                "effectSize": _finite_or_none(float(effect_size))
                if effect_size is not None
                else None,
            }
        )
    return rows


def _axis_delta_sort_key(row: dict[str, Any]) -> float:
    effect_size = row["effectSize"]
    if isinstance(effect_size, (int, float)):
        return abs(float(effect_size))
    absolute_delta = row["absoluteDelta"]
    return abs(float(absolute_delta)) if isinstance(absolute_delta, (int, float)) else 0.0


def _filter_sql(
    *,
    source_id: str | None,
    study_id: str | None,
    run_id: str | None,
    observation_kind: str | None,
) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if source_id is not None:
        clauses.append("comparison_observations_vw.source_id = ?")
        params.append(source_id)
    if study_id is not None:
        clauses.append("comparison_observations_vw.study_id = ?")
        params.append(study_id)
    if run_id is not None:
        clauses.append("comparison_observations_vw.run_id = ?")
        params.append(run_id)
    if observation_kind is not None:
        clauses.append("comparison_observations_vw.observation_kind = ?")
        params.append(observation_kind)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _observation_payloads(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    source_id: str | None,
    study_id: str | None,
    run_id: str | None,
    observation_kind: str | None,
) -> list[dict[str, Any]]:
    filter_sql, filter_params = _filter_sql(
        source_id=source_id,
        study_id=study_id,
        run_id=run_id,
        observation_kind=observation_kind,
    )
    rows = connection.execute(
        f"""
        SELECT DISTINCT
            comparison_observations_vw.observation_id,
            comparison_observations_vw.specimen_id,
            comparison_observations_vw.study_id,
            comparison_observations_vw.study_kind,
            comparison_observations_vw.study_label,
            comparison_observations_vw.source_id,
            comparison_observations_vw.source_kind,
            comparison_observations_vw.source_label,
            comparison_observations_vw.context_id,
            comparison_observations_vw.context_kind,
            comparison_observations_vw.context_label,
            comparison_observations_vw.observation_kind,
            comparison_observations_vw.source_ref,
            comparison_observations_vw.run_id,
            comparison_observations_vw.campaign_id,
            comparison_observations_vw.source_mode,
            comparison_observations_vw.source_algorithm,
            comparison_observations_vw.config_hash,
            comparison_observations_vw.canonical_family,
            comparison_observations_vw.runtime_family
        FROM feature_values
        JOIN comparison_observations_vw USING (observation_id)
        WHERE feature_values.feature_space_id = ?
        {filter_sql}
        ORDER BY
            comparison_observations_vw.source_id,
            comparison_observations_vw.study_id,
            comparison_observations_vw.run_id,
            comparison_observations_vw.specimen_id,
            comparison_observations_vw.observation_id
        """,
        [feature_space_id, *filter_params],
    ).fetchall()
    return [
        {
            "observationId": row[0],
            "specimenId": row[1],
            "studyId": row[2],
            "studyKind": row[3],
            "studyLabel": row[4],
            "sourceId": row[5],
            "sourceKind": row[6],
            "sourceLabel": row[7],
            "contextId": row[8],
            "contextKind": row[9],
            "contextLabel": row[10],
            "observationKind": row[11],
            "sourceRef": row[12],
            "runId": row[13],
            "campaignId": row[14],
            "sourceMode": row[15],
            "sourceAlgorithm": row[16],
            "configHash": row[17],
            "canonicalFamily": row[18],
            "runtimeFamily": row[19],
        }
        for row in rows
    ]


def export_feature_matrix(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    run_id: str | None = None,
    observation_kind: str | None = None,
) -> dict[str, Any]:
    resolved_value_column = _validate_value_column(value_column)
    feature_space = _feature_space_payload(connection, feature_space_id=feature_space_id)
    axes = _axis_payloads(connection, feature_space_id=feature_space_id)
    axis_ids = [str(axis["axisId"]) for axis in axes]
    axis_index = {axis_id: index for index, axis_id in enumerate(axis_ids)}
    observations = _observation_payloads(
        connection,
        feature_space_id=feature_space_id,
        source_id=source_id,
        study_id=study_id,
        run_id=run_id,
        observation_kind=observation_kind,
    )
    observation_index = {
        str(observation["observationId"]): index for index, observation in enumerate(observations)
    }
    rows = connection.execute(
        f"""
        SELECT feature_values.observation_id, feature_values.axis_id,
               feature_values.{resolved_value_column}
        FROM feature_values
        JOIN comparison_observations_vw USING (observation_id)
        WHERE feature_values.feature_space_id = ?
          AND feature_values.{resolved_value_column} IS NOT NULL
        ORDER BY feature_values.observation_id, feature_values.axis_id
        """,
        [feature_space_id],
    ).fetchall()
    matrix = np.full((len(observations), len(axis_ids)), np.nan, dtype=np.float64)
    for observation_id, axis_id, value in rows:
        if observation_id not in observation_index or axis_id not in axis_index:
            continue
        matrix[observation_index[str(observation_id)], axis_index[str(axis_id)]] = float(value)

    complete_mask = ~np.isnan(matrix).any(axis=1)
    complete_indices = [index for index, complete in enumerate(complete_mask.tolist()) if complete]
    complete_observations = [observations[index] for index in complete_indices]
    complete_matrix = matrix[complete_mask]
    source_counts = Counter(str(row["sourceId"]) for row in complete_observations)
    study_counts = Counter(str(row["studyId"]) for row in complete_observations)
    run_counts = Counter(
        str(row["runId"]) for row in complete_observations if row["runId"] is not None
    )
    return {
        "packetKind": "comparative_feature_matrix_v1",
        "summary": {
            "featureSpaceId": feature_space_id,
            "valueColumn": resolved_value_column,
            "observationCount": len(complete_observations),
            "droppedObservationCount": len(observations) - len(complete_observations),
            "axisCount": len(axis_ids),
            "sourceCounts": dict(sorted(source_counts.items())),
            "studyCounts": dict(sorted(study_counts.items())),
            "runCounts": dict(sorted(run_counts.items())),
        },
        "featureSpace": feature_space,
        "axes": axes,
        "observations": complete_observations,
        "matrix": complete_matrix.tolist(),
    }


def run_feature_tda(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    value_column: str = "normalized_value",
    source_id: str | None = None,
    study_id: str | None = None,
    run_id: str | None = None,
    observation_kind: str | None = None,
    max_homology_dim: int = 1,
) -> dict[str, Any]:
    matrix_packet = export_feature_matrix(
        connection,
        feature_space_id=feature_space_id,
        value_column=value_column,
        source_id=source_id,
        study_id=study_id,
        run_id=run_id,
        observation_kind=observation_kind,
    )
    matrix = np.asarray(matrix_packet["matrix"], dtype=np.float64)
    if matrix.shape[0] < 2:
        raise ValueError("TDA requires at least two complete observations")
    distances = _pairwise_distance_matrix(matrix)
    pairwise = _upper_triangle(distances)
    diagrams = ripser(distances, distance_matrix=True, maxdim=max_homology_dim)["dgms"]
    topology = _diagram_summary(diagrams, float(np.max(pairwise)) if pairwise.size else 0.0)
    return {
        "packetKind": "comparative_feature_tda_v1",
        "summary": {
            **matrix_packet["summary"],
            "maxHomologyDim": max_homology_dim,
            "backend": "ripser-euclidean",
            "pairwiseDistance": {
                "count": int(pairwise.size),
                "min": float(np.min(pairwise)) if pairwise.size else None,
                "mean": float(np.mean(pairwise)) if pairwise.size else None,
                "max": float(np.max(pairwise)) if pairwise.size else None,
            },
        },
        "featureSpace": matrix_packet["featureSpace"],
        "axes": matrix_packet["axes"],
        "observations": matrix_packet["observations"],
        "topology": topology,
    }


def compare_feature_cohorts(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    value_column: str = "normalized_value",
    left_label: str = "left",
    right_label: str = "right",
    left_source_id: str | None = None,
    left_study_id: str | None = None,
    left_run_id: str | None = None,
    left_observation_kind: str | None = None,
    right_source_id: str | None = None,
    right_study_id: str | None = None,
    right_run_id: str | None = None,
    right_observation_kind: str | None = None,
) -> dict[str, Any]:
    left_filters: MatrixFilters = {
        "sourceId": left_source_id,
        "studyId": left_study_id,
        "runId": left_run_id,
        "observationKind": left_observation_kind,
    }
    right_filters: MatrixFilters = {
        "sourceId": right_source_id,
        "studyId": right_study_id,
        "runId": right_run_id,
        "observationKind": right_observation_kind,
    }
    left_packet = export_feature_matrix(
        connection,
        feature_space_id=feature_space_id,
        value_column=value_column,
        source_id=left_source_id,
        study_id=left_study_id,
        run_id=left_run_id,
        observation_kind=left_observation_kind,
    )
    right_packet = export_feature_matrix(
        connection,
        feature_space_id=feature_space_id,
        value_column=value_column,
        source_id=right_source_id,
        study_id=right_study_id,
        run_id=right_run_id,
        observation_kind=right_observation_kind,
    )
    left_matrix = np.asarray(left_packet["matrix"], dtype=np.float64)
    right_matrix = np.asarray(right_packet["matrix"], dtype=np.float64)
    if left_matrix.shape[0] == 0:
        raise ValueError(f"{left_label}: no complete observations")
    if right_matrix.shape[0] == 0:
        raise ValueError(f"{right_label}: no complete observations")
    if left_matrix.shape[1] != right_matrix.shape[1]:
        raise ValueError("cohorts must have the same axis count")

    distances = np.sqrt(
        np.sum(
            (left_matrix[:, None, :] - right_matrix[None, :, :]) ** 2,
            axis=2,
            dtype=np.float64,
        )
    )
    left_to_right = np.min(distances, axis=1)
    right_to_left = np.min(distances, axis=0)
    axis_comparisons = _axis_comparisons(
        axes=left_packet["axes"],
        left_matrix=left_matrix,
        right_matrix=right_matrix,
    )
    top_axis_deltas = sorted(axis_comparisons, key=_axis_delta_sort_key, reverse=True)[:10]
    return {
        "packetKind": "comparative_feature_cohort_comparison_v1",
        "summary": {
            "featureSpaceId": feature_space_id,
            "valueColumn": _validate_value_column(value_column),
            "axisCount": left_matrix.shape[1],
            "left": _matrix_summary(left_packet, label=left_label, filters=left_filters),
            "right": _matrix_summary(right_packet, label=right_label, filters=right_filters),
            "crossDistance": _distribution_summary(distances.reshape(-1)),
            "leftToRightNearestDistance": _distribution_summary(left_to_right),
            "rightToLeftNearestDistance": _distribution_summary(right_to_left),
        },
        "featureSpace": left_packet["featureSpace"],
        "axes": left_packet["axes"],
        "axisComparisons": axis_comparisons,
        "topAxisDeltas": top_axis_deltas,
    }
