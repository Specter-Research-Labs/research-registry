from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import duckdb
import pytest

from lenia_swarm_analysis.morphospace import consolidate as consolidate_module
from lenia_swarm_analysis.morphospace.compact_catalog import compact_catalog
from lenia_swarm_analysis.morphospace.consolidate import (
    ConsolidationError,
    ConsolidationVerificationError,
    build_consolidated_database,
    verify_consolidated_candidate,
    verify_consolidated_database,
)
from lenia_swarm_analysis.morphospace.warehouse import connect_database, file_sha256
from lenia_swarm_analysis.morphospace_cli import main as morphospace_main


def _identity(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _write_v10_warehouse(path: Path) -> None:
    connection = connect_database(path)
    try:
        connection.execute(
            "CREATE TABLE consolidation_probe (probe_id BIGINT PRIMARY KEY, payload VARCHAR)"
        )
        connection.executemany(
            "INSERT INTO consolidation_probe VALUES (?, ?)",
            [(1, "first"), (2, "second")],
        )
        connection.execute(
            "CREATE VIEW consolidation_probe_view AS "
            "SELECT probe_id, payload FROM consolidation_probe WHERE probe_id = 2"
        )
        connection.execute("FORCE CHECKPOINT")
    finally:
        connection.close()


def _write_compendium(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE creatures (
                creature_id TEXT PRIMARY KEY,
                canonical INTEGER NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO creatures(rowid, creature_id, canonical, raw_json) VALUES (?, ?, ?, ?)",
            (11, "canonical", 1, '{"x":1}'),
        )
        connection.execute(
            "INSERT INTO creatures(rowid, creature_id, canonical, raw_json) VALUES (?, ?, ?, ?)",
            (29, "noncanonical", 0, '  { "z": [3, 2], "x": 1 }\n'),
        )
        connection.execute(
            """
            CREATE TABLE future_payload (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_kind TEXT NOT NULL,
                payload BLOB NOT NULL,
                exact_integer INTEGER NOT NULL,
                score REAL NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO future_payload(payload_kind, payload, exact_integer, score) "
            "VALUES (?, ?, ?, ?)",
            [
                ("alpha", b"\x00\x01", 9_007_199_254_740_993, 1.25),
                ("beta", b"future", -9_007_199_254_740_993, -0.0),
            ],
        )
        connection.execute("CREATE INDEX future_payload_kind ON future_payload(payload_kind)")
        connection.execute(
            """
            CREATE TABLE keyed_state (
                scope TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (scope, ordinal)
            ) WITHOUT ROWID
            """
        )
        connection.executemany(
            "INSERT INTO keyed_state VALUES (?, ?, ?)",
            [("b", 2, "last"), ("a", 1, "first")],
        )
        connection.execute(
            "CREATE VIEW canonical_creatures AS SELECT * FROM creatures WHERE canonical = 1"
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def database_sources(tmp_path: Path) -> tuple[Path, Path]:
    warehouse = tmp_path / "morphospace.duckdb"
    compendium = tmp_path / "compendium.sqlite"
    _write_v10_warehouse(warehouse)
    _write_compendium(compendium)
    return warehouse, compendium


def _producer_verification(**overrides: object) -> dict[str, object]:
    verification: dict[str, object] = {
        "contentHashAlgorithm": "sha256",
        "receiptCanonicalization": consolidate_module.RECEIPT_CANONICALIZATION,
        "rowDigestAlgorithm": consolidate_module.ROW_DIGEST_ALGORITHM,
        "catalogDigestAlgorithm": consolidate_module.CATALOG_DIGEST_ALGORITHM,
        "duckdbVersion": duckdb.__version__,
        "sqliteVersion": sqlite3.sqlite_version,
    }
    verification.update(overrides)
    return verification


def test_consolidation_preserves_all_rows_raw_text_rowids_and_v10_tables(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "consolidated.duckdb"
    warehouse_sha256 = file_sha256(warehouse)
    compendium_sha256 = file_sha256(compendium)
    warehouse_identity = _identity(warehouse)
    compendium_identity = _identity(compendium)

    result = build_consolidated_database(warehouse, compendium, destination)

    assert destination.is_file()
    assert file_sha256(warehouse) == warehouse_sha256
    assert file_sha256(compendium) == compendium_sha256
    assert _identity(warehouse) == warehouse_identity
    assert _identity(compendium) == compendium_identity
    assert result.imported_row_counts == {
        "creatures": 2,
        "future_payload": 2,
        "keyed_state": 2,
        "sqlite_sequence": 1,
    }
    assert result.warehouse_row_counts["consolidation_probe"] == 2
    assert not Path(f"{destination}.wal").exists()

    connection = duckdb.connect(str(destination), read_only=True)
    try:
        assert connection.execute(
            "SELECT * FROM main.consolidation_probe ORDER BY probe_id"
        ).fetchall() == [(1, "first"), (2, "second")]
        assert connection.execute("SELECT * FROM main.consolidation_probe_view").fetchall() == [
            (2, "second")
        ]
        assert connection.execute(
            """
            SELECT _source_rowid, creature_id, canonical, raw_json
            FROM catalog.creatures
            ORDER BY _source_rowid
            """
        ).fetchall() == [
            (11, "canonical", 1, '{"x":1}'),
            (29, "noncanonical", 0, '  { "z": [3, 2], "x": 1 }\n'),
        ]
        assert connection.execute(
            "SELECT count(*) FROM catalog.creatures WHERE canonical = 0"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT _source_rowid, payload_kind, payload, exact_integer, score "
            "FROM catalog.future_payload ORDER BY 1"
        ).fetchall() == [
            (1, "alpha", b"\x00\x01", 9_007_199_254_740_993, 1.25),
            (2, "beta", b"future", -9_007_199_254_740_993, -0.0),
        ]
        assert connection.execute("SELECT count(*) FROM catalog.sqlite_sequence").fetchone() == (1,)
        assert connection.execute(
            "SELECT _source_rowid, scope, ordinal, payload FROM catalog.keyed_state "
            "ORDER BY scope, ordinal"
        ).fetchall() == [
            (None, "a", 1, "first"),
            (None, "b", 2, "last"),
        ]
        ddl_rows = connection.execute(
            """
            SELECT object_name, ddl
            FROM consolidation.sqlite_master_objects
            ORDER BY ordinal
            """
        ).fetchall()
        assert any(
            name == "future_payload_kind" and "CREATE INDEX" in ddl for name, ddl in ddl_rows
        )
        assert any(name == "canonical_creatures" and "CREATE VIEW" in ddl for name, ddl in ddl_rows)
        receipt_rows = connection.execute(
            "SELECT receipt_sha256, manifest_json FROM consolidation.manifest"
        ).fetchall()
        assert len(receipt_rows) == 1
        manifest = json.loads(receipt_rows[0][1])
        assert receipt_rows[0][0] == result.receipt_sha256 == manifest["receiptSha256"]
        assert manifest["derivedRecomputationPerformed"] is False
        assert sorted(manifest["compendium"]["tables"]) == [
            "creatures",
            "future_payload",
            "keyed_state",
            "sqlite_sequence",
        ]
    finally:
        connection.close()

    verification = verify_consolidated_database(warehouse, compendium, destination)
    assert verification.receipt_sha256 == result.receipt_sha256
    assert verification.database_sha256 == result.destination_sha256
    assert verification.imported_row_counts == result.imported_row_counts


def test_consolidation_digest_connections_use_bounded_resources_and_clean_spill(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "bounded.duckdb"
    original_digest = consolidate_module._candidate_stream_digest
    observations: list[tuple[object, object, object, Path]] = []

    def observe_settings(
        connection: duckdb.DuckDBPyConnection,
        plan: consolidate_module.SQLiteTablePlan,
    ) -> dict[str, object]:
        settings = connection.execute(
            """
            SELECT current_setting('memory_limit'),
                   current_setting('threads'),
                   current_setting('preserve_insertion_order'),
                   current_setting('temp_directory')
            """
        ).fetchone()
        assert settings is not None
        observations.append((*settings[:3], Path(str(settings[3]))))
        return original_digest(connection, plan)

    monkeypatch.setattr(consolidate_module, "_candidate_stream_digest", observe_settings)

    build_consolidated_database(warehouse, compendium, destination)

    assert observations
    build_spills = [row[3] for row in observations if ".verify-" not in row[3].name]
    verifier_spills = [row[3] for row in observations if ".verify-" in row[3].name]
    assert build_spills
    assert verifier_spills
    for memory_limit, threads, preserve_insertion_order, spill in observations:
        assert str(memory_limit).replace(".0", "") == (
            consolidate_module.CONSOLIDATION_MEMORY_LIMIT
        )
        assert threads == consolidate_module.CONSOLIDATION_THREADS
        assert preserve_insertion_order is False
        assert spill.parent == tmp_path
        assert not spill.exists()

    observations.clear()
    observer = duckdb.connect(str(destination), read_only=True)
    try:
        before = observer.execute(
            """
            SELECT current_setting('memory_limit'),
                   current_setting('threads'),
                   current_setting('preserve_insertion_order'),
                   current_setting('temp_directory')
            """
        ).fetchone()
        verify_consolidated_candidate(destination)
        after = observer.execute(
            """
            SELECT current_setting('memory_limit'),
                   current_setting('threads'),
                   current_setting('preserve_insertion_order'),
                   current_setting('temp_directory')
            """
        ).fetchone()
    finally:
        observer.close()

    assert observations
    assert all(".verify-" in row[3].name for row in observations)
    assert all(not row[3].exists() for row in observations)
    assert after == before


def test_consolidation_cleans_created_spill_after_digest_failure(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "failed-build.duckdb"
    spills: list[Path] = []

    def fail_after_creating_spill(
        connection: duckdb.DuckDBPyConnection,
        plan: consolidate_module.SQLiteTablePlan,
    ) -> dict[str, object]:
        del plan
        row = connection.execute("SELECT current_setting('temp_directory')").fetchone()
        assert row is not None
        spill = Path(str(row[0]))
        spill.mkdir(parents=True, exist_ok=True)
        (spill / "forced-spill.tmp").write_bytes(b"spill")
        spills.append(spill)
        raise RuntimeError("injected digest failure")

    monkeypatch.setattr(
        consolidate_module,
        "_candidate_stream_digest",
        fail_after_creating_spill,
    )

    with pytest.raises(RuntimeError, match="injected digest failure"):
        build_consolidated_database(warehouse, compendium, destination)

    assert spills
    assert all(not spill.exists() for spill in spills)
    assert not destination.exists()


def test_candidate_verifier_cleans_created_spill_after_digest_failure(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "failed-verification.duckdb"
    build_consolidated_database(warehouse, compendium, destination)
    spills: list[Path] = []

    def fail_after_creating_spill(
        connection: duckdb.DuckDBPyConnection,
        plan: consolidate_module.SQLiteTablePlan,
    ) -> dict[str, object]:
        del plan
        row = connection.execute("SELECT current_setting('temp_directory')").fetchone()
        assert row is not None
        spill = Path(str(row[0]))
        spill.mkdir(parents=True, exist_ok=True)
        (spill / "forced-spill.tmp").write_bytes(b"spill")
        spills.append(spill)
        raise RuntimeError("injected verification failure")

    monkeypatch.setattr(
        consolidate_module,
        "_candidate_stream_digest",
        fail_after_creating_spill,
    )

    with pytest.raises(RuntimeError, match="injected verification failure"):
        verify_consolidated_candidate(destination)

    assert spills
    assert all(not spill.exists() for spill in spills)


def test_compaction_aware_verifier_rechecks_original_manifest_semantics(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "compacted.duckdb"
    build_consolidated_database(warehouse, compendium, destination)

    connection = duckdb.connect(str(destination))
    try:
        compact_catalog(connection)
        connection.execute("FORCE CHECKPOINT")
    finally:
        connection.close()

    with pytest.raises(
        ConsolidationVerificationError,
        match="logical-object inventory mismatch",
    ):
        verify_consolidated_candidate(destination)
    verification = verify_consolidated_candidate(
        destination,
        allow_catalog_extensions=True,
    )
    assert verification.imported_row_counts["creatures"] == 2

    connection = duckdb.connect(str(destination))
    try:
        connection.execute(
            "UPDATE catalog.__compact_creatures SET canonical = 0 WHERE creature_id = 'canonical'"
        )
        connection.execute("FORCE CHECKPOINT")
    finally:
        connection.close()
    with pytest.raises(
        ConsolidationVerificationError,
        match="catalog table digest mismatch: creatures",
    ):
        verify_consolidated_candidate(
            destination,
            allow_catalog_extensions=True,
        )


def test_compacted_candidate_digest_preserves_lsc1_bytes_with_bounded_batches(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "bounded-compacted.duckdb"
    build_consolidated_database(warehouse, compendium, destination)

    connection = duckdb.connect(str(destination))
    try:
        compact_catalog(connection)
        plan = consolidate_module.SQLiteTablePlan(
            name="creatures",
            columns=("creature_id", "canonical", "raw_json"),
            declared_types=("TEXT", "INTEGER", "TEXT"),
            primary_key=("creature_id",),
            rowid_alias="rowid",
        )
        expected = consolidate_module._logical_candidate_stream_digest(connection, plan)
        layout = consolidate_module._compact_candidate_layout(connection, plan)
        assert layout is not None

        document_batches: list[set[int]] = []
        original_document_texts = consolidate_module._compact_document_texts

        def observe_document_batch(
            connection: duckdb.DuckDBPyConnection,
            *,
            documents: str,
            document_ids: set[int],
        ) -> dict[int, str]:
            document_batches.append(document_ids)
            return original_document_texts(
                connection,
                documents=documents,
                document_ids=document_ids,
            )

        monkeypatch.setattr(consolidate_module, "COMPACT_CANDIDATE_ROW_BATCH_SIZE", 1)
        monkeypatch.setattr(consolidate_module, "COMPACT_CANDIDATE_DOCUMENT_BATCH_IDS", 1)
        monkeypatch.setattr(
            consolidate_module,
            "COMPACT_CANDIDATE_DOCUMENT_BATCH_BYTES",
            1,
        )
        monkeypatch.setattr(
            consolidate_module,
            "_compact_document_texts",
            observe_document_batch,
        )

        assert consolidate_module._candidate_stream_digest(connection, plan) == expected
        assert len(document_batches) == 2
        assert all(len(document_ids) == 1 for document_ids in document_batches)
    finally:
        connection.close()


def test_compacted_candidate_digest_does_not_fall_back_to_logical_sort(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "compact-fast-path.duckdb"
    build_consolidated_database(warehouse, compendium, destination)
    connection = duckdb.connect(str(destination))
    try:
        compact_catalog(connection)
        plan = consolidate_module.SQLiteTablePlan(
            name="creatures",
            columns=("creature_id", "canonical", "raw_json"),
            declared_types=("TEXT", "INTEGER", "TEXT"),
            primary_key=("creature_id",),
            rowid_alias="rowid",
        )

        def reject_logical_sort(
            _connection: duckdb.DuckDBPyConnection,
            _plan: consolidate_module.SQLiteTablePlan,
        ) -> dict[str, object]:
            raise AssertionError("compacted candidate used the logical row sort")

        monkeypatch.setattr(
            consolidate_module,
            "_logical_candidate_stream_digest",
            reject_logical_sort,
        )

        assert consolidate_module._candidate_stream_digest(connection, plan)["rowCount"] == 2
    finally:
        connection.close()


def test_consolidation_is_repeatable_and_refuses_existing_destination(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    first_path = tmp_path / "first.duckdb"
    second_path = tmp_path / "second.duckdb"

    first = build_consolidated_database(warehouse, compendium, first_path)
    second = build_consolidated_database(warehouse, compendium, second_path)

    assert first.receipt_sha256 == second.receipt_sha256
    assert first.imported_row_counts == second.imported_row_counts
    assert first.warehouse_row_counts == second.warehouse_row_counts
    existing_sha256 = file_sha256(first_path)
    with pytest.raises(FileExistsError):
        build_consolidated_database(warehouse, compendium, first_path)
    assert file_sha256(first_path) == existing_sha256


def test_verification_detects_catalog_row_mutation(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "mutated.duckdb"
    build_consolidated_database(warehouse, compendium, destination)
    connection = duckdb.connect(str(destination))
    try:
        connection.execute(
            "UPDATE catalog.creatures SET raw_json = 'changed' WHERE creature_id = 'canonical'"
        )
        connection.execute("FORCE CHECKPOINT")
    finally:
        connection.close()

    with pytest.raises(ConsolidationVerificationError, match="catalog table digest mismatch"):
        verify_consolidated_database(warehouse, compendium, destination)


def test_candidate_verification_does_not_require_old_sources(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "self-contained.duckdb"
    result = build_consolidated_database(warehouse, compendium, destination)
    warehouse.unlink()
    compendium.unlink()

    verification = verify_consolidated_candidate(destination)

    assert verification.receipt_sha256 == result.receipt_sha256
    assert verification.database_sha256 == result.destination_sha256


def test_verification_accepts_authenticated_producer_version_drift(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "older-producer.duckdb"
    with monkeypatch.context() as producer:
        producer.setattr(consolidate_module.duckdb, "__version__", "1.5.0")
        producer.setattr(consolidate_module.sqlite3, "sqlite_version", "3.50.4")
        result = build_consolidated_database(warehouse, compendium, destination)

    candidate = verify_consolidated_candidate(destination)
    source_bound = verify_consolidated_database(warehouse, compendium, destination)

    assert candidate.receipt_sha256 == result.receipt_sha256
    assert source_bound.receipt_sha256 == result.receipt_sha256


@pytest.mark.parametrize(
    "verification",
    [
        {
            "contentHashAlgorithm": "sha256",
            "receiptCanonicalization": consolidate_module.RECEIPT_CANONICALIZATION,
            "rowDigestAlgorithm": consolidate_module.ROW_DIGEST_ALGORITHM,
            "catalogDigestAlgorithm": consolidate_module.CATALOG_DIGEST_ALGORITHM,
            "duckdbVersion": "1.5.0",
        },
        _producer_verification(extraProducerField="unexpected"),
        _producer_verification(rowDigestAlgorithm="unrecognized-row-digest"),
        _producer_verification(duckdbVersion=""),
        _producer_verification(sqliteVersion=3504),
    ],
    ids=[
        "missing-key",
        "extra-key",
        "algorithm-drift",
        "empty-duckdb-version",
        "non-string-sqlite-version",
    ],
)
def test_manifest_contract_rejects_every_non_version_drift(
    verification: dict[str, object],
) -> None:
    manifest = {
        "format": consolidate_module.CONSOLIDATION_FORMAT,
        "verification": verification,
    }

    with pytest.raises(ConsolidationVerificationError):
        consolidate_module._validate_manifest_contract(manifest)


def test_candidate_verification_detects_index_mutation(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "index-mutated.duckdb"
    build_consolidated_database(warehouse, compendium, destination)
    connection = duckdb.connect(str(destination))
    try:
        connection.execute("CREATE INDEX injected_index ON catalog.creatures(creature_id)")
        connection.execute("FORCE CHECKPOINT")
    finally:
        connection.close()

    with pytest.raises(ConsolidationVerificationError, match="logical-object inventory"):
        verify_consolidated_candidate(destination)


def test_numeric_affinity_large_integer_fails_before_coercive_import(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    warehouse, compendium = database_sources
    connection = sqlite3.connect(compendium)
    try:
        connection.execute("CREATE TABLE lossy_numeric (value NUMERIC NOT NULL)")
        connection.execute(
            "INSERT INTO lossy_numeric VALUES (?)",
            (9_007_199_254_740_993,),
        )
        connection.commit()
    finally:
        connection.close()
    destination = tmp_path / "numeric-rejected.duckdb"

    with pytest.raises(ConsolidationError, match="NUMERIC affinity"):
        build_consolidated_database(warehouse, compendium, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(f".{destination.name}.*snapshot*"))
    assert not list(tmp_path.glob(f".{destination.name}.building-*"))


def test_wal_mode_source_directory_is_unchanged(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "sources"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    output_dir.mkdir()
    warehouse = source_dir / "morphospace.duckdb"
    compendium = source_dir / "compendium.sqlite"
    destination = output_dir / "consolidated.duckdb"
    _write_v10_warehouse(warehouse)
    _write_compendium(compendium)
    connection = sqlite3.connect(compendium)
    try:
        assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
    finally:
        connection.close()

    before = {
        path.name: (_identity(path), file_sha256(path))
        for path in source_dir.iterdir()
        if path.is_file()
    }
    before_entries = tuple(sorted(path.name for path in source_dir.iterdir()))
    result = build_consolidated_database(warehouse, compendium, destination)
    verification = verify_consolidated_database(warehouse, compendium, destination)
    after = {
        path.name: (_identity(path), file_sha256(path))
        for path in source_dir.iterdir()
        if path.is_file()
    }
    after_entries = tuple(sorted(path.name for path in source_dir.iterdir()))

    assert after_entries == before_entries
    assert after == before
    assert verification.receipt_sha256 == result.receipt_sha256
    assert not list(output_dir.glob("*.sqlite-*"))
    assert not list(output_dir.glob(".*snapshot*"))


@pytest.mark.parametrize("failing_fsync_call", [1, 2])
def test_publication_fsync_failure_rolls_back_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_fsync_call: int,
) -> None:
    build = tmp_path / ".candidate.building"
    destination = tmp_path / "candidate.duckdb"
    build.write_bytes(b"candidate")
    real_fsync = consolidate_module.os.fsync
    call_count = 0

    def fail_once(descriptor: int) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == failing_fsync_call:
            raise OSError("injected fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(consolidate_module.os, "fsync", fail_once)

    with pytest.raises(OSError, match="injected fsync failure"):
        consolidate_module._publish_no_clobber(build, destination)

    assert build.read_bytes() == b"candidate"
    assert not destination.exists()


def test_publication_unlink_failure_rolls_back_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = tmp_path / ".candidate.building"
    destination = tmp_path / "candidate.duckdb"
    build.write_bytes(b"candidate")
    real_unlink = Path.unlink
    failure_injected = False

    def fail_build_unlink(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal failure_injected
        if path == build and not failure_injected:
            failure_injected = True
            raise OSError("injected unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_build_unlink)

    with pytest.raises(OSError, match="injected unlink failure"):
        consolidate_module._publish_no_clobber(build, destination)

    assert build.read_bytes() == b"candidate"
    assert not destination.exists()


@pytest.mark.parametrize("source_kind", ["warehouse", "compendium"])
def test_consolidation_rejects_nonempty_source_wal_without_publishing(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    source_kind: str,
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / f"rejected-{source_kind}.duckdb"
    wal_path = Path(f"{warehouse}.wal") if source_kind == "warehouse" else Path(f"{compendium}-wal")
    wal_path.write_bytes(b"pending transaction")

    with pytest.raises(ConsolidationError, match="nonempty"):
        build_consolidated_database(warehouse, compendium, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(f".{destination.name}.building-*"))
    assert wal_path.read_bytes() == b"pending transaction"


def test_consolidation_cli_builds_and_verifies_json(
    database_sources: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    warehouse, compendium = database_sources
    destination = tmp_path / "cli-consolidated.duckdb"

    assert (
        morphospace_main(
            [
                "consolidate-database",
                "--warehouse",
                str(warehouse),
                "--compendium",
                str(compendium),
                "--destination",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert built["destination"]["path"] == str(destination)
    assert built["importedRowCounts"]["creatures"] == 2
    assert len(built["externalReceiptSha256"]) == 64

    assert (
        morphospace_main(
            [
                "verify-consolidated-database",
                "--warehouse",
                str(warehouse),
                "--compendium",
                str(compendium),
                "--database",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    verified = json.loads(capsys.readouterr().out)
    assert verified["verified"] is True
    assert verified["receiptSha256"] == built["receiptSha256"]

    assert (
        morphospace_main(
            [
                "verify-consolidated-candidate",
                "--database",
                str(destination),
                "--json",
            ]
        )
        == 0
    )
    self_contained = json.loads(capsys.readouterr().out)
    assert self_contained["receiptSha256"] == built["receiptSha256"]
