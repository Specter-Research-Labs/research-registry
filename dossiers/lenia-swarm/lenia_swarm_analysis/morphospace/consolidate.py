from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import duckdb
from duckdb import DuckDBPyConnection

from .schema import SCHEMA_VERSION, read_schema_version
from .warehouse import file_sha256

CONSOLIDATION_FORMAT = "lenia-morphospace-consolidation-v1"
CATALOG_SCHEMA = "catalog"
METADATA_SCHEMA = "consolidation"
SOURCE_ROWID_COLUMN = "_source_rowid"
ROW_DIGEST_ALGORITHM = "duckdb-hash64-xor-and-hugeint-sum-v1"
CATALOG_DIGEST_ALGORITHM = "sqlite-type-tagged-row-stream-sha256-v1"
RECEIPT_CANONICALIZATION = "json-sort-keys-compact-ascii-v1"
SQLITE_STREAM_BATCH_SIZE = 4096
CONSOLIDATION_MEMORY_LIMIT = "8 GiB"
CONSOLIDATION_THREADS = 1
COMPACT_CANDIDATE_ROW_BATCH_SIZE = 65_536
COMPACT_CANDIDATE_DOCUMENT_BATCH_BYTES = 128 * 1024**2
COMPACT_CANDIDATE_DOCUMENT_BATCH_IDS = 512


class ConsolidationError(RuntimeError):
    pass


class ConsolidationVerificationError(ConsolidationError):
    pass


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size_bytes: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def read(cls, path: Path) -> FileIdentity:
        stat = path.stat()
        return cls(
            device=stat.st_dev,
            inode=stat.st_ino,
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            changed_ns=stat.st_ctime_ns,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "device": self.device,
            "inode": self.inode,
            "sizeBytes": self.size_bytes,
            "modifiedNs": self.modified_ns,
            "changedNs": self.changed_ns,
        }


@dataclass(frozen=True)
class SQLiteTablePlan:
    name: str
    columns: tuple[str, ...]
    declared_types: tuple[str, ...]
    primary_key: tuple[str, ...]
    rowid_alias: str | None

    def as_dict(
        self,
        digest: dict[str, object],
        column_types: tuple[str, ...],
        profile: SQLiteTableProfile,
    ) -> dict[str, object]:
        return {
            "columns": list(self.columns),
            "columnTypes": list(column_types),
            "declaredTypes": list(self.declared_types),
            "affinities": list(profile.affinities),
            "storageClasses": [list(values) for values in profile.storage_classes],
            "importMode": profile.import_mode,
            "primaryKey": list(self.primary_key),
            "sourceRowidAlias": self.rowid_alias,
            "digest": digest,
        }


@dataclass(frozen=True)
class SQLiteTableProfile:
    affinities: tuple[str, ...]
    storage_classes: tuple[tuple[str, ...], ...]
    import_mode: str
    target_types: tuple[str, ...]


@dataclass(frozen=True)
class SQLiteCatalog:
    tables: tuple[SQLiteTablePlan, ...]
    master_objects: tuple[tuple[int, str, str, str, int, str | None], ...]


@dataclass(frozen=True)
class _CompactCandidateColumn:
    name: str
    backing_name: str
    payload: bool


@dataclass(frozen=True)
class _CompactCandidateLayout:
    database_name: str
    backing_table: str
    columns: tuple[_CompactCandidateColumn, ...]


@dataclass(frozen=True)
class ConsolidationResult:
    warehouse_source: Path
    compendium_source: Path
    destination_path: Path
    warehouse_sha256: str
    compendium_sha256: str
    destination_sha256: str
    warehouse_identity: FileIdentity
    compendium_identity: FileIdentity
    destination_identity: FileIdentity
    receipt_sha256: str
    imported_row_counts: dict[str, int]
    warehouse_row_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "format": CONSOLIDATION_FORMAT,
            "warehouseSource": {
                "path": str(self.warehouse_source),
                "sha256": self.warehouse_sha256,
                "identity": self.warehouse_identity.as_dict(),
            },
            "compendiumSource": {
                "path": str(self.compendium_source),
                "sha256": self.compendium_sha256,
                "identity": self.compendium_identity.as_dict(),
            },
            "destination": {
                "path": str(self.destination_path),
                "sha256": self.destination_sha256,
                "identity": self.destination_identity.as_dict(),
            },
            "receiptSha256": self.receipt_sha256,
            "catalogSchema": CATALOG_SCHEMA,
            "importedRowCounts": self.imported_row_counts,
            "warehouseRowCounts": self.warehouse_row_counts,
            "derivedRecomputationPerformed": False,
        }
        payload["externalReceiptSha256"] = _canonical_sha256(payload)
        return payload


