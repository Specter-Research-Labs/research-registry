from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx

from analysis.learning_common import build_sig_features, features_for_sig, load_goal_cache
from analysis.logs import iter_provider_runs, read_json, relpath_under, write_json_atomic
from prover.goal_features import FEATURE_DIM
from prover.providers.base import normalize_tactic, tactic_family

SHAPE_VERSION = 1


def _bucket(value: float, cuts: list[int]) -> int:
    v = int(value)
    for i, cut in enumerate(cuts):
        if v <= cut:
            return i
    return len(cuts)


def goal_shape_key(features: list[float]) -> str:
    if len(features) != FEATURE_DIM:
        return "shape_v1:unknown"
    and_count = int(features[12])
    or_count = int(features[13])
    exists_count = int(features[14])
    iff_count = int(features[15])
    not_count = int(features[16])
    hyp_count = int(features[17])
    node_count = int(features[10])

    h = _bucket(hyp_count, [0, 2, 5])
    s = _bucket(node_count, [20, 60, 150])

    flags = [
        f"A{1 if and_count > 0 else 0}",
        f"O{1 if or_count > 0 else 0}",
        f"E{1 if exists_count > 0 else 0}",
        f"I{1 if iff_count > 0 else 0}",
        f"N{1 if not_count > 0 else 0}",
    ]
    return f"shape_v1:H{h}:S{s}:" + "".join(flags)


@dataclass(frozen=True)
class TransitionResult:
    provider: str | None
    out_dir: Path


def _safe_mvar_to_sig(mvar_to_sig: dict[str, Any], mvar_id: str) -> str | None:
    sig = mvar_to_sig.get(mvar_id)
    return sig if isinstance(sig, str) else None


