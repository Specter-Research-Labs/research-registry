from __future__ import annotations

import gzip
import json
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from analysis.lake.db import (
    SCHEMA_VERSION,
    connect,
    ensure_schema,
    root_id_for_path,
    run_key_for,
    run_key_for_run_dir,
)
from analysis.lake.export_parquet import export_parquet
from analysis.lake.reconcile import ReconcileReport, reconcile


@dataclass(frozen=True)
class Lake:
    tmp_path: Path
    logs_root: Path
    conn: duckdb.DuckDBPyConnection

    def reconcile(self, *logs_dirs: Path, prune: bool = False) -> ReconcileReport:
        return reconcile(
            self.conn,
            logs_dirs=list(logs_dirs or [self.logs_root]),
            prune=prune,
        )

    def count(
        self,
        table: str,
        where: str = "",
        params: list[object] | None = None,
    ) -> int:
        query = f"SELECT count(*) FROM {table}"
        if where:
            query += f" WHERE {where}"
        return int(_scalar(self.conn, query, params))

    def run_count(self, table: str, run_key: str) -> int:
        return self.count(table, "run_key = ?", [run_key])


@pytest.fixture
def lake(tmp_path: Path) -> Iterator[Lake]:
    conn = connect(tmp_path / "lake.duckdb")
    try:
        ensure_schema(conn)
        yield Lake(tmp_path=tmp_path, logs_root=tmp_path / "logs", conn=conn)
    finally:
        conn.close()


def _scalar(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    params: list[object] | None = None,
) -> object:
    cur = conn.execute(query, params) if params is not None else conn.execute(query)
    row = cur.fetchone()
    assert row is not None
    return row[0]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _summary(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "goal_sig_scheme": "ast",
        "theorems": [
            {
                "name": "t1",
                "wild_type": {"solved": True, "iterations": 2, "proof_term_hash": "h1"},
                "interventions": [],
            }
        ],
        "aggregates": {},
    }


def _basin_analysis(theorem: str, *, paper_k: object | None = None) -> dict:
    paper_k_payload = {"K": 0.82, "tau_agent": 5, "tau_blind": 33} if paper_k is None else paper_k
    return {
        "theorem_name": theorem,
        "seeds": [0, 1, 2],
        "seed_results": [
            {
                "seed": 0,
                "solved": True,
                "structure_hash": "abc",
                "iterations_to_solve": 5,
                "attempts_total": 10,
            },
            {
                "seed": 1,
                "solved": False,
                "structure_hash": None,
                "iterations_to_solve": None,
                "attempts_total": 10,
            },
            {
                "seed": 2,
                "solved": True,
                "structure_hash": "abc",
                "iterations_to_solve": 3,
                "attempts_total": 10,
            },
        ],
        "solve_rate": 0.667,
        "unique_structures": 1,
        "dominant_structure_frequency": 1.0,
        "structure_distribution": {"abc": 2},
        "blind_solve_rate": 0.1,
        "paper_k": paper_k_payload,
    }


def _make_run(
    logs_root: Path,
    name: str,
    *,
    with_summary: bool = True,
    with_basin: bool = False,
    basin_payload: dict | None = None,
    run_config_extra: dict | None = None,
) -> Path:
    run_dir = logs_root / name
    run_config = {
        "run_id": name,
        "backend": "lean",
        "provider": "reprover",
        "mode": "dev",
    }
    if run_config_extra:
        run_config.update(run_config_extra)
    _write_json(run_dir / "run_config.json", run_config)
    if with_summary:
        _write_json_gz(run_dir / "summary.json.gz", _summary(name))
    _write_json_gz(run_dir / "goal_cache.json.gz", {"entries": {}})
    if with_basin:
        _write_json(
            run_dir / "t1" / "basin_analysis.json",
            basin_payload if basin_payload is not None else _basin_analysis("t1"),
        )
    return run_dir


