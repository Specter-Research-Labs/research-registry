from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, cast

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

from .warehouse import (
    ingest_sqlite_rows,
    register_artifact,
    register_specimen_study,
    register_study,
    replace_specimen_axes,
    upsert_specimen,
)


def _load_sqlite_rows(path: Path, table_name: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table_name}")]
    finally:
        connection.close()


def _sqlite_columns(path: Path, table_name: str) -> set[str]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
    finally:
        connection.close()


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _loads_optional_json(value: Any) -> dict[str, Any] | list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return None
    return json.loads(value)


def _normalize_terminal_descriptor(terminal: dict[str, Any]) -> dict[str, Any]:
    angular = terminal.get("angularSymmetry")
    if not isinstance(angular, dict):
        return terminal
    harmonics = angular.get("harmonics")
    if not isinstance(harmonics, list):
        return terminal
    harmonic_values: list[float] = []
    for raw in harmonics:
        if not isinstance(raw, (int, float)) or not math.isfinite(raw):
            return terminal
        harmonic_values.append(float(raw))

    normalized = dict(terminal)
    angular_normalized = dict(angular)
    if harmonic_values:
        dominant_index, dominant_amplitude = max(
            enumerate(harmonic_values),
            key=lambda item: item[1],
        )
    else:
        dominant_index, dominant_amplitude = 0, 0.0

    if angular_normalized.get("dominantAmplitude") is None:
        angular_normalized["dominantAmplitude"] = dominant_amplitude
    if angular_normalized.get("dominantOrder") is None:
        angular_normalized["dominantOrder"] = dominant_index + 1 if dominant_amplitude > 0.0 else 0
    if angular_normalized.get("normalizedEntropy") is None and all(
        abs(value) <= 1e-12 for value in harmonic_values
    ):
        angular_normalized["normalizedEntropy"] = 1.0
    normalized["angularSymmetry"] = angular_normalized
    return normalized


def _taxonomy_family(row: dict[str, Any]) -> str | None:
    value = row.get("taxonomy_family_id") or row.get("initial_condition_family")
    if isinstance(value, str) and value:
        return value
    return None


def _canonical_export_kind(
    row: dict[str, Any],
    *,
    research_metadata: dict[str, Any] | None = None,
) -> str | None:
    bundle_kind = row.get("bundle_kind")
    if isinstance(bundle_kind, str) and bundle_kind:
        return bundle_kind
    if isinstance(research_metadata, dict):
        value = research_metadata.get("canonical_export_kind")
        if isinstance(value, str) and value:
            return value
        nested = research_metadata.get("source_research_metadata")
        if isinstance(nested, dict):
            nested_value = nested.get("canonical_export_kind")
            if isinstance(nested_value, str) and nested_value:
                return nested_value
    return None


def _runtime_family(
    row: dict[str, Any],
    *,
    research_metadata: dict[str, Any] | None = None,
) -> str:
    explicit = row.get("runtime_family")
    if isinstance(explicit, str) and explicit:
        return explicit
    bundle_kind = _canonical_export_kind(row, research_metadata=research_metadata)
    if bundle_kind == "qd24_paper_replay_bundle_v1":
        return "qd24_paper"
    if bundle_kind == "sensorimotor24_paper_replay_bundle_v1":
        return "sensorimotor24_paper"
    source_mode = row.get("source_mode")
    if isinstance(source_mode, str):
        if source_mode == "qd-2024":
            return "qd24_paper"
        if source_mode == "sensorimotor-2024":
            return "sensorimotor24_paper"
    return "flow_lenia"


