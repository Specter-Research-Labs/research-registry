from __future__ import annotations

import json
import math
from statistics import mean
from typing import Any

from duckdb import DuckDBPyConnection

from .warehouse import replace_trajectory_segments, stable_id


def _sample_axis_series(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
) -> dict[str, list[tuple[int, float]]]:
    rows = connection.execute(
        """
        SELECT axis_id, step, raw_value
        FROM development_sample_axes
        WHERE specimen_id = ?
        ORDER BY axis_id, step
        """,
        [specimen_id],
    ).fetchall()
    series: dict[str, list[tuple[int, float]]] = {}
    for axis_id, step, raw_value in rows:
        if raw_value is None:
            continue
        series.setdefault(str(axis_id), []).append((int(step), float(raw_value)))
    return series


def _peak_abs(values: list[float]) -> float | None:
    if not values:
        return None
    return max(abs(value) for value in values)


def _context_sample_axis_series(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
) -> dict[str, list[tuple[int, float]]]:
    rows = connection.execute(
        """
        SELECT axis_id, step, raw_value
        FROM context_sample_axes
        WHERE context_trial_id = ?
        ORDER BY axis_id, step
        """,
        [context_trial_id],
    ).fetchall()
    series: dict[str, list[tuple[int, float]]] = {}
    for axis_id, step, raw_value in rows:
        if raw_value is None:
            continue
        series.setdefault(str(axis_id), []).append((int(step), float(raw_value)))
    return series


def _center_trace_summary(
    axis_series: dict[str, list[tuple[int, float]]],
) -> dict[str, float] | None:
    x_series = axis_series.get("center_x", [])
    y_series = axis_series.get("center_y", [])
    if len(x_series) < 2 or len(y_series) < 2 or len(x_series) != len(y_series):
        return None
    path_length = 0.0
    velocities: list[float] = []
    for previous_x, current_x, previous_y, current_y in zip(
        x_series,
        x_series[1:],
        y_series,
        y_series[1:],
        strict=False,
    ):
        delta_step = max(current_x[0] - previous_x[0], 1)
        displacement = math.hypot(current_x[1] - previous_x[1], current_y[1] - previous_y[1])
        path_length += displacement
        velocities.append(displacement / float(delta_step))
    displacement = math.hypot(
        x_series[-1][1] - x_series[0][1],
        y_series[-1][1] - y_series[0][1],
    )
    return {
        "pathLength": path_length,
        "displacement": displacement,
        "peakCenterVelocity": max(velocities) if velocities else 0.0,
        "meanCenterVelocity": float(mean(velocities)) if velocities else 0.0,
    }


def _context_metrics(raw_response: dict[str, Any]) -> dict[str, float]:
    for key in ("metrics", "meanMetrics", "responseMetrics"):
        value = raw_response.get(key)
        if isinstance(value, dict):
            return {
                str(metric_id): float(metric_value)
                for metric_id, metric_value in value.items()
                if isinstance(metric_value, (int, float))
            }
    return {}


def _context_outcome_values(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
) -> dict[str, float]:
    return {
        str(outcome_kind): float(outcome_value)
        for outcome_kind, outcome_value in connection.execute(
            """
            SELECT outcome_kind, outcome_value
            FROM context_outcomes
            WHERE context_trial_id = ? AND outcome_value IS NOT NULL
            """,
            [context_trial_id],
        ).fetchall()
    }


