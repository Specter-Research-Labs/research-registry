from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import duckdb
from duckdb import DuckDBPyConnection

from lenia_swarm_analysis._io import sha256_file

from .schema import create_schema

APPLE_REFERENCE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def stable_id(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:24]


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _replace_rows(
    connection: DuckDBPyConnection,
    delete_sql: str,
    delete_params: Sequence[Any],
    insert_sql: str,
    rows: Sequence[Sequence[Any]],
) -> None:
    connection.execute(delete_sql, list(delete_params))
    if rows:
        connection.executemany(insert_sql, rows)


def normalize_optional_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        return (APPLE_REFERENCE_EPOCH + timedelta(seconds=float(value))).replace(
            tzinfo=None
        )
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("Z"):
            stripped = f"{stripped[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(stripped)
            return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            try:
                return normalize_optional_timestamp(float(stripped))
            except ValueError as exc:
                raise ValueError(f"unsupported timestamp format: {value!r}") from exc
    raise TypeError(f"unsupported timestamp type: {type(value).__name__}")


def connect_database(path: Path) -> DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    # Full-study refreshes write multi-gigabyte derived tables; the default 16 MiB
    # autocheckpoint churns the WAL and dominates wall-clock time on real archives.
    connection.execute("SET wal_autocheckpoint='1.0 GiB'")
    connection.execute("SET checkpoint_threshold='1.0 GiB'")
    create_schema(connection)
    return connection


def connect_read_only_database(path: Path) -> DuckDBPyConnection:
    if not path.exists():
        raise FileNotFoundError(path)
    return duckdb.connect(str(path), read_only=True)


def row_sha256(payload: Any) -> str:
    return hashlib.sha256(json_text(payload).encode("utf-8")).hexdigest()


def register_study(
    connection: DuckDBPyConnection,
    *,
    study_kind: str,
    label: str,
    run_id: str | None = None,
    campaign_id: str | None = None,
    parent_study_id: str | None = None,
    config_hash: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    study_id: str | None = None,
) -> str:
    resolved_study_id = study_id or stable_id(
        "study", study_kind, label, run_id or "", campaign_id or ""
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO studies (
            study_id, study_kind, run_id, campaign_id, parent_study_id, label,
            config_hash, created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            resolved_study_id,
            study_kind,
            run_id,
            campaign_id,
            parent_study_id,
            label,
            config_hash,
            utc_now(),
            json_text(metadata_json or {}),
        ],
    )
    return resolved_study_id


def register_artifact(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    artifact_kind: str,
    path: Path,
    metadata_json: dict[str, Any] | None = None,
    hash_content: bool = True,
) -> str:
    stat = path.stat()
    content_fingerprint = (
        sha256_file(path)
        if hash_content
        else f"stat:{stat.st_size}:{stat.st_mtime_ns}"
    )
    artifact_id = stable_id("artifact", artifact_kind, path.resolve(), content_fingerprint)
    connection.execute(
        """
        INSERT OR REPLACE INTO artifacts (
            artifact_id, study_id, artifact_kind, path, sha256, size_bytes,
            created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            artifact_id,
            study_id,
            artifact_kind,
            str(path),
            content_fingerprint,
            stat.st_size,
            utc_now(),
            json_text(
                {
                    **(metadata_json or {}),
                    "contentHashPolicy": "sha256" if hash_content else "stat-fingerprint",
                }
            ),
        ],
    )
    return artifact_id


def ingest_json_object_artifact(
    connection: DuckDBPyConnection,
    *,
    artifact_id: str,
    object_kind: str,
    payload: dict[str, Any],
    object_key: str = "root",
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO raw_json_objects (
            artifact_id, object_kind, object_key, payload_json
        )
        VALUES (?, ?, ?, CAST(? AS JSON))
        """,
        [artifact_id, object_kind, object_key, json_text(payload)],
    )


def ingest_jsonl_rows(
    connection: DuckDBPyConnection,
    *,
    artifact_id: str,
    rows: Iterable[dict[str, Any]],
) -> None:
    for index, row in enumerate(rows):
        connection.execute(
            """
            INSERT OR REPLACE INTO raw_jsonl_rows (
                artifact_id, row_index, row_hash, payload_json
            )
            VALUES (?, ?, ?, CAST(? AS JSON))
            """,
            [artifact_id, index, row_sha256(row), json_text(row)],
        )


