from __future__ import annotations

import hashlib
import json
import math
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import duckdb
from duckdb import DuckDBPyConnection

from .schema import SCHEMA_VERSION, SchemaVersionError, create_schema, read_schema_version

TOOL_VERSION = "morphospace-warehouse-v10"
APPLE_REFERENCE_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
DESCRIPTOR_VERSION = "2"
TERMINAL_VERSION = "2"
NORMALIZATION_POLICY = "border_aware_com_center_peak_q32_u8_v2"
CANONICAL_COMPENDIUM_STUDY_LABEL = "compendium"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def stable_id(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:24]


def canonical_compendium_study_id() -> str:
    return stable_id(
        "study",
        "discovery",
        CANONICAL_COMPENDIUM_STUDY_LABEL,
        "",
        "",
    )


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
    if path.exists() and path.stat().st_size > 0:
        probe = duckdb.connect(str(path), read_only=True)
        try:
            version = read_schema_version(probe)
        finally:
            probe.close()
        if version != SCHEMA_VERSION:
            label = "unversioned" if version is None else f"v{version}"
            raise SchemaVersionError(
                f"warehouse schema {label} is not writable by schema v{SCHEMA_VERSION}; "
                "rebuild the warehouse side by side"
            )
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
    connection = duckdb.connect(str(path), read_only=True)
    try:
        version = read_schema_version(connection)
        if version != SCHEMA_VERSION:
            label = "unversioned" if version is None else f"v{version}"
            raise SchemaVersionError(
                f"warehouse schema {label} is not readable by schema v{SCHEMA_VERSION}; "
                "migrate the warehouse side by side"
            )
        return connection
    except BaseException:
        connection.close()
        raise


@contextmanager
def warehouse_transaction(connection: DuckDBPyConnection) -> Iterator[None]:
    connection.execute("BEGIN TRANSACTION")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


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
    hash_content: bool = True,
    content_fingerprint: str | None = None,
    size_bytes: int | None = None,
) -> str:
    stat = path.stat()
    if size_bytes is not None and size_bytes != stat.st_size:
        raise ValueError(f"artifact size changed before registration: {path}")
    resolved_size_bytes = stat.st_size if size_bytes is None else size_bytes
    resolved_fingerprint = content_fingerprint or (
        file_sha256(path) if hash_content else f"stat:{stat.st_size}:{stat.st_mtime_ns}"
    )
    artifact_id = stable_id(
        "artifact",
        study_id,
        artifact_kind,
        path.resolve(),
        resolved_fingerprint,
    )
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
            resolved_fingerprint,
            resolved_size_bytes,
            utc_now(),
            json_text(
                {
                    **(metadata_json or {}),
                    "contentHashPolicy": (
                        "precomputed"
                        if content_fingerprint is not None
                        else "sha256"
                        if hash_content
                        else "stat-fingerprint"
                    ),
                }
            ),
        ],
    )
    return artifact_id