@dataclass(frozen=True)
class ConsolidationVerification:
    database_path: Path
    database_sha256: str
    database_identity: FileIdentity
    receipt_sha256: str
    imported_row_counts: dict[str, int]
    warehouse_row_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "format": CONSOLIDATION_FORMAT,
            "verified": True,
            "database": {
                "path": str(self.database_path),
                "sha256": self.database_sha256,
                "identity": self.database_identity.as_dict(),
            },
            "receiptSha256": self.receipt_sha256,
            "importedRowCounts": self.imported_row_counts,
            "warehouseRowCounts": self.warehouse_row_counts,
            "derivedRecomputationPerformed": False,
        }
        payload["externalReceiptSha256"] = _canonical_sha256(payload)
        return payload


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _quote_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def _remove_temp_directory(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _configure_resource_bounds(
    connection: DuckDBPyConnection,
    *,
    temp_directory: Path,
) -> None:
    connection.execute(f"SET memory_limit={_quote_literal(CONSOLIDATION_MEMORY_LIMIT)}")
    connection.execute(f"SET threads={CONSOLIDATION_THREADS}")
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET temp_directory=?", [str(temp_directory)])


def _assert_identity(path: Path, expected: FileIdentity, *, stage: str) -> None:
    actual = FileIdentity.read(path)
    if actual != expected:
        raise ConsolidationError(f"{path}: source identity changed {stage}")


def _nonempty_sidecar(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _assert_warehouse_wal_free(path: Path, *, stage: str) -> None:
    wal_path = Path(f"{path}.wal")
    if _nonempty_sidecar(wal_path):
        raise ConsolidationError(
            f"{path}: nonempty DuckDB WAL found {stage}; checkpoint the warehouse first"
        )


def _assert_sqlite_sidecars_clean(path: Path, *, stage: str) -> None:
    for suffix, label in (("-wal", "WAL"), ("-journal", "rollback journal")):
        sidecar = Path(f"{path}{suffix}")
        if _nonempty_sidecar(sidecar):
            raise ConsolidationError(
                f"{path}: nonempty SQLite {label} found {stage}; checkpoint it first"
            )


def _cleanup_sqlite_snapshot(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal", ".wal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _create_verified_sqlite_snapshot(
    source: Path,
    snapshot: Path,
    *,
    source_sha256: str,
    source_identity: FileIdentity,
) -> None:
    try:
        shutil.copyfile(source, snapshot)
        if file_sha256(snapshot) != source_sha256:
            raise ConsolidationVerificationError("private SQLite snapshot SHA-256 mismatch")
        _assert_identity(source, source_identity, stage="while snapshotting")
    except BaseException:
        _cleanup_sqlite_snapshot(snapshot)
        raise


def _sqlite_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _rowid_alias(columns: tuple[str, ...], ddl: str | None) -> str | None:
    if ddl is not None and re.search(r"\bWITHOUT\s+ROWID\b", ddl, flags=re.IGNORECASE):
        return None
    occupied = {column.casefold() for column in columns}
    for alias in ("rowid", "_rowid_", "oid"):
        if alias.casefold() not in occupied:
            return alias
    raise ConsolidationError(
        "SQLite table shadows rowid, _rowid_, and oid; its physical rowid is inaccessible"
    )


def _read_sqlite_catalog(path: Path) -> SQLiteCatalog:
    connection = _sqlite_read_only(path)
    try:
        raw_master = connection.execute(
            "SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master ORDER BY rowid"
        ).fetchall()
        master_objects = tuple(
            (
                ordinal,
                str(object_type),
                str(name),
                str(table_name),
                int(root_page),
                None if ddl is None else str(ddl),
            )
            for ordinal, (object_type, name, table_name, root_page, ddl) in enumerate(raw_master)
        )
        table_rows = connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name COLLATE BINARY
            """
        ).fetchall()
        tables: list[SQLiteTablePlan] = []
        for raw_name, raw_ddl in table_rows:
            name = str(raw_name)
            cursor = connection.execute(f"SELECT * FROM {_quote_identifier(name)} LIMIT 0")
            columns = tuple(str(column[0]) for column in (cursor.description or ()))
            xinfo = connection.execute(f"PRAGMA table_xinfo({_quote_identifier(name)})").fetchall()
            declared_by_name = {str(row[1]): str(row[2] or "") for row in xinfo}
            primary_key = tuple(
                str(row[1])
                for row in sorted(xinfo, key=lambda value: int(value[5]) or len(xinfo) + 1)
                if int(row[5]) > 0
            )
            try:
                declared_types = tuple(declared_by_name[column] for column in columns)
            except KeyError as exc:
                raise ConsolidationError(
                    f"SQLite table {name!r} exposes a column absent from table_xinfo"
                ) from exc
            if SOURCE_ROWID_COLUMN.casefold() in {column.casefold() for column in columns}:
                raise ConsolidationError(
                    f"SQLite table {name!r} already has reserved column {SOURCE_ROWID_COLUMN!r}"
                )
            ddl = None if raw_ddl is None else str(raw_ddl)
            tables.append(
                SQLiteTablePlan(
                    name=name,
                    columns=columns,
                    declared_types=declared_types,
                    primary_key=primary_key,
                    rowid_alias=_rowid_alias(columns, ddl),
                )
            )
        return SQLiteCatalog(tables=tuple(tables), master_objects=master_objects)
    finally:
        connection.close()


def _table_names(connection: DuckDBPyConnection, schema: str) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = ? AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            [schema],
        ).fetchall()
    )


def _table_columns(
    connection: DuckDBPyConnection,
    schema: str,
    table_name: str,
) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table_name],
        ).fetchall()
    )


def _table_column_types(
    connection: DuckDBPyConnection,
    schema: str,
    table_name: str,
) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table_name],
        ).fetchall()
    )


def _table_layouts(
    connection: DuckDBPyConnection,
    schema: str,
) -> dict[str, dict[str, list[str]]]:
    return {
        table_name: {
            "columns": list(_table_columns(connection, schema, table_name)),
            "columnTypes": list(_table_column_types(connection, schema, table_name)),
        }
        for table_name in _table_names(connection, schema)
    }


def _warehouse_definitions(connection: DuckDBPyConnection) -> dict[str, dict[str, str]]:
    tables = {
        str(name): str(sql)
        for name, sql in connection.execute(
            """
            SELECT table_name, sql
            FROM duckdb_tables()
            WHERE schema_name = 'main' AND NOT internal
            ORDER BY table_name
            """
        ).fetchall()
    }
    views = {
        str(name): str(sql)
        for name, sql in connection.execute(
            """
            SELECT view_name, sql
            FROM duckdb_views()
            WHERE schema_name = 'main' AND NOT internal
            ORDER BY view_name
            """
        ).fetchall()
    }
    return {"tables": tables, "views": views}


def _logical_inventory(connection: DuckDBPyConnection) -> dict[str, object]:
    schemas = [
        str(row[0])
        for row in connection.execute(
            """
            SELECT schema_name
            FROM duckdb_schemas()
            WHERE database_name = current_database() AND NOT internal
            ORDER BY schema_name
            """
        ).fetchall()
    ]

    def definitions(function_name: str, object_column: str) -> dict[str, str]:
        return {
            f"{schema_name}.{object_name}": str(sql)
            for schema_name, object_name, sql in connection.execute(
                f"""
                SELECT schema_name, {object_column}, sql
                FROM {function_name}()
                WHERE database_name = current_database()
                ORDER BY schema_name, {object_column}
                """
            ).fetchall()
        }

    user_types = [
        {
            "schema": str(row[0]),
            "name": str(row[1]),
            "logicalType": str(row[2]),
            "labels": None if row[3] is None else [str(value) for value in row[3]],
        }
        for row in connection.execute(
            """
            SELECT schema_name, type_name, logical_type, labels
            FROM duckdb_types()
            WHERE database_name = current_database() AND NOT internal
            ORDER BY schema_name, type_name
            """
        ).fetchall()
    ]
    functions = [
        {
            "schema": str(row[0]),
            "name": str(row[1]),
            "functionType": str(row[2]),
            "definition": None if row[3] is None else str(row[3]),
            "parameters": [str(value) for value in row[4]],
            "parameterTypes": [str(value) for value in row[5]],
            "returnType": None if row[6] is None else str(row[6]),
        }
        for row in connection.execute(
            """
            SELECT schema_name, function_name, function_type, macro_definition,
                   parameters, parameter_types, return_type
            FROM duckdb_functions()
            WHERE database_name = current_database() AND NOT internal
            ORDER BY schema_name, function_name, function_type
            """
        ).fetchall()
    ]
    return {
        "schemas": schemas,
        "tables": definitions("duckdb_tables", "table_name"),
        "views": definitions("duckdb_views", "view_name"),
        "indexes": definitions("duckdb_indexes", "index_name"),
        "sequences": definitions("duckdb_sequences", "sequence_name"),
        "types": user_types,
        "functions": functions,
    }


def _inventory_outside_catalog(inventory: dict[str, object]) -> dict[str, object]:
    def entry_schema(value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        schema = cast(dict[str, object], value).get("schema")
        return schema if isinstance(schema, str) else None

    def definitions(name: str) -> dict[str, str]:
        values = _require_mapping(inventory.get(name), label=f"inventory.{name}")
        return {
            str(key): str(value)
            for key, value in values.items()
            if not str(key).startswith(f"{CATALOG_SCHEMA}.")
        }

    raw_types = inventory.get("types")
    raw_functions = inventory.get("functions")
    if not isinstance(raw_types, list) or not isinstance(raw_functions, list):
        raise ConsolidationVerificationError("logical inventory extensions are invalid")
    return {
        "schemas": inventory.get("schemas"),
        "tables": definitions("tables"),
        "views": definitions("views"),
        "indexes": definitions("indexes"),
        "sequences": definitions("sequences"),
        "types": [value for value in raw_types if entry_schema(value) != CATALOG_SCHEMA],
        "functions": [value for value in raw_functions if entry_schema(value) != CATALOG_SCHEMA],
    }


def _preserves_inventory_outside_catalog(
    actual: dict[str, object],
    expected: dict[str, object],
) -> bool:
    actual_base = _inventory_outside_catalog(actual)
    expected_base = _inventory_outside_catalog(expected)
    actual_schemas = actual_base.get("schemas")
    expected_schemas = expected_base.get("schemas")
    if not isinstance(actual_schemas, list) or not isinstance(expected_schemas, list):
        return False
    if not set(expected_schemas) <= set(actual_schemas):
        return False
    base_schemas = set(expected_schemas) - {CATALOG_SCHEMA}
    for name in ("tables", "views", "indexes", "sequences"):
        expected_definitions = _require_mapping(expected_base.get(name), label=f"expected.{name}")
        base_schemas.update(key.partition(".")[0] for key in expected_definitions)
    for name in ("tables", "views", "indexes", "sequences"):
        actual_definitions = _require_mapping(actual_base.get(name), label=f"actual.{name}")
        expected_definitions = _require_mapping(expected_base.get(name), label=f"expected.{name}")
        actual_base_definitions = {
            key: value
            for key, value in actual_definitions.items()
            if key.partition(".")[0] in base_schemas
        }
        if actual_base_definitions != expected_definitions:
            return False
    for name in ("types", "functions"):
        actual_values = actual_base.get(name)
        expected_values = expected_base.get(name)
        if not isinstance(actual_values, list) or not isinstance(expected_values, list):
            return False
        actual_base_values = [
            value
            for value in actual_values
            if (
                isinstance(value, dict)
                and cast(dict[str, object], value).get("schema") in base_schemas
            )
        ]
        if actual_base_values != expected_values:
            return False
    return True


def _digest_query(
    connection: DuckDBPyConnection,
    qualified_table: str,
    expressions: tuple[str, ...],
) -> dict[str, object]:
    if not expressions:
        raise ConsolidationError(f"cannot digest a columnless table: {qualified_table}")
    row_hash = f"hash({', '.join(expressions)})"
    row = connection.execute(
        f"""
        SELECT
            count(*),
            coalesce(bit_xor({row_hash}), 0::UBIGINT),
            cast(coalesce(sum(cast({row_hash} AS HUGEINT)), 0::HUGEINT) AS VARCHAR)
        FROM {qualified_table}
        """
    ).fetchone()
    if row is None:
        raise AssertionError(f"digest query returned no row for {qualified_table}")
    return {
        "rowCount": int(row[0]),
        "rowHashXor64": str(row[1]),
        "rowHashSum128": str(row[2]),
    }


def _duckdb_table_digests(
    connection: DuckDBPyConnection,
    schema: str,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for table_name in _table_names(connection, schema):
        columns = _table_columns(connection, schema, table_name)
        result[table_name] = _digest_query(
            connection,
            f"{_quote_identifier(schema)}.{_quote_identifier(table_name)}",
            tuple(_quote_identifier(column) for column in columns),
        )
    return result


def _sqlite_affinity(declared_type: str) -> str:
    normalized = declared_type.upper()
    if "INT" in normalized:
        return "INTEGER"
    if any(token in normalized for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not normalized or "BLOB" in normalized:
        return "BLOB"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _frame_value(storage_class: str, value: object) -> bytes:
    if storage_class == "null":
        payload = b""
        tag = b"N"
    elif storage_class == "integer":
        if not isinstance(value, int):
            raise ConsolidationError("SQLite INTEGER value did not decode as int")
        payload = struct.pack(">q", value)
        tag = b"I"
    elif storage_class == "real":
        if not isinstance(value, float):
            raise ConsolidationError("SQLite REAL value did not decode as float")
        payload = struct.pack(">d", value)
        tag = b"R"
    elif storage_class == "text":
        if isinstance(value, str):
            payload = value.encode("utf-8")
        elif isinstance(value, bytes):
            payload = value
        else:
            raise ConsolidationError("SQLite TEXT value did not decode as UTF-8 bytes")
        tag = b"T"
    elif storage_class == "blob":
        if isinstance(value, memoryview):
            payload = value.tobytes()
        elif isinstance(value, bytes):
            payload = value
        else:
            raise ConsolidationError("SQLite BLOB value did not decode as bytes")
        tag = b"B"
    else:
        raise ConsolidationError(f"unsupported SQLite storage class: {storage_class!r}")
    return tag + len(payload).to_bytes(8, "big") + payload


def _python_storage_class(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "integer"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    if isinstance(value, str):
        return "text"
    if isinstance(value, (bytes, memoryview)):
        return "blob"
    raise ConsolidationVerificationError(
        f"candidate value has unsupported Python type: {type(value).__name__}"
    )


def _stream_order(plan: SQLiteTablePlan, *, candidate: bool) -> str:
    if plan.rowid_alias is not None:
        return (
            _quote_identifier(SOURCE_ROWID_COLUMN)
            if candidate
            else _quote_identifier(plan.rowid_alias)
        )
    if not plan.primary_key:
        raise ConsolidationError(
            f"WITHOUT ROWID table {plan.name!r} has no declared primary-key order"
        )
    return ", ".join(_quote_identifier(column) for column in plan.primary_key)


def _finish_stream_digest(digest: Any, row_count: int) -> dict[str, object]:
    digest.update(b"E" + row_count.to_bytes(8, "big"))
    return {"rowCount": row_count, "rowStreamSha256": digest.hexdigest()}


def _profile_sqlite_snapshot(
    path: Path,
    catalog: SQLiteCatalog,
) -> tuple[dict[str, SQLiteTableProfile], dict[str, dict[str, object]]]:
    connection = _sqlite_read_only(path)
    connection.text_factory = bytes
    try:
        profiles: dict[str, SQLiteTableProfile] = {}
        digests: dict[str, dict[str, object]] = {}
        for plan in catalog.tables:
            rowid = "NULL" if plan.rowid_alias is None else _quote_identifier(plan.rowid_alias)
            typed_values = ", ".join(
                f"typeof({_quote_identifier(column)}), {_quote_identifier(column)}"
                for column in plan.columns
            )
            select_values = f"{rowid}, {typed_values}" if typed_values else rowid
            cursor = connection.execute(
                f"SELECT {select_values} FROM {_quote_identifier(plan.name)} "
                f"ORDER BY {_stream_order(plan, candidate=False)}"
            )
            storage_classes = [set[str]() for _ in plan.columns]
            digest = hashlib.sha256()
            digest.update(b"LSC1" + (len(plan.columns) + 1).to_bytes(8, "big"))
            row_count = 0
            while rows := cursor.fetchmany(SQLITE_STREAM_BATCH_SIZE):
                for row in rows:
                    digest.update(b"R")
                    rowid_value = row[0]
                    rowid_storage = "null" if rowid_value is None else "integer"
                    digest.update(_frame_value(rowid_storage, rowid_value))
                    offset = 1
                    for index in range(len(plan.columns)):
                        raw_storage_class = row[offset]
                        storage_class = (
                            raw_storage_class.decode("ascii")
                            if isinstance(raw_storage_class, bytes)
                            else str(raw_storage_class)
                        )
                        value = row[offset + 1]
                        storage_classes[index].add(storage_class)
                        digest.update(_frame_value(storage_class, value))
                        offset += 2
                    row_count += 1

            affinities = tuple(_sqlite_affinity(value) for value in plan.declared_types)
            import_mode = (
                "native-sqlite-stream"
                if any(not declared_type for declared_type in plan.declared_types)
                else "duckdb-sqlite-attach"
            )
            target_types: list[str] = []
            for column, declared_type, affinity, observed in zip(
                plan.columns,
                plan.declared_types,
                affinities,
                storage_classes,
                strict=True,
            ):
                nonnull = observed - {"null"}
                if affinity == "NUMERIC" and nonnull:
                    raise ConsolidationError(
                        f"SQLite table {plan.name!r} column {column!r} has NUMERIC affinity "
                        f"with current storage classes {sorted(nonnull)}; refusing a coercive import"
                    )
                allowed = {
                    "INTEGER": {"integer"},
                    "REAL": {"real"},
                    "TEXT": {"text"},
                    "BLOB": {"blob"},
                    "NUMERIC": set(),
                }[affinity]
                if declared_type and not nonnull <= allowed:
                    raise ConsolidationError(
                        f"SQLite table {plan.name!r} column {column!r} has {affinity} affinity "
                        f"but current storage classes {sorted(nonnull)}"
                    )
                if not declared_type:
                    if len(nonnull) > 1:
                        raise ConsolidationError(
                            f"untyped SQLite column {plan.name}.{column} mixes storage classes "
                            f"{sorted(nonnull)}"
                        )
                    storage_class = next(iter(nonnull), "blob")
                    target_types.append(
                        {
                            "integer": "BIGINT",
                            "real": "DOUBLE",
                            "text": "VARCHAR",
                            "blob": "BLOB",
                        }[storage_class]
                    )
                else:
                    target_types.append(
                        {
                            "INTEGER": "BIGINT",
                            "REAL": "DOUBLE",
                            "TEXT": "VARCHAR",
                            "BLOB": "BLOB",
                            "NUMERIC": "VARCHAR",
                        }[affinity]
                    )
            profiles[plan.name] = SQLiteTableProfile(
                affinities=affinities,
                storage_classes=tuple(tuple(sorted(values)) for values in storage_classes),
                import_mode=import_mode,
                target_types=tuple(target_types),
            )
            digests[plan.name] = _finish_stream_digest(digest, row_count)
        return profiles, digests
    finally:
        connection.close()


def _logical_candidate_stream_digest(
    connection: DuckDBPyConnection,
    plan: SQLiteTablePlan,
) -> dict[str, object]:
    columns = (SOURCE_ROWID_COLUMN, *plan.columns)
    cursor = connection.execute(
        f"SELECT {', '.join(_quote_identifier(column) for column in columns)} "
        f"FROM {_quote_identifier(CATALOG_SCHEMA)}.{_quote_identifier(plan.name)} "
        f"ORDER BY {_stream_order(plan, candidate=True)}"
    )
    digest = hashlib.sha256()
    digest.update(b"LSC1" + len(columns).to_bytes(8, "big"))
    row_count = 0
    while rows := cursor.fetchmany(SQLITE_STREAM_BATCH_SIZE):
        for row in rows:
            digest.update(b"R")
            for value in row:
                digest.update(_frame_value(_python_storage_class(value), value))
            row_count += 1
    return _finish_stream_digest(digest, row_count)


def _compact_candidate_layout(
    connection: DuckDBPyConnection,
    plan: SQLiteTablePlan,
) -> _CompactCandidateLayout | None:
    if plan.rowid_alias is None:
        return None
    support_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_catalog = current_database()
          AND table_schema = ?
          AND table_name IN ('compaction_tables', 'compaction_columns',
                             'json_documents', 'json_document_templates')
          AND table_type = 'BASE TABLE'
        """,
        [CATALOG_SCHEMA],
    ).fetchone()
    if support_count is None or int(support_count[0]) != 4:
        return None
    table_rows = connection.execute(
        f"""
        SELECT backing_table
        FROM {_quote_identifier(CATALOG_SCHEMA)}.compaction_tables
        WHERE source_schema = ? AND source_table = ?
        """,
        [CATALOG_SCHEMA, plan.name],
    ).fetchall()
    if len(table_rows) != 1:
        return None
    backing_table = str(table_rows[0][0])
    raw_columns = connection.execute(
        f"""
        SELECT ordinal_position, column_name, data_type, is_nullable,
               column_default, is_payload, backing_column
        FROM {_quote_identifier(CATALOG_SCHEMA)}.compaction_columns
        WHERE source_schema = ? AND source_table = ?
        ORDER BY ordinal_position
        """,
        [CATALOG_SCHEMA, plan.name],
    ).fetchall()
    expected_names = (SOURCE_ROWID_COLUMN, *plan.columns)
    if tuple(str(row[1]) for row in raw_columns) != expected_names:
        return None

    from . import compact_catalog as compact_catalog_module

    compact_columns = tuple(
        compact_catalog_module.ColumnSpec(
            name=str(name),
            data_type=str(data_type),
            nullable=bool(nullable),
            default=None if default is None else str(default),
            ordinal=int(ordinal),
            payload=bool(payload),
            backing_column=None if backing_column is None else str(backing_column),
        )
        for ordinal, name, data_type, nullable, default, payload, backing_column in raw_columns
    )
    expected_view = compact_catalog_module._detail_query(
        schema_name=CATALOG_SCHEMA,
        backing_table=backing_table,
        columns=compact_columns,
    )
    actual_view = (
        f"SELECT * FROM {_quote_identifier(CATALOG_SCHEMA)}.{_quote_identifier(plan.name)}"
    )
    expected_document_values = compact_catalog_module._document_values_query(
        schema_name=CATALOG_SCHEMA
    )
    actual_document_values = (
        f"SELECT * FROM {_quote_identifier(CATALOG_SCHEMA)}."
        f"{_quote_identifier(compact_catalog_module.DOCUMENT_VALUES_VIEW)}"
    )
    try:
        if compact_catalog_module._query_layout(
            connection, actual_view
        ) != compact_catalog_module._query_layout(
            connection, expected_view
        ) or compact_catalog_module._normalized_query_plan(
            connection, actual_view
        ) != compact_catalog_module._normalized_query_plan(connection, expected_view):
            return None
        if compact_catalog_module._query_layout(
            connection, actual_document_values
        ) != compact_catalog_module._query_layout(
            connection, expected_document_values
        ) or compact_catalog_module._normalized_query_plan(
            connection, actual_document_values
        ) != compact_catalog_module._normalized_query_plan(connection, expected_document_values):
            return None
    except compact_catalog_module.CatalogCompactionError:
        return None
    template_count = connection.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(CATALOG_SCHEMA)}."
        f"{_quote_identifier(compact_catalog_module.DOCUMENT_TEMPLATE_TABLE)}"
    ).fetchone()
    if template_count is None or int(template_count[0]) != 0:
        return None
    current_database = connection.execute("SELECT current_database()").fetchone()
    if current_database is None or not isinstance(current_database[0], str):
        raise ConsolidationVerificationError("candidate database name is unavailable")
    columns: list[_CompactCandidateColumn] = []
    for column in compact_columns:
        backing_name = column.backing_column if column.payload else column.name
        if backing_name is None:
            return None
        columns.append(
            _CompactCandidateColumn(
                name=column.name,
                backing_name=backing_name,
                payload=column.payload,
            )
        )
    return _CompactCandidateLayout(
        database_name=str(current_database[0]),
        backing_table=backing_table,
        columns=tuple(columns),
    )


