from prover.goal_cache import GoalCache
from prover.goal_distance import (
    GoalSigTedDistance,
    goal_ast_dag_to_tree,
    normalized_sequence_edit_distance,
)
from prover.goal_signature import GoalSignatureConfig
from prover.tree_edit_distance import tree_edit_distance


def test_goal_ast_commutative_and_normalizes():
    type_expr_p_and_q = {
        "rootId": "and_app",
        "nodes": [
            ("and_app", {"kind": "app", "fn": "and_p", "arg": "q"}),
            ("and_p", {"kind": "app", "fn": "and", "arg": "p"}),
            ("and", {"kind": "const", "name": "And"}),
            ("p", {"kind": "const", "name": "P"}),
            ("q", {"kind": "const", "name": "Q"}),
        ],
    }
    type_expr_q_and_p = {
        "rootId": "and_app",
        "nodes": [
            ("and_app", {"kind": "app", "fn": "and_q", "arg": "p"}),
            ("and_q", {"kind": "app", "fn": "and", "arg": "q"}),
            ("and", {"kind": "const", "name": "And"}),
            ("p", {"kind": "const", "name": "P"}),
            ("q", {"kind": "const", "name": "Q"}),
        ],
    }

    t1 = goal_ast_dag_to_tree(type_expr_p_and_q, strict=False, max_nodes=200)
    t2 = goal_ast_dag_to_tree(type_expr_q_and_p, strict=False, max_nodes=200)
    assert tree_edit_distance(t1, t2) == 0


def test_goal_sig_ted_distance_basic():
    config = GoalSignatureConfig(scheme="ast")
    cache = GoalCache(config)

    type_expr_p = {"rootId": "r", "nodes": [("r", {"kind": "const", "name": "P"})]}
    type_expr_q = {"rootId": "r", "nodes": [("r", {"kind": "const", "name": "Q"})]}

    sig_p = cache.add_goal(
        mvar_id="cp1:_uniq.1",
        type_str="P",
        type_expr=type_expr_p,
        hyp_types=[],
        hyp_exprs=[],
    )
    sig_q = cache.add_goal(
        mvar_id="cp1:_uniq.2",
        type_str="Q",
        type_expr=type_expr_q,
        hyp_types=[],
        hyp_exprs=[],
    )

    dist = GoalSigTedDistance(cache, max_goal_tree_nodes=200)
    assert dist.normalized_distance(sig_p, sig_p) == 0.0
    # Substitution of const:P -> const:Q is 1 edit over total size 6.
    assert dist.normalized_distance(sig_p, sig_q) == 1.0 / 6.0


def test_solution_path_soft_distance_sequence_edit_distance():
    config = GoalSignatureConfig(scheme="ast")
    cache = GoalCache(config)
    type_expr_p = {"rootId": "r", "nodes": [("r", {"kind": "const", "name": "P"})]}
    type_expr_q = {"rootId": "r", "nodes": [("r", {"kind": "const", "name": "Q"})]}
    sig_p = cache.add_goal(
        mvar_id="cp1:_uniq.1",
        type_str="P",
        type_expr=type_expr_p,
        hyp_types=[],
        hyp_exprs=[],
    )
    sig_q = cache.add_goal(
        mvar_id="cp1:_uniq.2",
        type_str="Q",
        type_expr=type_expr_q,
        hyp_types=[],
        hyp_exprs=[],
    )

    dist = GoalSigTedDistance(cache, max_goal_tree_nodes=200)
    assert (
        normalized_sequence_edit_distance(
            [sig_p, sig_q],
            [sig_p, sig_q],
            subst_cost=dist.normalized_distance,
        )
        == 0.0
    )
