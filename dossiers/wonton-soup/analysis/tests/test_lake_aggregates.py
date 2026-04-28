from __future__ import annotations

import json
from pathlib import Path

from analysis.lake.db import connect, ensure_schema, root_id_for_path
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.job import load_job_config, run_job


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def test_extract_run_aggregates_and_goal_matrix_and_postprocess_multi_provider_root(
    tmp_path: Path,
) -> None:
    logs_root = tmp_path / "logs"

    # Multi-provider root.
    root = logs_root / "corpus-1"
    # Provider subrun.
    run_dir = root / "provider=reprover"

    _write_json(
        root / "run_config.json",
        {
            "run_id": "corpus-1",
            "backend": "lean",
            "providers": ["reprover"],
            "mode": "dev",
            "corpus": "easy",
            "trace_mcts": True,
        },
    )
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

    summary = {
        "run_id": "corpus-1",
        "goal_sig_scheme": "ast",
        "theorems": [
            {
                "name": "t1",
                "wild_type": {
                    "solved": True,
                    "iterations": 2,
                    "metrics": {},
                },
                "interventions": [
                    {
                        "name": "block_intro",
                        "blocked": ["intro"],
                        "solved": True,
                        "status": "solved",
                        "metrics": {
                            "example": 1,
                        },
                        "ged_search_graph": {"value": 1.0, "normalized": 0.25},
                        "ged_search_graph_soft": {"value": 0.5, "normalized": 0.125},
                        "goal_novelty": {"novel_goal_count": 3, "dropped_goal_count": 1},
                        "solution_path_soft_distance": {"value": 0.2, "valid": True},
                    }
                ],
            }
        ],
        "aggregates": {
            "theorem_count": 1,
            "crashed_count": 0,
            "wild_type_solve_rate": 1.0,
            "intervention_count": 1,
            "intervention_solve_rate": 1.0,
            "ged_validity": {"ged_search_graph_soft": {"valid": 1, "invalid": 0}},
            "goal_type_tactic_matrix": {
                "A -> B": {
                    "intro": {"success": 2, "failure": 1, "blocked": 0},
                    "simp": {"success": 0, "failure": 3, "blocked": 1},
                }
            },
        },
    }
    _write_json_gz(run_dir / "summary.json.gz", summary)

    theorem_dir = run_dir / "t1"

    _write_json(
        theorem_dir / "block_intro_comparison.json",
        {
            "name": "block_intro",
            "blocked": ["intro"],
            "solved": True,
            "status": "solved",
            "wild_type_hash": "h_wild",
            "intervention_hash": "h_int",
            "hash_mismatch": True,
            "ged_search_graph": {
                "value": 4.0,
                "normalized": 0.1,
                "valid": True,
                "trace_source": "mcts",
                "trace_completeness": "full"
            },
            "axiom_delta": ["Nat.add_comm"],
            "axiom_removed": [],
            "trajectory_diff": {"iteration_diff": 2, "backtrack_diff": 0}
        },
    )

    # Variant metrics (per theorem).
    _write_json(
        theorem_dir / "wild_type_metrics.json",
        {
            "trajectory": {"total_iterations": 5, "backtrack_count": 1, "max_depth_reached": 3},
            "detour": {
                "total_attempts": 8,
                "success_count": 5,
                "failure_count": 3,
                "failure_ratio": 0.375,
            },
            "proof_term": {"node_count": 45, "depth": 12, "width": 3},
            "solution_path": ["intro h", "exact hp"],
            "tactic_fingerprint": "intro|exact",
            "root_goal_sigs": ["sig0"],
            "proof_term_pretty": "SHOULD_NOT_STORE",
        },
    )

    # postprocess_metrics.json is written at the multi-provider root.
    _write_json(
        root / "postprocess_metrics.json",
        {
            "schema_version": 1,
            "valid": True,
            "computed_at": "2026-02-07T00:00:00+00:00",
            "params": {"max_soft_ged_nodes": 60},
            "inputs": {"summary_sha256": "abc"},
            "metrics": {"computed": 3, "skipped": 0},
            "runs": [{"run_dir": str(run_dir), "provider": "reprover"}],
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

        row = conn.execute(
            "SELECT theorem_count, wild_type_solve_rate FROM run_aggregates",
        ).fetchone()
        assert row == (1, 1.0)

        rows = conn.execute(
            "SELECT goal_type, tactic_norm, tactic_family, success, failure, blocked, total "
            "FROM goal_type_tactic ORDER BY tactic_norm",
        ).fetchall()
        assert rows == [
            ("A -> B", "intro", "intro", 2, 1, 0, 3),
            ("A -> B", "simp", "simplify", 0, 3, 1, 4),
        ]

        inv_post = conn.execute(
            "SELECT goal_novelty_novel_goal_count, goal_novelty_dropped_goal_count, "
            "solution_path_soft_distance_value, solution_path_soft_distance_valid "
            "FROM theorem_intervention_postprocess",
        ).fetchone()
        assert inv_post == (3, 1, 0.2, True)

        mrow = conn.execute(
            "SELECT trajectory_total_iterations, detour_total_attempts, proof_term_node_count, "
            "solution_path_len, tactic_fingerprint FROM theorem_variant_metrics",
        ).fetchone()
        assert mrow == (5, 8, 45, 2, "intro|exact")

        crow = conn.execute(
            "SELECT wild_type_hash, intervention_hash, hash_mismatch, axiom_delta_count, "
            "trajectory_iteration_diff, ged_search_value, ged_search_trace_source "
            "FROM theorem_intervention_comparison",
        ).fetchone()
        assert crow == ("h_wild", "h_int", True, 1, 2, 4.0, "mcts")

        post = conn.execute(
            "SELECT valid, computed_at FROM run_postprocess",
        ).fetchone()
        assert post == (True, "2026-02-07T00:00:00+00:00")

        job_cfg = tmp_path / "postprocess_job.json"
        job_cfg.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "name": "postprocess_smoke",
                    "selection": {"provider": ["reprover"]},
                    "reference": None,
                    "datasets": [
                        {
                            "name": "run_postprocess",
                            "format": "jsonl",
                            "query": (
                                "SELECT p.valid, p.computed_at "
                                "FROM run_postprocess p "
                                "JOIN selected_runs s USING(run_key) "
                                "ORDER BY p.run_key"
                            ),
                        },
                        {
                            "name": "theorem_intervention_postprocess",
                            "format": "jsonl",
                            "query": (
                                "SELECT tp.goal_novelty_novel_goal_count, "
                                "tp.solution_path_soft_distance_value "
                                "FROM theorem_intervention_postprocess tp "
                                "JOIN selected_runs s USING(run_key) "
                                "ORDER BY tp.run_key, tp.theorem, tp.intervention"
                            ),
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        report = run_job(
            conn,
            job=load_job_config(job_cfg),
            logs_root=logs_root,
            out_dir=out_dir,
        )
        assert report.selected_runs == 1
        assert (out_dir / "run_postprocess.jsonl").exists()
        assert (out_dir / "theorem_intervention_postprocess.jsonl").exists()
    finally:
        conn.close()
