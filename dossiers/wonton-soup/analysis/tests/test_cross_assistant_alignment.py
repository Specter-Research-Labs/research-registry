from __future__ import annotations

import gzip
import json
from pathlib import Path

from analysis.cross_assistant_alignment import (
    LexicalAblationConfig,
    NameObfuscationConfig,
    align_runs,
    load_run_signatures,
    pair_distance,
)
from prover.proof import GRAPH_FAMILY_SEARCH_TRACE


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_json_gz(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _graph_payload(
    *,
    theorem: str,
    node_count: int,
    depth_offset: int = 0,
    edge_attrs: dict | None = None,
) -> dict:
    nodes = []
    edges = []
    for idx in range(node_count):
        node_id = f"n{idx}"
        nodes.append(
            {
                "id": node_id,
                "goal_sig": f"{theorem}-sig-{idx}",
                "goal_type": f"{theorem}.goal.{idx}",
                "depth": idx + depth_offset,
            }
        )
        if idx > 0:
            payload = {
                "source": f"n{idx-1}",
                "target": node_id,
                "tactic": "intro",
                "tactic_norm": "intro",
            }
            if edge_attrs:
                payload.update(edge_attrs)
            edges.append(payload)
    return {
        "graph_family": GRAPH_FAMILY_SEARCH_TRACE,
        "graph_backend": "unknown",
        "graph_provenance": "imported",
        "nodes": nodes,
        "edges": edges,
    }


def _build_run(run_dir: Path, theorem_specs: list[tuple[str, int, bool]]) -> None:
    _write_json(
        run_dir / "run_config.json",
        {"mode": "external", "corpus": "coq-stdlib", "run_id": run_dir.name},
    )
    theorems = []
    for theorem, node_count, solved in theorem_specs:
        theorems.append({"name": theorem, "wild_type": {"solved": solved}, "interventions": []})
        _write_json(
            run_dir / theorem / "wild_type_graph.json",
            _graph_payload(theorem=theorem, node_count=node_count),
        )
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": theorems, "aggregates": {}})


def _add_intervention(
    run_dir: Path,
    theorem: str,
    *,
    name: str,
    node_count: int,
    solved: bool = True,
    with_proof_term: bool = False,
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
                "proof_term": {
                    "const_names": [name],
                }
            },
        }
    )
    _write_json(
        run_dir / theorem / f"{name}_graph.json",
        _graph_payload(theorem=f"{theorem}_{name}", node_count=node_count),
    )
    if with_proof_term:
        _write_proof_term(run_dir, theorem, variant=name)
    _write_json_gz(summary_path, summary)


def _build_run_with_statement(
    run_dir: Path,
    theorem: str,
    *,
    node_count: int,
    statement_text: str,
) -> None:
    _write_json(
        run_dir / "run_config.json",
        {"mode": "external", "corpus": "coq-stdlib", "run_id": run_dir.name},
    )
    _write_json(
        run_dir / theorem / "wild_type_graph.json",
        _graph_payload(theorem=theorem, node_count=node_count),
    )
    _write_json_gz(
        run_dir / "summary.json.gz",
        {
            "theorems": [
                {
                    "name": theorem,
                    "wild_type": {
                        "solved": True,
                        "metrics": {
                            "statement_text": statement_text,
                            "statement_source": "serapi_check",
                        },
                    },
                    "interventions": [],
                }
            ],
            "aggregates": {},
        },
    )


def _write_proof_term(run_dir: Path, theorem: str, *, variant: str = "wild_type") -> None:
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
    theorem_dir = run_dir / theorem
    theorem_dir.mkdir(parents=True, exist_ok=True)
    if variant == "wild_type":
        path = theorem_dir / "wild_type_proof_term.json.gz"
    else:
        path = theorem_dir / f"{variant}_proof_term.json.gz"
    with gzip.open(path, "wt") as handle:
        json.dump(payload, handle)


def _build_lean_run_with_items(
    run_dir: Path,
    theorem_specs: list[tuple[str, int, bool]],
    items: list[dict[str, object]],
) -> None:
    items_path = run_dir / "items.jsonl"
    items_path.parent.mkdir(parents=True, exist_ok=True)
    with items_path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item) + "\n")

    _write_json(
        run_dir / "run_config.json",
        {
            "backend": "lean",
            "mode": "research",
            "corpus_meta": {"items_path": str(items_path)},
            "run_id": run_dir.name,
        },
    )
    theorems = []
    for theorem, node_count, solved in theorem_specs:
        theorems.append({"name": theorem, "wild_type": {"solved": solved}, "interventions": []})
        _write_json(
            run_dir / theorem / "wild_type_graph.json",
            _graph_payload(theorem=theorem, node_count=node_count),
        )
    _write_json_gz(run_dir / "summary.json.gz", {"theorems": theorems, "aggregates": {}})


