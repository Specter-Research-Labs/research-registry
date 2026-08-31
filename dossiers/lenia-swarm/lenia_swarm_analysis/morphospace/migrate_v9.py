from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from duckdb import DuckDBPyConnection

from .schema import SCHEMA_VERSION, create_schema, read_schema_version
from .warehouse import (
    CANONICAL_COMPENDIUM_STUDY_LABEL,
    DESCRIPTOR_VERSION,
    NORMALIZATION_POLICY,
    TERMINAL_VERSION,
    canonical_compendium_study_id,
    json_text,
    register_source_receipt,
    register_study,
    row_sha256,
    stable_id,
    utc_now,
)

SOURCE_SCHEMA_VERSION = 8
LEGACY_NORMALIZATION_POLICY = "legacy_v8_unspecified"
INELIGIBLE_NORMALIZATION_POLICY = "legacy_v8_ineligible"
MIGRATION_MEMORY_LIMIT = "4 GiB"
MIGRATION_CHECKPOINT_THRESHOLD = "1 GiB"
MIGRATION_THREADS = 1
SPECIMEN_PROJECTION_BATCH_SIZE = 256
SPECIMEN_PROJECTION_BATCH_SOURCE_BYTES = 8 * 1024 * 1024
SPECIMEN_PROJECTION_SINGLE_ROW_MAX_SOURCE_BYTES = SPECIMEN_PROJECTION_BATCH_SOURCE_BYTES
COMPACT_MANIFEST_KEYS = (
    "version",
    "specimenID",
    "creatureID",
    "runID",
    "campaignID",
    "sourceKind",
    "sourceMode",
    "sourceAlgorithm",
    "runtimeFamily",
    "runtimeCapabilities",
    "configHash",
    "recordedAt",
    "initialConditionFamily",
    "taxonomy",
    "traitLabels",
    "replay",
)
SOURCE_OBSERVATION_KINDS = frozenset(
    {
        "geometric_morphometric_embedding",
        "embryomaker_legacy_snapshot_summary",
    }
)
DERIVED_OBSERVATION_KINDS = frozenset(
    {
        "synthetic_ca_terminal_embedding",
        "common_point_cloud_morphology",
    }
)
COMPENDIUM_ARTIFACT_KINDS = frozenset({"compendium", "compendium_sqlite"})
TRANSFORMED_TABLES = frozenset(
    {
        "feature_axes",
        "feature_spaces",
        "feature_values",
        "observations",
        "specimens",
        "study_specimens",
    }
)

# These tables encode coordinates produced under the v8 descriptor contract. Copying
# them would make it possible to mix the old planar geometry with torus-v2 geometry.
INVALIDATED_COORDINATE_TABLES = frozenset(
    {
        "anatomical_state_axes",
        "context_sample_axes",
        "creature_signal_axes",
        "development_sample_axes",
        "perturbation_axes",
        "specimen_axes",
    }
)
LEGACY_DERIVED_TABLES = frozenset(
    {
        *INVALIDATED_COORDINATE_TABLES,
        "anatomical_states",
        "context_outcomes",
        "creature_state_labels",
        "feature_calibrations",
        "fiber_group_members",
        "fiber_groups",
        "specimen_status",
        "specimen_feature_vectors",
        "topology_features",
        "topology_runs",
        "trajectory_segments",
        "universality_runs",
    }
)
STALE_DERIVED_TABLE_REASONS = {
    "anatomical_states": "anatomical states depend on invalidated descriptor coordinates",
    "context_outcomes": "context outcomes depend on invalidated response coordinates",
    "creature_state_labels": "creature labels depend on invalidated anatomical coordinates",
    "fiber_group_members": "fiber memberships depend on invalidated anatomical coordinates",
    "fiber_groups": "fiber groups depend on invalidated anatomical coordinates",
    "observations": "comparison observations depend on omitted legacy feature projections",
    "specimen_status": "eligibility status must be recomputed from the v9 descriptor contract",
    "trajectory_segments": "trajectory segments depend on invalidated response coordinates",
    "universality_runs": "universality results depend on omitted legacy feature projections",
}
MIGRATION_METADATA_TABLES = frozenset(
    {
        "derived_artifact_state",
        "source_receipts",
        "specimen_descriptors",
    }
)
OMITTED_TABLES = frozenset(
    {
        "schema_meta",
        "feature_axes",
        "feature_spaces",
        "feature_values",
        "observations",
        "raw_sqlite_rows",
        *LEGACY_DERIVED_TABLES,
        *MIGRATION_METADATA_TABLES,
    }
)


class WarehouseMigrationError(RuntimeError):
    pass


