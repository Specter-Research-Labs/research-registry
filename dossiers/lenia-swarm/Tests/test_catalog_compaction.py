from __future__ import annotations

import hashlib
import json
from typing import cast

import duckdb
import pytest

import lenia_swarm_analysis.morphospace.compact_catalog as catalog_compaction
from lenia_swarm_analysis.morphospace.compact_catalog import (
    CANONICAL_WRITABLE_TABLES,
    CatalogCompactionError,
    compact_catalog,
    verify_compacted_catalog,
)


def _fixture_connection() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE SCHEMA catalog")
    connection.execute(
        """
        CREATE TABLE catalog.creatures (
            _source_rowid BIGINT NOT NULL,
            id VARCHAR NOT NULL,
            score DOUBLE,
            specimen_manifest_json JSON,
            metrics_json VARCHAR
        )
        """
    )
    connection.execute(
        """
        INSERT INTO catalog.creatures VALUES
            (1, 'creature-a', 1.5, '{"replay":{"seed":7}}', '{"mass":2.0}'),
            (2, 'creature-b', NULL, '{"replay":{"seed":7}}', NULL)
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog.results (
            _source_rowid BIGINT NOT NULL,
            id VARCHAR NOT NULL,
            implementation_json VARCHAR NOT NULL,
            score_weights_json JSON
        )
        """
    )
    connection.execute(
        """
        INSERT INTO catalog.results VALUES
            (10, 'result-a', '{"runtime":"flow"}', '{"mass":1.0}'),
            (11, 'result-b', '{"runtime":"flow"}', '{"mass":1.0}')
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog.specimens (
            _source_rowid BIGINT NOT NULL,
            id VARCHAR NOT NULL,
            specimen_manifest_json JSON,
            terminal_descriptor_json JSON
        )
        """
    )
    connection.execute(
        """
        INSERT INTO catalog.specimens VALUES
            (20, 'specimen-a', '{"replay":{"seed":7}}', '{"mass":2.0}'),
            (21, 'specimen-b', NULL, '{"mass":3.0}')
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog.qc_events (
            _source_rowid BIGINT NOT NULL,
            event_id VARCHAR NOT NULL,
            details_json VARCHAR
        )
        """
    )
    connection.execute("INSERT INTO catalog.qc_events VALUES (30, 'event-a', '{\"mass\":2.0}')")
    connection.execute(
        """
        CREATE TABLE catalog.runs (
            _source_rowid BIGINT NOT NULL,
            run_id VARCHAR NOT NULL,
            run_name VARCHAR NOT NULL,
            host_id VARCHAR,
            output_root VARCHAR,
            run_dir VARCHAR NOT NULL,
            indexed_at VARCHAR NOT NULL,
            config_hash VARCHAR,
            source_mode VARCHAR,
            source_algorithm VARCHAR
        )
        """
    )
    connection.execute(
        """
        INSERT INTO catalog.runs VALUES
            (40, 'run-a', 'Run A', 'host-a', '/tmp', '/tmp/run-a',
             '2026-07-17T00:00:00Z', 'config-a', 'search', 'beam'),
            (41, 'run-b', 'Run B', NULL, NULL, '/tmp/run-b',
             '2026-07-17T00:00:01Z', NULL, 'replay', 'beam')
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog.exports (
            _source_rowid BIGINT NOT NULL,
            id VARCHAR NOT NULL,
            creature_id VARCHAR NOT NULL,
            specimen_manifest_json VARCHAR
        )
        """
    )
    connection.execute(
        "INSERT INTO catalog.exports VALUES "
        "(50, 'export-a', 'creature-a', '{\"replay\":{\"seed\":7}}')"
    )
    return connection


def _rows(connection: duckdb.DuckDBPyConnection, table_name: str) -> list[tuple[object, ...]]:
    return connection.execute(
        f'SELECT * FROM catalog."{table_name}" ORDER BY _source_rowid'
    ).fetchall()


