from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atp.sexp import sexpr_to_string
from prover.expr import ExprDAG, ExprNode
from prover.proof import ProofGraph


@dataclass
class CoqDagResult:
    dag: ExprDAG
    graph: ProofGraph


class CoqExprBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, ExprNode] = {}
        self._counter = 0

    def build(self, expr: Any) -> str:
        if isinstance(expr, str):
            return self._new_const(expr)
        if isinstance(expr, list) and not expr:
            return self._new_const("empty")
        if not isinstance(expr, list):
            return self._new_const(str(expr))

        head = expr[0]
        if not isinstance(head, str):
            return self._apply_generic(head, expr[1:])
        if head == "Rel" and len(expr) >= 2:
            return self._new_node(
                kind="bvar",
                de_bruijn_idx=_as_int(expr[1]),
            )
        if head == "Var" and len(expr) >= 2:
            return self._new_node(
                kind="fvar",
                fvar_id=_as_str(expr[1]),
            )
        if head in {"Const", "Ind", "Construct"} and len(expr) >= 2:
            return self._new_node(
                kind="const",
                name=_coq_name(expr[1]),
            )
        if head == "Sort" and len(expr) >= 2:
            return self._new_node(
                kind="sort",
                level_val=_as_str(expr[1]),
            )
        if head == "Lambda" and len(expr) >= 4:
            name = _coq_name(expr[1])
            ty = self.build(expr[2])
            body = self.build(expr[3])
            return self._new_node(
                kind="lam",
                binder_name=name,
                binder_type=ty,
                body=body,
            )
        if head == "Prod" and len(expr) >= 4:
            name = _coq_name(expr[1])
            ty = self.build(expr[2])
            body = self.build(expr[3])
            return self._new_node(
                kind="forallE",
                binder_name=name,
                binder_type=ty,
                body=body,
            )
        if head == "LetIn" and len(expr) >= 5:
            name = _coq_name(expr[1])
            value = self.build(expr[2])
            ty = self.build(expr[3])
            body = self.build(expr[4])
            return self._new_node(
                kind="letE",
                binder_name=name,
                binder_type=ty,
                body=body,
                value=value,
            )
        if head == "App" and len(expr) >= 3:
            fn = self.build(expr[1])
            args = expr[2]
            if isinstance(args, list):
                for arg in args:
                    fn = self._new_app(fn, self.build(arg))
                return fn
            for arg in expr[2:]:
                fn = self._new_app(fn, self.build(arg))
            return fn

        return self._apply_generic(head, expr[1:])

    def _apply_generic(self, head: Any, args: list[Any]) -> str:
        fn = self._new_const(_coq_name(head))
        for arg in args:
            fn = self._new_app(fn, self.build(arg))
        return fn

    def _new_const(self, name: str) -> str:
        return self._new_node(kind="const", name=name)

    def _new_app(self, fn: str, arg: str) -> str:
        return self._new_node(kind="app", fn=fn, arg=arg)

    def _new_node(self, **fields: Any) -> str:
        node_id = f"n{self._counter}"
        self._counter += 1
        self.nodes[node_id] = ExprNode(kind=fields.pop("kind"), **fields)
        return node_id


def coq_constr_to_dag(expr: Any) -> ExprDAG:
    builder = CoqExprBuilder()
    root_id = builder.build(expr)
    return ExprDAG(root_id=root_id, nodes=builder.nodes)


def proof_graph_from_dag(dag: ExprDAG) -> ProofGraph:
    graph = ProofGraph.for_proof_term_dag(backend="coq", provenance="proof_term")
    node_hashes = _compute_node_hashes(dag)
    depths = _compute_node_depths(dag)
    for node_id, node in dag.nodes.items():
        node_attrs: dict[str, Any] = {
            "node_kind": node.kind,
        }
        if node.name:
            node_attrs["const_name"] = node.name
        if node.binder_name:
            node_attrs["binder_name"] = node.binder_name
        if node.binder_info:
            node_attrs["binder_info"] = node.binder_info
        if node.fvar_id:
            node_attrs["fvar_id"] = node.fvar_id
        if node.de_bruijn_idx is not None:
            node_attrs["de_bruijn_idx"] = node.de_bruijn_idx
        if node.lit_val:
            node_attrs["lit_val"] = node.lit_val
        if node.struct_name:
            node_attrs["struct_name"] = node.struct_name
        if node.proj_idx is not None:
            node_attrs["proj_idx"] = node.proj_idx
        if node.level_val:
            node_attrs["level_val"] = node.level_val
        graph.add_node(
            node_id,
            goal_type=node.kind,
            depth=depths.get(node_id, 0),
            goal_sig=node_hashes.get(node_id),
            **node_attrs,
        )
    for node_id, node in dag.nodes.items():
        for relation, child in _iter_children(node):
            graph.graph.add_edge(
                node_id,
                child,
                tactic=relation,
                tactic_norm=relation,
                edge_role=relation,
                action_kind="term_constructor",
            )
    return graph


def _iter_children(node: ExprNode) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if node.fn:
        pairs.append(("fn", node.fn))
    if node.arg:
        pairs.append(("arg", node.arg))
    if node.binder_type:
        pairs.append(("binder_type", node.binder_type))
    if node.body:
        pairs.append(("body", node.body))
    if node.value:
        pairs.append(("value", node.value))
    if node.proj_expr:
        pairs.append(("proj_expr", node.proj_expr))
    return pairs


def _compute_node_hashes(dag: ExprDAG) -> dict[str, str]:
    cache: dict[str, str] = {}

    def visit(node_id: str) -> str:
        if node_id in cache:
            return cache[node_id]
        node = dag.nodes[node_id]
        parts = [node.canonical_repr()]
        for _, child in _iter_children(node):
            parts.append(visit(child))
        digest = _hash_text("|".join(parts))
        cache[node_id] = digest
        return digest

    for node_id in dag.nodes:
        visit(node_id)
    return cache


def _compute_node_depths(dag: ExprDAG) -> dict[str, int]:
    depths: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id in depths:
            return depths[node_id]
        node = dag.nodes[node_id]
        children = [child for _, child in _iter_children(node)]
        if not children:
            depths[node_id] = 0
        else:
            depths[node_id] = 1 + max(visit(child) for child in children)
        return depths[node_id]

    for node_id in dag.nodes:
        visit(node_id)
    return depths


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _coq_name(expr: Any) -> str:
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list):
        if not expr:
            return "empty"
        if all(isinstance(e, str) for e in expr):
            return ".".join(expr)
        return _coq_name(expr[0])
    return str(expr)


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_str(value: Any) -> str:
    return sexpr_to_string(value)
