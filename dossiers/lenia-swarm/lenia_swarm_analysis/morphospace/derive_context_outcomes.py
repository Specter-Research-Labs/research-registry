from __future__ import annotations

import json
import math
from statistics import mean
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import transform_axes

from .creature_signals import (
    body_plan_axes,
    body_plan_class_shift_score,
    body_plan_error_score,
    creature_labels,
    endpoint_creature_axes,
    organization_score,
)
from .derive_anatomy import (
    _arrangement_class,
    _assembly_class,
    _enclosure_class,
    _symmetry_class,
)
from .warehouse import (
    register_context,
    register_control_program,
    replace_context_outcomes,
    replace_context_trials,
)

ANATOMICAL_GOAL_AXIS_IDS = (
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
    "locomotion",
    "meander",
)

REFERENCE_MOTION_METRIC_KEYS = (
    "pathLength",
    "displacement",
    "centerVelocity",
)


def _context_kind(environment: str | None, perturbation: str | None) -> str:
    env = (environment or "").strip()
    pert = (perturbation or "").strip()
    if pert == "baseline":
        return "obstacle" if env.startswith("obstacle") else "baseline"
    if pert == "lesion":
        return "lesion_plus_obstacle" if env.startswith("obstacle") else "lesion"
    return "intervention"


def _context_label(environment: str | None, perturbation: str | None) -> str:
    env = (environment or "").strip() or "unknown-environment"
    pert = (perturbation or "").strip() or "unknown-perturbation"
    if pert == "baseline":
        return env
    return f"{env}::{pert}"


