from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from analysis.learning_common import (
    build_sig_features,
    committed_tactic_by_mvar,
    features_for_sig,
    load_goal_cache,
    open_jsonl,
)
from analysis.logs import (
    iter_provider_runs,
    iter_theorem_variant_prefixes,
    read_json,
    relpath_under,
    write_json_atomic,
)
from prover.goal_features import FEATURE_DIM
from prover.providers.base import normalize_tactic, tactic_family


@dataclass(frozen=True)
class ExportResult:
    provider: str | None
    dataset_path: Path
    manifest_path: Path
    rows_written: int


def export_learning_dataset(
    run_dir: Path,
    out_root: Path,
    *,
    overwrite: bool = False,
) -> list[ExportResult]:
    """Export attempt-level training data from an existing logs run dir."""
    results: list[ExportResult] = []
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

        dataset_path = out_dir / "dataset.jsonl.gz"
        manifest_path = out_dir / "dataset_manifest.json"
        if not overwrite and (dataset_path.exists() or manifest_path.exists()):
            raise FileExistsError(f"Refusing to overwrite existing dataset in {out_dir}")

        rows_written = 0
        with gzip.open(dataset_path, "wt") as out_f:
            for theorem_dir in sorted(p for p in single_run_dir.iterdir() if p.is_dir()):
                theorem = theorem_dir.name
                variant_prefixes = list(iter_theorem_variant_prefixes(theorem_dir))
                if not variant_prefixes:
                    continue

                for prefix in variant_prefixes:
                    trace_path = theorem_dir / f"{prefix}_mcts_trace.jsonl"
                    if not trace_path.exists():
                        trace_gz = trace_path.with_suffix(trace_path.suffix + ".gz")
                        if trace_gz.exists():
                            trace_path = trace_gz
                        else:
                            raise FileNotFoundError(f"Missing trace for {theorem}/{prefix}")

                    tree_path = theorem_dir / f"{prefix}_mcts_tree.json"
                    if not tree_path.exists():
                        raise FileNotFoundError(
                            f"Missing mcts tree for {theorem}/{prefix}: {tree_path}"
                        )
                    tree = read_json(tree_path)
                    if not isinstance(tree, dict):
                        raise ValueError(f"Invalid mcts tree: {tree_path}")
                    committed_by_mvar = committed_tactic_by_mvar(tree)

                    solved = None
                    solution_mvars: set[str] = set()
                    history_path = theorem_dir / f"{prefix}_history.json"
                    if history_path.exists():
                        history = read_json(history_path)
                        if isinstance(history, dict):
                            solution = history.get("solution_path")
                            if solution is None:
                                solved = False
                            elif isinstance(solution, list):
                                solved = True
                                for step in solution:
                                    if not isinstance(step, dict):
                                        continue
                                    m = step.get("mvar_id")
                                    if isinstance(m, str):
                                        solution_mvars.add(m)

                    for record in open_jsonl(trace_path):
                        if record.get("event") != "iteration":
                            continue
                        node = record.get("node")
                        if not isinstance(node, dict):
                            continue
                        node_mvar = node.get("mvar_id")
                        if not isinstance(node_mvar, str):
                            continue
                        node_sig = node.get("goal_sig")
                        goal_sig = node_sig if isinstance(node_sig, str) else None
                        goal_sig_strict = node.get("goal_sig_strict")
                        node_goal_type = node.get("goal_type")
                        node_features = features_for_sig(goal_sig, sig_features)

                        tactic_scores: dict[str, float] = {}
                        tactics = record.get("tactics", [])
                        if isinstance(tactics, list):
                            for item in tactics:
                                if not isinstance(item, dict):
                                    continue
                                t = item.get("tactic")
                                s = item.get("score")
                                if isinstance(t, str) and isinstance(s, (int, float)):
                                    tactic_scores[t] = float(s)

                        committed_tactic = committed_by_mvar.get(node_mvar)
                        attempts = record.get("attempts", [])
                        if not isinstance(attempts, list):
                            continue
                        for attempt in attempts:
                            if not isinstance(attempt, dict):
                                continue
                            tactic = attempt.get("tactic")
                            if not isinstance(tactic, str):
                                continue
                            tactic_norm = attempt.get("tactic_norm")
                            tactic_norm_str = (
                                tactic_norm
                                if isinstance(tactic_norm, str)
                                else normalize_tactic(tactic)
                            )
                            fam = tactic_family(tactic_norm_str)
                            provider_score = tactic_scores.get(tactic)
                            outcome = attempt.get("outcome")
                            if not isinstance(outcome, str):
                                continue
                            child_mvars = attempt.get("child_mvar_ids", [])
                            child_list = child_mvars if isinstance(child_mvars, list) else []
                            child_sigs: list[str] | None = None
                            committed = committed_tactic == tactic
                            if committed:
                                resolved: list[str] = []
                                for child in child_list:
                                    if not isinstance(child, str):
                                        continue
                                    sig = mvar_to_sig.get(child)
                                    if isinstance(sig, str):
                                        resolved.append(sig)
                                child_sigs = resolved

                            row = {
                                "schema_version": 1,
                                "run_id": run_id,
                                "provider": run_config.get("provider"),
                                "provider_label": run_config.get("provider_label"),
                                "theorem": theorem,
                                "variant": prefix,
                                "variant_solved": solved,
                                "node_on_solution_path": node_mvar in solution_mvars,
                                "tier": record.get("tier"),
                                "budget": record.get("budget"),
                                "iteration": record.get("iteration"),
                                "node_mvar_id": node_mvar,
                                "goal_sig": goal_sig,
                                "goal_sig_strict": (
                                    goal_sig_strict
                                    if isinstance(goal_sig_strict, str)
                                    else None
                                ),
                                "goal_type": (
                                    node_goal_type if isinstance(node_goal_type, str) else None
                                ),
                                "goal_features": node_features,
                                "tactic": tactic,
                                "tactic_norm": tactic_norm_str,
                                "tactic_family": fam,
                                "provider_score": provider_score,
                                "outcome": outcome,
                                "committed": committed,
                                "child_count": len([c for c in child_list if isinstance(c, str)]),
                                "child_goal_sigs": child_sigs,
                                "peg_id": attempt.get("peg_id"),
                                "peg_kind": attempt.get("peg_kind"),
                                "block_reason": attempt.get("block_reason"),
                                "provider_id": attempt.get("provider_id"),
                            }
                            out_f.write(json.dumps(row) + "\n")
                            rows_written += 1

        manifest = {
            "schema_version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": run_id,
            "provider": provider_run.provider,
            "source_run_subdir": relpath_under(run_dir, single_run_dir),
            "dataset_relpath": relpath_under(out_root, dataset_path),
            "manifest_relpath": relpath_under(out_root, manifest_path),
            "rows_written": rows_written,
            "feature_dim": FEATURE_DIM,
            "sig_scheme": goal_cache.get("sig_scheme"),
            "sig_stats": goal_cache.get("sig_stats"),
        }
        write_json_atomic(manifest_path, manifest)

        results.append(
            ExportResult(
                provider=provider_run.provider,
                dataset_path=dataset_path,
                manifest_path=manifest_path,
                rows_written=rows_written,
            )
        )

    return results
