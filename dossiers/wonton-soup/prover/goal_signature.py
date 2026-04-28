from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leantree.core.lean import LeanGoal


@dataclass
class GoalSignatureStats:
    ast_missing: int = 0


@dataclass
class GoalSignatureConfig:
    scheme: str
    stats: GoalSignatureStats = field(default_factory=GoalSignatureStats)


def goal_signature(goal: LeanGoal, config: GoalSignatureConfig) -> str:
    hyp_types = [h.type for h in goal.hypotheses]
    hyp_exprs = [h.type_expr for h in goal.hypotheses]
    return compute_goal_signature(
        type_str=goal.type,
        type_expr=goal.type_expr,
        hyp_types=hyp_types,
        hyp_exprs=hyp_exprs,
        config=config,
    )


def compute_goal_signature(
    type_str: str,
    type_expr: dict | None,
    hyp_types: list[str],
    hyp_exprs: list[dict | None],
    config: GoalSignatureConfig,
) -> str:
    if config.scheme == "text":
        return _text_signature(type_str, hyp_types)
    if config.scheme != "ast":
        raise ValueError(f"Unknown goal signature scheme: {config.scheme}")

    if type_expr is None or any(h is None for h in hyp_exprs):
        config.stats.ast_missing += 1
        raise ValueError(
            "Missing AST for goal signature; use --goal-sig text if ASTs are unavailable"
        )

    goal_hash = _hash_normalized_ast(type_expr, strict=False)
    hyp_hashes = sorted(
        _hash_normalized_ast(h, strict=False) for h in hyp_exprs if h is not None
    )
    combined = goal_hash + "|" + "|".join(hyp_hashes)
    return hashlib.sha1(combined.encode()).hexdigest()[:12]


def compute_goal_signature_strict(
    type_str: str,
    type_expr: dict | None,
    hyp_types: list[str],
    hyp_exprs: list[dict | None],
    config: GoalSignatureConfig,
) -> str:
    if config.scheme == "text":
        return _text_signature(type_str, hyp_types)
    if config.scheme != "ast":
        raise ValueError(f"Unknown goal signature scheme: {config.scheme}")

    if type_expr is None or any(h is None for h in hyp_exprs):
        config.stats.ast_missing += 1
        raise ValueError(
            "Missing AST for goal signature; use --goal-sig text if ASTs are unavailable"
        )

    goal_hash = _hash_normalized_ast(type_expr, strict=True)
    hyp_hashes = [_hash_normalized_ast(h, strict=True) for h in hyp_exprs if h is not None]
    combined = goal_hash + "|" + "|".join(hyp_hashes)
    return hashlib.sha1(combined.encode()).hexdigest()[:12]


