from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from prover.goal_cache import GoalCache
from prover.goal_signature import (
    hash_normalized_goal_ast,
    normalize_commutative_goal_ast,
    validate_goal_ast,
)
from prover.tree_edit_distance import OrderedTree, tree_edit_distance

MAX_GOAL_TREE_NODES = 800


def _tree_size(root: OrderedTree) -> int:
    n = 0
    stack = [root]
    while stack:
        node = stack.pop()
        n += 1
        stack.extend(node.children)
    return n


def goal_ast_dag_to_tree(
    dag: dict,
    *,
    strict: bool = False,
    max_nodes: int = MAX_GOAL_TREE_NODES,
) -> OrderedTree:
    """Convert the Lean goal AST DAG to an ordered tree for edit distance.

    Notes:
    - Non-strict mode normalizes commutative operators (And/Or/Iff).
    - fvar/mvar labels are anonymized in non-strict mode (renaming-invariant).
    - We intentionally *unfold* the DAG into a tree; shared subexpressions are duplicated.
    """

    if not strict:
        dag = normalize_commutative_goal_ast(dag)

    root_id, nodes = validate_goal_ast(dag)

    built = 0
    in_stack: set[str] = set()

    def build(node_id: str) -> OrderedTree:
        nonlocal built
        if node_id in in_stack:
            raise ValueError("Cycle detected in goal AST DAG")
        node = nodes.get(node_id)
        if node is None:
            raise ValueError(f"Goal AST missing node: {node_id}")

        built += 1
        if built > max_nodes:
            raise ValueError(f"Goal AST tree exceeds max_nodes={max_nodes}")

        in_stack.add(node_id)
        try:
            kind = node.get("kind")
            if not kind:
                raise ValueError(f"Goal AST node {node_id} missing kind")

            if kind == "const":
                name = node.get("name")
                if not name:
                    raise ValueError(f"const node {node_id} missing name")
                return OrderedTree(f"const:{name}")
            if kind == "bvar":
                if "deBruijnIdx" not in node:
                    raise ValueError(f"bvar node {node_id} missing deBruijnIdx")
                return OrderedTree(f"bvar:{node['deBruijnIdx']}")
            if kind == "fvar":
                if strict:
                    fvar_id = node.get("fvarId")
                    if not fvar_id:
                        raise ValueError(f"fvar node {node_id} missing fvarId")
                    return OrderedTree(f"fvar:{fvar_id}")
                return OrderedTree("fvar")
            if kind == "mvar":
                if strict:
                    name = node.get("name")
                    if not name:
                        raise ValueError(f"mvar node {node_id} missing name")
                    return OrderedTree(f"mvar:{name}")
                return OrderedTree("mvar")
            if kind == "sort":
                if "levelVal" not in node:
                    raise ValueError(f"sort node {node_id} missing levelVal")
                return OrderedTree(f"sort:{node['levelVal']}")
            if kind == "lit":
                if "litVal" not in node:
                    raise ValueError(f"lit node {node_id} missing litVal")
                return OrderedTree(f"lit:{node['litVal']}")
            if kind == "app":
                fn_id = node.get("fn")
                arg_id = node.get("arg")
                if fn_id is None or arg_id is None:
                    raise ValueError(f"app node {node_id} missing fn or arg")
                return OrderedTree("app", (build(fn_id), build(arg_id)))
            if kind in ("lam", "forallE"):
                ty_id = node.get("binderType")
                body_id = node.get("body")
                if ty_id is None or body_id is None:
                    raise ValueError(f"{kind} node {node_id} missing binderType or body")
                label = "lam" if kind == "lam" else "forall"
                return OrderedTree(label, (build(ty_id), build(body_id)))
            if kind == "letE":
                ty_id = node.get("binderType")
                val_id = node.get("value")
                body_id = node.get("body")
                if ty_id is None or val_id is None or body_id is None:
                    raise ValueError(f"letE node {node_id} missing binderType, value, or body")
                return OrderedTree("let", (build(ty_id), build(val_id), build(body_id)))
            if kind == "proj":
                expr_id = node.get("projExpr")
                if expr_id is None:
                    raise ValueError(f"proj node {node_id} missing projExpr")
                struct_name = node.get("structName")
                if not struct_name:
                    raise ValueError(f"proj node {node_id} missing structName")
                if "projIdx" not in node:
                    raise ValueError(f"proj node {node_id} missing projIdx")
                return OrderedTree(
                    f"proj:{struct_name}:{node['projIdx']}",
                    (build(expr_id),),
                )

            raise ValueError(f"Unknown goal AST node kind: {kind}")
        finally:
            in_stack.remove(node_id)

    return build(root_id)