def _compact_document_byte_lengths(
    connection: DuckDBPyConnection,
    *,
    documents: str,
    document_ids: set[int],
) -> dict[int, int]:
    if not document_ids:
        return {}
    rows = connection.execute(
        f"""
        SELECT document_id, byte_length
        FROM {documents}
        WHERE document_id IN (SELECT unnest(?::BIGINT[]))
        """,
        [sorted(document_ids)],
    ).fetchall()
    result = {}
    for document_id, byte_length in rows:
        if byte_length is None or int(byte_length) < 0:
            raise ConsolidationVerificationError(
                "compacted catalog document byte length is invalid"
            )
        result[int(document_id)] = int(byte_length)
    if result.keys() != document_ids:
        raise ConsolidationVerificationError(
            "compacted catalog row references a missing or templated document"
        )
    return result


def _compact_row_document_ids(
    row: tuple[object, ...],
    columns: tuple[_CompactCandidateColumn, ...],
) -> set[int]:
    return {
        int(value)
        for value, column in zip(row, columns, strict=True)
        if column.payload and value is not None
    }


def _compact_document_groups(
    rows: list[tuple[object, ...]],
    *,
    columns: tuple[_CompactCandidateColumn, ...],
    byte_lengths: dict[int, int],
) -> list[list[tuple[object, ...]]]:
    groups: list[list[tuple[object, ...]]] = []
    current_rows: list[tuple[object, ...]] = []
    current_ids: set[int] = set()
    current_bytes = 0
    for row in rows:
        row_ids = _compact_row_document_ids(row, columns)
        added_ids = row_ids - current_ids
        added_bytes = sum(byte_lengths[document_id] for document_id in added_ids)
        if current_rows and (
            len(current_ids | row_ids) > COMPACT_CANDIDATE_DOCUMENT_BATCH_IDS
            or current_bytes + added_bytes > COMPACT_CANDIDATE_DOCUMENT_BATCH_BYTES
        ):
            groups.append(current_rows)
            current_rows = []
            current_ids = set()
            current_bytes = 0
            added_ids = row_ids
            added_bytes = sum(byte_lengths[document_id] for document_id in added_ids)
        current_rows.append(row)
        current_ids.update(added_ids)
        current_bytes += added_bytes
    if current_rows:
        groups.append(current_rows)
    return groups