def _baseline_segment_row(
    *,
    study_id: str,
    specimen_id: str,
    context_id: str | None,
    provenance_json: str | None,
    axis_series: dict[str, list[tuple[int, float]]],
) -> dict[str, Any] | None:
    if not axis_series:
        return None
    steps = sorted({step for values in axis_series.values() for step, _value in values})
    if not steps:
        return None
    provenance = json.loads(provenance_json) if provenance_json else {}
    center_velocity_values = [value for _, value in axis_series.get("center_velocity", [])]
    coverage_values = [value for _, value in axis_series.get("coverage", [])]
    elongation_values = [value for _, value in axis_series.get("elongation", [])]
    return {
        "segment_id": stable_id("trajectory-segment", study_id, specimen_id, "baseline"),
        "study_id": study_id,
        "specimen_id": specimen_id,
        "context_trial_id": None,
        "context_id": context_id,
        "segment_kind": "baseline_development",
        "start_step": steps[0],
        "end_step": steps[-1],
        "segment_index": 0,
        "summary_json": {
            "sampleCount": len(steps),
            "stepCount": steps[-1] - steps[0] if len(steps) > 1 else 0,
            "peakCenterVelocity": max(center_velocity_values) if center_velocity_values else None,
            "meanCenterVelocity": (
                float(mean(center_velocity_values)) if center_velocity_values else None
            ),
            "coverageRange": (
                max(coverage_values) - min(coverage_values) if coverage_values else None
            ),
            "elongationRange": (
                max(elongation_values) - min(elongation_values) if elongation_values else None
            ),
            "peakAxisExcursions": {
                axis_id: _peak_abs([value for _, value in values])
                for axis_id, values in sorted(axis_series.items())
            },
            "trajectory": provenance.get("trajectory"),
        },
    }


def _context_segment_row(
    *,
    study_id: str,
    context_trial_id: str,
    specimen_id: str,
    context_id: str,
    raw_response: dict[str, Any],
    outcome_values: dict[str, float],
    axis_series: dict[str, list[tuple[int, float]]],
) -> dict[str, Any]:
    mean_metrics = _context_metrics(raw_response)
    trace_steps = sorted({step for values in axis_series.values() for step, _value in values})
    trace_summary = _center_trace_summary(axis_series)
    recovery_lag = mean_metrics.get("recoveryLagSteps")
    end_step = trace_steps[-1] if trace_steps else (
        int(recovery_lag) if isinstance(recovery_lag, int) else None
    )
    return {
        "segment_id": stable_id("trajectory-segment", study_id, context_trial_id, "context"),
        "study_id": study_id,
        "specimen_id": specimen_id,
        "context_trial_id": context_trial_id,
        "context_id": context_id,
        "segment_kind": "context_response",
        "start_step": trace_steps[0] if trace_steps else 0,
        "end_step": end_step,
        "segment_index": 0,
        "summary_json": {
            "sampleCount": len(trace_steps) if trace_steps else None,
            "stepCount": (
                trace_steps[-1] - trace_steps[0]
                if len(trace_steps) > 1
                else 0 if trace_steps else None
            ),
            "meanFragilityScore": raw_response.get("meanFragilityScore"),
            "meanRobustnessScore": raw_response.get("meanRobustnessScore"),
            "meanMetrics": mean_metrics,
            "pathLength": mean_metrics.get("pathLength"),
            "displacement": mean_metrics.get("displacement"),
            "centerVelocity": mean_metrics.get("centerVelocity"),
            "tracePathLength": None if trace_summary is None else trace_summary["pathLength"],
            "traceDisplacement": (
                None if trace_summary is None else trace_summary["displacement"]
            ),
            "tracePeakCenterVelocity": (
                None if trace_summary is None else trace_summary["peakCenterVelocity"]
            ),
            "traceMeanCenterVelocity": (
                None if trace_summary is None else trace_summary["meanCenterVelocity"]
            ),
            "peakAxisExcursions": {
                axis_id: _peak_abs([value for _, value in values])
                for axis_id, values in sorted(axis_series.items())
            }
            if axis_series
            else None,
            "recoveryLagSteps": mean_metrics.get("recoveryLagSteps"),
            "goalErrorScore": outcome_values.get("goal_error_score"),
            "peakGoalErrorScore": outcome_values.get("peak_goal_error_score"),
            "cumulativeGoalErrorScore": outcome_values.get("cumulative_goal_error_score"),
            "bodyPlanErrorScore": outcome_values.get("body_plan_error_score"),
            "bodyPlanClassShiftScore": outcome_values.get("body_plan_class_shift_score"),
            "coherenceDropScore": outcome_values.get("coherence_drop_score"),
            "organizationDropScore": outcome_values.get("organization_drop_score"),
            "wholeBodyMotionChangeScore": outcome_values.get(
                "whole_body_motion_change_score"
            ),
            "traceClassChangeCount": outcome_values.get("trace_class_change_count"),
            "matchedBaselineErrorScore": outcome_values.get("matched_baseline_error_score"),
            "classShiftScore": outcome_values.get("class_shift_score"),
            "controlCostProxy": outcome_values.get("control_cost_proxy"),
            "pathLengthRatioToReference": outcome_values.get("path_length_ratio_to_reference"),
            "displacementRatioToReference": outcome_values.get("displacement_ratio_to_reference"),
            "centerVelocityRatioToReference": outcome_values.get(
                "center_velocity_ratio_to_reference"
            ),
            "tracePathLengthRatioToReference": outcome_values.get(
                "trace_path_length_ratio_to_reference"
            ),
            "traceDisplacementRatioToReference": outcome_values.get(
                "trace_displacement_ratio_to_reference"
            ),
            "tracePeakCenterVelocityRatioToReference": outcome_values.get(
                "trace_peak_center_velocity_ratio_to_reference"
            ),
        },
    }