def register_source_receipt(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    artifact_id: str,
    source_kind: str,
    source_tables: Sequence[str],
    source_row_counts: dict[str, int],
    source_schema_version: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> str:
    artifact = connection.execute(
        "SELECT sha256, size_bytes FROM artifacts WHERE artifact_id = ?",
        [artifact_id],
    ).fetchone()
    if artifact is None:
        raise ValueError(f"unknown artifact_id: {artifact_id}")
    content_sha256, size_bytes = str(artifact[0]), int(artifact[1])
    receipt_payload = {
        "studyId": study_id,
        "artifactId": artifact_id,
        "sourceKind": source_kind,
        "sourceSchemaVersion": source_schema_version,
        "sourceTables": sorted(source_tables),
        "sourceRowCounts": dict(sorted(source_row_counts.items())),
        "contentSha256": content_sha256,
        "sizeBytes": size_bytes,
    }
    receipt_hash = row_sha256(receipt_payload)
    receipt_id = stable_id("source-receipt", receipt_hash)
    connection.execute(
        """
        INSERT OR REPLACE INTO source_receipts (
            receipt_id, study_id, artifact_id, source_kind, source_schema_version,
            source_tables_json, source_row_counts_json, content_sha256, size_bytes,
            recorded_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?, ?, CAST(? AS JSON))
        """,
        [
            receipt_id,
            study_id,
            artifact_id,
            source_kind,
            source_schema_version,
            json_text(sorted(source_tables)),
            json_text(dict(sorted(source_row_counts.items()))),
            content_sha256,
            size_bytes,
            utc_now(),
            json_text({**(metadata_json or {}), "receiptHash": receipt_hash}),
        ],
    )
    return receipt_id


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
    provenance = merged.get("provenance_json")
    if isinstance(provenance, str) and provenance:
        provenance = json.loads(provenance)
    if isinstance(provenance, dict):
        descriptor_bundle = provenance.get("descriptorBundle")
        terminal = provenance.get("terminal")
        if not isinstance(terminal, dict) and isinstance(descriptor_bundle, dict):
            terminal = descriptor_bundle.get("terminal")
        if isinstance(terminal, dict):
            merged.setdefault(
                "descriptor_version",
                str(
                    terminal.get("descriptorVersion")
                    or (
                        descriptor_bundle.get("descriptorVersion")
                        if isinstance(descriptor_bundle, dict)
                        else ""
                    )
                    or terminal.get("version")
                    or ""
                )
                or None,
            )
            merged.setdefault("terminal_version", str(terminal.get("version") or "") or None)
            merged.setdefault("normalization_policy", terminal.get("normalizationPolicy"))
            merged.setdefault("fingerprint_resolution", terminal.get("fingerprintResolution"))
    merged["recorded_at"] = normalize_optional_timestamp(merged.get("recorded_at"))
    connection.execute(
        """
        INSERT OR REPLACE INTO specimens (
            specimen_id, source_creature_id, study_id, run_id, campaign_id, source_kind,
            source_mode, source_algorithm, config_hash, initial_condition_family,
            regime_family, geometry_family, canonical_family, family_kind, score,
            filters_passed, search_is_stable_candidate, recorded_at, results_path,
            export_dir, activity_path, fingerprint_path, provenance_json,
            runtime_family, runtime_capabilities_json, specimen_manifest_json,
            descriptor_version, terminal_version, normalization_policy,
            fingerprint_resolution
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            CAST(? AS JSON), ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?, ?, ?
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
            merged.get("descriptor_version"),
            merged.get("terminal_version"),
            merged.get("normalization_policy"),
            merged.get("fingerprint_resolution"),
        ],
    )


def upsert_specimen_descriptor(
    connection: DuckDBPyConnection,
    *,
    specimen_id: str,
    terminal_descriptor: dict[str, Any],
    trajectory_descriptor: dict[str, Any],
    descriptor_version: str,
    terminal_version: str,
    normalization_policy: str,
    fingerprint_resolution: int | None,
) -> str:
    payload = {
        "descriptorVersion": descriptor_version,
        "terminalVersion": terminal_version,
        "normalizationPolicy": normalization_policy,
        "fingerprintResolution": fingerprint_resolution,
        "terminal": terminal_descriptor,
        "trajectory": trajectory_descriptor,
    }
    content_sha256 = row_sha256(payload)
    connection.execute(
        """
        INSERT OR REPLACE INTO specimen_descriptors (
            specimen_id, descriptor_version, terminal_version,
            normalization_policy, fingerprint_resolution,
            terminal_descriptor_json, trajectory_descriptor_json,
            content_sha256, recorded_at
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), ?, ?)
        """,
        [
            specimen_id,
            descriptor_version,
            terminal_version,
            normalization_policy,
            fingerprint_resolution,
            json_text(terminal_descriptor),
            json_text(trajectory_descriptor),
            content_sha256,
            utc_now(),
        ],
    )
    return content_sha256


def register_feature_calibration(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    calibration_version: str,
    axis_order: Sequence[str],
    reference_query: dict[str, Any],
    axis_transforms: dict[str, Any],
    metadata_json: dict[str, Any] | None = None,
) -> str:
    payload = {
        "featureSpaceId": feature_space_id,
        "calibrationVersion": calibration_version,
        "axisOrder": list(axis_order),
        "referenceQuery": reference_query,
        "axisTransforms": axis_transforms,
    }
    content_sha256 = row_sha256(payload)
    calibration_id = stable_id("feature-calibration", content_sha256)
    connection.execute(
        """
        INSERT INTO feature_calibrations (
            calibration_id, feature_space_id, calibration_version,
            axis_order_json, reference_query_json, axis_transforms_json, content_sha256,
            created_at, frozen, metadata_json
        )
        VALUES (?, ?, ?, CAST(? AS JSON), CAST(? AS JSON), CAST(? AS JSON), ?, ?, TRUE,
                CAST(? AS JSON))
        ON CONFLICT DO NOTHING
        """,
        [
            calibration_id,
            feature_space_id,
            calibration_version,
            json_text(list(axis_order)),
            json_text(reference_query),
            json_text(axis_transforms),
            content_sha256,
            utc_now(),
            json_text(metadata_json or {}),
        ],
    )
    return calibration_id


def upsert_specimen_feature_vectors(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    calibration_id: str,
    vector_version: str,
    axis_count: int,
    rows: Sequence[tuple[str, str, str, Sequence[float], Sequence[float]]],
) -> int:
    if not rows:
        return 0
    contract_row = connection.execute(
        """
        SELECT spaces.storage_mode,
               json_extract_string(spaces.metadata_json, '$.activeCalibrationId'),
               calibrations.frozen,
               calibrations.axis_order_json,
               (SELECT list(axis_id ORDER BY axis_index)
                FROM feature_axes
                WHERE feature_space_id = spaces.feature_space_id)
        FROM feature_spaces AS spaces
        LEFT JOIN feature_calibrations AS calibrations
          ON calibrations.feature_space_id = spaces.feature_space_id
         AND calibrations.calibration_id = ?
        WHERE spaces.feature_space_id = ?
        """,
        [calibration_id, feature_space_id],
    ).fetchone()
    if contract_row is None:
        raise ValueError(f"unknown feature_space_id: {feature_space_id}")
    calibration_axes = (
        json.loads(contract_row[3])
        if isinstance(contract_row[3], str)
        else contract_row[3]
    )
    if (
        str(contract_row[0]) != "dense_vectors"
        or str(contract_row[1]) != calibration_id
        or not bool(contract_row[2])
        or calibration_axes != contract_row[4]
        or len(calibration_axes or []) != axis_count
    ):
        raise ValueError(f"{feature_space_id}: dense-vector calibration contract is invalid")
    keys = [(row[0], feature_space_id, calibration_id) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("feature-vector batch contains duplicate observation keys")
    for observation_id, _, _, raw_vector, normalized_vector in rows:
        if len(raw_vector) != axis_count or len(normalized_vector) != axis_count:
            raise ValueError(
                f"{observation_id}: expected {axis_count} coordinates in each vector"
            )
        if not all(math.isfinite(float(value)) for value in (*raw_vector, *normalized_vector)):
            raise ValueError(f"{observation_id}: feature vectors must be finite")
    connection.execute(
        """
        INSERT OR REPLACE INTO specimen_feature_vectors (
            observation_id, specimen_id, study_id, feature_space_id, calibration_id,
            vector_version, axis_count, raw_vector, normalized_vector,
            content_sha256, created_at
        )
        SELECT observation_id, specimen_id, study_id, ?, ?, ?, ?, raw_vector,
               normalized_vector,
               sha256(to_json(struct_pack(
                   observationId := observation_id,
                   specimenId := specimen_id,
                   featureSpaceId := ?,
                   calibrationId := ?,
                   vectorVersion := ?,
                   rawVector := raw_vector,
                   normalizedVector := normalized_vector
               ))),
               current_timestamp
        FROM (
            SELECT unnest(?::VARCHAR[]) AS observation_id,
                   unnest(?::VARCHAR[]) AS specimen_id,
                   unnest(?::VARCHAR[]) AS study_id,
                   unnest(?::DOUBLE[][]) AS raw_vector,
                   unnest(?::DOUBLE[][]) AS normalized_vector
        )
        """,
        [
            feature_space_id,
            calibration_id,
            vector_version,
            axis_count,
            feature_space_id,
            calibration_id,
            vector_version,
            [row[0] for row in rows],
            [row[1] for row in rows],
            [row[2] for row in rows],
            [[float(value) for value in row[3]] for row in rows],
            [[float(value) for value in row[4]] for row in rows],
        ],
    )
    return len(rows)


def validate_dense_feature_space(
    connection: DuckDBPyConnection,
    *,
    feature_space_id: str,
    calibration_id: str,
    observation_kind: str,
    axis_count: int,
) -> int:
    axis_row = connection.execute(
        """
        SELECT count(*), count(DISTINCT axis_index), min(axis_index), max(axis_index)
        FROM feature_axes
        WHERE feature_space_id = ?
        """,
        [feature_space_id],
    ).fetchone()
    if axis_row is None or tuple(axis_row) != (axis_count, axis_count, 0, axis_count - 1):
        raise ValueError(f"{feature_space_id}: feature axes are not contiguous")
    sparse_row = connection.execute(
        "SELECT count(*) FROM sparse_feature_values WHERE feature_space_id = ?",
        [feature_space_id],
    ).fetchone()
    if sparse_row is None or int(sparse_row[0]):
        raise ValueError(f"{feature_space_id}: dense space contains physical scalar values")
    coverage_row = connection.execute(
        """
        WITH expected AS (
            SELECT observation_id, specimen_id, study_id
            FROM observations
            WHERE observation_kind = ?
        ), vectors AS (
            SELECT *
            FROM specimen_feature_vectors
            WHERE feature_space_id = ? AND calibration_id = ?
        )
        SELECT count(expected.observation_id), count(vectors.observation_id),
               count(*) FILTER (
                   WHERE expected.observation_id IS NULL
                      OR vectors.observation_id IS NULL
                      OR expected.specimen_id IS DISTINCT FROM vectors.specimen_id
                      OR expected.study_id IS DISTINCT FROM vectors.study_id
                      OR vectors.axis_count != ?
                      OR len(vectors.raw_vector) != ?
                      OR len(vectors.normalized_vector) != ?
                      OR len(list_filter(
                          vectors.raw_vector,
                          value -> value IS NULL OR NOT isfinite(value)
                      )) != 0
                      OR len(list_filter(
                          vectors.normalized_vector,
                          value -> value IS NULL OR NOT isfinite(value)
                      )) != 0
               )
        FROM expected
        FULL OUTER JOIN vectors USING (observation_id)
        """,
        [
            observation_kind,
            feature_space_id,
            calibration_id,
            axis_count,
            axis_count,
            axis_count,
        ],
    ).fetchone()
    if coverage_row is None:
        raise ValueError(f"{feature_space_id}: dense-vector coverage query returned no row")
    expected_count, vector_count, invalid_count = map(int, coverage_row)
    if expected_count == 0 or expected_count != vector_count or invalid_count:
        raise ValueError(
            f"{feature_space_id}: dense-vector coverage is incomplete "
            f"(observations={expected_count}, vectors={vector_count}, invalid={invalid_count})"
        )
    return vector_count


def mark_derived_artifact_state(
    connection: DuckDBPyConnection,
    *,
    artifact_kind: str,
    status: str,
    reason: str | None,
    feature_space_id: str | None = None,
    descriptor_version: str | None = None,
    normalization_policy: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> str:
    if status not in {"valid", "invalid", "building"}:
        raise ValueError(f"unsupported derived artifact status: {status}")
    payload = {
        "artifactKind": artifact_kind,
        "featureSpaceId": feature_space_id,
        "descriptorVersion": descriptor_version,
        "normalizationPolicy": normalization_policy,
        "status": status,
        "reason": reason,
        "metadata": metadata_json or {},
    }
    generation_hash = row_sha256(payload)
    artifact_key = stable_id(
        "derived-artifact",
        artifact_kind,
        feature_space_id or "",
        descriptor_version or "",
        normalization_policy or "",
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO derived_artifact_state (
            artifact_key, artifact_kind, feature_space_id, descriptor_version,
            normalization_policy, status, reason, generation_hash, updated_at,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            artifact_key,
            artifact_kind,
            feature_space_id,
            descriptor_version,
            normalization_policy,
            status,
            reason,
            generation_hash,
            utc_now(),
            json_text(metadata_json or {}),
        ],
    )
    return artifact_key


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
    storage_mode: str,
    label: str,
    version_label: str,
    coordinate_policy: str,
    metric_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    if storage_mode not in {"sparse_values", "dense_vectors"}:
        raise ValueError(f"unsupported feature-space storage mode: {storage_mode}")
    connection.execute(
        """
        INSERT OR REPLACE INTO feature_spaces (
            feature_space_id, feature_space_kind, storage_mode, label, version_label,
            coordinate_policy, metric_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSON), CAST(? AS JSON))
        """,
        [
            feature_space_id,
            feature_space_kind,
            storage_mode,
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


def replace_sparse_feature_values(
    connection: DuckDBPyConnection,
    *,
    observation_id: str,
    feature_space_id: str,
    value_rows: list[dict[str, Any]],
) -> None:
    storage_row = connection.execute(
        "SELECT storage_mode FROM feature_spaces WHERE feature_space_id = ?",
        [feature_space_id],
    ).fetchone()
    if storage_row is None:
        raise ValueError(f"unknown feature_space_id: {feature_space_id}")
    if str(storage_row[0]) != "sparse_values":
        raise ValueError(
            f"{feature_space_id}: physical scalar values require sparse_values storage"
        )
    _replace_rows(
        connection,
        """
        DELETE FROM sparse_feature_values
        WHERE observation_id = ? AND feature_space_id = ?
        """,
        [observation_id, feature_space_id],
        """
        INSERT INTO sparse_feature_values (
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


def replace_perturbation_axes(
    connection: DuckDBPyConnection,
    *,
    trial_id: str,
    axis_rows: list[tuple[str, float | None, float | None]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM perturbation_axes WHERE trial_id = ?",
        [trial_id],
        """
        INSERT INTO perturbation_axes (
            trial_id, axis_id, raw_value, transformed_value
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            [trial_id, axis_id, raw_value, transformed_value]
            for axis_id, raw_value, transformed_value in axis_rows
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


def replace_creature_signal_axes(
    connection: DuckDBPyConnection,
    *,
    state_id: str,
    axis_rows: list[tuple[str, float | None, float | None]],
) -> None:
    _replace_rows(
        connection,
        "DELETE FROM creature_signal_axes WHERE state_id = ?",
        [state_id],
        """
        INSERT INTO creature_signal_axes (
            state_id, axis_id, raw_value, transformed_value
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            [state_id, axis_id, raw_value, transformed_value]
            for axis_id, raw_value, transformed_value in axis_rows
        ],
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
    _replace_rows(
        connection,
        "DELETE FROM context_sample_axes WHERE context_trial_id = ?",
        [context_trial_id],
        """
        INSERT INTO context_sample_axes (
            context_trial_id, step, axis_id, raw_value
        )
        VALUES (?, ?, ?, ?)
        """,
        [
            [context_trial_id, step, axis_id, raw_value]
            for step, axis_id, raw_value in axis_rows
        ],
    )


def replace_context_outcomes(
    connection: DuckDBPyConnection,
    *,
    context_trial_id: str,
    rows: list[tuple[str, float | None, dict[str, Any] | None]],
) -> None:
    deduplicated: dict[str, tuple[float | None, dict[str, Any] | None]] = {}
    for outcome_kind, outcome_value, metadata_json in rows:
        deduplicated[str(outcome_kind)] = (outcome_value, metadata_json)
    _replace_rows(
        connection,
        "DELETE FROM context_outcomes WHERE context_trial_id = ?",
        [context_trial_id],
        """
        INSERT INTO context_outcomes (
            context_trial_id, outcome_kind, outcome_value, metadata_json
        )
        VALUES (?, ?, ?, CAST(? AS JSON))
        """,
        [
            [
                context_trial_id,
                outcome_kind,
                outcome_value,
                json_text(metadata_json or {}),
            ]
            for outcome_kind, (outcome_value, metadata_json) in deduplicated.items()
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
