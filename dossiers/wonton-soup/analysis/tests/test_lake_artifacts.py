from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.lake.db import connect, ensure_schema
from analysis.lake.reconcile import reconcile


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _summary(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "goal_sig_scheme": "ast",
        "theorems": [
            {
                "name": "t1",
                "wild_type": {"solved": True, "iterations": 2, "proof_term_hash": "h1"},
                "interventions": [
                    {
                        "name": "block_intro",
                        "solved": True,
                        "status": "solved",
                        "is_control": False,
                        "baseline_solved": True,
                    }
                ],
            }
        ],
        "aggregates": {},
    }


def _make_run(logs_root: Path, run_id: str) -> Path:
    run_dir = logs_root / run_id
    _write_json(
        run_dir / "run_config.json",
        {"run_id": run_id, "backend": "lean", "provider": "reprover", "mode": "dev"},
    )
    _write_json_gz(run_dir / "summary.json.gz", _summary(run_id))
    _write_json_gz(run_dir / "goal_cache.json.gz", {"entries": {}})
    return run_dir


def test_reconcile_extracts_graph_artifacts_and_trace_stats(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    run_dir = _make_run(logs_root, "run-1")

    _write_json(
        run_dir / "t1" / "wild_type_graph.json",
        {
            "graph_kind": "search_graph",
            "nodes": [
                {"id": "n0", "goal_sig": "sig0", "depth": 0, "in_proof": True},
                {"id": "n1", "goal_sig": "sig1", "depth": 1},
            ],
            "edges": [
                {"source": "n0", "target": "n1", "tactic": "intro h", "in_proof": True},
            ],
        },
    )
    _write_json(
        run_dir / "t1" / "block_intro_search_trace_graph.json",
        {
            "trace_source": "tstp",
            "trace_completeness": "proxy",
            "nodes": [
                {"id": "c1", "goal_sig": "g1"},
                {"id": "c2", "goal_sig": "g2"},
            ],
            "edges": [
                {
                    "src": "c1",
                    "dst": "c2",
                    "action_family": "Resolution",
                    "action_norm": "res",
                }
            ],
        },
    )
    _write_jsonl(
        run_dir / "t1" / "wild_type_mcts_trace.jsonl",
        [
            {
                "event": "iteration",
                "iteration": 0,
                "node": {"mvar_id": "n0"},
                "tactics": [{"tactic": "intro"}, {"tactic": "apply h"}],
            },
            {
                "event": "iteration",
                "iteration": 1,
                "node": {"mvar_id": "n1"},
                "tactics": [{"tactic": "exact h"}],
            },
            {"event": "tactic_attempt", "mvar_id": "n1", "tactic": "exact h"},
        ],
    )

    conn = connect(tmp_path / "lake.duckdb")
    try:
        ensure_schema(conn)
        rep = reconcile(conn, logs_dirs=[logs_root])
        assert rep.artifacts.artifacts_indexed >= 3
        assert rep.artifacts.graph_files == 2
        assert rep.artifacts.graph_nodes == 4
        assert rep.artifacts.graph_edges == 2
        assert rep.artifacts.trace_files == 1
        assert rep.artifacts.trace_rows == 1

        kinds = conn.execute(
            """
            SELECT artifact_kind, variant, parse_status
            FROM theorem_artifacts
            WHERE run_key = (SELECT run_key FROM runs LIMIT 1)
            ORDER BY artifact_kind, variant
            """
        ).fetchall()
        assert ("graph", "wild_type", "parsed") in kinds
        assert ("search_trace_graph", "block_intro", "parsed") in kinds
        assert ("mcts_trace", "wild_type", "trace_summarized") in kinds

        trace = conn.execute(
            """
            SELECT
              line_count,
              bad_json_lines,
              event_count,
              iteration_event_count,
              tactic_attempt_event_count,
              max_iteration,
              unique_mvar_count,
              candidate_total,
              candidate_max
            FROM mcts_trace_stats
            """
        ).fetchone()
        assert trace == (3, 0, 3, 2, 1, 1, 2, 3, 2)

        # Second pass should reuse source-hash watermark and skip heavy parse.
        rep2 = reconcile(conn, logs_dirs=[logs_root])
        assert rep2.artifacts.graph_nodes == 0
        statuses = conn.execute(
            """
            SELECT artifact_kind, parse_status
            FROM theorem_artifacts
            WHERE artifact_kind IN ('graph', 'search_trace_graph', 'mcts_trace')
            ORDER BY artifact_kind
            """
        ).fetchall()
        assert ("graph", "skipped_unchanged") in statuses
        assert ("search_trace_graph", "skipped_unchanged") in statuses
        assert ("mcts_trace", "trace_skipped_unchanged") in statuses

        # Mutating one graph should trigger a re-parse for that artifact only.
        _write_json(
            run_dir / "t1" / "wild_type_graph.json",
            {
                "graph_kind": "search_graph",
                "nodes": [
                    {"id": "n0", "goal_sig": "sig0", "depth": 0},
                    {"id": "n1", "goal_sig": "sig1", "depth": 1},
                    {"id": "n2", "goal_sig": "sig2", "depth": 2},
                ],
                "edges": [
                    {"source": "n0", "target": "n1", "tactic": "intro h"},
                    {"source": "n1", "target": "n2", "tactic": "exact h"},
                ],
            },
        )
        rep3 = reconcile(conn, logs_dirs=[logs_root])
        assert rep3.artifacts.graph_nodes == 3
        updated_nodes = conn.execute(
            "SELECT count(*) FROM graph_nodes WHERE rel_path = 't1/wild_type_graph.json'"
        ).fetchone()[0]
        assert updated_nodes == 3
    finally:
        conn.close()


def test_reconcile_records_graph_parse_errors_and_continues(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    run_dir = _make_run(logs_root, "run-bad-graph")
    _write_json(
        run_dir / "t1" / "wild_type_graph.json",
        {"nodes": "not-a-list", "edges": []},
    )

    conn = connect(tmp_path / "lake.duckdb")
    try:
        ensure_schema(conn)
        rep = reconcile(conn, logs_dirs=[logs_root])
        assert rep.extract.runs_extracted == 1
        assert rep.artifacts.graph_files == 1
        assert rep.artifacts.errors

        status = conn.execute(
            """
            SELECT parse_status
            FROM theorem_artifacts
            WHERE rel_path = 't1/wild_type_graph.json'
            """
        ).fetchone()
        assert status == ("parse_error",)

        err_count = conn.execute(
            "SELECT count(*) FROM graph_extract_errors WHERE stage = 'parse_graph'"
        ).fetchone()[0]
        assert err_count == 1
    finally:
        conn.close()
