from __future__ import annotations

import numpy as np

STRIP_PREFIXES = ["Init.", "Nat.", "Int.", "List.", "Std.", "Lean."]

FEATURE_DIM = 18


def normalize_const_name(name: str) -> str:
    for prefix in STRIP_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def count_const(dag: dict, target: str) -> int:
    count = 0
    for _, node in dag.get("nodes", []):
        if node.get("kind") == "const":
            name = normalize_const_name(node.get("name", ""))
            if name == target:
                count += 1
    return count


def count_kind(nodes: list[tuple[str, dict]], kind: str) -> int:
    return sum(1 for _, node in nodes if node.get("kind") == kind)


def extract_features(dag: dict | None, hyp_count: int) -> np.ndarray:
    if dag is None:
        return np.zeros(FEATURE_DIM, dtype=np.float32)

    nodes = dag.get("nodes", [])
    const_names = [
        normalize_const_name(n.get("name", ""))
        for _, n in nodes
        if n.get("kind") == "const"
    ]

    features = [
        count_kind(nodes, "app"),
        count_kind(nodes, "lam"),
        count_kind(nodes, "forallE"),
        count_kind(nodes, "bvar"),
        count_kind(nodes, "fvar"),
        count_kind(nodes, "letE"),
        count_kind(nodes, "lit"),
        count_kind(nodes, "const"),
        count_kind(nodes, "proj"),
        count_kind(nodes, "sort"),
        len(nodes),
        len(set(const_names)),
        count_const(dag, "And"),
        count_const(dag, "Or"),
        count_const(dag, "Exists"),
        count_const(dag, "Iff"),
        count_const(dag, "Not"),
        hyp_count,
    ]
    return np.array(features, dtype=np.float32)
