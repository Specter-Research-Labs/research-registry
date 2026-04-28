from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

from .warehouse import (
    ingest_jsonl_rows,
    register_artifact,
    register_specimen_study,
    register_study,
    replace_specimen_axes,
    upsert_specimen,
)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list_or_none(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(entry, str) and entry for entry in value):
        return sorted(set(value))
    return None


def _manifest_taxonomy_family(manifest: dict[str, Any]) -> str | None:
    taxonomy = _dict_or_empty(manifest.get("taxonomy"))
    family_id = taxonomy.get("familyID")
    if isinstance(family_id, str) and family_id:
        return family_id
    return _string_or_none(manifest.get("initialConditionFamily"))


def _manifest_replay_export_dir(manifest: dict[str, Any]) -> str | None:
    replay = _dict_or_empty(manifest.get("replay"))
    return _string_or_none(replay.get("exportDir"))


def resolve_library_row_context(
    row: dict[str, Any],
    *,
    artifact_kind: str,
) -> dict[str, Any]:
    creature = _dict_or_empty(row.get("creature"))
    manifest = _dict_or_empty(row.get("specimen_manifest"))
    research_metadata = _dict_or_empty(manifest.get("researchMetadata"))
    if not research_metadata:
        research_metadata = _dict_or_empty(row.get("research_metadata"))
    source_research_metadata = _dict_or_empty(research_metadata.get("source_research_metadata"))
    initial_condition_family = _string_or_none(
        manifest.get("initialConditionFamily")
    ) or _string_or_none(creature.get("initialConditionFamily"))
    regime_family = source_research_metadata.get("regime_family") or research_metadata.get(
        "regime_family"
    )
    geometry_family = source_research_metadata.get("geometry_family") or research_metadata.get(
        "geometry_family"
    )
    canonical_family = source_research_metadata.get("canonical_family") or research_metadata.get(
        "canonical_family"
    )
    runtime_capabilities = _string_list_or_none(manifest.get("runtimeCapabilities"))
    if runtime_capabilities is None:
        runtime_capabilities = _string_list_or_none(row.get("runtime_capabilities")) or []

    return {
        "creature": creature,
        "manifest": manifest,
        "research_metadata": research_metadata,
        "source_research_metadata": source_research_metadata,
        "specimen_id": _string_or_none(manifest.get("specimenID"))
        or str(creature["id"]),
        "source_creature_id": _string_or_none(manifest.get("creatureID"))
        or str(creature["id"]),
        "run_id": _string_or_none(manifest.get("runID")) or row.get("run_id"),
        "campaign_id": manifest.get("campaignID")
        if manifest.get("campaignID") is not None
        else row.get("campaign_id"),
        "source_kind": _string_or_none(manifest.get("sourceKind")) or artifact_kind,
        "source_mode": _string_or_none(manifest.get("sourceMode")) or row.get("source_mode"),
        "source_algorithm": _string_or_none(manifest.get("sourceAlgorithm"))
        or row.get("source_algorithm"),
        "config_hash": _string_or_none(manifest.get("configHash")) or row.get("config_hash"),
        "initial_condition_family": initial_condition_family,
        "regime_family": regime_family,
        "geometry_family": geometry_family,
        "canonical_family": canonical_family,
        "family_kind": _manifest_taxonomy_family(manifest)
        or canonical_family
        or geometry_family
        or initial_condition_family,
        "recorded_at": manifest.get("recordedAt", row.get("recorded_at")),
        "runtime_family": _string_or_none(manifest.get("runtimeFamily"))
        or _string_or_none(row.get("runtime_family")),
        "runtime_capabilities": runtime_capabilities,
        "source_origin_kind": _string_or_none(research_metadata.get("source_kind")),
        "source_origin_mode": _string_or_none(research_metadata.get("source_mode")),
        "source_origin_algorithm": _string_or_none(research_metadata.get("source_algorithm")),
        "source_run_id": _string_or_none(research_metadata.get("source_run_id")),
        "source_campaign_id": research_metadata.get("source_campaign_id"),
        "source_input_path": _string_or_none(research_metadata.get("source_input_path")),
        "source_reason": _string_or_none(research_metadata.get("source_reason")),
        "source_reason_family": _string_or_none(research_metadata.get("source_reason_family")),
        "source_reason_kind": _string_or_none(research_metadata.get("source_reason_kind")),
        "source_reason_value": research_metadata.get("source_reason_value"),
        "source_pair_slug": _string_or_none(research_metadata.get("source_pair_slug")),
        "source_pair_order": research_metadata.get("source_pair_order"),
        "source_pair_rank": research_metadata.get("source_pair_rank"),
        "source_pair_specimen_a": _string_or_none(research_metadata.get("source_pair_specimen_a")),
        "source_pair_specimen_b": _string_or_none(research_metadata.get("source_pair_specimen_b")),
        "source_bridge_alpha": research_metadata.get("source_bridge_alpha"),
        "source_export_dir": _manifest_replay_export_dir(manifest)
        or _string_or_none(research_metadata.get("source_export_dir")),
    }