def _outcome_rows_from_payload(
    payload: dict[str, Any],
    *,
    context_kind: str,
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    rows: list[tuple[str, float | None, dict[str, Any] | None]] = []
    derived_mean_fragility: float | None = None
    derived_mean_robustness: float | None = None
    for payload_key, outcome_kind in (
        ("meanFragilityScore", "mean_fragility_score"),
        ("maxFragilityScore", "max_fragility_score"),
        ("meanRobustnessScore", "mean_robustness_score"),
        ("minRobustnessScore", "min_robustness_score"),
    ):
        value = payload.get(payload_key)
        if isinstance(value, (int, float)):
            rows.append((outcome_kind, float(value), {"sourceKey": payload_key}))
    metric_sources: list[tuple[str, dict[str, Any]]] = []
    mean_metrics = payload.get("meanMetrics")
    if isinstance(mean_metrics, dict):
        metric_sources.append(("meanMetrics", mean_metrics))
    response_metrics = payload.get("responseMetrics")
    if isinstance(response_metrics, dict):
        metric_sources.append(("responseMetrics", response_metrics))
    direct_metrics = payload.get("metrics")
    if isinstance(direct_metrics, dict):
        metric_sources.append(("metrics", direct_metrics))
    for source_name, metrics in metric_sources:
        for metric_key in (
            "postPerturbationDivergence",
            "returnToBaselineScore",
            "redirectedBehaviorScore",
            "massRetentionRatio",
            "displacementRatio",
            "occupancyDelta",
            "varianceDelta",
            "centerVelocity",
            "score",
        ):
            metric_value = metrics.get(metric_key)
            if isinstance(metric_value, (int, float)):
                rows.append(
                    (
                        metric_key,
                        float(metric_value),
                        {"sourceKey": metric_key, "metricSource": source_name},
                    )
                )
                if metric_key == "postPerturbationDivergence" and derived_mean_fragility is None:
                    derived_mean_fragility = float(metric_value)
                if metric_key == "returnToBaselineScore" and derived_mean_robustness is None:
                    derived_mean_robustness = float(metric_value)
    if derived_mean_fragility is not None:
        rows.append(
            (
                "mean_fragility_score",
                derived_mean_fragility,
                {"derivedFrom": "postPerturbationDivergence"},
            )
        )
        rows.append(
            (
                "max_fragility_score",
                derived_mean_fragility,
                {"derivedFrom": "postPerturbationDivergence"},
            )
        )
    elif context_kind in {"baseline", "obstacle"}:
        rows.append(
            (
                "mean_fragility_score",
                0.0,
                {"derivedFrom": "baseline_default"},
            )
        )
        rows.append(
            (
                "max_fragility_score",
                0.0,
                {"derivedFrom": "baseline_default"},
            )
        )
    if derived_mean_robustness is not None:
        rows.append(
            (
                "mean_robustness_score",
                derived_mean_robustness,
                {"derivedFrom": "returnToBaselineScore"},
            )
        )
        rows.append(
            (
                "min_robustness_score",
                derived_mean_robustness,
                {"derivedFrom": "returnToBaselineScore"},
            )
        )
    elif context_kind in {"baseline", "obstacle"}:
        rows.append(
            (
                "mean_robustness_score",
                1.0,
                {"derivedFrom": "baseline_default"},
            )
        )
        rows.append(
            (
                "min_robustness_score",
                1.0,
                {"derivedFrom": "baseline_default"},
            )
        )
    return rows


def _baseline_raw_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> dict[str, float]:
    return {
        str(axis_id): float(raw_value)
        for axis_id, raw_value in connection.execute(
            """
            SELECT axis_id, raw_value
            FROM specimen_axes
            WHERE specimen_id = ? AND raw_value IS NOT NULL
            """,
            [specimen_id],
        ).fetchall()
    }


def _baseline_transformed_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> dict[str, float]:
    transformed_axes = {
        str(axis_id): float(transformed_value)
        for axis_id, transformed_value in connection.execute(
            """
            SELECT axis_id, transformed_value
            FROM specimen_axes
            WHERE specimen_id = ? AND transformed_value IS NOT NULL
            """,
            [specimen_id],
        ).fetchall()
    }
    if transformed_axes:
        return transformed_axes
    baseline_raw_axes = _baseline_raw_axes(connection, specimen_id=specimen_id)
    if not baseline_raw_axes:
        return {}
    return {
        str(axis_id): float(value)
        for axis_id, value in transform_axes(baseline_raw_axes).items()
        if isinstance(value, (int, float))
    }


def _context_raw_axes(payload: dict[str, Any]) -> dict[str, float]:
    endpoint_axes = payload.get("endpointRawAxes")
    if not isinstance(endpoint_axes, dict):
        return {}
    return {
        str(axis_id): float(value)
        for axis_id, value in endpoint_axes.items()
        if isinstance(value, (int, float))
    }


def _context_transformed_axes(payload: dict[str, Any]) -> dict[str, float]:
    endpoint_axes = payload.get("endpointTransformedAxes")
    if isinstance(endpoint_axes, dict):
        return {
            str(axis_id): float(value)
            for axis_id, value in endpoint_axes.items()
            if isinstance(value, (int, float))
        }
    raw_axes = _context_raw_axes(payload)
    if not raw_axes:
        return {}
    return {
        str(axis_id): float(value)
        for axis_id, value in transform_axes(raw_axes).items()
        if isinstance(value, (int, float))
    }


def _payload_metrics(payload: dict[str, Any]) -> dict[str, float]:
    for key in ("metrics", "meanMetrics", "responseMetrics"):
        value = payload.get(key)
        if isinstance(value, dict):
            return {
                str(metric_id): float(metric_value)
                for metric_id, metric_value in value.items()
                if isinstance(metric_value, (int, float))
            }
    return {}


def _reference_payload(
    payload: dict[str, Any],
    *,
    specimen_id: str,
) -> dict[str, Any]:
    raw_axes = _context_raw_axes(payload)
    transformed_axes = _context_transformed_axes(payload)
    creature_axes: dict[str, float] = {}
    creature_label_values: dict[str, str] | None = None
    endpoint_terminal = payload.get("endpointTerminalDescriptor")
    endpoint_trajectory = payload.get("endpointTrajectoryDescriptor")
    if isinstance(endpoint_terminal, dict) and isinstance(endpoint_trajectory, dict):
        endpoint_raw_axes, creature_axes = endpoint_creature_axes(
            specimen_id=specimen_id,
            terminal_descriptor=endpoint_terminal,
            trajectory_descriptor=endpoint_trajectory,
        )
        if not raw_axes:
            raw_axes = endpoint_raw_axes
        if not transformed_axes:
            transformed_axes = {
                str(axis_id): float(value)
                for axis_id, value in transform_axes(endpoint_raw_axes).items()
                if isinstance(value, (int, float))
            }
        creature_label_values = creature_labels(
            raw_axes=endpoint_raw_axes,
            creature_axes=creature_axes,
        )
    body_axes = (
        body_plan_axes(raw_axes=raw_axes, creature_axes=creature_axes) if creature_axes else {}
    )
    return {
        "rawAxes": raw_axes,
        "transformedAxes": transformed_axes,
        "metrics": _payload_metrics(payload),
        "creatureAxes": creature_axes,
        "creatureLabels": creature_label_values,
        "bodyPlanAxes": body_axes,
    }


def _baseline_context_references(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT specimen_id, environment, raw_response_json
        FROM perturbation_trials
        WHERE study_id = ? AND perturbation = 'baseline'
        ORDER BY specimen_id, environment, trial_id
        """,
        [study_id],
    ).fetchall()
    references: dict[str, dict[str, dict[str, Any]]] = {}
    for specimen_id, environment, raw_response_json in rows:
        payload = json.loads(raw_response_json) if raw_response_json else {}
        references.setdefault(str(specimen_id), {})[str(environment)] = _reference_payload(
            payload,
            specimen_id=str(specimen_id),
        )
    return references


def _target_reference(
    references_by_environment: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not references_by_environment:
        return None
    for preferred_environment in ("flat", "baseline"):
        reference = references_by_environment.get(preferred_environment)
        if reference is not None:
            return reference
    return references_by_environment[sorted(references_by_environment)[0]]


def _matched_reference(
    *,
    references_by_environment: dict[str, dict[str, Any]],
    environment: str | None,
    perturbation: str | None,
) -> dict[str, Any] | None:
    target_reference = _target_reference(references_by_environment)
    if perturbation == "baseline":
        return target_reference
    if environment is not None:
        matched = references_by_environment.get(environment)
        if matched is not None:
            return matched
    return target_reference


def _mean_abs_delta(
    baseline_axes: dict[str, float],
    context_axes: dict[str, float],
    *,
    axis_ids: tuple[str, ...],
) -> float | None:
    deltas = [
        abs(float(context_axes[axis_id]) - float(baseline_axes[axis_id]))
        for axis_id in axis_ids
        if axis_id in baseline_axes and axis_id in context_axes
    ]
    if not deltas:
        return None
    return float(mean(deltas))


def _ratio(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0.0:
        return None
    return float(value / reference)


def _snake_metric_name(metric_key: str) -> str:
    characters: list[str] = []
    for index, character in enumerate(metric_key):
        if character.isupper() and index > 0:
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)


def _metric_delta_rows(
    *,
    outcome_prefix: str,
    current_metrics: dict[str, float],
    reference_metrics: dict[str, float],
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    rows: list[tuple[str, float | None, dict[str, Any] | None]] = []
    for metric_key in REFERENCE_MOTION_METRIC_KEYS:
        current_value = current_metrics.get(metric_key)
        reference_value = reference_metrics.get(metric_key)
        ratio = _ratio(current_value, reference_value)
        if ratio is None:
            continue
        metric_name = _snake_metric_name(metric_key)
        rows.append(
            (
                f"{metric_name}_ratio_to_{outcome_prefix}",
                ratio,
                {"derivedFrom": "baseline_metric_ratio", "referenceKind": outcome_prefix},
            )
        )
        rows.append(
            (
                f"{metric_name}_overrun_cost",
                max(0.0, ratio - 1.0),
                {"derivedFrom": "baseline_metric_ratio", "referenceKind": outcome_prefix},
            )
        )
    recovery_lag = current_metrics.get("recoveryLagSteps")
    if recovery_lag is not None:
        rows.append(
            (
                "recovery_lag_steps",
                float(recovery_lag),
                {"derivedFrom": "metrics.recoveryLagSteps"},
            )
        )
    return rows


def _context_sample_step_rows(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
) -> list[tuple[int, dict[str, float]]]:
    rows = connection.execute(
        """
        SELECT step, axis_id, raw_value
        FROM context_sample_axes
        WHERE context_trial_id = ?
        ORDER BY step, axis_id
        """,
        [context_trial_id],
    ).fetchall()
    by_step: dict[int, dict[str, float]] = {}
    for step, axis_id, raw_value in rows:
        if raw_value is None:
            continue
        by_step.setdefault(int(step), {})[str(axis_id)] = float(raw_value)
    return sorted(by_step.items())


def _trace_motion_values(
    step_rows: list[tuple[int, dict[str, float]]],
) -> dict[str, float]:
    centers: list[tuple[int, float, float]] = []
    for step, axes in step_rows:
        center_x = axes.get("center_x")
        center_y = axes.get("center_y")
        if center_x is None or center_y is None:
            continue
        centers.append((step, center_x, center_y))
    if len(centers) < 2:
        return {}
    path_length = 0.0
    velocities: list[float] = []
    for previous, current in zip(centers, centers[1:], strict=False):
        delta_step = max(current[0] - previous[0], 1)
        displacement = math.hypot(current[1] - previous[1], current[2] - previous[2])
        path_length += displacement
        velocities.append(displacement / float(delta_step))
    displacement = math.hypot(
        centers[-1][1] - centers[0][1],
        centers[-1][2] - centers[0][2],
    )
    return {
        "trace_path_length": path_length,
        "trace_displacement": displacement,
        "trace_peak_center_velocity": max(velocities) if velocities else 0.0,
        "trace_mean_center_velocity": float(mean(velocities)) if velocities else 0.0,
        "trace_sample_count": float(len(centers)),
    }


def _trace_goal_rows(
    *,
    baseline_transformed_axes: dict[str, float],
    matched_reference: dict[str, dict[str, float]] | None,
    step_rows: list[tuple[int, dict[str, float]]],
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    if not step_rows:
        return []
    rows: list[tuple[str, float | None, dict[str, Any] | None]] = []
    goal_errors: list[float] = []
    class_change_count = 0
    previous_class: tuple[str, str, str, str] | None = None
    for _step, raw_axes in step_rows:
        transformed_axes = {
            str(axis_id): float(value)
            for axis_id, value in transform_axes(
                {
                    axis_id: raw_axes[axis_id]
                    for axis_id in ANATOMICAL_GOAL_AXIS_IDS
                    if axis_id in raw_axes
                }
            ).items()
            if isinstance(value, (int, float))
        }
        goal_error = _mean_abs_delta(
            baseline_transformed_axes,
            transformed_axes,
            axis_ids=ANATOMICAL_GOAL_AXIS_IDS,
        )
        if goal_error is not None:
            goal_errors.append(goal_error)
        if raw_axes:
            current_class = (
                _symmetry_class(raw_axes),
                _arrangement_class(raw_axes),
                _enclosure_class(raw_axes),
                _assembly_class(raw_axes),
            )
            if previous_class is not None and current_class != previous_class:
                class_change_count += 1
            previous_class = current_class
    if goal_errors:
        rows.append(
            (
                "peak_goal_error_score",
                float(max(goal_errors)),
                {"derivedFrom": "trace_samples", "referenceKind": "target"},
            )
        )
        rows.append(
            (
                "cumulative_goal_error_score",
                float(mean(goal_errors)),
                {"derivedFrom": "trace_samples", "referenceKind": "target"},
            )
        )
    rows.append(
        (
            "trace_class_change_count",
            float(class_change_count),
            {"derivedFrom": "trace_samples"},
        )
    )
    motion_values = _trace_motion_values(step_rows)
    for metric_name, metric_value in motion_values.items():
        rows.append(
            (
                metric_name,
                metric_value,
                {"derivedFrom": "trace_samples"},
            )
        )
    if matched_reference is not None:
        reference_metrics = matched_reference.get("metrics", {})
        trace_ratios = (
            ("trace_path_length", "pathLength"),
            ("trace_displacement", "displacement"),
            ("trace_peak_center_velocity", "centerVelocity"),
        )
        for trace_metric_name, reference_metric_name in trace_ratios:
            ratio = _ratio(
                motion_values.get(trace_metric_name),
                reference_metrics.get(reference_metric_name),
            )
            if ratio is None:
                continue
            rows.append(
                (
                    f"{trace_metric_name}_ratio_to_reference",
                    ratio,
                    {"derivedFrom": "trace_samples", "referenceKind": "matched_baseline"},
                )
            )
            rows.append(
                (
                    f"{trace_metric_name}_overrun_cost",
                    max(0.0, ratio - 1.0),
                    {"derivedFrom": "trace_samples", "referenceKind": "matched_baseline"},
                )
            )
    return rows


def _class_shift_values(
    *,
    baseline_raw_axes: dict[str, float],
    context_raw_axes: dict[str, float],
) -> dict[str, float]:
    if not baseline_raw_axes or not context_raw_axes:
        return {}
    return {
        "symmetry_class_shift": float(
            _symmetry_class(baseline_raw_axes) != _symmetry_class(context_raw_axes)
        ),
        "arrangement_class_shift": float(
            _arrangement_class(baseline_raw_axes) != _arrangement_class(context_raw_axes)
        ),
        "enclosure_class_shift": float(
            _enclosure_class(baseline_raw_axes) != _enclosure_class(context_raw_axes)
        ),
        "assembly_class_shift": float(
            _assembly_class(baseline_raw_axes) != _assembly_class(context_raw_axes)
        ),
    }


def _class_shift_rows(
    *,
    baseline_raw_axes: dict[str, float],
    context_raw_axes: dict[str, float],
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    comparisons = _class_shift_values(
        baseline_raw_axes=baseline_raw_axes,
        context_raw_axes=context_raw_axes,
    )
    if not comparisons:
        return []
    class_shift_score = sum(comparisons.values()) / float(len(comparisons))
    rows = [
        (
            outcome_kind,
            outcome_value,
            {"derivedFrom": "anatomical_class_comparison"},
        )
        for outcome_kind, outcome_value in comparisons.items()
    ]
    rows.append(
        (
            "class_shift_score",
            class_shift_score,
            {"derivedFrom": "anatomical_class_comparison"},
        )
    )
    return [
        (outcome_kind, float(outcome_value), dict(metadata) if metadata is not None else None)
        for outcome_kind, outcome_value, metadata in rows
    ]


def _baseline_creature_reference(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT creature_states_vw.state_id,
               creature_states_vw.coherence_class,
               creature_states_vw.organization_class,
               creature_states_vw.mobility_class,
               creature_states_vw.creature_bucket
        FROM creature_states_vw
        LEFT JOIN (
            SELECT state_id, COUNT(*) AS signal_count
            FROM creature_signal_axes
            GROUP BY state_id
        ) AS creature_signal_counts
          ON creature_signal_counts.state_id = creature_states_vw.state_id
        WHERE creature_states_vw.specimen_id = ?
          AND creature_states_vw.source_kind = 'specimen_baseline'
          AND creature_states_vw.context_kind = 'baseline'
        ORDER BY coalesce(creature_signal_counts.signal_count, 0) DESC,
                 creature_states_vw.study_id,
                 creature_states_vw.state_id
        LIMIT 1
        """,
        [specimen_id],
    ).fetchone()
    if row is None:
        return None
    state_id = str(row[0])
    raw_axes = _baseline_raw_axes(connection, specimen_id=specimen_id)
    creature_axes = {
        str(axis_id): float(raw_value)
        for axis_id, raw_value in connection.execute(
            """
            SELECT axis_id, raw_value
            FROM creature_signal_axes
            WHERE state_id = ? AND raw_value IS NOT NULL
            """,
            [state_id],
        ).fetchall()
    }
    if not creature_axes:
        return None
    labels = {
        "coherence_class": str(row[1]) if row[1] is not None else "",
        "organization_class": str(row[2]) if row[2] is not None else "",
        "mobility_class": str(row[3]) if row[3] is not None else "",
        "creature_bucket": str(row[4]) if row[4] is not None else "",
    }
    return {
        "rawAxes": raw_axes,
        "creatureAxes": creature_axes,
        "creatureLabels": labels,
        "bodyPlanAxes": body_plan_axes(raw_axes=raw_axes, creature_axes=creature_axes),
    }


def _context_creature_reference(
    *,
    specimen_id: str,
    payload: dict[str, Any],
    context_raw_axes: dict[str, float],
) -> dict[str, Any] | None:
    endpoint_terminal = payload.get("endpointTerminalDescriptor")
    endpoint_trajectory = payload.get("endpointTrajectoryDescriptor")
    if not isinstance(endpoint_terminal, dict) or not isinstance(endpoint_trajectory, dict):
        return None
    endpoint_raw_axes, creature_axes = endpoint_creature_axes(
        specimen_id=specimen_id,
        terminal_descriptor=endpoint_terminal,
        trajectory_descriptor=endpoint_trajectory,
    )
    raw_axes = context_raw_axes or endpoint_raw_axes
    labels = creature_labels(raw_axes=raw_axes, creature_axes=creature_axes)
    return {
        "rawAxes": raw_axes,
        "creatureAxes": creature_axes,
        "creatureLabels": labels,
        "bodyPlanAxes": body_plan_axes(raw_axes=raw_axes, creature_axes=creature_axes),
    }


def _body_plan_rows(
    *,
    baseline_reference: dict[str, Any] | None,
    matched_reference: dict[str, Any] | None,
    current_reference: dict[str, Any] | None,
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    if baseline_reference is None or current_reference is None:
        return []
    baseline_body_axes = baseline_reference.get("bodyPlanAxes")
    baseline_labels = baseline_reference.get("creatureLabels")
    current_body_axes = current_reference.get("bodyPlanAxes")
    current_labels = current_reference.get("creatureLabels")
    if not isinstance(baseline_body_axes, dict) or not isinstance(current_body_axes, dict):
        return []
    if not isinstance(baseline_labels, dict) or not isinstance(current_labels, dict):
        return []
    rows: list[tuple[str, float | None, dict[str, Any] | None]] = []
    body_plan_error = body_plan_error_score(baseline_body_axes, current_body_axes)
    if body_plan_error is not None:
        rows.append(
            (
                "body_plan_error_score",
                body_plan_error,
                {"derivedFrom": "body_plan_axes", "referenceKind": "target"},
            )
        )
    rows.append(
        (
            "body_plan_class_shift_score",
            body_plan_class_shift_score(baseline_labels, current_labels),
            {"derivedFrom": "creature_labels", "referenceKind": "target"},
        )
    )
    target_coherence = baseline_body_axes.get("largest_component_share_final")
    current_coherence = current_body_axes.get("largest_component_share_final")
    if isinstance(target_coherence, (int, float)) and isinstance(current_coherence, (int, float)):
        rows.append(
            (
                "coherence_drop_score",
                max(0.0, float(target_coherence) - float(current_coherence)),
                {"derivedFrom": "largest_component_share_final", "referenceKind": "target"},
            )
        )
    organization_delta = max(
        0.0,
        organization_score(
            raw_axes=baseline_reference["rawAxes"],
            creature_axes=baseline_reference["creatureAxes"],
        )
        - organization_score(
            raw_axes=current_reference["rawAxes"],
            creature_axes=current_reference["creatureAxes"],
        ),
    )
    rows.append(
        (
            "organization_drop_score",
            organization_delta,
            {"derivedFrom": "creature_labels", "referenceKind": "target"},
        )
    )
    target_motion = baseline_body_axes.get("whole_body_motion_score")
    current_motion = current_body_axes.get("whole_body_motion_score")
    if isinstance(target_motion, (int, float)) and isinstance(current_motion, (int, float)):
        rows.append(
            (
                "whole_body_motion_change_score",
                abs(float(target_motion) - float(current_motion)),
                {"derivedFrom": "whole_body_motion_score", "referenceKind": "target"},
            )
        )
    if matched_reference is None:
        return rows
    matched_body_axes = matched_reference.get("bodyPlanAxes")
    matched_labels = matched_reference.get("creatureLabels")
    if not isinstance(matched_body_axes, dict) or not isinstance(matched_labels, dict):
        return rows
    matched_error = body_plan_error_score(matched_body_axes, current_body_axes)
    if matched_error is not None:
        rows.append(
            (
                "matched_body_plan_error_score",
                matched_error,
                {"derivedFrom": "body_plan_axes", "referenceKind": "matched_baseline"},
            )
        )
    rows.append(
        (
            "matched_body_plan_class_shift_score",
            body_plan_class_shift_score(matched_labels, current_labels),
            {"derivedFrom": "creature_labels", "referenceKind": "matched_baseline"},
        )
    )
    matched_coherence = matched_body_axes.get("largest_component_share_final")
    if isinstance(matched_coherence, (int, float)) and isinstance(current_coherence, (int, float)):
        rows.append(
            (
                "matched_coherence_drop_score",
                max(0.0, float(matched_coherence) - float(current_coherence)),
                {
                    "derivedFrom": "largest_component_share_final",
                    "referenceKind": "matched_baseline",
                },
            )
        )
    matched_organization_delta = max(
        0.0,
        organization_score(
            raw_axes=matched_reference["rawAxes"],
            creature_axes=matched_reference["creatureAxes"],
        )
        - organization_score(
            raw_axes=current_reference["rawAxes"],
            creature_axes=current_reference["creatureAxes"],
        ),
    )
    rows.append(
        (
            "matched_organization_drop_score",
            matched_organization_delta,
            {"derivedFrom": "creature_labels", "referenceKind": "matched_baseline"},
        )
    )
    matched_motion = matched_body_axes.get("whole_body_motion_score")
    if isinstance(matched_motion, (int, float)) and isinstance(current_motion, (int, float)):
        rows.append(
            (
                "matched_whole_body_motion_change_score",
                abs(float(matched_motion) - float(current_motion)),
                {
                    "derivedFrom": "whole_body_motion_score",
                    "referenceKind": "matched_baseline",
                },
            )
        )
    return rows


def _goal_error_rows(
    *,
    baseline_raw_axes: dict[str, float],
    baseline_transformed_axes: dict[str, float],
    context_raw_axes: dict[str, float],
    context_transformed_axes: dict[str, float],
    matched_reference: dict[str, dict[str, float]] | None,
    current_metrics: dict[str, float],
    class_shift_values: dict[str, float],
    trace_step_rows: list[tuple[int, dict[str, float]]],
) -> list[tuple[str, float | None, dict[str, Any] | None]]:
    rows: list[tuple[str, float | None, dict[str, Any] | None]] = []
    goal_error_score = _mean_abs_delta(
        baseline_transformed_axes,
        context_transformed_axes,
        axis_ids=ANATOMICAL_GOAL_AXIS_IDS,
    )
    if goal_error_score is not None:
        rows.append(
            (
                "goal_error_score",
                goal_error_score,
                {"derivedFrom": "transformed_anatomical_axes", "referenceKind": "target"},
            )
        )

    center_offset_delta = None
    if "center_offset" in baseline_raw_axes and "center_offset" in context_raw_axes:
        center_offset_delta = abs(
            float(context_raw_axes["center_offset"]) - float(baseline_raw_axes["center_offset"])
        )
        rows.append(
            (
                "center_offset_delta_to_target",
                center_offset_delta,
                {"derivedFrom": "raw_anatomical_axes", "referenceKind": "target"},
            )
        )

    if "fragmentation" in baseline_raw_axes and "fragmentation" in context_raw_axes:
        rows.append(
            (
                "fragmentation_delta_to_target",
                abs(
                    float(context_raw_axes["fragmentation"])
                    - float(baseline_raw_axes["fragmentation"])
                ),
                {"derivedFrom": "raw_anatomical_axes", "referenceKind": "target"},
            )
        )
    if "cavity_count" in baseline_raw_axes and "cavity_count" in context_raw_axes:
        rows.append(
            (
                "cavity_count_delta_to_target",
                abs(
                    float(context_raw_axes["cavity_count"])
                    - float(baseline_raw_axes["cavity_count"])
                ),
                {"derivedFrom": "raw_anatomical_axes", "referenceKind": "target"},
            )
        )

    matched_error_score = None
    if matched_reference is not None:
        matched_error_score = _mean_abs_delta(
            matched_reference.get("transformedAxes", {}),
            context_transformed_axes,
            axis_ids=ANATOMICAL_GOAL_AXIS_IDS,
        )
        if matched_error_score is not None:
            rows.append(
                (
                    "matched_baseline_error_score",
                    matched_error_score,
                    {
                        "derivedFrom": "transformed_anatomical_axes",
                        "referenceKind": "matched_baseline",
                    },
                )
            )
        rows.extend(
            _metric_delta_rows(
                outcome_prefix="reference",
                current_metrics=current_metrics,
                reference_metrics=matched_reference.get("metrics", {}),
            )
        )
    rows.extend(
        _trace_goal_rows(
            baseline_transformed_axes=baseline_transformed_axes,
            matched_reference=matched_reference,
            step_rows=trace_step_rows,
        )
    )

    control_cost_terms: list[float] = []
    if goal_error_score is not None:
        control_cost_terms.append(goal_error_score)
    peak_goal_error_score = next(
        (
            float(outcome_value)
            for outcome_kind, outcome_value, _metadata in rows
            if outcome_kind == "peak_goal_error_score" and outcome_value is not None
        ),
        None,
    )
    if peak_goal_error_score is not None:
        control_cost_terms.append(peak_goal_error_score)
    class_shift_score = (
        sum(class_shift_values.values()) / float(len(class_shift_values))
        if class_shift_values
        else None
    )
    if class_shift_score is not None:
        control_cost_terms.append(class_shift_score)
    overrun_rows = {
        outcome_kind: float(outcome_value)
        for outcome_kind, outcome_value, _metadata in rows
        if outcome_value is not None
        and outcome_kind
        in {
            "path_length_overrun_cost",
            "displacement_overrun_cost",
            "center_velocity_overrun_cost",
            "trace_path_length_overrun_cost",
            "trace_displacement_overrun_cost",
            "trace_peak_center_velocity_overrun_cost",
        }
    }
    trace_overrun_kinds = (
        "trace_path_length_overrun_cost",
        "trace_displacement_overrun_cost",
        "trace_peak_center_velocity_overrun_cost",
    )
    legacy_overrun_kinds = (
        "path_length_overrun_cost",
        "displacement_overrun_cost",
        "center_velocity_overrun_cost",
    )
    if any(kind in overrun_rows for kind in trace_overrun_kinds):
        control_cost_terms.extend(
            overrun_rows[kind] for kind in trace_overrun_kinds if kind in overrun_rows
        )
    else:
        control_cost_terms.extend(
            overrun_rows[kind] for kind in legacy_overrun_kinds if kind in overrun_rows
        )
    if control_cost_terms:
        rows.append(
            (
                "control_cost_proxy",
                float(mean(control_cost_terms)),
                {"derivedFrom": "goal_error_peak_error_class_shift_and_motion_overrun"},
            )
        )
    return rows


def derive_context_outcomes(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
    if study_id is None:
        study_ids = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT study_id
                FROM studies
                WHERE study_kind = 'focal_batch'
                ORDER BY study_id
                """
            ).fetchall()
        ]
    else:
        study_ids = [study_id]

    updated = 0
    for resolved_study_id in study_ids:
        baseline_axes_by_specimen: dict[str, dict[str, float]] = {}
        baseline_transformed_axes_by_specimen: dict[str, dict[str, float]] = {}
        baseline_creature_refs_by_specimen: dict[str, dict[str, Any] | None] = {}
        baseline_context_refs_by_specimen = _baseline_context_references(
            connection, study_id=resolved_study_id
        )
        trial_rows = connection.execute(
            """
            SELECT trial_id, specimen_id, environment, perturbation, repeat_index,
                   results_path, summary_path, raw_response_json
            FROM perturbation_trials
            WHERE study_id = ?
            ORDER BY specimen_id, environment, perturbation, repeat_index, trial_id
            """,
            [resolved_study_id],
        ).fetchall()
        per_specimen_rows: dict[str, list[dict[str, Any]]] = {}
        for (
            trial_id,
            specimen_id,
            environment,
            perturbation,
            repeat_index,
            results_path,
            summary_path,
            raw_response_json,
        ) in trial_rows:
            payload = json.loads(raw_response_json) if raw_response_json else {}
            context_kind = _context_kind(environment, perturbation)
            context_id = register_context(
                connection,
                study_id=resolved_study_id,
                context_kind=context_kind,
                label=_context_label(environment, perturbation),
                metadata_json={
                    "environment": environment,
                    "perturbation": perturbation,
                },
            )
            control_program_id = None
            if perturbation != "baseline":
                control_program_id = register_control_program(
                    connection,
                    study_id=resolved_study_id,
                    label=str(perturbation),
                    sequence_index=0,
                    family=str(perturbation),
                    payload={"environment": environment, "perturbation": perturbation},
                    metadata_json={"contextKind": context_kind},
                )
            context_trial_id = str(trial_id)
            per_specimen_rows.setdefault(str(specimen_id), []).append(
                {
                    "context_trial_id": context_trial_id,
                    "specimen_id": str(specimen_id),
                    "study_id": resolved_study_id,
                    "context_id": context_id,
                    "control_program_id": control_program_id,
                    "environment": environment,
                    "perturbation": perturbation,
                    "repeat_index": int(repeat_index),
                    "results_path": results_path,
                    "summary_path": summary_path,
                    "provenance_json": {
                        "perturbationTrialId": trial_id,
                        "rawResponse": payload,
                    },
                }
            )
            baseline_raw_axes = baseline_axes_by_specimen.setdefault(
                str(specimen_id),
                _baseline_raw_axes(connection, specimen_id=str(specimen_id)),
            )
            baseline_transformed_axes = baseline_transformed_axes_by_specimen.setdefault(
                str(specimen_id),
                _baseline_transformed_axes(connection, specimen_id=str(specimen_id)),
            )
            context_raw_axes = _context_raw_axes(payload)
            context_transformed_axes = _context_transformed_axes(payload)
            current_metrics = _payload_metrics(payload)
            class_shift_values = _class_shift_values(
                baseline_raw_axes=baseline_raw_axes,
                context_raw_axes=context_raw_axes,
            )
            baseline_creature_reference = baseline_creature_refs_by_specimen.setdefault(
                str(specimen_id),
                _baseline_creature_reference(connection, specimen_id=str(specimen_id)),
            )
            matched_reference = _matched_reference(
                references_by_environment=baseline_context_refs_by_specimen.get(
                    str(specimen_id), {}
                ),
                environment=str(environment) if environment is not None else None,
                perturbation=str(perturbation) if perturbation is not None else None,
            )
            current_creature_reference = _context_creature_reference(
                specimen_id=str(specimen_id),
                payload=payload,
                context_raw_axes=context_raw_axes,
            )
            replace_context_outcomes(
                connection,
                context_trial_id=context_trial_id,
                rows=[
                    *_outcome_rows_from_payload(payload, context_kind=context_kind),
                    *_class_shift_rows(
                        baseline_raw_axes=baseline_raw_axes,
                        context_raw_axes=context_raw_axes,
                    ),
                    *_goal_error_rows(
                        baseline_raw_axes=baseline_raw_axes,
                        baseline_transformed_axes=baseline_transformed_axes,
                        context_raw_axes=context_raw_axes,
                        context_transformed_axes=context_transformed_axes,
                        matched_reference=matched_reference,
                        current_metrics=current_metrics,
                        class_shift_values=class_shift_values,
                        trace_step_rows=_context_sample_step_rows(
                            connection,
                            context_trial_id=context_trial_id,
                        ),
                    ),
                    *_body_plan_rows(
                        baseline_reference=baseline_creature_reference,
                        matched_reference=matched_reference,
                        current_reference=current_creature_reference,
                    ),
                ],
            )
            updated += 1
        for specimen_id, rows in per_specimen_rows.items():
            replace_context_trials(
                connection,
                study_id=resolved_study_id,
                specimen_id=specimen_id,
                rows=rows,
            )
    return updated
