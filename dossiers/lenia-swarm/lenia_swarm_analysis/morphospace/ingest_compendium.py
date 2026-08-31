from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transformation_metrics import (
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

from .warehouse import (
    CANONICAL_COMPENDIUM_STUDY_LABEL,
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
    canonical_compendium_study_id,
    file_sha256,
    json_text,
    mark_derived_artifact_state,
    normalize_optional_timestamp,
    register_artifact,
    register_source_receipt,
    register_study,
    row_sha256,
    utc_now,
    warehouse_transaction,
)

SPECIMEN_PROJECTION = frozenset(
    {
        "id",
        "result_id",
        "creature_id",
        "run_id",
        "campaign_id",
        "source_kind",
        "source_mode",
        "source_algorithm",
        "config_hash",
        "initial_condition_family",
        "recorded_at",
        "activity_path",
        "fingerprint_path",
        "terminal_descriptor_json",
        "trajectory_descriptor_json",
        "runtime_family",
        "runtime_capabilities_json",
    }
)
CREATURE_PROJECTION = frozenset(
    {
        "id",
        "canonical_specimen_id",
        "run_id",
        "campaign_id",
        "source_mode",
        "source_algorithm",
        "config_hash",
        "initial_condition_family",
        "score",
        "is_stable",
        "recorded_at",
        "taxonomy_family_id",
        "taxonomy_genus_id",
        "taxonomy_species_id",
        "taxonomy_confidence",
        "taxonomy_method",
        "taxonomy_version",
        "trait_labels_json",
        "catalog_status",
        "runtime_family",
        "runtime_capabilities_json",
    }
)
EXPORT_PROJECTION = frozenset(
    {
        "creature_id",
        "run_id",
        "campaign_id",
        "bundle_kind",
        "base_config_path",
        "search_config_path",
        "payload_path",
        "export_dir",
        "exported_at",
        "filters_passed",
        "runtime_family",
        "runtime_capabilities_json",
    }
)
RESULT_PROJECTION = frozenset({"id", "backend", "implementation_json"})
RECEIPT_PROJECTION_TABLES = ("creatures", "exports", "results", "specimens")


@dataclass(frozen=True)
class CompendiumSnapshot:
    connection: sqlite3.Connection
    tables: tuple[str, ...]
    row_counts: dict[str, int]
    schema_version: str
    content_fingerprint: str
    size_bytes: int
    source_identity: tuple[int, int, int, int]


def _source_identity(path: Path) -> tuple[int, int, int, int]:
    wal_path = Path(f"{path}-wal")
    if wal_path.exists() and wal_path.stat().st_size > 0:
        raise ValueError(
            f"{path}: non-empty SQLite WAL; checkpoint or quiesce the compendium "
            "before warehouse ingest"
        )
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _sqlite_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    }