def test_compaction_interns_payloads_and_reconstructs_source_tables() -> None:
    connection = _fixture_connection()
    try:
        expected = {
            table_name: _rows(connection, table_name)
            for table_name in (
                "creatures",
                "results",
                "specimens",
                "runs",
                "exports",
                "qc_events",
            )
        }

        report = compact_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )

        assert len(report.receipt_sha256) == 64
        verification = verify_compacted_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )
        assert verification.receipt_sha256 == report.receipt_sha256
        assert verification.table_count == 6
        assert verification.row_count == 10

        assert [table.table_name for table in report.tables] == [
            "runs",
            "results",
            "creatures",
            "exports",
            "specimens",
            "qc_events",
        ]
        assert report.documents_before == 0
        assert report.documents_after == 5
        for table in report.tables:
            assert table.pre_compaction_sha256 == table.reconstruction_sha256
            assert _rows(connection, table.table_name) == expected[table.table_name]

        object_types = dict(
            connection.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'catalog'
                """
            ).fetchall()
        )
        assert object_types["creatures"] == "VIEW"
        assert object_types["__compact_creatures"] == "BASE TABLE"
        assert object_types["qc_events"] == "VIEW"
        assert object_types["__compact_qc_events"] == "BASE TABLE"
        assert object_types["runs"] == "VIEW"
        assert object_types["__compact_runs"] == "BASE TABLE"

        creature_browse_columns = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM catalog.creatures_browse"
            ).fetchall()
        ]
        assert creature_browse_columns == [
            "_source_rowid",
            "id",
            "score",
            "_json_document_ids",
        ]
        browse_row = connection.execute(
            """
            SELECT _source_rowid, id, score,
                   _json_document_ids.specimen_manifest_json,
                   _json_document_ids.metrics_json
            FROM catalog.creatures_browse
            WHERE _source_rowid = 1
            """
        ).fetchone()
        assert browse_row is not None
        assert browse_row[:3] == (1, "creature-a", 1.5)
        assert all(isinstance(value, int) for value in browse_row[3:])
        assert [
            row[0]
            for row in connection.execute("DESCRIBE SELECT * FROM catalog.runs_browse").fetchall()
        ] == [
            "_source_rowid",
            "run_id",
            "run_name",
            "host_id",
            "output_root",
            "run_dir",
            "indexed_at",
            "config_hash",
            "source_mode",
            "source_algorithm",
        ]

        shared_document_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM catalog.json_documents
            WHERE document_text = '{"mass":2.0}'
            """
        ).fetchone()
        assert shared_document_count == (1,)
        assert connection.execute(
            "SELECT COUNT(*), SUM(byte_length) FROM catalog.json_documents"
        ).fetchone() == (5, 75)

        metadata = connection.execute(
            """
            SELECT source_table, row_count, pre_compaction_sha256,
                   reconstruction_sha256
            FROM catalog.compaction_tables
            ORDER BY source_table
            """
        ).fetchall()
        assert len(metadata) == 6
        assert all(row[2] == row[3] for row in metadata)
        assert connection.execute("SELECT COUNT(*) FROM catalog.compaction_columns").fetchone() == (
            30,
        )

        second_report = compact_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )
        assert second_report.tables == ()
        assert second_report.documents_before == second_report.documents_after == 5
        assert second_report.receipt_sha256 == report.receipt_sha256
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (
            "UPDATE catalog.json_documents SET byte_length = byte_length + 1 "
            "WHERE document_id = (SELECT min(document_id) FROM catalog.json_documents)",
            "SHA-256 or byte-length",
        ),
        (
            "UPDATE catalog.compaction_tables SET row_count = row_count + 1 "
            "WHERE source_table = 'creatures'",
            "table metadata differs",
        ),
        (
            "UPDATE catalog.__compact_creatures SET score = 99.0 WHERE id = 'creature-a'",
            "reconstruction digest changed",
        ),
        (
            "UPDATE catalog.compaction_manifest "
            "SET manifest_json = replace(manifest_json, '\"format\"', '\"formats\"')",
            "manifest hash mismatch",
        ),
    ],
)
def test_self_contained_verifier_rejects_compact_base_corruption(mutation: str, error: str) -> None:
    connection = _fixture_connection()
    try:
        compact_catalog(connection, required_writable_tables=CANONICAL_WRITABLE_TABLES)
        connection.execute(mutation)

        with pytest.raises(CatalogCompactionError, match=error):
            verify_compacted_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
    finally:
        connection.close()