def _collect_transitions_for_tree(
    tree: dict[str, Any],
    mvar_to_sig: dict[str, Any],
    sig_features: dict[str, list[float]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("mcts_tree.nodes must be a dict")

    micro: dict[str, dict[str, dict[str, int]]] = {}
    macro: dict[str, dict[str, dict[str, int]]] = {}

    for mvar_id, node in nodes.items():
        if not isinstance(mvar_id, str) or not isinstance(node, dict):
            continue
        parent_sig = node.get("goal_sig") if isinstance(node.get("goal_sig"), str) else None
        if parent_sig is None:
            parent_sig = _safe_mvar_to_sig(mvar_to_sig, mvar_id)
        parent_shape = goal_shape_key(features_for_sig(parent_sig, sig_features))

        children = node.get("children", {})
        if not isinstance(children, dict) or not children:
            continue
        for tactic, child_mvars in children.items():
            if not isinstance(tactic, str):
                continue
            fam = tactic_family(normalize_tactic(tactic))
            if not isinstance(child_mvars, list):
                continue
            if not child_mvars:
                # Terminal expansion.
                child_shape = "__terminal__"
                child_sig = "__terminal__"
                micro.setdefault(parent_sig or "__unknown__", {}).setdefault(fam, {})
                micro[parent_sig or "__unknown__"][fam][child_sig] = (
                    micro[parent_sig or "__unknown__"][fam].get(child_sig, 0) + 1
                )
                macro.setdefault(parent_shape, {}).setdefault(fam, {})
                fam_counts = macro[parent_shape][fam]
                fam_counts[child_shape] = fam_counts.get(child_shape, 0) + 1
                continue

            for child_mvar in child_mvars:
                if not isinstance(child_mvar, str):
                    continue
                child_sig = _safe_mvar_to_sig(mvar_to_sig, child_mvar)
                child_shape = goal_shape_key(features_for_sig(child_sig, sig_features))
                micro.setdefault(parent_sig or "__unknown__", {}).setdefault(fam, {})
                key_child_sig = child_sig or "__unknown__"
                micro[parent_sig or "__unknown__"][fam][key_child_sig] = (
                    micro[parent_sig or "__unknown__"][fam].get(key_child_sig, 0) + 1
                )
                macro.setdefault(parent_shape, {}).setdefault(fam, {})
                fam_counts = macro[parent_shape][fam]
                fam_counts[child_shape] = fam_counts.get(child_shape, 0) + 1

    return micro, macro


def _normalize_macro_counts(macro: dict[str, Any]) -> dict[str, Any]:
    probs: dict[str, dict[str, dict[str, float]]] = {}
    for parent_shape, fam_map in macro.items():
        if not isinstance(parent_shape, str) or not isinstance(fam_map, dict):
            continue
        probs[parent_shape] = {}
        for fam, child_counts in fam_map.items():
            if not isinstance(fam, str) or not isinstance(child_counts, dict):
                continue
            total = sum(int(v) for v in child_counts.values() if isinstance(v, int))
            if total <= 0:
                continue
            probs[parent_shape][fam] = {
                k: (int(v) / total)
                for k, v in child_counts.items()
                if isinstance(v, int)
            }
    return probs


def _macro_sccs(macro_probs: dict[str, Any], *, min_edge_prob: float = 0.05) -> dict[str, Any]:
    g = nx.DiGraph()
    for parent_shape, fam_map in macro_probs.items():
        if not isinstance(parent_shape, str) or not isinstance(fam_map, dict):
            continue
        g.add_node(parent_shape)
        for _, child_probs in fam_map.items():
            if not isinstance(child_probs, dict):
                continue
            for child_shape, p in child_probs.items():
                if not isinstance(child_shape, str) or not isinstance(p, (int, float)):
                    continue
                if float(p) >= min_edge_prob:
                    g.add_edge(parent_shape, child_shape)
    sccs = [sorted(list(c)) for c in nx.strongly_connected_components(g) if len(c) > 1]
    sccs.sort(key=len, reverse=True)
    return {
        "min_edge_prob": min_edge_prob,
        "sccs": sccs,
        "n_sccs": len(sccs),
        "n_nodes": g.number_of_nodes(),
        "n_edges": g.number_of_edges(),
    }


def transition_analysis(
    run_dir: Path,
    out_root: Path,
    *,
    overwrite: bool = False,
) -> list[TransitionResult]:
    results: list[TransitionResult] = []
    providers = iter_provider_runs(run_dir)

    for provider_run in providers:
        single_run_dir = provider_run.run_dir
        run_config = read_json(single_run_dir / "run_config.json")
        if not isinstance(run_config, dict):
            raise ValueError("run_config.json must be a dict")
        run_id = run_config.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_config.json missing run_id")

        goal_cache = load_goal_cache(single_run_dir)
        mvar_to_sig = goal_cache.get("mvar_to_sig", {})
        if not isinstance(mvar_to_sig, dict):
            raise ValueError("goal_cache.mvar_to_sig must be a dict")
        sig_features = build_sig_features(goal_cache)

        out_dir = out_root / run_id
        if provider_run.provider:
            out_dir = out_dir / f"provider={provider_run.provider}"
        out_dir.mkdir(parents=True, exist_ok=True)

        micro_all: dict[str, Any] = {}
        macro_all: dict[str, Any] = {}
        scc_all: dict[str, Any] = {}

        for theorem_dir in sorted(p for p in single_run_dir.iterdir() if p.is_dir()):
            theorem = theorem_dir.name
            variants: dict[str, Any] = {}
            variant_sccs: dict[str, Any] = {}
            for tree_path in sorted(theorem_dir.glob("*_mcts_tree.json")):
                prefix = tree_path.name.split("_mcts_tree", 1)[0]
                tree = read_json(tree_path)
                if not isinstance(tree, dict):
                    continue
                micro, macro = _collect_transitions_for_tree(tree, mvar_to_sig, sig_features)
                macro_probs = _normalize_macro_counts(macro)
                variants[prefix] = {
                    "micro": micro,
                    "macro_counts": macro,
                    "macro_probs": macro_probs,
                }
                variant_sccs[prefix] = _macro_sccs(macro_probs)
            if variants:
                micro_all[theorem] = {k: v["micro"] for k, v in variants.items()}
                macro_all[theorem] = {k: v["macro_probs"] for k, v in variants.items()}
                scc_all[theorem] = variant_sccs

        payload = {
            "schema_version": 1,
            "shape_version": SHAPE_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": run_id,
            "provider": provider_run.provider,
            "source_run_subdir": relpath_under(run_dir, single_run_dir),
            "macro_probs": macro_all,
            "micro_counts": micro_all,
            "macro_sccs": scc_all,
        }

        out_path = out_dir / "transition_analysis.json.gz"
        if not overwrite and out_path.exists():
            raise FileExistsError(f"Refusing to overwrite: {out_path}")
        with gzip.open(out_path, "wt") as f:
            json.dump(payload, f)
        if not out_path.exists():
            raise RuntimeError(f"Missing after write: {out_path}")

        # Also write a small manifest for quick inspection.
        manifest = {
            "schema_version": 1,
            "created_at": payload["created_at"],
            "run_id": run_id,
            "provider": provider_run.provider,
            "source_run_subdir": payload["source_run_subdir"],
            "output_relpath": relpath_under(out_root, out_path),
            "shape_version": SHAPE_VERSION,
            "feature_dim": FEATURE_DIM,
        }
        write_json_atomic(out_dir / "transition_manifest.json", manifest)

        results.append(TransitionResult(provider=provider_run.provider, out_dir=out_dir))

    return results