V5_LEGACY_TABLES: dict[str, tuple[str, ...]] = {
    "schema_meta": (
        "schema_version INTEGER NOT NULL",
        "created_at TIMESTAMP NOT NULL DEFAULT now()",
    ),
    "log_roots": (
        "root_id VARCHAR PRIMARY KEY",
        "root_path VARCHAR NOT NULL",
        "created_at TIMESTAMP NOT NULL DEFAULT now()",
    ),
    "runs": (
        "run_key VARCHAR PRIMARY KEY",
        "root_id VARCHAR NOT NULL",
        "rel_run_dir VARCHAR NOT NULL",
        "run_id VARCHAR",
        "provider VARCHAR",
        "backend VARCHAR",
        "mode VARCHAR",
        "corpus VARCHAR",
        "created_at VARCHAR",
        "goal_sig_scheme VARCHAR",
        "trace_mcts BOOLEAN",
        "problem_space JSON",
        "config_whitelist_hash VARCHAR",
        "config_full_hash VARCHAR",
        "run_config JSON",
        "run_status JSON",
        "indexed_at TIMESTAMP NOT NULL DEFAULT now()",
    ),
    "run_files": (
        "run_key VARCHAR NOT NULL",
        "file_name VARCHAR NOT NULL",
        "sha256 VARCHAR",
        "bytes BIGINT",
        "mtime_epoch BIGINT",
        "PRIMARY KEY (run_key, file_name)",
    ),
    "theorem_wild": (
        "run_key VARCHAR NOT NULL",
        "theorem VARCHAR NOT NULL",
        "solved BOOLEAN",
        "iterations BIGINT",
        "proof_term_hash VARCHAR",
        "k_valid BOOLEAN",
        "k_null_model VARCHAR",
        "k_tau_agent BIGINT",
        "k_tau_blind DOUBLE",
        "k_K DOUBLE",
        "metrics JSON",
        "k_json JSON",
        "wild_json JSON",
        "PRIMARY KEY (run_key, theorem)",
    ),
}


def _seed_v5_nested_duplicate_lake(
    db_path: Path,
    *,
    parent_root: Path,
    child_root: Path,
) -> tuple[str, Path]:
    parent_rid = root_id_for_path(parent_root)
    child_rid = root_id_for_path(child_root)
    legacy_parent_key = run_key_for(parent_rid, "campaign-a/run-1")
    legacy_child_key = run_key_for(child_rid, "run-1")
    run_payload = json.dumps(
        {"run_id": "run-1", "provider": "reprover", "backend": "lean", "mode": "dev"}
    )

    conn = duckdb.connect(str(db_path))
    try:
        for table, columns in V5_LEGACY_TABLES.items():
            conn.execute(f"CREATE TABLE {table} ({', '.join(columns)})")
        conn.execute("INSERT INTO schema_meta(schema_version) VALUES (5)")
        conn.executemany(
            "INSERT INTO log_roots(root_id, root_path) VALUES (?, ?)",
            [(parent_rid, str(parent_root)), (child_rid, str(child_root))],
        )
        conn.executemany(
            """
            INSERT INTO runs(
              run_key, root_id, rel_run_dir, run_id, provider, backend, mode, run_config
            ) VALUES (?, ?, ?, 'run-1', 'reprover', 'lean', 'dev', ?)
            """,
            [
                (legacy_parent_key, parent_rid, "campaign-a/run-1", run_payload),
                (legacy_child_key, child_rid, "run-1", run_payload),
            ],
        )
        conn.executemany(
            """
            INSERT INTO run_files(run_key, file_name, sha256, bytes, mtime_epoch)
            VALUES (?, 'run_config.json', 'abc', 12, 1)
            """,
            [(legacy_parent_key,), (legacy_child_key,)],
        )
        conn.executemany(
            """
            INSERT INTO theorem_wild(run_key, theorem, solved, iterations, proof_term_hash)
            VALUES (?, 't1', true, 2, 'h1')
            """,
            [(legacy_parent_key,), (legacy_child_key,)],
        )
    finally:
        conn.close()

    return parent_rid, (child_root / "run-1").resolve()


def test_reconcile_index_extract_in_one_pass(lake: Lake) -> None:
    _make_run(lake.logs_root, "run-1")
    _make_run(lake.logs_root, "run-2")

    report = lake.reconcile()

    assert report.index.runs_indexed == 2
    assert report.extract.runs_extracted == 2
    assert report.extract.wild_rows == 2
    assert report.basin.basin_run_rows == 0
    assert report.basin.errors == []
    assert report.stale_run_keys == []
    assert report.pruned == 0