def test_dirty_support_store_fails_without_aliasing_documents() -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute(
            """
            CREATE TABLE catalog.json_documents (
                document_id BIGINT PRIMARY KEY,
                content_sha256 VARCHAR NOT NULL,
                byte_length BIGINT NOT NULL,
                document_text VARCHAR NOT NULL
            )
            """
        )
        wanted = '{"value":1}'
        digest = hashlib.sha256(wanted.encode()).hexdigest()
        collision = '{"different":true}'
        connection.execute(
            "INSERT INTO catalog.json_documents VALUES (1, ?, ?, ?)",
            [digest, len(collision.encode()), collision],
        )
        connection.execute(
            """
            CREATE TABLE catalog.creatures (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL
            )
            """
        )
        connection.execute("INSERT INTO catalog.creatures VALUES (1, 'creature-a', ?)", [wanted])

        with pytest.raises(CatalogCompactionError, match="requires empty support tables"):
            compact_catalog(connection, required_writable_tables=())

        assert connection.execute("SELECT COUNT(*) FROM catalog.json_documents").fetchone() == (1,)
        assert connection.execute("SELECT payload_json FROM catalog.creatures").fetchone() == (
            wanted,
        )
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'catalog' AND table_name = '__compact_creatures'
            """
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_compact_verifier_rejects_public_view_drift() -> None:
    connection = _fixture_connection()
    try:
        compact_catalog(connection, required_writable_tables=CANONICAL_WRITABLE_TABLES)
        connection.execute(
            "CREATE OR REPLACE VIEW catalog.creatures AS "
            "SELECT * FROM catalog.__compact_creatures WHERE false"
        )

        with pytest.raises(CatalogCompactionError, match="public view changed"):
            verify_compacted_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
    finally:
        connection.close()


def test_compact_verifier_rejects_document_values_view_drift() -> None:
    connection = _fixture_connection()
    try:
        compact_catalog(connection, required_writable_tables=CANONICAL_WRITABLE_TABLES)
        connection.execute(
            """
            CREATE OR REPLACE VIEW catalog.json_document_values AS
            SELECT document_id, content_sha256, byte_length, ''::VARCHAR AS document_text
            FROM catalog.json_documents
            """
        )

        with pytest.raises(CatalogCompactionError, match="public view changed"):
            verify_compacted_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
    finally:
        connection.close()


def test_raw_document_integrity_check_has_no_payload_join() -> None:
    connection = duckdb.connect(":memory:")
    try:
        catalog_compaction._ensure_support_tables(connection, schema_name="catalog")
        query = catalog_compaction._raw_document_integrity_query(schema_name="catalog")
        row = connection.execute(f"EXPLAIN (FORMAT JSON) {query}").fetchone()
        assert row is not None
        plan = json.loads(str(row[1]))

        def operators(value: object) -> list[str]:
            if isinstance(value, dict):
                mapping = cast(dict[str, object], value)
                own = [str(mapping["name"])] if "name" in mapping else []
                return own + [operator for item in mapping.values() for operator in operators(item)]
            if isinstance(value, list):
                return [operator for item in value for operator in operators(item)]
            return []

        names = operators(plan)
        assert names.count("SEQ_SCAN") == 1
        assert "HASH_JOIN" not in names
        assert "ORDER_BY" not in names
    finally:
        connection.close()


def test_zero_template_verification_does_not_hash_the_reconstruction_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()
    try:
        compact_catalog(connection, required_writable_tables=CANONICAL_WRITABLE_TABLES)
        queries: list[str] = []
        original_scalar_int = catalog_compaction._scalar_int

        def observe_query(
            connection: duckdb.DuckDBPyConnection,
            query: str,
            parameters: list[object],
        ) -> int:
            queries.append(query)
            return original_scalar_int(connection, query, parameters)

        monkeypatch.setattr(catalog_compaction, "_scalar_int", observe_query)
        verify_compacted_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )

        assert any(
            'FROM "catalog"."json_documents"' in query and "sha256(document_text)" in query
            for query in queries
        )
        assert not any(
            'FROM "catalog"."json_document_values"' in query and "sha256(document_text)" in query
            for query in queries
        )
    finally:
        connection.close()


def test_template_document_verification_is_bounded_and_byte_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = duckdb.connect(":memory:")
    try:
        catalog_compaction._ensure_support_tables(connection, schema_name="catalog")
        raw_values = {1: "a", 2: "b", 4: "c", 5: "d"}
        for document_id, value in raw_values.items():
            connection.execute(
                "INSERT INTO catalog.json_documents VALUES (?, ?, ?, ?)",
                [
                    document_id,
                    hashlib.sha256(value.encode()).hexdigest(),
                    len(value.encode()),
                    value,
                ],
            )
        for document_id, first_id, second_id, value in (
            (3, 1, 2, "ab"),
            (6, 4, 5, "cd"),
        ):
            connection.execute(
                "INSERT INTO catalog.json_documents VALUES (?, ?, ?, NULL)",
                [
                    document_id,
                    hashlib.sha256(value.encode()).hexdigest(),
                    len(value.encode()),
                ],
            )
            connection.execute(
                """
                INSERT INTO catalog.json_document_templates
                VALUES (?, 'specimen_manifest_descriptor_substrings_v1',
                        '', ?, '', ?, NULL, NULL, '')
                """,
                [document_id, first_id, second_id],
            )

        batches: list[set[int]] = []
        original_rows = catalog_compaction._template_document_rows

        def observe_batch(
            connection: duckdb.DuckDBPyConnection,
            *,
            documents: str,
            document_ids: set[int],
        ) -> dict[int, tuple[str, int, str | None]]:
            batches.append(document_ids)
            return original_rows(
                connection,
                documents=documents,
                document_ids=document_ids,
            )

        monkeypatch.setattr(catalog_compaction, "DOCUMENT_VERIFICATION_BATCH_SIZE", 1)
        monkeypatch.setattr(catalog_compaction, "_template_document_rows", observe_batch)

        assert catalog_compaction._template_document_errors(
            connection,
            schema_name="catalog",
        ) == (
            0,
            0,
        )
        assert batches == [{1, 2, 3}, {4, 5, 6}]

        connection.execute(
            "UPDATE catalog.json_document_templates SET prefix_text = 'x' WHERE document_id = 6"
        )
        assert catalog_compaction._template_document_errors(
            connection,
            schema_name="catalog",
        ) == (
            0,
            1,
        )
    finally:
        connection.close()


def test_payload_interning_deduplicates_with_one_set_based_source_scan() -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute(
            """
            CREATE TABLE catalog.creatures (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO catalog.creatures VALUES
                (1, 'first', '{"shared":true}'),
                (2, 'second', '{"shared":true}')
            """
        )

        catalog_compaction._ensure_support_tables(connection, schema_name="catalog")
        insert_query = catalog_compaction._intern_payload_insert_query(
            source='"catalog"."creatures"',
            documents='"catalog"."json_documents"',
            column='"payload_json"',
        )
        plan_row = connection.execute(f"EXPLAIN (FORMAT JSON) {insert_query}").fetchone()
        assert plan_row is not None
        plan = json.loads(str(plan_row[1]))

        def source_scans(value: object) -> int:
            if isinstance(value, dict):
                own = int(
                    value.get("name") == "SEQ_SCAN"
                    and str(value.get("extra_info", {}).get("Table", "")).endswith(
                        '"catalog".creatures'
                    )
                )
                return own + sum(source_scans(item) for item in value.values())
            if isinstance(value, list):
                return sum(source_scans(item) for item in value)
            return 0

        assert source_scans(plan) == 1

        report = compact_catalog(connection, required_writable_tables=())

        assert report.documents_after == 1
        assert connection.execute(
            "SELECT payload_json FROM catalog.creatures ORDER BY _source_rowid"
        ).fetchall() == [('{"shared":true}',), ('{"shared":true}',)]
    finally:
        connection.close()


def test_canonical_verifier_rejects_old_manifest_that_omits_payload_free_runs() -> None:
    connection = _fixture_connection()
    try:
        relaxed_report = compact_catalog(connection, required_writable_tables=())
        assert "runs" not in {table.table_name for table in relaxed_report.tables}

        with pytest.raises(
            CatalogCompactionError,
            match="required writable catalog tables are not compacted: runs",
        ):
            verify_compacted_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
    finally:
        connection.close()


def test_manifest_factoring_defaults_to_raw_documents() -> None:
    connection = duckdb.connect(":memory:")
    genotype = '{"vector":[1,2]}'
    terminal = '{"mass":2.0}'
    manifest = (
        '{"snapshots":{"descriptorBundle":{"genotype":'
        + genotype
        + ',"terminal":'
        + terminal
        + '}},"creatureID":"eligible"}'
    )
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute(
            """
            CREATE TABLE catalog.specimens (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                genotype_descriptor_json JSON NOT NULL,
                terminal_descriptor_json JSON NOT NULL,
                specimen_manifest_json JSON NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO catalog.specimens VALUES (1, 'eligible', ?::JSON, ?::JSON, ?::JSON)",
            [genotype, terminal, manifest],
        )

        report = compact_catalog(connection, required_writable_tables=())

        assert report.manifest_factoring.factored_documents == 0
        assert report.manifest_factoring.original_bytes == 0
        assert report.manifest_factoring.referenced_bytes == 0
        assert report.manifest_factoring.residual_bytes == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.json_document_templates"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT document_text FROM catalog.json_documents WHERE content_sha256 = ?",
            [hashlib.sha256(manifest.encode()).hexdigest()],
        ).fetchone() == (manifest,)
        manifest_payload = json.loads(
            connection.execute("SELECT manifest_json FROM catalog.compaction_manifest").fetchone()[
                0
            ]
        )
        assert manifest_payload["manifestFactoring"] == {
            "factoredDocuments": 0,
            "originalBytes": 0,
            "referencedBytes": 0,
            "residualBytes": 0,
        }
        verify_compacted_catalog(connection, required_writable_tables=())
    finally:
        connection.close()


