from __future__ import annotations

import json
import math
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import transform_axes

from .warehouse import (
    json_text,
    register_context,
    stable_id,
)

ANATOMICAL_AXIS_IDS: tuple[str, ...] = (
    "fragmentation",
    "cavity_count",
    "boundary_complexity",
    "bilateral_symmetry",
    "radial_symmetry",
    "rotational_symmetry",
    "left_right_asymmetry",
    "axial_polarity",
    "center_offset",
    "coverage",
    "compactness",
    "elongation",
    "expansion_gain",
    "condensation_gain",
    "elongation_gain",
    "folding_gain",
    "fragmentation_gain",
    "locomotion_onset_step",
    "meander_final",
)

_PARTIAL_CONTEXT_AXIS_MAP = {
    "occupancyMean": "coverage",
    "gyration": "spread",
    "centerVelocity": "locomotion",
}
_BASELINE_BATCH_SIZE = 8192
_CONTEXT_TRIAL_BATCH_SIZE = 4096


def _state_row_batch(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    after_specimen_id: str | None,
) -> list[tuple[str, str, str | None, str | None, str | None, str | None, str | None]]:
    query = """
        SELECT specimens.specimen_id, specimens.study_id, specimens.recorded_at,
               specimens.family_kind, specimens.regime_family, specimens.geometry_family,
               specimens.canonical_family
        FROM specimens
        WHERE specimens.study_id = ?
          AND EXISTS (
              SELECT 1 FROM study_specimens
              WHERE study_specimens.study_id = specimens.study_id
                AND study_specimens.specimen_id = specimens.specimen_id
          )
          AND (? IS NULL OR specimens.specimen_id > ?)
        ORDER BY specimens.specimen_id
        LIMIT ?
    """
    return [
        tuple(row)
        for row in connection.execute(
            query,
            [study_id, after_specimen_id, after_specimen_id, _BASELINE_BATCH_SIZE],
        ).fetchall()
    ]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _finite_numeric(value: Any, *, label: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{label} must be finite")
    return resolved


def _raw_context_trial_axes(provenance: dict[str, Any]) -> dict[str, float]:
    raw_response = provenance.get("rawResponse")
    if not isinstance(raw_response, dict):
        return {}
    endpoint_axes = raw_response.get("endpointRawAxes")
    if isinstance(endpoint_axes, dict):
        mapped_endpoint_axes: dict[str, float] = {}
        for axis_id, value in endpoint_axes.items():
            resolved = _finite_numeric(value, label=f"endpointRawAxes.{axis_id}")
            if resolved is not None:
                mapped_endpoint_axes[str(axis_id)] = resolved
        if mapped_endpoint_axes:
            return mapped_endpoint_axes
    mean_metrics = raw_response.get("meanMetrics")
    if not isinstance(mean_metrics, dict):
        metrics = raw_response.get("metrics")
        if isinstance(metrics, dict):
            mean_metrics = metrics
        else:
            return {}
    mapped: dict[str, float] = {}
    for metric_key, axis_id in _PARTIAL_CONTEXT_AXIS_MAP.items():
        value = _finite_numeric(mean_metrics.get(metric_key), label=f"meanMetrics.{metric_key}")
        if value is not None:
            mapped[axis_id] = value
    if "finalMass" in mean_metrics and "gyration" in mean_metrics:
        mass = _finite_numeric(mean_metrics.get("finalMass"), label="meanMetrics.finalMass")
        gyration = _finite_numeric(mean_metrics.get("gyration"), label="meanMetrics.gyration")
        if mass is not None and gyration is not None and gyration:
            mapped["compactness"] = mass / gyration
    return mapped


def _symmetry_class(raw_axes: dict[str, float]) -> str:
    radial = raw_axes.get("radial_symmetry", 0.0)
    bilateral = raw_axes.get("bilateral_symmetry", 0.0)
    rotational = raw_axes.get("rotational_symmetry", 0.0)
    left_right = raw_axes.get("left_right_asymmetry", 1.0)
    if radial >= max(bilateral, rotational) and radial >= 0.7:
        return "radial_like"
    if bilateral >= max(radial, rotational) and bilateral >= 0.55 and left_right <= 0.35:
        return "bilateral_like"
    if rotational >= max(radial, bilateral) and rotational >= 0.55:
        return "rotational_like"
    return "asymmetric_like"


def _arrangement_class(raw_axes: dict[str, float]) -> str:
    fragmentation = raw_axes.get("fragmentation", 0.0)
    center_offset = raw_axes.get("center_offset", 0.0)
    axial_polarity = raw_axes.get("axial_polarity", 0.0)
    if fragmentation >= 2.0:
        return "fragmented"
    if center_offset <= 0.05:
        return "centered"
    if axial_polarity >= 0.2:
        return "polarized"
    return "offset"


def _enclosure_class(raw_axes: dict[str, float]) -> str:
    cavity_count = raw_axes.get("cavity_count", 0.0)
    boundary = raw_axes.get("boundary_complexity", 0.0)
    if cavity_count >= 1.0:
        return "enclosing"
    if boundary >= 2.0:
        return "folded_open"
    return "solid"


def _assembly_class(raw_axes: dict[str, float]) -> str:
    fragmentation = raw_axes.get("fragmentation", 0.0)
    cavity_count = raw_axes.get("cavity_count", 0.0)
    elongation = raw_axes.get("elongation", 0.0)
    if fragmentation >= 2.0:
        return "multipart"
    if cavity_count >= 1.0:
        return "enclosing"
    if elongation >= 1.0:
        return "elongated"
    return "compact"


def _state_payload(
    *,
    raw_axes: dict[str, float],
    study_id: str,
    specimen_id: str,
    context_id: str | None,
    source_kind: str,
    family_kind: str | None,
    regime_family: str | None,
    geometry_family: str | None,
    canonical_family: str | None,
) -> dict[str, Any]:
    available_axes = sorted(axis_id for axis_id in ANATOMICAL_AXIS_IDS if axis_id in raw_axes)
    missing_axes = sorted(axis_id for axis_id in ANATOMICAL_AXIS_IDS if axis_id not in raw_axes)
    return {
        "studyId": study_id,
        "specimenId": specimen_id,
        "contextId": context_id,
        "sourceKind": source_kind,
        "familyKind": family_kind,
        "regimeFamily": regime_family,
        "geometryFamily": geometry_family,
        "canonicalFamily": canonical_family,
        "symmetry_class": _symmetry_class(raw_axes),
        "arrangement_class": _arrangement_class(raw_axes),
        "enclosure_class": _enclosure_class(raw_axes),
        "assembly_class": _assembly_class(raw_axes),
        "availableAxes": available_axes,
        "missingAxes": missing_axes,
        "axisCoverage": {
            "availableCount": len(available_axes),
            "requiredCount": len(ANATOMICAL_AXIS_IDS),
        },
    }


def _replace_state_batch(
    connection: DuckDBPyConnection,
    *,
    state_ids: list[str],
    state_insert_rows: list[tuple[Any, ...]],
    state_axis_rows: list[tuple[Any, ...]],
) -> int:
    connection.execute(
        "DELETE FROM anatomical_state_axes "
        "WHERE state_id IN (SELECT unnest(?::VARCHAR[]))",
        [state_ids],
    )
    inserted_state_ids = {str(row[0]) for row in state_insert_rows}
    stale_state_ids = [
        state_id for state_id in state_ids if state_id not in inserted_state_ids
    ]
    if stale_state_ids:
        for table_name in (
            "creature_signal_axes",
            "creature_state_labels",
            "fiber_group_members",
        ):
            connection.execute(
                f"DELETE FROM {table_name} "
                "WHERE state_id IN (SELECT unnest(?::VARCHAR[]))",
                [stale_state_ids],
            )
        connection.execute(
            "DELETE FROM anatomical_states "
            "WHERE state_id IN (SELECT unnest(?::VARCHAR[]))",
            [stale_state_ids],
        )
    if not state_insert_rows:
        return 0
    columns = list(zip(*state_insert_rows, strict=True))
    connection.execute(
        """
        INSERT OR REPLACE INTO anatomical_states (
            state_id, specimen_id, study_id, context_id, source_kind, source_ref,
            recorded_at, state_json
        )
        SELECT unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::TIMESTAMP[]), CAST(unnest(?::VARCHAR[]) AS JSON)
        """,
        [list(column) for column in columns],
    )
    columns = list(zip(*state_axis_rows, strict=True))
    connection.execute(
        """
        INSERT INTO anatomical_state_axes (
            state_id, axis_id, raw_value, transformed_value
        )
        SELECT unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),
               unnest(?::DOUBLE[]), unnest(?::DOUBLE[])
        """,
        [list(column) for column in columns],
    )
    return len(state_insert_rows)


def _replace_baseline_states(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> int:
    last_specimen_id: str | None = None
    state_rows = _state_row_batch(
        connection,
        study_id=study_id,
        after_specimen_id=last_specimen_id,
    )
    if not state_rows:
        return 0
    baseline_context_id = register_context(
        connection,
        study_id=study_id,
        context_kind="baseline",
        label="baseline",
        metadata_json={"environment": "baseline", "perturbation": "baseline"},
    )
    updated = 0
    while state_rows:
        specimen_ids = [str(row[0]) for row in state_rows]
        last_specimen_id = specimen_ids[-1]
        axes_by_specimen: dict[str, dict[str, float]] = {}
        for specimen_id, axis_id, raw_value in connection.execute(
            """
            SELECT specimen_id, axis_id, raw_value
            FROM specimen_axes
            WHERE specimen_id IN (SELECT unnest(?::VARCHAR[]))
              AND raw_value IS NOT NULL
              AND axis_id IN (SELECT unnest(?::VARCHAR[]))
            ORDER BY specimen_id, axis_id
            """,
            [specimen_ids, list(ANATOMICAL_AXIS_IDS)],
        ).fetchall():
            axes_by_specimen.setdefault(str(specimen_id), {})[str(axis_id)] = float(
                raw_value
            )

        state_insert_rows: list[tuple[Any, ...]] = []
        state_axis_rows: list[tuple[Any, ...]] = []
        state_ids: list[str] = []
        for (
            specimen_id,
            specimen_study_id,
            recorded_at,
            family_kind,
            regime_family,
            geometry_family,
            canonical_family,
        ) in state_rows:
            resolved_specimen_id = str(specimen_id)
            resolved_study_id = str(specimen_study_id)
            raw_axes = axes_by_specimen.get(resolved_specimen_id, {})
            axis_rows: list[tuple[str, float | None, float | None]] = [
                (
                    axis_id,
                    float(raw_axes[axis_id]),
                    float(transform_axes({axis_id: float(raw_axes[axis_id])})[axis_id]),
                )
                for axis_id in ANATOMICAL_AXIS_IDS
                if axis_id in raw_axes
            ]
            state_id = stable_id(
                "anatomical-state",
                resolved_study_id,
                resolved_specimen_id,
                "baseline",
            )
            state_ids.append(state_id)
            if not axis_rows:
                continue
            state_insert_rows.append(
                (
                    state_id,
                    resolved_specimen_id,
                    resolved_study_id,
                    baseline_context_id,
                    "specimen_baseline",
                    resolved_specimen_id,
                    recorded_at,
                    json_text(
                        _state_payload(
                            raw_axes=raw_axes,
                            study_id=resolved_study_id,
                            specimen_id=resolved_specimen_id,
                            context_id=baseline_context_id,
                            source_kind="specimen_baseline",
                            family_kind=(
                                str(family_kind) if family_kind is not None else None
                            ),
                            regime_family=(
                                str(regime_family) if regime_family is not None else None
                            ),
                            geometry_family=(
                                str(geometry_family) if geometry_family is not None else None
                            ),
                            canonical_family=(
                                str(canonical_family)
                                if canonical_family is not None
                                else None
                            ),
                        )
                    ),
                )
            )
            state_axis_rows.extend(
                (state_id, axis_id, raw_value, transformed_value)
                for axis_id, raw_value, transformed_value in axis_rows
            )

        updated += _replace_state_batch(
            connection,
            state_ids=state_ids,
            state_insert_rows=state_insert_rows,
            state_axis_rows=state_axis_rows,
        )
        state_rows = _state_row_batch(
            connection,
            study_id=study_id,
            after_specimen_id=last_specimen_id,
        )
    return updated


def _replace_context_trial_states(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> int:
    updated = 0
    last_context_trial_id: str | None = None
    while True:
        rows = connection.execute(
            """
            SELECT context_trials.context_trial_id, context_trials.specimen_id,
                   context_trials.context_id, context_trials.provenance_json,
                   specimens.family_kind, specimens.regime_family,
                   specimens.geometry_family, specimens.canonical_family
            FROM context_trials
            JOIN specimens USING (specimen_id)
            WHERE context_trials.study_id = ?
              AND (? IS NULL OR context_trials.context_trial_id > ?)
            ORDER BY context_trials.context_trial_id
            LIMIT ?
            """,
            [
                study_id,
                last_context_trial_id,
                last_context_trial_id,
                _CONTEXT_TRIAL_BATCH_SIZE,
            ],
        ).fetchall()
        if not rows:
            break
        last_context_trial_id = str(rows[-1][0])
        state_ids: list[str] = []
        state_insert_rows: list[tuple[Any, ...]] = []
        state_axis_rows: list[tuple[Any, ...]] = []
        for (
            context_trial_id,
            specimen_id,
            context_id,
            provenance_json,
            family_kind,
            regime_family,
            geometry_family,
            canonical_family,
        ) in rows:
            resolved_trial_id = str(context_trial_id)
            resolved_specimen_id = str(specimen_id)
            resolved_context_id = str(context_id) if context_id is not None else None
            provenance = _json_object(provenance_json)
            raw_axes = _raw_context_trial_axes(provenance)
            state_id = stable_id(
                "anatomical-state",
                study_id,
                resolved_trial_id,
                "context-trial",
            )
            state_ids.append(state_id)
            if not raw_axes:
                continue
            state_insert_rows.append(
                (
                    state_id,
                    resolved_specimen_id,
                    study_id,
                    resolved_context_id,
                    "context_trial_endpoint",
                    resolved_trial_id,
                    None,
                    json_text(
                        {
                            **_state_payload(
                                raw_axes=raw_axes,
                                study_id=study_id,
                                specimen_id=resolved_specimen_id,
                                context_id=resolved_context_id,
                                source_kind="context_trial_endpoint",
                                family_kind=(
                                    str(family_kind) if family_kind is not None else None
                                ),
                                regime_family=(
                                    str(regime_family) if regime_family is not None else None
                                ),
                                geometry_family=(
                                    str(geometry_family)
                                    if geometry_family is not None
                                    else None
                                ),
                                canonical_family=(
                                    str(canonical_family)
                                    if canonical_family is not None
                                    else None
                                ),
                            ),
                            "provenance": provenance,
                        }
                    ),
                )
            )
            state_axis_rows.extend(
                (
                    state_id,
                    axis_id,
                    float(value),
                    float(transform_axes({axis_id: float(value)}).get(axis_id, value)),
                )
                for axis_id, value in sorted(raw_axes.items())
            )
        updated += _replace_state_batch(
            connection,
            state_ids=state_ids,
            state_insert_rows=state_insert_rows,
            state_axis_rows=state_axis_rows,
        )
    return updated


def derive_anatomy(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        study_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT study_id FROM studies ORDER BY study_id"
            ).fetchall()
        ]
    else:
        study_ids = [study_id]
    updated = 0
    for resolved_study_id in study_ids:
        updated += _replace_baseline_states(connection, study_id=resolved_study_id)
        updated += _replace_context_trial_states(connection, study_id=resolved_study_id)
    return updated