def _open_compendium_snapshot(
    path: Path,
    *,
    run_id: str | None = None,
) -> CompendiumSnapshot:
    resolved_path = path.expanduser().resolve(strict=True)
    source_identity = _source_identity(resolved_path)
    connection = sqlite3.connect(f"{resolved_path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        tables = tuple(sorted(_sqlite_tables(connection)))
        row_counts: dict[str, int] = {}
        for table_name in RECEIPT_PROJECTION_TABLES:
            if table_name not in tables:
                continue
            if run_id is not None and "run_id" in _sqlite_columns(connection, table_name):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table_name)} WHERE run_id = ?",
                    [run_id],
                ).fetchone()[0]
            else:
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
                ).fetchone()[0]
            row_counts[table_name] = int(count)
        if "compendium_meta" in tables:
            schema_rows = connection.execute(
                "SELECT schema_version FROM compendium_meta LIMIT 2"
            ).fetchall()
            if len(schema_rows) != 1 or schema_rows[0][0] is None:
                raise ValueError(
                    f"{resolved_path}: expected exactly one compendium schema version"
                )
            schema_version = str(int(schema_rows[0][0]))
        else:
            schema_row = connection.execute("PRAGMA user_version").fetchone()
            schema_version = str(int(schema_row[0])) if schema_row is not None else "0"
        content_fingerprint = file_sha256(resolved_path)
        if _source_identity(resolved_path) != source_identity:
            raise ValueError(f"{resolved_path}: compendium changed while opening snapshot")
        return CompendiumSnapshot(
            connection=connection,
            tables=tables,
            row_counts=row_counts,
            schema_version=schema_version,
            content_fingerprint=content_fingerprint,
            size_bytes=source_identity[2],
            source_identity=source_identity,
        )
    except BaseException:
        connection.close()
        raise


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _iter_compendium_rows(
    connection: sqlite3.Connection,
    *,
    tables: set[str],
    run_id: str | None,
    batch_size: int = 2048,
) -> Iterator[
    tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any] | None,
        dict[str, Any] | None,
    ]
]:
    all_specimen_columns = _sqlite_columns(connection, "specimens")
    all_creature_columns = _sqlite_columns(connection, "creatures")
    all_export_columns = _sqlite_columns(connection, "exports") if "exports" in tables else set()
    all_result_columns = _sqlite_columns(connection, "results") if "results" in tables else set()
    specimen_columns = sorted(all_specimen_columns & SPECIMEN_PROJECTION)
    creature_columns = sorted(all_creature_columns & CREATURE_PROJECTION)
    export_columns = sorted(all_export_columns & EXPORT_PROJECTION)
    result_columns = (
        sorted(all_result_columns & RESULT_PROJECTION)
        if "result_id" in all_specimen_columns
        else []
    )
    required = {
        "specimens": {"id", "terminal_descriptor_json"} - all_specimen_columns,
        "creatures": {"id", "canonical_specimen_id"} - all_creature_columns,
    }
    missing = {table: columns for table, columns in required.items() if columns}
    if missing:
        details = "; ".join(
            f"{table}: {', '.join(sorted(columns))}" for table, columns in missing.items()
        )
        raise ValueError(f"compendium is missing required columns ({details})")

    def projection(alias: str, prefix: str, columns: list[str]) -> list[str]:
        return [
            f"{alias}.{_quote_identifier(column)} AS {_quote_identifier(prefix + column)}"
            for column in columns
        ]

    select_columns = [
        *projection("s", "specimen__", specimen_columns),
        *projection("c", "creature__", creature_columns),
        *projection("e", "export__", export_columns),
        *projection("r", "result__", result_columns),
    ]
    sql = (
        f"SELECT {', '.join(select_columns)} "
        "FROM specimens AS s "
        "JOIN creatures AS c ON c.canonical_specimen_id = s.id "
    )
    params: list[Any] = []
    if export_columns:
        export_run_clause = ""
        if run_id is not None:
            if "run_id" not in all_export_columns:
                raise ValueError("run-scoped ingest requires exports.run_id")
            export_run_clause = " WHERE run_id = ?"
            params.append(run_id)
        export_order = (
            "coalesce(exported_at, '') DESC, rowid DESC"
            if "exported_at" in all_export_columns
            else "rowid DESC"
        )
        sql += (
            "LEFT JOIN ("
            f"SELECT {', '.join(_quote_identifier(column) for column in export_columns)}, "
            "row_number() OVER ("
            "PARTITION BY creature_id "
            f"ORDER BY {export_order}"
            f") AS latest_rank FROM exports{export_run_clause}"
            ") AS e ON e.creature_id = c.id AND e.latest_rank = 1 "
        )
    if result_columns:
        sql += (
            "LEFT JOIN results AS r ON r.id = CASE "
            "WHEN s.result_id LIKE 'result:%' THEN substr(s.result_id, 8) "
            "ELSE s.result_id END "
        )
    clauses: list[str] = []
    if run_id is not None:
        if "run_id" not in all_specimen_columns or "run_id" not in all_creature_columns:
            raise ValueError("run-scoped ingest requires specimens.run_id and creatures.run_id")
        clauses.extend(["s.run_id = ?", "c.run_id = ?"])
        params.extend([run_id, run_id])
    if "catalog_status" in all_creature_columns:
        clauses.append("c.catalog_status IN ('active', 'protected')")
    if clauses:
        sql += "WHERE " + " AND ".join(clauses) + " "
    sql += "ORDER BY s.id"

    cursor = connection.execute(sql, params)
    while batch := cursor.fetchmany(batch_size):
        for row in batch:
            specimen = {column: row[f"specimen__{column}"] for column in specimen_columns}
            creature = {column: row[f"creature__{column}"] for column in creature_columns}
            export_candidate = {column: row[f"export__{column}"] for column in export_columns}
            export = (
                export_candidate
                if any(value is not None for value in export_candidate.values())
                else None
            )
            result_candidate = {column: row[f"result__{column}"] for column in result_columns}
            result = (
                result_candidate
                if any(value is not None for value in result_candidate.values())
                else None
            )
            yield specimen, creature, export, result