def test_reconcile_basin_extraction(lake: Lake) -> None:
    _make_run(lake.logs_root, "run-basin", with_basin=True)

    report = lake.reconcile()

    assert report.basin.basin_run_rows == 1
    assert report.basin.basin_seed_rows == 3
    assert report.basin.basin_structure_rows == 1

    basin_row = lake.conn.execute(
        """
        SELECT theorem, seeds_requested, solve_rate, unique_structures,
               blind_solve_rate, paper_k
        FROM basin_runs
        """
    ).fetchone()
    assert basin_row == (
        "t1",
        3,
        pytest.approx(0.667, abs=0.01),
        1,
        pytest.approx(0.1, abs=0.01),
        pytest.approx(0.82, abs=0.01),
    )

    seed_rows = lake.conn.execute(
        """
        SELECT seed, solved, structure_hash, iterations_to_solve
        FROM basin_seed
        ORDER BY seed
        """
    ).fetchall()
    assert seed_rows == [
        (0, True, "abc", 5),
        (1, False, None, None),
        (2, True, "abc", 3),
    ]

    assert lake.conn.execute(
        "SELECT structure_hash, count FROM basin_structure_counts"
    ).fetchall() == [("abc", 2)]


def test_reconcile_basin_only_run_clears_stale_summary_state(lake: Lake) -> None:
    run_dir = _make_run(
        lake.logs_root,
        "run-basin-only",
        with_basin=True,
        run_config_extra={"basin_seeds": 50},
    )

    report = lake.reconcile()
    assert report.extract.runs_extracted == 1
    assert lake.count("theorem_wild") == 1

    (run_dir / "summary.json.gz").unlink()

    report2 = lake.reconcile()
    assert report2.extract.runs_extracted == 0
    assert report2.extract.errors == []
    assert report2.basin.basin_run_rows == 1
    assert lake.count("theorem_wild") == 0
    assert lake.count("basin_runs") == 1
    assert lake.count("extract_errors", "stage = 'read_summary'") == 0


def test_reconcile_basin_extraction_nested_paper_k_shape(lake: Lake) -> None:
    _make_run(
        lake.logs_root,
        "run-basin-nested",
        with_basin=True,
        basin_payload=_basin_analysis(
            "t1",
            paper_k={
                "schema_version": 1,
                "K": {
                    "lower_bound_censored_at_H": 0.37,
                    "conditional_on_both_solved": None,
                },
            },
        ),
    )

    report = lake.reconcile()

    assert report.basin.basin_run_rows == 1
    assert _scalar(lake.conn, "SELECT paper_k FROM basin_runs") == pytest.approx(0.37)


def test_reconcile_malformed_basin_records_error(lake: Lake) -> None:
    run_dir = _make_run(lake.logs_root, "run-bad-basin")
    theorem_dir = run_dir / "t1"
    theorem_dir.mkdir(parents=True, exist_ok=True)
    (theorem_dir / "basin_analysis.json").write_text("not json", encoding="utf-8")

    report = lake.reconcile()

    assert report.basin.basin_run_rows == 0
    assert lake.count("extract_errors", "stage = 'read_basin'") == 1


def test_reconcile_prune_deletes_stale_runs(lake: Lake) -> None:
    run_keep = _make_run(lake.logs_root, "run-keep")
    run_delete = _make_run(lake.logs_root, "run-delete", with_basin=True)

    report = lake.reconcile()
    assert report.index.runs_indexed == 2
    assert report.basin.basin_run_rows == 1

    stale_key = run_key_for_run_dir(run_delete.resolve())
    shutil.rmtree(run_delete)

    report2 = lake.reconcile(prune=False)
    assert report2.stale_run_keys == [stale_key]
    assert report2.pruned == 0
    assert lake.run_count("runs", stale_key) == 1

    report3 = lake.reconcile(prune=True)
    assert report3.pruned == 1
    assert lake.run_count("runs", stale_key) == 0
    assert lake.run_count("basin_runs", stale_key) == 0
    assert lake.run_count("basin_seed", stale_key) == 0
    assert lake.run_count("basin_structure_counts", stale_key) == 0

    kept_key = run_key_for_run_dir(run_keep.resolve())
    assert lake.run_count("runs", kept_key) == 1