class MigrationValidationError(WarehouseMigrationError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    source_path: Path
    destination_path: Path
    source_sha256: str
    receipt_id: str
    copied_row_counts: dict[str, int]
    descriptor_count: int
    invalidation_count: int
    membership_normalization: dict[str, object]
    nonfinite_feature_quarantine: dict[str, object]
    orphan_context_omission: dict[str, object]


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class MembershipNormalizationPlan:
    canonical_study_id: str
    source_study_ids: tuple[str, ...]
    retired_study_ids: tuple[str, ...]
    source_study_count: int
    source_aggregate_study_count: int
    source_run_scoped_study_count: int
    direct_compendium_study_count: int
    artifact_lineage_study_count: int
    metadata_lineage_study_count: int
    source_membership_count: int
    source_distinct_membership_specimen_count: int
    source_primary_specimen_count: int
    normalized_specimen_count: int
    reassigned_specimen_count: int
    collapsed_duplicate_membership_count: int
    synthesized_primary_only_membership_count: int
    preserved_membership_count: int
    resulting_membership_count: int
    canonical_study_preexisting: bool

    def metadata(self) -> dict[str, object]:
        return {
            "policy": "canonical-aggregate-compendium-v1",
            "canonicalStudyId": self.canonical_study_id,
            "canonicalStudyLabel": CANONICAL_COMPENDIUM_STUDY_LABEL,
            "canonicalStudyPreexisting": self.canonical_study_preexisting,
            "sourceStudyCount": self.source_study_count,
            "sourceAggregateStudyCount": self.source_aggregate_study_count,
            "sourceRunScopedStudyCount": self.source_run_scoped_study_count,
            "retiredLegacyStudyCount": len(self.retired_study_ids),
            "directCompendiumStudyCount": self.direct_compendium_study_count,
            "artifactLineageStudyCount": self.artifact_lineage_study_count,
            "metadataLineageStudyCount": self.metadata_lineage_study_count,
            "sourceMembershipCount": self.source_membership_count,
            "sourceDistinctMembershipSpecimenCount": (
                self.source_distinct_membership_specimen_count
            ),
            "sourcePrimarySpecimenCount": self.source_primary_specimen_count,
            "normalizedSpecimenCount": self.normalized_specimen_count,
            "reassignedSpecimenCount": self.reassigned_specimen_count,
            "removedSourceMembershipCount": self.source_membership_count,
            "insertedCanonicalMembershipCount": self.normalized_specimen_count,
            "collapsedDuplicateMembershipCount": (self.collapsed_duplicate_membership_count),
            "synthesizedPrimaryOnlyMembershipCount": (
                self.synthesized_primary_only_membership_count
            ),
            "preservedMembershipCount": self.preserved_membership_count,
            "resultingMembershipCount": self.resulting_membership_count,
            "sourceStudyIdsSha256": row_sha256(list(self.source_study_ids)),
        }


@dataclass(frozen=True)
class OrphanContextOmissionPlan:
    contexts: tuple[tuple[str, str | None], ...]

    @property
    def context_ids(self) -> tuple[str, ...]:
        return tuple(context_id for context_id, _ in self.contexts)

    def metadata(self) -> dict[str, object]:
        return {
            "policy": "omit-unreferenced-orphan-contexts-v1",
            "omittedContextCount": len(self.contexts),
            "omittedContextIds": list(self.context_ids),
            "missingStudyIds": sorted(
                {study_id for _, study_id in self.contexts if study_id is not None}
            ),
            "contexts": [
                {"contextId": context_id, "missingStudyId": study_id}
                for context_id, study_id in self.contexts
            ],
        }


@dataclass(frozen=True)
class NonfiniteFeatureQuarantine:
    affected_row_count: int
    affected_observation_count: int
    raw_value_count: int
    normalized_value_count: int
    feature_space_ids: tuple[str, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "policy": "null-nonfinite-source-coordinates-v1",
            "affectedFeatureValueRowCount": self.affected_row_count,
            "affectedObservationCount": self.affected_observation_count,
            "rawValueCount": self.raw_value_count,
            "normalizedValueCount": self.normalized_value_count,
            "featureSpaceIds": list(self.feature_space_ids),
        }


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _file_identity(path: Path) -> FileIdentity:
    stat = path.stat()
    return FileIdentity(
        device=stat.st_dev,
        inode=stat.st_ino,
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        changed_ns=stat.st_ctime_ns,
    )


def _same_directory_hardlink_aliases(path: Path) -> list[Path]:
    source_stat = path.stat()
    aliases: list[Path] = []
    for candidate in path.parent.iterdir():
        try:
            candidate_stat = candidate.stat()
        except FileNotFoundError:
            continue
        if (
            candidate_stat.st_dev == source_stat.st_dev
            and candidate_stat.st_ino == source_stat.st_ino
        ):
            aliases.append(candidate)
    return sorted(aliases)


def _assert_source_wal_free(path: Path, *, stage: str) -> None:
    for alias in _same_directory_hardlink_aliases(path):
        wal_path = Path(f"{alias}.wal")
        try:
            wal_size = wal_path.stat().st_size
        except FileNotFoundError:
            continue
        if wal_size > 0:
            raise MigrationValidationError(
                f"source warehouse has a non-empty DuckDB WAL {stage}: {wal_path} "
                f"({wal_size} bytes); checkpoint and quiesce the source before migration"
            )


def _assert_source_identity(
    path: Path,
    expected: FileIdentity,
    *,
    stage: str,
) -> None:
    _assert_source_wal_free(path, stage=stage)
    if _file_identity(path) != expected:
        raise MigrationValidationError(f"source warehouse changed {stage}")


def _configure_migration_connection(
    connection: DuckDBPyConnection,
    *,
    temp_directory: Path,
    writable: bool,
) -> None:
    temp_directory.mkdir(parents=True, exist_ok=True)
    connection.execute(f"SET memory_limit={_quote_literal(MIGRATION_MEMORY_LIMIT)}")
    connection.execute(f"SET threads={MIGRATION_THREADS}")
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET temp_directory=?", [str(temp_directory)])
    if writable:
        connection.execute(
            f"SET wal_autocheckpoint={_quote_literal(MIGRATION_CHECKPOINT_THRESHOLD)}"
        )
        connection.execute(
            f"SET checkpoint_threshold={_quote_literal(MIGRATION_CHECKPOINT_THRESHOLD)}"
        )


def _table_names(connection: DuckDBPyConnection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_catalog = current_database()
              AND table_schema = 'main'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()
    ]


def _classify_source_tables(
    source_tables: list[str],
    destination_tables: set[str],
) -> dict[str, list[str]]:
    source_set = set(source_tables)
    transformed = source_set & TRANSFORMED_TABLES
    omitted = source_set & (OMITTED_TABLES - TRANSFORMED_TABLES)
    direct = (source_set & destination_tables) - transformed - omitted
    unknown = source_set - transformed - omitted - direct
    if unknown:
        raise WarehouseMigrationError(
            "source contains unclassified tables: " + ", ".join(sorted(unknown))
        )
    return {
        "directCopy": sorted(direct),
        "transformedCopy": sorted(transformed),
        "omitted": sorted(omitted),
    }


def _table_columns(connection: DuckDBPyConnection, table_name: str) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_catalog = current_database()
              AND table_schema = 'main'
              AND table_name = ?
            ORDER BY ordinal_position
            """,
            [table_name],
        ).fetchall()
    ]


def _validate_copy_columns(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
    table_classification: dict[str, list[str]],
) -> None:
    copied_tables = table_classification["directCopy"] + table_classification["transformedCopy"]
    for table_name in copied_tables:
        source_columns = set(_table_columns(source, table_name))
        destination_columns = set(_table_columns(destination, table_name))
        unclassified_columns = source_columns - destination_columns
        if unclassified_columns:
            raise WarehouseMigrationError(
                f"{table_name} contains unclassified source columns: "
                + ", ".join(sorted(unclassified_columns))
            )


def _row_count(connection: DuckDBPyConnection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}").fetchone()
    if row is None:
        raise MigrationValidationError(f"count query returned no row for {table_name}")
    return int(row[0])


def _query_count(
    connection: DuckDBPyConnection,
    query: str,
    params: list[Any] | None = None,
) -> int:
    row = connection.execute(query, params or []).fetchone()
    if row is None:
        raise MigrationValidationError("count query returned no row")
    return int(row[0])


def _validate_source_references(
    connection: DuckDBPyConnection,
    source_tables: set[str],
) -> None:
    required = {"specimens", "studies", "study_specimens"}
    missing = required - source_tables
    if missing:
        raise MigrationValidationError(
            "source is missing required tables: " + ", ".join(sorted(missing))
        )
    orphan_memberships = _query_count(
        connection,
        """
        SELECT count(*)
        FROM study_specimens
        LEFT JOIN studies USING (study_id)
        LEFT JOIN specimens USING (specimen_id)
        WHERE studies.study_id IS NULL OR specimens.specimen_id IS NULL
        """,
    )
    if orphan_memberships:
        raise MigrationValidationError("source study_specimens contains orphaned membership")
    orphan_specimens = _query_count(
        connection,
        """
        SELECT count(*)
        FROM specimens
        LEFT JOIN studies USING (study_id)
        WHERE studies.study_id IS NULL
        """,
    )
    if orphan_specimens:
        raise MigrationValidationError("source specimens contains an unknown study_id")


def _build_orphan_context_omission_plan(
    connection: DuckDBPyConnection,
    *,
    source_tables: set[str],
) -> OrphanContextOmissionPlan:
    if "contexts" not in source_tables:
        return OrphanContextOmissionPlan(())
    context_columns = set(_table_columns(connection, "contexts"))
    required_columns = {"context_id", "study_id"}
    missing_columns = required_columns - context_columns
    if missing_columns:
        raise MigrationValidationError(
            "source contexts is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    rows = connection.execute(
        """
        SELECT context.context_id, context.study_id
        FROM contexts AS context
        LEFT JOIN studies AS study ON study.study_id = context.study_id
        WHERE study.study_id IS NULL
        ORDER BY context.context_id
        """
    ).fetchall()
    if any(row[0] is None for row in rows):
        raise MigrationValidationError("source contexts contains a null context_id")
    contexts = tuple(
        (str(context_id), None if study_id is None else str(study_id))
        for context_id, study_id in rows
    )
    plan = OrphanContextOmissionPlan(contexts)
    if not contexts:
        return plan

    orphan_ids = list(plan.context_ids)
    for table_name in sorted(source_tables - {"contexts"}):
        if "context_id" not in set(_table_columns(connection, table_name)):
            continue
        referenced_rows = connection.execute(
            f"""
            SELECT count(*), list(DISTINCT context_id ORDER BY context_id)
            FROM {_quote_identifier(table_name)}
            WHERE context_id IN (SELECT unnest(?::VARCHAR[]))
            """,
            [orphan_ids],
        ).fetchone()
        if referenced_rows is None:
            raise MigrationValidationError(
                f"orphan-context reference query returned no row for {table_name}"
            )
        reference_count = int(referenced_rows[0])
        if reference_count:
            referenced_ids = ", ".join(str(value) for value in referenced_rows[1])
            raise MigrationValidationError(
                "source orphan contexts have dependent rows and cannot be omitted: "
                f"{table_name} has {reference_count} row(s) referencing {referenced_ids}"
            )
    return plan


def _metadata_path_is_compendium(value: object) -> bool:
    if value is None:
        return False
    normalized = str(value).replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1].casefold() == "compendium.sqlite"


def _build_membership_normalization_plan(
    connection: DuckDBPyConnection,
    *,
    source_tables: set[str],
) -> MembershipNormalizationPlan:
    canonical_study_id = canonical_compendium_study_id()
    study_columns = set(_table_columns(connection, "studies"))
    metadata_expression = (
        "json_extract_string(metadata_json, '$.sourceArtifact')"
        if "metadata_json" in study_columns
        else "NULL"
    )
    study_rows = connection.execute(
        f"""
        SELECT study_id, study_kind, run_id, label, {metadata_expression}
        FROM studies
        ORDER BY study_id
        """
    ).fetchall()
    artifact_lineage_ids: set[str] = set()
    if "artifacts" in source_tables:
        artifact_columns = set(_table_columns(connection, "artifacts"))
        if {"study_id", "artifact_kind"} <= artifact_columns:
            artifact_lineage_ids = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT DISTINCT study_id
                    FROM artifacts
                    WHERE artifact_kind IN (SELECT unnest(?))
                    """,
                    [sorted(COMPENDIUM_ARTIFACT_KINDS)],
                ).fetchall()
            }

    source_study_ids: list[str] = []
    direct_compendium_count = 0
    artifact_lineage_count = 0
    metadata_lineage_count = 0
    aggregate_count = 0
    run_scoped_count = 0
    canonical_preexisting = False
    for raw_study_id, raw_kind, run_id, raw_label, source_artifact in study_rows:
        study_id = str(raw_study_id)
        study_kind = str(raw_kind)
        label = None if raw_label is None else str(raw_label)
        if study_id == canonical_study_id:
            canonical_preexisting = True
            if (
                study_kind != "discovery"
                or run_id is not None
                or label != CANONICAL_COMPENDIUM_STUDY_LABEL
            ):
                raise MigrationValidationError(
                    "canonical compendium study ID is occupied by an incompatible study"
                )
        direct_lineage = study_kind == "compendium"
        artifact_lineage = study_kind == "discovery" and study_id in artifact_lineage_ids
        metadata_lineage = study_kind == "discovery" and _metadata_path_is_compendium(
            source_artifact
        )
        canonical_lineage = study_id == canonical_study_id
        if not (direct_lineage or artifact_lineage or metadata_lineage or canonical_lineage):
            continue
        source_study_ids.append(study_id)
        direct_compendium_count += int(direct_lineage)
        artifact_lineage_count += int(artifact_lineage)
        metadata_lineage_count += int(metadata_lineage)
        if run_id is None:
            aggregate_count += 1
        else:
            run_scoped_count += 1

    source_study_ids.sort()
    retired_study_ids = tuple(
        study_id for study_id in source_study_ids if study_id != canonical_study_id
    )
    total_membership_count = _row_count(connection, "study_specimens")
    if not source_study_ids:
        return MembershipNormalizationPlan(
            canonical_study_id=canonical_study_id,
            source_study_ids=(),
            retired_study_ids=(),
            source_study_count=0,
            source_aggregate_study_count=0,
            source_run_scoped_study_count=0,
            direct_compendium_study_count=0,
            artifact_lineage_study_count=0,
            metadata_lineage_study_count=0,
            source_membership_count=0,
            source_distinct_membership_specimen_count=0,
            source_primary_specimen_count=0,
            normalized_specimen_count=0,
            reassigned_specimen_count=0,
            collapsed_duplicate_membership_count=0,
            synthesized_primary_only_membership_count=0,
            preserved_membership_count=total_membership_count,
            resulting_membership_count=total_membership_count,
            canonical_study_preexisting=False,
        )

    params = [source_study_ids]
    source_membership_count = _query_count(
        connection,
        """
        SELECT count(*)
        FROM study_specimens
        WHERE study_id IN (SELECT unnest(?))
        """,
        params,
    )
    distinct_membership_specimens = _query_count(
        connection,
        """
        SELECT count(DISTINCT specimen_id)
        FROM study_specimens
        WHERE study_id IN (SELECT unnest(?))
        """,
        params,
    )
    source_primary_specimens = _query_count(
        connection,
        """
        SELECT count(*)
        FROM specimens
        WHERE study_id IN (SELECT unnest(?))
        """,
        params,
    )
    normalized_specimens = _query_count(
        connection,
        """
        SELECT count(*)
        FROM (
            SELECT specimen_id
            FROM specimens
            WHERE study_id IN (SELECT unnest(?))
            UNION
            SELECT specimen_id
            FROM study_specimens
            WHERE study_id IN (SELECT unnest(?))
        ) AS normalized
        """,
        [source_study_ids, source_study_ids],
    )
    reassigned_specimens = _query_count(
        connection,
        """
        SELECT count(*)
        FROM specimens
        WHERE specimen_id IN (
            SELECT specimen_id
            FROM specimens
            WHERE study_id IN (SELECT unnest(?))
            UNION
            SELECT specimen_id
            FROM study_specimens
            WHERE study_id IN (SELECT unnest(?))
        )
          AND study_id <> ?
        """,
        [source_study_ids, source_study_ids, canonical_study_id],
    )
    preserved_memberships = total_membership_count - source_membership_count
    return MembershipNormalizationPlan(
        canonical_study_id=canonical_study_id,
        source_study_ids=tuple(source_study_ids),
        retired_study_ids=retired_study_ids,
        source_study_count=len(source_study_ids),
        source_aggregate_study_count=aggregate_count,
        source_run_scoped_study_count=run_scoped_count,
        direct_compendium_study_count=direct_compendium_count,
        artifact_lineage_study_count=artifact_lineage_count,
        metadata_lineage_study_count=metadata_lineage_count,
        source_membership_count=source_membership_count,
        source_distinct_membership_specimen_count=distinct_membership_specimens,
        source_primary_specimen_count=source_primary_specimens,
        normalized_specimen_count=normalized_specimens,
        reassigned_specimen_count=reassigned_specimens,
        collapsed_duplicate_membership_count=(
            source_membership_count - distinct_membership_specimens
        ),
        synthesized_primary_only_membership_count=(
            normalized_specimens - distinct_membership_specimens
        ),
        preserved_membership_count=preserved_memberships,
        resulting_membership_count=preserved_memberships + normalized_specimens,
        canonical_study_preexisting=canonical_preexisting,
    )


