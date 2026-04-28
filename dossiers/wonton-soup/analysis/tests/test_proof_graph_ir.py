from __future__ import annotations

from analysis.proof_graph_ir import (
    ProofGraphIR,
    apply_relative_ranks,
    build_proof_graph_ir,
    build_tactic_action_ir,
)
from prover.proof import (
    GRAPH_FAMILY_EXTERNAL_PROOF,
    GRAPH_FAMILY_PROOF_TERM_DAG,
    GRAPH_FAMILY_SEARCH_TRACE,
    ProofGraph,
)


def _build_search_trace_graph() -> ProofGraph:
    graph = ProofGraph.for_search_trace(backend="lean")
    graph.add_node("r", goal_type="P -> P", depth=0, goal_sig="root")
    graph.add_expansion(
        "r",
        "intro h",
        ["h_goal"],
        ["P"],
        ["h_goal"],
    )
    graph.add_expansion(
        "h_goal",
        "exact h",
        [],
        [],
        [],
    )
    return graph


def _build_term_graph() -> ProofGraph:
    payload = {
        "graph_family": GRAPH_FAMILY_PROOF_TERM_DAG,
        "graph_backend": "coq",
        "graph_provenance": "proof_term",
        "nodes": [
            {"id": "n0", "goal_type": "app", "goal_sig": "s0", "depth": 0},
            {"id": "n1", "goal_type": "const", "goal_sig": "s1", "depth": 1},
            {"id": "n2", "goal_type": "bvar", "goal_sig": "s2", "depth": 1},
            {"id": "n3", "goal_type": "lam", "goal_sig": "s3", "depth": 2},
        ],
        "edges": [
            {"source": "n0", "target": "n1", "tactic_norm": "fn"},
            {"source": "n0", "target": "n2", "tactic_norm": "arg"},
            {"source": "n3", "target": "n1", "tactic_norm": "binder_type"},
            {"source": "n3", "target": "n2", "tactic_norm": "body"},
        ],
    }
    return ProofGraph.deserialize(payload)


def test_build_proof_graph_ir_classifies_search_trace() -> None:
    ir = build_proof_graph_ir(_build_search_trace_graph(), backend_hint="lean")
    assert ir.graph_family == GRAPH_FAMILY_SEARCH_TRACE
    assert "fam:intro" in ir.edge_role_profile
    assert ir.action_kind_profile["tactic_step"] == 1.0
    assert "bind" in ir.operator_profile
    assert ir.effect_profile["opens_binder"] == 0.5
    assert ir.effect_profile["discharges_goal"] == 0.5
    assert ir.continuation_profile["chain"] == 0.5
    assert ir.continuation_profile["solve"] == 0.5
    assert ir.coupling_profile["none"] == 1.0
    assert "motif:bind_open" in ir.motif_profile


def test_build_proof_graph_ir_classifies_term_dag() -> None:
    ir = build_proof_graph_ir(_build_term_graph(), backend_hint="coq")
    assert ir.graph_family == GRAPH_FAMILY_PROOF_TERM_DAG
    assert "fn" in ir.edge_role_profile
    assert "arg" in ir.edge_role_profile
    assert ir.action_kind_profile["term_constructor"] == 1.0
    assert ir.operator_profile["apply"] > 0.0
    assert ir.operator_profile["value"] > 0.0
    assert ir.motif_profile["motif:term_apply"] > 0.0
    assert ir.motif_profile["motif:term_value"] > 0.0
    assert ir.effect_profile["builds_term"] == 1.0
    assert ir.effect_profile["refines_term"] > 0.0
    assert ir.effect_profile["opens_binder"] > 0.0
    assert ir.continuation_profile["structural"] == 1.0
    assert ir.coupling_profile["none"] == 1.0


def test_build_tactic_action_ir_groups_term_constructors_by_node() -> None:
    actions = build_tactic_action_ir(_build_term_graph(), graph_family=GRAPH_FAMILY_PROOF_TERM_DAG)

    assert len(actions) == 4
    branch_arities = sorted(action.branch_arity for action in actions)
    assert branch_arities == [0, 0, 2, 2]
    assert all(action.action_kind == "term_constructor" for action in actions)
    assert all(action.continuation_kind == "structural" for action in actions)
    assert all(action.goal_coupling == "none" for action in actions)
    assert any(action.operator_kind == "value" for action in actions)


def test_build_proof_graph_ir_recovers_term_family_from_legacy_proof_graph() -> None:
    payload = {
        "graph_kind": "proof_graph",
        "nodes": [
            {"id": "n0", "goal_type": "app", "depth": 0, "goal_sig": "s0"},
            {"id": "n1", "goal_type": "const", "depth": 1, "goal_sig": "s1"},
            {"id": "n2", "goal_type": "bvar", "depth": 1, "goal_sig": "s2"},
        ],
        "edges": [
            {"source": "n0", "target": "n1", "tactic_norm": "fn"},
            {"source": "n0", "target": "n2", "tactic_norm": "arg"},
        ],
    }
    graph = ProofGraph.deserialize(payload)

    assert graph.graph_family == GRAPH_FAMILY_EXTERNAL_PROOF

    ir = build_proof_graph_ir(graph, backend_hint="coq")

    assert ir.graph_family == GRAPH_FAMILY_PROOF_TERM_DAG
    assert ir.action_kind_profile["term_constructor"] == 1.0
    assert ir.continuation_profile["structural"] == 1.0


