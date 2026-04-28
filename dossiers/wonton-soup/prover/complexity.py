"""
Proof complexity metrics for ExprDAG proof terms.

Implements several complexity measures:
- DAG sharing ratio: tree_size / dag_size
- Cut count: intro-elim pairs (proof-theoretic detours)
- Lambda depth: maximum nesting of lambda abstractions
- Application spine length: longest chain of applications
"""

from dataclasses import dataclass

from prover.expr import ExprDAG


@dataclass
class ComplexityMetrics:
    dag_size: int
    tree_size: int
    sharing_ratio: float
    cut_count: int
    lambda_depth: int
    max_app_spine: int
    let_count: int
    projection_count: int


INTRO_CONSTS = frozenset({
    "And.intro",
    "Or.inl",
    "Or.inr",
    "Exists.intro",
    "Iff.intro",
    "True.intro",
    "Eq.refl",
    "HEq.refl",
    "Subtype.mk",
})

ELIM_CONSTS = frozenset({
    "And.left",
    "And.right",
    "Or.elim",
    "Or.rec",
    "Exists.elim",
    "Exists.rec",
    "Iff.mp",
    "Iff.mpr",
    "False.elim",
    "False.rec",
    "Eq.mpr",
    "Eq.mp",
    "Eq.subst",
    "Eq.rec",
    "HEq.subst",
    "HEq.rec",
    "eq_true",
    "of_eq_true",
    "eq_false",
    "of_eq_false",
})


def compute_tree_size(dag: ExprDAG) -> int:
    if not dag.nodes or dag.root_id not in dag.nodes:
        return 0

    def visit(node_id: str) -> int:
        node = dag.nodes.get(node_id)
        if node is None:
            return 0

        size = 1
        children = [
            node.fn,
            node.arg,
            node.binder_type,
            node.body,
            node.value,
            node.proj_expr,
        ]
        for child_id in children:
            if child_id:
                size += visit(child_id)
        return size

    return visit(dag.root_id)


def compute_sharing_ratio(dag: ExprDAG) -> float:
    dag_size = len(dag.nodes)
    if dag_size == 0:
        return 1.0
    tree_size = compute_tree_size(dag)
    return tree_size / dag_size


def count_cuts(dag: ExprDAG) -> int:
    const_names = set()
    for node in dag.nodes.values():
        if node.kind == "const" and node.name:
            const_names.add(node.name)

    intros_present = const_names & INTRO_CONSTS
    elims_present = const_names & ELIM_CONSTS

    cut_pairs = 0

    if "And.intro" in intros_present:
        if "And.left" in elims_present or "And.right" in elims_present:
            cut_pairs += 1

    if "Or.inl" in intros_present or "Or.inr" in intros_present:
        if "Or.elim" in elims_present or "Or.rec" in elims_present:
            cut_pairs += 1

    if "Exists.intro" in intros_present:
        if "Exists.elim" in elims_present or "Exists.rec" in elims_present:
            cut_pairs += 1

    if "Iff.intro" in intros_present:
        if "Iff.mp" in elims_present or "Iff.mpr" in elims_present:
            cut_pairs += 1

    if "Eq.refl" in intros_present:
        if any(e in elims_present for e in ["Eq.mpr", "Eq.mp", "Eq.subst", "Eq.rec"]):
            cut_pairs += 1

    if "eq_true" in elims_present and "of_eq_true" in elims_present:
        cut_pairs += 1

    return cut_pairs


def compute_lambda_depth(dag: ExprDAG) -> int:
    if not dag.nodes or dag.root_id not in dag.nodes:
        return 0

    max_depth = [0]

    def visit(node_id: str, current_depth: int) -> None:
        node = dag.nodes.get(node_id)
        if node is None:
            return

        if node.kind == "lam":
            new_depth = current_depth + 1
            max_depth[0] = max(max_depth[0], new_depth)
            if node.body:
                visit(node.body, new_depth)
            if node.binder_type:
                visit(node.binder_type, current_depth)
        else:
            children = [
                node.fn,
                node.arg,
                node.binder_type,
                node.body,
                node.value,
                node.proj_expr,
            ]
            for child_id in children:
                if child_id:
                    visit(child_id, current_depth)

    visit(dag.root_id, 0)
    return max_depth[0]


def compute_max_app_spine(dag: ExprDAG) -> int:
    if not dag.nodes or dag.root_id not in dag.nodes:
        return 0

    cache: dict[str, int] = {}

    def spine_length(node_id: str) -> int:
        if node_id in cache:
            return cache[node_id]

        node = dag.nodes.get(node_id)
        if node is None:
            return 0

        if node.kind == "app":
            fn_spine = 1 + spine_length(node.fn) if node.fn else 1
            cache[node_id] = fn_spine
            return fn_spine
        else:
            cache[node_id] = 0
            return 0

    max_spine = 0
    for node_id in dag.nodes:
        max_spine = max(max_spine, spine_length(node_id))

    return max_spine


def compute_let_count(dag: ExprDAG) -> int:
    return sum(1 for n in dag.nodes.values() if n.kind == "letE")


def compute_projection_count(dag: ExprDAG) -> int:
    return sum(1 for n in dag.nodes.values() if n.kind == "proj")


def compute_complexity(dag: ExprDAG) -> ComplexityMetrics:
    dag_size = len(dag.nodes)
    tree_size = compute_tree_size(dag)
    sharing_ratio = tree_size / dag_size if dag_size > 0 else 1.0

    return ComplexityMetrics(
        dag_size=dag_size,
        tree_size=tree_size,
        sharing_ratio=round(sharing_ratio, 3),
        cut_count=count_cuts(dag),
        lambda_depth=compute_lambda_depth(dag),
        max_app_spine=compute_max_app_spine(dag),
        let_count=compute_let_count(dag),
        projection_count=compute_projection_count(dag),
    )


def metrics_to_dict(metrics: ComplexityMetrics) -> dict:
    return {
        "dag_size": metrics.dag_size,
        "tree_size": metrics.tree_size,
        "sharing_ratio": metrics.sharing_ratio,
        "cut_count": metrics.cut_count,
        "lambda_depth": metrics.lambda_depth,
        "max_app_spine": metrics.max_app_spine,
        "let_count": metrics.let_count,
        "projection_count": metrics.projection_count,
    }


def compare_complexity(dag1: ExprDAG, dag2: ExprDAG) -> dict:
    m1 = compute_complexity(dag1)
    m2 = compute_complexity(dag2)

    return {
        "first": metrics_to_dict(m1),
        "second": metrics_to_dict(m2),
        "comparison": {
            "dag_size_ratio": round(m2.dag_size / m1.dag_size, 3) if m1.dag_size > 0 else None,
            "tree_size_ratio": round(m2.tree_size / m1.tree_size, 3) if m1.tree_size > 0 else None,
            "sharing_diff": round(m2.sharing_ratio - m1.sharing_ratio, 3),
            "cut_diff": m2.cut_count - m1.cut_count,
            "lambda_depth_diff": m2.lambda_depth - m1.lambda_depth,
            "app_spine_diff": m2.max_app_spine - m1.max_app_spine,
        },
    }
