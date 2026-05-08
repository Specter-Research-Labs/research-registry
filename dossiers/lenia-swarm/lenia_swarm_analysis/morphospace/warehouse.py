from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import duckdb
from duckdb import DuckDBPyConnection

from .schema import create_schema

TOOL_VERSION = "morphospace-warehouse-v1"
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
) -> str:
    artifact_id = stable_id("artifact", artifact_kind, path.resolve(), file_sha256(path))
    stat = path.stat()
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
            file_sha256(path),
            stat.st_size,
            utc_now(),
            json_text(metadata_json or {}),
        ],
    )
    return artifact_id


def register_ingest_run(
    connection: DuckDBPyConnection,
    *,
    notes: str | None = None,
    ingest_id: str | None = None,
) -> str:
    resolved_ingest_id = ingest_id or stable_id("ingest", utc_now().isoformat(), notes or "")
    connection.execute(
        """
        INSERT OR REPLACE INTO ingest_runs (
            ingest_id, started_at, completed_at, status, tool_version, notes
        )
        VALUES (?, ?, NULL, 'running', ?, ?)
        """,
        [resolved_ingest_id, utc_now(), TOOL_VERSION, notes],
    )
    return resolved_ingest_id


def complete_ingest_run(
    connection: DuckDBPyConnection,
    *,
    ingest_id: str,
    status: str = "completed",
) -> None:
    connection.execute(
        """
        UPDATE ingest_runs
        SET completed_at = ?, status = ?
        WHERE ingest_id = ?
        """,
        [utc_now(), status, ingest_id],
    )


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
    connection.execute(
        "DELETE FROM feature_axes WHERE feature_space_id = ?",
        [feature_space_id],
    )
    for row in axis_rows:
        connection.execute(
            """
            INSERT INTO feature_axes (
                feature_space_id, axis_id, axis_index, axis_family, label, units, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                feature_space_id,
                row["axis_id"],
                int(row["axis_index"]),
                row["axis_family"],
                row.get("label"),
                row.get("units"),
                json_text(row.get("metadata_json") or {}),
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
    connection.execute(
        """
        DELETE FROM feature_values
        WHERE observation_id = ? AND feature_space_id = ?
        """,
        [observation_id, feature_space_id],
    )
    for row in value_rows:
        connection.execute(
            """
            INSERT INTO feature_values (
                observation_id, feature_space_id, axis_id, raw_value,
                normalized_value, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                observation_id,
                feature_space_id,
                row["axis_id"],
                row.get("raw_value"),
                row.get("normalized_value"),
                json_text(row.get("metadata_json") or {}),
            ],
        )


def replace_specimen_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    axis_rows: list[tuple[str, str, float | None, float | None]],
) -> None:
    connection.execute("DELETE FROM specimen_axes WHERE specimen_id = ?", [specimen_id])
    for axis_id, axis_family, raw_value, transformed_value in axis_rows:
        connection.execute(
            """
            INSERT INTO specimen_axes (
                specimen_id, axis_id, axis_family, raw_value, transformed_value
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [specimen_id, axis_id, axis_family, raw_value, transformed_value],
        )


def replace_development_sample_axes(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    axis_rows: list[tuple[int, str, float | None]],
) -> None:
    connection.execute(
        "DELETE FROM development_sample_axes WHERE specimen_id = ?",
        [specimen_id],
    )
    for step, axis_id, raw_value in axis_rows:
        connection.execute(
            """
            INSERT INTO development_sample_axes (
                specimen_id, step, axis_id, raw_value
            )
            VALUES (?, ?, ?, ?)
            """,
            [specimen_id, step, axis_id, raw_value],
        )


def replace_perturbation_axes(
    connection: DuckDBPyConnection,
    *,
    trial_id: str,
    axis_rows: list[tuple[str, float | None, float | None]],
) -> None:
    connection.execute("DELETE FROM perturbation_axes WHERE trial_id = ?", [trial_id])
    for axis_id, raw_value, transformed_value in axis_rows:
        connection.execute(
            """
            INSERT INTO perturbation_axes (
                trial_id, axis_id, raw_value, transformed_value
            )
            VALUES (?, ?, ?, ?)
            """,
            [trial_id, axis_id, raw_value, transformed_value],
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


def register_control_program(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    label: str,
    sequence_index: int,
    family: str | None,
    payload: dict[str, Any] | None,
    metadata_json: dict[str, Any] | None = None,
    control_program_id: str | None = None,
) -> str:
    resolved_control_program_id = control_program_id or stable_id(
        "control-program",
        study_id,
        label,
        sequence_index,
        family or "",
        json_text(payload or {}),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO control_programs (
            control_program_id, study_id, label, sequence_index, family, payload_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON))
        """,
        [
            resolved_control_program_id,
            study_id,
            label,
            sequence_index,
            family,
            json_text(payload or {}),
            json_text(metadata_json or {}),
        ],
    )
    return resolved_control_program_id


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
    connection.execute("DELETE FROM anatomical_state_axes WHERE state_id = ?", [state_id])
    for axis_id, raw_value, transformed_value in axis_rows:
        connection.execute(
            """
            INSERT INTO anatomical_state_axes (
                state_id, axis_id, raw_value, transformed_value
            )
            VALUES (?, ?, ?, ?)
            """,
            [state_id, axis_id, raw_value, transformed_value],
        )


