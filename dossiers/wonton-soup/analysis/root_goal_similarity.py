from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from analysis.attractors import cluster_proof_structures
from prover.goal_cache import GoalCache
from prover.goal_distance import GoalSigTedDistance
from prover.tree_edit_distance import OrderedTree, tree_edit_distance

DISTANCE_THRESHOLD = 0.2
SAMPLE_SEED = "root_goal_similarity:v1"


def _tree_size(tree: OrderedTree) -> int:
    size = 0
    stack = [tree]
    while stack:
        node = stack.pop()
        size += 1
        stack.extend(node.children)
    return size


def _normalized_distance(
    a: OrderedTree, b: OrderedTree, size_a: int, size_b: int
) -> float:
    denom = size_a + size_b
    return tree_edit_distance(a, b) / denom if denom else 0.0


def _select_sample(
    theorem_names: list[str], sample_size: int
) -> tuple[list[str], dict[str, Any]]:
    if sample_size >= len(theorem_names):
        return sorted(theorem_names), {"sample_strategy": "all"}
    ranked: list[tuple[str, str]] = []
    for name in theorem_names:
        digest = hashlib.sha256((SAMPLE_SEED + name).encode("utf-8")).hexdigest()
        ranked.append((digest, name))
    ranked.sort()
    sample = sorted(name for _, name in ranked[:sample_size])
    return sample, {"sample_strategy": "sha256", "sample_seed": SAMPLE_SEED}


def _resolve_mode(
    mode: str,
    theorem_count: int,
    *,
    max_theorems: int,
    max_knn_theorems: int,
) -> str:
    if mode == "auto":
        if theorem_count <= max_theorems:
            return "full"
        if theorem_count <= max_knn_theorems:
            return "knn"
        return "sample"
    if mode not in {"full", "knn", "sample"}:
        raise ValueError(f"unknown root_goal_similarity mode: {mode}")
    return mode


def _load_summary(log_dir: Path) -> dict[str, Any]:
    path = log_dir / "summary.json.gz"
    if not path.exists():
        raise FileNotFoundError(f"Missing summary.json.gz: {path}")
    with gzip.open(path, "rt") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("summary.json.gz must contain a JSON object")
    return data


def _extract_root_goal_sigs(
    theorem_dir: Path, theorem_entry: dict[str, Any]
) -> tuple[list[str], str | None]:
    wild = theorem_entry.get("wild_type", {})
    wild_metrics = wild.get("metrics", {}) if isinstance(wild, dict) else {}
    root_sigs = wild_metrics.get("root_goal_sigs")
    if isinstance(root_sigs, list) and all(isinstance(s, str) for s in root_sigs):
        return root_sigs, None

    # Back-compat: recover from wild_type_graph.json if the summary predates root_goal_sigs.
    graph_path = theorem_dir / "wild_type_graph.json"
    if not graph_path.exists():
        return [], "missing_wild_type_graph"
    try:
        graph = json.loads(graph_path.read_text())
    except Exception:
        return [], "invalid_wild_type_graph_json"
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return [], "invalid_wild_type_graph_schema"

    in_deg: dict[str, int] = {}
    goal_sig_by_id: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        goal_sig = node.get("goal_sig")
        if isinstance(node_id, str):
            in_deg.setdefault(node_id, 0)
            if isinstance(goal_sig, str):
                goal_sig_by_id[node_id] = goal_sig

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if isinstance(tgt, str):
            in_deg[tgt] = in_deg.get(tgt, 0) + 1
        if isinstance(src, str):
            in_deg.setdefault(src, 0)

    roots = sorted(n for n, d in in_deg.items() if d == 0)
    root_sigs_out = [goal_sig_by_id[r] for r in roots if r in goal_sig_by_id]
    return root_sigs_out, None