def test_manifest_factoring_is_byte_exact_and_falls_back_conservatively() -> None:
    connection = duckdb.connect(":memory:")
    genotype = '{"vector":[1,2]}'
    terminal = '{"mass":2.0}'
    trajectory = '{"path":[0,1]}'
    manifest = (
        '{"snapshots":{"descriptorBundle":{"genotype":'
        + genotype
        + ',"terminal":'
        + terminal
        + ',"trajectory":'
        + trajectory
        + '}},"creatureID":"eligible"}'
    )
    ambiguous_manifest = (
        '{"copy":'
        + genotype
        + ',"snapshots":{"descriptorBundle":{"genotype":'
        + genotype
        + ',"terminal":'
        + terminal
        + "}}}"
    )
    missing_manifest = '{"snapshots":{"descriptorBundle":{"genotype":' + genotype + "}}}"
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute(
            """
            CREATE TABLE catalog.creatures (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                specimen_manifest_json JSON NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO catalog.creatures VALUES (1, 'eligible', ?::JSON)", [manifest]
        )
        connection.execute(
            """
            CREATE TABLE catalog.specimens (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                genotype_descriptor_json JSON NOT NULL,
                terminal_descriptor_json JSON NOT NULL,
                trajectory_descriptor_json JSON,
                specimen_manifest_json JSON NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO catalog.specimens VALUES (?, ?, ?::JSON, ?::JSON, ?::JSON, ?::JSON)",
            [
                (1, "eligible", genotype, terminal, trajectory, manifest),
                (2, "ambiguous", genotype, terminal, None, ambiguous_manifest),
                (3, "missing", genotype, '{"mass":999.0}', None, missing_manifest),
            ],
        )
        expected_creatures = _rows(connection, "creatures")
        expected_specimens = _rows(connection, "specimens")

        report = compact_catalog(
            connection,
            required_writable_tables=(),
            factor_specimen_manifests=True,
        )

        assert report.manifest_factoring.factored_documents == 1
        assert report.manifest_factoring.original_bytes == len(manifest.encode())
        expected_referenced_bytes = sum(
            len(value.encode()) for value in (genotype, terminal, trajectory)
        )
        assert report.manifest_factoring.referenced_bytes == expected_referenced_bytes
        assert report.manifest_factoring.residual_bytes == (
            len(manifest.encode()) - expected_referenced_bytes
        )
        assert _rows(connection, "creatures") == expected_creatures
        assert _rows(connection, "specimens") == expected_specimens

        eligible_storage = connection.execute(
            """
            SELECT document.document_text, template.template_kind,
                   resolved.document_text, resolved.content_sha256
            FROM catalog.json_documents AS document
            JOIN catalog.json_document_templates AS template USING (document_id)
            JOIN catalog.json_document_values AS resolved USING (document_id)
            WHERE resolved.content_sha256 = ?
            """,
            [hashlib.sha256(manifest.encode()).hexdigest()],
        ).fetchone()
        assert eligible_storage == (
            None,
            "specimen_manifest_descriptor_substrings_v1",
            manifest,
            hashlib.sha256(manifest.encode()).hexdigest(),
        )

        fallback_documents = connection.execute(
            """
            SELECT content_sha256, document_text
            FROM catalog.json_documents
            WHERE content_sha256 IN (?, ?)
            ORDER BY content_sha256
            """,
            [
                hashlib.sha256(ambiguous_manifest.encode()).hexdigest(),
                hashlib.sha256(missing_manifest.encode()).hexdigest(),
            ],
        ).fetchall()
        assert len(fallback_documents) == 2
        assert {row[1] for row in fallback_documents} == {
            ambiguous_manifest,
            missing_manifest,
        }
        verification = verify_compacted_catalog(connection, required_writable_tables=())
        assert verification.receipt_sha256 == report.receipt_sha256
        repeated = compact_catalog(connection, required_writable_tables=())
        assert repeated.manifest_factoring == report.manifest_factoring
    finally:
        connection.close()


def test_manifest_factoring_keeps_descriptor_dependencies_raw() -> None:
    connection = duckdb.connect(":memory:")
    genotype = '{"vector":[1,2]}'
    terminal = '{"mass":2.0}'
    inner_manifest = (
        '{"snapshots":{"descriptorBundle":{"genotype":'
        + genotype
        + ',"terminal":'
        + terminal
        + "}}}"
    )
    outer_terminal = '{"mass":3.0}'
    outer_manifest = (
        '{"snapshots":{"descriptorBundle":{"genotype":'
        + inner_manifest
        + ',"terminal":'
        + outer_terminal
        + "}}}"
    )
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute(
            """
            CREATE TABLE catalog.specimens (
                _source_rowid BIGINT NOT NULL,
                id VARCHAR NOT NULL,
                genotype_descriptor_json JSON NOT NULL,
                terminal_descriptor_json JSON NOT NULL,
                specimen_manifest_json JSON NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO catalog.specimens VALUES (?, ?, ?::JSON, ?::JSON, ?::JSON)",
            [
                (1, "inner", genotype, terminal, inner_manifest),
                (2, "outer", inner_manifest, outer_terminal, outer_manifest),
            ],
        )
        expected = _rows(connection, "specimens")

        report = compact_catalog(
            connection,
            required_writable_tables=(),
            factor_specimen_manifests=True,
        )

        assert report.manifest_factoring.factored_documents == 1
        assert _rows(connection, "specimens") == expected
        assert connection.execute(
            "SELECT document_text FROM catalog.json_documents WHERE content_sha256 = ?",
            [hashlib.sha256(inner_manifest.encode()).hexdigest()],
        ).fetchone() == (inner_manifest,)
        verify_compacted_catalog(connection, required_writable_tables=())
    finally:
        connection.close()


def test_missing_source_rowid_rolls_back_without_replacing_source() -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("CREATE SCHEMA catalog")
        connection.execute("CREATE TABLE catalog.creatures (id VARCHAR, payload_json JSON)")
        connection.execute("INSERT INTO catalog.creatures VALUES ('a', '{}')")

        with pytest.raises(CatalogCompactionError, match="must contain _source_rowid"):
            compact_catalog(connection, required_writable_tables=())

        assert connection.execute(
            """
            SELECT table_type
            FROM information_schema.tables
            WHERE table_schema = 'catalog' AND table_name = 'creatures'
            """
        ).fetchone() == ("BASE TABLE",)
        assert connection.execute("SELECT COUNT(*) FROM catalog.creatures").fetchone() == (1,)
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'catalog' AND table_name = 'json_documents'
            """
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_first_table_failure_keeps_only_the_resumable_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()

    def reject_reconstruction(*args: object, **kwargs: object) -> tuple[str, str]:
        raise CatalogCompactionError("injected reconstruction failure")

    monkeypatch.setattr(catalog_compaction, "_verify_reconstruction", reject_reconstruction)
    try:
        with pytest.raises(CatalogCompactionError, match="injected reconstruction failure"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )

        assert connection.execute(
            """
            SELECT table_type
            FROM information_schema.tables
            WHERE table_schema = 'catalog' AND table_name = 'creatures'
            """
        ).fetchone() == ("BASE TABLE",)
        assert connection.execute("SELECT COUNT(*) FROM catalog.creatures").fetchone() == (2,)
        assert connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'catalog'
              AND table_name IN ('json_documents', '__compact_creatures')
            ORDER BY table_name
            """
        ).fetchall() == [("json_documents",)]
        assert connection.execute("SELECT COUNT(*) FROM catalog.json_documents").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM catalog.compaction_plan").fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.compaction_checkpoints"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.compaction_manifest"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_compaction_resumes_after_committed_table_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()
    original_compact_table = catalog_compaction._compact_table

    def fail_at_creatures(
        connection: duckdb.DuckDBPyConnection,
        *,
        schema_name: str,
        table_name: str,
        columns: tuple[catalog_compaction.ColumnSpec, ...],
    ) -> catalog_compaction.TableCompaction:
        if table_name == "creatures":
            raise CatalogCompactionError("injected creature compaction failure")
        return original_compact_table(
            connection,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

    monkeypatch.setattr(catalog_compaction, "_compact_table", fail_at_creatures)
    try:
        with pytest.raises(CatalogCompactionError, match="injected creature"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )

        assert connection.execute(
            "SELECT source_table FROM catalog.compaction_checkpoints ORDER BY source_table"
        ).fetchall() == [("results",), ("runs",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.compaction_manifest"
        ).fetchone() == (0,)
        assert connection.execute(
            """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'catalog'
              AND table_name IN ('runs', 'results', 'creatures')
            ORDER BY table_name
            """
        ).fetchall() == [
            ("creatures", "BASE TABLE"),
            ("results", "VIEW"),
            ("runs", "VIEW"),
        ]

        resumed_tables: list[str] = []

        def observe_resume(
            connection: duckdb.DuckDBPyConnection,
            *,
            schema_name: str,
            table_name: str,
            columns: tuple[catalog_compaction.ColumnSpec, ...],
        ) -> catalog_compaction.TableCompaction:
            resumed_tables.append(table_name)
            return original_compact_table(
                connection,
                schema_name=schema_name,
                table_name=table_name,
                columns=columns,
            )

        monkeypatch.setattr(catalog_compaction, "_compact_table", observe_resume)
        report = compact_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )

        assert resumed_tables == ["creatures", "exports", "specimens", "qc_events"]
        assert [table.table_name for table in report.tables] == resumed_tables
        assert (
            verify_compacted_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            ).receipt_sha256
            == report.receipt_sha256
        )
        assert (
            connection.execute(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'catalog'
              AND table_name IN ('compaction_plan', 'compaction_checkpoints')
            """
            ).fetchall()
            == []
        )
    finally:
        connection.close()