def _validate_canonical_creature_links(
    connection: sqlite3.Connection,
    *,
    run_id: str | None,
) -> None:
    creature_columns = _sqlite_columns(connection, "creatures")
    specimen_columns = _sqlite_columns(connection, "specimens")
    clauses: list[str] = []
    params: list[Any] = []
    if "catalog_status" in creature_columns:
        clauses.append("c.catalog_status IN ('active', 'protected')")
    if run_id is not None:
        if "run_id" not in creature_columns or "run_id" not in specimen_columns:
            raise ValueError("run-scoped ingest requires creatures.run_id and specimens.run_id")
        clauses.append("c.run_id = ?")
        params.append(run_id)
    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    null_count = int(
        connection.execute(
            f"""
            SELECT count(*) FROM creatures AS c
            WHERE {where_sql}
              AND (c.canonical_specimen_id IS NULL OR trim(c.canonical_specimen_id) = '')
            """,
            params,
        ).fetchone()[0]
    )
    dangling_count = int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM creatures AS c
            LEFT JOIN specimens AS s ON s.id = c.canonical_specimen_id
            WHERE {where_sql}
              AND c.canonical_specimen_id IS NOT NULL
              AND trim(c.canonical_specimen_id) != ''
              AND s.id IS NULL
            """,
            params,
        ).fetchone()[0]
    )
    duplicate_count = int(
        connection.execute(
            f"""
            SELECT count(*)
            FROM (
                SELECT c.canonical_specimen_id
                FROM creatures AS c
                WHERE {where_sql}
                  AND c.canonical_specimen_id IS NOT NULL
                  AND trim(c.canonical_specimen_id) != ''
                GROUP BY c.canonical_specimen_id
                HAVING count(*) > 1
            )
            """,
            params,
        ).fetchone()[0]
    )
    run_mismatch_count = 0
    if "run_id" in creature_columns and "run_id" in specimen_columns:
        run_mismatch_count = int(
            connection.execute(
                f"""
                SELECT count(*)
                FROM creatures AS c
                JOIN specimens AS s ON s.id = c.canonical_specimen_id
                WHERE {where_sql} AND c.run_id IS DISTINCT FROM s.run_id
                """,
                params,
            ).fetchone()[0]
        )
    counts = {
        "null": null_count,
        "dangling": dangling_count,
        "duplicate": duplicate_count,
        "runMismatch": run_mismatch_count,
    }
    if any(counts.values()):
        raise ValueError(f"invalid canonical creature links: {counts}")


def _validate_compendium_partition_mode(
    connection: DuckDBPyConnection,
    *,
    run_id: str | None,
) -> None:
    opposite_scope = "IS NULL" if run_id is not None else "IS NOT NULL"
    conflicting = connection.execute(
        f"""
        SELECT count(*)
        FROM studies
        WHERE studies.study_kind = 'discovery'
          AND studies.run_id {opposite_scope}
          AND (
              json_extract_string(studies.metadata_json, '$.projection') = 'compact-v10'
              OR EXISTS (
                  SELECT 1
                  FROM artifacts
                  WHERE artifacts.study_id = studies.study_id
                    AND artifacts.artifact_kind IN ('compendium', 'compendium_sqlite')
              )
          )
          AND EXISTS (
              SELECT 1
              FROM study_specimens
              WHERE study_specimens.study_id = studies.study_id
          )
        """
    ).fetchone()
    if conflicting is not None and int(conflicting[0]) > 0:
        requested = "run-scoped" if run_id is not None else "aggregate"
        existing = "aggregate" if run_id is not None else "run-scoped"
        raise ValueError(
            f"cannot mix {requested} and {existing} compendium studies in one warehouse; "
            "rebuild or migrate into a single canonical partitioning mode"
        )


def _canonical_append_study_id(connection: DuckDBPyConnection) -> str:
    study_id = canonical_compendium_study_id()
    row = connection.execute(
        "SELECT study_kind, run_id, label FROM studies WHERE study_id = ?",
        [study_id],
    ).fetchone()
    expected = ("discovery", None, CANONICAL_COMPENDIUM_STUDY_LABEL)
    if row != expected:
        raise ValueError(
            "native-v2 run append requires the canonical aggregate compendium study; "
            f"expected {expected!r}, found {row!r}"
        )
    return study_id


def _validate_native_v2_append_staging(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    run_id: str,
) -> int:
    staged_row = connection.execute(
        "SELECT count(*) FROM staged_compendium_specimens"
    ).fetchone()
    if staged_row is None:
        raise AssertionError("native-v2 staging count query returned no row")
    staged_count = int(staged_row[0])
    if staged_count == 0:
        raise ValueError(f"compendium contains no canonical specimens for run_id={run_id!r}")

    invalid_row = connection.execute(
        """
        SELECT count(*)
        FROM staged_compendium_specimens AS specimens
        JOIN staged_compendium_descriptors AS descriptors USING (specimen_id)
        WHERE specimens.study_id IS DISTINCT FROM ?
           OR specimens.run_id IS DISTINCT FROM ?
           OR specimens.source_mode IS DISTINCT FROM 'replay'
           OR specimens.source_algorithm IS DISTINCT FROM 'canonical-replay'
           OR specimens.runtime_family IS DISTINCT FROM 'flow_lenia'
           OR descriptors.descriptor_version IS DISTINCT FROM ?
           OR descriptors.terminal_version IS DISTINCT FROM ?
           OR descriptors.normalization_policy IS DISTINCT FROM ?
           OR descriptors.fingerprint_resolution IS DISTINCT FROM 32
           OR json_extract_string(
                specimens.specimen_manifest_json, '$.effectiveReplay.backend'
           ) IS NULL
           OR json_extract_string(
                specimens.specimen_manifest_json, '$.effectiveReplay.implementation.mode'
           ) IS NULL
           OR json_extract_string(
                specimens.specimen_manifest_json, '$.effectiveReplay.resultId'
           ) IS NULL
           OR json_extract(
                specimens.specimen_manifest_json, '$.effectiveReplay'
           ) IS DISTINCT FROM json_extract(
                specimens.provenance_json, '$.effectiveReplay'
           )
        """,
        [study_id, run_id, DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY],
    ).fetchone()
    if invalid_row is None:
        raise AssertionError("native-v2 staging validation query returned no row")
    invalid_count = int(invalid_row[0])
    if invalid_count:
        raise ValueError(
            f"run_id={run_id!r} contains {invalid_count} rows outside the canonical "
            "Flow Lenia native-v2 replay contract"
        )

    conflicts = connection.execute(
        """
        SELECT staged.specimen_id
        FROM staged_compendium_specimens AS staged
        JOIN specimens AS existing USING (specimen_id)
        JOIN staged_compendium_descriptors AS staged_descriptor USING (specimen_id)
        LEFT JOIN specimen_descriptors AS existing_descriptor USING (specimen_id)
        WHERE existing.study_id IS DISTINCT FROM ?
           OR existing.source_creature_id IS DISTINCT FROM staged.source_creature_id
           OR existing.run_id IS DISTINCT FROM staged.run_id
           OR existing.source_kind IS DISTINCT FROM staged.source_kind
           OR existing.source_mode IS DISTINCT FROM staged.source_mode
           OR existing.source_algorithm IS DISTINCT FROM staged.source_algorithm
           OR existing.config_hash IS DISTINCT FROM staged.config_hash
           OR existing.runtime_family IS DISTINCT FROM staged.runtime_family
           OR existing_descriptor.content_sha256 IS DISTINCT FROM staged_descriptor.content_sha256
           OR json_extract(
                existing.specimen_manifest_json, '$.effectiveReplay'
           ) IS DISTINCT FROM json_extract(
                staged.specimen_manifest_json, '$.effectiveReplay'
           )
           OR EXISTS (
                SELECT 1
                FROM study_specimens AS membership
                WHERE membership.specimen_id = staged.specimen_id
                  AND membership.study_id != ?
           )
        ORDER BY staged.specimen_id
        LIMIT 10
        """,
        [study_id, study_id],
    ).fetchall()
    if conflicts:
        specimen_ids = ", ".join(str(row[0]) for row in conflicts)
        raise ValueError(
            "native-v2 append would overwrite non-identical warehouse specimens: "
            f"{specimen_ids}"
        )
    return staged_count


def _invalidate_native_v2_feature_spaces(
    connection: DuckDBPyConnection,
    *,
    run_id: str,
    specimen_count: int,
    source_receipt_id: str,
) -> None:
    from .common_morphology import FEATURE_SPACE_ID as common_feature_space_id
    from .derive_lenia_features import FEATURE_SPACE_ID as terminal_feature_space_id

    metadata = {
        "appendedSpecimenCount": specimen_count,
        "runId": run_id,
        "sourceReceiptId": source_receipt_id,
    }
    for feature_space_id in (terminal_feature_space_id, common_feature_space_id):
        mark_derived_artifact_state(
            connection,
            artifact_kind="feature-space",
            feature_space_id=feature_space_id,
            descriptor_version=DESCRIPTOR_VERSION,
            normalization_policy=NORMALIZATION_POLICY,
            status="invalid",
            reason="native-v2 replay append requires global regeneration",
            metadata_json=metadata,
        )


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


def _effective_replay_projection(result_row: dict[str, Any] | None) -> dict[str, Any] | None:
    if result_row is None:
        return None
    backend = result_row.get("backend")
    result_id = result_row.get("id")
    implementation = _loads_optional_json(result_row.get("implementation_json"))
    if not isinstance(backend, str) or not backend.strip():
        return None
    if not isinstance(result_id, str) or not result_id.strip():
        return None
    if not isinstance(implementation, dict):
        return None
    return {
        "backend": backend,
        "implementation": implementation,
        "resultId": result_id,
    }


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


def _canonical_export_kind(row: dict[str, Any]) -> str | None:
    bundle_kind = row.get("bundle_kind")
    if isinstance(bundle_kind, str) and bundle_kind:
        return bundle_kind
    return None


def _runtime_family(row: dict[str, Any]) -> str:
    explicit = row.get("runtime_family")
    if isinstance(explicit, str) and explicit:
        return explicit
    bundle_kind = _canonical_export_kind(row)
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
    descriptor_ready: bool = False,
    replayable: bool = False,
) -> list[str]:
    explicit = _loads_optional_json(row.get("runtime_capabilities_json"))
    if isinstance(explicit, list) and all(isinstance(value, str) for value in explicit):
        return sorted(set(cast(list[str], explicit)))

    capabilities = {"archive", "warehouse_ingest"}
    if replayable:
        capabilities.update({"replay", "intervention", "media"})
    if descriptor_ready:
        capabilities.add("topology")
    return sorted(capabilities)


def _compact_specimen_manifest(
    row: dict[str, Any],
    *,
    creature_row: dict[str, Any],
    export_row: dict[str, Any] | None,
    effective_replay: dict[str, Any] | None,
    runtime_family: str,
    runtime_capabilities: list[str],
    receipt_id: str,
    artifact_id: str,
    descriptor_hash: str,
) -> dict[str, Any]:
    taxonomy = {
        "familyID": creature_row.get("taxonomy_family_id"),
        "genusID": creature_row.get("taxonomy_genus_id"),
        "speciesID": creature_row.get("taxonomy_species_id"),
        "confidence": creature_row.get("taxonomy_confidence"),
        "method": creature_row.get("taxonomy_method"),
        "version": creature_row.get("taxonomy_version"),
    }
    replay = {
        "bundleKind": export_row.get("bundle_kind") if export_row else None,
        "exportDir": export_row.get("export_dir") if export_row else None,
        "baseConfigPath": export_row.get("base_config_path") if export_row else None,
        "searchConfigPath": export_row.get("search_config_path") if export_row else None,
        "payloadPath": export_row.get("payload_path") if export_row else None,
    }
    manifest = {
        "version": 1,
        "specimenID": str(row["id"]),
        "creatureID": str(creature_row["id"]),
        "runID": row.get("run_id"),
        "campaignID": row.get("campaign_id"),
        "sourceKind": row.get("source_kind") or "compendium_specimen",
        "sourceMode": row.get("source_mode") or creature_row.get("source_mode"),
        "sourceAlgorithm": row.get("source_algorithm") or creature_row.get("source_algorithm"),
        "runtimeFamily": runtime_family,
        "runtimeCapabilities": runtime_capabilities,
        "configHash": row.get("config_hash") or creature_row.get("config_hash"),
        "recordedAt": row.get("recorded_at") or creature_row.get("recorded_at"),
        "initialConditionFamily": row.get("initial_condition_family")
        or creature_row.get("initial_condition_family"),
        "taxonomy": {key: value for key, value in taxonomy.items() if value is not None},
        "traitLabels": _loads_optional_json(creature_row.get("trait_labels_json")),
        "replay": {key: value for key, value in replay.items() if value is not None},
        "effectiveReplay": effective_replay,
        "sourceReceiptId": receipt_id,
        "sourceArtifactId": artifact_id,
        "descriptorHash": descriptor_hash,
    }
    return {key: value for key, value in manifest.items() if value is not None}


def _append_columnar_rows(
    connection: DuckDBPyConnection,
    *,
    table_name: str,
    expressions: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    columns = [list(column) for column in zip(*rows, strict=True)]
    connection.execute(
        f"INSERT INTO {table_name} SELECT {', '.join(expressions)}",
        columns,
    )


def _create_compendium_staging_tables(connection: DuckDBPyConnection) -> None:
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE staged_compendium_specimens "
        "AS SELECT * FROM specimens WHERE FALSE"
    )
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE staged_compendium_descriptors "
        "AS SELECT * FROM specimen_descriptors WHERE FALSE"
    )
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE staged_compendium_axes "
        "AS SELECT * FROM specimen_axes WHERE FALSE"
    )


def _merge_compendium_staging(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO specimen_descriptors "
        "SELECT * FROM staged_compendium_descriptors"
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO specimens
        SELECT
            staged.specimen_id,
            coalesce(staged.source_creature_id, existing.source_creature_id),
            coalesce(existing.study_id, staged.study_id),
            coalesce(staged.run_id, existing.run_id),
            coalesce(staged.campaign_id, existing.campaign_id),
            staged.source_kind,
            coalesce(staged.source_mode, existing.source_mode),
            coalesce(staged.source_algorithm, existing.source_algorithm),
            coalesce(staged.config_hash, existing.config_hash),
            coalesce(staged.initial_condition_family, existing.initial_condition_family),
            coalesce(staged.regime_family, existing.regime_family),
            coalesce(staged.geometry_family, existing.geometry_family),
            coalesce(staged.canonical_family, existing.canonical_family),
            coalesce(staged.family_kind, existing.family_kind),
            coalesce(staged.score, existing.score),
            coalesce(staged.filters_passed, existing.filters_passed),
            coalesce(staged.search_is_stable_candidate, existing.search_is_stable_candidate),
            coalesce(staged.recorded_at, existing.recorded_at),
            coalesce(staged.results_path, existing.results_path),
            coalesce(staged.export_dir, existing.export_dir),
            coalesce(staged.activity_path, existing.activity_path),
            coalesce(staged.fingerprint_path, existing.fingerprint_path),
            staged.provenance_json,
            coalesce(staged.runtime_family, existing.runtime_family),
            staged.runtime_capabilities_json,
            staged.specimen_manifest_json,
            staged.descriptor_version,
            staged.terminal_version,
            staged.normalization_policy,
            staged.fingerprint_resolution
        FROM staged_compendium_specimens AS staged
        LEFT JOIN specimens AS existing USING (specimen_id)
        """
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO study_specimens (study_id, specimen_id)
        SELECT ?, specimen_id FROM staged_compendium_specimens
        """,
        [study_id],
    )
    connection.execute(
        """
        DELETE FROM specimen_axes
        WHERE specimen_id IN (SELECT specimen_id FROM staged_compendium_specimens)
          AND axis_family = 'terminal'
        """
    )
    connection.execute(
        "INSERT INTO specimen_axes SELECT * FROM staged_compendium_axes"
    )


def _reconcile_primary_specimen_studies(connection: DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE affected_compendium_specimens AS
        SELECT specimen_id FROM incoming_compendium_specimens
        UNION
        SELECT specimen_id FROM stale_compendium_specimens
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE preferred_compendium_studies AS
        SELECT specimen_id, study_id
        FROM (
            SELECT
                study_specimens.specimen_id,
                study_specimens.study_id,
                row_number() OVER (
                    PARTITION BY study_specimens.specimen_id
                    ORDER BY
                        CASE WHEN studies.run_id IS NULL THEN 0 ELSE 1 END,
                        study_specimens.study_id
                ) AS ownership_rank
            FROM study_specimens
            JOIN studies USING (study_id)
            JOIN affected_compendium_specimens USING (specimen_id)
        ) AS ranked_memberships
        WHERE ownership_rank = 1
        """
    )
    connection.execute(
        """
        UPDATE specimens
        SET study_id = preferred_compendium_studies.study_id
        FROM preferred_compendium_studies
        WHERE specimens.specimen_id = preferred_compendium_studies.specimen_id
          AND specimens.study_id IS DISTINCT FROM preferred_compendium_studies.study_id
        """
    )


