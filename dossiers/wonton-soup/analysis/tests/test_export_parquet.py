from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.lake.db import connect, ensure_schema, root_id_for_path
from analysis.lake.export_parquet import export_parquet
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _setup_lake(tmp_path: Path) -> Path:
    logs_root = tmp_path / "logs"
    run_dir = logs_root / "corpus-1"
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": "corpus-1",
            "backend": "lean",
            "provider": "reprover",
            "mode": "dev",
            "corpus": "easy",
            "trace_mcts": True,
        },
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "run_id": "corpus-1",
            "goal_sig_scheme": "ast",
            "theorems": [
                {
                    "name": "t1",
                    "wild_type": {"solved": True, "iterations": 2, "metrics": {}},
                    "interventions": [
                        {
                            "name": "block_intro",
                            "blocked": ["intro"],
                            "solved": True,
                            "status": "solved",
                            "metrics": {},
                            "ged_search_graph": {"value": 1.0, "normalized": 0.25},
                        }
                    ],
                }
            ],
            "aggregates": {},
        },
    )

    db_path = tmp_path / "lake.duckdb"
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        index_logs(conn, logs_dirs=[logs_root])
        rid = root_id_for_path(logs_root)
        run_rows = conn.execute(
            "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ?",
            [rid],
        ).fetchall()
        extract_facts(
            conn,
            root_dir=logs_root,
            run_rows=[(rk, rel) for rk, rel in run_rows],
            with_goal_outcomes=False,
        )
    finally:
        conn.close()
    return db_path


def test_export_parquet_profiles(tmp_path: Path) -> None:
    cases = [
        {
            "profile": "full",
            "table_count": 20,
            "files": ["runs.parquet", "theorem_wild.parquet", "theorem_intervention.parquet"],
            "tables": {"runs", "theorem_wild"},
            "absent_tables": set(),
            "selected_runs": 1,
        },
        {
            "profile": "dashboard",
            "table_count": 13,
            "files": ["runs.parquet"],
            "tables": {"runs", "run_aggregates", "mcts_tree_nodes", "mcts_tree_edges"},
            "absent_tables": {"basin_runs", "basin_seed"},
            "selected_runs": None,
        },
    ]

    for case in cases:
        profile_root = tmp_path / str(case["profile"])
        db_path = _setup_lake(profile_root)
        out_dir = profile_root / "out"
        conn = connect(db_path)
        try:
            ensure_schema(conn)
            report = export_parquet(conn, profile=str(case["profile"]), out_dir=out_dir)
        finally:
            conn.close()

        assert report["profile"] == case["profile"]
        if case["selected_runs"] is not None:
            assert report["selected_runs"] == case["selected_runs"]
        assert (out_dir / "dashboard_manifest.json").exists()
        for filename in case["files"]:
            assert (out_dir / str(filename)).exists()

        manifest = _read_json(out_dir / "dashboard_manifest.json")
        assert manifest["schema_version"] == 1
        assert manifest["format"] == "parquet"
        assert manifest["profile"] == case["profile"]
        if case["selected_runs"] is not None:
            assert manifest["selected_runs"] == case["selected_runs"]
        assert "compiled_at" in manifest
        assert len(manifest["tables"]) == case["table_count"]
        table_names = {t["name"] for t in manifest["tables"]}
        assert case["tables"] <= table_names
        assert table_names.isdisjoint(case["absent_tables"])


def test_export_parquet_dashboard_accepts_graph_family_schema(tmp_path: Path) -> None:
    db_path = _setup_lake(tmp_path)
    out_dir = tmp_path / "out-dashboard-family"

    conn = connect(db_path)
    try:
        ensure_schema(conn)
        conn.execute("ALTER TABLE graph_nodes RENAME graph_kind TO graph_family")
        conn.execute("ALTER TABLE graph_edges RENAME graph_kind TO graph_family")
        report = export_parquet(conn, profile="dashboard", out_dir=out_dir)
    finally:
        conn.close()

    assert report["profile"] == "dashboard"
    assert (out_dir / "graph_nodes.parquet").exists()
    assert (out_dir / "graph_edges.parquet").exists()