def test_reconcile_prune_deletes_stale_mcts_tree_rows(lake: Lake) -> None:
    run_delete = _make_run(lake.logs_root, "run-delete")
    _write_json(
        run_delete / "t1" / "wild_type_mcts_tree.json",
        {
            "nodes": {
                "n0": {
                    "goal_type": "goal",
                    "goal_sig": "sig0",
                    "depth": 0,
                    "visit_count": 3,
                    "success_count": 1,
                    "children": {"intro": ["n1"]},
                },
                "n1": {
                    "goal_type": "goal",
                    "goal_sig": "sig1",
                    "depth": 1,
                    "visit_count": 1,
                    "success_count": 1,
                    "is_terminal": True,
                },
            }
        },
    )

    lake.reconcile()

    stale_key = run_key_for_run_dir(run_delete.resolve())
    assert lake.run_count("mcts_tree_nodes", stale_key) == 2
    assert lake.run_count("mcts_tree_edges", stale_key) == 1

    shutil.rmtree(run_delete)

    report = lake.reconcile(prune=True)
    assert report.pruned == 1
    assert lake.run_count("mcts_tree_nodes", stale_key) == 0
    assert lake.run_count("mcts_tree_edges", stale_key) == 0


def test_reconcile_nested_roots_share_one_run_identity(lake: Lake) -> None:
    child_root = lake.logs_root / "campaign-a"
    run_dir = _make_run(child_root, "run-1")

    lake.reconcile()
    lake.reconcile(child_root)

    assert lake.conn.execute(
        "SELECT run_key, root_id, rel_run_dir, run_dir FROM runs ORDER BY run_key"
    ).fetchall() == [
        (
            run_key_for_run_dir(run_dir.resolve()),
            root_id_for_path(lake.logs_root.resolve()),
            "campaign-a/run-1",
            str(run_dir.resolve()),
        )
    ]


def test_ensure_schema_migrates_v5_nested_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "lake.duckdb"
    parent_root = (tmp_path / "logs").resolve()
    child_root = (parent_root / "campaign-a").resolve()
    parent_rid, run_dir = _seed_v5_nested_duplicate_lake(
        db_path,
        parent_root=parent_root,
        child_root=child_root,
    )

    conn = connect(db_path)
    try:
        ensure_schema(conn)
        assert _scalar(conn, "SELECT max(schema_version) FROM schema_meta") == SCHEMA_VERSION

        assert conn.execute(
            "SELECT run_key, root_id, rel_run_dir, run_dir FROM runs ORDER BY run_key"
        ).fetchall() == [
            (
                run_key_for_run_dir(run_dir),
                parent_rid,
                "campaign-a/run-1",
                str(run_dir),
            )
        ]

        assert conn.execute(
            "SELECT run_key, file_name FROM run_files ORDER BY run_key, file_name"
        ).fetchall() == [(run_key_for_run_dir(run_dir), "run_config.json")]

        assert conn.execute(
            "SELECT run_key, theorem FROM theorem_wild ORDER BY run_key, theorem"
        ).fetchall() == [(run_key_for_run_dir(run_dir), "t1")]

        assert conn.execute(
            "SELECT root_id, root_path FROM log_roots ORDER BY root_path"
        ).fetchall() == [(parent_rid, str(parent_root))]
    finally:
        conn.close()


def test_reconcile_export_includes_basin(lake: Lake) -> None:
    _make_run(lake.logs_root, "run-basin", with_basin=True)
    lake.reconcile()

    out_dir = lake.tmp_path / "export"
    report = export_parquet(lake.conn, profile="full", out_dir=out_dir)

    dataset_names = {ds["name"] for ds in report["datasets"]}
    assert {"basin_runs", "basin_seed", "basin_structure_counts"} <= dataset_names

    reader = duckdb.connect()
    try:
        assert reader.execute(
            f"SELECT theorem, seeds_requested FROM '{out_dir / 'basin_runs.parquet'}'"
        ).fetchall() == [("t1", 3)]
        assert (
            _scalar(
                reader,
                f"SELECT count(*) FROM '{out_dir / 'basin_seed.parquet'}'",
            )
            == 3
        )
    finally:
        reader.close()