def _text_signature(type_str: str, hyp_types: list[str]) -> str:
    def normalize_str(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    parts = [normalize_str(type_str)]
    for hyp in hyp_types:
        parts.append(normalize_str(hyp))
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _hash_normalized_ast(dag: dict, strict: bool) -> str:
    if strict:
        canonical = _canonicalize_dag(dag, strict=True)
    else:
        dag = _normalize_commutative_recursive(dag)
        canonical = _canonicalize_dag(dag, strict=False)
    return hashlib.sha1(canonical.encode()).hexdigest()[:16]


def _validate_dag(dag: dict) -> tuple[str, dict[str, dict]]:
    if "rootId" not in dag:
        raise ValueError("Goal signature AST is missing rootId")
    if "nodes" not in dag:
        raise ValueError("Goal signature AST is missing nodes")
    nodes_list = dag["nodes"]
    if not isinstance(nodes_list, list):
        raise ValueError("Goal signature AST nodes must be a list")

    nodes: dict[str, dict] = {}
    for item in nodes_list:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("Goal signature AST nodes must be (id, node) pairs")
        node_id, node = item
        if not isinstance(node, dict):
            raise ValueError(f"Goal signature AST node {node_id} is not a dict")
        if "kind" not in node:
            raise ValueError(f"Goal signature AST node {node_id} is missing kind")
        nodes[node_id] = node

    root_id = dag["rootId"]
    if root_id not in nodes:
        raise ValueError(f"Goal signature AST rootId {root_id} missing from nodes")
    return root_id, nodes


def _normalize_commutative_recursive(dag: dict) -> dict:
    root_id, original_nodes = _validate_dag(dag)
    nodes = {nid: dict(node) for nid, node in original_nodes.items()}
    visited: set[str] = set()
    _normalize_node_recursive(nodes, root_id, visited)
    return {"rootId": root_id, "nodes": list(nodes.items())}


def _normalize_node_recursive(nodes: dict[str, dict], node_id: str, visited: set[str]) -> None:
    if node_id in visited:
        return
    visited.add(node_id)

    node = nodes.get(node_id)
    if node is None:
        raise ValueError(f"Goal signature AST missing node {node_id}")

    kind = node.get("kind")
    if kind is None:
        raise ValueError(f"Goal signature AST node {node_id} missing kind")
    if kind == "app":
        fn_id = node.get("fn")
        arg_id = node.get("arg")
        if fn_id is None or arg_id is None:
            raise ValueError(f"app node {node_id} missing fn or arg")
        _normalize_node_recursive(nodes, fn_id, visited)
        _normalize_node_recursive(nodes, arg_id, visited)
        _try_normalize_commutative(nodes, node_id)
    elif kind in ("lam", "forallE"):
        ty_id = node.get("binderType")
        body_id = node.get("body")
        if ty_id is None or body_id is None:
            raise ValueError(f"{kind} node {node_id} missing binderType or body")
        _normalize_node_recursive(nodes, ty_id, visited)
        _normalize_node_recursive(nodes, body_id, visited)
    elif kind == "letE":
        ty_id = node.get("binderType")
        val_id = node.get("value")
        body_id = node.get("body")
        if ty_id is None or val_id is None or body_id is None:
            raise ValueError(f"letE node {node_id} missing binderType, value, or body")
        _normalize_node_recursive(nodes, ty_id, visited)
        _normalize_node_recursive(nodes, val_id, visited)
        _normalize_node_recursive(nodes, body_id, visited)
    elif kind == "proj":
        proj_id = node.get("projExpr")
        if proj_id is None:
            raise ValueError(f"proj node {node_id} missing projExpr")
        _normalize_node_recursive(nodes, proj_id, visited)


def _try_normalize_commutative(nodes: dict[str, dict], node_id: str) -> None:
    node = nodes.get(node_id)
    if node is None:
        raise ValueError(f"Goal signature AST missing node {node_id}")
    if node.get("kind") != "app":
        return

    fn_id = node.get("fn")
    arg2_id = node.get("arg")
    if fn_id is None or arg2_id is None:
        raise ValueError(f"app node {node_id} missing fn or arg")
    fn = nodes.get(fn_id)
    if fn is None:
        raise ValueError(f"Goal signature AST missing node {fn_id}")
    if fn.get("kind") != "app":
        return

    const_id = fn.get("fn")
    arg1_id = fn.get("arg")
    if const_id is None or arg1_id is None:
        raise ValueError(f"app node {fn_id} missing fn or arg")
    const_node = nodes.get(const_id)
    if const_node is None:
        raise ValueError(f"Goal signature AST missing node {const_id}")
    if const_node.get("kind") != "const":
        return

    name = const_node.get("name")
    if not name:
        raise ValueError(f"Const node {const_id} missing name")
    if name not in ("And", "Or", "Iff"):
        return

    h1 = _hash_subtree(nodes, arg1_id)
    h2 = _hash_subtree(nodes, arg2_id)

    if h1 <= h2:
        return

    nodes[fn_id] = {**fn, "arg": arg2_id}
    nodes[node_id] = {**node, "arg": arg1_id}


def _hash_subtree(nodes: dict[str, dict], node_id: str) -> str:
    canonical = _canonicalize_subtree(nodes, node_id)
    return hashlib.sha1(canonical.encode()).hexdigest()[:8]


def _canonicalize_subtree(nodes: dict[str, dict], node_id: str) -> str:
    node = nodes.get(node_id)
    if node is None:
        raise ValueError(f"Goal signature AST missing node {node_id}")
    kind = node.get("kind")
    if kind is None:
        raise ValueError(f"Goal signature AST node {node_id} missing kind")

    if kind == "const":
        name = node.get("name")
        if not name:
            raise ValueError(f"Const node {node_id} missing name")
        return f"const:{name}"
    if kind == "bvar":
        if "deBruijnIdx" not in node:
            raise ValueError(f"bvar node {node_id} missing deBruijnIdx")
        return f"bvar:{node['deBruijnIdx']}"
    if kind == "fvar":
        return "fvar"
    if kind == "mvar":
        return "mvar"
    if kind == "sort":
        if "levelVal" not in node:
            raise ValueError(f"sort node {node_id} missing levelVal")
        return f"sort:{node['levelVal']}"
    if kind == "app":
        fn_id = node.get("fn")
        arg_id = node.get("arg")
        if fn_id is None or arg_id is None:
            raise ValueError(f"app node {node_id} missing fn or arg")
        fn = _canonicalize_subtree(nodes, fn_id)
        arg = _canonicalize_subtree(nodes, arg_id)
        return f"app({fn},{arg})"
    if kind == "lam":
        ty_id = node.get("binderType")
        body_id = node.get("body")
        if ty_id is None or body_id is None:
            raise ValueError(f"lam node {node_id} missing binderType or body")
        ty = _canonicalize_subtree(nodes, ty_id)
        body = _canonicalize_subtree(nodes, body_id)
        return f"lam({ty},{body})"
    if kind == "forallE":
        ty_id = node.get("binderType")
        body_id = node.get("body")
        if ty_id is None or body_id is None:
            raise ValueError(f"forallE node {node_id} missing binderType or body")
        ty = _canonicalize_subtree(nodes, ty_id)
        body = _canonicalize_subtree(nodes, body_id)
        return f"forall({ty},{body})"
    if kind == "letE":
        ty_id = node.get("binderType")
        val_id = node.get("value")
        body_id = node.get("body")
        if ty_id is None or val_id is None or body_id is None:
            raise ValueError(f"letE node {node_id} missing binderType, value, or body")
        ty = _canonicalize_subtree(nodes, ty_id)
        val = _canonicalize_subtree(nodes, val_id)
        body = _canonicalize_subtree(nodes, body_id)
        return f"let({ty},{val},{body})"
    if kind == "lit":
        if "litVal" not in node:
            raise ValueError(f"lit node {node_id} missing litVal")
        return f"lit:{node['litVal']}"
    if kind == "proj":
        expr_id = node.get("projExpr")
        if expr_id is None:
            raise ValueError(f"proj node {node_id} missing projExpr")
        struct_name = node.get("structName")
        if not struct_name:
            raise ValueError(f"proj node {node_id} missing structName")
        if "projIdx" not in node:
            raise ValueError(f"proj node {node_id} missing projIdx")
        expr = _canonicalize_subtree(nodes, expr_id)
        return f"proj:{struct_name}:{node['projIdx']}({expr})"
    raise ValueError(f"Unknown node kind: {kind}")


def _canonicalize_subtree_strict(nodes: dict[str, dict], node_id: str) -> str:
    node = nodes.get(node_id)
    if node is None:
        raise ValueError(f"Goal signature AST missing node {node_id}")
    kind = node.get("kind")
    if kind is None:
        raise ValueError(f"Goal signature AST node {node_id} missing kind")

    if kind == "const":
        name = node.get("name")
        if not name:
            raise ValueError(f"Const node {node_id} missing name")
        return f"const:{name}"
    if kind == "bvar":
        if "deBruijnIdx" not in node:
            raise ValueError(f"bvar node {node_id} missing deBruijnIdx")
        return f"bvar:{node['deBruijnIdx']}"
    if kind == "fvar":
        fvar_id = node.get("fvarId")
        if not fvar_id:
            raise ValueError(f"fvar node {node_id} missing fvarId")
        return f"fvar:{fvar_id}"
    if kind == "mvar":
        name = node.get("name")
        if not name:
            raise ValueError(f"mvar node {node_id} missing name")
        return f"mvar:{name}"
    if kind == "sort":
        if "levelVal" not in node:
            raise ValueError(f"sort node {node_id} missing levelVal")
        return f"sort:{node['levelVal']}"
    if kind == "app":
        fn_id = node.get("fn")
        arg_id = node.get("arg")
        if fn_id is None or arg_id is None:
            raise ValueError(f"app node {node_id} missing fn or arg")
        fn = _canonicalize_subtree_strict(nodes, fn_id)
        arg = _canonicalize_subtree_strict(nodes, arg_id)
        return f"app({fn},{arg})"
    if kind == "lam":
        ty_id = node.get("binderType")
        body_id = node.get("body")
        if ty_id is None or body_id is None:
            raise ValueError(f"lam node {node_id} missing binderType or body")
        ty = _canonicalize_subtree_strict(nodes, ty_id)
        body = _canonicalize_subtree_strict(nodes, body_id)
        return f"lam({ty},{body})"
    if kind == "forallE":
        ty_id = node.get("binderType")
        body_id = node.get("body")
        if ty_id is None or body_id is None:
            raise ValueError(f"forallE node {node_id} missing binderType or body")
        ty = _canonicalize_subtree_strict(nodes, ty_id)
        body = _canonicalize_subtree_strict(nodes, body_id)
        return f"forall({ty},{body})"
    if kind == "letE":
        ty_id = node.get("binderType")
        val_id = node.get("value")
        body_id = node.get("body")
        if ty_id is None or val_id is None or body_id is None:
            raise ValueError(f"letE node {node_id} missing binderType, value, or body")
        ty = _canonicalize_subtree_strict(nodes, ty_id)
        val = _canonicalize_subtree_strict(nodes, val_id)
        body = _canonicalize_subtree_strict(nodes, body_id)
        return f"let({ty},{val},{body})"
    if kind == "lit":
        if "litVal" not in node:
            raise ValueError(f"lit node {node_id} missing litVal")
        return f"lit:{node['litVal']}"
    if kind == "proj":
        expr_id = node.get("projExpr")
        if expr_id is None:
            raise ValueError(f"proj node {node_id} missing projExpr")
        struct_name = node.get("structName")
        if not struct_name:
            raise ValueError(f"proj node {node_id} missing structName")
        if "projIdx" not in node:
            raise ValueError(f"proj node {node_id} missing projIdx")
        expr = _canonicalize_subtree_strict(nodes, expr_id)
        return f"proj:{struct_name}:{node['projIdx']}({expr})"
    raise ValueError(f"Unknown node kind: {kind}")


def _canonicalize_dag(dag: dict, strict: bool) -> str:
    root_id, nodes = _validate_dag(dag)
    if strict:
        return _canonicalize_subtree_strict(nodes, root_id)
    return _canonicalize_subtree(nodes, root_id)


def validate_goal_ast(dag: dict) -> tuple[str, dict[str, dict]]:
    """Validate the Lean expression AST payload used for goal signatures.

    Returns the rootId and a nodes-by-id mapping.
    """

    return _validate_dag(dag)


def normalize_commutative_goal_ast(dag: dict) -> dict:
    """Normalize commutative operators (And/Or/Iff) by sorting arguments."""

    return _normalize_commutative_recursive(dag)


def hash_normalized_goal_ast(dag: dict, *, strict: bool = False) -> str:
    """Hash a goal AST after canonicalization (and commutative normalization when non-strict)."""

    return _hash_normalized_ast(dag, strict=strict)