def _runtime_capabilities(
    row: dict[str, Any],
    *,
    research_metadata: dict[str, Any] | None = None,
    descriptor_ready: bool = False,
    replayable: bool = False,
) -> list[str]:
    explicit = _loads_optional_json(row.get("runtime_capabilities_json"))
    if isinstance(explicit, list) and all(isinstance(value, str) for value in explicit):
        return sorted(set(cast(list[str], explicit)))

    capabilities = {"archive", "warehouse_ingest"}
    metadata_replayable = bool(research_metadata.get("canonical_export_available")) if isinstance(research_metadata, dict) else False
    metadata_topology = bool(research_metadata.get("morphospace_ready")) if isinstance(research_metadata, dict) else False
    if replayable or metadata_replayable:
        capabilities.update({"replay", "intervention", "media"})
    if descriptor_ready or metadata_topology:
        capabilities.add("topology")
    return sorted(capabilities)


def _strict_specimen_manifest(
    row: dict[str, Any],
    *,
    creature_row: dict[str, Any] | None,
    export_row: dict[str, Any] | None,
    research_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = _loads_optional_json(row.get("specimen_manifest_json"))
    if isinstance(existing, dict):
        return existing
    genotype = _loads_optional_json(creature_row.get("genotype_json")) if creature_row else None
    initial_condition = (
        _loads_optional_json(creature_row.get("initial_condition_json"))
        if creature_row
        else None
    )
    metrics = _loads_optional_json(creature_row.get("metrics_json")) if creature_row else None
    morphometrics = (
        _loads_optional_json(creature_row.get("morphometrics_json"))
        if creature_row
        else None
    )
    descriptor_bundle = {
        "descriptorVersion": row.get("descriptor_version"),
        "symmetryPolicy": row.get("symmetry_policy"),
        "genotype": _loads_optional_json(row.get("genotype_descriptor_json")),
        "terminal": _loads_optional_json(row.get("terminal_descriptor_json")),
        "trajectory": _loads_optional_json(row.get("trajectory_descriptor_json")),
    }
    runtime_family = _runtime_family(
        {
            "runtime_family": row.get("runtime_family"),
            "source_mode": row.get("source_mode") or (creature_row.get("source_mode") if creature_row else None),
            "bundle_kind": export_row.get("bundle_kind") if export_row else None,
        },
        research_metadata=research_metadata,
    )
    runtime_capabilities = _runtime_capabilities(
        row,
        research_metadata=research_metadata,
        descriptor_ready=True,
        replayable=export_row is not None,
    )
    return {
        "version": 1,
        "specimenID": str(row["id"]),
        "creatureID": str(row["creature_id"]) if row.get("creature_id") is not None else None,
        "runID": row.get("run_id"),
        "campaignID": row.get("campaign_id"),
        "sourceKind": row.get("source_kind") or "compendium_specimen",
        "sourceMode": row.get("source_mode"),
        "sourceAlgorithm": row.get("source_algorithm"),
        "runtimeFamily": runtime_family,
        "runtimeCapabilities": runtime_capabilities,
        "configHash": row.get("config_hash"),
        "recordedAt": row.get("recorded_at"),
        "initialConditionFamily": row.get("initial_condition_family"),
        "taxonomy": {
            "familyID": creature_row.get("taxonomy_family_id") if creature_row else None,
            "genusID": creature_row.get("taxonomy_genus_id") if creature_row else None,
            "speciesID": creature_row.get("taxonomy_species_id") if creature_row else None,
            "confidence": creature_row.get("taxonomy_confidence") if creature_row else None,
            "method": creature_row.get("taxonomy_method") if creature_row else None,
            "version": creature_row.get("taxonomy_version") if creature_row else None,
        },
        "traitLabels": _loads_optional_json(creature_row.get("trait_labels_json")) if creature_row else None,
        "replay": {
            "bundleKind": export_row.get("bundle_kind") if export_row else None,
            "exportDir": export_row.get("export_dir") if export_row else None,
            "baseConfigPath": export_row.get("base_config_path") if export_row else None,
            "searchConfigPath": export_row.get("search_config_path") if export_row else None,
            "payloadPath": export_row.get("payload_path") if export_row else None,
        },
        "snapshots": {
            "genotype": genotype,
            "initialCondition": initial_condition,
            "metrics": metrics,
            "descriptorBundle": descriptor_bundle,
            "morphometrics": morphometrics,
        },
        "researchMetadata": research_metadata,
    }


def _manifest_string(manifest: dict[str, Any], key: str) -> str | None:
    value = manifest.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _manifest_string_list(manifest: dict[str, Any], key: str) -> list[str] | None:
    value = manifest.get(key)
    if isinstance(value, list) and all(isinstance(entry, str) and entry for entry in value):
        return sorted(set(cast(list[str], value)))
    return None


def _manifest_taxonomy_family(manifest: dict[str, Any]) -> str | None:
    taxonomy = manifest.get("taxonomy")
    if isinstance(taxonomy, dict):
        family_id = taxonomy.get("familyID")
        if isinstance(family_id, str) and family_id:
            return family_id
    return _manifest_string(manifest, "initialConditionFamily")


def _manifest_replay_export_dir(manifest: dict[str, Any]) -> str | None:
    replay = manifest.get("replay")
    if isinstance(replay, dict):
        export_dir = replay.get("exportDir")
        if isinstance(export_dir, str) and export_dir:
            return export_dir
    return None


def ingest_compendium(
    connection: DuckDBPyConnection,
    *,
    compendium_path: Path,
    study_id: str | None = None,
    label: str | None = None,
) -> str:
    resolved_study_id = register_study(
        connection,
        study_kind="discovery",
        label=label or compendium_path.stem,
        study_id=study_id,
        metadata_json={"sourceArtifact": str(compendium_path)},
    )
    artifact_id = register_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_kind="compendium_sqlite",
        path=compendium_path,
    )
    tables = ingest_sqlite_rows(connection, artifact_id=artifact_id, sqlite_path=compendium_path)
    if "specimens" not in tables:
        raise ValueError("Compendium is missing specimens; canonical warehouse ingest requires strict specimen rows.")
    if "creatures" not in tables:
        raise ValueError("Compendium is missing creatures; canonical warehouse ingest requires creature projections.")
    if "canonical_specimen_id" not in _sqlite_columns(compendium_path, "creatures"):
        raise ValueError(
            "Compendium is missing creatures.canonical_specimen_id; rebuild the canonical compendium before warehouse ingest."
        )

    creature_rows = _load_sqlite_rows(compendium_path, "creatures")
    creature_by_specimen_id = {
        str(row["canonical_specimen_id"]): row
        for row in creature_rows
        if row.get("canonical_specimen_id") is not None
    }
    latest_export_by_creature_id: dict[str, dict[str, Any]] = {}
    if "exports" in tables:
        for row in _load_sqlite_rows(compendium_path, "exports"):
            creature_id = row.get("creature_id")
            if creature_id is None:
                continue
            key = str(creature_id)
            existing = latest_export_by_creature_id.get(key)
            if existing is None or str(row.get("exported_at") or "") >= str(existing.get("exported_at") or ""):
                latest_export_by_creature_id[key] = row

    for row in _load_sqlite_rows(compendium_path, "specimens"):
            specimen_id = str(row["id"])
            creature_row = creature_by_specimen_id.get(specimen_id)
            if creature_row is None:
                continue
            creature_id = str(creature_row["id"])
            export_row = latest_export_by_creature_id.get(creature_id)
            research_metadata = cast(
                dict[str, Any] | None,
                _loads_optional_json(creature_row.get("research_metadata_json")),
            )
            terminal_descriptor = _normalize_terminal_descriptor(
                cast(dict[str, Any], json.loads(row["terminal_descriptor_json"]))
            )
            trajectory_descriptor = (
                json.loads(row["trajectory_descriptor_json"])
                if row.get("trajectory_descriptor_json")
                else {"centerVelocity": 0.0, "pathTortuosity": 0.0}
            )
            runtime_family = _runtime_family(
                {
                    "runtime_family": row.get("runtime_family"),
                    "source_mode": row.get("source_mode") or creature_row.get("source_mode"),
                    "bundle_kind": export_row.get("bundle_kind") if export_row else None,
                },
                research_metadata=research_metadata,
            )
            runtime_capabilities = _runtime_capabilities(
                row,
                research_metadata=research_metadata,
                descriptor_ready=True,
                replayable=export_row is not None,
            )
            specimen_manifest = _strict_specimen_manifest(
                row,
                creature_row=creature_row,
                export_row=export_row,
                research_metadata=research_metadata,
            )
            manifest_source_kind = _manifest_string(specimen_manifest, "sourceKind")
            manifest_source_mode = _manifest_string(specimen_manifest, "sourceMode")
            manifest_source_algorithm = _manifest_string(specimen_manifest, "sourceAlgorithm")
            manifest_config_hash = _manifest_string(specimen_manifest, "configHash")
            manifest_initial_condition_family = _manifest_string(
                specimen_manifest,
                "initialConditionFamily",
            )
            manifest_recorded_at = _manifest_string(specimen_manifest, "recordedAt")
            manifest_runtime_family = _manifest_string(specimen_manifest, "runtimeFamily")
            manifest_runtime_capabilities = _manifest_string_list(
                specimen_manifest,
                "runtimeCapabilities",
            )
            manifest_family_kind = _manifest_taxonomy_family(specimen_manifest)
            manifest_export_dir = _manifest_replay_export_dir(specimen_manifest)
            upsert_specimen(
                connection,
                {
                    "specimen_id": specimen_id,
                    "source_creature_id": creature_id,
                    "study_id": resolved_study_id,
                    "run_id": row.get("run_id"),
                    "campaign_id": row.get("campaign_id"),
                    "source_kind": manifest_source_kind or row.get("source_kind") or "compendium_specimen",
                    "source_mode": manifest_source_mode or row.get("source_mode") or creature_row.get("source_mode"),
                    "source_algorithm": (
                        manifest_source_algorithm
                        or row.get("source_algorithm")
                        or creature_row.get("source_algorithm")
                    ),
                    "config_hash": manifest_config_hash or row.get("config_hash") or creature_row.get("config_hash"),
                    "initial_condition_family": (
                        manifest_initial_condition_family
                        or row.get("initial_condition_family")
                        or creature_row.get("initial_condition_family")
                    ),
                    "regime_family": None,
                    "geometry_family": None,
                    "canonical_family": None,
                    "family_kind": manifest_family_kind or _taxonomy_family(creature_row),
                    "score": creature_row.get("score"),
                    "filters_passed": _bool_or_none(export_row.get("filters_passed")) if export_row else None,
                    "search_is_stable_candidate": _bool_or_none(creature_row.get("is_stable")),
                    "recorded_at": manifest_recorded_at or row.get("recorded_at") or creature_row.get("recorded_at"),
                    "results_path": None,
                    "export_dir": manifest_export_dir or (export_row.get("export_dir") if export_row else None),
                    "activity_path": row.get("activity_path"),
                    "fingerprint_path": row.get("fingerprint_path"),
                    "runtime_family": manifest_runtime_family or runtime_family,
                    "runtime_capabilities_json": manifest_runtime_capabilities or runtime_capabilities,
                    "specimen_manifest_json": specimen_manifest,
                    "provenance_json": {
                        "specimen": row,
                        "creature": creature_row,
                        "export": export_row,
                        "terminal": terminal_descriptor,
                        "trajectory": trajectory_descriptor,
                        "research_metadata": research_metadata,
                    },
                },
            )
            register_specimen_study(
                connection,
                study_id=resolved_study_id,
                specimen_id=specimen_id,
            )
            terminal_axes = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal_descriptor,
                trajectory=trajectory_descriptor,
                specimen_id=specimen_id,
            )
            transformed_axes = transform_axes(terminal_axes)
            replace_specimen_axes(
                connection,
                specimen_id=specimen_id,
                axis_rows=[
                    (
                        axis_id,
                        "terminal",
                        float(terminal_axes[axis_id]),
                        float(transformed_axes[axis_id]),
                    )
                    for axis_id in terminal_axes
                ],
            )

    return resolved_study_id