def _copy_intersecting_table(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
    table_name: str,
    *,
    source_row_count: int,
) -> int:
    source_columns = set(_table_columns(source, table_name))
    destination_column_order = _table_columns(destination, table_name)
    unclassified_columns = source_columns - set(destination_column_order)
    if unclassified_columns:
        raise WarehouseMigrationError(
            f"{table_name} contains unclassified source columns: "
            + ", ".join(sorted(unclassified_columns))
        )
    columns = [column for column in destination_column_order if column in source_columns]
    if not columns:
        return 0
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    destination.execute(
        f"INSERT INTO main.{_quote_identifier(table_name)} ({column_sql}) "
        f"SELECT {column_sql} FROM legacy.main.{_quote_identifier(table_name)}"
    )
    return source_row_count


def _copy_contexts(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
    *,
    source_row_count: int,
    omission_plan: OrphanContextOmissionPlan,
) -> int:
    if not omission_plan.contexts:
        return _copy_intersecting_table(
            source,
            destination,
            "contexts",
            source_row_count=source_row_count,
        )
    source_columns = set(_table_columns(source, "contexts"))
    destination_column_order = _table_columns(destination, "contexts")
    unclassified_columns = source_columns - set(destination_column_order)
    if unclassified_columns:
        raise WarehouseMigrationError(
            "contexts contains unclassified source columns: "
            + ", ".join(sorted(unclassified_columns))
        )
    columns = [column for column in destination_column_order if column in source_columns]
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    destination.execute(
        f"INSERT INTO main.contexts ({column_sql}) "
        f"SELECT {column_sql} FROM legacy.main.contexts "
        "WHERE context_id NOT IN (SELECT unnest(?::VARCHAR[]))",
        [list(omission_plan.context_ids)],
    )
    return source_row_count - len(omission_plan.contexts)


def _copy_source_observation_layer(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
) -> tuple[dict[str, int], int, set[str], NonfiniteFeatureQuarantine]:
    empty_quarantine = NonfiniteFeatureQuarantine(0, 0, 0, 0, ())
    if "observations" not in _table_names(source):
        return {}, 0, set(), empty_quarantine
    kinds = {
        str(row[0])
        for row in source.execute("SELECT DISTINCT observation_kind FROM observations").fetchall()
    }
    known_kinds = SOURCE_OBSERVATION_KINDS | DERIVED_OBSERVATION_KINDS
    unknown_kinds = kinds - known_kinds
    if unknown_kinds:
        raise WarehouseMigrationError(
            "observations contain unknown kinds: " + ", ".join(sorted(unknown_kinds))
        )

    source_columns = set(_table_columns(source, "observations"))
    columns = [
        column for column in _table_columns(destination, "observations") if column in source_columns
    ]
    if not columns:
        return {}, 0, set(), empty_quarantine
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    source_kinds = sorted(SOURCE_OBSERVATION_KINDS & kinds)
    if source_kinds:
        placeholders = ", ".join("?" for _ in source_kinds)
        destination.execute(
            f"INSERT INTO main.observations ({column_sql}) "
            f"SELECT {column_sql} FROM legacy.main.observations "
            f"WHERE observation_kind IN ({placeholders})",
            source_kinds,
        )
    copied_row = source.execute(
        "SELECT COUNT(*) FROM observations WHERE observation_kind IN (SELECT unnest(?))",
        [source_kinds],
    ).fetchone()
    derived_kinds = sorted(DERIVED_OBSERVATION_KINDS & kinds)
    derived_row = source.execute(
        "SELECT COUNT(*) FROM observations WHERE observation_kind IN (SELECT unnest(?))",
        [derived_kinds],
    ).fetchone()
    counts = {"observations": int(copied_row[0]) if copied_row is not None else 0}
    preserved_feature_space_ids: set[str] = set()
    quarantine = empty_quarantine
    source_tables = set(_table_names(source))
    if source_kinds and "feature_values" in source_tables:
        preserved_feature_space_ids = {
            str(row[0])
            for row in source.execute(
                """
                SELECT DISTINCT feature_values.feature_space_id
                FROM feature_values
                JOIN observations USING (observation_id)
                WHERE observations.observation_kind IN (SELECT unnest(?))
                """,
                [source_kinds],
            ).fetchall()
        }
        feature_value_columns = [
            column
            for column in _table_columns(destination, "sparse_feature_values")
            if column in set(_table_columns(source, "feature_values"))
        ]
        finite_columns = {"raw_value", "normalized_value"} & set(feature_value_columns)
        nonfinite_predicates = [
            f"feature_values.{_quote_identifier(column)} IS NOT NULL "
            f"AND NOT isfinite(feature_values.{_quote_identifier(column)})"
            for column in sorted(finite_columns)
        ]
        nonfinite_predicate = " OR ".join(f"({predicate})" for predicate in nonfinite_predicates)
        if nonfinite_predicate:
            placeholders = ", ".join("?" for _ in source_kinds)
            quarantine_row = source.execute(
                f"""
                SELECT count(*) FILTER (WHERE {nonfinite_predicate}),
                       count(DISTINCT feature_values.observation_id)
                           FILTER (WHERE {nonfinite_predicate}),
                       count(*) FILTER (
                           WHERE feature_values.raw_value IS NOT NULL
                             AND NOT isfinite(feature_values.raw_value)
                       ),
                       count(*) FILTER (
                           WHERE feature_values.normalized_value IS NOT NULL
                             AND NOT isfinite(feature_values.normalized_value)
                       )
                FROM feature_values
                JOIN observations USING (observation_id)
                WHERE observations.observation_kind IN ({placeholders})
                """,
                source_kinds,
            ).fetchone()
            if quarantine_row is None:
                raise MigrationValidationError(
                    "nonfinite feature-value count query returned no row"
                )
            quarantined_space_ids = tuple(
                sorted(
                    str(row[0])
                    for row in source.execute(
                        f"""
                        SELECT DISTINCT feature_values.feature_space_id
                        FROM feature_values
                        JOIN observations USING (observation_id)
                        WHERE observations.observation_kind IN ({placeholders})
                          AND ({nonfinite_predicate})
                        """,
                        source_kinds,
                    ).fetchall()
                )
            )
            quarantine = NonfiniteFeatureQuarantine(
                affected_row_count=int(quarantine_row[0]),
                affected_observation_count=int(quarantine_row[1]),
                raw_value_count=int(quarantine_row[2]),
                normalized_value_count=int(quarantine_row[3]),
                feature_space_ids=quarantined_space_ids,
            )
        feature_value_expressions: list[str] = []
        for column in feature_value_columns:
            qualified = f"feature_values.{_quote_identifier(column)}"
            if column in finite_columns:
                feature_value_expressions.append(
                    f"CASE WHEN {qualified} IS NULL OR isfinite({qualified}) THEN {qualified} END"
                )
            else:
                feature_value_expressions.append(qualified)
        feature_value_sql = ", ".join(feature_value_expressions)
        destination_column_sql = ", ".join(
            _quote_identifier(column) for column in feature_value_columns
        )
        placeholders = ", ".join("?" for _ in source_kinds)
        destination.execute(
            f"INSERT INTO main.sparse_feature_values ({destination_column_sql}) "
            f"SELECT {feature_value_sql} FROM legacy.main.feature_values AS feature_values "
            "JOIN legacy.main.observations AS observations USING (observation_id) "
            f"WHERE observations.observation_kind IN ({placeholders})",
            source_kinds,
        )
        count_row = destination.execute(
            "SELECT COUNT(*) FROM sparse_feature_values"
        ).fetchone()
        counts["sparse_feature_values"] = int(count_row[0]) if count_row is not None else 0

    feature_space_ids = sorted(preserved_feature_space_ids)
    if feature_space_ids and "feature_spaces" in source_tables:
        columns = [
            column
            for column in _table_columns(destination, "feature_spaces")
            if column in set(_table_columns(source, "feature_spaces"))
        ]
        source_column_sql = ", ".join(_quote_identifier(column) for column in columns)
        destination_column_sql = source_column_sql + ", storage_mode"
        placeholders = ", ".join("?" for _ in feature_space_ids)
        destination.execute(
            f"INSERT INTO main.feature_spaces ({destination_column_sql}) "
            f"SELECT {source_column_sql}, 'sparse_values' "
            "FROM legacy.main.feature_spaces "
            f"WHERE feature_space_id IN ({placeholders})",
            feature_space_ids,
        )
        counts["feature_spaces"] = len(feature_space_ids)
    if feature_space_ids and "feature_axes" in source_tables:
        columns = [
            column
            for column in _table_columns(destination, "feature_axes")
            if column in set(_table_columns(source, "feature_axes"))
        ]
        column_sql = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in feature_space_ids)
        destination.execute(
            f"INSERT INTO main.feature_axes ({column_sql}) "
            f"SELECT {column_sql} FROM legacy.main.feature_axes "
            f"WHERE feature_space_id IN ({placeholders})",
            feature_space_ids,
        )
        count_row = destination.execute("SELECT COUNT(*) FROM feature_axes").fetchone()
        counts["feature_axes"] = int(count_row[0]) if count_row is not None else 0
    return (
        counts,
        int(derived_row[0]) if derived_row is not None else 0,
        preserved_feature_space_ids,
        quarantine,
    )