def test_build_proof_graph_ir_uses_coq_constructor_metadata_when_available() -> None:
    payload = {
        "graph_family": GRAPH_FAMILY_PROOF_TERM_DAG,
        "nodes": [
            {
                "id": "n0",
                "goal_type": "const",
                "node_kind": "const",
                "const_name": "Case",
                "goal_sig": "s0",
            },
            {
                "id": "n1",
                "goal_type": "const",
                "node_kind": "const",
                "const_name": "Prod",
                "goal_sig": "s1",
            },
            {
                "id": "n2",
                "goal_type": "const",
                "node_kind": "const",
                "const_name": "Cast",
                "goal_sig": "s2",
            },
        ],
        "edges": [],
    }
    graph = ProofGraph.deserialize(payload)

    ir = build_proof_graph_ir(graph, backend_hint="coq")

    assert ir.operator_profile["branch"] == 1 / 3
    assert ir.operator_profile["bind"] == 1 / 3
    assert ir.operator_profile["rewrite"] == 1 / 3
    assert ir.effect_profile["branches_goals"] == 1 / 3
    assert ir.effect_profile["opens_goals"] == 1 / 3
    assert ir.effect_profile["opens_binder"] == 1 / 3
    assert ir.effect_profile["rewrites_target"] == 1 / 3


def test_build_tactic_action_ir_preserves_branching_and_terminal_steps() -> None:
    graph = ProofGraph.for_search_trace(backend="lean")
    graph.add_node("r", goal_type="P /\\ Q", depth=0, goal_sig="root")
    graph.add_expansion(
        "r",
        "constructor",
        ["left_goal", "right_goal"],
        ["P", "Q"],
        ["left_goal", "right_goal"],
    )
    graph.add_expansion("left_goal", "exact hp", [], [], [])
    graph.add_expansion("right_goal", "exact hq", [], [], [])

    actions = build_tactic_action_ir(graph, graph_family=GRAPH_FAMILY_SEARCH_TRACE)

    assert len(actions) == 3
    split_action = next(action for action in actions if action.branch_arity == 2)
    assert split_action.continuation_kind == "branch"
    assert split_action.goal_coupling == "unknown"
    assert split_action.effect_flags == frozenset({"branches_goals"})
    terminal_actions = [action for action in actions if action.branch_arity == 0]
    assert len(terminal_actions) == 2
    assert all(action.continuation_kind == "solve" for action in terminal_actions)


def test_build_tactic_action_ir_prefers_explicit_preview_metadata() -> None:
    graph = ProofGraph.for_search_trace(backend="lean")
    graph.add_node("r", goal_type="P /\\ Q", depth=0, goal_sig="root")
    graph.add_expansion(
        "r",
        "constructor",
        ["left_goal", "right_goal"],
        ["P", "Q"],
        ["left_goal", "right_goal"],
        action_attrs={
            "branch_arity": 2,
            "goal_coupling": "independent",
            "shared_mvar_count": 0,
            "continuation_kind": "refine",
            "effect_flags": [
                "branches_goals",
                "splits_independent_goals",
                "refines_term",
                "uses_hypotheses",
            ],
        },
    )

    actions = build_tactic_action_ir(graph, graph_family=GRAPH_FAMILY_SEARCH_TRACE)

    assert len(actions) == 1
    action = actions[0]
    assert action.branch_arity == 2
    assert action.goal_coupling == "independent"
    assert action.continuation_kind == "refine"
    assert "splits_independent_goals" in action.effect_flags
    assert "uses_hypotheses" in action.effect_flags
    ir = build_proof_graph_ir(graph, backend_hint="lean")
    assert ir.continuation_profile["refine"] == 1.0
    assert ir.coupling_profile["independent"] == 1.0
    assert ir.effect_profile["uses_hypotheses"] == 1.0


def _ir(kind: str, node_count: int) -> ProofGraphIR:
    return ProofGraphIR(
        graph_family=kind,
        node_count=node_count,
        edge_count=max(node_count - 1, 0),
        max_depth=node_count,
        root_count=1,
        leaf_ratio=0.2,
        branching_ratio=0.1,
        mean_branch_factor=1.0,
        edge_role_profile={},
        action_kind_profile={},
        operator_profile={},
        motif_profile={},
        effect_profile={},
        continuation_profile={},
        coupling_profile={},
        shape_hash=f"h-{kind}-{node_count}",
    )


def test_apply_relative_ranks_normalizes_within_kind() -> None:
    ranked = apply_relative_ranks(
        [
            _ir(GRAPH_FAMILY_SEARCH_TRACE, 2),
            _ir(GRAPH_FAMILY_SEARCH_TRACE, 4),
            _ir(GRAPH_FAMILY_SEARCH_TRACE, 8),
            _ir(GRAPH_FAMILY_PROOF_TERM_DAG, 100),
        ]
    )
    assert ranked[0].node_rank == 0.0
    assert ranked[1].node_rank == 0.5
    assert ranked[2].node_rank == 1.0
    assert ranked[3].node_rank == 0.5