def replace_creature_signal_axes(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
    axis_rows: list[tuple[str, float | None, float | None]],
) -> None:
    connection.execute("DELETE FROM creature_signal_axes WHERE state_id = ?", [state_id])
    for axis_id, raw_value, transformed_value in axis_rows:
        connection.execute(
            """
            INSERT INTO creature_signal_axes (
                state_id, axis_id, raw_value, transformed_value
            )
            VALUES (?, ?, ?, ?)
            """,
            [state_id, axis_id, raw_value, transformed_value],
        )


def upsert_creature_state_labels(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
    coherence_class: str | None,
    organization_class: str | None,
    mobility_class: str | None,
    creature_bucket: str | None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO creature_state_labels (
            state_id, coherence_class, organization_class, mobility_class,
            creature_bucket, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            state_id,
            coherence_class,
            organization_class,
            mobility_class,
            creature_bucket,
            json_text(metadata_json or {}),
        ],
    )


def upsert_discovery_export_resolution(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    study_id: str,
    original_export_dir: str | None,
    resolved_export_dir: str | None,
    replayable: bool,
    resolution_source: str,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO discovery_export_resolutions (
            specimen_id, study_id, original_export_dir, resolved_export_dir,
            replayable, resolution_source, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            specimen_id,
            study_id,
            original_export_dir,
            resolved_export_dir,
            replayable,
            resolution_source,
            json_text(metadata_json or {}),
        ],
    )