def _object_json_expression(root: str, path: str, *, decode_string: bool = False) -> str:
    extracted = (
        f"try_cast(json_extract_string({root}, {_quote_literal(path)}) AS JSON)"
        if decode_string
        else f"json_extract({root}, {_quote_literal(path)})"
    )
    return f"CASE WHEN json_type({extracted}) = 'OBJECT' THEN {extracted} END"


def _first_object_expression(expressions: list[str]) -> str:
    return "coalesce(" + ", ".join(expressions) + ")"


def _retained_manifest_expression() -> str:
    arguments: list[str] = []
    for key in COMPACT_MANIFEST_KEYS:
        arguments.extend(
            [
                _quote_literal(key),
                f"json_extract(legacy_manifest, {_quote_literal(f'$.{key}')})",
            ]
        )
    return "json_merge_patch('{}'::JSON, json_object(" + ", ".join(arguments) + "))"


def _next_specimen_ids(
    source: DuckDBPyConnection,
    *,
    after_specimen_id: str | None,
    batch_size: int,
) -> list[str]:
    if batch_size <= 0:
        raise ValueError("specimen projection batch size must be positive")
    if after_specimen_id is None:
        rows = source.execute(
            "SELECT specimen_id FROM specimens ORDER BY specimen_id LIMIT ?",
            [batch_size],
        ).fetchall()
    else:
        rows = source.execute(
            """
            SELECT specimen_id
            FROM specimens
            WHERE specimen_id > ?
            ORDER BY specimen_id
            LIMIT ?
            """,
            [after_specimen_id, batch_size],
        ).fetchall()
    if any(row[0] is None for row in rows):
        raise MigrationValidationError("legacy specimens contains a null specimen_id")
    specimen_ids = [str(row[0]) for row in rows]
    if len(specimen_ids) != len(set(specimen_ids)):
        raise MigrationValidationError("legacy specimens contains duplicate specimen_id values")
    return specimen_ids


def _byte_bounded_specimen_ids(
    source: DuckDBPyConnection,
    specimen_ids: list[str],
    *,
    source_columns: set[str],
    max_source_bytes: int,
    single_row_max_source_bytes: int,
) -> tuple[list[str], int]:
    if not specimen_ids:
        return [], 0
    if max_source_bytes <= 0:
        raise ValueError("specimen projection byte limit must be positive")
    if single_row_max_source_bytes < max_source_bytes:
        raise ValueError("specimen projection single-row limit must cover the batch byte limit")

    def serialized_size(column: str) -> str:
        if column not in source_columns:
            return "2"
        return (
            "octet_length(encode(CAST(coalesce("
            f"s.{_quote_identifier(column)}, '{{}}'::JSON) AS VARCHAR)))"
        )

    rows = source.execute(
        f"""
        SELECT s.specimen_id,
               {serialized_size("provenance_json")}
               + {serialized_size("specimen_manifest_json")} AS source_bytes
        FROM specimens AS s
        WHERE s.specimen_id >= ? AND s.specimen_id <= ?
        ORDER BY s.specimen_id
        """,
        [specimen_ids[0], specimen_ids[-1]],
    ).fetchall()
    measured_ids = [str(row[0]) for row in rows]
    if measured_ids != specimen_ids:
        raise MigrationValidationError(
            "legacy specimen keyset changed while measuring projection payloads"
        )

    selected: list[str] = []
    selected_bytes = 0
    for specimen_id, raw_source_bytes in rows:
        source_bytes = int(raw_source_bytes)
        if source_bytes > single_row_max_source_bytes:
            raise MigrationValidationError(
                "legacy specimen serialized projection payload exceeds the single-row "
                f"hard limit: {specimen_id} has {source_bytes} bytes, limit is "
                f"{single_row_max_source_bytes} bytes"
            )
        if selected and selected_bytes + source_bytes > max_source_bytes:
            break
        selected.append(str(specimen_id))
        selected_bytes += source_bytes

    if not selected:
        raise MigrationValidationError("specimen projection byte selection returned no rows")
    return selected, selected_bytes


def _note_cleanup_failure(
    primary_error: BaseException,
    *,
    operation: str,
    cleanup_error: BaseException,
) -> None:
    primary_error.add_note(
        f"{operation} also failed with {type(cleanup_error).__name__}: {cleanup_error}"
    )


def _preserve_cleanup_failure(
    primary_error: BaseException | None,
    *,
    operation: str,
    cleanup_error: BaseException,
) -> BaseException:
    if primary_error is None:
        return cleanup_error
    _note_cleanup_failure(
        primary_error,
        operation=operation,
        cleanup_error=cleanup_error,
    )
    return primary_error


def _rollback_preserving_error(
    connection: DuckDBPyConnection,
    primary_error: BaseException,
) -> None:
    try:
        connection.execute("ROLLBACK")
    except BaseException as cleanup_error:
        _note_cleanup_failure(
            primary_error,
            operation="specimen projection rollback",
            cleanup_error=cleanup_error,
        )


def _drop_specimen_projection(
    connection: DuckDBPyConnection,
    *,
    primary_error: BaseException | None,
) -> None:
    try:
        connection.execute("DROP TABLE IF EXISTS migration_specimen_projection")
    except BaseException as cleanup_error:
        if primary_error is None:
            raise
        _note_cleanup_failure(
            primary_error,
            operation="specimen projection cleanup",
            cleanup_error=cleanup_error,
        )


