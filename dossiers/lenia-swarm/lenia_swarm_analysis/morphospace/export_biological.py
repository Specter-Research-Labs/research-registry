from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from statistics import mean, median
from typing import Any

from duckdb import DuckDBPyConnection

from .export_legacy import export_topology_packet

CONTEXT_SUMMARY_METRICS = (
    "meanFragilityScore",
    "meanRobustnessScore",
    "classShiftScore",
    "goalErrorScore",
    "peakGoalErrorScore",
    "cumulativeGoalErrorScore",
    "bodyPlanErrorScore",
    "bodyPlanClassShiftScore",
    "coherenceDropScore",
    "organizationDropScore",
    "wholeBodyMotionChangeScore",
    "matchedBaselineErrorScore",
    "controlCostProxy",
    "pathLengthRatioToReference",
    "displacementRatioToReference",
    "centerVelocityRatioToReference",
    "traceClassChangeCount",
    "tracePathLength",
    "traceDisplacement",
    "tracePeakCenterVelocity",
    "traceMeanCenterVelocity",
    "traceSampleCount",
    "tracePathLengthRatioToReference",
    "traceDisplacementRatioToReference",
    "tracePeakCenterVelocityRatioToReference",
    "recoveryLagSteps",
)


def _group_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _state_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT creature_states_vw.state_id, creature_states_vw.specimen_id,
               creature_states_vw.context_id, creature_states_vw.context_kind,
               creature_states_vw.context_label, creature_states_vw.family_kind,
               creature_states_vw.regime_family, creature_states_vw.geometry_family,
               creature_states_vw.canonical_family, creature_states_vw.state_json,
               creature_states_vw.coherence_class, creature_states_vw.organization_class,
               creature_states_vw.mobility_class, creature_states_vw.creature_bucket,
               creature_states_vw.largest_component_share_final,
               creature_states_vw.coherence_mean,
               creature_states_vw.coherence_min,
               creature_states_vw.fragmentation_peak,
               creature_states_vw.fragmentation_variability,
               creature_states_vw.part_persistence_score,
               creature_states_vw.shape_persistence_score,
               creature_states_vw.symmetry_stability_score,
               creature_states_vw.polarity_stability_score,
               creature_states_vw.enclosure_persistence_score,
               creature_states_vw.whole_body_motion_score,
               creature_states_vw.deformation_without_dissolution_score,
               creature_states_vw.localization_score,
               creature_states_vw.extent_stability_score,
               creature_states_vw.temporal_individuality_score
        FROM creature_states_vw
        WHERE creature_states_vw.study_id = ?
        ORDER BY creature_states_vw.state_id
        """,
        [study_id],
    ).fetchall()
    resolved: list[dict[str, Any]] = []
    for row in rows:
        state_id = str(row[0])
        state_json = json.loads(row[9]) if row[9] else {}
        axes = {
            str(axis_id): {
                "raw": raw_value,
                "transformed": transformed_value,
            }
            for axis_id, raw_value, transformed_value in connection.execute(
                """
                SELECT axis_id, raw_value, transformed_value
                FROM anatomical_state_axes
                WHERE state_id = ?
                ORDER BY axis_id
                """,
                [state_id],
            ).fetchall()
        }
        resolved.append(
            {
                "stateId": state_id,
                "specimenId": row[1],
                "contextId": row[2],
                "contextKind": row[3],
                "contextLabel": row[4],
                "familyKind": row[5],
                "regimeFamily": row[6],
                "geometryFamily": row[7],
                "canonicalFamily": row[8],
                "state": state_json,
                "axes": axes,
                "creatureLabels": {
                    "coherenceClass": row[10],
                    "organizationClass": row[11],
                    "mobilityClass": row[12],
                    "creatureBucket": row[13],
                },
                "creatureSignals": {
                    "largestComponentShareFinal": row[14],
                    "coherenceMean": row[15],
                    "coherenceMin": row[16],
                    "fragmentationPeak": row[17],
                    "fragmentationVariability": row[18],
                    "partPersistenceScore": row[19],
                    "shapePersistenceScore": row[20],
                    "symmetryStabilityScore": row[21],
                    "polarityStabilityScore": row[22],
                    "enclosurePersistenceScore": row[23],
                    "wholeBodyMotionScore": row[24],
                    "deformationWithoutDissolutionScore": row[25],
                    "localizationScore": row[26],
                    "extentStabilityScore": row[27],
                    "temporalIndividualityScore": row[28],
                },
            }
        )
    return resolved


def _group_summary(
    rows: list[dict[str, Any]],
    *,
    group_key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(group_key)
        if isinstance(value, str) and value:
            grouped[value].append(row)
    summaries: list[dict[str, Any]] = []
    for group_value, group_rows in sorted(grouped.items()):
        axis_values: dict[str, list[float]] = defaultdict(list)
        for row in group_rows:
            for axis_id, axis_payload in row["axes"].items():
                raw_value = axis_payload.get("raw")
                if isinstance(raw_value, (int, float)):
                    axis_values[str(axis_id)].append(float(raw_value))
        summaries.append(
            {
                group_key: group_value,
                "stateCount": len(group_rows),
                "medianAxes": {
                    axis_id: float(median(values))
                    for axis_id, values in sorted(axis_values.items())
                    if values
                },
            }
        )
    return summaries


def _creature_group_summary(
    rows: list[dict[str, Any]],
    *,
    group_key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(group_key)
        if isinstance(value, str) and value:
            grouped[value].append(row)
    summaries: list[dict[str, Any]] = []
    for group_value, group_rows in sorted(grouped.items()):
        signal_values: dict[str, list[float]] = defaultdict(list)
        for row in group_rows:
            creature_signals = row.get("creatureSignals")
            if not isinstance(creature_signals, dict):
                continue
            for signal_id, value in creature_signals.items():
                if isinstance(value, (int, float)):
                    signal_values[str(signal_id)].append(float(value))
        summaries.append(
            {
                group_key: group_value,
                "stateCount": len(group_rows),
                "byCreatureBucket": _group_counts(group_rows, "creatureBucket"),
                "medianSignals": {
                    signal_id: float(median(values))
                    for signal_id, values in sorted(signal_values.items())
                    if values
                },
            }
        )
    return summaries


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = max(0.0, min(1.0, fraction)) * float(len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _bootstrap_mean_interval(
    values: list[float],
    *,
    seed_key: str,
    draws: int = 512,
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1:
        value = float(values[0])
        return value, value
    seed = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    sample_count = len(values)
    means: list[float] = []
    for _ in range(draws):
        sampled = [values[rng.randrange(sample_count)] for _ in range(sample_count)]
        means.append(float(mean(sampled)))
    return _quantile(means, 0.025), _quantile(means, 0.975)


def _metric_distribution_summary(
    values: list[float],
    *,
    seed_key: str,
) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p05": None,
            "p95": None,
            "ciLow": None,
            "ciHigh": None,
        }
    ci_low, ci_high = _bootstrap_mean_interval(values, seed_key=seed_key)
    return {
        "count": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "p05": _quantile(values, 0.05),
        "p95": _quantile(values, 0.95),
        "ciLow": ci_low,
        "ciHigh": ci_high,
    }


def _metric_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]


def _reference_context_kind(context_kind: str) -> str:
    if context_kind == "lesion_plus_obstacle":
        return "obstacle"
    return "baseline"


def _summarize_group(
    group_rows: list[dict[str, Any]],
    *,
    seed_prefix: str,
    target_reference_rows: list[dict[str, Any]] | None = None,
    matched_reference_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    def average(field: str) -> float | None:
        values = _metric_values(group_rows, field)
        if not values:
            return None
        return float(mean(values))

    metric_summaries = {
        metric_name: _metric_distribution_summary(
            _metric_values(group_rows, metric_name),
            seed_key=f"{seed_prefix}:{metric_name}",
        )
        for metric_name in CONTEXT_SUMMARY_METRICS
    }

    def calibrate(reference_rows: list[dict[str, Any]] | None, *, label: str) -> dict[str, Any]:
        if not reference_rows:
            return {
                "referenceKind": label,
                "available": False,
            }
        reference_metric_summaries = {
            metric_name: _metric_distribution_summary(
                _metric_values(reference_rows, metric_name),
                seed_key=f"{seed_prefix}:{label}:{metric_name}:reference",
            )
            for metric_name in CONTEXT_SUMMARY_METRICS
        }
        comparisons: dict[str, dict[str, float | bool | None]] = {}
        for metric_name in CONTEXT_SUMMARY_METRICS:
            current_mean = metric_summaries[metric_name]["mean"]
            reference_mean = reference_metric_summaries[metric_name]["mean"]
            reference_p05 = reference_metric_summaries[metric_name]["p05"]
            reference_p95 = reference_metric_summaries[metric_name]["p95"]
            outside_envelope = None
            if (
                isinstance(current_mean, float)
                and isinstance(reference_p05, float)
                and isinstance(reference_p95, float)
            ):
                outside_envelope = bool(
                    current_mean < reference_p05 or current_mean > reference_p95
                )
            comparisons[metric_name] = {
                "referenceMean": reference_mean,
                "referenceP05": reference_p05,
                "referenceP95": reference_p95,
                "deltaFromReferenceMean": (
                    None
                    if not isinstance(current_mean, float) or not isinstance(reference_mean, float)
                    else float(current_mean - reference_mean)
                ),
                "outsideReferenceEnvelope": outside_envelope,
            }
        return {
            "referenceKind": label,
            "available": True,
            "trialCount": len(reference_rows),
            "metrics": comparisons,
        }

    summary = {
        metric_name: metric_summaries[metric_name]["mean"]
        for metric_name in CONTEXT_SUMMARY_METRICS
    }
    return {
        **summary,
        "metricSummaries": metric_summaries,
        "relativeToTargetBaseline": calibrate(target_reference_rows, label="target_baseline"),
        "relativeToMatchedBaseline": calibrate(
            matched_reference_rows, label="matched_context_baseline"
        ),
    }


def _context_summary(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT context_trial_id, specimen_id, context_kind, context_label,
               environment, perturbation, repeat_index, family_kind, regime_family,
               geometry_family, canonical_family, mean_fragility_score,
               mean_robustness_score, class_shift_score, goal_error_score,
               peak_goal_error_score, cumulative_goal_error_score,
               body_plan_error_score, body_plan_class_shift_score, coherence_drop_score,
               organization_drop_score, whole_body_motion_change_score,
               matched_baseline_error_score, control_cost_proxy,
               path_length_ratio_to_reference, displacement_ratio_to_reference,
               center_velocity_ratio_to_reference, trace_class_change_count,
               trace_path_length, trace_displacement, trace_peak_center_velocity,
               trace_mean_center_velocity, trace_sample_count,
               trace_path_length_ratio_to_reference,
               trace_displacement_ratio_to_reference,
               trace_peak_center_velocity_ratio_to_reference, recovery_lag_steps
        FROM creature_context_summary_vw
        WHERE study_id = ?
        ORDER BY context_trial_id
        """,
        [study_id],
    ).fetchall()
    trials = [
        {
            "contextTrialId": row[0],
            "specimenId": row[1],
            "contextKind": row[2],
            "contextLabel": row[3],
            "environment": row[4],
            "perturbation": row[5],
            "repeatIndex": row[6],
            "familyKind": row[7],
            "regimeFamily": row[8],
            "geometryFamily": row[9],
            "canonicalFamily": row[10],
            "meanFragilityScore": row[11],
            "meanRobustnessScore": row[12],
            "classShiftScore": row[13],
            "goalErrorScore": row[14],
            "peakGoalErrorScore": row[15],
            "cumulativeGoalErrorScore": row[16],
            "bodyPlanErrorScore": row[17],
            "bodyPlanClassShiftScore": row[18],
            "coherenceDropScore": row[19],
            "organizationDropScore": row[20],
            "wholeBodyMotionChangeScore": row[21],
            "matchedBaselineErrorScore": row[22],
            "controlCostProxy": row[23],
            "pathLengthRatioToReference": row[24],
            "displacementRatioToReference": row[25],
            "centerVelocityRatioToReference": row[26],
            "traceClassChangeCount": row[27],
            "tracePathLength": row[28],
            "traceDisplacement": row[29],
            "tracePeakCenterVelocity": row[30],
            "traceMeanCenterVelocity": row[31],
            "traceSampleCount": row[32],
            "tracePathLengthRatioToReference": row[33],
            "traceDisplacementRatioToReference": row[34],
            "tracePeakCenterVelocityRatioToReference": row[35],
            "recoveryLagSteps": row[36],
        }
        for row in rows
    ]
    grouped_by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_by_family_context: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        context_kind = trial.get("contextKind")
        canonical_family = trial.get("canonicalFamily")
        if isinstance(context_kind, str):
            grouped_by_context[context_kind].append(trial)
            if isinstance(canonical_family, str):
                grouped_by_family_context[(canonical_family, context_kind)].append(trial)
    baseline_by_context = {
        context_kind: group_rows
        for context_kind, group_rows in grouped_by_context.items()
        if context_kind in {"baseline", "obstacle"}
    }
    baseline_by_family_context = {
        (canonical_family, context_kind): group_rows
        for (canonical_family, context_kind), group_rows in grouped_by_family_context.items()
        if context_kind in {"baseline", "obstacle"}
    }

    return {
        "summary": {
            "contextTrialCount": len(trials),
            "contextKinds": sorted(
                {trial["contextKind"] for trial in trials if isinstance(trial["contextKind"], str)}
            ),
            "byContextKind": [
                {
                    "contextKind": context_kind,
                    "trialCount": len(group_rows),
                    **_summarize_group(
                        group_rows,
                        seed_prefix=f"context:{context_kind}",
                        target_reference_rows=baseline_by_context.get("baseline"),
                        matched_reference_rows=baseline_by_context.get(
                            _reference_context_kind(context_kind)
                        ),
                    ),
                }
                for context_kind, group_rows in sorted(grouped_by_context.items())
            ],
            "byCanonicalFamilyAndContextKind": [
                {
                    "canonicalFamily": canonical_family,
                    "contextKind": context_kind,
                    "trialCount": len(group_rows),
                    **_summarize_group(
                        group_rows,
                        seed_prefix=f"family:{canonical_family}:context:{context_kind}",
                        target_reference_rows=baseline_by_family_context.get(
                            (canonical_family, "baseline")
                        ),
                        matched_reference_rows=baseline_by_family_context.get(
                            (canonical_family, _reference_context_kind(context_kind))
                        ),
                    ),
                }
                for (canonical_family, context_kind), group_rows in sorted(
                    grouped_by_family_context.items()
                )
            ],
        },
        "trials": trials,
    }