def _compact_document_texts(
    connection: DuckDBPyConnection,
    *,
    documents: str,
    document_ids: set[int],
) -> dict[int, str]:
    if not document_ids:
        return {}
    rows = connection.execute(
        f"""
        SELECT document_id, document_text
        FROM {documents}
        WHERE document_id IN (SELECT unnest(?::BIGINT[]))
        """,
        [sorted(document_ids)],
    ).fetchall()
    result = {
        int(document_id): str(document_text)
        for document_id, document_text in rows
        if document_text is not None
    }
    if result.keys() != document_ids:
        raise ConsolidationVerificationError(
            "compacted catalog row references a missing or templated document"
        )
    return result


def _compact_candidate_stream_digest(
    connection: DuckDBPyConnection,
    plan: SQLiteTablePlan,
    layout: _CompactCandidateLayout,
) -> dict[str, object]:
    database = _quote_identifier(layout.database_name)
    schema = _quote_identifier(CATALOG_SCHEMA)
    backing = f"{database}.{schema}.{_quote_identifier(layout.backing_table)}"
    documents = f"{database}.{schema}.{_quote_identifier('json_documents')}"
    source_rowid = _quote_identifier(SOURCE_ROWID_COLUMN)
    projected = ", ".join(_quote_identifier(column.backing_name) for column in layout.columns)
    key_cursor = connection.execute(f"SELECT {source_rowid} FROM {backing} ORDER BY {source_rowid}")
    worker = connection.cursor()
    digest = hashlib.sha256()
    digest.update(b"LSC1" + len(layout.columns).to_bytes(8, "big"))
    row_count = 0
    previous_rowid: int | None = None
    try:
        while key_rows := key_cursor.fetchmany(COMPACT_CANDIDATE_ROW_BATCH_SIZE):
            rowids = [row[0] for row in key_rows]
            if not all(isinstance(rowid, int) for rowid in rowids):
                raise ConsolidationVerificationError(
                    f"compacted catalog row order is invalid: {plan.name}"
                )
            typed_rowids = cast(list[int], rowids)
            if previous_rowid is not None and typed_rowids[0] <= previous_rowid:
                raise ConsolidationVerificationError(
                    f"compacted catalog row order is invalid: {plan.name}"
                )
            if any(
                left >= right for left, right in zip(typed_rowids, typed_rowids[1:], strict=False)
            ):
                raise ConsolidationVerificationError(
                    f"compacted catalog row order is invalid: {plan.name}"
                )
            rows = worker.execute(
                f"""
                SELECT {projected}
                FROM {backing}
                WHERE {source_rowid} BETWEEN ? AND ?
                ORDER BY {source_rowid}
                """,
                [typed_rowids[0], typed_rowids[-1]],
            ).fetchall()
            if [row[0] for row in rows] != typed_rowids:
                raise ConsolidationVerificationError(
                    f"compacted catalog row range changed: {plan.name}"
                )
            all_document_ids = {
                document_id
                for row in rows
                for document_id in _compact_row_document_ids(row, layout.columns)
            }
            byte_lengths = _compact_document_byte_lengths(
                worker,
                documents=documents,
                document_ids=all_document_ids,
            )
            for group in _compact_document_groups(
                rows,
                columns=layout.columns,
                byte_lengths=byte_lengths,
            ):
                group_document_ids = {
                    document_id
                    for row in group
                    for document_id in _compact_row_document_ids(row, layout.columns)
                }
                document_texts = _compact_document_texts(
                    worker,
                    documents=documents,
                    document_ids=group_document_ids,
                )
                for row in group:
                    digest.update(b"R")
                    for value, column in zip(row, layout.columns, strict=True):
                        logical_value = (
                            document_texts[int(value)]
                            if column.payload and value is not None
                            else value
                        )
                        digest.update(
                            _frame_value(
                                _python_storage_class(logical_value),
                                logical_value,
                            )
                        )
                    row_count += 1
            previous_rowid = typed_rowids[-1]
    finally:
        worker.close()
    return _finish_stream_digest(digest, row_count)