def ingest_library_index(
    connection: DuckDBPyConnection,
    *,
    index_path: Path,
    study_id: str | None = None,
    label: str | None = None,
) -> str:
    rows = [
        json.loads(line)
        for line in index_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    artifact_kind = "library_index" if "library" in index_path.parts else "export_index"
    resolved_study_id = register_study(
        connection,
        study_kind="import",
        label=label or index_path.stem,
        study_id=study_id,
        metadata_json={"sourceArtifact": str(index_path)},
    )
    artifact_id = register_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_kind=artifact_kind,
        path=index_path,
    )
    ingest_jsonl_rows(connection, artifact_id=artifact_id, rows=rows)

    for row in rows:
        context = resolve_library_row_context(row, artifact_kind=artifact_kind)
        creature = context["creature"]
        if not isinstance(creature, dict):
            continue
        research_metadata = context["research_metadata"]
        specimen_id = context["specimen_id"]
        descriptor_bundle = creature.get("descriptorBundle")
        terminal = (
            descriptor_bundle.get("terminal") if isinstance(descriptor_bundle, dict) else None
        )
        trajectory = (
            descriptor_bundle.get("trajectory") if isinstance(descriptor_bundle, dict) else None
        )
        upsert_specimen(
            connection,
            {
                "specimen_id": specimen_id,
                "source_creature_id": context["source_creature_id"],
                "study_id": resolved_study_id,
                "run_id": context["run_id"],
                "campaign_id": context["campaign_id"],
                "source_kind": context["source_kind"],
                "source_mode": context["source_mode"],
                "source_algorithm": context["source_algorithm"],
                "config_hash": context["config_hash"],
                "initial_condition_family": context["initial_condition_family"],
                "regime_family": context["regime_family"],
                "geometry_family": context["geometry_family"],
                "canonical_family": context["canonical_family"],
                "family_kind": context["family_kind"],
                "score": creature.get("score"),
                "filters_passed": None,
                "search_is_stable_candidate": None,
                "recorded_at": context["recorded_at"],
                "results_path": None,
                "export_dir": context["source_export_dir"],
                "activity_path": None,
                "fingerprint_path": None,
                "runtime_family": context["runtime_family"],
                "runtime_capabilities_json": context["runtime_capabilities"],
                "specimen_manifest_json": context["manifest"],
                "provenance_json": {
                    **row,
                    "research_metadata": research_metadata,
                    "terminal": terminal,
                    "trajectory": trajectory,
                },
            },
        )
        register_specimen_study(
            connection,
            study_id=resolved_study_id,
            specimen_id=specimen_id,
        )
        if isinstance(terminal, dict):
            terminal_axes = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal,
                trajectory=trajectory
                if isinstance(trajectory, dict)
                else {"centerVelocity": 0.0, "pathTortuosity": 0.0},
                specimen_id=specimen_id,
            )
            transformed = transform_axes(terminal_axes)
            replace_specimen_axes(
                connection,
                specimen_id=specimen_id,
                axis_rows=[
                    (
                        axis_id,
                        "terminal",
                        float(value),
                        float(transformed[axis_id]),
                    )
                    for axis_id, value in terminal_axes.items()
                ],
            )
    return resolved_study_id