@dataclass
class GoalSigTedDistance:
    """Distance between goal signatures based on normalized goal-AST ordered TED."""

    goal_cache: GoalCache
    max_goal_tree_nodes: int = MAX_GOAL_TREE_NODES
    _trees: dict[str, OrderedTree] = field(default_factory=dict)
    _tree_sizes: dict[str, int] = field(default_factory=dict)
    _dist_cache: dict[tuple[str, str], float] = field(default_factory=dict)
    tree_errors: dict[str, str] = field(default_factory=dict)

    def tree(self, sig: str) -> OrderedTree | None:
        if sig in self._trees:
            return self._trees[sig]
        if sig in self.tree_errors:
            return None

        entry = self.goal_cache.entries.get(sig)
        if entry is None:
            self.tree_errors[sig] = "missing_sig_in_goal_cache"
            return None
        if entry.type_expr is None or any(h is None for h in entry.hyp_exprs):
            self.tree_errors[sig] = "missing_ast_for_sig"
            return None

        try:
            type_tree = goal_ast_dag_to_tree(
                entry.type_expr,
                strict=False,
                max_nodes=self.max_goal_tree_nodes,
            )
            hyp_exprs = list(entry.hyp_exprs)
            hyp_exprs.sort(key=lambda dag: hash_normalized_goal_ast(dag, strict=False))
            hyp_trees = tuple(
                goal_ast_dag_to_tree(h, strict=False, max_nodes=self.max_goal_tree_nodes)
                for h in hyp_exprs
            )
            combined = OrderedTree("goal", (type_tree, OrderedTree("hyps", hyp_trees)))
        except Exception as e:
            self.tree_errors[sig] = f"tree_build_failed:{type(e).__name__}:{e}"
            return None

        self._trees[sig] = combined
        self._tree_sizes[sig] = _tree_size(combined)
        return combined

    def normalized_distance(self, sig1: str, sig2: str) -> float:
        if sig1 == sig2:
            return 0.0
        a, b = (sig1, sig2) if sig1 <= sig2 else (sig2, sig1)
        cached = self._dist_cache.get((a, b))
        if cached is not None:
            return cached

        t1 = self.tree(sig1)
        t2 = self.tree(sig2)
        if t1 is None or t2 is None:
            self._dist_cache[(a, b)] = 1.0
            return 1.0

        n1 = self._tree_sizes[sig1]
        n2 = self._tree_sizes[sig2]
        denom = n1 + n2
        if denom == 0:
            self._dist_cache[(a, b)] = 0.0
            return 0.0

        dist = tree_edit_distance(t1, t2) / denom
        self._dist_cache[(a, b)] = dist
        return dist


def sequence_edit_distance(
    seq1: list[str],
    seq2: list[str],
    *,
    subst_cost: Callable[[str, str], float],
) -> float:
    """Levenshtein-style edit distance over sequences with custom substitution costs."""

    n = len(seq1)
    m = len(seq2)
    if n == 0:
        return float(m)
    if m == 0:
        return float(n)

    prev = [float(j) for j in range(m + 1)]
    curr = [0.0] * (m + 1)
    for i in range(1, n + 1):
        curr[0] = float(i)
        s1 = seq1[i - 1]
        for j in range(1, m + 1):
            s2 = seq2[j - 1]
            cost_sub = float(subst_cost(s1, s2))
            curr[j] = min(
                prev[j] + 1.0,
                curr[j - 1] + 1.0,
                prev[j - 1] + cost_sub,
            )
        prev, curr = curr, prev
    return prev[m]


def normalized_sequence_edit_distance(
    seq1: list[str],
    seq2: list[str],
    *,
    subst_cost: Callable[[str, str], float],
) -> float:
    denom = len(seq1) + len(seq2)
    if denom == 0:
        return 0.0
    return sequence_edit_distance(seq1, seq2, subst_cost=subst_cost) / denom