def test_resumed_compaction_rejects_checkpoint_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()
    original_compact_table = catalog_compaction._compact_table

    def fail_after_runs(
        connection: duckdb.DuckDBPyConnection,
        *,
        schema_name: str,
        table_name: str,
        columns: tuple[catalog_compaction.ColumnSpec, ...],
    ) -> catalog_compaction.TableCompaction:
        if table_name == "results":
            raise CatalogCompactionError("injected result compaction failure")
        return original_compact_table(
            connection,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

    monkeypatch.setattr(catalog_compaction, "_compact_table", fail_after_runs)
    try:
        with pytest.raises(CatalogCompactionError, match="injected result"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
        connection.execute(
            "UPDATE catalog.compaction_checkpoints SET receipt_sha256 = ?",
            ["0" * 64],
        )
        monkeypatch.setattr(catalog_compaction, "_compact_table", original_compact_table)

        with pytest.raises(CatalogCompactionError, match="checkpoint runs SHA-256 mismatch"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.compaction_manifest"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_resumed_compaction_rejects_changed_plan_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()
    original_compact_table = catalog_compaction._compact_table

    def fail_after_runs(
        connection: duckdb.DuckDBPyConnection,
        *,
        schema_name: str,
        table_name: str,
        columns: tuple[catalog_compaction.ColumnSpec, ...],
    ) -> catalog_compaction.TableCompaction:
        if table_name == "results":
            raise CatalogCompactionError("injected result compaction failure")
        return original_compact_table(
            connection,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

    monkeypatch.setattr(catalog_compaction, "_compact_table", fail_after_runs)
    try:
        with pytest.raises(CatalogCompactionError, match="injected result"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )
        monkeypatch.setattr(catalog_compaction, "_compact_table", original_compact_table)

        with pytest.raises(CatalogCompactionError, match="plan changed"):
            compact_catalog(connection, required_writable_tables=())
        with pytest.raises(CatalogCompactionError, match="plan changed"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
                factor_specimen_manifests=True,
            )
    finally:
        connection.close()


def test_final_verification_failure_keeps_all_table_checkpoints_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _fixture_connection()
    original_verify = catalog_compaction.verify_compacted_catalog

    def reject_final_verification(*args: object, **kwargs: object) -> object:
        raise CatalogCompactionError("injected final verification failure")

    monkeypatch.setattr(
        catalog_compaction,
        "verify_compacted_catalog",
        reject_final_verification,
    )
    try:
        with pytest.raises(CatalogCompactionError, match="injected final verification"):
            compact_catalog(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            )

        assert connection.execute(
            "SELECT source_table FROM catalog.compaction_checkpoints ORDER BY source_table"
        ).fetchall() == [
            ("creatures",),
            ("exports",),
            ("qc_events",),
            ("results",),
            ("runs",),
            ("specimens",),
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM catalog.compaction_manifest"
        ).fetchone() == (0,)

        monkeypatch.setattr(catalog_compaction, "verify_compacted_catalog", original_verify)

        def reject_recompaction(*args: object, **kwargs: object) -> object:
            raise AssertionError("a completed table was compacted again")

        monkeypatch.setattr(catalog_compaction, "_compact_table", reject_recompaction)
        report = compact_catalog(
            connection,
            required_writable_tables=CANONICAL_WRITABLE_TABLES,
        )

        assert report.tables == ()
        assert (
            original_verify(
                connection,
                required_writable_tables=CANONICAL_WRITABLE_TABLES,
            ).receipt_sha256
            == report.receipt_sha256
        )
    finally:
        connection.close()