def ingest_sqlite_rows(
    connection: DuckDBPyConnection,
    *,
    artifact_id: str,
    sqlite_path: Path,
) -> list[str]:
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        tables = [
            str(row["name"])
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        for table_name in tables:
            columns = list(source.execute(f"PRAGMA table_info({table_name})"))
            pk_columns = [str(column["name"]) for column in columns if int(column["pk"]) > 0]
            for row_index, row in enumerate(source.execute(f"SELECT * FROM {table_name}")):
                payload = dict(row)
                if pk_columns:
                    primary_key = "|".join(str(payload.get(column, "")) for column in pk_columns)
                else:
                    primary_key = str(row_index)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO raw_sqlite_rows (
                        artifact_id, table_name, primary_key, row_hash, payload_json
                    )
                    VALUES (?, ?, ?, ?, CAST(? AS JSON))
                    """,
                    [
                        artifact_id,
                        table_name,
                        primary_key,
                        row_sha256(payload),
                        json_text(payload),
                    ],
                )
        return tables
    finally:
        source.close()


def _fetch_existing_specimen(
    connection: DuckDBPyConnection,
    specimen_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM specimens WHERE specimen_id = ?",
        [specimen_id],
    ).fetchone()
    if row is None:
        return None
    column_names = [column[0] for column in connection.description]
    return dict(zip(column_names, row, strict=True))


def _merge_json_like(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = dict(existing)
        for key, value in incoming.items():
            if key in merged:
                merged[key] = _merge_json_like(merged[key], value)
            else:
                merged[key] = value
        return merged
    return incoming


def upsert_specimen(
    connection: DuckDBPyConnection,
    row: dict[str, Any],
) -> None:
    specimen_id = str(row["specimen_id"])
    existing = _fetch_existing_specimen(connection, specimen_id)
    merged = dict(existing or {})
    for key, value in row.items():
        if key in {"provenance_json", "specimen_manifest_json"} and isinstance(value, dict):
            existing_value = merged.get(key)
            if isinstance(existing_value, str) and existing_value:
                existing_value = json.loads(existing_value)
            merged[key] = _merge_json_like(existing_value, value)
            continue
        if value is not None:
            merged[key] = value
        elif key not in merged:
            merged[key] = None
    if existing is not None and existing.get("study_id") is not None:
        merged["study_id"] = existing["study_id"]
    merged["recorded_at"] = normalize_optional_timestamp(merged.get("recorded_at"))
    connection.execute(
        """
        INSERT OR REPLACE INTO specimens (
            specimen_id, source_creature_id, study_id, run_id, campaign_id, source_kind,
            source_mode, source_algorithm, config_hash, initial_condition_family,
            regime_family, geometry_family, canonical_family, family_kind, score,
            filters_passed, search_is_stable_candidate, recorded_at, results_path,
            export_dir, activity_path, fingerprint_path, provenance_json,
            runtime_family, runtime_capabilities_json, specimen_manifest_json
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            CAST(? AS JSON), ?, CAST(? AS JSON), CAST(? AS JSON)
        )
        """,
        [
            specimen_id,
            merged.get("source_creature_id"),
            merged["study_id"],
            merged.get("run_id"),
            merged.get("campaign_id"),
            merged["source_kind"],
            merged.get("source_mode"),
            merged.get("source_algorithm"),
            merged.get("config_hash"),
            merged.get("initial_condition_family"),
            merged.get("regime_family"),
            merged.get("geometry_family"),
            merged.get("canonical_family"),
            merged.get("family_kind"),
            merged.get("score"),
            merged.get("filters_passed"),
            merged.get("search_is_stable_candidate"),
            merged.get("recorded_at"),
            merged.get("results_path"),
            merged.get("export_dir"),
            merged.get("activity_path"),
            merged.get("fingerprint_path"),
            json_text(merged.get("provenance_json") or {}),
            merged.get("runtime_family"),
            json_text(merged.get("runtime_capabilities_json") or []),
            json_text(merged.get("specimen_manifest_json") or {}),
        ],
    )


def register_specimen_study(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    specimen_id: str,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO study_specimens (study_id, specimen_id)
        VALUES (?, ?)
        """,
        [study_id, specimen_id],
    )


def upsert_morphospace_source(
    connection: DuckDBPyConnection,
    *,
    source_id: str,
    source_kind: str,
    label: str,
    version_label: str | None = None,
    doi: str | None = None,
    url: str | None = None,
    license: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO morphospace_sources (
            source_id, source_kind, label, version_label, doi, url, license, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            source_id,
            source_kind,
            label,
            version_label,
            doi,
            url,
            license,
            json_text(metadata_json or {}),
        ],
    )


