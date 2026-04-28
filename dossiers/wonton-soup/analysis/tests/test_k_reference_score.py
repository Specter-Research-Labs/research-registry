from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.lake.db import connect, ensure_schema, root_id_for_path, run_key_for_run_dir
from analysis.lake.extract import extract_facts
from analysis.lake.index import index_logs
from analysis.lake.reference import build_goal_outcomes_reference
from analysis.lake.score_k import inspect_score_k_run, score_k_for_run


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        json.dump(payload, f)


def test_score_k_against_reference(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    run_dir = logs_root / "corpus-1"
    theorem_dir = run_dir / "t1"
    theorem_dir.mkdir(parents=True, exist_ok=True)

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
            "goal_sig_scheme": "text",
            "theorems": [{"name": "t1", "wild_type": {"solved": True}, "interventions": []}],
            "aggregates": {},
        },
    )
    _write_json_gz(
        run_dir / "goal_cache.json.gz",
        {
            "mvar_to_sig": {"m1": "sigA", "m2": "sigB"},
            "entries": {
                "sigA": {
                    "occurrences": {"m1": {"outcomes": {"2": [True], "4": [False]}}},
                },
                "sigB": {
                    "occurrences": {"m2": {"outcomes": {"5": [True], "0": [False]}}},
                },
            },
        },
    )

    _write_json(
        theorem_dir / "wild_type_mcts_tree.json",
        {
            "root_mvar_id": "m1",
            "expansion_count": 2,
            "nodes": {
                "m1": {"goal_sig": "sigA", "children": {"intro h": ["m2"]}},
                "m2": {"goal_sig": "sigB", "children": {"exact hp": []}},
            },
        },
    )
    _write_json(
        theorem_dir / "wild_type_history.json",
        {
            "detour_metrics": {"total_attempts": 2},
            "solution_path": [
                {"mvar_id": "m1", "tactic": "intro h"},
                {"mvar_id": "m2", "tactic": "exact hp"},
            ],
            "iterations": [
                {
                    "iteration": 0,
                    "selected_path": ["m1"],
                    "attempts": [
                        {
                            "tactic": "intro h",
                            "outcome": "success",
                            "child_mvar_ids": ["m2"],
                        }
                    ],
                },
                {
                    "iteration": 1,
                    "selected_path": ["m1", "m2"],
                    "attempts": [
                        {
                            "tactic": "exact hp",
                            "outcome": "success",
                            "child_mvar_ids": [],
                        }
                    ],
                },
            ],
        },
    )
    (theorem_dir / "wild_type_mcts_trace.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "iteration",
                        "iteration": 0,
                        "node": {"mvar_id": "m1"},
                        "tactics": [
                            {"tactic": "intro h", "score": 1.0},
                            {"tactic": "cases h", "score": 0.9},
                        ],
                    }
                ),
                json.dumps(
                    {
                        "event": "iteration",
                        "iteration": 1,
                        "node": {"mvar_id": "m2"},
                        "tactics": [
                            {"tactic": "exact hp", "score": 1.0},
                            {"tactic": "simp", "score": 0.5},
                        ],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "lake.duckdb"
    conn = connect(db_path)
    try:
        ensure_schema(conn)
        index_logs(conn, logs_dirs=[logs_root])
        rid = root_id_for_path(logs_root)
        run_rows = conn.execute(
            "SELECT run_key, rel_run_dir FROM runs WHERE root_id = ? ORDER BY rel_run_dir",
            [rid],
        ).fetchall()
        extract_facts(
            conn,
            root_dir=logs_root,
            run_rows=[(rk, rel) for rk, rel in run_rows],
            with_goal_outcomes=True,
        )

        run_key = run_key_for_run_dir(run_dir.resolve())
        ref = build_goal_outcomes_reference(conn, run_keys=[run_key], alpha=1.0)
        rep = score_k_for_run(conn, run_key=run_key, run_dir=run_dir, ref_id=ref.ref_id)
        assert rep.scored == 1

        row = conn.execute(
            "SELECT K FROM k_reference_score WHERE run_key = ? AND theorem = ? AND variant = ?",
            [run_key, "t1", "wild_type"],
        ).fetchone()
        assert row is not None
        assert abs(float(row[0]) - 0.30103) < 1e-4
    finally:
        conn.close()


def test_inspect_score_k_run_requires_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    run_dir.mkdir(parents=True, exist_ok=True)

    missing = inspect_score_k_run(run_dir)
    assert missing.eligible is False
    assert missing.reason == "missing_summary"

    _write_json(run_dir / "summary.json", {"theorems": []})
    ready = inspect_score_k_run(run_dir)
    assert ready.eligible is True
    assert ready.reason is None
