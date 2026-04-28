from __future__ import annotations

import json
from pathlib import Path

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    transform_axes,
)

from .warehouse import (
    json_text,
    register_artifact,
    register_specimen_study,
    register_study,
    replace_context_sample_axes,
    replace_perturbation_axes,
    stable_id,
    upsert_specimen,
)


def ingest_focal_packet(
    connection: DuckDBPyConnection,
    *,
    focal_packet_path: Path,
    study_id: str | None = None,
    label: str | None = None,
) -> str:
    packet = json.loads(focal_packet_path.read_text(encoding="utf-8"))
    if packet.get("packetKind") != "transformation_focal_packet_v1":
        raise SystemExit(f"{focal_packet_path}: expected transformation_focal_packet_v1")
    resolved_study_id = register_study(
        connection,
        study_kind="focal_batch",
        label=label or focal_packet_path.stem,
        run_id=None,
        study_id=study_id,
        metadata_json={"sourceArtifact": str(focal_packet_path)},
    )
    artifact_id = register_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_kind="focal_packet",
        path=focal_packet_path,
    )
    from .warehouse import ingest_json_object_artifact

    ingest_json_object_artifact(
        connection,
        artifact_id=artifact_id,
        object_kind="focal_packet",
        payload=packet,
    )

    specimens = packet.get("specimens")
    if not isinstance(specimens, list):
        raise SystemExit(f"{focal_packet_path}: missing specimens")
    for specimen in specimens:
        if not isinstance(specimen, dict):
            raise SystemExit(f"{focal_packet_path}: specimen rows must be objects")
        specimen_id = str(specimen["specimenId"])
        upsert_specimen(
            connection,
            {
                "specimen_id": specimen_id,
                "source_creature_id": None,
                "study_id": resolved_study_id,
                "run_id": specimen.get("runId"),
                "campaign_id": specimen.get("campaignId"),
                "source_kind": str(specimen.get("sourceKind", "unknown")),
                "source_mode": None,
                "source_algorithm": None,
                "config_hash": None,
                "initial_condition_family": None,
                "regime_family": specimen.get("regimeFamily"),
                "geometry_family": specimen.get("geometryFamily"),
                "canonical_family": specimen.get("canonicalFamily"),
                "family_kind": specimen.get("familyKind"),
                "score": None,
                "filters_passed": None,
                "search_is_stable_candidate": None,
                "recorded_at": None,
                "results_path": None,
                "export_dir": None,
                "activity_path": None,
                "fingerprint_path": None,
                "provenance_json": specimen,
            },
        )
        register_specimen_study(
            connection,
            study_id=resolved_study_id,
            specimen_id=specimen_id,
        )
        raw_axes = specimen.get("rawAxes")
        if isinstance(raw_axes, dict):
            transformed = specimen.get("transformedAxes")
            transformed_axes = (
                transformed if isinstance(transformed, dict) else transform_axes(raw_axes)
            )
            from .warehouse import replace_specimen_axes

            axis_rows = []
            for axis_id, value in raw_axes.items():
                if axis_id in TERMINAL_AXIS_IDS:
                    axis_family = "terminal"
                elif axis_id in DEVELOPMENTAL_AXIS_IDS:
                    axis_family = "developmental"
                else:
                    continue
                axis_rows.append(
                    (
                        axis_id,
                        axis_family,
                        float(value),
                        (
                            None
                            if transformed_axes.get(axis_id) is None
                            else float(transformed_axes[axis_id])
                        ),
                    )
                )
            if axis_rows:
                replace_specimen_axes(connection, specimen_id=specimen_id, axis_rows=axis_rows)

        connection.execute(
            "DELETE FROM perturbation_trials WHERE specimen_id = ? AND study_id = ?",
            [specimen_id, resolved_study_id],
        )

        context_trials = specimen.get("contextTrials")
        if isinstance(context_trials, list) and context_trials:
            for trial in context_trials:
                if not isinstance(trial, dict):
                    continue
                environment = str(trial.get("environmentLabel", "unknown"))
                perturbation = str(trial.get("perturbationLabel", "unknown"))
                repeat_value = trial.get("repeatIndex", 0)
                repeat_index = int(repeat_value) if isinstance(repeat_value, (int, float)) else 0
                run_ref = trial.get("runId") if isinstance(trial.get("runId"), str) else ""
                trial_id = stable_id(
                    "context-trial",
                    specimen_id,
                    resolved_study_id,
                    environment,
                    perturbation,
                    repeat_index,
                    run_ref,
                )
                connection.execute(
                    """
                    INSERT INTO perturbation_trials (
                        trial_id, specimen_id, study_id, run_id, campaign_id, phase_name,
                        environment, perturbation, repeat_index, results_path,
                        summary_path, raw_response_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
                    """,
                    [
                        trial_id,
                        specimen_id,
                        resolved_study_id,
                        trial.get("runId"),
                        specimen.get("campaignId"),
                        specimen.get("phaseName"),
                        environment,
                        perturbation,
                        repeat_index,
                        trial.get("resultsPath"),
                        trial.get("summaryPath"),
                        json_text(trial),
                    ],
                )
                axis_rows = []
                metrics_payload = trial.get("metrics")
                if isinstance(metrics_payload, dict):
                    for axis_id, value in metrics_payload.items():
                        if isinstance(value, (int, float)):
                            axis_rows.append((str(axis_id), float(value), float(value)))
                endpoint_axes = trial.get("endpointRawAxes")
                if isinstance(endpoint_axes, dict):
                    for axis_id, value in endpoint_axes.items():
                        if isinstance(value, (int, float)):
                            axis_rows.append(
                                (
                                    f"endpoint.{axis_id}",
                                    float(value),
                                    float(value),
                                )
                            )
                replace_perturbation_axes(connection, trial_id=trial_id, axis_rows=axis_rows)
                context_axis_rows: list[tuple[int, str, float | None]] = []
                development_trace = trial.get("developmentTrace")
                if isinstance(development_trace, dict):
                    sample_rows_payload = development_trace.get("samples")
                    if isinstance(sample_rows_payload, list):
                        for sample in sample_rows_payload:
                            if not isinstance(sample, dict):
                                continue
                            step_value = sample.get("step")
                            if not isinstance(step_value, (int, float)):
                                continue
                            step = int(step_value)
                            raw_axes = sample.get("rawAxes")
                            if isinstance(raw_axes, dict):
                                for axis_id, value in raw_axes.items():
                                    if isinstance(value, (int, float)):
                                        context_axis_rows.append(
                                            (step, str(axis_id), float(value))
                                        )
                replace_context_sample_axes(
                    connection,
                    context_trial_id=trial_id,
                    axis_rows=context_axis_rows,
                )
            continue

        baseline_rows = specimen.get("baselineByEnvironment")
        if isinstance(baseline_rows, list):
            for baseline in baseline_rows:
                if not isinstance(baseline, dict):
                    continue
                trial_id = stable_id(
                    "baseline",
                    specimen_id,
                    resolved_study_id,
                    baseline.get("environmentLabel", ""),
                )
                connection.execute(
                    """
                    INSERT INTO perturbation_trials (
                        trial_id, specimen_id, study_id, run_id, campaign_id, phase_name,
                        environment, perturbation, repeat_index, results_path,
                        summary_path, raw_response_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'baseline', 0, NULL, NULL, CAST(? AS JSON))
                    """,
                    [
                        trial_id,
                        specimen_id,
                        resolved_study_id,
                        specimen.get("runId"),
                        specimen.get("campaignId"),
                        specimen.get("phaseName"),
                        baseline.get("environmentLabel"),
                        json_text(baseline),
                    ],
                )
                mean_metrics = baseline.get("meanMetrics")
                axis_rows = []
                if isinstance(mean_metrics, dict):
                    for axis_id, value in mean_metrics.items():
                        if isinstance(value, (int, float)):
                            axis_rows.append((str(axis_id), float(value), float(value)))
                replace_perturbation_axes(connection, trial_id=trial_id, axis_rows=axis_rows)

        response_rows = specimen.get("responseByCondition")
        if not isinstance(response_rows, list):
            continue
        for response in response_rows:
            if not isinstance(response, dict):
                continue
            environment = str(response.get("environmentLabel", "unknown"))
            perturbation = str(response.get("perturbationLabel", "unknown"))
            trial_id = stable_id(
                "response",
                specimen_id,
                resolved_study_id,
                environment,
                perturbation,
            )
            connection.execute(
                """
                INSERT INTO perturbation_trials (
                    trial_id, specimen_id, study_id, run_id, campaign_id, phase_name,
                    environment, perturbation, repeat_index, results_path,
                    summary_path, raw_response_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, CAST(? AS JSON))
                """,
                [
                    trial_id,
                    specimen_id,
                    resolved_study_id,
                    specimen.get("runId"),
                    specimen.get("campaignId"),
                    specimen.get("phaseName"),
                    environment,
                    perturbation,
                    json_text(response),
                ],
            )
            axis_rows = []
            mean_metrics = response.get("meanMetrics")
            if isinstance(mean_metrics, dict):
                for axis_id, value in mean_metrics.items():
                    if isinstance(value, (int, float)):
                        axis_rows.append((str(axis_id), float(value), float(value)))
            for key in (
                "meanFragilityScore",
                "maxFragilityScore",
                "meanRobustnessScore",
                "minRobustnessScore",
            ):
                value = response.get(key)
                if isinstance(value, (int, float)):
                    axis_rows.append((key, float(value), float(value)))
            replace_perturbation_axes(connection, trial_id=trial_id, axis_rows=axis_rows)

    return resolved_study_id
