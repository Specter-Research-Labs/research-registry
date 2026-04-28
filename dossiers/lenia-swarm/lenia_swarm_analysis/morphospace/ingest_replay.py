from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis._io import read_jsonl
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    developmental_trace_from_samples,
    extract_terminal_raw_axes_from_row,
    transform_axes,
)

from .ingest_library import resolve_library_row_context
from .warehouse import (
    ingest_json_object_artifact,
    ingest_jsonl_rows,
    register_artifact,
    register_specimen_study,
    register_study,
    replace_development_sample_axes,
    replace_specimen_axes,
    upsert_specimen,
)


def _load_trace_samples(trace_path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(trace_path)
    return sorted(rows, key=lambda row: int(row["step"]))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected JSON object")
    return payload


def _load_single_jsonl_row(path: Path) -> dict[str, Any]:
    rows = read_jsonl(path)
    if len(rows) != 1:
        raise SystemExit(f"{path}: expected exactly one JSONL row, found {len(rows)}")
    payload = rows[0]
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected JSON object row")
    return payload


def _infer_record_every(captured_steps: list[int]) -> int:
    if len(captured_steps) < 2:
        return 0
    delta = captured_steps[1] - captured_steps[0]
    return delta if delta > 0 else 0


def _load_terminal_and_trajectory(
    *,
    specimen_id: str,
    library_row: dict[str, Any],
    results_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    creature = library_row.get("creature")
    descriptor_bundle = creature.get("descriptorBundle") if isinstance(creature, dict) else None
    terminal = descriptor_bundle.get("terminal") if isinstance(descriptor_bundle, dict) else None
    trajectory = (
        descriptor_bundle.get("trajectory") if isinstance(descriptor_bundle, dict) else None
    )
    if isinstance(terminal, dict) and isinstance(trajectory, dict):
        return terminal, trajectory
    result_row = _load_single_jsonl_row(results_path)
    descriptor_bundle = result_row.get("descriptor_bundle")
    terminal = descriptor_bundle.get("terminal") if isinstance(descriptor_bundle, dict) else None
    trajectory = (
        descriptor_bundle.get("trajectory") if isinstance(descriptor_bundle, dict) else None
    )
    if not isinstance(terminal, dict):
        raise SystemExit(f"{specimen_id}: missing terminal descriptor in replay bundle")
    if not isinstance(trajectory, dict):
        raise SystemExit(f"{specimen_id}: missing trajectory descriptor in replay bundle")
    return terminal, trajectory


def _summary_row_from_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    campaign_dir = manifest_path.parent
    library_path = Path(
        str(manifest.get("libraryPath", campaign_dir / "library/index.jsonl"))
    ).expanduser().resolve()
    library_row = _load_single_jsonl_row(library_path)
    creature = library_row.get("creature")
    if not isinstance(creature, dict):
        raise SystemExit(f"{library_path}: missing creature payload")
    context = resolve_library_row_context(library_row, artifact_kind="library_index")

    trace_path = Path(str(manifest["developmentTracePath"])).expanduser().resolve()
    trace_samples = _load_trace_samples(trace_path)
    captured_steps = [int(sample["step"]) for sample in trace_samples]

    search_path_raw = manifest.get("searchPath")
    search_payload: dict[str, Any] = {}
    if isinstance(search_path_raw, str) and search_path_raw:
        search_payload = _load_json(Path(search_path_raw).expanduser().resolve())
    results_path = Path(str(manifest["resultsPath"])).expanduser().resolve()
    specimen_id = str(creature["id"])
    terminal, trajectory = _load_terminal_and_trajectory(
        specimen_id=specimen_id,
        library_row=library_row,
        results_path=results_path,
    )

    return {
        "specimenId": specimen_id,
        "specimenName": str(creature.get("name", specimen_id)),
        "runId": str(library_row.get("run_id", manifest.get("replayRunId", "unknown"))),
        "campaignId": manifest.get("campaignId"),
        "sourceKind": str(
            context["source_origin_kind"] or manifest.get("inputKind", context["source_kind"] or "unknown")
        ),
        "sourceRunId": str(context["source_run_id"] or manifest.get("sourceRunId", "unknown")),
        "sourceCampaignId": context["source_campaign_id"] or manifest.get("sourceCampaignId"),
        "sourceInputPath": str(context["source_input_path"] or manifest.get("inputPath", "")),
        "sourceMode": context["source_origin_mode"] or manifest.get("sourceMode") or context["source_mode"],
        "sourceAlgorithm": context["source_origin_algorithm"]
        or manifest.get("sourceAlgorithm")
        or context["source_algorithm"],
        "sourceExportDir": context["source_export_dir"] or manifest.get("sourceExportDir"),
        "sourceReason": context["source_reason"] or manifest.get("sourceReason"),
        "sourceReasonFamily": context["source_reason_family"] or manifest.get("sourceReasonFamily"),
        "sourceReasonKind": context["source_reason_kind"] or manifest.get("sourceReasonKind"),
        "sourceReasonValue": context["source_reason_value"] or manifest.get("sourceReasonValue"),
        "sourcePairSlug": context["source_pair_slug"] or manifest.get("sourcePairSlug"),
        "sourcePairOrder": context["source_pair_order"] or manifest.get("sourcePairOrder"),
        "sourcePairRank": context["source_pair_rank"] or manifest.get("sourcePairRank"),
        "sourcePairSpecimenA": context["source_pair_specimen_a"] or manifest.get("sourcePairSpecimenA"),
        "sourcePairSpecimenB": context["source_pair_specimen_b"] or manifest.get("sourcePairSpecimenB"),
        "sourceBridgeAlpha": context["source_bridge_alpha"] or manifest.get("sourceBridgeAlpha"),
        "sourceCreatureId": str(
            context["research_metadata"].get(
                "source_creature_id",
                manifest.get("sourceCreatureId", specimen_id),
            )
        ),
        "regimeFamily": context["regime_family"],
        "geometryFamily": context["geometry_family"],
        "canonicalFamily": context["canonical_family"],
        "initialConditionFamily": context["initial_condition_family"],
        "replayRunId": str(manifest.get("replayRunId", library_row.get("run_id", "unknown"))),
        "replaySteps": int(
            search_payload.get("steps", captured_steps[-1] if captured_steps else 0)
        ),
        "recordEvery": int(
            search_payload.get("record_interval", _infer_record_every(captured_steps))
        ),
        "includeInitial": bool(captured_steps and captured_steps[0] == 0),
        "sampleCount": len(trace_samples),
        "capturedSteps": captured_steps,
        "developmentTracePath": str(trace_path),
        "developmentFramesDir": manifest.get("developmentFramesDir"),
        "resultsPath": str(results_path),
        "terminal": terminal,
        "trajectory": trajectory,
    }


def _load_replay_summary_rows(path: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    if path.is_dir():
        manifest_paths = sorted(path.glob("**/replay-manifest.json"))
        rows = [_summary_row_from_manifest(manifest_path) for manifest_path in manifest_paths]
        return rows, manifest_paths
    return read_jsonl(path), []


def ingest_replay_batch(
    connection: DuckDBPyConnection,
    *,
    development_traces_path: Path,
    study_id: str | None = None,
    label: str | None = None,
    replay_packet_path: Path | None = None,
) -> str:
    summary_rows, manifest_paths = _load_replay_summary_rows(development_traces_path)
    run_id = (
        str(summary_rows[0].get("replayRunId"))
        if summary_rows and isinstance(summary_rows[0].get("replayRunId"), str)
        else None
    )
    resolved_study_id = register_study(
        connection,
        study_kind="replay_batch",
        label=label or development_traces_path.stem,
        run_id=run_id,
        study_id=study_id,
        metadata_json={"sourceArtifact": str(development_traces_path)},
    )
    if development_traces_path.is_file():
        traces_artifact_id = register_artifact(
            connection,
            study_id=resolved_study_id,
            artifact_kind="development_traces",
            path=development_traces_path,
        )
        ingest_jsonl_rows(connection, artifact_id=traces_artifact_id, rows=summary_rows)
    else:
        for manifest_path, summary_row in zip(manifest_paths, summary_rows, strict=True):
            manifest_artifact_id = register_artifact(
                connection,
                study_id=resolved_study_id,
                artifact_kind="json",
                path=manifest_path,
                metadata_json={
                    "kind": "replay_manifest",
                    "specimenId": str(summary_row.get("specimenId", "")),
                },
            )
            ingest_json_object_artifact(
                connection,
                artifact_id=manifest_artifact_id,
                object_kind="replay_manifest",
                payload=summary_row,
            )
    if replay_packet_path is not None and replay_packet_path.is_file():
        replay_packet = json.loads(replay_packet_path.read_text(encoding="utf-8"))
        replay_artifact_id = register_artifact(
            connection,
            study_id=resolved_study_id,
            artifact_kind="replay_packet",
            path=replay_packet_path,
        )
        ingest_json_object_artifact(
            connection,
            artifact_id=replay_artifact_id,
            object_kind="replay_packet",
            payload=replay_packet,
        )

    for summary_row in summary_rows:
        specimen_id = str(summary_row["specimenId"])
        trace_path = Path(str(summary_row["developmentTracePath"])).expanduser().resolve()
        trace_artifact_id = register_artifact(
            connection,
            study_id=resolved_study_id,
            artifact_kind="jsonl",
            path=trace_path,
            metadata_json={"specimenId": specimen_id, "kind": "development_trace"},
        )
        trace_samples = _load_trace_samples(trace_path)
        ingest_jsonl_rows(connection, artifact_id=trace_artifact_id, rows=trace_samples)

        upsert_specimen(
            connection,
            {
                "specimen_id": specimen_id,
                "source_creature_id": summary_row.get("sourceCreatureId"),
                "study_id": resolved_study_id,
                "run_id": summary_row.get("sourceRunId"),
                "campaign_id": summary_row.get("sourceCampaignId"),
                "source_kind": str(summary_row.get("sourceKind", "unknown")),
                "source_mode": summary_row.get("sourceMode"),
                "source_algorithm": summary_row.get("sourceAlgorithm"),
                "config_hash": summary_row.get("configHash"),
                "initial_condition_family": summary_row.get("initialConditionFamily"),
                "regime_family": summary_row.get("regimeFamily"),
                "geometry_family": summary_row.get("geometryFamily"),
                "canonical_family": summary_row.get("canonicalFamily"),
                "family_kind": (
                    summary_row.get("canonicalFamily")
                    or summary_row.get("geometryFamily")
                    or summary_row.get("initialConditionFamily")
                ),
                "score": None,
                "filters_passed": None,
                "search_is_stable_candidate": None,
                "recorded_at": None,
                "results_path": summary_row.get("resultsPath"),
                "export_dir": summary_row.get("sourceExportDir"),
                "activity_path": None,
                "fingerprint_path": None,
                "provenance_json": summary_row,
            },
        )
        register_specimen_study(
            connection,
            study_id=resolved_study_id,
            specimen_id=specimen_id,
        )

        connection.execute(
            "DELETE FROM development_samples WHERE specimen_id = ?",
            [specimen_id],
        )
        for sample_index, sample in enumerate(trace_samples):
            connection.execute(
                """
                INSERT INTO development_samples (
                    specimen_id, step, sample_index, width, height, center_x, center_y, frame_path,
                    terminal_descriptor_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
                """,
                [
                    specimen_id,
                    int(sample["step"]),
                    sample_index,
                    int(sample["width"])
                    if "width" in sample
                    else int(sample["terminal"]["fingerprintResolution"]),
                    int(sample["height"])
                    if "height" in sample
                    else int(sample["terminal"]["fingerprintResolution"]),
                    float(sample["centerX"]),
                    float(sample["centerY"]),
                    sample.get("framePath"),
                    json.dumps(sample["terminal"], sort_keys=True),
                ],
            )

        terminal_axes = extract_terminal_raw_axes_from_row(summary_row)
        development = developmental_trace_from_samples(
            specimen_id=specimen_id,
            trace_samples=trace_samples,
            meander_final=float(terminal_axes["meander"]),
        )
        axis_rows: list[tuple[str, str, float | None, float | None]] = [
            (
                axis_id,
                "terminal",
                float(terminal_axes[axis_id]),
                float(transform_axes({axis_id: float(terminal_axes[axis_id])})[axis_id]),
            )
            for axis_id in TERMINAL_AXIS_IDS
        ]
        axis_rows.extend(
            (
                axis_id,
                "developmental",
                (
                    None
                    if development["developmentalAxes"][axis_id] is None
                    else float(development["developmentalAxes"][axis_id])
                ),
                (
                    None
                    if development["transformedDevelopmentalAxes"][axis_id] is None
                    else float(development["transformedDevelopmentalAxes"][axis_id])
                ),
            )
            for axis_id in DEVELOPMENTAL_AXIS_IDS
        )
        replace_specimen_axes(connection, specimen_id=specimen_id, axis_rows=axis_rows)

        trace_axis_rows: list[tuple[int, str, float | None]] = []
        for axis_id, values in development["traceAxes"].items():
            for step, value in zip(development["steps"], values, strict=True):
                trace_axis_rows.append((int(step), str(axis_id), float(value)))
        replace_development_sample_axes(
            connection,
            specimen_id=specimen_id,
            axis_rows=trace_axis_rows,
        )

    return resolved_study_id
