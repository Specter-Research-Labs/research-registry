from __future__ import annotations

from typing import Any


def tokenize_sexpr(text: str) -> list[str]:
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
    tokens = tokenize_sexpr(text)
    if not tokens:
        raise ValueError("Empty s-expression")
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
        raise ValueError("Empty s-expression")
    return root


def sexpr_to_string(expr: Any) -> str:
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
