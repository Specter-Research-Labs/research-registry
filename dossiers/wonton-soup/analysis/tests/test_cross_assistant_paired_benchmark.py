from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.cross_assistant_paired_benchmark import evaluate_paired_benchmark


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _graph_payload(*, theorem: str, node_count: int, style: str = "search") -> dict:
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
            if style == "term":
                tactic_norm = "arg" if idx % 2 else "fn"
                goal_type = "app" if idx % 2 else "const"
                nodes[idx]["goal_type"] = goal_type
                nodes[idx - 1]["goal_type"] = "app"
            else:
                tactic_norm = "intro"
            edges.append(
                {
                    "source": f"n{idx-1}",
                    "target": node_id,
                    "tactic": tactic_norm,
                    "tactic_norm": tactic_norm,
                }
            )
    return {"nodes": nodes, "edges": edges}


def _build_run(
    run_dir: Path,
    theorem_specs: list[tuple[str, int]],
    *,
    style: str = "search",
    backend: str | None = None,
) -> None:
    _write_json(
        run_dir / "run_config.json",
        {
            "mode": "external",
            "corpus": "coq-stdlib",
            "run_id": run_dir.name,
            "backend": backend,
        },
    )
    theorems = []
    for theorem, node_count in theorem_specs:
        theorems.append({"name": theorem, "wild_type": {"solved": True}, "interventions": []})
        _write_json(
            run_dir / theorem / "wild_type_graph.json",
            _graph_payload(theorem=theorem, node_count=node_count, style=style),
        )
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": theorems, "aggregates": {}})


def _write_proof_term(run_dir: Path, theorem: str, *, variant: str = "wild_type") -> None:
    theorem_dir = run_dir / theorem
    theorem_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "rootId": "n0",
        "nodes": [
            [
                "n0",
                {
                    "kind": "app",
                    "fn": "n1",
                    "arg": "n2",
                },
            ],
            [
                "n1",
                {
                    "kind": "const",
                    "name": theorem,
                },
            ],
            [
                "n2",
                {
                    "kind": "const",
                    "name": "arg",
                },
            ],
        ],
    }
    if variant == "wild_type":
        path = theorem_dir / "wild_type_proof_term.json.gz"
    else:
        path = theorem_dir / f"{variant}_proof_term.json.gz"
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _add_intervention(
    run_dir: Path,
    theorem: str,
    *,
    name: str,
    node_count: int,
    solved: bool = True,
) -> None:
    summary_path = run_dir / "summary.json.gz"
    with gzip.open(summary_path, "rt") as handle:
        summary = json.load(handle)
    theorems = summary.get("theorems")
    assert isinstance(theorems, list)
    theorem_entry = next(
        (entry for entry in theorems if isinstance(entry, dict) and entry.get("name") == theorem),
        None,
    )
    assert isinstance(theorem_entry, dict)
    interventions = theorem_entry.get("interventions")
    if not isinstance(interventions, list):
        interventions = []
        theorem_entry["interventions"] = interventions
    interventions.append(
        {
            "name": name,
            "solved": solved,
            "metrics": {
                "proof_term": {"const_names": [name]},
            },
        }
    )
    _write_json(
        run_dir / theorem / f"{name}_graph.json",
        _graph_payload(theorem=f"{theorem}_{name}", node_count=node_count, style="search"),
    )
    _write_json_gz(summary_path, summary)


def _write_pairs(path: Path, pairs: list[dict[str, str]]) -> None:
    payload = {
        "schema_version": 1,
        "benchmark_id": "test-bench",
        "gate": {"min_recall_at_1": 1.0, "min_recall_at_10": 1.0, "min_mrr": 1.0},
        "pairs": pairs,
    }
    _write_json(path, payload)


def test_paired_benchmark_perfect_alignment(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3), ("l2", 7)])
    _build_run(run_coq, [("c1", 3), ("c2", 7)])
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
            {"pair_id": "p2", "lean_item_id": "l2", "coq_theorem": "c2"},
        ],
    )

    report = evaluate_paired_benchmark(run_lean, run_coq, pairs_path)
    summary = report["summary"]
    assert summary["pairs_total"] == 2
    assert summary["pairs_evaluated"] == 2
    assert summary["pairs_missing"] == 0
    assert summary["recall_at_1"] == 1.0
    assert summary["mrr"] == 1.0
    assert report["gate"]["passed"] is True


def test_paired_benchmark_marks_missing_pairs(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3)])
    _build_run(run_coq, [("c1", 3)])
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
            {"pair_id": "p2", "lean_item_id": "missing_lean", "coq_theorem": "c1"},
            {"pair_id": "p3", "lean_item_id": "l1", "coq_theorem": "missing_coq"},
        ],
    )

    report = evaluate_paired_benchmark(run_lean, run_coq, pairs_path)
    summary = report["summary"]
    assert summary["pairs_total"] == 3
    assert summary["pairs_evaluated"] == 1
    assert summary["pairs_missing"] == 2
    statuses = {row["pair_id"]: row["status"] for row in report["pairs"]}
    assert statuses["p1"] == "ok"
    assert statuses["p2"] == "missing_theorem"
    assert statuses["p3"] == "missing_theorem"