def replace_context_trials(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    specimen_id: str | None = None,
    rows: list[dict[str, Any]],
) -> None:
    if specimen_id is None:
        connection.execute("DELETE FROM context_trials WHERE study_id = ?", [study_id])
    else:
        connection.execute(
            "DELETE FROM context_trials WHERE study_id = ? AND specimen_id = ?",
            [study_id, specimen_id],
        )
    for row in rows:
        connection.execute(
            """
            INSERT INTO context_trials (
                context_trial_id, specimen_id, study_id, context_id, control_program_id,
                environment, perturbation, repeat_index, results_path, summary_path, provenance_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                row["context_trial_id"],
                row["specimen_id"],
                row["study_id"],
                row["context_id"],
                row.get("control_program_id"),
                row.get("environment"),
                row.get("perturbation"),
                row.get("repeat_index", 0),
                row.get("results_path"),
                row.get("summary_path"),
                json_text(row.get("provenance_json") or {}),
            ],
        )


def replace_context_sample_axes(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
    axis_rows: list[tuple[int, str, float | None]],
) -> None:
    connection.execute(
        "DELETE FROM context_sample_axes WHERE context_trial_id = ?",
        [context_trial_id],
    )
    for step, axis_id, raw_value in axis_rows:
        connection.execute(
            """
            INSERT INTO context_sample_axes (
                context_trial_id, step, axis_id, raw_value
            )
            VALUES (?, ?, ?, ?)
            """,
            [context_trial_id, step, axis_id, raw_value],
        )


def replace_context_outcomes(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
    rows: list[tuple[str, float | None, dict[str, Any] | None]],
) -> None:
    connection.execute(
        "DELETE FROM context_outcomes WHERE context_trial_id = ?",
        [context_trial_id],
    )
    deduplicated: dict[str, tuple[float | None, dict[str, Any] | None]] = {}
    for outcome_kind, outcome_value, metadata_json in rows:
        deduplicated[str(outcome_kind)] = (outcome_value, metadata_json)
    for outcome_kind, (outcome_value, metadata_json) in deduplicated.items():
        connection.execute(
            """
            INSERT INTO context_outcomes (
                context_trial_id, outcome_kind, outcome_value, metadata_json
            )
            VALUES (?, ?, ?, CAST(? AS JSON))
            """,
            [
                context_trial_id,
                outcome_kind,
                outcome_value,
                json_text(metadata_json or {}),
            ],
        )


def replace_trajectory_segments(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    specimen_id: str | None = None,
    context_trial_id: str | None = None,
    rows: list[dict[str, Any]],
) -> None:
    if context_trial_id is not None:
        connection.execute(
            "DELETE FROM trajectory_segments WHERE study_id = ? AND context_trial_id = ?",
            [study_id, context_trial_id],
        )
    elif specimen_id is not None:
        connection.execute(
            """
            DELETE FROM trajectory_segments
            WHERE study_id = ? AND specimen_id = ? AND context_trial_id IS NULL
            """,
            [study_id, specimen_id],
        )
    else:
        connection.execute("DELETE FROM trajectory_segments WHERE study_id = ?", [study_id])
    for row in rows:
        connection.execute(
            """
            INSERT INTO trajectory_segments (
                segment_id, study_id, specimen_id, context_trial_id, context_id,
                segment_kind, start_step, end_step, segment_index, summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                row["segment_id"],
                row["study_id"],
                row.get("specimen_id"),
                row.get("context_trial_id"),
                row.get("context_id"),
                row["segment_kind"],
                row.get("start_step"),
                row.get("end_step"),
                row.get("segment_index", 0),
                json_text(row.get("summary_json") or {}),
            ],
        )


def replace_fiber_groups(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    groups: list[dict[str, Any]],
) -> None:
    connection.execute(
        """
        DELETE FROM fiber_group_members
        WHERE fiber_group_id IN (
            SELECT fiber_group_id FROM fiber_groups WHERE study_id = ?
        )
        """,
        [study_id],
    )
    connection.execute("DELETE FROM fiber_groups WHERE study_id = ?", [study_id])
    for group in groups:
        fiber_group_id = str(group["fiber_group_id"])
        connection.execute(
            """
            INSERT INTO fiber_groups (
                fiber_group_id, study_id, grouping_kind, state_class_key, member_count,
                volume_proxy, diversity_proxy, connectivity_proxy, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                fiber_group_id,
                study_id,
                group["grouping_kind"],
                group["state_class_key"],
                group["member_count"],
                group.get("volume_proxy"),
                group.get("diversity_proxy"),
                group.get("connectivity_proxy"),
                json_text(group.get("metadata_json") or {}),
            ],
        )
        for member in group.get("members", []):
            connection.execute(
                """
                INSERT INTO fiber_group_members (
                    fiber_group_id, state_id, specimen_id
                )
                VALUES (?, ?, ?)
                """,
                [fiber_group_id, member["state_id"], member.get("specimen_id")],
            )


def replace_universality_runs(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    runs: list[dict[str, Any]],
) -> None:
    connection.execute("DELETE FROM universality_runs WHERE study_id = ?", [study_id])
    for row in runs:
        connection.execute(
            """
            INSERT INTO universality_runs (
                universality_run_id, study_id, comparison_scope, coarse_kind,
                created_at, summary_json
            )
            VALUES (?, ?, ?, ?, ?, CAST(? AS JSON))
            """,
            [
                row["universality_run_id"],
                study_id,
                row["comparison_scope"],
                row["coarse_kind"],
                normalize_optional_timestamp(row.get("created_at")) or utc_now(),
                json_text(row.get("summary_json") or {}),
            ],
        )
