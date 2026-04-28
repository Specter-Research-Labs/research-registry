from __future__ import annotations

from atp.coq.terms import proof_graph_from_dag
from prover.expr import ExprDAG, ExprNode


def test_proof_graph_from_dag_preserves_term_node_metadata() -> None:
    dag = ExprDAG(
        root_id="n0",
        nodes={
            "n0": ExprNode(kind="app", fn="n1", arg="n2"),
            "n1": ExprNode(kind="const", name="Case"),
            "n2": ExprNode(kind="lam", binder_name="h", binder_type="n3", body="n4"),
            "n3": ExprNode(kind="sort", level_val="Prop"),
            "n4": ExprNode(kind="bvar", de_bruijn_idx=0),
        },
    )

    graph = proof_graph_from_dag(dag)

    case_node = graph.graph.nodes["n1"]
    lam_node = graph.graph.nodes["n2"]
    assert case_node["const_name"] == "Case"
    assert lam_node["binder_name"] == "h"
    assert graph.graph.nodes["n3"]["level_val"] == "Prop"
    assert graph.graph.nodes["n4"]["de_bruijn_idx"] == 0
