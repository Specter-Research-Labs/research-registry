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


def _summary(run_id: str) -> dict:
    k = {
        "schema_version": 1,
        "valid": True,
        "tau_agent": 2,
        "primary": {"null_model": "blind_uniform_candidate", "tau_blind": 4.0, "K": 0.30103},
    }
    return {
        "run_id": run_id,
        "goal_sig_scheme": "ast",
        "theorems": [
            {
                "name": "t1",
                "wild_type": {
                    "solved": True,
                    "iterations": 2,
                    "proof_term_hash": "h1",
                    "metrics": {"detour": {"total_attempts": 2}},
                    "k_search_efficiency": k,
                },
                "interventions": [
                    {
                        "name": "block_intro",
                        "blocked": ["intro"],
                        "solved": True,
                        "status": "solved",
                        "is_control": False,
                        "baseline_solved": True,
                        "metrics": {"detour": {"total_attempts": 2}},
                        "ged_search_graph": {"value": 1.0, "normalized": 0.25},
                        "ged_search_graph_soft": {"value": 1.0, "normalized": 0.25},
                        "k_search_efficiency": k,
                    }
                ],
            }
        ],
        "aggregates": {},
    }


def test_lake_index_extract_export_smoke(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"

    # Single-provider run.
    run1 = logs_root / "corpus-1"
    _write_json(
        run1 / "run_config.json",
        {
            "run_id": "corpus-1",
            "backend": "lean",
            "provider": "reprover",
            "mode": "dev",
            "corpus": "easy",
            "trace_mcts": True,
        },
    )
    _write_json_gz(run1 / "summary.json.gz", _summary("corpus-1"))
    _write_json_gz(
        run1 / "goal_cache.json.gz",
        {
            "entries": {
                "sigA": {
                    "occurrences": {
                        "m1": {"outcomes": {"2": [True, False], "4": [False]}},
                    }
                }
            }
        },
    )

    # Multi-provider root with a provider subrun.
    root2 = logs_root / "corpus-2"
    _write_json(root2 / "run_config.json", {"run_id": "corpus-2", "multi_provider": True})
    run2 = root2 / "provider=deepseek"
    _write_json(
        run2 / "run_config.json",
        {"run_id": "corpus-2", "backend": "lean", "provider": "deepseek"},
    )
    _write_json_gz(run2 / "summary.json.gz", _summary("corpus-2"))
    _write_json_gz(
        run2 / "goal_cache.json.gz",
        {
            "entries": {
                "sigB": {
                    "occurrences": {
                        "m2": {"outcomes": {"5": [True], "0": [False, False]}},
                    }
                }
            }
        },
    )

    db_path = tmp_path / "lake.duckdb"
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        idx = index_logs(conn, logs_dirs=[logs_root])
        assert idx.runs_indexed == 2

        rid = root_id_for_path(logs_root)
        run_rows = conn.execute(
            "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ? ORDER BY rel_run_dir",
            [rid],
        ).fetchall()
        rep = extract_facts(
            conn,
            root_dir=logs_root,
            run_rows=[(rk, rel) for rk, rel in run_rows],
            with_goal_outcomes=True,
        )
        assert rep.runs_extracted == 2
        assert rep.wild_rows == 2
        assert rep.intervention_rows == 2
        assert rep.outcome_rows > 0

        # Ensure outcome tables are non-empty.
        assert conn.execute("SELECT count(*) FROM goal_outcome_global_family").fetchone()[0] >= 2
        assert conn.execute("SELECT count(*) FROM goal_outcome_sig_family").fetchone()[0] >= 2

        out_dir = tmp_path / "export"
        report = export_parquet(conn, profile="full", out_dir=out_dir)
        assert (out_dir / "manifest.json").exists()
        assert {ds["name"] for ds in report["datasets"]} == {
            "goal_type_tactic",
            "graph_edges",
            "graph_extract_errors",
            "graph_nodes",
            "k_reference_score",
            "mcts_trace_stats",
            "run_aggregates",
            "run_postprocess",
            "runs",
            "theorem_intervention_comparison",
            "theorem_intervention_postprocess",
            "theorem_artifacts",
            "theorem_variant_metrics",
            "theorem_intervention",
            "theorem_wild",
            "basin_runs",
            "basin_seed",
            "basin_structure_counts",
        }
    finally:
        conn.close()