def _copy_specimens(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
    *,
    receipt_id: str,
    artifact_id: str,
    source_guard: Callable[[], None] | None = None,
) -> tuple[int, int]:
    source_columns = set(_table_columns(source, "specimens"))
    if "specimen_id" not in source_columns:
        raise MigrationValidationError("legacy specimens table has no specimen_id")
    destination_columns = _table_columns(destination, "specimens")
    overridden_columns = {
        "provenance_json",
        "specimen_manifest_json",
        "descriptor_version",
        "terminal_version",
        "normalization_policy",
        "fingerprint_resolution",
    }
    passthrough_columns = [
        column
        for column in destination_columns
        if column in source_columns and column not in overridden_columns
    ]
    source_projection = [f"s.{_quote_identifier(column)}" for column in passthrough_columns]
    source_projection.extend(
        [
            (
                "coalesce(s.provenance_json, '{}'::JSON) AS legacy_provenance"
                if "provenance_json" in source_columns
                else "'{}'::JSON AS legacy_provenance"
            ),
            (
                "coalesce(s.specimen_manifest_json, '{}'::JSON) AS legacy_manifest"
                if "specimen_manifest_json" in source_columns
                else "'{}'::JSON AS legacy_manifest"
            ),
        ]
    )
    passthrough_column_sql = ", ".join(_quote_identifier(column) for column in passthrough_columns)
    terminal_expression = _first_object_expression(
        [
            _object_json_expression("legacy_provenance", "$.terminal"),
            _object_json_expression("legacy_provenance", "$.descriptorBundle.terminal"),
            _object_json_expression("legacy_provenance", "$.descriptor_bundle.terminal"),
            _object_json_expression("legacy_manifest", "$.snapshots.descriptorBundle.terminal"),
            _object_json_expression("legacy_manifest", "$.snapshots.descriptor_bundle.terminal"),
            _object_json_expression(
                "legacy_provenance",
                "$.specimen.terminal_descriptor_json",
                decode_string=True,
            ),
        ]
    )
    trajectory_expression = _first_object_expression(
        [
            _object_json_expression("legacy_provenance", "$.trajectory"),
            _object_json_expression("legacy_provenance", "$.descriptorBundle.trajectory"),
            _object_json_expression("legacy_provenance", "$.descriptor_bundle.trajectory"),
            _object_json_expression("legacy_manifest", "$.snapshots.descriptorBundle.trajectory"),
            _object_json_expression("legacy_manifest", "$.snapshots.descriptor_bundle.trajectory"),
            _object_json_expression(
                "legacy_provenance",
                "$.specimen.trajectory_descriptor_json",
                decode_string=True,
            ),
        ]
    )
    output_expressions: list[str] = []
    for column in destination_columns:
        quoted = _quote_identifier(column)
        if column == "provenance_json":
            expression = "compact_provenance"
        elif column == "specimen_manifest_json":
            expression = "compact_manifest"
        elif column in {
            "descriptor_version",
            "terminal_version",
            "normalization_policy",
            "fingerprint_resolution",
        }:
            expression = f"{column}_v9"
        elif column in passthrough_columns:
            expression = quoted
        else:
            expression = "NULL"
        output_expressions.append(f"{expression} AS {quoted}")

    recorded_at_expression = (
        _quote_identifier("recorded_at") if "recorded_at" in passthrough_columns else "NULL"
    )

    def selected_columns(columns: list[str]) -> str:
        return ", ".join(_quote_identifier(column) for column in columns)

    descriptor_candidate_columns = [
        *passthrough_columns,
        "terminal_descriptor_json_v9",
        "trajectory_descriptor_json_v9",
        "legacy_manifest_descriptor_version",
        "legacy_manifest_terminal_version",
        "legacy_manifest_normalization_policy",
        "legacy_manifest_fingerprint_resolution",
        "legacy_provenance_sha256",
        "legacy_manifest_sha256",
        "retained_manifest",
    ]
    contracted_static_columns = [
        *passthrough_columns,
        "terminal_descriptor_json_v9",
        "trajectory_descriptor_json_v9",
        "legacy_provenance_sha256",
        "legacy_manifest_sha256",
        "retained_manifest",
        "descriptor_version_v9",
    ]
    classified_static_columns = [
        *contracted_static_columns,
        "terminal_version_v9",
    ]
    classified_columns = [
        *classified_static_columns,
        "normalization_policy_v9",
        "fingerprint_resolution_v9",
        "descriptor_eligibility_v9",
    ]
    compacted_static_columns = [
        *passthrough_columns,
        "descriptor_version_v9",
        "terminal_version_v9",
        "normalization_policy_v9",
        "fingerprint_resolution_v9",
        "terminal_descriptor_json_v9",
        "trajectory_descriptor_json_v9",
        "descriptor_content_sha256",
    ]
    projection_sql = f"""
        CREATE TEMP TABLE migration_specimen_projection AS
        WITH source_rows AS (
            SELECT {", ".join(source_projection)}
            FROM legacy.main.specimens AS s
            WHERE s.specimen_id >= ? AND s.specimen_id <= ?
        ),
        descriptor_candidates AS MATERIALIZED (
            SELECT {passthrough_column_sql},
                   {terminal_expression} AS terminal_descriptor_json_v9,
                   {trajectory_expression} AS trajectory_descriptor_json_v9,
                   nullif(json_extract_string(
                       legacy_manifest, '$.descriptorVersion'
                   ), '') AS legacy_manifest_descriptor_version,
                   nullif(json_extract_string(
                       legacy_manifest, '$.terminalVersion'
                   ), '') AS legacy_manifest_terminal_version,
                   nullif(json_extract_string(
                       legacy_manifest, '$.normalizationPolicy'
                   ), '') AS legacy_manifest_normalization_policy,
                   nullif(json_extract_string(
                       legacy_manifest, '$.fingerprintResolution'
                   ), '') AS legacy_manifest_fingerprint_resolution,
                   sha256(CAST(legacy_provenance AS VARCHAR))
                       AS legacy_provenance_sha256,
                   sha256(CAST(legacy_manifest AS VARCHAR))
                       AS legacy_manifest_sha256,
                   {_retained_manifest_expression()} AS retained_manifest
            FROM source_rows
        ),
        versioned AS (
            SELECT {selected_columns(descriptor_candidate_columns)},
                   CASE WHEN terminal_descriptor_json_v9 IS NOT NULL THEN coalesce(
                       nullif(json_extract_string(
                           terminal_descriptor_json_v9, '$.descriptorVersion'
                       ), ''),
                       nullif(json_extract_string(terminal_descriptor_json_v9, '$.version'), ''),
                       legacy_manifest_descriptor_version,
                       '1'
                   ) END AS descriptor_version_v9
            FROM descriptor_candidates
        ),
        contracted AS (
            SELECT {selected_columns(contracted_static_columns)},
                   CASE WHEN terminal_descriptor_json_v9 IS NOT NULL THEN coalesce(
                       nullif(json_extract_string(
                           terminal_descriptor_json_v9, '$.terminalVersion'
                       ), ''),
                       legacy_manifest_terminal_version,
                       descriptor_version_v9
                   ) END AS terminal_version_v9,
                   CASE WHEN terminal_descriptor_json_v9 IS NOT NULL THEN coalesce(
                       nullif(json_extract_string(
                           terminal_descriptor_json_v9, '$.normalizationPolicy'
                       ), ''),
                       legacy_manifest_normalization_policy,
                       {_quote_literal(LEGACY_NORMALIZATION_POLICY)}
                   ) END AS normalization_policy_raw_v9,
                   CASE WHEN terminal_descriptor_json_v9 IS NOT NULL THEN try_cast(coalesce(
                           nullif(json_extract_string(
                               terminal_descriptor_json_v9, '$.fingerprintResolution'
                           ), ''),
                           legacy_manifest_fingerprint_resolution
                       ) AS DOUBLE) END AS fingerprint_resolution_number_v9
            FROM versioned
        ),
        classified AS (
            SELECT {selected_columns(classified_static_columns)},
                   CASE
                       WHEN descriptor_version_v9 = {_quote_literal(DESCRIPTOR_VERSION)}
                        AND terminal_version_v9 = {_quote_literal(TERMINAL_VERSION)}
                        AND normalization_policy_raw_v9 = {_quote_literal(NORMALIZATION_POLICY)}
                        AND json_extract_string(
                            terminal_descriptor_json_v9, '$.borderMode'
                        ) = 'torus'
                        AND fingerprint_resolution_number_v9 = 32.0
                       THEN normalization_policy_raw_v9
                       WHEN descriptor_version_v9 = {_quote_literal(DESCRIPTOR_VERSION)}
                         OR terminal_version_v9 = {_quote_literal(TERMINAL_VERSION)}
                         OR normalization_policy_raw_v9 = {_quote_literal(NORMALIZATION_POLICY)}
                       THEN {_quote_literal(INELIGIBLE_NORMALIZATION_POLICY)}
                       ELSE normalization_policy_raw_v9
                   END AS normalization_policy_v9,
                   CASE
                       WHEN fingerprint_resolution_number_v9 > 0
                        AND fingerprint_resolution_number_v9 = trunc(
                            fingerprint_resolution_number_v9
                        )
                       THEN try_cast(fingerprint_resolution_number_v9 AS INTEGER)
                   END AS fingerprint_resolution_v9,
                   CASE
                       WHEN descriptor_version_v9 = {_quote_literal(DESCRIPTOR_VERSION)}
                        AND terminal_version_v9 = {_quote_literal(TERMINAL_VERSION)}
                        AND normalization_policy_raw_v9 = {_quote_literal(NORMALIZATION_POLICY)}
                        AND json_extract_string(
                            terminal_descriptor_json_v9, '$.borderMode'
                        ) = 'torus'
                        AND fingerprint_resolution_number_v9 = 32.0
                       THEN 'eligible'
                       ELSE 'ineligible'
                   END AS descriptor_eligibility_v9
            FROM contracted
        ),
        hashed AS (
            SELECT {selected_columns(classified_columns)},
                   CASE WHEN terminal_descriptor_json_v9 IS NOT NULL THEN sha256(CAST(
                       json_object(
                           'descriptorVersion', descriptor_version_v9,
                           'terminalVersion', terminal_version_v9,
                           'normalizationPolicy', normalization_policy_v9,
                           'fingerprintResolution', fingerprint_resolution_v9,
                           'terminal', terminal_descriptor_json_v9,
                           'trajectory', coalesce(trajectory_descriptor_json_v9, '{{}}'::JSON)
                       ) AS VARCHAR
                   )) END AS descriptor_content_sha256
            FROM classified
        ),
        compacted AS (
            SELECT {selected_columns(compacted_static_columns)},
                   json_object(
                       'sourceReceiptId', ?,
                       'sourceArtifactId', ?,
                       'sourceSchemaVersion', ?,
                       'sourceTable', 'specimens',
                       'sourcePrimaryKey', specimen_id,
                       'legacyProvenanceSha256', legacy_provenance_sha256
                   ) AS compact_provenance,
                   json_merge_patch(
                       retained_manifest,
                       json_object(
                           'sourceReceiptId', ?,
                           'sourceArtifactId', ?,
                           'legacyManifestSha256', legacy_manifest_sha256,
                           'descriptorHash', descriptor_content_sha256,
                           'descriptorVersion', descriptor_version_v9,
                           'terminalVersion', terminal_version_v9,
                           'normalizationPolicy', normalization_policy_v9,
                           'fingerprintResolution', fingerprint_resolution_v9,
                           'descriptorEligibility', descriptor_eligibility_v9
                       )
                   ) AS compact_manifest
            FROM hashed
        )
        SELECT {", ".join(output_expressions)},
               terminal_descriptor_json_v9,
               coalesce(trajectory_descriptor_json_v9, '{{}}'::JSON)
                   AS trajectory_descriptor_json_v9,
               descriptor_content_sha256,
               coalesce({recorded_at_expression}, CAST(? AS TIMESTAMP))
                   AS descriptor_recorded_at
        FROM compacted
        """
    destination_column_sql = ", ".join(_quote_identifier(column) for column in destination_columns)
    source_row_count = _row_count(source, "specimens")
    migration_recorded_at = utc_now()
    copied = 0
    descriptor_count = 0
    after_specimen_id: str | None = None
    destination.execute("DROP TABLE IF EXISTS migration_specimen_projection")
    while copied < source_row_count:
        if source_guard is not None:
            source_guard()
        candidate_ids = _next_specimen_ids(
            source,
            after_specimen_id=after_specimen_id,
            batch_size=SPECIMEN_PROJECTION_BATCH_SIZE,
        )
        if not candidate_ids:
            raise MigrationValidationError(
                f"specimen projection copied {copied} of {source_row_count} source rows"
            )
        specimen_ids, _ = _byte_bounded_specimen_ids(
            source,
            candidate_ids,
            source_columns=source_columns,
            max_source_bytes=SPECIMEN_PROJECTION_BATCH_SOURCE_BYTES,
            single_row_max_source_bytes=(SPECIMEN_PROJECTION_SINGLE_ROW_MAX_SOURCE_BYTES),
        )
        first_specimen_id = specimen_ids[0]
        last_specimen_id = specimen_ids[-1]
        primary_error: BaseException | None = None
        try:
            destination.execute(
                projection_sql,
                [
                    first_specimen_id,
                    last_specimen_id,
                    receipt_id,
                    artifact_id,
                    str(SOURCE_SCHEMA_VERSION),
                    receipt_id,
                    artifact_id,
                    migration_recorded_at,
                ],
            )
            count_row = destination.execute(
                """
                SELECT count(*), count(terminal_descriptor_json_v9)
                FROM migration_specimen_projection
                """
            ).fetchone()
            if count_row is None:
                raise MigrationValidationError("specimen projection count query returned no row")
            batch_count = int(count_row[0])
            batch_descriptor_count = int(count_row[1])
            if batch_count != len(specimen_ids):
                raise MigrationValidationError(
                    "specimen projection keyset changed: "
                    f"expected {len(specimen_ids)} rows, found {batch_count}"
                )
            transaction_open = False
            try:
                destination.execute("BEGIN TRANSACTION")
                transaction_open = True
                destination.execute(
                    f"""
                    INSERT INTO specimens ({destination_column_sql})
                    SELECT {destination_column_sql}
                    FROM migration_specimen_projection
                    """
                )
                destination.execute(
                    """
                    INSERT INTO specimen_descriptors (
                        specimen_id, descriptor_version, terminal_version,
                        normalization_policy, fingerprint_resolution,
                        terminal_descriptor_json, trajectory_descriptor_json,
                        content_sha256, recorded_at
                    )
                    SELECT specimen_id, descriptor_version, terminal_version,
                           normalization_policy, fingerprint_resolution,
                           terminal_descriptor_json_v9, trajectory_descriptor_json_v9,
                           descriptor_content_sha256, descriptor_recorded_at
                    FROM migration_specimen_projection
                    WHERE terminal_descriptor_json_v9 IS NOT NULL
                    """
                )
                destination.execute("COMMIT")
                transaction_open = False
            except BaseException as error:
                if transaction_open:
                    _rollback_preserving_error(destination, error)
                raise
            copied += batch_count
            descriptor_count += batch_descriptor_count
        except BaseException as error:
            primary_error = error
            raise
        finally:
            _drop_specimen_projection(destination, primary_error=primary_error)
        after_specimen_id = last_specimen_id
    if source_guard is not None:
        source_guard()
    if copied != source_row_count:
        raise MigrationValidationError(
            f"specimen projection copied {copied} of {source_row_count} source rows"
        )
    return copied, descriptor_count