def test_paired_benchmark_reports_by_kind_and_bucket_gate(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3), ("l2", 7)], style="search", backend="lean")
    _build_run(run_coq, [("c1", 3), ("c2", 7)], style="term", backend="coq")
    pairs_path = tmp_path / "pairs.json"
    _write_json(
        pairs_path,
        {
            "schema_version": 1,
            "benchmark_id": "test-bench",
            "gate": {
                "min_recall_at_1": 0.0,
                "min_recall_at_10": 0.0,
                "min_mrr": 0.0,
                "by_kind": {
                    "cross_kind": {"min_pairs": 1, "min_recall_at_1": 0.0, "min_mrr": 0.0},
                    "same_kind": {"min_pairs": 1},
                },
            },
            "pairs": [
                {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
                {"pair_id": "p2", "lean_item_id": "l2", "coq_theorem": "c2"},
            ],
        },
    )

    report = evaluate_paired_benchmark(run_lean, run_coq, pairs_path)
    by_kind = report["summary"]["by_kind"]
    assert by_kind["cross_kind"]["pairs_evaluated"] == 2
    assert by_kind["same_kind"]["pairs_evaluated"] == 0
    assert report["gate"]["passed"] is False
    failures = report["gate"]["failures"]
    assert any("cohorts.same_kind.pairs_evaluated" in failure for failure in failures)


def test_paired_benchmark_name_obfuscation_mode_is_reported(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("alpha_comm", 3)], style="search", backend="lean")
    _build_run(run_coq, [("alpha_comm", 3)], style="search", backend="lean")
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "alpha_comm", "coq_theorem": "alpha_comm"},
        ],
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        name_obfuscation_mode="names",
        name_obfuscation_salt="test-salt",
    )
    assert report["name_obfuscation"]["mode"] == "names"
    assert report["name_obfuscation"]["salt"] == "test-salt"


def test_paired_benchmark_lexical_ablation_mode_is_reported(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("alpha_comm", 3)], style="search", backend="lean")
    _build_run(run_coq, [("alpha_comm", 3)], style="search", backend="lean")
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "alpha_comm", "coq_theorem": "alpha_comm"},
        ],
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        lexical_ablation_mode="graph_only",
    )
    assert report["lexical_ablation"]["mode"] == "graph_only"


def test_paired_benchmark_supports_same_kind_with_proof_term_source(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3), ("l2", 7)], style="search", backend="lean")
    _build_run(run_coq, [("c1", 3), ("c2", 7)], style="search", backend="coq")
    _write_proof_term(run_lean, "l1")
    _write_proof_term(run_lean, "l2")
    _write_proof_term(run_coq, "c1")
    _write_proof_term(run_coq, "c2")
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
            {"pair_id": "p2", "lean_item_id": "l2", "coq_theorem": "c2"},
        ],
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        graph_source_lean="proof_term_graph",
        graph_source_coq="proof_term_graph",
    )
    assert report["graph_sources"]["run_lean"] == "proof_term_graph"
    assert report["graph_sources"]["run_coq"] == "proof_term_graph"
    by_kind = report["summary"]["by_kind"]
    assert by_kind["same_kind"]["pairs_evaluated"] == 2
    assert by_kind["cross_kind"]["pairs_evaluated"] == 0


def test_paired_benchmark_gate_claim_same_kind_ignores_cross_kind_gate(
    tmp_path: Path,
) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3)], style="search", backend="lean")
    _build_run(run_coq, [("c1", 3)], style="search", backend="coq")
    _write_proof_term(run_lean, "l1")
    _write_proof_term(run_coq, "c1")
    pairs_path = tmp_path / "pairs.json"
    _write_json(
        pairs_path,
        {
            "schema_version": 1,
            "benchmark_id": "test-bench",
            "gate": {
                "min_recall_at_1": 0.0,
                "min_recall_at_10": 0.0,
                "min_mrr": 0.0,
                "by_kind": {
                    "cross_kind": {"min_pairs": 1},
                    "same_kind": {"min_pairs": 1, "min_mrr": 0.0},
                },
            },
            "pairs": [
                {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
            ],
        },
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        graph_source_lean="proof_term_graph",
        graph_source_coq="proof_term_graph",
        gate_claim="same_kind",
    )
    assert report["gate"]["claim"] == "same_kind"
    assert report["gate"]["passed"] is True


def test_paired_benchmark_gate_axis_coverage_only(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 3)])
    _build_run(run_coq, [("c1", 3)])
    pairs_path = tmp_path / "pairs.json"
    _write_json(
        pairs_path,
        {
            "schema_version": 1,
            "benchmark_id": "test-bench",
            "gate": {
                "min_pairs_evaluated": 2,
                "min_recall_at_1": 1.0,
            },
            "pairs": [
                {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
                {"pair_id": "p2", "lean_item_id": "missing", "coq_theorem": "c1"},
            ],
        },
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        gate_axis="coverage",
    )
    assert report["gate"]["axis"] == "coverage"
    assert report["gate"]["passed"] is False
    assert report["gate"]["coverage_failures"]
    assert not report["gate"]["quality_failures"]


def test_paired_benchmark_best_of_uses_variant_pool(tmp_path: Path) -> None:
    run_lean = tmp_path / "lean"
    run_coq = tmp_path / "coq"
    _build_run(run_lean, [("l1", 9), ("l2", 4)], style="search", backend="lean")
    _build_run(run_coq, [("c1", 3), ("c2", 9)], style="search", backend="coq")
    _add_intervention(run_lean, "l1", name="bridge", node_count=3, solved=True)
    pairs_path = tmp_path / "pairs.json"
    _write_pairs(
        pairs_path,
        [
            {"pair_id": "p1", "lean_item_id": "l1", "coq_theorem": "c1"},
        ],
    )

    report = evaluate_paired_benchmark(
        run_lean,
        run_coq,
        pairs_path,
        proof_aggregation="best_of",
    )
    assert report["proof_aggregation"] == "best_of"
    pair_row = report["pairs"][0]
    assert pair_row["status"] == "ok"
    assert pair_row["rank"] == 1
    assert pair_row["representative_pair"]["variant_lean"] == "bridge"