def _fiber_summary(connection: DuckDBPyConnection, *, study_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT fiber_group_id, grouping_kind, state_class_key, member_count,
               volume_proxy, diversity_proxy, connectivity_proxy, metadata_json
        FROM fiber_groups
        WHERE study_id = ?
        ORDER BY state_class_key
        """,
        [study_id],
    ).fetchall()
    groups = [
        {
            "fiberGroupId": row[0],
            "groupingKind": row[1],
            "stateClassKey": row[2],
            "memberCount": row[3],
            "volumeProxy": row[4],
            "diversityProxy": row[5],
            "connectivityProxy": row[6],
            "metadata": json.loads(row[7]) if row[7] else {},
        }
        for row in rows
    ]
    return {
        "summary": {"fiberGroupCount": len(groups)},
        "groups": groups,
    }


def _universality_summary(connection: DuckDBPyConnection, *, study_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT universality_run_id, comparison_scope, coarse_kind, summary_json
        FROM universality_runs
        WHERE study_id = ?
        ORDER BY universality_run_id
        """,
        [study_id],
    ).fetchall()
    runs = [
        {
            "universalityRunId": row[0],
            "comparisonScope": row[1],
            "coarseKind": row[2],
            "summary": json.loads(row[3]) if row[3] else {},
        }
        for row in rows
    ]
    return {
        "summary": {"universalityRunCount": len(runs)},
        "runs": runs,
    }