def compute_root_goal_similarity(
    log_dir: Path,
    *,
    max_theorems: int = 400,
    max_knn_theorems: int = 2000,
    knn_k: int = 12,
    knn_sample_size: int = 200,
    sample_size: int = 400,
    mode: str = "auto",
) -> dict[str, Any]:
    """Compute a cross-theorem similarity matrix over root goals (statement ASTs).

    Modes:
    - full: dense NxN matrix
    - knn: sparse kNN matrix against a deterministic sample
    - sample: dense matrix over a deterministic sample subset
    """

    summary = _load_summary(log_dir)
    sig_scheme = summary.get("goal_sig_scheme")
    if sig_scheme != "ast":
        return {
            "schema_version": 1,
            "valid": False,
            "validity_notes": [
                "root_goal_similarity requires goal_sig_scheme=ast (run with --goal-sig ast)"
            ],
        }

    goal_cache = GoalCache.load(log_dir / "goal_cache.json")
    dist = GoalSigTedDistance(goal_cache)

    theorems_raw = summary.get("theorems", [])
    if not isinstance(theorems_raw, list):
        raise ValueError("summary.theorems must be a list")

    theorem_names: list[str] = []
    trees: dict[str, OrderedTree] = {}
    invalid: dict[str, str] = {}

    for entry in theorems_raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        theorem_dir = log_dir / name
        root_sigs, root_sig_err = _extract_root_goal_sigs(theorem_dir, entry)
        if not root_sigs:
            invalid[name] = root_sig_err or "missing_root_goal_sigs"
            continue

        root_sigs_sorted = sorted(set(root_sigs))
        children: list[OrderedTree] = []
        ok = True
        for sig in root_sigs_sorted:
            t = dist.tree(sig)
            if t is None:
                ok = False
                invalid[name] = f"invalid_root_goal_sig:{sig}"
                break
            children.append(t)
        if not ok:
            continue

        theorem_names.append(name)
        trees[name] = OrderedTree("root_goals", tuple(children))

    theorem_names.sort()

    if not theorem_names:
        return {
            "schema_version": 1,
            "valid": True,
            "validity_notes": [],
            "goal_sig_scheme": sig_scheme,
            "distance_metric": "normalized_goal_ast_ted",
            "distance_threshold": DISTANCE_THRESHOLD,
            "matrix_mode": "full",
            "matrix_kind": "dense",
            "theorem_count_total": 0,
            "theorems": [],
            "distance_matrix": {},
            "clusters": None,
        }

    mode_used = _resolve_mode(
        mode,
        len(theorem_names),
        max_theorems=max_theorems,
        max_knn_theorems=max_knn_theorems,
    )

    tree_sizes = {name: _tree_size(tree) for name, tree in trees.items()}

    sample_meta: dict[str, Any] = {}
    sample_names: list[str] = []
    if mode_used in {"knn", "sample"}:
        sample_size_eff = knn_sample_size if mode_used == "knn" else sample_size
        if sample_size_eff < 1:
            raise ValueError("sample_size must be >= 1")
        sample_names, sample_meta = _select_sample(theorem_names, sample_size_eff)

    if mode_used == "sample":
        names_for_matrix = sample_names
    else:
        names_for_matrix = theorem_names

    matrix: dict[str, dict[str, float | None]] = {n: {} for n in names_for_matrix}

    if mode_used == "full":
        for i, a in enumerate(names_for_matrix):
            matrix[a][a] = 0.0
            for j in range(i + 1, len(names_for_matrix)):
                b = names_for_matrix[j]
                value = _normalized_distance(
                    trees[a], trees[b], tree_sizes[a], tree_sizes[b]
                )
                matrix[a][b] = value
                matrix[b][a] = value
    elif mode_used == "sample":
        for i, a in enumerate(names_for_matrix):
            matrix[a][a] = 0.0
            for j in range(i + 1, len(names_for_matrix)):
                b = names_for_matrix[j]
                value = _normalized_distance(
                    trees[a], trees[b], tree_sizes[a], tree_sizes[b]
                )
                matrix[a][b] = value
                matrix[b][a] = value
    else:
        if knn_k < 1:
            raise ValueError("knn_k must be >= 1")
        matrix = {n: {} for n in theorem_names}
        for name in theorem_names:
            matrix[name][name] = 0.0
            neighbors: list[tuple[float, str]] = []
            for sample in sample_names:
                if sample == name:
                    continue
                value = _normalized_distance(
                    trees[name], trees[sample], tree_sizes[name], tree_sizes[sample]
                )
                neighbors.append((value, sample))
            neighbors.sort(key=lambda item: (item[0], item[1]))
            for value, sample in neighbors[:knn_k]:
                matrix[name][sample] = value
                matrix[sample][name] = value

    clusters = (
        cluster_proof_structures(
            matrix,
            distance_threshold=DISTANCE_THRESHOLD,
            theorem_name="root_goal_similarity",
            missing_distance=1.0,
        ).serialize()
        if names_for_matrix
        else None
    )

    validity_notes = []
    if invalid:
        examples = list(sorted(invalid.items()))[:5]
        validity_notes.append(
            f"excluded_theorems={len(invalid)}; examples={examples}"
        )
    if dist.tree_errors:
        examples = list(sorted(dist.tree_errors.items()))[:5]
        validity_notes.append(f"goal_tree_errors={len(dist.tree_errors)}; examples={examples}")
    if mode_used != "full":
        note = f"matrix_mode={mode_used}; theorem_count={len(theorem_names)}"
        if mode_used == "knn":
            note = f"{note}; knn_k={knn_k}; knn_sample_size={len(sample_names)}"
        if mode_used == "sample":
            note = f"{note}; sample_size={len(sample_names)}"
        validity_notes.append(note)

    report = {
        "schema_version": 1,
        "valid": True,
        "validity_notes": validity_notes,
        "goal_sig_scheme": sig_scheme,
        "distance_metric": "normalized_goal_ast_ted",
        "distance_threshold": DISTANCE_THRESHOLD,
        "matrix_mode": mode_used,
        "matrix_kind": "dense" if mode_used in {"full", "sample"} else "sparse",
        "theorem_count_total": len(theorem_names),
        "theorems": names_for_matrix,
        "distance_matrix": matrix,
        "clusters": clusters,
    }
    if mode_used in {"knn", "sample"}:
        report.update(
            {
                "sample_size": len(sample_names),
                "sample_meta": sample_meta,
            }
        )
    if mode_used == "knn":
        report.update(
            {
                "knn_k": knn_k,
                "knn_sample_size": knn_sample_size,
                "max_knn_theorems": max_knn_theorems,
                "max_theorems_full": max_theorems,
            }
        )
    if mode_used == "sample":
        report.update(
            {
                "sample_size_target": sample_size,
                "max_knn_theorems": max_knn_theorems,
                "max_theorems_full": max_theorems,
            }
        )
    if mode_used == "full":
        report.update(
            {
                "max_theorems_full": max_theorems,
            }
        )
    return report
