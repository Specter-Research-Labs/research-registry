from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.inspect_proof_ir import inspect_theorem_ir, inspect_theorem_ir_pair
from prover.proof import GRAPH_FAMILY_SEARCH_TRACE


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _graph_payload(*, theorem: str, node_count: int) -> dict:
    nodes = []
    edges = []
    for idx in range(node_count):
        node_id = f"n{idx}"
        nodes.append(
            {
                "id": node_id,
                "goal_sig": f"{theorem}-sig-{idx}",
                "goal_type": f"{theorem}.goal.{idx}",
                "depth": idx,
            }
        )
        if idx > 0:
            edges.append(
                {
                    "source": f"n{idx-1}",
                    "target": node_id,
                    "tactic": "intro",
                    "tactic_norm": "intro",
                    "edge_role": "fam:intro",
                    "action_kind": "tactic_step",
                    "order": idx,
                    "branch_arity": 1,
                    "continuation_kind": "chain",
                    "goal_coupling": "none",
                    "effect_flags": ["opens_binder"],
                }
            )
    return {
        "graph_family": GRAPH_FAMILY_SEARCH_TRACE,
        "graph_backend": "lean",
        "graph_provenance": "mcts",
        "nodes": nodes,
        "edges": edges,
    }


def _build_run(run_dir: Path, theorem_specs: list[tuple[str, int]]) -> None:
    _write_json(
        run_dir / "run_config.json",
        {"backend": "lean", "mode": "research", "run_id": run_dir.name},
    )
    theorems = []
    for theorem, node_count in theorem_specs:
        theorems.append({"name": theorem, "wild_type": {"solved": True}, "interventions": []})
        _write_json(
            run_dir / theorem / "wild_type_graph.json",
            _graph_payload(theorem=theorem, node_count=node_count),
        )
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": theorems, "aggregates": {}})


def test_inspect_theorem_ir_returns_action_trace_and_profiles(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run(run_dir, [("t1", 2)])

    inspected = inspect_theorem_ir(run_dir, theorem="t1")

    assert inspected.payload["graph"]["family"] == GRAPH_FAMILY_SEARCH_TRACE
    assert inspected.payload["graph"]["node_count"] == 2
    assert inspected.payload["proof_ir"]["continuation_profile"]["chain"] == 1.0
    assert len(inspected.payload["actions"]) == 1
    assert inspected.payload["actions"][0]["operator_kind"] == "bind"
    assert inspected.payload["actions"][0]["effect_flags"] == ["opens_binder"]


def test_inspect_theorem_ir_pair_reports_distance_breakdown(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(run_a, [("left", 2)])
    _build_run(run_b, [("right", 3)])

    report = inspect_theorem_ir_pair(
        run_a,
        theorem_a="left",
        run_b_dir=run_b,
        theorem_b="right",
    )

    assert report["left"]["theorem"] == "left"
    assert report["right"]["theorem"] == "right"
    assert report["distance"]["graph"] >= 0.0
    assert report["distance"]["lexical"] >= 0.0
