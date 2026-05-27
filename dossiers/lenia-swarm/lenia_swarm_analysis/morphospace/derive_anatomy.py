from __future__ import annotations

import json
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import transform_axes

from .warehouse import (
    json_text,
    register_context,
    replace_anatomical_state_axes,
    stable_id,
    upsert_anatomical_state,
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


def _state_rows_for_study(
    connection: DuckDBPyConnection,
    *,
    study_id: str | None,
) -> list[tuple[str, str, str | None, str | None, str | None, str | None, str | None]]:
    if study_id is None:
        query = """
            SELECT specimen_id, study_id, recorded_at, family_kind, regime_family,
                   geometry_family, canonical_family
            FROM specimens
            ORDER BY study_id, specimen_id
        """
        return [tuple(row) for row in connection.execute(query).fetchall()]
    query = """
        SELECT specimens.specimen_id, study_specimens.study_id, specimens.recorded_at,
               specimens.family_kind, specimens.regime_family, specimens.geometry_family,
               specimens.canonical_family
        FROM study_specimens
        JOIN specimens USING (specimen_id)
        WHERE study_specimens.study_id = ?
        ORDER BY specimens.specimen_id
    """
    return [tuple(row) for row in connection.execute(query, [study_id]).fetchall()]


def _raw_specimen_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> dict[str, float]:
    return {
        str(axis_id): float(value)
        for axis_id, value in connection.execute(
            """
            SELECT axis_id, raw_value
            FROM specimen_axes
            WHERE specimen_id = ? AND raw_value IS NOT NULL
            """,
            [specimen_id],
        ).fetchall()
    }


def _raw_context_trial_axes(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
) -> dict[str, float]:
    rows = connection.execute(
        """
        SELECT provenance_json
        FROM context_trials
        WHERE context_trial_id = ?
        """,
        [context_trial_id],
    ).fetchone()
    if rows is None or not rows[0]:
        return {}
    provenance = json.loads(rows[0])
    raw_response = provenance.get("rawResponse")
    if not isinstance(raw_response, dict):
        return {}
    endpoint_axes = raw_response.get("endpointRawAxes")
    if isinstance(endpoint_axes, dict):
        mapped_endpoint_axes = {
            str(axis_id): float(value)
            for axis_id, value in endpoint_axes.items()
            if isinstance(value, (int, float))
        }
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
        value = mean_metrics.get(metric_key)
        if isinstance(value, (int, float)):
            mapped[axis_id] = float(value)
    if "finalMass" in mean_metrics and "gyration" in mean_metrics:
        mass = mean_metrics.get("finalMass")
        gyration = mean_metrics.get("gyration")
        if isinstance(mass, (int, float)) and isinstance(gyration, (int, float)) and gyration:
            mapped["compactness"] = float(mass) / float(gyration)
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


def _replace_baseline_states(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> int:
    baseline_context_id = register_context(
        connection,
        study_id=study_id,
        context_kind="baseline",
        label="baseline",
        metadata_json={"environment": "baseline", "perturbation": "baseline"},
    )
    state_rows = _state_rows_for_study(connection, study_id=study_id)
    if not state_rows:
        return 0

    axes_by_specimen: dict[str, dict[str, float]] = {}
    for specimen_id, axis_id, raw_value in connection.execute(
        """
        SELECT specimen_axes.specimen_id, specimen_axes.axis_id, specimen_axes.raw_value
        FROM study_specimens
        JOIN specimen_axes USING (specimen_id)
        WHERE study_specimens.study_id = ?
          AND specimen_axes.raw_value IS NOT NULL
          AND specimen_axes.axis_id IN (SELECT unnest(?))
        ORDER BY specimen_axes.specimen_id, specimen_axes.axis_id
        """,
        [study_id, list(ANATOMICAL_AXIS_IDS)],
    ).fetchall():
        axes_by_specimen.setdefault(str(specimen_id), {})[str(axis_id)] = float(raw_value)

    state_insert_rows: list[tuple[Any, ...]] = []
    state_axis_rows: list[tuple[Any, ...]] = []
    state_ids: list[tuple[str]] = []
    for (
        specimen_id,
        specimen_study_id,
        recorded_at,
        family_kind,
        regime_family,
        geometry_family,
        canonical_family,
    ) in state_rows:
        raw_axes = axes_by_specimen.get(str(specimen_id), {})
        axis_rows: list[tuple[str, float | None, float | None]] = [
            (
                axis_id,
                float(raw_axes[axis_id]),
                float(transform_axes({axis_id: float(raw_axes[axis_id])})[axis_id]),
            )
            for axis_id in ANATOMICAL_AXIS_IDS
            if axis_id in raw_axes
        ]
        if not axis_rows:
            continue
        state_id = stable_id("anatomical-state", specimen_study_id, specimen_id, "baseline")
        state_ids.append((state_id,))
        state_insert_rows.append(
            (
                state_id,
                str(specimen_id),
                str(specimen_study_id),
                baseline_context_id,
                "specimen_baseline",
                str(specimen_id),
                recorded_at,
                json_text(_state_payload(
                    raw_axes=raw_axes,
                    study_id=str(specimen_study_id),
                    specimen_id=str(specimen_id),
                    context_id=baseline_context_id,
                    source_kind="specimen_baseline",
                    family_kind=str(family_kind) if family_kind is not None else None,
                    regime_family=str(regime_family) if regime_family is not None else None,
                    geometry_family=str(geometry_family) if geometry_family is not None else None,
                    canonical_family=(
                        str(canonical_family) if canonical_family is not None else None
                    ),
                )),
            )
        )
        state_axis_rows.extend(
            (state_id, axis_id, raw_value, transformed_value)
            for axis_id, raw_value, transformed_value in axis_rows
        )

    if not state_insert_rows:
        return 0

    connection.execute("CREATE OR REPLACE TEMP TABLE tmp_anatomical_state_ids (state_id TEXT)")
    connection.executemany(
        "INSERT INTO tmp_anatomical_state_ids (state_id) VALUES (?)",
        state_ids,
    )
    connection.execute(
        """
        DELETE FROM anatomical_state_axes
        WHERE state_id IN (SELECT state_id FROM tmp_anatomical_state_ids)
        """
    )
    connection.executemany(
        """
        INSERT OR REPLACE INTO anatomical_states (
            state_id, specimen_id, study_id, context_id, source_kind, source_ref,
            recorded_at, state_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        state_insert_rows,
    )
    connection.executemany(
        """
        INSERT INTO anatomical_state_axes (
            state_id, axis_id, raw_value, transformed_value
        )
        VALUES (?, ?, ?, ?)
        """,
        state_axis_rows,
    )
    return len(state_insert_rows)


def _replace_context_trial_states(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> int:
    rows = connection.execute(
        """
        SELECT context_trial_id, specimen_id, context_id, context_trials.provenance_json,
               specimens.family_kind, specimens.regime_family, specimens.geometry_family,
               specimens.canonical_family
        FROM context_trials
        JOIN specimens USING (specimen_id)
        WHERE context_trials.study_id = ?
        ORDER BY context_trial_id
        """,
        [study_id],
    ).fetchall()
    updated = 0
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
        raw_axes = _raw_context_trial_axes(connection, context_trial_id=str(context_trial_id))
        if not raw_axes:
            continue
        state_id = stable_id("anatomical-state", study_id, context_trial_id, "context-trial")
        upsert_anatomical_state(
            connection,
            state_id=state_id,
            specimen_id=str(specimen_id),
            study_id=study_id,
            context_id=str(context_id) if context_id is not None else None,
            source_kind="context_trial_endpoint",
            source_ref=str(context_trial_id),
            recorded_at=None,
            state_json={
                **_state_payload(
                    raw_axes=raw_axes,
                    study_id=study_id,
                    specimen_id=str(specimen_id),
                    context_id=str(context_id) if context_id is not None else None,
                    source_kind="context_trial_endpoint",
                    family_kind=str(family_kind) if family_kind is not None else None,
                    regime_family=str(regime_family) if regime_family is not None else None,
                    geometry_family=str(geometry_family) if geometry_family is not None else None,
                    canonical_family=(
                        str(canonical_family) if canonical_family is not None else None
                    ),
                ),
                "provenance": json.loads(provenance_json) if provenance_json else {},
            },
        )
        axis_rows: list[tuple[str, float | None, float | None]] = [
            (
                axis_id,
                float(value),
                float(
                    transform_axes({axis_id: float(value)}).get(axis_id, float(value))
                ),
            )
            for axis_id, value in sorted(raw_axes.items())
        ]
        replace_anatomical_state_axes(connection, state_id=state_id, axis_rows=axis_rows)
        updated += 1
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