def _topology_packets(
    connection: DuckDBPyConnection,
    *,
    parent_study_id: str,
) -> list[dict[str, Any]]:
    topology_study_ids = [
        str(row[0])
        for row in connection.execute(
            """
            SELECT study_id
            FROM studies
            WHERE parent_study_id = ? AND study_kind = 'topology_run'
            ORDER BY study_id
            """,
            [parent_study_id],
        ).fetchall()
    ]
    return [
        export_topology_packet(connection, study_id=study_id)
        for study_id in topology_study_ids
    ]


def export_biological_study(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    context_study_id: str | None = None,
) -> dict[str, Any]:
    baseline_states = [
        row
        for row in _state_rows(connection, study_id=study_id)
        if row["contextKind"] == "baseline"
    ]
    context_states = (
        [] if context_study_id is None else _state_rows(connection, study_id=context_study_id)
    )
    packet = {
        "version": 1,
        "packetKind": "biological_morphospace_study_v1",
        "sourceArtifacts": {
            "baselineStudy": f"duckdb://study/{study_id}",
            "contextStudy": (
                None if context_study_id is None else f"duckdb://study/{context_study_id}"
            ),
        },
        "summary": {
            "baselineStateCount": len(baseline_states),
            "contextStateCount": len(context_states),
            "regimeFamilies": sorted(
                {row["regimeFamily"] for row in baseline_states if row["regimeFamily"]}
            ),
            "canonicalFamilies": sorted(
                {row["canonicalFamily"] for row in baseline_states if row["canonicalFamily"]}
            ),
        },
        "baseline": {
            "states": baseline_states,
            "groupSummary": {
                "byRegimeFamily": _group_summary(baseline_states, group_key="regimeFamily"),
                "byCanonicalFamily": _group_summary(baseline_states, group_key="canonicalFamily"),
                "creatureByCanonicalFamily": _creature_group_summary(
                    baseline_states,
                    group_key="canonicalFamily",
                ),
            },
            "counts": {
                "byRegimeFamily": _group_counts(baseline_states, "regimeFamily"),
                "byCanonicalFamily": _group_counts(baseline_states, "canonicalFamily"),
                "byCreatureBucket": _group_counts(
                    [
                        {
                            **row,
                            "creatureBucket": (
                                row.get("creatureLabels", {}).get("creatureBucket")
                                if isinstance(row.get("creatureLabels"), dict)
                                else None
                            ),
                        }
                        for row in baseline_states
                    ],
                    "creatureBucket",
                ),
            },
            "creatures": {
                "byCoherenceClass": _group_counts(
                    [
                        {
                            **row,
                            "coherenceClass": (
                                row.get("creatureLabels", {}).get("coherenceClass")
                                if isinstance(row.get("creatureLabels"), dict)
                                else None
                            ),
                        }
                        for row in baseline_states
                    ],
                    "coherenceClass",
                ),
                "byOrganizationClass": _group_counts(
                    [
                        {
                            **row,
                            "organizationClass": (
                                row.get("creatureLabels", {}).get("organizationClass")
                                if isinstance(row.get("creatureLabels"), dict)
                                else None
                            ),
                        }
                        for row in baseline_states
                    ],
                    "organizationClass",
                ),
                "byMobilityClass": _group_counts(
                    [
                        {
                            **row,
                            "mobilityClass": (
                                row.get("creatureLabels", {}).get("mobilityClass")
                                if isinstance(row.get("creatureLabels"), dict)
                                else None
                            ),
                        }
                        for row in baseline_states
                    ],
                    "mobilityClass",
                ),
            },
            "topology": _topology_packets(connection, parent_study_id=study_id),
        },
        "context": (
            None
            if context_study_id is None
            else {
                "states": context_states,
                "outcomes": _context_summary(connection, study_id=context_study_id),
                "topology": _topology_packets(connection, parent_study_id=context_study_id),
            }
        ),
        "fibers": _fiber_summary(connection, study_id=study_id),
        "universality": _universality_summary(connection, study_id=study_id),
    }
    return packet