def derive_trajectories(connection: DuckDBPyConnection, *, study_id: str | None = None) -> int:
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
        specimen_rows = connection.execute(
            """
            SELECT specimens.specimen_id, baseline_contexts.context_id, specimens.provenance_json
            FROM study_specimens
            JOIN specimens USING (specimen_id)
            LEFT JOIN (
                SELECT study_id, min(context_id) AS context_id
                FROM contexts
                WHERE context_kind = 'baseline'
                GROUP BY study_id
            ) AS baseline_contexts
              ON baseline_contexts.study_id = study_specimens.study_id
            WHERE study_specimens.study_id = ?
            ORDER BY specimens.specimen_id
            """,
            [resolved_study_id],
        ).fetchall()
        for specimen_id, context_id, provenance_json in specimen_rows:
            row = _baseline_segment_row(
                study_id=resolved_study_id,
                specimen_id=str(specimen_id),
                context_id=str(context_id) if context_id is not None else None,
                provenance_json=provenance_json,
                axis_series=_sample_axis_series(connection, specimen_id=str(specimen_id)),
            )
            if row is None:
                continue
            replace_trajectory_segments(
                connection,
                study_id=resolved_study_id,
                specimen_id=str(specimen_id),
                rows=[row],
            )
            updated += 1

        context_rows = connection.execute(
            """
            SELECT context_trial_id, specimen_id, context_id, provenance_json
            FROM context_trials
            WHERE study_id = ?
            ORDER BY context_trial_id
            """,
            [resolved_study_id],
        ).fetchall()
        for context_trial_id, specimen_id, context_id, provenance_json in context_rows:
            provenance = json.loads(provenance_json) if provenance_json else {}
            raw_response = provenance.get("rawResponse")
            if not isinstance(raw_response, dict):
                continue
            outcome_values = _context_outcome_values(
                connection, context_trial_id=str(context_trial_id)
            )
            axis_series = _context_sample_axis_series(
                connection,
                context_trial_id=str(context_trial_id),
            )
            replace_trajectory_segments(
                connection,
                study_id=resolved_study_id,
                context_trial_id=str(context_trial_id),
                rows=[
                    _context_segment_row(
                        study_id=resolved_study_id,
                        context_trial_id=str(context_trial_id),
                        specimen_id=str(specimen_id),
                        context_id=str(context_id),
                        raw_response=raw_response,
                        outcome_values=outcome_values,
                        axis_series=axis_series,
                    )
                ],
            )
            updated += 1
    return updated
