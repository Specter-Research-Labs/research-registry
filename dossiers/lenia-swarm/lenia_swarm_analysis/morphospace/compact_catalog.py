from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from duckdb import ConstraintException, DuckDBPyConnection
from duckdb import Error as DuckDBError

DOCUMENT_TABLE = "json_documents"
DOCUMENT_TEMPLATE_TABLE = "json_document_templates"
DOCUMENT_VALUES_VIEW = "json_document_values"
TABLE_METADATA = "compaction_tables"
COLUMN_METADATA = "compaction_columns"
COMPACTION_MANIFEST_TABLE = "compaction_manifest"
COMPACTION_PLAN_TABLE = "compaction_plan"
COMPACTION_CHECKPOINT_TABLE = "compaction_checkpoints"
COMPACTION_FORMAT = "lenia-catalog-compaction-v1"
COMPACTION_PLAN_FORMAT = "lenia-catalog-compaction-plan-v1"
COMPACTION_CHECKPOINT_FORMAT = "lenia-catalog-compaction-table-checkpoint-v1"
RECEIPT_CANONICALIZATION = "json-sort-keys-compact-ascii-v1"
ROW_DIGEST_VERSION = "sha256-duckdb-json-content-hash-struct-v2"
DOCUMENT_VERIFICATION_BATCH_SIZE = 128
CANONICAL_WRITABLE_TABLES: Final[tuple[str, ...]] = (
    "runs",
    "results",
    "creatures",
    "exports",
    "specimens",
)

LOGGER = logging.getLogger(__name__)


class CatalogCompactionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: str
    nullable: bool
    default: str | None
    ordinal: int
    payload: bool
    backing_column: str | None


@dataclass(frozen=True)
class TableCompaction:
    table_name: str
    backing_table: str
    browse_view: str
    row_count: int
    payload_columns: tuple[str, ...]
    pre_compaction_sha256: str
    reconstruction_sha256: str


@dataclass(frozen=True)
class ManifestFactoring:
    factored_documents: int
    original_bytes: int
    referenced_bytes: int
    residual_bytes: int


@dataclass(frozen=True)
class CatalogCompaction:
    schema_name: str
    documents_before: int
    documents_after: int
    tables: tuple[TableCompaction, ...]
    manifest_factoring: ManifestFactoring
    receipt_sha256: str


@dataclass(frozen=True)
class CatalogCompactionVerification:
    schema_name: str
    receipt_sha256: str
    document_count: int
    table_count: int
    row_count: int


@dataclass(frozen=True)
class _CompactionPlan:
    receipt_sha256: str
    parent_consolidation_receipt_sha256: str | None
    required_writable_tables: tuple[str, ...]
    factor_specimen_manifests: bool
    tables: tuple[tuple[str, tuple[ColumnSpec, ...]], ...]


@dataclass(frozen=True)
class _TableCheckpoint:
    receipt_sha256: str
    table: TableCompaction
    columns: tuple[ColumnSpec, ...]


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _qualified(schema_name: str, object_name: str) -> str:
    return f"{_quote_identifier(schema_name)}.{_quote_identifier(object_name)}"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_query_plan(connection: DuckDBPyConnection, query: str) -> str:
    try:
        row = connection.execute(f"EXPLAIN (FORMAT JSON) {query}").fetchone()
    except DuckDBError as error:
        raise CatalogCompactionError("could not bind a required catalog view") from error
    if row is None or row[1] is None:
        raise CatalogCompactionError("catalog view plan query returned no row")
    try:
        raw = json.loads(str(row[1]))
    except json.JSONDecodeError as error:
        raise CatalogCompactionError("catalog view plan is invalid JSON") from error

    def scrub(value: object) -> object:
        if isinstance(value, dict):
            return {
                str(key): scrub(item)
                for key, item in value.items()
                if key not in {"CTE Index", "Table Index"}
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return _canonical_json(scrub(raw))


def _query_layout(connection: DuckDBPyConnection, query: str) -> tuple[tuple[object, ...], ...]:
    try:
        return tuple(connection.execute(f"DESCRIBE {query}").fetchall())
    except DuckDBError as error:
        raise CatalogCompactionError("could not describe a required catalog view") from error


def _scalar_int(connection: DuckDBPyConnection, query: str, parameters: list[object]) -> int:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise CatalogCompactionError("count query returned no row")
    return int(row[0])


def _object_exists(connection: DuckDBPyConnection, *, schema_name: str, object_name: str) -> bool:
    return (
        _scalar_int(
            connection,
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema_name, object_name],
        )
        != 0
    )


def _source_columns(
    connection: DuckDBPyConnection, *, schema_name: str, table_name: str
) -> tuple[ColumnSpec, ...]:
    rows = connection.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema_name, table_name],
    ).fetchall()
    columns: list[ColumnSpec] = []
    for name, data_type, is_nullable, default, ordinal in rows:
        column_name = str(name)
        type_name = str(data_type)
        is_payload = column_name.lower().endswith("_json") and type_name.upper() in {
            "JSON",
            "VARCHAR",
        }
        columns.append(
            ColumnSpec(
                name=column_name,
                data_type=type_name,
                nullable=str(is_nullable).upper() == "YES",
                default=None if default is None else str(default),
                ordinal=int(ordinal),
                payload=is_payload,
                backing_column=f"__catalog_document_{int(ordinal)}" if is_payload else None,
            )
        )
    return tuple(columns)


def _discover_tables(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    required_writable_tables: Sequence[str],
) -> list[tuple[str, tuple[ColumnSpec, ...]]]:
    support_tables = {
        DOCUMENT_TABLE,
        DOCUMENT_TEMPLATE_TABLE,
        TABLE_METADATA,
        COLUMN_METADATA,
        COMPACTION_MANIFEST_TABLE,
        COMPACTION_PLAN_TABLE,
        COMPACTION_CHECKPOINT_TABLE,
    }
    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = ? AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        [schema_name],
    ).fetchall()
    discovered: list[tuple[str, tuple[ColumnSpec, ...]]] = []
    for (raw_name,) in rows:
        table_name = str(raw_name)
        if table_name in support_tables or table_name.startswith("__compact_"):
            continue
        columns = _source_columns(connection, schema_name=schema_name, table_name=table_name)
        if any(column.payload for column in columns) or table_name in required_writable_tables:
            discovered.append((table_name, columns))

    priority = {name: index for index, name in enumerate(required_writable_tables)}
    discovered.sort(key=lambda item: (priority.get(item[0], len(priority)), item[0]))
    return discovered


def _normalize_required_tables(required_writable_tables: Sequence[str]) -> tuple[str, ...]:
    required = tuple(str(name) for name in required_writable_tables)
    if not required or len(required) == len(set(required)):
        return required
    raise CatalogCompactionError("required writable catalog tables contain duplicates")


def _require_writable_tables(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    required_writable_tables: Sequence[str],
    compacted_tables: Sequence[str] | None = None,
) -> None:
    required = set(required_writable_tables)
    if not required:
        return
    if compacted_tables is None:
        rows = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = ? AND table_type = 'BASE TABLE'
            """,
            [schema_name],
        ).fetchall()
        available = {str(row[0]) for row in rows}
        missing = sorted(required - available)
        message = "required writable catalog source tables are missing"
    else:
        missing = sorted(required - set(compacted_tables))
        message = "required writable catalog tables are not compacted"
    if missing:
        raise CatalogCompactionError(f"{message}: {', '.join(missing)}")


def _ensure_support_tables(connection: DuckDBPyConnection, *, schema_name: str) -> None:
    schema = _quote_identifier(schema_name)
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, DOCUMENT_TABLE)} (
            document_id BIGINT PRIMARY KEY,
            content_sha256 VARCHAR NOT NULL UNIQUE,
            byte_length BIGINT NOT NULL,
            document_text VARCHAR
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)} (
            document_id BIGINT PRIMARY KEY,
            template_kind VARCHAR NOT NULL,
            prefix_text VARCHAR NOT NULL,
            first_document_id BIGINT NOT NULL,
            between_first_second_text VARCHAR NOT NULL,
            second_document_id BIGINT NOT NULL,
            between_second_third_text VARCHAR,
            third_document_id BIGINT,
            suffix_text VARCHAR NOT NULL,
            CHECK (
                (third_document_id IS NULL AND between_second_third_text IS NULL)
                OR
                (third_document_id IS NOT NULL AND between_second_third_text IS NOT NULL)
            )
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, TABLE_METADATA)} (
            source_schema VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,
            backing_table VARCHAR NOT NULL,
            browse_view VARCHAR NOT NULL,
            row_count BIGINT NOT NULL,
            source_column_count INTEGER NOT NULL,
            payload_column_count INTEGER NOT NULL,
            pre_compaction_sha256 VARCHAR NOT NULL,
            reconstruction_sha256 VARCHAR NOT NULL,
            row_digest_version VARCHAR NOT NULL,
            compacted_at TIMESTAMP NOT NULL,
            PRIMARY KEY (source_schema, source_table)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, COLUMN_METADATA)} (
            source_schema VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,
            ordinal_position INTEGER NOT NULL,
            column_name VARCHAR NOT NULL,
            data_type VARCHAR NOT NULL,
            is_nullable BOOLEAN NOT NULL,
            column_default VARCHAR,
            is_payload BOOLEAN NOT NULL,
            backing_column VARCHAR,
            PRIMARY KEY (source_schema, source_table, ordinal_position)
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, COMPACTION_MANIFEST_TABLE)} (
            receipt_sha256 VARCHAR PRIMARY KEY,
            manifest_json VARCHAR NOT NULL
        )
        """
    )
    _create_document_values_view(connection, schema_name=schema_name)