def _delete_topology_children(
    connection: DuckDBPyConnection,
    *,
    parent_study_id: str,
) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE stale_topology_studies AS
        SELECT study_id
        FROM studies
        WHERE parent_study_id = ? AND study_kind = 'topology_run'
        """,
        [parent_study_id],
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE stale_topology_artifacts AS
        SELECT artifact_id
        FROM artifacts
        WHERE study_id IN (SELECT study_id FROM stale_topology_studies)
        """
    )
    connection.execute(
        """
        DELETE FROM topology_features
        WHERE topology_run_id IN (
            SELECT topology_run_id
            FROM topology_runs
            WHERE study_id IN (SELECT study_id FROM stale_topology_studies)
        )
        """
    )
    connection.execute(
        "DELETE FROM topology_runs "
        "WHERE study_id IN (SELECT study_id FROM stale_topology_studies)"
    )
    connection.execute(
        "DELETE FROM raw_json_objects "
        "WHERE artifact_id IN (SELECT artifact_id FROM stale_topology_artifacts)"
    )
    connection.execute(
        "DELETE FROM raw_jsonl_rows "
        "WHERE artifact_id IN (SELECT artifact_id FROM stale_topology_artifacts)"
    )
    connection.execute(
        "DELETE FROM artifacts WHERE artifact_id IN (SELECT artifact_id FROM stale_topology_artifacts)"
    )
    connection.execute(
        "DELETE FROM studies WHERE study_id IN (SELECT study_id FROM stale_topology_studies)"
    )