def _candidate_stream_digest(
    connection: DuckDBPyConnection,
    plan: SQLiteTablePlan,
) -> dict[str, object]:
    layout = _compact_candidate_layout(connection, plan)
    if layout is None:
        return _logical_candidate_stream_digest(connection, plan)
    return _compact_candidate_stream_digest(connection, plan, layout)


def _attach_sqlite(connection: DuckDBPyConnection, path: Path, name: str) -> None:
    connection.execute(
        f"ATTACH {_quote_literal(str(path))} AS {_quote_identifier(name)} (TYPE sqlite, READ_ONLY)"
    )


def _copy_sqlite_tables(
    connection: DuckDBPyConnection,
    snapshot: Path,
    catalog: SQLiteCatalog,
    profiles: dict[str, SQLiteTableProfile],
    *,
    attached_name: str,
) -> None:
    for plan in catalog.tables:
        profile = profiles[plan.name]
        if profile.import_mode == "native-sqlite-stream":
            definitions = [f"{_quote_identifier(SOURCE_ROWID_COLUMN)} BIGINT"]
            definitions.extend(
                f"{_quote_identifier(column)} {column_type}"
                for column, column_type in zip(
                    plan.columns,
                    profile.target_types,
                    strict=True,
                )
            )
            connection.execute(
                f"CREATE TABLE {_quote_identifier(CATALOG_SCHEMA)}.{_quote_identifier(plan.name)} "
                f"({', '.join(definitions)})"
            )
            source = _sqlite_read_only(snapshot)
            try:
                rowid = "NULL" if plan.rowid_alias is None else _quote_identifier(plan.rowid_alias)
                cursor = source.execute(
                    f"SELECT {rowid}, * FROM {_quote_identifier(plan.name)} "
                    f"ORDER BY {_stream_order(plan, candidate=False)}"
                )
                placeholders = ", ".join("?" for _ in range(len(plan.columns) + 1))
                insert_sql = (
                    f"INSERT INTO {_quote_identifier(CATALOG_SCHEMA)}."
                    f"{_quote_identifier(plan.name)} VALUES ({placeholders})"
                )
                while rows := cursor.fetchmany(SQLITE_STREAM_BATCH_SIZE):
                    connection.executemany(insert_sql, rows)
            finally:
                source.close()
            continue
        rowid = (
            "NULL::BIGINT"
            if plan.rowid_alias is None
            else f"CAST({_quote_identifier(plan.rowid_alias)} AS BIGINT)"
        )
        connection.execute(
            f"""
            CREATE TABLE {_quote_identifier(CATALOG_SCHEMA)}.{_quote_identifier(plan.name)} AS
            SELECT {rowid} AS {_quote_identifier(SOURCE_ROWID_COLUMN)}, *
            FROM {_quote_identifier(attached_name)}.{_quote_identifier(plan.name)}
            """
        )


def _sqlite_master_payload(
    rows: tuple[tuple[int, str, str, str, int, str | None], ...],
) -> list[dict[str, object]]:
    return [
        {
            "ordinal": ordinal,
            "type": object_type,
            "name": name,
            "tableName": table_name,
            "rootPage": root_page,
            "ddl": ddl,
        }
        for ordinal, object_type, name, table_name, root_page, ddl in rows
    ]