def _ensure_progress_tables(connection: DuckDBPyConnection, *, schema_name: str) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, COMPACTION_PLAN_TABLE)} (
            singleton BOOLEAN PRIMARY KEY CHECK (singleton),
            plan_sha256 VARCHAR NOT NULL UNIQUE,
            plan_json VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(schema_name, COMPACTION_CHECKPOINT_TABLE)} (
            source_schema VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,
            plan_sha256 VARCHAR NOT NULL,
            receipt_sha256 VARCHAR NOT NULL UNIQUE,
            receipt_json VARCHAR NOT NULL,
            PRIMARY KEY (source_schema, source_table)
        )
        """
    )


def _document_values_query(*, schema_name: str) -> str:
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    templates = _qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)
    return f"""
        SELECT
            document.document_id,
            document.content_sha256,
            document.byte_length,
            COALESCE(
                document.document_text,
                template.prefix_text
                    || first_document.document_text
                    || template.between_first_second_text
                    || second_document.document_text
                    || CASE
                        WHEN template.third_document_id IS NULL THEN ''
                        ELSE template.between_second_third_text
                            || third_document.document_text
                    END
                    || template.suffix_text
            ) AS document_text
        FROM {documents} AS document
        LEFT JOIN {templates} AS template
          ON template.document_id = document.document_id
        LEFT JOIN {documents} AS first_document
          ON first_document.document_id = template.first_document_id
        LEFT JOIN {documents} AS second_document
          ON second_document.document_id = template.second_document_id
        LEFT JOIN {documents} AS third_document
          ON third_document.document_id = template.third_document_id
    """


def _create_document_values_view(connection: DuckDBPyConnection, *, schema_name: str) -> None:
    values_view = _qualified(schema_name, DOCUMENT_VALUES_VIEW)
    connection.execute(
        f"CREATE OR REPLACE VIEW {values_view} AS "
        + _document_values_query(schema_name=schema_name)
    )


def _validate_source_rowids(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    columns: tuple[ColumnSpec, ...],
) -> int:
    if "_source_rowid" not in {column.name for column in columns}:
        raise CatalogCompactionError(
            f"{schema_name}.{table_name} must contain _source_rowid before compaction"
        )
    source = _qualified(schema_name, table_name)
    row = connection.execute(
        f"""
        SELECT COUNT(*), COUNT("_source_rowid"), COUNT(DISTINCT "_source_rowid")
        FROM {source}
        """
    ).fetchone()
    if row is None:
        raise CatalogCompactionError(f"could not count {schema_name}.{table_name}")
    row_count, nonnull_count, distinct_count = (int(value) for value in row)
    if row_count != nonnull_count or row_count != distinct_count:
        raise CatalogCompactionError(
            f"{schema_name}.{table_name}._source_rowid must be non-null and unique"
        )
    return row_count


def _intern_payload_column(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    column_name: str,
) -> None:
    source = _qualified(schema_name, table_name)
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    column = _quote_identifier(column_name)
    try:
        connection.execute(
            _intern_payload_insert_query(
                source=source,
                documents=documents,
                column=column,
            )
        )
    except ConstraintException as error:
        raise CatalogCompactionError(
            f"SHA-256 collision while interning {schema_name}.{table_name}.{column_name}"
        ) from error


def _intern_payload_insert_query(*, source: str, documents: str, column: str) -> str:
    return f"""
        INSERT INTO {documents} (document_id, content_sha256, byte_length, document_text)
        WITH candidates AS MATERIALIZED (
            SELECT DISTINCT
                sha256(CAST({column} AS VARCHAR)) AS content_sha256,
                octet_length(encode(CAST({column} AS VARCHAR))) AS byte_length,
                CAST({column} AS VARCHAR) AS document_text
            FROM {source}
            WHERE {column} IS NOT NULL
        ),
        numbered AS (
            SELECT
                (SELECT COALESCE(MAX(document_id), 0) FROM {documents})
                    + row_number() OVER (
                        ORDER BY content_sha256, byte_length, document_text
                    ) AS document_id,
                content_sha256,
                byte_length,
                document_text
            FROM candidates AS candidate
            WHERE NOT EXISTS (
                SELECT 1
                FROM {documents} AS existing
                WHERE existing.content_sha256 = candidate.content_sha256
                  AND existing.byte_length = candidate.byte_length
                  AND existing.document_text = candidate.document_text
            )
        )
        SELECT document_id, content_sha256, byte_length, document_text
        FROM numbered
    """


def _detail_query(
    *,
    schema_name: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
) -> str:
    backing = _qualified(schema_name, backing_table)
    document_values = _qualified(schema_name, DOCUMENT_VALUES_VIEW)
    select_items: list[str] = []
    joins: list[str] = []
    for index, column in enumerate(columns):
        quoted_name = _quote_identifier(column.name)
        if not column.payload:
            select_items.append(f"backing.{quoted_name} AS {quoted_name}")
            continue
        if column.backing_column is None:
            raise AssertionError("payload column has no backing column")
        alias = f"document_{index}"
        reconstructed = f"{alias}.document_text"
        if column.data_type.upper() == "JSON":
            reconstructed = f"CAST({reconstructed} AS JSON)"
        select_items.append(f"{reconstructed} AS {quoted_name}")
        joins.append(
            f"LEFT JOIN {document_values} AS {alias} "
            f"ON {alias}.document_id = "
            f"backing.{_quote_identifier(column.backing_column)}"
        )
    return f"SELECT {', '.join(select_items)} FROM {backing} AS backing {' '.join(joins)}"


def _create_backing_table(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
) -> None:
    source = _qualified(schema_name, table_name)
    backing = _qualified(schema_name, backing_table)
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    select_items: list[str] = []
    joins: list[str] = []
    for index, column in enumerate(columns):
        quoted_name = _quote_identifier(column.name)
        if not column.payload:
            select_items.append(f"source.{quoted_name} AS {quoted_name}")
            continue
        if column.backing_column is None:
            raise AssertionError("payload column has no backing column")
        alias = f"document_{index}"
        payload_text = f"CAST(source.{quoted_name} AS VARCHAR)"
        select_items.append(f"{alias}.document_id AS {_quote_identifier(column.backing_column)}")
        joins.append(
            f"LEFT JOIN {documents} AS {alias} ON {alias}.content_sha256 = sha256({payload_text})"
        )
    connection.execute(
        f"CREATE TABLE {backing} AS "
        f"SELECT {', '.join(select_items)} FROM {source} AS source {' '.join(joins)}"
    )
    index_name = f"__catalog_{schema_name}_{table_name}_source_rowid"
    connection.execute(
        f'CREATE UNIQUE INDEX {_quote_identifier(index_name)} ON {backing} ("_source_rowid")'
    )


def _source_row_digest_expression(alias: str, columns: tuple[ColumnSpec, ...]) -> str:
    fields: list[str] = []
    for column in columns:
        quoted_name = _quote_identifier(column.name)
        value = f"{alias}.{quoted_name}"
        if column.payload:
            value = f"sha256(CAST({value} AS VARCHAR))"
        fields.append(f"{quoted_name} := {value}")
    return f"sha256(CAST(to_json(struct_pack({', '.join(fields)})) AS VARCHAR))"


def _backing_digest_query(
    *,
    schema_name: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
) -> str:
    backing = _qualified(schema_name, backing_table)
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    fields: list[str] = []
    joins: list[str] = []
    for index, column in enumerate(columns):
        quoted_name = _quote_identifier(column.name)
        if not column.payload:
            fields.append(f"{quoted_name} := backing.{quoted_name}")
            continue
        if column.backing_column is None:
            raise AssertionError("payload column has no backing column")
        alias = f"digest_document_{index}"
        fields.append(f"{quoted_name} := {alias}.content_sha256")
        joins.append(
            f"LEFT JOIN {documents} AS {alias} "
            f"ON {alias}.document_id = "
            f"backing.{_quote_identifier(column.backing_column)}"
        )
    row_digest = f"sha256(CAST(to_json(struct_pack({', '.join(fields)})) AS VARCHAR))"
    return (
        f'SELECT backing."_source_rowid", {row_digest} AS row_digest '
        f"FROM {backing} AS backing {' '.join(joins)}"
    )


def _digest_query(connection: DuckDBPyConnection, *, query: str) -> tuple[int, str]:
    row = connection.execute(
        f"""
        SELECT COUNT(*),
               sha256(COALESCE(string_agg(row_digest, '' ORDER BY "_source_rowid"), ''))
        FROM ({query}) AS digest_rows
        """
    ).fetchone()
    if row is None or row[1] is None:
        raise CatalogCompactionError("semantic digest query returned no row")
    return int(row[0]), str(row[1])


def _verify_reconstruction(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
    expected_rows: int,
) -> tuple[str, str]:
    source = _qualified(schema_name, table_name)
    backing_rows = _validate_source_rowids(
        connection,
        schema_name=schema_name,
        table_name=backing_table,
        columns=columns,
    )
    if backing_rows != expected_rows:
        raise CatalogCompactionError(
            f"{schema_name}.{table_name} compacted to {backing_rows} rows; expected {expected_rows}"
        )
    source_row_digest = _source_row_digest_expression("source", columns)
    source_query = (
        f'SELECT source."_source_rowid", {source_row_digest} AS row_digest FROM {source} AS source'
    )
    backing_query = _backing_digest_query(
        schema_name=schema_name,
        backing_table=backing_table,
        columns=columns,
    )
    row = connection.execute(
        f"""
        WITH source_rows AS ({source_query}),
        backing_rows AS ({backing_query}),
        compared AS (
            SELECT
                COALESCE(source_rows."_source_rowid", backing_rows."_source_rowid")
                    AS "_source_rowid",
                source_rows.row_digest AS source_digest,
                backing_rows.row_digest AS backing_digest
            FROM source_rows
            FULL OUTER JOIN backing_rows USING ("_source_rowid")
        )
        SELECT
            COUNT(source_digest),
            COUNT(backing_digest),
            COUNT(*) FILTER (WHERE source_digest IS DISTINCT FROM backing_digest),
            sha256(COALESCE(
                string_agg(source_digest, '' ORDER BY "_source_rowid"),
                ''
            ))
        FROM compared
        """
    ).fetchone()
    if row is None:
        raise CatalogCompactionError(
            f"could not verify semantic digest for {schema_name}.{table_name}"
        )
    source_rows, compacted_rows, mismatched_digests = (int(value) for value in row[:3])
    source_digest = str(row[3])
    if source_rows != expected_rows or compacted_rows != expected_rows:
        raise CatalogCompactionError(
            f"{schema_name}.{table_name} semantic digest row counts changed"
        )
    if mismatched_digests:
        raise CatalogCompactionError(
            f"{schema_name}.{table_name} has {mismatched_digests} reconstructed row digest mismatches"
        )
    return source_digest, source_digest


def _browse_query(
    *,
    schema_name: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
) -> str:
    non_payload = [column for column in columns if not column.payload]
    payload = [column for column in columns if column.payload]
    select_items = [
        f"backing.{_quote_identifier(column.name)} AS {_quote_identifier(column.name)}"
        for column in non_payload
    ]
    if payload:
        document_fields = ", ".join(
            f"{_quote_identifier(column.name)} := "
            f"backing.{_quote_identifier(str(column.backing_column))}"
            for column in payload
        )
        select_items.append(f"struct_pack({document_fields}) AS _json_document_ids")
    return (
        f"SELECT {', '.join(select_items)} FROM {_qualified(schema_name, backing_table)} AS backing"
    )


def _create_browse_view(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    browse_view: str,
    backing_table: str,
    columns: tuple[ColumnSpec, ...],
) -> None:
    connection.execute(
        f"CREATE VIEW {_qualified(schema_name, browse_view)} AS "
        + _browse_query(
            schema_name=schema_name,
            backing_table=backing_table,
            columns=columns,
        )
    )


def _record_metadata(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    backing_table: str,
    browse_view: str,
    columns: tuple[ColumnSpec, ...],
    row_count: int,
    pre_compaction_sha256: str,
    reconstruction_sha256: str,
) -> None:
    connection.execute(
        f"""
        INSERT INTO {_qualified(schema_name, TABLE_METADATA)}
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        [
            schema_name,
            table_name,
            backing_table,
            browse_view,
            row_count,
            len(columns),
            sum(column.payload for column in columns),
            pre_compaction_sha256,
            reconstruction_sha256,
            ROW_DIGEST_VERSION,
        ],
    )
    connection.executemany(
        f"""
        INSERT INTO {_qualified(schema_name, COLUMN_METADATA)}
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                schema_name,
                table_name,
                column.ordinal,
                column.name,
                column.data_type,
                column.nullable,
                column.default,
                column.payload,
                column.backing_column,
            )
            for column in columns
        ],
    )


def _empty_manifest_factoring() -> ManifestFactoring:
    return ManifestFactoring(
        factored_documents=0,
        original_bytes=0,
        referenced_bytes=0,
        residual_bytes=0,
    )


def _factor_specimen_manifests(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    columns: tuple[ColumnSpec, ...] | None,
) -> ManifestFactoring:
    if columns is None:
        return _empty_manifest_factoring()
    by_name = {column.name: column for column in columns}
    required_names = {
        "specimen_manifest_json",
        "genotype_descriptor_json",
        "terminal_descriptor_json",
    }
    if not required_names <= by_name.keys():
        return _empty_manifest_factoring()
    required_columns = [by_name[name] for name in sorted(required_names)]
    if any(not column.payload or column.backing_column is None for column in required_columns):
        return _empty_manifest_factoring()

    trajectory = by_name.get("trajectory_descriptor_json")
    has_trajectory = bool(
        trajectory is not None and trajectory.payload and trajectory.backing_column is not None
    )
    manifest = by_name["specimen_manifest_json"]
    genotype = by_name["genotype_descriptor_json"]
    terminal = by_name["terminal_descriptor_json"]
    assert manifest.backing_column is not None
    assert genotype.backing_column is not None
    assert terminal.backing_column is not None

    backing = _qualified(schema_name, "__compact_specimens")
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    templates = _qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)
    values_view = _qualified(schema_name, DOCUMENT_VALUES_VIEW)
    candidates = "temp.__catalog_manifest_factor_candidates"
    trajectory_reference = (
        f"backing.{_quote_identifier(str(trajectory.backing_column))}"
        if has_trajectory and trajectory is not None
        else "CAST(NULL AS BIGINT)"
    )

    connection.execute(
        f"""
        CREATE TEMP TABLE {candidates} AS
        WITH raw_references AS (
            SELECT DISTINCT
                backing.{_quote_identifier(manifest.backing_column)} AS manifest_document_id,
                backing.{_quote_identifier(genotype.backing_column)} AS genotype_document_id,
                backing.{_quote_identifier(terminal.backing_column)} AS terminal_document_id,
                {trajectory_reference} AS trajectory_document_id
            FROM {backing} AS backing
            WHERE backing.{_quote_identifier(manifest.backing_column)} IS NOT NULL
              AND backing.{_quote_identifier(genotype.backing_column)} IS NOT NULL
              AND backing.{_quote_identifier(terminal.backing_column)} IS NOT NULL
        ),
        unambiguous_references AS (
            SELECT *
            FROM raw_references
            QUALIFY COUNT(*) OVER (PARTITION BY manifest_document_id) = 1
        ),
        texts AS (
            SELECT
                reference.*,
                manifest_document.byte_length AS original_bytes,
                manifest_document.document_text AS manifest_text,
                genotype_document.document_text AS genotype_text,
                terminal_document.document_text AS terminal_text,
                trajectory_document.document_text AS trajectory_text
            FROM unambiguous_references AS reference
            JOIN {documents} AS manifest_document
              ON manifest_document.document_id = reference.manifest_document_id
             AND manifest_document.document_text IS NOT NULL
            JOIN {documents} AS genotype_document
              ON genotype_document.document_id = reference.genotype_document_id
             AND genotype_document.document_text IS NOT NULL
            JOIN {documents} AS terminal_document
              ON terminal_document.document_id = reference.terminal_document_id
             AND terminal_document.document_text IS NOT NULL
            LEFT JOIN {documents} AS trajectory_document
              ON trajectory_document.document_id = reference.trajectory_document_id
             AND trajectory_document.document_text IS NOT NULL
        ),
        located AS (
            SELECT
                *,
                strpos(manifest_text, genotype_text) AS genotype_position,
                strpos(manifest_text, terminal_text) AS terminal_position,
                strpos(manifest_text, trajectory_text) AS trajectory_position,
                length(genotype_text) AS genotype_length,
                length(terminal_text) AS terminal_length,
                length(trajectory_text) AS trajectory_length
            FROM texts
        ),
        eligible AS (
            SELECT
                *,
                trajectory_text IS NOT NULL
                    AND trajectory_length > 4
                    AND trajectory_position >= terminal_position + terminal_length
                    AND strpos(
                        substr(manifest_text, trajectory_position + trajectory_length),
                        trajectory_text
                    ) = 0 AS factor_trajectory
            FROM located
            WHERE genotype_position > 0
              AND terminal_position >= genotype_position + genotype_length
              AND strpos(
                    substr(manifest_text, genotype_position + genotype_length),
                    genotype_text
                  ) = 0
              AND strpos(
                    substr(manifest_text, terminal_position + terminal_length),
                    terminal_text
                  ) = 0
        ),
        candidate_rows AS (
            SELECT
                manifest_document_id AS document_id,
                sha256(manifest_text) AS expected_content_sha256,
                original_bytes,
                substr(manifest_text, 1, genotype_position - 1) AS prefix_text,
                genotype_document_id AS first_document_id,
                substr(
                    manifest_text,
                    genotype_position + genotype_length,
                    terminal_position - (genotype_position + genotype_length)
                ) AS between_first_second_text,
                terminal_document_id AS second_document_id,
                CASE
                    WHEN factor_trajectory THEN substr(
                        manifest_text,
                        terminal_position + terminal_length,
                        trajectory_position - (terminal_position + terminal_length)
                    )
                    ELSE NULL
                END AS between_second_third_text,
                CASE WHEN factor_trajectory THEN trajectory_document_id ELSE NULL END
                    AS third_document_id,
                CASE
                    WHEN factor_trajectory THEN substr(
                        manifest_text,
                        trajectory_position + trajectory_length
                    )
                    ELSE substr(manifest_text, terminal_position + terminal_length)
                END AS suffix_text,
                octet_length(encode(genotype_text))
                    + octet_length(encode(terminal_text))
                    + CASE
                        WHEN factor_trajectory THEN octet_length(encode(trajectory_text))
                        ELSE 0
                      END AS referenced_bytes
            FROM eligible
        ),
        component_document_ids AS (
            SELECT first_document_id AS document_id FROM candidate_rows
            UNION
            SELECT second_document_id AS document_id FROM candidate_rows
            UNION
            SELECT third_document_id AS document_id
            FROM candidate_rows
            WHERE third_document_id IS NOT NULL
        )
        SELECT candidate.*
        FROM candidate_rows AS candidate
        ANTI JOIN component_document_ids AS component USING (document_id)
        """
    )

    stats_row = connection.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(original_bytes), 0),
            COALESCE(SUM(referenced_bytes), 0),
            COALESCE(SUM(original_bytes - referenced_bytes), 0)
        FROM {candidates}
        """
    ).fetchone()
    if stats_row is None:
        raise CatalogCompactionError("manifest factoring statistics query returned no row")
    result = ManifestFactoring(*(int(value) for value in stats_row))
    if result.factored_documents == 0:
        connection.execute(f"DROP TABLE {candidates}")
        return result

    connection.execute(
        f"""
        INSERT INTO {templates}
        SELECT
            document_id,
            'specimen_manifest_descriptor_substrings_v1',
            prefix_text,
            first_document_id,
            between_first_second_text,
            second_document_id,
            between_second_third_text,
            third_document_id,
            suffix_text
        FROM {candidates}
        """
    )
    connection.execute(
        f"""
        UPDATE {documents}
        SET document_text = NULL
        WHERE document_id IN (SELECT document_id FROM {candidates})
        """
    )

    failed_written_templates = _scalar_int(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {candidates} AS candidate
        JOIN {values_view} AS reconstructed
          ON reconstructed.document_id = candidate.document_id
        WHERE reconstructed.content_sha256 IS DISTINCT FROM
                candidate.expected_content_sha256
           OR sha256(reconstructed.document_text) IS DISTINCT FROM
                candidate.expected_content_sha256
           OR reconstructed.byte_length IS DISTINCT FROM candidate.original_bytes
           OR octet_length(encode(reconstructed.document_text)) IS DISTINCT FROM
                candidate.original_bytes
        """,
        [],
    )
    if failed_written_templates:
        raise CatalogCompactionError(
            f"{failed_written_templates} written manifest templates failed exact reconstruction"
        )
    connection.execute(f"DROP TABLE {candidates}")
    return result


def _compact_table(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table_name: str,
    columns: tuple[ColumnSpec, ...],
) -> TableCompaction:
    backing_table = f"__compact_{table_name}"
    browse_view = f"{table_name}_browse"
    for object_name in (backing_table, browse_view):
        if _object_exists(connection, schema_name=schema_name, object_name=object_name):
            raise CatalogCompactionError(
                f"refusing to replace existing {schema_name}.{object_name}"
            )

    row_count = _validate_source_rowids(
        connection,
        schema_name=schema_name,
        table_name=table_name,
        columns=columns,
    )
    payload_columns = tuple(column.name for column in columns if column.payload)
    for column_name in payload_columns:
        LOGGER.info(
            "catalog compaction: interning %s.%s.%s",
            schema_name,
            table_name,
            column_name,
        )
        _intern_payload_column(
            connection,
            schema_name=schema_name,
            table_name=table_name,
            column_name=column_name,
        )

    LOGGER.info("catalog compaction: writing compact backing for %s.%s", schema_name, table_name)
    _create_backing_table(
        connection,
        schema_name=schema_name,
        table_name=table_name,
        backing_table=backing_table,
        columns=columns,
    )
    LOGGER.info("catalog compaction: proving exact rows for %s.%s", schema_name, table_name)
    source_digest, reconstruction_digest = _verify_reconstruction(
        connection,
        schema_name=schema_name,
        table_name=table_name,
        backing_table=backing_table,
        columns=columns,
        expected_rows=row_count,
    )

    detail_query = _detail_query(
        schema_name=schema_name,
        backing_table=backing_table,
        columns=columns,
    )
    connection.execute(f"DROP TABLE {_qualified(schema_name, table_name)}")
    connection.execute(f"CREATE VIEW {_qualified(schema_name, table_name)} AS {detail_query}")
    _create_browse_view(
        connection,
        schema_name=schema_name,
        browse_view=browse_view,
        backing_table=backing_table,
        columns=columns,
    )
    _record_metadata(
        connection,
        schema_name=schema_name,
        table_name=table_name,
        backing_table=backing_table,
        browse_view=browse_view,
        columns=columns,
        row_count=row_count,
        pre_compaction_sha256=source_digest,
        reconstruction_sha256=reconstruction_digest,
    )
    return TableCompaction(
        table_name=table_name,
        backing_table=backing_table,
        browse_view=browse_view,
        row_count=row_count,
        payload_columns=payload_columns,
        pre_compaction_sha256=source_digest,
        reconstruction_sha256=reconstruction_digest,
    )


def _column_payload(column: ColumnSpec) -> dict[str, object]:
    return {
        "name": column.name,
        "dataType": column.data_type,
        "nullable": column.nullable,
        "default": column.default,
        "ordinal": column.ordinal,
        "payload": column.payload,
        "backingColumn": column.backing_column,
    }


def _table_payload(table: TableCompaction, columns: tuple[ColumnSpec, ...]) -> dict[str, object]:
    return {
        "tableName": table.table_name,
        "backingTable": table.backing_table,
        "browseView": table.browse_view,
        "rowCount": table.row_count,
        "payloadColumns": list(table.payload_columns),
        "preCompactionSha256": table.pre_compaction_sha256,
        "reconstructionSha256": table.reconstruction_sha256,
        "columns": [_column_payload(column) for column in columns],
    }


def _factoring_payload(factoring: ManifestFactoring) -> dict[str, int]:
    return {
        "factoredDocuments": factoring.factored_documents,
        "originalBytes": factoring.original_bytes,
        "referencedBytes": factoring.referenced_bytes,
        "residualBytes": factoring.residual_bytes,
    }


def _manifest_core(
    *,
    schema_name: str,
    parent_consolidation_receipt_sha256: str | None,
    documents_after: int,
    compacted: tuple[TableCompaction, ...],
    columns_by_table: dict[str, tuple[ColumnSpec, ...]],
    manifest_factoring: ManifestFactoring,
) -> dict[str, object]:
    return {
        "format": COMPACTION_FORMAT,
        "schemaName": schema_name,
        "receiptCanonicalization": RECEIPT_CANONICALIZATION,
        "rowDigestVersion": ROW_DIGEST_VERSION,
        "parentConsolidationReceiptSha256": parent_consolidation_receipt_sha256,
        "documents": {"count": documents_after},
        "manifestFactoring": _factoring_payload(manifest_factoring),
        "tables": [
            _table_payload(table, columns_by_table[table.table_name]) for table in compacted
        ],
    }


def _parent_consolidation_receipt(
    connection: DuckDBPyConnection,
) -> str | None:
    rows = connection.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'consolidation'
          AND table_name = 'manifest'
          AND table_type = 'BASE TABLE'
        """
    ).fetchone()
    if rows is None or int(rows[0]) == 0:
        return None
    manifests = connection.execute(
        "SELECT receipt_sha256, manifest_json FROM consolidation.manifest"
    ).fetchall()
    if len(manifests) != 1:
        raise CatalogCompactionError(
            "consolidation.manifest must contain exactly one parent receipt"
        )
    receipt_sha256 = str(manifests[0][0])
    try:
        manifest = json.loads(str(manifests[0][1]))
    except json.JSONDecodeError as exc:
        raise CatalogCompactionError("parent consolidation manifest is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise CatalogCompactionError("parent consolidation manifest must be an object")
    payload = cast(dict[str, Any], manifest)
    embedded_receipt = payload.pop("receiptSha256", None)
    if embedded_receipt != receipt_sha256 or _canonical_sha256(payload) != receipt_sha256:
        raise CatalogCompactionError("parent consolidation manifest hash mismatch")
    return receipt_sha256


def _embed_compaction_manifest(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    core: dict[str, object],
) -> str:
    receipt_sha256 = _canonical_sha256(core)
    manifest = {**core, "receiptSha256": receipt_sha256}
    connection.execute(
        f"INSERT INTO {_qualified(schema_name, COMPACTION_MANIFEST_TABLE)} VALUES (?, ?)",
        [receipt_sha256, _canonical_json(manifest)],
    )
    return receipt_sha256


def _read_compaction_manifest(
    connection: DuckDBPyConnection, *, schema_name: str
) -> tuple[str, dict[str, Any]]:
    rows = connection.execute(
        f"SELECT receipt_sha256, manifest_json "
        f"FROM {_qualified(schema_name, COMPACTION_MANIFEST_TABLE)}"
    ).fetchall()
    if len(rows) != 1:
        raise CatalogCompactionError(
            f"{schema_name}.{COMPACTION_MANIFEST_TABLE} must contain exactly one receipt"
        )
    receipt_sha256 = str(rows[0][0])
    try:
        manifest = json.loads(str(rows[0][1]))
    except json.JSONDecodeError as exc:
        raise CatalogCompactionError("compaction manifest is invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise CatalogCompactionError("compaction manifest must be an object")
    payload = cast(dict[str, Any], manifest)
    embedded_receipt = payload.pop("receiptSha256", None)
    if embedded_receipt != receipt_sha256 or _canonical_sha256(payload) != receipt_sha256:
        raise CatalogCompactionError("compaction manifest hash mismatch")
    payload["receiptSha256"] = receipt_sha256
    return receipt_sha256, payload


def _require_mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogCompactionError(f"compaction manifest {label} must be an object")
    return cast(dict[str, Any], value)


def _require_list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogCompactionError(f"compaction manifest {label} must be a list")
    return cast(list[Any], value)


def _column_from_payload(value: object, *, table_name: str) -> ColumnSpec:
    payload = _require_mapping(value, label=f"tables.{table_name}.columns[]")
    try:
        return ColumnSpec(
            name=str(payload["name"]),
            data_type=str(payload["dataType"]),
            nullable=bool(payload["nullable"]),
            default=None if payload.get("default") is None else str(payload["default"]),
            ordinal=int(payload["ordinal"]),
            payload=bool(payload["payload"]),
            backing_column=(
                None if payload.get("backingColumn") is None else str(payload["backingColumn"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogCompactionError(
            f"compaction manifest column is invalid for {table_name}"
        ) from exc


def _table_from_payload(
    value: object,
) -> tuple[TableCompaction, tuple[ColumnSpec, ...]]:
    payload = _require_mapping(value, label="tables[]")
    try:
        table_name = str(payload["tableName"])
        raw_payload_columns = _require_list(
            payload["payloadColumns"], label=f"tables.{table_name}.payloadColumns"
        )
        columns = tuple(
            _column_from_payload(column, table_name=table_name)
            for column in _require_list(payload["columns"], label=f"tables.{table_name}.columns")
        )
        table = TableCompaction(
            table_name=table_name,
            backing_table=str(payload["backingTable"]),
            browse_view=str(payload["browseView"]),
            row_count=int(payload["rowCount"]),
            payload_columns=tuple(str(column) for column in raw_payload_columns),
            pre_compaction_sha256=str(payload["preCompactionSha256"]),
            reconstruction_sha256=str(payload["reconstructionSha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogCompactionError("compaction manifest table is invalid") from exc
    if tuple(column.name for column in columns if column.payload) != table.payload_columns:
        raise CatalogCompactionError(
            f"compaction manifest payload columns disagree for {table.table_name}"
        )
    if tuple(column.ordinal for column in columns) != tuple(range(1, len(columns) + 1)):
        raise CatalogCompactionError(
            f"compaction manifest column ordinals are invalid for {table.table_name}"
        )
    return table, columns


def _receipt_payload(
    receipt_sha256: object,
    receipt_json: object,
    *,
    embedded_key: str,
    label: str,
) -> tuple[str, dict[str, Any]]:
    stored_sha256 = str(receipt_sha256)
    try:
        parsed = json.loads(str(receipt_json))
    except json.JSONDecodeError as exc:
        raise CatalogCompactionError(f"{label} is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise CatalogCompactionError(f"{label} must be an object")
    payload = cast(dict[str, Any], parsed)
    embedded_sha256 = payload.pop(embedded_key, None)
    if embedded_sha256 != stored_sha256 or _canonical_sha256(payload) != stored_sha256:
        raise CatalogCompactionError(f"{label} SHA-256 mismatch")
    payload[embedded_key] = stored_sha256
    return stored_sha256, payload


def _plan_core(
    *,
    schema_name: str,
    parent_consolidation_receipt_sha256: str | None,
    required_writable_tables: tuple[str, ...],
    factor_specimen_manifests: bool,
    tables: Sequence[tuple[str, tuple[ColumnSpec, ...]]],
) -> dict[str, object]:
    return {
        "format": COMPACTION_PLAN_FORMAT,
        "schemaName": schema_name,
        "receiptCanonicalization": RECEIPT_CANONICALIZATION,
        "rowDigestVersion": ROW_DIGEST_VERSION,
        "parentConsolidationReceiptSha256": parent_consolidation_receipt_sha256,
        "requiredWritableTables": list(required_writable_tables),
        "factorSpecimenManifests": factor_specimen_manifests,
        "tables": [
            {
                "tableName": table_name,
                "columns": [_column_payload(column) for column in columns],
            }
            for table_name, columns in tables
        ],
    }


def _embed_compaction_plan(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    core: dict[str, object],
) -> str:
    receipt_sha256 = _canonical_sha256(core)
    payload = {**core, "planSha256": receipt_sha256}
    connection.execute(
        f"INSERT INTO {_qualified(schema_name, COMPACTION_PLAN_TABLE)} VALUES (true, ?, ?)",
        [receipt_sha256, _canonical_json(payload)],
    )
    return receipt_sha256


def _read_compaction_plan(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
) -> _CompactionPlan:
    rows = connection.execute(
        f"SELECT plan_sha256, plan_json FROM "
        f"{_qualified(schema_name, COMPACTION_PLAN_TABLE)} WHERE singleton"
    ).fetchall()
    if len(rows) != 1:
        raise CatalogCompactionError(
            f"{schema_name}.{COMPACTION_PLAN_TABLE} must contain exactly one plan"
        )
    receipt_sha256, payload = _receipt_payload(
        rows[0][0],
        rows[0][1],
        embedded_key="planSha256",
        label="catalog compaction plan",
    )
    if payload.get("format") != COMPACTION_PLAN_FORMAT:
        raise CatalogCompactionError("catalog compaction plan format mismatch")
    if payload.get("schemaName") != schema_name:
        raise CatalogCompactionError("catalog compaction plan schema mismatch")
    if payload.get("receiptCanonicalization") != RECEIPT_CANONICALIZATION:
        raise CatalogCompactionError("catalog compaction plan canonicalization mismatch")
    if payload.get("rowDigestVersion") != ROW_DIGEST_VERSION:
        raise CatalogCompactionError("catalog compaction plan row digest mismatch")
    parent_receipt = payload.get("parentConsolidationReceiptSha256")
    if parent_receipt is not None and not isinstance(parent_receipt, str):
        raise CatalogCompactionError("catalog compaction plan parent receipt is invalid")
    raw_required = _require_list(
        payload.get("requiredWritableTables"), label="plan.requiredWritableTables"
    )
    if not all(isinstance(value, str) for value in raw_required):
        raise CatalogCompactionError("catalog compaction plan required tables are invalid")
    required_tables = _normalize_required_tables(tuple(cast(list[str], raw_required)))
    factor_specimen_manifests = payload.get("factorSpecimenManifests")
    if not isinstance(factor_specimen_manifests, bool):
        raise CatalogCompactionError("catalog compaction plan factoring mode is invalid")
    tables: list[tuple[str, tuple[ColumnSpec, ...]]] = []
    for raw_table in _require_list(payload.get("tables"), label="plan.tables"):
        table_payload = _require_mapping(raw_table, label="plan.tables[]")
        table_name_value = table_payload.get("tableName")
        if not isinstance(table_name_value, str) or not table_name_value:
            raise CatalogCompactionError("catalog compaction plan table name is invalid")
        columns = tuple(
            _column_from_payload(value, table_name=table_name_value)
            for value in _require_list(
                table_payload.get("columns"),
                label=f"plan.tables.{table_name_value}.columns",
            )
        )
        if tuple(column.ordinal for column in columns) != tuple(range(1, len(columns) + 1)):
            raise CatalogCompactionError(
                f"catalog compaction plan column ordinals changed for {table_name_value}"
            )
        column_names = tuple(column.name for column in columns)
        if len(column_names) != len(set(column_names)) or "_source_rowid" not in column_names:
            raise CatalogCompactionError(
                f"catalog compaction plan columns are invalid for {table_name_value}"
            )
        tables.append((table_name_value, columns))
    table_names = tuple(table_name for table_name, _ in tables)
    if len(table_names) != len(set(table_names)):
        raise CatalogCompactionError("catalog compaction plan contains duplicate tables")
    return _CompactionPlan(
        receipt_sha256=receipt_sha256,
        parent_consolidation_receipt_sha256=cast(str | None, parent_receipt),
        required_writable_tables=required_tables,
        factor_specimen_manifests=factor_specimen_manifests,
        tables=tuple(tables),
    )


def catalog_compaction_state(
    connection: DuckDBPyConnection,
    *,
    schema_name: str = "catalog",
) -> Literal["original", "partial", "final"]:
    support_relations = {
        DOCUMENT_TABLE,
        DOCUMENT_TEMPLATE_TABLE,
        DOCUMENT_VALUES_VIEW,
        TABLE_METADATA,
        COLUMN_METADATA,
        COMPACTION_MANIFEST_TABLE,
        COMPACTION_PLAN_TABLE,
        COMPACTION_CHECKPOINT_TABLE,
    }
    present = {
        name
        for name in support_relations
        if _object_exists(connection, schema_name=schema_name, object_name=name)
    }

    def relation_rows(relation_name: str) -> int:
        return _scalar_int(
            connection,
            f"SELECT count(*) FROM {_qualified(schema_name, relation_name)}",
            [],
        )

    manifest_count = (
        relation_rows(COMPACTION_MANIFEST_TABLE) if COMPACTION_MANIFEST_TABLE in present else 0
    )
    if manifest_count > 1:
        raise CatalogCompactionError("catalog has multiple compaction manifests")
    plan_count = relation_rows(COMPACTION_PLAN_TABLE) if COMPACTION_PLAN_TABLE in present else 0
    if plan_count > 1:
        raise CatalogCompactionError("catalog has multiple compaction plans")
    if manifest_count == 1:
        final_relations = support_relations - {
            COMPACTION_PLAN_TABLE,
            COMPACTION_CHECKPOINT_TABLE,
        }
        if present != final_relations:
            raise CatalogCompactionError(
                "final catalog compaction support is malformed: "
                + _canonical_json(
                    {
                        "missing": sorted(final_relations - present),
                        "extra": sorted(present - final_relations),
                    }
                )
            )
        return "final"
    if plan_count == 1:
        if present != support_relations:
            raise CatalogCompactionError(
                "partial catalog compaction support is malformed: "
                + _canonical_json(
                    {
                        "missing": sorted(support_relations - present),
                        "extra": sorted(present - support_relations),
                    }
                )
            )
        _read_compaction_plan(connection, schema_name=schema_name)
        return "partial"
    if present:
        raise CatalogCompactionError(
            "catalog has compaction support without a final manifest or resumable plan: "
            + ", ".join(sorted(present))
        )
    return "original"


def _checkpoint_core(
    *,
    schema_name: str,
    plan_receipt_sha256: str,
    table: TableCompaction,
    columns: tuple[ColumnSpec, ...],
) -> dict[str, object]:
    return {
        "format": COMPACTION_CHECKPOINT_FORMAT,
        "schemaName": schema_name,
        "planReceiptSha256": plan_receipt_sha256,
        "rowDigestVersion": ROW_DIGEST_VERSION,
        "table": _table_payload(table, columns),
    }


def _embed_table_checkpoint(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    plan_receipt_sha256: str,
    table: TableCompaction,
    columns: tuple[ColumnSpec, ...],
) -> _TableCheckpoint:
    core = _checkpoint_core(
        schema_name=schema_name,
        plan_receipt_sha256=plan_receipt_sha256,
        table=table,
        columns=columns,
    )
    receipt_sha256 = _canonical_sha256(core)
    payload = {**core, "receiptSha256": receipt_sha256}
    connection.execute(
        f"INSERT INTO {_qualified(schema_name, COMPACTION_CHECKPOINT_TABLE)} "
        "VALUES (?, ?, ?, ?, ?)",
        [
            schema_name,
            table.table_name,
            plan_receipt_sha256,
            receipt_sha256,
            _canonical_json(payload),
        ],
    )
    return _TableCheckpoint(
        receipt_sha256=receipt_sha256,
        table=table,
        columns=columns,
    )


def _relation_type(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    object_name: str,
) -> str | None:
    rows = connection.execute(
        """
        SELECT table_type
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema_name, object_name],
    ).fetchall()
    if len(rows) > 1:
        raise CatalogCompactionError(f"duplicate catalog object: {schema_name}.{object_name}")
    return None if not rows else str(rows[0][0])


def _verify_checkpoint_metadata(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    checkpoint: _TableCheckpoint,
) -> None:
    table = checkpoint.table
    columns = checkpoint.columns
    table_rows = connection.execute(
        f"""
        SELECT source_schema, source_table, backing_table, browse_view, row_count,
               source_column_count, payload_column_count, pre_compaction_sha256,
               reconstruction_sha256, row_digest_version
        FROM {_qualified(schema_name, TABLE_METADATA)}
        WHERE source_schema = ? AND source_table = ?
        """,
        [schema_name, table.table_name],
    ).fetchall()
    expected_table_row = (
        schema_name,
        table.table_name,
        table.backing_table,
        table.browse_view,
        table.row_count,
        len(columns),
        len(table.payload_columns),
        table.pre_compaction_sha256,
        table.reconstruction_sha256,
        ROW_DIGEST_VERSION,
    )
    if table_rows != [expected_table_row]:
        raise CatalogCompactionError(
            f"catalog compaction checkpoint metadata changed for {table.table_name}"
        )
    column_rows = connection.execute(
        f"""
        SELECT source_schema, source_table, ordinal_position, column_name, data_type,
               is_nullable, column_default, is_payload, backing_column
        FROM {_qualified(schema_name, COLUMN_METADATA)}
        WHERE source_schema = ? AND source_table = ?
        ORDER BY ordinal_position
        """,
        [schema_name, table.table_name],
    ).fetchall()
    expected_column_rows = [
        (
            schema_name,
            table.table_name,
            column.ordinal,
            column.name,
            column.data_type,
            column.nullable,
            column.default,
            column.payload,
            column.backing_column,
        )
        for column in columns
    ]
    if column_rows != expected_column_rows:
        raise CatalogCompactionError(
            f"catalog compaction checkpoint columns changed for {table.table_name}"
        )
    expected_relations = {
        table.table_name: "VIEW",
        table.backing_table: "BASE TABLE",
        table.browse_view: "VIEW",
    }
    actual_relations = {
        name: _relation_type(connection, schema_name=schema_name, object_name=name)
        for name in expected_relations
    }
    if actual_relations != expected_relations:
        raise CatalogCompactionError(
            f"catalog compaction checkpoint objects changed for {table.table_name}"
        )


def _read_table_checkpoints(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    plan: _CompactionPlan,
) -> dict[str, _TableCheckpoint]:
    planned_columns = dict(plan.tables)
    checkpoints: dict[str, _TableCheckpoint] = {}
    rows = connection.execute(
        f"SELECT source_schema, source_table, plan_sha256, receipt_sha256, receipt_json "
        f"FROM {_qualified(schema_name, COMPACTION_CHECKPOINT_TABLE)} "
        "ORDER BY source_table"
    ).fetchall()
    for source_schema, source_table, plan_sha256, receipt_sha256, receipt_json in rows:
        table_name = str(source_table)
        if (
            str(source_schema) != schema_name
            or str(plan_sha256) != plan.receipt_sha256
            or table_name not in planned_columns
        ):
            raise CatalogCompactionError(
                f"catalog compaction checkpoint binding changed for {table_name}"
            )
        stored_sha256, payload = _receipt_payload(
            receipt_sha256,
            receipt_json,
            embedded_key="receiptSha256",
            label=f"catalog compaction checkpoint {table_name}",
        )
        if (
            payload.get("format") != COMPACTION_CHECKPOINT_FORMAT
            or payload.get("schemaName") != schema_name
            or payload.get("planReceiptSha256") != plan.receipt_sha256
            or payload.get("rowDigestVersion") != ROW_DIGEST_VERSION
        ):
            raise CatalogCompactionError(
                f"catalog compaction checkpoint receipt changed for {table_name}"
            )
        table, columns = _table_from_payload(payload.get("table"))
        if table.table_name != table_name or columns != planned_columns[table_name]:
            raise CatalogCompactionError(
                f"catalog compaction checkpoint plan changed for {table_name}"
            )
        checkpoint = _TableCheckpoint(
            receipt_sha256=stored_sha256,
            table=table,
            columns=columns,
        )
        _verify_checkpoint_metadata(
            connection,
            schema_name=schema_name,
            checkpoint=checkpoint,
        )
        checkpoints[table_name] = checkpoint
    expected_bindings = {(schema_name, table_name) for table_name in checkpoints}
    actual_table_bindings = {
        (str(source_schema), str(source_table))
        for source_schema, source_table in connection.execute(
            f"SELECT source_schema, source_table FROM {_qualified(schema_name, TABLE_METADATA)}"
        ).fetchall()
    }
    actual_column_bindings = {
        (str(source_schema), str(source_table))
        for source_schema, source_table in connection.execute(
            f"SELECT DISTINCT source_schema, source_table "
            f"FROM {_qualified(schema_name, COLUMN_METADATA)}"
        ).fetchall()
    }
    if actual_table_bindings != expected_bindings or actual_column_bindings != expected_bindings:
        raise CatalogCompactionError("catalog compaction checkpoint ledger is incomplete")
    return checkpoints


def _validate_resumable_state(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    plan: _CompactionPlan,
    checkpoints: dict[str, _TableCheckpoint],
) -> None:
    missing_tables = tuple(
        (table_name, columns)
        for table_name, columns in plan.tables
        if table_name not in checkpoints
    )
    discovered = tuple(
        _discover_tables(
            connection,
            schema_name=schema_name,
            required_writable_tables=plan.required_writable_tables,
        )
    )
    if discovered != missing_tables:
        raise CatalogCompactionError(
            "catalog compaction source tables or columns changed after its plan was recorded"
        )
    for checkpoint in checkpoints.values():
        _verify_compacted_table(
            connection,
            schema_name=schema_name,
            table=checkpoint.table,
            columns=checkpoint.columns,
        )


def _drop_progress_tables(connection: DuckDBPyConnection, *, schema_name: str) -> None:
    connection.execute(f"DROP TABLE {_qualified(schema_name, COMPACTION_CHECKPOINT_TABLE)}")
    connection.execute(f"DROP TABLE {_qualified(schema_name, COMPACTION_PLAN_TABLE)}")


def _table_checkpoint_committed(_table_name: str) -> None:
    pass


def _compaction_manifest_committed() -> None:
    pass


def _factoring_from_manifest(manifest: dict[str, Any]) -> ManifestFactoring:
    payload = _require_mapping(manifest.get("manifestFactoring"), label="manifestFactoring")
    try:
        return ManifestFactoring(
            factored_documents=int(payload["factoredDocuments"]),
            original_bytes=int(payload["originalBytes"]),
            referenced_bytes=int(payload["referencedBytes"]),
            residual_bytes=int(payload["residualBytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogCompactionError(
            "compaction manifest factoring statistics are invalid"
        ) from exc


def _raw_document_integrity_query(*, schema_name: str) -> str:
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    return f"""
        SELECT COUNT(*)
        FROM {documents}
        WHERE document_text IS NOT NULL
          AND (
                sha256(document_text) IS DISTINCT FROM content_sha256
                OR octet_length(encode(document_text)) IS DISTINCT FROM byte_length
              )
    """


def _template_document_rows(
    connection: DuckDBPyConnection,
    *,
    documents: str,
    document_ids: set[int],
) -> dict[int, tuple[str, int, str | None]]:
    if not document_ids:
        return {}
    ordered_ids = sorted(document_ids)
    placeholders = ", ".join("?" for _ in ordered_ids)
    rows = connection.execute(
        f"""
        SELECT document_id, content_sha256, byte_length, document_text
        FROM {documents}
        WHERE document_id IN ({placeholders})
        """,
        ordered_ids,
    ).fetchall()
    return {
        int(document_id): (
            str(content_sha256),
            int(byte_length),
            None if document_text is None else str(document_text),
        )
        for document_id, content_sha256, byte_length, document_text in rows
    }


def _template_document_errors(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
) -> tuple[int, int]:
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    templates = _qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)
    last_document_id: int | None = None
    invalid_references = 0
    invalid_values = 0
    while True:
        where = "" if last_document_id is None else "WHERE document_id > ?"
        parameters: list[object] = [] if last_document_id is None else [last_document_id]
        rows = connection.execute(
            f"""
            SELECT document_id, template_kind, prefix_text, first_document_id,
                   between_first_second_text, second_document_id,
                   between_second_third_text, third_document_id, suffix_text
            FROM {templates}
            {where}
            ORDER BY document_id
            LIMIT {DOCUMENT_VERIFICATION_BATCH_SIZE}
            """,
            parameters,
        ).fetchall()
        if not rows:
            return invalid_references, invalid_values

        document_ids = {
            int(document_id)
            for row in rows
            for document_id in (row[0], row[3], row[5], row[7])
            if document_id is not None
        }
        document_rows = _template_document_rows(
            connection,
            documents=documents,
            document_ids=document_ids,
        )
        for row in rows:
            (
                document_id,
                template_kind,
                prefix_text,
                first_document_id,
                between_first_second_text,
                second_document_id,
                between_second_third_text,
                third_document_id,
                suffix_text,
            ) = row
            expected = document_rows.get(int(document_id))
            first = document_rows.get(int(first_document_id))
            second = document_rows.get(int(second_document_id))
            third = None if third_document_id is None else document_rows.get(int(third_document_id))
            if (
                template_kind != "specimen_manifest_descriptor_substrings_v1"
                or first is None
                or first[2] is None
                or second is None
                or second[2] is None
                or (third_document_id is not None and (third is None or third[2] is None))
            ):
                invalid_references += 1
                continue
            if (
                expected is None
                or expected[2] is not None
                or (third_document_id is None) != (between_second_third_text is None)
            ):
                invalid_values += 1
                continue

            first_text = first[2]
            second_text = second[2]
            if first_text is None or second_text is None:
                raise AssertionError("validated template reference is missing")
            segments = [
                str(prefix_text),
                first_text,
                str(between_first_second_text),
                second_text,
            ]
            if third is not None:
                third_text = third[2]
                if third_text is None:
                    raise AssertionError("validated template reference is missing")
                segments.extend((str(between_second_third_text), third_text))
            segments.append(str(suffix_text))
            digest = hashlib.sha256()
            byte_length = 0
            for segment in segments:
                if segment is None:
                    raise AssertionError("validated template segment is missing")
                encoded = segment.encode("utf-8")
                digest.update(encoded)
                byte_length += len(encoded)
            if digest.hexdigest() != expected[0] or byte_length != expected[1]:
                invalid_values += 1
        last_document_id = int(rows[-1][0])


def _verify_document_store(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    expected_documents: int,
    expected_templates: int,
) -> None:
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    templates = _qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)
    values = _qualified(schema_name, DOCUMENT_VALUES_VIEW)
    expected_values_query = _document_values_query(schema_name=schema_name)
    actual_values_query = f"SELECT * FROM {values}"
    if _query_layout(connection, actual_values_query) != _query_layout(
        connection, expected_values_query
    ) or _normalized_query_plan(connection, actual_values_query) != _normalized_query_plan(
        connection, expected_values_query
    ):
        raise CatalogCompactionError(
            f"compacted public view changed for {schema_name}.{DOCUMENT_VALUES_VIEW}"
        )
    actual_documents = _scalar_int(connection, f"SELECT COUNT(*) FROM {documents}", [])
    if actual_documents != expected_documents:
        raise CatalogCompactionError(
            f"catalog document count changed: {actual_documents} != {expected_documents}"
        )
    if _scalar_int(connection, f"SELECT COUNT(*) FROM {values}", []) != expected_documents:
        raise CatalogCompactionError("catalog document reconstruction is not one-to-one")
    duplicate_hashes = _scalar_int(
        connection,
        f"SELECT COUNT(*) - COUNT(DISTINCT content_sha256) FROM {documents}",
        [],
    )
    if duplicate_hashes:
        raise CatalogCompactionError("catalog document hashes are not unique")
    raw_template_mismatches = _scalar_int(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {documents} AS document
        LEFT JOIN {templates} AS template USING (document_id)
        WHERE (document.document_text IS NULL) = (template.document_id IS NULL)
        """,
        [],
    )
    if raw_template_mismatches:
        raise CatalogCompactionError(
            f"{raw_template_mismatches} catalog documents have invalid raw/template storage"
        )
    template_count = _scalar_int(connection, f"SELECT COUNT(*) FROM {templates}", [])
    if template_count != expected_templates:
        raise CatalogCompactionError(
            f"catalog template count changed: {template_count} != {expected_templates}"
        )
    invalid_references, invalid_template_values = (
        _template_document_errors(connection, schema_name=schema_name) if template_count else (0, 0)
    )
    if invalid_references:
        raise CatalogCompactionError(
            f"{invalid_references} catalog templates have invalid document references"
        )
    invalid_values = (
        _scalar_int(
            connection,
            _raw_document_integrity_query(schema_name=schema_name),
            [],
        )
        + invalid_template_values
    )
    if invalid_values:
        raise CatalogCompactionError(
            f"{invalid_values} catalog documents fail SHA-256 or byte-length verification"
        )


def _verify_compacted_table(
    connection: DuckDBPyConnection,
    *,
    schema_name: str,
    table: TableCompaction,
    columns: tuple[ColumnSpec, ...],
) -> None:
    if table.pre_compaction_sha256 != table.reconstruction_sha256:
        raise CatalogCompactionError(
            f"recorded reconstruction digest differs for {schema_name}.{table.table_name}"
        )
    backing_columns = _source_columns(
        connection,
        schema_name=schema_name,
        table_name=table.backing_table,
    )
    expected_backing_names = tuple(
        str(column.backing_column) if column.payload else column.name for column in columns
    )
    if tuple(column.name for column in backing_columns) != expected_backing_names:
        raise CatalogCompactionError(
            f"compacted backing columns changed for {schema_name}.{table.table_name}"
        )
    backing_rows = _validate_source_rowids(
        connection,
        schema_name=schema_name,
        table_name=table.backing_table,
        columns=columns,
    )
    if backing_rows != table.row_count:
        raise CatalogCompactionError(
            f"compacted row count changed for {schema_name}.{table.table_name}"
        )
    documents = _qualified(schema_name, DOCUMENT_TABLE)
    backing = _qualified(schema_name, table.backing_table)
    document_columns = [
        _quote_identifier(column.backing_column)
        for column in columns
        if column.payload and column.backing_column is not None
    ]
    if document_columns:
        references = ", ".join(f"backing.{column}" for column in document_columns)
        missing_documents = _scalar_int(
            connection,
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT unnest([{references}]) AS document_id
                FROM {backing} AS backing
            ) AS reference
            LEFT JOIN {documents} AS document
              USING (document_id)
            WHERE reference.document_id IS NOT NULL
              AND document.document_id IS NULL
            """,
            [],
        )
        if missing_documents:
            raise CatalogCompactionError(
                f"{schema_name}.{table.table_name} has {missing_documents} missing documents"
            )
    digest_query = _backing_digest_query(
        schema_name=schema_name,
        backing_table=table.backing_table,
        columns=columns,
    )
    digest_rows, actual_digest = _digest_query(connection, query=digest_query)
    if digest_rows != table.row_count:
        raise CatalogCompactionError(
            f"compacted digest row count changed for {schema_name}.{table.table_name}"
        )
    if actual_digest != table.pre_compaction_sha256:
        raise CatalogCompactionError(
            f"compacted reconstruction digest changed for {schema_name}.{table.table_name}"
        )
    overlay_owner = _object_exists(
        connection,
        schema_name=schema_name,
        object_name="writable_overlay_tables",
    ) and bool(
        _scalar_int(
            connection,
            f"SELECT count(*) FROM {_qualified(schema_name, 'writable_overlay_tables')} "
            "WHERE source_schema = ? AND source_table = ?",
            [schema_name, table.table_name],
        )
    )
    if not overlay_owner:
        expected_detail = _detail_query(
            schema_name=schema_name,
            backing_table=table.backing_table,
            columns=columns,
        )
        expected_browse = _browse_query(
            schema_name=schema_name,
            backing_table=table.backing_table,
            columns=columns,
        )
        for view_name, expected_query in (
            (table.table_name, expected_detail),
            (table.browse_view, expected_browse),
        ):
            actual_query = f"SELECT * FROM {_qualified(schema_name, view_name)}"
            if _query_layout(connection, actual_query) != _query_layout(
                connection, expected_query
            ) or _normalized_query_plan(connection, actual_query) != _normalized_query_plan(
                connection, expected_query
            ):
                raise CatalogCompactionError(
                    f"compacted public view changed for {schema_name}.{view_name}"
                )


def verify_compacted_catalog(
    connection: DuckDBPyConnection,
    *,
    schema_name: str = "catalog",
    required_writable_tables: Sequence[str] = (),
) -> CatalogCompactionVerification:
    """Verify the immutable compact base without consulting its source SQLite DB."""
    required_tables = _normalize_required_tables(required_writable_tables)
    receipt_sha256, manifest = _read_compaction_manifest(connection, schema_name=schema_name)
    retained_progress = [
        table_name
        for table_name in (COMPACTION_PLAN_TABLE, COMPACTION_CHECKPOINT_TABLE)
        if _object_exists(connection, schema_name=schema_name, object_name=table_name)
    ]
    if retained_progress:
        raise CatalogCompactionError(
            "completed catalog compaction retained progress tables: " + ", ".join(retained_progress)
        )
    if manifest.get("format") != COMPACTION_FORMAT:
        raise CatalogCompactionError("unsupported compaction manifest format")
    if manifest.get("schemaName") != schema_name:
        raise CatalogCompactionError("compaction manifest schema name mismatch")
    if manifest.get("receiptCanonicalization") != RECEIPT_CANONICALIZATION:
        raise CatalogCompactionError("compaction manifest canonicalization mismatch")
    if manifest.get("rowDigestVersion") != ROW_DIGEST_VERSION:
        raise CatalogCompactionError("compaction row digest version mismatch")
    parent_receipt = manifest.get("parentConsolidationReceiptSha256")
    if parent_receipt is not None and not isinstance(parent_receipt, str):
        raise CatalogCompactionError("compaction parent receipt is invalid")
    if _parent_consolidation_receipt(connection) != parent_receipt:
        raise CatalogCompactionError("compaction parent consolidation receipt mismatch")
    document_payload = _require_mapping(manifest.get("documents"), label="documents")
    try:
        expected_documents = int(document_payload["count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogCompactionError("compaction manifest document count is invalid") from exc
    factoring = _factoring_from_manifest(manifest)
    raw_tables = _require_list(manifest.get("tables"), label="tables")
    parsed = tuple(_table_from_payload(value) for value in raw_tables)
    table_names = tuple(table.table_name for table, _ in parsed)
    if len(set(table_names)) != len(table_names):
        raise CatalogCompactionError("compaction manifest contains duplicate tables")
    _require_writable_tables(
        connection,
        schema_name=schema_name,
        required_writable_tables=required_tables,
        compacted_tables=table_names,
    )

    metadata_rows = connection.execute(
        f"""
        SELECT source_schema, source_table, backing_table, browse_view, row_count,
               source_column_count, payload_column_count, pre_compaction_sha256,
               reconstruction_sha256, row_digest_version
        FROM {_qualified(schema_name, TABLE_METADATA)}
        ORDER BY source_table
        """
    ).fetchall()
    expected_metadata_rows = sorted(
        (
            schema_name,
            table.table_name,
            table.backing_table,
            table.browse_view,
            table.row_count,
            len(columns),
            len(table.payload_columns),
            table.pre_compaction_sha256,
            table.reconstruction_sha256,
            ROW_DIGEST_VERSION,
        )
        for table, columns in parsed
    )
    if metadata_rows != expected_metadata_rows:
        raise CatalogCompactionError("compaction table metadata differs from its receipt")

    column_rows = connection.execute(
        f"""
        SELECT source_schema, source_table, ordinal_position, column_name, data_type,
               is_nullable, column_default, is_payload, backing_column
        FROM {_qualified(schema_name, COLUMN_METADATA)}
        ORDER BY source_table, ordinal_position
        """
    ).fetchall()
    expected_column_rows = sorted(
        (
            schema_name,
            table.table_name,
            column.ordinal,
            column.name,
            column.data_type,
            column.nullable,
            column.default,
            column.payload,
            column.backing_column,
        )
        for table, columns in parsed
        for column in columns
    )
    if column_rows != expected_column_rows:
        raise CatalogCompactionError("compaction column metadata differs from its receipt")

    _verify_document_store(
        connection,
        schema_name=schema_name,
        expected_documents=expected_documents,
        expected_templates=factoring.factored_documents,
    )
    for table, columns in parsed:
        _verify_compacted_table(
            connection,
            schema_name=schema_name,
            table=table,
            columns=columns,
        )
    return CatalogCompactionVerification(
        schema_name=schema_name,
        receipt_sha256=receipt_sha256,
        document_count=expected_documents,
        table_count=len(parsed),
        row_count=sum(table.row_count for table, _ in parsed),
    )


def compact_catalog(
    connection: DuckDBPyConnection,
    *,
    schema_name: str = "catalog",
    required_writable_tables: Sequence[str] = (),
    factor_specimen_manifests: bool = False,
) -> CatalogCompaction:
    """Intern catalog JSON payloads through durable, exact per-table checkpoints."""
    required_tables = _normalize_required_tables(required_writable_tables)
    manifest_exists = _object_exists(
        connection,
        schema_name=schema_name,
        object_name=COMPACTION_MANIFEST_TABLE,
    )
    if manifest_exists:
        manifest_count = _scalar_int(
            connection,
            f"SELECT COUNT(*) FROM {_qualified(schema_name, COMPACTION_MANIFEST_TABLE)}",
            [],
        )
        if manifest_count > 1:
            raise CatalogCompactionError("catalog has multiple compaction receipts")
        if manifest_count == 1:
            connection.execute("BEGIN TRANSACTION")
            transaction_open = True
            try:
                documents_before = _scalar_int(
                    connection,
                    f"SELECT COUNT(*) FROM {_qualified(schema_name, DOCUMENT_TABLE)}",
                    [],
                )
                verification = verify_compacted_catalog(
                    connection,
                    schema_name=schema_name,
                    required_writable_tables=required_tables,
                )
                _, manifest = _read_compaction_manifest(connection, schema_name=schema_name)
                manifest_factoring = _factoring_from_manifest(manifest)
                connection.execute("COMMIT")
                transaction_open = False
            except BaseException:
                if transaction_open:
                    connection.execute("ROLLBACK")
                raise
            return CatalogCompaction(
                schema_name=schema_name,
                documents_before=documents_before,
                documents_after=documents_before,
                tables=(),
                manifest_factoring=manifest_factoring,
                receipt_sha256=verification.receipt_sha256,
            )

    connection.execute("BEGIN TRANSACTION")
    transaction_open = True
    try:
        _ensure_support_tables(connection, schema_name=schema_name)
        _ensure_progress_tables(connection, schema_name=schema_name)
        documents_before = _scalar_int(
            connection,
            f"SELECT COUNT(*) FROM {_qualified(schema_name, DOCUMENT_TABLE)}",
            [],
        )
        manifest_count = _scalar_int(
            connection,
            f"SELECT COUNT(*) FROM {_qualified(schema_name, COMPACTION_MANIFEST_TABLE)}",
            [],
        )
        if manifest_count:
            raise CatalogCompactionError("catalog compaction manifest appeared during planning")
        plan_count = _scalar_int(
            connection,
            f"SELECT COUNT(*) FROM {_qualified(schema_name, COMPACTION_PLAN_TABLE)}",
            [],
        )
        if plan_count > 1:
            raise CatalogCompactionError("catalog has multiple compaction plans")
        if plan_count == 0:
            support_rows = {
                DOCUMENT_TABLE: documents_before,
                DOCUMENT_TEMPLATE_TABLE: _scalar_int(
                    connection,
                    f"SELECT COUNT(*) FROM {_qualified(schema_name, DOCUMENT_TEMPLATE_TABLE)}",
                    [],
                ),
                TABLE_METADATA: _scalar_int(
                    connection,
                    f"SELECT COUNT(*) FROM {_qualified(schema_name, TABLE_METADATA)}",
                    [],
                ),
                COLUMN_METADATA: _scalar_int(
                    connection,
                    f"SELECT COUNT(*) FROM {_qualified(schema_name, COLUMN_METADATA)}",
                    [],
                ),
                COMPACTION_CHECKPOINT_TABLE: _scalar_int(
                    connection,
                    f"SELECT COUNT(*) FROM {_qualified(schema_name, COMPACTION_CHECKPOINT_TABLE)}",
                    [],
                ),
            }
            dirty_support = [name for name, count in support_rows.items() if count]
            if dirty_support:
                raise CatalogCompactionError(
                    "fresh catalog compaction requires empty support tables: "
                    + ", ".join(dirty_support)
                )
            _require_writable_tables(
                connection,
                schema_name=schema_name,
                required_writable_tables=required_tables,
            )
            tables = tuple(
                _discover_tables(
                    connection,
                    schema_name=schema_name,
                    required_writable_tables=required_tables,
                )
            )
            for table_name, columns in tables:
                if "_source_rowid" not in {column.name for column in columns}:
                    raise CatalogCompactionError(
                        f"{schema_name}.{table_name} must contain _source_rowid before compaction"
                    )
            plan_core = _plan_core(
                schema_name=schema_name,
                parent_consolidation_receipt_sha256=_parent_consolidation_receipt(connection),
                required_writable_tables=required_tables,
                factor_specimen_manifests=factor_specimen_manifests,
                tables=tables,
            )
            _embed_compaction_plan(
                connection,
                schema_name=schema_name,
                core=plan_core,
            )
        plan = _read_compaction_plan(connection, schema_name=schema_name)
        if (
            plan.parent_consolidation_receipt_sha256 != _parent_consolidation_receipt(connection)
            or plan.required_writable_tables != required_tables
            or plan.factor_specimen_manifests != factor_specimen_manifests
        ):
            raise CatalogCompactionError("resumed catalog compaction plan changed")
        checkpoints = _read_table_checkpoints(
            connection,
            schema_name=schema_name,
            plan=plan,
        )
        _validate_resumable_state(
            connection,
            schema_name=schema_name,
            plan=plan,
            checkpoints=checkpoints,
        )
        connection.execute("COMMIT")
        transaction_open = False
    except BaseException:
        if transaction_open:
            connection.execute("ROLLBACK")
        raise
    connection.execute("FORCE CHECKPOINT")

    newly_compacted: list[TableCompaction] = []
    for table_name, columns in plan.tables:
        if table_name in checkpoints:
            LOGGER.info(
                "catalog compaction: reusing checkpoint %s for %s.%s",
                checkpoints[table_name].receipt_sha256,
                schema_name,
                table_name,
            )
            continue
        LOGGER.info("catalog compaction: starting %s.%s", schema_name, table_name)
        connection.execute("BEGIN TRANSACTION")
        transaction_open = True
        try:
            if (
                _source_columns(
                    connection,
                    schema_name=schema_name,
                    table_name=table_name,
                )
                != columns
                or _relation_type(
                    connection,
                    schema_name=schema_name,
                    object_name=table_name,
                )
                != "BASE TABLE"
            ):
                raise CatalogCompactionError(
                    f"catalog compaction source changed before checkpointing {table_name}"
                )
            compacted_table = _compact_table(
                connection,
                schema_name=schema_name,
                table_name=table_name,
                columns=columns,
            )
            checkpoint = _embed_table_checkpoint(
                connection,
                schema_name=schema_name,
                plan_receipt_sha256=plan.receipt_sha256,
                table=compacted_table,
                columns=columns,
            )
            _verify_checkpoint_metadata(
                connection,
                schema_name=schema_name,
                checkpoint=checkpoint,
            )
            connection.execute("COMMIT")
            transaction_open = False
        except BaseException:
            if transaction_open:
                connection.execute("ROLLBACK")
            raise
        _table_checkpoint_committed(table_name)
        checkpoints[table_name] = checkpoint
        newly_compacted.append(compacted_table)
        connection.execute("FORCE CHECKPOINT")
        LOGGER.info(
            "catalog compaction: committed checkpoint %s for %s.%s",
            checkpoint.receipt_sha256,
            schema_name,
            table_name,
        )

    columns_by_table = dict(plan.tables)
    connection.execute("BEGIN TRANSACTION")
    transaction_open = True
    try:
        checkpoints = _read_table_checkpoints(
            connection,
            schema_name=schema_name,
            plan=plan,
        )
        planned_names = tuple(table_name for table_name, _ in plan.tables)
        if set(checkpoints) != set(planned_names):
            raise CatalogCompactionError("catalog compaction checkpoint ledger is incomplete")
        compacted = tuple(checkpoints[table_name].table for table_name in planned_names)
        manifest_factoring = _empty_manifest_factoring()
        if plan.factor_specimen_manifests:
            LOGGER.info("catalog compaction: factoring exact specimen manifest substrings")
            manifest_factoring = _factor_specimen_manifests(
                connection,
                schema_name=schema_name,
                columns=columns_by_table.get("specimens"),
            )
        documents_after = _scalar_int(
            connection,
            f"SELECT COUNT(*) FROM {_qualified(schema_name, DOCUMENT_TABLE)}",
            [],
        )
        core = _manifest_core(
            schema_name=schema_name,
            parent_consolidation_receipt_sha256=plan.parent_consolidation_receipt_sha256,
            documents_after=documents_after,
            compacted=compacted,
            columns_by_table=columns_by_table,
            manifest_factoring=manifest_factoring,
        )
        receipt_sha256 = _embed_compaction_manifest(
            connection,
            schema_name=schema_name,
            core=core,
        )
        _drop_progress_tables(connection, schema_name=schema_name)
        LOGGER.info("catalog compaction: running source-independent verification")
        verification = verify_compacted_catalog(
            connection,
            schema_name=schema_name,
            required_writable_tables=required_tables,
        )
        if verification.receipt_sha256 != receipt_sha256:
            raise CatalogCompactionError("compaction receipt changed before commit")
        connection.execute("COMMIT")
        transaction_open = False
        LOGGER.info("catalog compaction: committed receipt %s", receipt_sha256)
    except BaseException:
        if transaction_open:
            connection.execute("ROLLBACK")
        raise
    _compaction_manifest_committed()
    return CatalogCompaction(
        schema_name=schema_name,
        documents_before=documents_before,
        documents_after=documents_after,
        tables=tuple(newly_compacted),
        manifest_factoring=manifest_factoring,
        receipt_sha256=receipt_sha256,
    )