def upsert_feature_space(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    feature_space_kind: str,
    label: str,
    version_label: str,
    coordinate_policy: str,
    metric_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO feature_spaces (
            feature_space_id, feature_space_kind, label, version_label,
            coordinate_policy, metric_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON))
        """,
        [
            feature_space_id,
            feature_space_kind,
            label,
            version_label,
            coordinate_policy,
            json_text(metric_json or {}),
            json_text(metadata_json or {}),
        ],
    )


def replace_feature_axes(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    axis_rows: list[dict[str, Any]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM feature_axes WHERE feature_space_id = ?",
        [feature_space_id],
        """
        INSERT INTO feature_axes (
            feature_space_id, axis_id, axis_index, axis_family, label, units, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            [
                feature_space_id,
                row["axis_id"],
                int(row["axis_index"]),
                row["axis_family"],
                row.get("label"),
                row.get("units"),
                json_text(row.get("metadata_json") or {}),
            ]
            for row in axis_rows
        ],
    )


def upsert_observation(
    connection: DuckDBPyConnection,
    *,
    observation_id: str,
    specimen_id: str | None,
    study_id: str,
    source_id: str,
    observation_kind: str,
    context_id: str | None = None,
    observed_at: Any = None,
    step: int | None = None,
    source_ref: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO observations (
            observation_id, specimen_id, study_id, source_id, context_id,
            observation_kind, observed_at, step, source_ref, payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            observation_id,
            specimen_id,
            study_id,
            source_id,
            context_id,
            observation_kind,
            normalize_optional_timestamp(observed_at),
            step,
            source_ref,
            json_text(payload_json or {}),
        ],
    )


def replace_feature_values(
    connection: DuckDBPyConnection,
    *,
    observation_id: str,
    feature_space_id: str,
    value_rows: list[dict[str, Any]],
) -> None:
    _replace_rows(
        connection,
        """
        DELETE FROM feature_values
        WHERE observation_id = ? AND feature_space_id = ?
        """,
        [observation_id, feature_space_id],
        """
        INSERT INTO feature_values (
            observation_id, feature_space_id, axis_id, raw_value,
            normalized_value, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            [
                observation_id,
                feature_space_id,
                row["axis_id"],
                row.get("raw_value"),
                row.get("normalized_value"),
                json_text(row.get("metadata_json") or {}),
            ]
            for row in value_rows
        ],
    )


def replace_specimen_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    axis_rows: list[tuple[str, str, float | None, float | None]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM specimen_axes WHERE specimen_id = ?",
        [specimen_id],
        """
        INSERT INTO specimen_axes (
            specimen_id, axis_id, axis_family, raw_value, transformed_value
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            [specimen_id, axis_id, axis_family, raw_value, transformed_value]
            for axis_id, axis_family, raw_value, transformed_value in axis_rows
        ],
    )


def replace_development_sample_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    axis_rows: list[tuple[int, str, float | None]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM development_sample_axes WHERE specimen_id = ?",
        [specimen_id],
        """
        INSERT INTO development_sample_axes (
            specimen_id, step, axis_id, raw_value
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            [specimen_id, step, axis_id, raw_value]
            for step, axis_id, raw_value in axis_rows
        ],
    )


def register_context(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    context_kind: str,
    label: str,
    metadata_json: dict[str, Any] | None = None,
    context_id: str | None = None,
) -> str:
    resolved_context_id = context_id or stable_id(
        "context", study_id, context_kind, label, json_text(metadata_json or {})
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO contexts (
            context_id, study_id, context_kind, label, metadata_json
        )
        VALUES (?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            resolved_context_id,
            study_id,
            context_kind,
            label,
            json_text(metadata_json or {}),
        ],
    )
    return resolved_context_id


def upsert_anatomical_state(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
    specimen_id: str | None,
    study_id: str,
    context_id: str | None,
    source_kind: str,
    source_ref: str | None,
    recorded_at: Any,
    state_json: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO anatomical_states (
            state_id, specimen_id, study_id, context_id, source_kind, source_ref,
            recorded_at, state_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            state_id,
            specimen_id,
            study_id,
            context_id,
            source_kind,
            source_ref,
            normalize_optional_timestamp(recorded_at),
            json_text(state_json),
        ],
    )


def replace_anatomical_state_axes(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
    axis_rows: list[tuple[str, float | None, float | None]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM anatomical_state_axes WHERE state_id = ?",
        [state_id],
        """
        INSERT INTO anatomical_state_axes (
            state_id, axis_id, raw_value, transformed_value
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            [state_id, axis_id, raw_value, transformed_value]
            for axis_id, raw_value, transformed_value in axis_rows
        ],
    )