def test_load_run_signatures_filters_solved_when_requested(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run(
        run_dir,
        [
            ("t1", 3, True),
            ("t2", 7, False),
        ],
    )

    all_sigs = load_run_signatures(run_dir, solved_only=False)
    solved_sigs = load_run_signatures(run_dir, solved_only=True)
    assert [s.theorem for s in all_sigs] == ["t1", "t2"]
    assert [s.theorem for s in solved_sigs] == ["t1"]


def test_align_runs_one_to_one_pairs_by_shape_and_size(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(
        run_a,
        [
            ("a_small", 3, True),
            ("a_large", 9, True),
        ],
    )
    _build_run(
        run_b,
        [
            ("b_large", 9, True),
            ("b_small", 3, True),
        ],
    )

    report = align_runs(run_a, run_b, solved_only=True, top_k=2, one_to_one=True)
    matches = {(m["theorem_a"], m["theorem_b"]) for m in report["matches"]}
    assert matches == {("a_small", "b_small"), ("a_large", "b_large")}
    assert report["summary"]["shape_hash_equal_rate"] == 1.0


def test_align_runs_one_to_one_uses_top_k_candidates(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(
        run_a,
        [
            ("a1", 3, True),
            ("a2", 4, True),
        ],
    )
    _build_run(
        run_b,
        [
            ("b1", 3, True),
            ("b2", 5, True),
        ],
    )

    report = align_runs(run_a, run_b, solved_only=True, top_k=2, one_to_one=True)
    assert len(report["matches"]) == 2
    matched_b = {m["theorem_b"] for m in report["matches"]}
    assert matched_b == {"b1", "b2"}


def test_align_runs_uses_lexical_signal_from_encoded_names_and_statements(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(
        run_a,
        [
            ("and_x5fcomm", 4, True),
            ("or_x5fcomm", 4, True),
        ],
    )
    _build_lean_run_with_items(
        run_b,
        [
            ("t_and", 4, True),
            ("t_or", 4, True),
        ],
        [
            {
                "item_id": "t_and",
                "display_name": "and_comm",
                "payload": {
                    "statement": "theorem {name} (P Q : Prop) : P ∧ Q ↔ Q ∧ P := by sorry"
                },
            },
            {
                "item_id": "t_or",
                "display_name": "or_comm",
                "payload": {
                    "statement": "theorem {name} (P Q : Prop) : P ∨ Q ↔ Q ∨ P := by sorry"
                },
            },
        ],
    )

    report = align_runs(run_a, run_b, solved_only=True, top_k=2, one_to_one=True)
    matches = {(m["theorem_a"], m["theorem_b"]) for m in report["matches"]}
    assert matches == {("and_x5fcomm", "t_and"), ("or_x5fcomm", "t_or")}
    assert report["summary"]["run_b_statement_coverage"] == 1.0


def test_load_run_signatures_uses_external_statement_text_from_summary_metrics(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "coq-run"
    _build_run_with_statement(
        run_dir,
        "and_comm",
        node_count=4,
        statement_text="forall P Q : Prop, P /\\ Q <-> Q /\\ P",
    )
    sigs = load_run_signatures(run_dir, solved_only=False)
    assert len(sigs) == 1
    sig = sigs[0]
    assert sig.has_statement_text is True
    assert "forall" in sig.connective_profile


def test_load_run_signatures_supports_name_obfuscation(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run(
        run_dir,
        [
            ("and_comm", 4, True),
        ],
    )
    sigs_plain = load_run_signatures(run_dir, solved_only=False)
    sigs_obf = load_run_signatures(
        run_dir,
        solved_only=False,
        name_obfuscation=NameObfuscationConfig(mode="names", salt="test-salt"),
    )
    assert len(sigs_plain) == 1
    assert len(sigs_obf) == 1
    assert sigs_plain[0].theorem == sigs_obf[0].theorem
    assert sigs_plain[0].lexical_tokens != sigs_obf[0].lexical_tokens


def test_load_run_signatures_supports_lexical_ablation_modes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run_with_statement(
        run_dir,
        "logic_bridge",
        node_count=3,
        statement_text="forall x, P x -> Q x /\\ R x",
    )

    sig_plain = load_run_signatures(run_dir, solved_only=False)[0]
    sig_drop_tokens = load_run_signatures(
        run_dir,
        solved_only=False,
        lexical_ablation=LexicalAblationConfig(mode="drop_tokens"),
    )[0]
    sig_graph_only = load_run_signatures(
        run_dir,
        solved_only=False,
        lexical_ablation=LexicalAblationConfig(mode="graph_only"),
    )[0]

    assert sig_plain.lexical_tokens
    assert sig_plain.connective_profile
    assert not sig_drop_tokens.lexical_tokens
    assert sig_drop_tokens.connective_profile == sig_plain.connective_profile
    assert not sig_graph_only.lexical_tokens
    assert sig_graph_only.connective_profile == {}


def test_load_run_signatures_supports_proof_term_graph_source(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run(
        run_dir,
        [
            ("t1", 3, True),
        ],
    )
    _write_proof_term(run_dir, "t1")
    sigs = load_run_signatures(run_dir, solved_only=False, graph_source="proof_term_graph")
    assert len(sigs) == 1
    assert sigs[0].graph_kind == "proof_term_dag"


def test_pair_distance_uses_action_profiles_when_shape_matches(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_json(
        run_a / "run_config.json",
        {"mode": "external", "corpus": "coq-stdlib", "run_id": run_a.name},
    )
    _write_json(
        run_b / "run_config.json",
        {"mode": "external", "corpus": "coq-stdlib", "run_id": run_b.name},
    )
    theorem = "t1"
    payload_refine = _graph_payload(
        theorem=theorem,
        node_count=2,
        edge_attrs={
            "edge_role": "fam:intro",
            "action_kind": "tactic_step",
            "branch_arity": 1,
            "continuation_kind": "refine",
            "goal_coupling": "none",
            "effect_flags": ["opens_binder", "refines_term"],
        },
    )
    payload_chain = _graph_payload(
        theorem=theorem,
        node_count=2,
        edge_attrs={
            "edge_role": "fam:intro",
            "action_kind": "tactic_step",
            "branch_arity": 1,
            "continuation_kind": "chain",
            "goal_coupling": "none",
            "effect_flags": ["opens_binder"],
        },
    )
    _write_json(run_a / theorem / "wild_type_graph.json", payload_refine)
    _write_json(run_b / theorem / "wild_type_graph.json", payload_chain)
    _write_json_gz(
        run_a / "summary.json.gz",
        {"theorems": [{"name": theorem, "wild_type": {"solved": True}, "interventions": []}]},
    )
    _write_json_gz(
        run_b / "summary.json.gz",
        {"theorems": [{"name": theorem, "wild_type": {"solved": True}, "interventions": []}]},
    )

    sig_a = load_run_signatures(run_a, solved_only=False)[0]
    sig_b = load_run_signatures(run_b, solved_only=False)[0]

    assert sig_a.proof_ir.continuation_profile["refine"] == 1.0
    assert sig_b.proof_ir.continuation_profile["chain"] == 1.0
    pair = pair_distance(sig_a, sig_b)
    assert pair.graph_distance > 0.0


def test_load_run_signatures_can_include_interventions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-a"
    _build_run(run_dir, [("t1", 4, True)])
    _add_intervention(run_dir, "t1", name="alt", node_count=6, solved=True)

    sigs_single = load_run_signatures(run_dir, solved_only=True)
    sigs_multi = load_run_signatures(
        run_dir,
        solved_only=True,
        include_interventions=True,
    )
    assert len(sigs_single) == 1
    assert len(sigs_multi) == 2
    assert {sig.variant for sig in sigs_multi} == {"wild_type", "alt"}
    assert all("t1::" in sig.proof_id for sig in sigs_multi)


def test_align_runs_best_of_uses_variant_pool(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(run_a, [("a1", 9, True), ("a2", 6, True)])
    _build_run(run_b, [("b1", 3, True), ("b2", 6, True)])
    _add_intervention(run_a, "a1", name="bridge", node_count=3, solved=True)

    report = align_runs(
        run_a,
        run_b,
        solved_only=True,
        top_k=2,
        one_to_one=True,
        proof_aggregation="best_of",
    )
    a1_row = next(row for row in report["matches"] if row["theorem_a"] == "a1")
    assert a1_row["theorem_b"] == "b1"
    assert a1_row["representative_pair"]["variant_a"] == "bridge"
    assert report["proof_aggregation"] == "best_of"
    assert report["run_a_proofs"] == 3


def test_align_runs_consensus_reports_nearest_neighbor_stats(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _build_run(run_a, [("a1", 8, True)])
    _build_run(run_b, [("b1", 3, True)])
    _add_intervention(run_a, "a1", name="bridge", node_count=3, solved=True)

    report = align_runs(
        run_a,
        run_b,
        solved_only=True,
        top_k=1,
        one_to_one=True,
        proof_aggregation="consensus",
    )
    assert report["proof_aggregation"] == "consensus"
    assert report["matches"][0]["nearest_neighbor_stats"] is not None
