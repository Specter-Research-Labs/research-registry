from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from atp.proof_objects import ProofObjectEdge, ProofObjectGraph, ProofObjectNode


@dataclass(frozen=True)
class Z3ProofNode:
    node_id: str
    rule: str
    children: list[str]
    payload: Any | None = None


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    buf: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string
            buf.append(ch)
            i += 1
            continue
        if not in_string and ch in {"(", ")"}:
            if buf:
                tokens.append("".join(buf).strip())
                buf = []
            tokens.append(ch)
            i += 1
            continue
        if not in_string and ch.isspace():
            if buf:
                tokens.append("".join(buf).strip())
                buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        tokens.append("".join(buf).strip())
    return [t for t in tokens if t]


def parse_sexpr(text: str) -> Any:
    tokens = _tokenize(text)
    if not tokens:
        raise ValueError("Empty proof expression")
    stack: list[list[Any]] = []
    root: Any | None = None
    for token in tokens:
        if token == "(":
            stack.append([])
            continue
        if token == ")":
            if not stack:
                raise ValueError("Unbalanced parentheses in s-expression")
            expr = stack.pop()
            if stack:
                stack[-1].append(expr)
            else:
                if root is not None:
                    raise ValueError("Multiple top-level s-expressions")
                root = expr
            continue
        if stack:
            stack[-1].append(token)
        else:
            if root is not None:
                raise ValueError("Multiple top-level s-expressions")
            root = token
    if stack:
        raise ValueError("Unbalanced parentheses in s-expression")
    if root is None:
        raise ValueError("Empty proof expression")
    return root


def extract_proof_expr(expr: Any) -> Any:
    if isinstance(expr, list) and expr and expr[0] == "proof":
        return expr[1] if len(expr) > 1 else []
    return expr


def _expr_to_string(expr: Any) -> str:
    if not isinstance(expr, list):
        return str(expr)
    result: dict[int, str] = {}
    stack: list[tuple[Any, int]] = [(expr, 0)]
    while stack:
        node, state = stack.pop()
        if not isinstance(node, list):
            continue
        node_id = id(node)
        if state == 0:
            if node_id in result:
                continue
            stack.append((node, 1))
            for child in reversed(node):
                if isinstance(child, list) and id(child) not in result:
                    stack.append((child, 0))
        else:
            parts: list[str] = []
            for child in node:
                if isinstance(child, list):
                    parts.append(result[id(child)])
                else:
                    parts.append(str(child))
            result[node_id] = "(" + " ".join(parts) + ")"
    return result[id(expr)]


def _assign_depths(children_map: dict[str, list[str]]) -> dict[str, int]:
    depths: dict[str, int] = {}
    visiting: set[str] = set()

    for node_id in children_map:
        stack: list[tuple[str, int]] = [(node_id, 0)]
        while stack:
            current, state = stack.pop()
            if state == 0:
                if current in depths:
                    continue
                if current in visiting:
                    raise ValueError(f"Cycle detected in Z3 proof graph at {current}")
                visiting.add(current)
                stack.append((current, 1))
                for child in children_map.get(current, []):
                    if child not in depths:
                        stack.append((child, 0))
            else:
                visiting.discard(current)
                children = children_map.get(current, [])
                if not children:
                    depths[current] = 0
                else:
                    depths[current] = 1 + max(depths[child] for child in children)
    return depths


def proof_to_graph(expr: Any) -> ProofObjectGraph:
    env: dict[str, str] = {}
    nodes: dict[str, Z3ProofNode] = {}

    def ensure_node(rule: str, children: list[str], payload: Any | None) -> str:
        node_repr = _expr_to_string(payload if payload is not None else [rule] + children)
        node_id = _hash_text(node_repr)
        if node_id not in nodes:
            nodes[node_id] = Z3ProofNode(
                node_id=node_id,
                rule=rule,
                children=children,
                payload=payload,
            )
        return node_id

    def build(subexpr: Any) -> str:
        result_stack: list[str] = []
        tasks: list[tuple[str, Any]] = [("eval", subexpr)]
        while tasks:
            task, payload = tasks.pop()
            if task == "eval":
                expr = payload
                if isinstance(expr, str):
                    if expr in env:
                        result_stack.append(env[expr])
                    else:
                        result_stack.append(ensure_node(rule="atom", children=[], payload=expr))
                    continue
                if not isinstance(expr, list):
                    result_stack.append(ensure_node(rule="atom", children=[], payload=expr))
                    continue
                if not expr:
                    result_stack.append(ensure_node(rule="empty", children=[], payload=None))
                    continue
                head = expr[0]
                if head == "let" and len(expr) >= 3:
                    bindings = expr[1]
                    body = expr[2]
                    tasks.append(("let_body", body))
                    if isinstance(bindings, list):
                        for binding in reversed(bindings):
                            if isinstance(binding, list) and len(binding) == 2:
                                name = binding[0]
                                value = binding[1]
                                tasks.append(("let_assign", name))
                                tasks.append(("eval", value))
                    continue
                parts = expr[1:]
                tasks.append(("build_list", (expr, len(parts))))
                for part in reversed(parts):
                    if isinstance(part, str):
                        if part in env:
                            tasks.append(("push_node", env[part]))
                        continue
                    if isinstance(part, list):
                        tasks.append(("eval", part))
            elif task == "push_node":
                result_stack.append(payload)
            elif task == "let_assign":
                if not result_stack:
                    raise ValueError("Missing let binding value")
                env[payload] = result_stack.pop()
            elif task == "let_body":
                tasks.append(("eval", payload))
            elif task == "build_list":
                expr, count = payload
                if count:
                    children = result_stack[-count:]
                    del result_stack[-count:]
                else:
                    children = []
                rule = expr[0] if isinstance(expr[0], str) else "proof"
                node_id = ensure_node(rule=rule, children=list(children), payload=expr)
                result_stack.append(node_id)
            else:
                raise ValueError(f"Unknown task: {task}")
        if len(result_stack) != 1:
            raise ValueError("Malformed proof expression")
        return result_stack[0]

    root_id = build(expr)
    children_map = {node_id: node.children for node_id, node in nodes.items()}
    depths = _assign_depths(children_map)

    proof_nodes: list[ProofObjectNode] = []
    proof_edges: list[ProofObjectEdge] = []
    order = 0
    for node_id, node in nodes.items():
        proof_nodes.append(
            ProofObjectNode(
                node_id=node_id,
                goal_sig=_hash_text(_expr_to_string(node.payload)),
                goal_type=node.rule,
                depth=depths.get(node_id, 0),
                attrs={"rule": node.rule},
            )
        )
        for child_id in node.children:
            order += 1
            proof_edges.append(
                ProofObjectEdge(
                    source=child_id,
                    target=node_id,
                    rule=node.rule,
                    order=order,
                )
            )

    if root_id not in nodes:
        raise ValueError("Proof root missing from graph")

    return ProofObjectGraph(nodes=proof_nodes, edges=proof_edges)


def extract_proof_block(output: str) -> str | None:
    lines = output.splitlines()
    capture = False
    buf: list[str] = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not capture and stripped.startswith("("):
            capture = True
        if capture:
            buf.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                return "\n".join(buf).strip()
    return None