def _descriptor_contract(
    terminal: dict[str, Any],
    *,
    specimen_id: str,
) -> tuple[str, str, str, int]:
    descriptor_version = str(terminal.get("descriptorVersion") or terminal.get("version") or "")
    terminal_version = str(terminal.get("version") or "")
    normalization_policy = str(terminal.get("normalizationPolicy") or "")
    border_mode = str(terminal.get("borderMode") or "")
    resolution = terminal.get("fingerprintResolution")
    if isinstance(resolution, bool) or not isinstance(resolution, (int, float, str)):
        raise ValueError(f"{specimen_id}: missing integer terminal fingerprintResolution")
    try:
        fingerprint_resolution = int(resolution)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{specimen_id}: missing integer terminal fingerprintResolution"
        ) from exc
    if isinstance(resolution, float) and not resolution.is_integer():
        raise ValueError(f"{specimen_id}: terminal fingerprintResolution must be integral")
    if isinstance(resolution, str) and str(fingerprint_resolution) != resolution.strip():
        raise ValueError(f"{specimen_id}: terminal fingerprintResolution must be integral")
    expected = (DESCRIPTOR_VERSION, TERMINAL_VERSION, NORMALIZATION_POLICY, "torus", 32)
    actual = (
        descriptor_version,
        terminal_version,
        normalization_policy,
        border_mode,
        fingerprint_resolution,
    )
    if actual != expected:
        raise ValueError(
            f"{specimen_id}: unsupported descriptor contract {actual!r}; expected {expected!r}. "
            "Rebuild legacy descriptors before v9 ingest."
        )
    return descriptor_version, terminal_version, normalization_policy, fingerprint_resolution