def _ensure_canonical_compendium_study(
    connection: DuckDBPyConnection,
    plan: MembershipNormalizationPlan,
) -> bool:
    if plan.source_study_count == 0:
        return False
    existing = connection.execute(
        """
        SELECT study_kind, run_id, label
        FROM studies
        WHERE study_id = ?
        """,
        [plan.canonical_study_id],
    ).fetchone()
    if existing is not None:
        if existing != ("discovery", None, CANONICAL_COMPENDIUM_STUDY_LABEL):
            raise MigrationValidationError(
                "canonical compendium study ID is occupied by an incompatible study"
            )
        return False
    register_study(
        connection,
        study_id=plan.canonical_study_id,
        study_kind="discovery",
        label=CANONICAL_COMPENDIUM_STUDY_LABEL,
        metadata_json={
            "projection": "compact-v10",
            "membershipNormalizationPolicy": "canonical-aggregate-compendium-v1",
            "legacyStudyIds": list(plan.source_study_ids),
        },
    )
    return True


def _copy_normalized_study_memberships(
    destination: DuckDBPyConnection,
    plan: MembershipNormalizationPlan,
) -> int:
    if plan.source_study_count == 0:
        destination.execute(
            """
            INSERT INTO main.study_specimens (study_id, specimen_id)
            SELECT study_id, specimen_id
            FROM legacy.main.study_specimens
            """
        )
        return plan.resulting_membership_count

    source_study_ids = list(plan.source_study_ids)
    destination.execute(
        """
        INSERT INTO main.study_specimens (study_id, specimen_id)
        SELECT study_id, specimen_id
        FROM legacy.main.study_specimens
        WHERE study_id NOT IN (SELECT unnest(?))
        """,
        [source_study_ids],
    )
    destination.execute(
        """
        CREATE TEMP TABLE migration_normalized_specimens AS
        SELECT specimen_id
        FROM legacy.main.specimens
        WHERE study_id IN (SELECT unnest(?))
        UNION
        SELECT specimen_id
        FROM legacy.main.study_specimens
        WHERE study_id IN (SELECT unnest(?))
        """,
        [source_study_ids, source_study_ids],
    )
    try:
        destination.execute(
            """
            UPDATE main.specimens
            SET study_id = ?
            WHERE specimen_id IN (
                SELECT specimen_id FROM migration_normalized_specimens
            )
            """,
            [plan.canonical_study_id],
        )
        destination.execute(
            """
            INSERT INTO main.study_specimens (study_id, specimen_id)
            SELECT ?, specimen_id
            FROM migration_normalized_specimens
            """,
            [plan.canonical_study_id],
        )
    finally:
        destination.execute("DROP TABLE IF EXISTS migration_normalized_specimens")
    return plan.resulting_membership_count


def _register_source_artifact(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    source_path: Path,
    source_sha256: str,
) -> str:
    artifact_id = stable_id(
        "artifact",
        "legacy_morphospace_warehouse_v8",
        source_path,
        source_sha256,
    )
    stat = source_path.stat()
    connection.execute(
        """
        INSERT INTO artifacts (
            artifact_id, study_id, artifact_kind, path, sha256, size_bytes,
            created_at, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSON))
        """,
        [
            artifact_id,
            study_id,
            "legacy_morphospace_warehouse_v8",
            str(source_path),
            source_sha256,
            stat.st_size,
            utc_now(),
            json_text(
                {
                    "contentHashPolicy": "sha256",
                    "migrationTargetSchemaVersion": SCHEMA_VERSION,
                    "readOnlySource": True,
                }
            ),
        ],
    )
    return artifact_id


def _register_invalidations(
    source: DuckDBPyConnection,
    destination: DuckDBPyConnection,
    *,
    omitted_row_counts: dict[str, int],
    preserved_feature_space_ids: set[str],
    quarantined_feature_space_ids: set[str],
) -> int:
    invalidations: list[tuple[str, str | None, str, str]] = [
        (
            "descriptor_axes",
            None,
            "1",
            "v8 descriptor-derived coordinates require torus-v2 regeneration",
        ),
        (
            "topology",
            None,
            "1",
            "v8 topology was computed from invalidated descriptor coordinates",
        ),
    ]
    for table_name, reason in STALE_DERIVED_TABLE_REASONS.items():
        if omitted_row_counts.get(table_name, 0) > 0:
            invalidations.append((table_name, None, "1", reason))
    if "feature_spaces" in _table_names(source):
        feature_rows = source.execute(
            """
            SELECT feature_space_id, version_label
            FROM feature_spaces
            ORDER BY feature_space_id
            """
        ).fetchall()
        for feature_space_id, version_label in feature_rows:
            identifier = str(feature_space_id)
            if identifier in quarantined_feature_space_ids:
                reason = (
                    "source-native feature coordinates contained nonfinite values; "
                    "those coordinates were quarantined as NULL"
                )
            elif identifier in preserved_feature_space_ids:
                continue
            else:
                reason = "derived feature coordinates were omitted for explicit regeneration"
            invalidations.append(
                (
                    "feature_space",
                    identifier,
                    str(version_label),
                    reason,
                )
            )

    for artifact_kind, feature_space_id, descriptor_version, reason in invalidations:
        payload = {
            "artifactKind": artifact_kind,
            "featureSpaceId": feature_space_id,
            "descriptorVersion": descriptor_version,
            "normalizationPolicy": LEGACY_NORMALIZATION_POLICY,
            "status": "invalid",
            "reason": reason,
            "metadata": {"omittedRowCounts": omitted_row_counts},
        }
        destination.execute(
            """
            INSERT INTO derived_artifact_state (
                artifact_key, artifact_kind, feature_space_id, descriptor_version,
                normalization_policy, status, reason, generation_hash, updated_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'invalid', ?, ?, ?, CAST(? AS JSON))
            """,
            [
                stable_id(
                    "derived-artifact",
                    artifact_kind,
                    feature_space_id or "",
                    descriptor_version,
                    LEGACY_NORMALIZATION_POLICY,
                ),
                artifact_kind,
                feature_space_id,
                descriptor_version,
                LEGACY_NORMALIZATION_POLICY,
                reason,
                row_sha256(payload),
                utc_now(),
                json_text(payload["metadata"]),
            ],
        )
    return len(invalidations)


def _deactivate_quarantined_feature_spaces(
    connection: DuckDBPyConnection,
    feature_space_ids: tuple[str, ...],
) -> None:
    if not feature_space_ids:
        return
    connection.execute(
        """
        UPDATE feature_spaces
        SET metadata_json = json_merge_patch(
            metadata_json,
            '{"activeCalibrationId":null}'::JSON
        )
        WHERE feature_space_id IN (SELECT unnest(?::VARCHAR[]))
        """,
        [list(feature_space_ids)],
    )