def _create_metadata_tables(
    connection: DuckDBPyConnection,
    catalog: SQLiteCatalog,
) -> None:
    connection.execute(f"CREATE SCHEMA {_quote_identifier(METADATA_SCHEMA)}")
    connection.execute(
        f"""
        CREATE TABLE {_quote_identifier(METADATA_SCHEMA)}.sqlite_master_objects (
            ordinal BIGINT PRIMARY KEY,
            object_type VARCHAR NOT NULL,
            object_name VARCHAR NOT NULL,
            table_name VARCHAR NOT NULL,
            root_page BIGINT NOT NULL,
            ddl VARCHAR
        )
        """
    )
    if catalog.master_objects:
        connection.executemany(
            f"""
            INSERT INTO {_quote_identifier(METADATA_SCHEMA)}.sqlite_master_objects
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            catalog.master_objects,
        )
    connection.execute(
        f"""
        CREATE TABLE {_quote_identifier(METADATA_SCHEMA)}.manifest (
            receipt_sha256 VARCHAR PRIMARY KEY,
            manifest_json VARCHAR NOT NULL
        )
        """
    )


def _manifest_core(
    *,
    warehouse: Path,
    compendium: Path,
    warehouse_sha256: str,
    compendium_sha256: str,
    warehouse_identity: FileIdentity,
    compendium_identity: FileIdentity,
    warehouse_digests: dict[str, dict[str, object]],
    warehouse_layouts: dict[str, dict[str, list[str]]],
    warehouse_definitions: dict[str, dict[str, str]],
    compendium_digests: dict[str, dict[str, object]],
    catalog_layouts: dict[str, dict[str, list[str]]],
    catalog: SQLiteCatalog,
    profiles: dict[str, SQLiteTableProfile],
    candidate_inventory: dict[str, object],
) -> dict[str, object]:
    return {
        "format": CONSOLIDATION_FORMAT,
        "warehouse": {
            "path": str(warehouse),
            "sha256": warehouse_sha256,
            "identity": warehouse_identity.as_dict(),
            "schemaVersion": SCHEMA_VERSION,
            "tables": {
                table_name: {
                    **warehouse_layouts[table_name],
                    "digest": digest,
                }
                for table_name, digest in warehouse_digests.items()
            },
            "definitions": warehouse_definitions,
        },
        "compendium": {
            "path": str(compendium),
            "sha256": compendium_sha256,
            "identity": compendium_identity.as_dict(),
            "sqliteMasterObjectCount": len(catalog.master_objects),
            "sqliteMasterSha256": _canonical_sha256(_sqlite_master_payload(catalog.master_objects)),
            "tables": {
                plan.name: plan.as_dict(
                    compendium_digests[plan.name],
                    tuple(catalog_layouts[plan.name]["columnTypes"]),
                    profiles[plan.name],
                )
                for plan in catalog.tables
            },
        },
        "layout": {
            "warehouseSchema": "main",
            "catalogSchema": CATALOG_SCHEMA,
            "metadataSchema": METADATA_SCHEMA,
            "sourceRowidColumn": SOURCE_ROWID_COLUMN,
        },
        "warehouseCopiedBeforeCatalogImport": True,
        "derivedRecomputationPerformed": False,
        "candidateLogicalInventory": candidate_inventory,
        "verification": {
            "contentHashAlgorithm": "sha256",
            "receiptCanonicalization": RECEIPT_CANONICALIZATION,
            "rowDigestAlgorithm": ROW_DIGEST_ALGORITHM,
            "catalogDigestAlgorithm": CATALOG_DIGEST_ALGORITHM,
            "duckdbVersion": duckdb.__version__,
            "sqliteVersion": sqlite3.sqlite_version,
        },
    }


def _embed_manifest(connection: DuckDBPyConnection, core: dict[str, object]) -> str:
    receipt_sha256 = _canonical_sha256(core)
    manifest = {**core, "receiptSha256": receipt_sha256}
    connection.execute(
        f"INSERT INTO {_quote_identifier(METADATA_SCHEMA)}.manifest VALUES (?, ?)",
        [receipt_sha256, _canonical_json(manifest)],
    )
    return receipt_sha256


def _read_embedded_manifest(
    connection: DuckDBPyConnection,
) -> tuple[str, dict[str, Any]]:
    metadata_tables = _table_names(connection, METADATA_SCHEMA)
    if metadata_tables != ("manifest", "sqlite_master_objects"):
        raise ConsolidationVerificationError(
            f"unexpected {METADATA_SCHEMA} tables: {list(metadata_tables)}"
        )
    rows = connection.execute(
        f"SELECT receipt_sha256, manifest_json FROM {_quote_identifier(METADATA_SCHEMA)}.manifest"
    ).fetchall()
    if len(rows) != 1:
        raise ConsolidationVerificationError("consolidated database must contain one manifest")
    receipt_sha256 = str(rows[0][0])
    try:
        manifest = json.loads(str(rows[0][1]))
    except json.JSONDecodeError as exc:
        raise ConsolidationVerificationError(
            "embedded consolidation manifest is invalid JSON"
        ) from exc
    if not isinstance(manifest, dict):
        raise ConsolidationVerificationError("embedded consolidation manifest must be an object")
    embedded_receipt = manifest.pop("receiptSha256", None)
    if embedded_receipt != receipt_sha256 or _canonical_sha256(manifest) != receipt_sha256:
        raise ConsolidationVerificationError("embedded consolidation manifest hash mismatch")
    manifest["receiptSha256"] = receipt_sha256
    return receipt_sha256, manifest


def _require_mapping(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConsolidationVerificationError(f"manifest {label} must be an object")
    return cast(dict[str, Any], value)


def _expected_table_digests(
    manifest: dict[str, Any],
    source: str,
) -> dict[str, dict[str, object]]:
    section = _require_mapping(manifest.get(source), label=source)
    tables = _require_mapping(section.get("tables"), label=f"{source}.tables")
    result: dict[str, dict[str, object]] = {}
    for name, raw_table in tables.items():
        table = _require_mapping(raw_table, label=f"{source}.tables.{name}")
        raw_digest = table.get("digest", table)
        digest = _require_mapping(raw_digest, label=f"{source}.tables.{name}.digest")
        result[str(name)] = dict(digest)
    return result


def _expected_table_layouts(
    manifest: dict[str, Any],
    source: str,
) -> dict[str, dict[str, list[str]]]:
    section = _require_mapping(manifest.get(source), label=source)
    tables = _require_mapping(section.get("tables"), label=f"{source}.tables")
    result: dict[str, dict[str, list[str]]] = {}
    for name, raw_table in tables.items():
        table = _require_mapping(raw_table, label=f"{source}.tables.{name}")
        columns = table.get("columns")
        column_types = table.get("columnTypes")
        if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
            raise ConsolidationVerificationError(
                f"manifest {source}.tables.{name}.columns must be a string list"
            )
        if not isinstance(column_types, list) or not all(
            isinstance(column_type, str) for column_type in column_types
        ):
            raise ConsolidationVerificationError(
                f"manifest {source}.tables.{name}.columnTypes must be a string list"
            )
        result[str(name)] = {
            "columns": [str(column) for column in columns],
            "columnTypes": [str(column_type) for column_type in column_types],
        }
    return result


def _digest_row_counts(digests: dict[str, dict[str, object]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for name, digest in digests.items():
        row_count = digest.get("rowCount")
        if not isinstance(row_count, int):
            raise ConsolidationVerificationError(f"table digest row count is invalid: {name}")
        result[name] = row_count
    return result


def _validate_manifest_contract(manifest: dict[str, Any]) -> None:
    if manifest.get("format") != CONSOLIDATION_FORMAT:
        raise ConsolidationVerificationError("unsupported consolidation manifest format")
    verification = _require_mapping(manifest.get("verification"), label="verification")
    expected_algorithms = {
        "contentHashAlgorithm": "sha256",
        "receiptCanonicalization": RECEIPT_CANONICALIZATION,
        "rowDigestAlgorithm": ROW_DIGEST_ALGORITHM,
        "catalogDigestAlgorithm": CATALOG_DIGEST_ALGORITHM,
    }
    expected_keys = {*expected_algorithms, "duckdbVersion", "sqliteVersion"}
    if set(verification) != expected_keys:
        raise ConsolidationVerificationError(
            "consolidation verification contract has unexpected fields"
        )
    if any(verification[key] != value for key, value in expected_algorithms.items()):
        raise ConsolidationVerificationError("unsupported consolidation digest contract")
    for key in ("duckdbVersion", "sqliteVersion"):
        value = verification[key]
        if not isinstance(value, str) or not value.strip():
            raise ConsolidationVerificationError(
                f"consolidation producer provenance is invalid: {key}"
            )


def _verify_published_envelope(
    database: Path,
    *,
    expected_receipt_sha256: str,
) -> dict[str, Any]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        if read_schema_version(connection) != SCHEMA_VERSION:
            raise ConsolidationVerificationError(
                f"published warehouse schema is not v{SCHEMA_VERSION}"
            )
        receipt_sha256, manifest = _read_embedded_manifest(connection)
        if receipt_sha256 != expected_receipt_sha256:
            raise ConsolidationVerificationError("published database receipt mismatch")
        _validate_manifest_contract(manifest)
        expected_inventory = _require_mapping(
            manifest.get("candidateLogicalInventory"),
            label="candidateLogicalInventory",
        )
        if _logical_inventory(connection) != expected_inventory:
            raise ConsolidationVerificationError("published logical-object inventory mismatch")
        return manifest
    finally:
        connection.close()


def _verify_candidate_contents(
    database: Path,
    *,
    expected_receipt_sha256: str | None = None,
    allow_catalog_extensions: bool = False,
) -> tuple[dict[str, Any], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    temp_directory = database.with_name(f".{database.name}.verify-{uuid4().hex}.tmp")
    connection = duckdb.connect(":memory:")
    try:
        _configure_resource_bounds(connection, temp_directory=temp_directory)
        connection.execute(f"ATTACH {_quote_literal(str(database))} AS candidate (READ_ONLY)")
        connection.execute("USE candidate")
        if read_schema_version(connection) != SCHEMA_VERSION:
            raise ConsolidationVerificationError(
                f"candidate warehouse schema is not v{SCHEMA_VERSION}"
            )
        receipt_sha256, manifest = _read_embedded_manifest(connection)
        if expected_receipt_sha256 is not None and receipt_sha256 != expected_receipt_sha256:
            raise ConsolidationVerificationError("candidate receipt changed after construction")
        _validate_manifest_contract(manifest)
        expected_inventory = _require_mapping(
            manifest.get("candidateLogicalInventory"),
            label="candidateLogicalInventory",
        )
        actual_inventory = _logical_inventory(connection)
        if allow_catalog_extensions:
            if not _preserves_inventory_outside_catalog(
                actual_inventory,
                expected_inventory,
            ):
                raise ConsolidationVerificationError(
                    "candidate logical-object inventory changed outside catalog"
                )
        elif actual_inventory != expected_inventory:
            raise ConsolidationVerificationError("candidate logical-object inventory mismatch")

        expected_warehouse = _expected_table_digests(manifest, "warehouse")
        actual_warehouse = _duckdb_table_digests(connection, "main")
        if actual_warehouse != expected_warehouse:
            raise ConsolidationVerificationError("v10 warehouse table digest mismatch")
        if _table_layouts(connection, "main") != _expected_table_layouts(manifest, "warehouse"):
            raise ConsolidationVerificationError("v10 warehouse table layout mismatch")
        warehouse = _require_mapping(manifest.get("warehouse"), label="warehouse")
        definitions = _require_mapping(warehouse.get("definitions"), label="warehouse.definitions")
        if _warehouse_definitions(connection) != definitions:
            raise ConsolidationVerificationError("v10 warehouse definition or view mismatch")

        compendium = _require_mapping(manifest.get("compendium"), label="compendium")
        raw_tables = _require_mapping(compendium.get("tables"), label="compendium.tables")
        expected_catalog = _expected_table_digests(manifest, "compendium")
        expected_catalog_layouts = _expected_table_layouts(manifest, "compendium")
        if allow_catalog_extensions:
            catalog_relations = {
                str(row[0])
                for row in connection.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
                    [CATALOG_SCHEMA],
                ).fetchall()
            }
            missing_relations = sorted(set(expected_catalog) - catalog_relations)
            if missing_relations:
                raise ConsolidationVerificationError(
                    "catalog relations are missing from the manifest reconstruction: "
                    + ", ".join(missing_relations)
                )
        elif _table_names(connection, CATALOG_SCHEMA) != tuple(sorted(expected_catalog)):
            raise ConsolidationVerificationError("catalog table set does not match the manifest")
        actual_catalog: dict[str, dict[str, object]] = {}
        for table_name, expected_digest in expected_catalog.items():
            table = _require_mapping(
                raw_tables.get(table_name),
                label=f"compendium.tables.{table_name}",
            )
            raw_columns = table.get("columns")
            if not isinstance(raw_columns, list) or not all(
                isinstance(column, str) for column in raw_columns
            ):
                raise ConsolidationVerificationError(
                    f"manifest compendium.tables.{table_name}.columns must be a string list"
                )
            raw_declared_types = table.get("declaredTypes")
            raw_primary_key = table.get("primaryKey")
            raw_rowid_alias = table.get("sourceRowidAlias")
            if not isinstance(raw_declared_types, list) or not all(
                isinstance(value, str) for value in raw_declared_types
            ):
                raise ConsolidationVerificationError(
                    f"manifest compendium.tables.{table_name}.declaredTypes is invalid"
                )
            if not isinstance(raw_primary_key, list) or not all(
                isinstance(value, str) for value in raw_primary_key
            ):
                raise ConsolidationVerificationError(
                    f"manifest compendium.tables.{table_name}.primaryKey is invalid"
                )
            if raw_rowid_alias is not None and not isinstance(raw_rowid_alias, str):
                raise ConsolidationVerificationError(
                    f"manifest compendium.tables.{table_name}.sourceRowidAlias is invalid"
                )
            plan = SQLiteTablePlan(
                name=table_name,
                columns=tuple(str(value) for value in raw_columns),
                declared_types=tuple(str(value) for value in raw_declared_types),
                primary_key=tuple(str(value) for value in raw_primary_key),
                rowid_alias=raw_rowid_alias,
            )
            expected_columns = (SOURCE_ROWID_COLUMN, *(str(column) for column in raw_columns))
            actual_columns = _table_columns(connection, CATALOG_SCHEMA, table_name)
            if actual_columns != expected_columns:
                raise ConsolidationVerificationError(f"catalog table columns changed: {table_name}")
            actual_layout = {
                "columns": list(actual_columns[1:]),
                "columnTypes": list(_table_column_types(connection, CATALOG_SCHEMA, table_name)),
            }
            expected_layout = dict(expected_catalog_layouts[table_name])
            expected_layout["columns"] = list(expected_columns[1:])
            if actual_layout != expected_layout:
                raise ConsolidationVerificationError(f"catalog table layout changed: {table_name}")
            actual_digest = _candidate_stream_digest(connection, plan)
            if actual_digest != expected_digest:
                raise ConsolidationVerificationError(f"catalog table digest mismatch: {table_name}")
            actual_catalog[table_name] = actual_digest

        metadata_rows = tuple(
            (
                int(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                int(row[4]),
                None if row[5] is None else str(row[5]),
            )
            for row in connection.execute(
                f"""
                SELECT ordinal, object_type, object_name, table_name, root_page, ddl
                FROM {_quote_identifier(METADATA_SCHEMA)}.sqlite_master_objects
                ORDER BY ordinal
                """
            ).fetchall()
        )
        if len(metadata_rows) != int(compendium.get("sqliteMasterObjectCount", -1)):
            raise ConsolidationVerificationError("sqlite_master object count mismatch")
        if _canonical_sha256(_sqlite_master_payload(metadata_rows)) != compendium.get(
            "sqliteMasterSha256"
        ):
            raise ConsolidationVerificationError("sqlite_master metadata digest mismatch")
        return manifest, actual_warehouse, actual_catalog
    finally:
        try:
            connection.close()
        finally:
            _remove_temp_directory(temp_directory)


def _identity_from_manifest(value: object, *, label: str) -> FileIdentity:
    payload = _require_mapping(value, label=label)
    try:
        return FileIdentity(
            device=int(payload["device"]),
            inode=int(payload["inode"]),
            size_bytes=int(payload["sizeBytes"]),
            modified_ns=int(payload["modifiedNs"]),
            changed_ns=int(payload["changedNs"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConsolidationVerificationError(f"manifest {label} is invalid") from exc


def _verify_source_binding(
    path: Path,
    section: dict[str, Any],
    *,
    label: str,
) -> FileIdentity:
    if section.get("path") != str(path):
        raise ConsolidationVerificationError(f"{label} path does not match the manifest")
    expected_identity = _identity_from_manifest(section.get("identity"), label=f"{label}.identity")
    actual_identity = FileIdentity.read(path)
    if actual_identity != expected_identity:
        raise ConsolidationVerificationError(f"{label} identity does not match the manifest")
    if file_sha256(path) != section.get("sha256"):
        raise ConsolidationVerificationError(f"{label} SHA-256 does not match the manifest")
    _assert_identity(path, actual_identity, stage="while verifying its SHA-256")
    return actual_identity


def _cleanup_build(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(f"{path}.wal").unlink(missing_ok=True)
    _remove_temp_directory(Path(f"{path}.tmp"))


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_no_clobber(build_path: Path, destination: Path) -> None:
    directory_descriptor = os.open(destination.parent, os.O_RDONLY)
    linked = False
    staging_unlinked = False
    try:
        try:
            os.link(build_path, destination)
        except FileExistsError:
            raise FileExistsError(
                f"consolidation destination appeared during build: {destination}"
            ) from None
        linked = True
        os.fsync(directory_descriptor)
        build_path.unlink()
        staging_unlinked = True
        os.fsync(directory_descriptor)
    except BaseException as error:
        if linked:
            try:
                if staging_unlinked:
                    os.link(destination, build_path)
                destination.unlink()
                os.fsync(directory_descriptor)
            except BaseException as recovery_error:
                error.add_note(
                    f"failed to roll back partial destination publication: {recovery_error}"
                )
        raise
    finally:
        os.close(directory_descriptor)


def build_consolidated_database(
    warehouse_path: Path,
    compendium_path: Path,
    destination_path: Path,
) -> ConsolidationResult:
    warehouse = warehouse_path.expanduser().resolve(strict=True)
    compendium = compendium_path.expanduser().resolve(strict=True)
    destination = destination_path.expanduser().resolve()
    if len({warehouse, compendium, destination}) != 3:
        raise ConsolidationError("warehouse, compendium, and destination must be different paths")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_path = destination.with_name(f".{destination.name}.building-{uuid4().hex}")
    sqlite_snapshot = destination.with_name(
        f".{destination.name}.sqlite-snapshot-{uuid4().hex}.sqlite"
    )

    _assert_warehouse_wal_free(warehouse, stage="before consolidation")
    _assert_sqlite_sidecars_clean(compendium, stage="before consolidation")
    warehouse_identity = FileIdentity.read(warehouse)
    compendium_identity = FileIdentity.read(compendium)
    warehouse_sha256 = file_sha256(warehouse)
    _assert_identity(warehouse, warehouse_identity, stage="while hashing")
    compendium_sha256 = file_sha256(compendium)
    _assert_identity(compendium, compendium_identity, stage="while hashing")
    try:
        _create_verified_sqlite_snapshot(
            compendium,
            sqlite_snapshot,
            source_sha256=compendium_sha256,
            source_identity=compendium_identity,
        )
        sqlite_catalog = _read_sqlite_catalog(sqlite_snapshot)
        sqlite_profiles, compendium_digests = _profile_sqlite_snapshot(
            sqlite_snapshot,
            sqlite_catalog,
        )

        source_connection = duckdb.connect(str(warehouse), read_only=True)
        try:
            if read_schema_version(source_connection) != SCHEMA_VERSION:
                raise ConsolidationError(f"warehouse source must use schema v{SCHEMA_VERSION}")
            source_schemas = {
                str(row[0])
                for row in source_connection.execute(
                    "SELECT schema_name FROM information_schema.schemata"
                ).fetchall()
            }
            collisions = {CATALOG_SCHEMA, METADATA_SCHEMA} & source_schemas
            if collisions:
                raise ConsolidationError(
                    f"warehouse already uses reserved schemas: {sorted(collisions)}"
                )
            warehouse_digests = _duckdb_table_digests(source_connection, "main")
            warehouse_layouts = _table_layouts(source_connection, "main")
            warehouse_definitions = _warehouse_definitions(source_connection)
        finally:
            source_connection.close()
    except BaseException:
        _cleanup_sqlite_snapshot(sqlite_snapshot)
        raise

    published = False
    try:
        shutil.copyfile(warehouse, build_path)
        if file_sha256(build_path) != warehouse_sha256:
            raise ConsolidationVerificationError("warehouse copy SHA-256 mismatch")
        _assert_identity(warehouse, warehouse_identity, stage="while copying")

        connection = duckdb.connect(str(build_path))
        attached = False
        try:
            _configure_resource_bounds(
                connection,
                temp_directory=Path(f"{build_path}.tmp"),
            )
            connection.execute("SET wal_autocheckpoint='1.0 GiB'")
            connection.execute("SET checkpoint_threshold='1.0 GiB'")
            connection.execute(f"CREATE SCHEMA {_quote_identifier(CATALOG_SCHEMA)}")
            _create_metadata_tables(connection, sqlite_catalog)
            _attach_sqlite(connection, sqlite_snapshot, "source_catalog")
            attached = True
            _copy_sqlite_tables(
                connection,
                sqlite_snapshot,
                sqlite_catalog,
                sqlite_profiles,
                attached_name="source_catalog",
            )
            catalog_layouts = _table_layouts(connection, CATALOG_SCHEMA)
            candidate_catalog_digests = {
                plan.name: _candidate_stream_digest(connection, plan)
                for plan in sqlite_catalog.tables
            }
            if candidate_catalog_digests != compendium_digests:
                raise ConsolidationVerificationError(
                    "catalog type-tagged stream digest differs from the SQLite snapshot"
                )
            connection.execute(f"DETACH {_quote_identifier('source_catalog')}")
            attached = False
            candidate_inventory = _logical_inventory(connection)
            core = _manifest_core(
                warehouse=warehouse,
                compendium=compendium,
                warehouse_sha256=warehouse_sha256,
                compendium_sha256=compendium_sha256,
                warehouse_identity=warehouse_identity,
                compendium_identity=compendium_identity,
                warehouse_digests=warehouse_digests,
                warehouse_layouts=warehouse_layouts,
                warehouse_definitions=warehouse_definitions,
                compendium_digests=compendium_digests,
                catalog_layouts=catalog_layouts,
                catalog=sqlite_catalog,
                profiles=sqlite_profiles,
                candidate_inventory=candidate_inventory,
            )
            receipt_sha256 = _embed_manifest(connection, core)
            connection.execute("FORCE CHECKPOINT")
        finally:
            if attached:
                try:
                    connection.execute(f"DETACH {_quote_identifier('source_catalog')}")
                except BaseException:
                    pass
            connection.close()

        _assert_warehouse_wal_free(build_path, stage="after checkpoint")
        _assert_warehouse_wal_free(warehouse, stage="after consolidation")
        _assert_sqlite_sidecars_clean(compendium, stage="after consolidation")
        _assert_identity(warehouse, warehouse_identity, stage="during consolidation")
        _assert_identity(compendium, compendium_identity, stage="during consolidation")
        verified_manifest, actual_warehouse, actual_catalog = _verify_candidate_contents(
            build_path,
            expected_receipt_sha256=receipt_sha256,
        )
        _fsync_file(build_path)
        build_sha256 = file_sha256(build_path)
        build_identity = FileIdentity.read(build_path)
        _assert_identity(warehouse, warehouse_identity, stage="before publication")
        _assert_identity(compendium, compendium_identity, stage="before publication")
        _assert_warehouse_wal_free(warehouse, stage="before publication")
        _assert_sqlite_sidecars_clean(compendium, stage="before publication")
        _publish_no_clobber(build_path, destination)
        published = True
        destination_identity = FileIdentity.read(destination)
        if (
            destination_identity.device,
            destination_identity.inode,
            destination_identity.size_bytes,
            destination_identity.modified_ns,
        ) != (
            build_identity.device,
            build_identity.inode,
            build_identity.size_bytes,
            build_identity.modified_ns,
        ):
            raise ConsolidationVerificationError(
                "published path does not reference the verified staging inode"
            )
        published_manifest = _verify_published_envelope(
            destination,
            expected_receipt_sha256=receipt_sha256,
        )
        if published_manifest != verified_manifest:
            raise ConsolidationVerificationError(
                "published manifest differs from the verified staging database"
            )
        _assert_identity(destination, destination_identity, stage="during read-only verification")
        _assert_warehouse_wal_free(destination, stage="after read-only verification")
        _assert_identity(warehouse, warehouse_identity, stage="after publication")
        _assert_identity(compendium, compendium_identity, stage="after publication")
        return ConsolidationResult(
            warehouse_source=warehouse,
            compendium_source=compendium,
            destination_path=destination,
            warehouse_sha256=warehouse_sha256,
            compendium_sha256=compendium_sha256,
            destination_sha256=build_sha256,
            warehouse_identity=warehouse_identity,
            compendium_identity=compendium_identity,
            destination_identity=destination_identity,
            receipt_sha256=receipt_sha256,
            imported_row_counts=_digest_row_counts(actual_catalog),
            warehouse_row_counts=_digest_row_counts(actual_warehouse),
        )
    finally:
        _cleanup_sqlite_snapshot(sqlite_snapshot)
        if not published:
            _cleanup_build(build_path)


def verify_consolidated_candidate(
    database_path: Path,
    *,
    allow_catalog_extensions: bool = False,
) -> ConsolidationVerification:
    database = database_path.expanduser().resolve(strict=True)
    _assert_warehouse_wal_free(database, stage="before verification")
    database_identity = FileIdentity.read(database)
    manifest, warehouse_digests, catalog_digests = _verify_candidate_contents(
        database,
        allow_catalog_extensions=allow_catalog_extensions,
    )
    _assert_identity(database, database_identity, stage="during verification")
    _assert_warehouse_wal_free(database, stage="after verification")
    database_sha256 = file_sha256(database)
    _assert_identity(database, database_identity, stage="while hashing")
    return ConsolidationVerification(
        database_path=database,
        database_sha256=database_sha256,
        database_identity=database_identity,
        receipt_sha256=str(manifest["receiptSha256"]),
        imported_row_counts=_digest_row_counts(catalog_digests),
        warehouse_row_counts=_digest_row_counts(warehouse_digests),
    )


def verify_consolidated_database(
    warehouse_path: Path,
    compendium_path: Path,
    database_path: Path,
) -> ConsolidationVerification:
    warehouse = warehouse_path.expanduser().resolve(strict=True)
    compendium = compendium_path.expanduser().resolve(strict=True)
    database = database_path.expanduser().resolve(strict=True)
    _assert_warehouse_wal_free(warehouse, stage="before verification")
    _assert_sqlite_sidecars_clean(compendium, stage="before verification")
    _assert_warehouse_wal_free(database, stage="before verification")
    database_identity = FileIdentity.read(database)

    manifest, warehouse_digests, catalog_digests = _verify_candidate_contents(database)
    warehouse_section = _require_mapping(manifest.get("warehouse"), label="warehouse")
    compendium_section = _require_mapping(manifest.get("compendium"), label="compendium")
    warehouse_identity = _verify_source_binding(
        warehouse,
        warehouse_section,
        label="warehouse",
    )
    compendium_identity = _verify_source_binding(
        compendium,
        compendium_section,
        label="compendium",
    )

    source_warehouse = duckdb.connect(str(warehouse), read_only=True)
    try:
        if read_schema_version(source_warehouse) != SCHEMA_VERSION:
            raise ConsolidationVerificationError(
                f"warehouse source is not schema v{SCHEMA_VERSION}"
            )
        if _duckdb_table_digests(source_warehouse, "main") != warehouse_digests:
            raise ConsolidationVerificationError("warehouse source table digest mismatch")
    finally:
        source_warehouse.close()

    sqlite_snapshot = database.with_name(f".{database.name}.verify-snapshot-{uuid4().hex}.sqlite")
    try:
        _create_verified_sqlite_snapshot(
            compendium,
            sqlite_snapshot,
            source_sha256=str(compendium_section["sha256"]),
            source_identity=compendium_identity,
        )
        sqlite_catalog = _read_sqlite_catalog(sqlite_snapshot)
        sqlite_profiles, current_sqlite_digests = _profile_sqlite_snapshot(
            sqlite_snapshot,
            sqlite_catalog,
        )
        if len(sqlite_catalog.master_objects) != int(
            compendium_section.get("sqliteMasterObjectCount", -1)
        ) or _canonical_sha256(_sqlite_master_payload(sqlite_catalog.master_objects)) != (
            compendium_section.get("sqliteMasterSha256")
        ):
            raise ConsolidationVerificationError("compendium sqlite_master metadata mismatch")
        raw_tables = _require_mapping(compendium_section.get("tables"), label="compendium.tables")
        plans = {
            plan.name: {
                "columns": list(plan.columns),
                "declaredTypes": list(plan.declared_types),
                "primaryKey": list(plan.primary_key),
                "sourceRowidAlias": plan.rowid_alias,
                "affinities": list(sqlite_profiles[plan.name].affinities),
                "storageClasses": [
                    list(values) for values in sqlite_profiles[plan.name].storage_classes
                ],
                "importMode": sqlite_profiles[plan.name].import_mode,
            }
            for plan in sqlite_catalog.tables
        }
        manifest_plans = {
            str(name): {
                key: _require_mapping(table, label=f"compendium.tables.{name}").get(key)
                for key in (
                    "columns",
                    "declaredTypes",
                    "primaryKey",
                    "sourceRowidAlias",
                    "affinities",
                    "storageClasses",
                    "importMode",
                )
            }
            for name, table in raw_tables.items()
        }
        if plans != manifest_plans:
            raise ConsolidationVerificationError("compendium table layout mismatch")
    finally:
        _cleanup_sqlite_snapshot(sqlite_snapshot)
    if current_sqlite_digests != catalog_digests:
        raise ConsolidationVerificationError("compendium source table digest mismatch")

    _assert_identity(warehouse, warehouse_identity, stage="during verification")
    _assert_identity(compendium, compendium_identity, stage="during verification")
    _assert_identity(database, database_identity, stage="during verification")
    _assert_warehouse_wal_free(warehouse, stage="after verification")
    _assert_sqlite_sidecars_clean(compendium, stage="after verification")
    _assert_warehouse_wal_free(database, stage="after verification")
    database_sha256 = file_sha256(database)
    _assert_identity(database, database_identity, stage="while hashing")
    return ConsolidationVerification(
        database_path=database,
        database_sha256=database_sha256,
        database_identity=database_identity,
        receipt_sha256=str(manifest["receiptSha256"]),
        imported_row_counts=_digest_row_counts(catalog_digests),
        warehouse_row_counts=_digest_row_counts(warehouse_digests),
    )