def _ingest_compendium(
    connection: DuckDBPyConnection,
    *,
    compendium_path: Path,
    source: CompendiumSnapshot,
    study_id: str | None = None,
    label: str | None = None,
    run_id: str | None = None,
    append_native_v2_run: bool = False,
) -> str:
    if append_native_v2_run:
        if run_id is None:
            raise ValueError("native-v2 append requires a run_id")
        if study_id is not None or label is not None:
            raise ValueError("native-v2 append does not accept study_id or label overrides")
        resolved_study_id = _canonical_append_study_id(connection)
    else:
        _validate_compendium_partition_mode(connection, run_id=run_id)
        resolved_label = label or (
            CANONICAL_COMPENDIUM_STUDY_LABEL if run_id is None else compendium_path.stem
        )
        if run_id is not None:
            resolved_label = f"{resolved_label}:{run_id}"
        resolved_study_id_override = study_id
        if resolved_study_id_override is None and run_id is None and label is None:
            resolved_study_id_override = canonical_compendium_study_id()
        resolved_study_id = register_study(
            connection,
            study_kind="discovery",
            label=resolved_label,
            run_id=run_id,
            study_id=resolved_study_id_override,
            metadata_json={
                "sourceArtifact": str(compendium_path),
                "runId": run_id,
                "projection": "compact-v10",
            },
        )
    artifact_id = register_artifact(
        connection,
        study_id=resolved_study_id,
        artifact_kind="compendium_sqlite",
        path=compendium_path,
        metadata_json={
            "nativeV2RunAppend": append_native_v2_run,
            "runScopedRefresh": run_id is not None,
            "sourceSnapshotPolicy": "sqlite-read-transaction-no-wal-v1",
        },
        hash_content=False,
        content_fingerprint=source.content_fingerprint,
        size_bytes=source.size_bytes,
    )
    tables = list(source.tables)
    receipt_id = register_source_receipt(
        connection,
        study_id=resolved_study_id,
        artifact_id=artifact_id,
        source_kind="compendium_sqlite",
        source_schema_version=source.schema_version,
        source_tables=sorted(source.row_counts),
        source_row_counts=source.row_counts,
        metadata_json={
            "nativeV2RunAppend": append_native_v2_run,
            "runScopedRefresh": run_id is not None,
            "sourceSnapshotPolicy": "sqlite-read-transaction-no-wal-v1",
            "availableSourceTables": tables,
            "receiptProjectionTables": sorted(source.row_counts),
        },
    )
    if "specimens" not in tables:
        raise ValueError(
            "Compendium is missing specimens; "
            "canonical warehouse ingest requires strict specimen rows."
        )
    if "creatures" not in tables:
        raise ValueError(
            "Compendium is missing creatures; "
            "canonical warehouse ingest requires creature projections."
        )
    if "canonical_specimen_id" not in _sqlite_columns(source.connection, "creatures"):
        raise ValueError(
            "Compendium is missing creatures.canonical_specimen_id; "
            "rebuild the canonical compendium before warehouse ingest."
        )
    _validate_canonical_creature_links(source.connection, run_id=run_id)

    _create_compendium_staging_tables(connection)
    staged_specimens: list[tuple[Any, ...]] = []
    staged_descriptors: list[tuple[Any, ...]] = []
    staged_axes: list[tuple[Any, ...]] = []

    def flush_staging() -> None:
        _append_columnar_rows(
            connection,
            table_name="staged_compendium_specimens",
            expressions=(
                *("unnest(?::VARCHAR[])" for _ in range(14)),
                "unnest(?::DOUBLE[])",
                "unnest(?::BOOLEAN[])",
                "unnest(?::BOOLEAN[])",
                "unnest(?::TIMESTAMP[])",
                *("unnest(?::VARCHAR[])" for _ in range(4)),
                "CAST(unnest(?::VARCHAR[]) AS JSON)",
                "unnest(?::VARCHAR[])",
                "CAST(unnest(?::VARCHAR[]) AS JSON)",
                "CAST(unnest(?::VARCHAR[]) AS JSON)",
                *("unnest(?::VARCHAR[])" for _ in range(3)),
                "unnest(?::INTEGER[])",
            ),
            rows=staged_specimens,
        )
        _append_columnar_rows(
            connection,
            table_name="staged_compendium_descriptors",
            expressions=(
                *("unnest(?::VARCHAR[])" for _ in range(4)),
                "unnest(?::INTEGER[])",
                "CAST(unnest(?::VARCHAR[]) AS JSON)",
                "CAST(unnest(?::VARCHAR[]) AS JSON)",
                "unnest(?::VARCHAR[])",
                "unnest(?::TIMESTAMP[])",
            ),
            rows=staged_descriptors,
        )
        _append_columnar_rows(
            connection,
            table_name="staged_compendium_axes",
            expressions=(
                "unnest(?::VARCHAR[])",
                "unnest(?::VARCHAR[])",
                "unnest(?::VARCHAR[])",
                "unnest(?::DOUBLE[])",
                "unnest(?::DOUBLE[])",
            ),
            rows=staged_axes,
        )
        staged_specimens.clear()
        staged_descriptors.clear()
        staged_axes.clear()

    for row, creature_row, export_row, result_row in _iter_compendium_rows(
        source.connection,
        tables=set(tables),
        run_id=run_id,
    ):
        specimen_id = str(row["id"])
        source_creature_id = str(creature_row["id"])
        terminal_descriptor = _normalize_terminal_descriptor(
            cast(dict[str, Any], json.loads(row["terminal_descriptor_json"]))
        )
        trajectory_descriptor = (
            json.loads(row["trajectory_descriptor_json"])
            if row.get("trajectory_descriptor_json")
            else {"centerVelocity": 0.0, "pathTortuosity": 0.0}
        )
        (
            descriptor_version,
            terminal_version,
            normalization_policy,
            fingerprint_resolution,
        ) = _descriptor_contract(terminal_descriptor, specimen_id=specimen_id)
        runtime_family = _runtime_family(
            {
                "runtime_family": row.get("runtime_family")
                or creature_row.get("runtime_family")
                or (export_row.get("runtime_family") if export_row else None),
                "source_mode": row.get("source_mode") or creature_row.get("source_mode"),
                "bundle_kind": export_row.get("bundle_kind") if export_row else None,
            }
        )
        runtime_capabilities = _runtime_capabilities(
            {
                "runtime_capabilities_json": row.get("runtime_capabilities_json")
                or creature_row.get("runtime_capabilities_json")
                or (export_row.get("runtime_capabilities_json") if export_row else None)
            },
            descriptor_ready=True,
            replayable=export_row is not None,
        )
        descriptor_payload = {
            "descriptorVersion": descriptor_version,
            "terminalVersion": terminal_version,
            "normalizationPolicy": normalization_policy,
            "fingerprintResolution": fingerprint_resolution,
            "terminal": terminal_descriptor,
            "trajectory": trajectory_descriptor,
        }
        descriptor_hash = row_sha256(descriptor_payload)
        effective_replay = _effective_replay_projection(result_row)
        staged_descriptors.append(
            (
                specimen_id,
                descriptor_version,
                terminal_version,
                normalization_policy,
                fingerprint_resolution,
                json_text(terminal_descriptor),
                json_text(trajectory_descriptor),
                descriptor_hash,
                utc_now(),
            )
        )
        compact_manifest = _compact_specimen_manifest(
            row,
            creature_row=creature_row,
            export_row=export_row,
            effective_replay=effective_replay,
            runtime_family=runtime_family,
            runtime_capabilities=runtime_capabilities,
            receipt_id=receipt_id,
            artifact_id=artifact_id,
            descriptor_hash=descriptor_hash,
        )
        staged_specimens.append(
            (
                specimen_id,
                source_creature_id,
                resolved_study_id,
                row.get("run_id"),
                row.get("campaign_id"),
                row.get("source_kind") or "compendium_specimen",
                row.get("source_mode") or creature_row.get("source_mode"),
                row.get("source_algorithm") or creature_row.get("source_algorithm"),
                row.get("config_hash") or creature_row.get("config_hash"),
                row.get("initial_condition_family")
                or creature_row.get("initial_condition_family"),
                None,
                None,
                None,
                _taxonomy_family(creature_row),
                creature_row.get("score"),
                _bool_or_none(export_row.get("filters_passed")) if export_row else None,
                _bool_or_none(creature_row.get("is_stable")),
                normalize_optional_timestamp(
                    row.get("recorded_at") or creature_row.get("recorded_at")
                ),
                None,
                export_row.get("export_dir") if export_row else None,
                row.get("activity_path"),
                row.get("fingerprint_path"),
                json_text(
                    {
                        "sourceReceiptId": receipt_id,
                        "sourceArtifactId": artifact_id,
                        "sourceTable": "specimens",
                        "sourcePrimaryKey": specimen_id,
                        "sourceCreatureId": source_creature_id,
                        "effectiveReplay": effective_replay,
                    }
                ),
                runtime_family,
                json_text(runtime_capabilities),
                json_text(compact_manifest),
                descriptor_version,
                terminal_version,
                normalization_policy,
                fingerprint_resolution,
            )
        )
        terminal_axes = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal_descriptor,
            trajectory=trajectory_descriptor,
            specimen_id=specimen_id,
        )
        transformed_axes = transform_axes(terminal_axes)
        staged_axes.extend(
            [
                (
                    specimen_id,
                    axis_id,
                    "terminal",
                    float(terminal_axes[axis_id]),
                    float(transformed_axes[axis_id]),
                )
                for axis_id in terminal_axes
            ]
        )
        if len(staged_specimens) >= 2048:
            flush_staging()

    flush_staging()
    appended_specimen_count: int | None = None
    if append_native_v2_run:
        appended_specimen_count = _validate_native_v2_append_staging(
            connection,
            study_id=resolved_study_id,
            run_id=cast(str, run_id),
        )
    _merge_compendium_staging(connection, study_id=resolved_study_id)
    if append_native_v2_run:
        if appended_specimen_count is None:
            raise AssertionError("native-v2 append did not validate its staged specimen count")
        _invalidate_native_v2_feature_spaces(
            connection,
            run_id=cast(str, run_id),
            specimen_count=appended_specimen_count,
            source_receipt_id=receipt_id,
        )
        return resolved_study_id
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE incoming_compendium_specimens AS "
        "SELECT specimen_id FROM staged_compendium_specimens"
    )
    connection.execute(
        """
        CREATE OR REPLACE TEMP TABLE stale_compendium_specimens AS
        SELECT study_specimens.specimen_id
        FROM study_specimens
        WHERE study_specimens.study_id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM incoming_compendium_specimens AS incoming
              WHERE incoming.specimen_id = study_specimens.specimen_id
          )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM specimen_feature_vectors
        WHERE observation_id IN (
            SELECT observations.observation_id
            FROM observations
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE observations.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM sparse_feature_values
        WHERE observation_id IN (
            SELECT observations.observation_id
            FROM observations
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE observations.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM observations
        WHERE study_id = ?
          AND specimen_id IN (SELECT specimen_id FROM stale_compendium_specimens)
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM creature_signal_axes
        WHERE state_id IN (
            SELECT anatomical_states.state_id
            FROM anatomical_states
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE anatomical_states.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM creature_state_labels
        WHERE state_id IN (
            SELECT anatomical_states.state_id
            FROM anatomical_states
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE anatomical_states.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM anatomical_state_axes
        WHERE state_id IN (
            SELECT anatomical_states.state_id
            FROM anatomical_states
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE anatomical_states.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM anatomical_states
        WHERE study_id = ?
          AND specimen_id IN (SELECT specimen_id FROM stale_compendium_specimens)
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM context_outcomes
        WHERE context_trial_id IN (
            SELECT context_trials.context_trial_id
            FROM context_trials
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE context_trials.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM context_sample_axes
        WHERE context_trial_id IN (
            SELECT context_trials.context_trial_id
            FROM context_trials
            JOIN stale_compendium_specimens USING (specimen_id)
            WHERE context_trials.study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM context_trials
        WHERE study_id = ?
          AND specimen_id IN (SELECT specimen_id FROM stale_compendium_specimens)
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM trajectory_segments
        WHERE study_id = ?
          AND specimen_id IN (SELECT specimen_id FROM stale_compendium_specimens)
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM discovery_export_resolutions
        WHERE study_id = ?
          AND specimen_id IN (SELECT specimen_id FROM stale_compendium_specimens)
        """,
        [resolved_study_id],
    )
    connection.execute(
        """
        DELETE FROM fiber_group_members
        WHERE fiber_group_id IN (
            SELECT fiber_group_id FROM fiber_groups WHERE study_id = ?
        )
        """,
        [resolved_study_id],
    )
    connection.execute("DELETE FROM fiber_groups WHERE study_id = ?", [resolved_study_id])
    connection.execute("DELETE FROM universality_runs WHERE study_id = ?", [resolved_study_id])
    _delete_topology_children(connection, parent_study_id=resolved_study_id)
    connection.execute(
        """
        DELETE FROM study_specimens
        WHERE study_id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM incoming_compendium_specimens AS incoming
              WHERE incoming.specimen_id = study_specimens.specimen_id
          )
        """,
        [resolved_study_id],
    )
    _reconcile_primary_specimen_studies(connection)
    return resolved_study_id