def _validate_destination_references(connection: DuckDBPyConnection) -> None:
    checks = {
        "artifacts -> studies": """
            SELECT count(*) FROM artifacts AS child
            LEFT JOIN studies AS parent USING (study_id)
            WHERE parent.study_id IS NULL
        """,
        "source_receipts -> studies/artifacts": """
            SELECT count(*) FROM source_receipts AS child
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            LEFT JOIN artifacts AS artifact ON artifact.artifact_id = child.artifact_id
            WHERE study.study_id IS NULL OR artifact.artifact_id IS NULL
               OR artifact.study_id <> child.study_id
        """,
        "raw_json_objects -> artifacts": """
            SELECT count(*) FROM raw_json_objects AS child
            LEFT JOIN artifacts AS parent USING (artifact_id)
            WHERE parent.artifact_id IS NULL
        """,
        "raw_jsonl_rows -> artifacts": """
            SELECT count(*) FROM raw_jsonl_rows AS child
            LEFT JOIN artifacts AS parent USING (artifact_id)
            WHERE parent.artifact_id IS NULL
        """,
        "specimen_descriptors -> specimens": """
            SELECT count(*) FROM specimen_descriptors AS child
            LEFT JOIN specimens AS parent USING (specimen_id)
            WHERE parent.specimen_id IS NULL
        """,
        "development_samples -> specimens": """
            SELECT count(*) FROM development_samples AS child
            LEFT JOIN specimens AS parent USING (specimen_id)
            WHERE parent.specimen_id IS NULL
        """,
        "specimen_axes -> specimens": """
            SELECT count(*) FROM specimen_axes AS child
            LEFT JOIN specimens AS parent USING (specimen_id)
            WHERE parent.specimen_id IS NULL
        """,
        "specimen_status -> specimens": """
            SELECT count(*) FROM specimen_status AS child
            LEFT JOIN specimens AS parent USING (specimen_id)
            WHERE parent.specimen_id IS NULL
        """,
        "perturbation_trials -> specimens/studies": """
            SELECT count(*) FROM perturbation_trials AS child
            LEFT JOIN specimens AS specimen ON specimen.specimen_id = child.specimen_id
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            WHERE specimen.specimen_id IS NULL OR study.study_id IS NULL
        """,
        "contexts -> studies": """
            SELECT count(*) FROM contexts AS child
            LEFT JOIN studies AS parent USING (study_id)
            WHERE parent.study_id IS NULL
        """,
        "control_programs -> studies": """
            SELECT count(*) FROM control_programs AS child
            LEFT JOIN studies AS parent USING (study_id)
            WHERE parent.study_id IS NULL
        """,
        "discovery_export_resolutions -> specimens/studies": """
            SELECT count(*) FROM discovery_export_resolutions AS child
            LEFT JOIN specimens AS specimen ON specimen.specimen_id = child.specimen_id
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            WHERE specimen.specimen_id IS NULL OR study.study_id IS NULL
        """,
        "context_trials -> specimens/studies/contexts/control_programs": """
            SELECT count(*) FROM context_trials AS child
            LEFT JOIN specimens AS specimen ON specimen.specimen_id = child.specimen_id
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            LEFT JOIN contexts AS context ON context.context_id = child.context_id
            LEFT JOIN control_programs AS control
              ON control.control_program_id = child.control_program_id
            WHERE specimen.specimen_id IS NULL OR study.study_id IS NULL
               OR context.context_id IS NULL
               OR (child.control_program_id IS NOT NULL
                   AND control.control_program_id IS NULL)
        """,
        "observations -> specimens/studies/sources/contexts": """
            SELECT count(*) FROM observations AS child
            LEFT JOIN specimens AS specimen ON specimen.specimen_id = child.specimen_id
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            LEFT JOIN morphospace_sources AS source ON source.source_id = child.source_id
            LEFT JOIN contexts AS context ON context.context_id = child.context_id
            WHERE study.study_id IS NULL OR source.source_id IS NULL
               OR (child.specimen_id IS NOT NULL AND specimen.specimen_id IS NULL)
               OR (child.context_id IS NOT NULL AND context.context_id IS NULL)
        """,
        "feature_axes -> feature_spaces": """
            SELECT count(*) FROM feature_axes AS child
            LEFT JOIN feature_spaces AS parent USING (feature_space_id)
            WHERE parent.feature_space_id IS NULL
        """,
        "feature_values -> observations/spaces/axes": """
            SELECT count(*) FROM feature_values AS child
            LEFT JOIN observations AS observation
              ON observation.observation_id = child.observation_id
            LEFT JOIN feature_spaces AS space
              ON space.feature_space_id = child.feature_space_id
            LEFT JOIN feature_axes AS axis
              ON axis.feature_space_id = child.feature_space_id
             AND axis.axis_id = child.axis_id
            WHERE observation.observation_id IS NULL OR space.feature_space_id IS NULL
               OR axis.axis_id IS NULL
        """,
        "feature_calibrations -> feature_spaces": """
            SELECT count(*) FROM feature_calibrations AS child
            LEFT JOIN feature_spaces AS parent USING (feature_space_id)
            WHERE parent.feature_space_id IS NULL
        """,
        "specimen_feature_vectors -> parents": """
            SELECT count(*) FROM specimen_feature_vectors AS child
            LEFT JOIN observations AS observation
              ON observation.observation_id = child.observation_id
            LEFT JOIN specimens AS specimen ON specimen.specimen_id = child.specimen_id
            LEFT JOIN studies AS study ON study.study_id = child.study_id
            LEFT JOIN feature_spaces AS space
              ON space.feature_space_id = child.feature_space_id
            LEFT JOIN feature_calibrations AS calibration
              ON calibration.calibration_id = child.calibration_id
             AND calibration.feature_space_id = child.feature_space_id
            WHERE observation.observation_id IS NULL OR specimen.specimen_id IS NULL
               OR study.study_id IS NULL OR space.feature_space_id IS NULL
               OR calibration.calibration_id IS NULL
        """,
    }
    for label, query in checks.items():
        orphan_count = _query_count(connection, query)
        if orphan_count:
            raise MigrationValidationError(
                f"destination referential integrity failed for {label}: "
                f"{orphan_count} orphaned rows"
            )


def _validate_destination(
    connection: DuckDBPyConnection,
    *,
    expected_row_counts: dict[str, int],
    expected_descriptor_count: int,
    expected_invalidation_count: int,
    membership_plan: MembershipNormalizationPlan,
) -> None:
    if read_schema_version(connection) != SCHEMA_VERSION:
        raise MigrationValidationError(f"destination schema is not v{SCHEMA_VERSION}")
    tables = set(_table_names(connection))
    if "raw_sqlite_rows" in tables:
        raise MigrationValidationError("destination contains raw_sqlite_rows")

    for table_name, expected_count in expected_row_counts.items():
        actual_count = _row_count(connection, table_name)
        if actual_count != expected_count:
            raise MigrationValidationError(
                f"{table_name}: expected {expected_count} rows, found {actual_count}"
            )
    for table_name in LEGACY_DERIVED_TABLES:
        if table_name in tables and _row_count(connection, table_name) != 0:
            raise MigrationValidationError(f"legacy derived table was not empty: {table_name}")
    if _row_count(connection, "specimen_descriptors") != expected_descriptor_count:
        raise MigrationValidationError("descriptor extraction count changed")
    if _row_count(connection, "derived_artifact_state") != expected_invalidation_count:
        raise MigrationValidationError("derived-artifact invalidation count changed")
    if _row_count(connection, "source_receipts") != 1:
        raise MigrationValidationError("migration must create exactly one source receipt")
    nonfinite_feature_values = _query_count(
        connection,
        """
        SELECT count(*)
        FROM feature_values
        WHERE (raw_value IS NOT NULL AND NOT isfinite(raw_value))
           OR (normalized_value IS NOT NULL AND NOT isfinite(normalized_value))
        """,
    )
    if nonfinite_feature_values:
        raise MigrationValidationError("destination contains active nonfinite feature values")

    orphan_membership = connection.execute(
        """
        SELECT COUNT(*)
        FROM study_specimens
        LEFT JOIN studies USING (study_id)
        LEFT JOIN specimens USING (specimen_id)
        WHERE studies.study_id IS NULL OR specimens.specimen_id IS NULL
        """
    ).fetchone()
    if orphan_membership is None or int(orphan_membership[0]) != 0:
        raise MigrationValidationError("study_specimens contains orphaned membership")
    orphan_specimens = connection.execute(
        """
        SELECT COUNT(*)
        FROM specimens
        LEFT JOIN studies USING (study_id)
        WHERE studies.study_id IS NULL
        """
    ).fetchone()
    if orphan_specimens is None or int(orphan_specimens[0]) != 0:
        raise MigrationValidationError("specimens contains an unknown study_id")
    _validate_destination_references(connection)

    if membership_plan.source_study_count == 0:
        return
    canonical_study = connection.execute(
        """
        SELECT study_kind, run_id, label
        FROM studies
        WHERE study_id = ?
        """,
        [membership_plan.canonical_study_id],
    ).fetchone()
    if canonical_study != ("discovery", None, CANONICAL_COMPENDIUM_STUDY_LABEL):
        raise MigrationValidationError("canonical compendium study contract changed")
    if membership_plan.retired_study_ids:
        retired_memberships = _query_count(
            connection,
            """
            SELECT count(*)
            FROM study_specimens
            WHERE study_id IN (SELECT unnest(?))
            """,
            [list(membership_plan.retired_study_ids)],
        )
        if retired_memberships:
            raise MigrationValidationError(
                "retired compendium studies retain active specimen memberships"
            )
    canonical_memberships = _query_count(
        connection,
        "SELECT count(*) FROM study_specimens WHERE study_id = ?",
        [membership_plan.canonical_study_id],
    )
    if canonical_memberships != membership_plan.normalized_specimen_count:
        raise MigrationValidationError(
            "canonical compendium membership normalization count changed"
        )
    inconsistent_canonical_specimens = _query_count(
        connection,
        """
        SELECT count(*)
        FROM (
            SELECT coalesce(members.specimen_id, assigned.specimen_id) AS specimen_id,
                   members.specimen_id AS member_id,
                   assigned.specimen_id AS assigned_id
            FROM (
                SELECT specimen_id
                FROM study_specimens
                WHERE study_id = ?
            ) AS members
            FULL OUTER JOIN (
                SELECT specimen_id
                FROM specimens
                WHERE study_id = ?
            ) AS assigned USING (specimen_id)
        ) AS canonical
        WHERE member_id IS NULL OR assigned_id IS NULL
        """,
        [membership_plan.canonical_study_id, membership_plan.canonical_study_id],
    )
    if inconsistent_canonical_specimens:
        raise MigrationValidationError(
            "canonical compendium membership and specimen study_id disagree"
        )


