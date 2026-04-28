import pytest

from prover.expr import ExprDAG, ExprNode
from prover.goal_signature import (
    GoalSignatureConfig,
    compute_goal_signature,
    compute_goal_signature_strict,
)
from prover.mcts import MCTSNode, MCTSTree


class TestMCTSTreeIsSolved:
    def test_single_terminal_node_is_solved(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        tree.root.is_terminal = True
        tree.root.children["trivial"] = []
        assert tree.is_solved()

    def test_single_dead_node_is_not_solved(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        tree.root.is_dead = True
        assert not tree.is_solved()

    def test_unexpanded_node_is_not_solved(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        assert not tree.is_solved()

    def test_and_node_requires_all_children_solved(self):
        tree = MCTSTree.create("root", "P /\\ Q", goal_sig="sig_and")
        child1 = MCTSNode(mvar_id="c1", goal_type="P", goal_sig="sig_P", parent=tree.root)
        child2 = MCTSNode(mvar_id="c2", goal_type="Q", goal_sig="sig_Q", parent=tree.root)
        tree.nodes_by_mvar["c1"] = child1
        tree.nodes_by_mvar["c2"] = child2
        tree.root.children["constructor"] = [child1, child2]
        child1.is_terminal = True
        child1.children["trivial"] = []
        assert not tree.is_solved()
        child2.is_terminal = True
        child2.children["assumption"] = []
        assert tree.is_solved()

    def test_or_node_only_needs_one_path(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        tactic1_child = MCTSNode(mvar_id="c1", goal_type="Q", goal_sig="sig_Q", parent=tree.root)
        tactic2_child = MCTSNode(mvar_id="c2", goal_type="R", goal_sig="sig_R", parent=tree.root)
        tree.nodes_by_mvar["c1"] = tactic1_child
        tree.nodes_by_mvar["c2"] = tactic2_child
        tree.root.children["apply h1"] = [tactic1_child]
        tree.root.children["apply h2"] = [tactic2_child]
        tactic1_child.is_dead = True
        tactic2_child.is_terminal = True
        tactic2_child.children["rfl"] = []
        assert tree.is_solved()

    def test_deep_tree_is_solved(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        current = tree.root
        for i in range(5):
            child = MCTSNode(
                mvar_id=f"n{i}",
                goal_type=f"G{i}",
                goal_sig=f"sig_{i}",
                parent=current,
                depth=i + 1,
            )
            tree.nodes_by_mvar[child.mvar_id] = child
            current.children[f"tactic_{i}"] = [child]
            current = child
        current.is_terminal = True
        current.children["done"] = []
        assert tree.is_solved()


class TestExprDAGStructuralHash:
    def test_identical_dags_have_same_hash(self):
        dag1 = ExprDAG(
            root_id="r",
            nodes={"r": ExprNode(kind="const", name="True")},
        )
        dag2 = ExprDAG(
            root_id="r",
            nodes={"r": ExprNode(kind="const", name="True")},
        )
        assert dag1.structural_hash() == dag2.structural_hash()
        assert dag1.is_equivalent(dag2)

    def test_different_consts_have_different_hash(self):
        dag1 = ExprDAG(
            root_id="r",
            nodes={"r": ExprNode(kind="const", name="True")},
        )
        dag2 = ExprDAG(
            root_id="r",
            nodes={"r": ExprNode(kind="const", name="False")},
        )
        assert dag1.structural_hash() != dag2.structural_hash()
        assert not dag1.is_equivalent(dag2)

    def test_different_root_ids_same_structure_same_hash(self):
        dag1 = ExprDAG(
            root_id="a",
            nodes={"a": ExprNode(kind="const", name="Nat.zero")},
        )
        dag2 = ExprDAG(
            root_id="x",
            nodes={"x": ExprNode(kind="const", name="Nat.zero")},
        )
        assert dag1.structural_hash() == dag2.structural_hash()

    def test_app_nodes_with_same_structure(self):
        dag1 = ExprDAG(
            root_id="app",
            nodes={
                "app": ExprNode(kind="app", fn="f", arg="x"),
                "f": ExprNode(kind="const", name="id"),
                "x": ExprNode(kind="const", name="Nat.zero"),
            },
        )
        dag2 = ExprDAG(
            root_id="app2",
            nodes={
                "app2": ExprNode(kind="app", fn="fn", arg="arg"),
                "fn": ExprNode(kind="const", name="id"),
                "arg": ExprNode(kind="const", name="Nat.zero"),
            },
        )
        assert dag1.structural_hash() == dag2.structural_hash()


class TestGoalSignature:
    def test_text_scheme_basic(self):
        config = GoalSignatureConfig(scheme="text")
        sig = compute_goal_signature(
            type_str="P -> Q",
            type_expr=None,
            hyp_types=["P"],
            hyp_exprs=[None],
            config=config,
        )
        assert len(sig) == 12
        assert isinstance(sig, str)

    def test_text_scheme_same_goal_same_sig(self):
        config = GoalSignatureConfig(scheme="text")
        sig1 = compute_goal_signature(
            type_str="Nat",
            type_expr=None,
            hyp_types=["n : Nat"],
            hyp_exprs=[None],
            config=config,
        )
        sig2 = compute_goal_signature(
            type_str="Nat",
            type_expr=None,
            hyp_types=["n : Nat"],
            hyp_exprs=[None],
            config=config,
        )
        assert sig1 == sig2

    def test_text_scheme_different_goals_different_sig(self):
        config = GoalSignatureConfig(scheme="text")
        sig1 = compute_goal_signature(
            type_str="Nat",
            type_expr=None,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        sig2 = compute_goal_signature(
            type_str="Int",
            type_expr=None,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        assert sig1 != sig2

    def test_text_scheme_normalizes_whitespace(self):
        config = GoalSignatureConfig(scheme="text")
        sig1 = compute_goal_signature(
            type_str="P  ->   Q",
            type_expr=None,
            hyp_types=["h :   P"],
            hyp_exprs=[None],
            config=config,
        )
        sig2 = compute_goal_signature(
            type_str="P -> Q",
            type_expr=None,
            hyp_types=["h : P"],
            hyp_exprs=[None],
            config=config,
        )
        assert sig1 == sig2

    def test_ast_scheme_raises_without_expr(self):
        config = GoalSignatureConfig(scheme="ast")
        with pytest.raises(ValueError, match="Missing AST"):
            compute_goal_signature(
                type_str="P",
                type_expr=None,
                hyp_types=[],
                hyp_exprs=[],
                config=config,
            )

    def test_ast_scheme_with_expr(self):
        config = GoalSignatureConfig(scheme="ast")
        type_expr = {
            "rootId": "r",
            "nodes": [("r", {"kind": "const", "name": "True"})],
        }
        sig = compute_goal_signature(
            type_str="True",
            type_expr=type_expr,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        assert len(sig) == 12


class TestBug1FvarMvarIdentity:
    def test_fvar_identity_affects_strict_only(self):
        config = GoalSignatureConfig(scheme="ast")
        type_expr_h1 = {
            "rootId": "r",
            "nodes": [("r", {"kind": "fvar", "fvarId": "_uniq.1"})],
        }
        type_expr_h2 = {
            "rootId": "r",
            "nodes": [("r", {"kind": "fvar", "fvarId": "_uniq.2"})],
        }
        coarse1 = compute_goal_signature(
            type_str="h1", type_expr=type_expr_h1, hyp_types=[], hyp_exprs=[], config=config
        )
        coarse2 = compute_goal_signature(
            type_str="h2", type_expr=type_expr_h2, hyp_types=[], hyp_exprs=[], config=config
        )
        strict1 = compute_goal_signature_strict(
            type_str="h1", type_expr=type_expr_h1, hyp_types=[], hyp_exprs=[], config=config
        )
        strict2 = compute_goal_signature_strict(
            type_str="h2", type_expr=type_expr_h2, hyp_types=[], hyp_exprs=[], config=config
        )
        assert coarse1 == coarse2
        assert strict1 != strict2

    def test_mvar_identity_affects_strict_only(self):
        config = GoalSignatureConfig(scheme="ast")
        type_expr_m1 = {
            "rootId": "r",
            "nodes": [("r", {"kind": "mvar", "name": "_uniq.100"})],
        }
        type_expr_m2 = {
            "rootId": "r",
            "nodes": [("r", {"kind": "mvar", "name": "_uniq.200"})],
        }
        coarse1 = compute_goal_signature(
            type_str="?m1", type_expr=type_expr_m1, hyp_types=[], hyp_exprs=[], config=config
        )
        coarse2 = compute_goal_signature(
            type_str="?m2", type_expr=type_expr_m2, hyp_types=[], hyp_exprs=[], config=config
        )
        strict1 = compute_goal_signature_strict(
            type_str="?m1", type_expr=type_expr_m1, hyp_types=[], hyp_exprs=[], config=config
        )
        strict2 = compute_goal_signature_strict(
            type_str="?m2", type_expr=type_expr_m2, hyp_types=[], hyp_exprs=[], config=config
        )
        assert coarse1 == coarse2
        assert strict1 != strict2


class TestBackpropTreeSemantics:
    def test_backprop_updates_parent_chain(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        child = tree.expand(tree.root, "tactic1", ["c1"], ["Q"], ["sig_Q"])[0]
        tree.backpropagate(child, success=True)
        assert child.visit_count == 1
        assert child.success_count == 1
        assert tree.root.visit_count == 1
        assert tree.root.success_count == 1

    def test_expand_rejects_duplicate_mvar(self):
        tree = MCTSTree.create("root", "P", goal_sig="sig_P")
        tree.expand(tree.root, "tactic1", ["c1"], ["Q"], ["sig_Q"])
        with pytest.raises(ValueError, match="Duplicate mvar_id"):
            tree.expand(tree.root, "tactic2", ["c1"], ["Q"], ["sig_Q"])

    def test_expand_allows_checkpoint_scoped_ids(self):
        tree = MCTSTree.create("cp1:root", "P", goal_sig="sig_P")
        tree.expand(tree.root, "tactic1", ["cp1:_uniq.1"], ["Q"], ["sig_Q"])
        tree.expand(tree.root, "tactic2", ["cp2:_uniq.1"], ["Q"], ["sig_Q"])


class TestBug3AlphaEquivalence:
    def test_alpha_equivalent_lambdas_same_hash(self):
        dag1 = ExprDAG(
            root_id="lam",
            nodes={
                "lam": ExprNode(kind="lam", binder_name="x", binder_type="ty", body="body"),
                "ty": ExprNode(kind="const", name="Nat"),
                "body": ExprNode(kind="bvar", de_bruijn_idx=0),
            },
        )
        dag2 = ExprDAG(
            root_id="lam",
            nodes={
                "lam": ExprNode(kind="lam", binder_name="y", binder_type="ty", body="body"),
                "ty": ExprNode(kind="const", name="Nat"),
                "body": ExprNode(kind="bvar", de_bruijn_idx=0),
            },
        )
        assert dag1.structural_hash() == dag2.structural_hash()
        assert dag1.is_equivalent(dag2)

    def test_different_fvar_ids_different_hash(self):
        dag1 = ExprDAG(
            root_id="fvar",
            nodes={"fvar": ExprNode(kind="fvar", fvar_id="_uniq.1")},
        )
        dag2 = ExprDAG(
            root_id="fvar",
            nodes={"fvar": ExprNode(kind="fvar", fvar_id="_uniq.2")},
        )
        assert dag1.structural_hash() != dag2.structural_hash()


class TestBug4NestedCommutativeNormalization:
    def test_nested_and_normalized(self):
        config = GoalSignatureConfig(scheme="ast")
        type_expr_pq_or_r = {
            "rootId": "or_app",
            "nodes": [
                ("or_app", {"kind": "app", "fn": "or_pq", "arg": "r"}),
                ("or_pq", {"kind": "app", "fn": "or", "arg": "and_app"}),
                ("or", {"kind": "const", "name": "Or"}),
                ("and_app", {"kind": "app", "fn": "and_p", "arg": "q"}),
                ("and_p", {"kind": "app", "fn": "and", "arg": "p"}),
                ("and", {"kind": "const", "name": "And"}),
                ("p", {"kind": "const", "name": "P"}),
                ("q", {"kind": "const", "name": "Q"}),
                ("r", {"kind": "const", "name": "R"}),
            ],
        }
        type_expr_qp_or_r = {
            "rootId": "or_app",
            "nodes": [
                ("or_app", {"kind": "app", "fn": "or_qp", "arg": "r"}),
                ("or_qp", {"kind": "app", "fn": "or", "arg": "and_app"}),
                ("or", {"kind": "const", "name": "Or"}),
                ("and_app", {"kind": "app", "fn": "and_q", "arg": "p"}),
                ("and_q", {"kind": "app", "fn": "and", "arg": "q"}),
                ("and", {"kind": "const", "name": "And"}),
                ("p", {"kind": "const", "name": "P"}),
                ("q", {"kind": "const", "name": "Q"}),
                ("r", {"kind": "const", "name": "R"}),
            ],
        }
        sig1 = compute_goal_signature(
            type_str="(P /\\ Q) \\/ R",
            type_expr=type_expr_pq_or_r,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        sig2 = compute_goal_signature(
            type_str="(Q /\\ P) \\/ R",
            type_expr=type_expr_qp_or_r,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        assert sig1 == sig2

    def test_top_level_commutative_still_works(self):
        config = GoalSignatureConfig(scheme="ast")
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
        sig1 = compute_goal_signature(
            type_str="P /\\ Q",
            type_expr=type_expr_p_and_q,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        sig2 = compute_goal_signature(
            type_str="Q /\\ P",
            type_expr=type_expr_q_and_p,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        assert sig1 == sig2

    def test_strict_signature_keeps_commutative_order(self):
        config = GoalSignatureConfig(scheme="ast")
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
        sig1 = compute_goal_signature_strict(
            type_str="P /\\ Q",
            type_expr=type_expr_p_and_q,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        sig2 = compute_goal_signature_strict(
            type_str="Q /\\ P",
            type_expr=type_expr_q_and_p,
            hyp_types=[],
            hyp_exprs=[],
            config=config,
        )
        assert sig1 != sig2