def ingest_compendium(
    connection: DuckDBPyConnection,
    *,
    compendium_path: Path,
    study_id: str | None = None,
    label: str | None = None,
    run_id: str | None = None,
) -> str:
    resolved_path = compendium_path.expanduser().resolve(strict=True)
    source = _open_compendium_snapshot(resolved_path, run_id=run_id)
    try:
        with warehouse_transaction(connection):
            result = _ingest_compendium(
                connection,
                compendium_path=resolved_path,
                source=source,
                study_id=study_id,
                label=label,
                run_id=run_id,
            )
            if _source_identity(resolved_path) != source.source_identity:
                raise ValueError(f"{resolved_path}: compendium changed during warehouse ingest")
            return result
    finally:
        source.connection.close()


def append_native_v2_compendium_run(
    connection: DuckDBPyConnection,
    *,
    compendium_path: Path,
    run_id: str,
) -> str:
    if not run_id.strip():
        raise ValueError("native-v2 append requires a nonempty run_id")
    resolved_path = compendium_path.expanduser().resolve(strict=True)
    source = _open_compendium_snapshot(resolved_path, run_id=run_id)
    try:
        with warehouse_transaction(connection):
            result = _ingest_compendium(
                connection,
                compendium_path=resolved_path,
                source=source,
                run_id=run_id,
                append_native_v2_run=True,
            )
            if _source_identity(resolved_path) != source.source_identity:
                raise ValueError(f"{resolved_path}: compendium changed during warehouse append")
            return result
    finally:
        source.connection.close()