def _cleanup_build_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(f"{path}.wal").unlink(missing_ok=True)
    temporary_directory = Path(f"{path}.tmp")
    if temporary_directory.exists():
        shutil.rmtree(temporary_directory)


def _publish_no_clobber(build_path: Path, destination: Path) -> None:
    try:
        os.link(build_path, destination)
    except FileExistsError:
        raise FileExistsError(
            f"migration destination appeared during build: {destination}"
        ) from None
    build_path.unlink(missing_ok=True)


def build_warehouse_side_by_side(
    source_path: Path,
    destination_path: Path,
) -> MigrationResult:
    source = source_path.expanduser().resolve(strict=True)
    destination = destination_path.expanduser().resolve()
    if source == destination:
        raise WarehouseMigrationError("source and destination must be different paths")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_path = destination.with_name(f".{destination.name}.building-{uuid4().hex}")
    spill_root = Path(f"{build_path}.tmp")
    _assert_source_wal_free(source, stage="before opening")
    source_identity = _file_identity(source)

    source_connection: DuckDBPyConnection | None = None
    destination_connection: DuckDBPyConnection | None = None
    build_error: BaseException | None = None
    try:
        source_connection = duckdb.connect(str(source), read_only=True)
        _configure_migration_connection(
            source_connection,
            temp_directory=spill_root / "source",
            writable=False,
        )
        source_version = read_schema_version(source_connection)
        if source_version != SOURCE_SCHEMA_VERSION:
            raise WarehouseMigrationError(
                f"expected a v{SOURCE_SCHEMA_VERSION} source, found v{source_version}"
            )
        source_tables = _table_names(source_connection)
        source_table_set = set(source_tables)
        _validate_source_references(source_connection, source_table_set)
        orphan_context_plan = _build_orphan_context_omission_plan(
            source_connection,
            source_tables=source_table_set,
        )
        source_sha256 = _file_sha256(source)
        _assert_source_identity(source, source_identity, stage="while hashing")
        source_row_counts = {
            table_name: _row_count(source_connection, table_name) for table_name in source_tables
        }
        membership_plan = _build_membership_normalization_plan(
            source_connection,
            source_tables=source_table_set,
        )

        destination_connection = duckdb.connect(str(build_path))
        _configure_migration_connection(
            destination_connection,
            temp_directory=spill_root / "destination",
            writable=True,
        )
        create_schema(destination_connection)
        destination_tables = set(_table_names(destination_connection))
        table_classification = _classify_source_tables(source_tables, destination_tables)
        _validate_copy_columns(
            source_connection,
            destination_connection,
            table_classification,
        )
        destination_connection.execute(
            f"ATTACH {_quote_literal(str(source))} AS legacy (READ_ONLY)"
        )
        try:
            copied_row_counts: dict[str, int] = {}
            for table_name in table_classification["directCopy"]:
                if table_name == "contexts":
                    copied_row_counts[table_name] = _copy_contexts(
                        source_connection,
                        destination_connection,
                        source_row_count=source_row_counts[table_name],
                        omission_plan=orphan_context_plan,
                    )
                else:
                    copied_row_counts[table_name] = _copy_intersecting_table(
                        source_connection,
                        destination_connection,
                        table_name,
                        source_row_count=source_row_counts[table_name],
                    )
            (
                copied_source_layer,
                omitted_derived_observations,
                preserved_feature_space_ids,
                nonfinite_feature_quarantine,
            ) = _copy_source_observation_layer(
                source_connection,
                destination_connection,
            )
            copied_row_counts.update(copied_source_layer)

            migration_study_id = stable_id("study", "warehouse_migration", source, source_sha256)
            register_study(
                destination_connection,
                study_id=migration_study_id,
                study_kind="warehouse_migration",
                label=f"v8 to v{SCHEMA_VERSION} side-by-side migration",
                config_hash=source_sha256,
                metadata_json={
                    "sourcePath": str(source),
                    "sourceSchemaVersion": SOURCE_SCHEMA_VERSION,
                    "targetSchemaVersion": SCHEMA_VERSION,
                    "migrationMemoryLimit": MIGRATION_MEMORY_LIMIT,
                    "migrationCheckpointThreshold": MIGRATION_CHECKPOINT_THRESHOLD,
                    "specimenProjectionMaxRows": SPECIMEN_PROJECTION_BATCH_SIZE,
                    "specimenProjectionMaxSourceBytes": (SPECIMEN_PROJECTION_BATCH_SOURCE_BYTES),
                    "specimenProjectionSingleRowMaxSourceBytes": (
                        SPECIMEN_PROJECTION_SINGLE_ROW_MAX_SOURCE_BYTES
                    ),
                },
            )
            canonical_study_created = _ensure_canonical_compendium_study(
                destination_connection,
                membership_plan,
            )
            artifact_id = _register_source_artifact(
                destination_connection,
                study_id=migration_study_id,
                source_path=source,
                source_sha256=source_sha256,
            )
            receipt_id = register_source_receipt(
                destination_connection,
                study_id=migration_study_id,
                artifact_id=artifact_id,
                source_kind="legacy_morphospace_warehouse",
                source_schema_version=str(SOURCE_SCHEMA_VERSION),
                source_tables=source_tables,
                source_row_counts=source_row_counts,
                metadata_json={
                    "migrationTargetSchemaVersion": SCHEMA_VERSION,
                    "sourceTableClassification": table_classification,
                    "selectivelyCopiedObservationKinds": sorted(SOURCE_OBSERVATION_KINDS),
                    "membershipNormalization": membership_plan.metadata(),
                    "nonfiniteSourceFeatureQuarantine": (nonfinite_feature_quarantine.metadata()),
                    "orphanContextOmission": orphan_context_plan.metadata(),
                    "sourceOpenedReadOnly": True,
                    "sourceIdentity": {
                        "device": source_identity.device,
                        "inode": source_identity.inode,
                        "size": source_identity.size,
                        "modifiedNs": source_identity.modified_ns,
                        "changedNs": source_identity.changed_ns,
                    },
                },
            )
            copied_specimens, descriptor_count = _copy_specimens(
                source_connection,
                destination_connection,
                receipt_id=receipt_id,
                artifact_id=artifact_id,
                source_guard=lambda: _assert_source_identity(
                    source,
                    source_identity,
                    stage="during specimen projection",
                ),
            )
            copied_row_counts["specimens"] = copied_specimens
            copied_row_counts["study_specimens"] = _copy_normalized_study_memberships(
                destination_connection,
                membership_plan,
            )

            omitted_row_counts = {
                table_name: source_row_counts[table_name]
                for table_name in sorted(LEGACY_DERIVED_TABLES & set(source_tables))
            }
            if omitted_derived_observations > 0:
                omitted_row_counts["observations"] = omitted_derived_observations
            _deactivate_quarantined_feature_spaces(
                destination_connection,
                nonfinite_feature_quarantine.feature_space_ids,
            )
            invalidation_count = _register_invalidations(
                source_connection,
                destination_connection,
                omitted_row_counts=omitted_row_counts,
                preserved_feature_space_ids=preserved_feature_space_ids,
                quarantined_feature_space_ids=set(nonfinite_feature_quarantine.feature_space_ids),
            )
            expected_row_counts = dict(copied_row_counts)
            expected_row_counts["studies"] = (
                source_row_counts.get("studies", 0) + 1 + int(canonical_study_created)
            )
            expected_row_counts["artifacts"] = source_row_counts.get("artifacts", 0) + 1
            _validate_destination(
                destination_connection,
                expected_row_counts=expected_row_counts,
                expected_descriptor_count=descriptor_count,
                expected_invalidation_count=invalidation_count,
                membership_plan=membership_plan,
            )
        except BaseException as error:
            error.add_note(
                "warehouse migration failed while constructing the unpublished destination"
            )
            raise

        destination_connection.execute("DETACH legacy")
        destination_connection.execute("FORCE CHECKPOINT")
        destination_connection.close()
        destination_connection = None
        source_connection.close()
        source_connection = None

        verification_connection = duckdb.connect(str(build_path), read_only=True)
        verification_error: BaseException | None = None
        try:
            _validate_destination(
                verification_connection,
                expected_row_counts=expected_row_counts,
                expected_descriptor_count=descriptor_count,
                expected_invalidation_count=invalidation_count,
                membership_plan=membership_plan,
            )
        except BaseException as error:
            verification_error = error
            raise
        finally:
            try:
                verification_connection.close()
            except BaseException as error:
                if verification_error is None:
                    raise
                _note_cleanup_failure(
                    verification_error,
                    operation="closing destination verification",
                    cleanup_error=error,
                )

        _assert_source_identity(source, source_identity, stage="during migration")

        _publish_no_clobber(build_path, destination)
        return MigrationResult(
            source_path=source,
            destination_path=destination,
            source_sha256=source_sha256,
            receipt_id=receipt_id,
            copied_row_counts=copied_row_counts,
            descriptor_count=descriptor_count,
            invalidation_count=invalidation_count,
            membership_normalization=membership_plan.metadata(),
            nonfinite_feature_quarantine=nonfinite_feature_quarantine.metadata(),
            orphan_context_omission=orphan_context_plan.metadata(),
        )
    except BaseException as error:
        build_error = error
        raise
    finally:
        cleanup_error = build_error
        if destination_connection is not None:
            try:
                destination_connection.close()
            except BaseException as error:
                cleanup_error = _preserve_cleanup_failure(
                    cleanup_error,
                    operation="closing the unpublished destination",
                    cleanup_error=error,
                )
        if source_connection is not None:
            try:
                source_connection.close()
            except BaseException as error:
                cleanup_error = _preserve_cleanup_failure(
                    cleanup_error,
                    operation="closing the read-only source",
                    cleanup_error=error,
                )
        try:
            _cleanup_build_files(build_path)
        except BaseException as error:
            cleanup_error = _preserve_cleanup_failure(
                cleanup_error,
                operation="removing the unpublished destination",
                cleanup_error=error,
            )
        if build_error is None and cleanup_error is not None:
            raise cleanup_error


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
