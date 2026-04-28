from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Iterable

from analysis.logs import read_json, read_json_gz
from prover.goal_features import FEATURE_DIM, extract_features


def open_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix == ".gz":
        f = gzip.open(path, "rt")
    else:
        f = path.open("rt")
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj


def load_goal_cache(run_dir: Path) -> dict[str, Any]:
    gz = run_dir / "goal_cache.json.gz"
    plain = run_dir / "goal_cache.json"
    if gz.exists():
        data = read_json_gz(gz)
    elif plain.exists():
        data = read_json(plain)
    else:
        raise FileNotFoundError(f"No goal_cache.json(.gz) in {run_dir}")
    if not isinstance(data, dict):
        raise ValueError("goal_cache must be a dict")
    return data


def build_sig_features(goal_cache: dict[str, Any]) -> dict[str, list[float]]:
    entries = goal_cache.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError("goal_cache.entries must be a dict")
    out: dict[str, list[float]] = {}
    for sig, entry in entries.items():
        if not isinstance(sig, str) or not isinstance(entry, dict):
            continue
        type_expr = entry.get("type_expr")
        hyp_exprs = entry.get("hyp_exprs", [])
        hyp_count = len(hyp_exprs) if isinstance(hyp_exprs, list) else 0
        feats = extract_features(type_expr if isinstance(type_expr, dict) else None, hyp_count)
        out[sig] = [float(x) for x in feats.tolist()]
    return out


def features_for_sig(
    sig: str | None,
    sig_features: dict[str, list[float]],
) -> list[float]:
    if sig is None:
        return [0.0] * FEATURE_DIM
    return sig_features.get(sig, [0.0] * FEATURE_DIM)


def committed_tactic_by_mvar(tree: dict[str, Any]) -> dict[str, str]:
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("mcts_tree.nodes must be a dict")
    committed: dict[str, str] = {}
    for mvar_id, node in nodes.items():
        if not isinstance(mvar_id, str) or not isinstance(node, dict):
            continue
        children = node.get("children", {})
        if not isinstance(children, dict) or not children:
            continue
        keys = list(children.keys())
        if len(keys) != 1:
            raise ValueError(f"Expected 1 committed tactic for {mvar_id}, got {len(keys)}")
        tactic = keys[0]
        if not isinstance(tactic, str):
            continue
        committed[mvar_id] = tactic
    return committed

