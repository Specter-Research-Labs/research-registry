# ruff: noqa: I001
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from shared import (
    import_wonton_symbol,
    iter_jsonl_objects,
    iter_trace_paths,
    resolve_repo_root,
)

DEFAULT_ALPHAS = "0,0.1,0.25,0.5,0.75,1.0"


@dataclass(frozen=True)
class IterRecord:
    provider_order: list[str]
    provider_score: dict[str, float]
    model_score: dict[str, float]
    success_by_tactic: dict[str, bool]


def _parse_alphas(value: str) -> list[float]:
    raw = [part.strip() for part in value.split(",")]
    if not raw or all(not part for part in raw):
        raise ValueError("alphas must not be empty")
    result: list[float] = []
    for part in raw:
        if not part:
            continue
        alpha = float(part)
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be in [0,1], got {alpha}")
        if alpha not in result:
            result.append(alpha)
    if not result:
        raise ValueError("alphas must contain at least one value")
    return result


def _rank_order(record: IterRecord, alpha: float) -> list[str]:
    scored: list[tuple[str, float, float, int]] = []
    for idx, tactic in enumerate(record.provider_order):
        model_score = record.model_score[tactic]
        provider_score = record.provider_score.get(tactic, 0.0)
        combined = (alpha * model_score) + ((1.0 - alpha) * provider_score)
        scored.append((tactic, combined, provider_score, idx))
    scored.sort(key=lambda item: (-item[1], -item[2], item[3]))
    return [tactic for tactic, _, _, _ in scored]


def _first_success_rank(order: list[str], success_by_tactic: dict[str, bool]) -> int:
    for idx, tactic in enumerate(order, start=1):
        if success_by_tactic.get(tactic, False):
            return idx
    raise ValueError("order does not contain a successful tactic")


def _alpha_metrics(records: list[IterRecord], alpha: float) -> dict[str, Any]:
    top1_success = 0
    rank_sum = 0
    pair_total = 0
    pair_correct = 0

    for record in records:
        ranked = _rank_order(record, alpha)
        success_by_tactic = record.success_by_tactic
        if success_by_tactic.get(ranked[0], False):
            top1_success += 1
        rank_sum += _first_success_rank(ranked, success_by_tactic)

        pos = {tactic: idx for idx, tactic in enumerate(ranked, start=1)}
        succ = [t for t in ranked if success_by_tactic.get(t, False)]
        fail = [t for t in ranked if not success_by_tactic.get(t, False)]
        for s in succ:
            for f in fail:
                pair_total += 1
                if pos[s] < pos[f]:
                    pair_correct += 1

    n = len(records)
    return {
        "alpha": alpha,
        "iters": n,
        "top1_success": round(top1_success / n, 4) if n else None,
        "mean_rank_first_success": round(rank_sum / n, 4) if n else None,
        "pairwise_success_ahead": round(pair_correct / pair_total, 4) if pair_total else None,
        "pairs": pair_total,
    }


def _comparison_vs_alpha0(records: list[IterRecord], alpha: float) -> dict[str, Any]:
    improved = 0
    worse = 0
    for record in records:
        base_order = _rank_order(record, 0.0)
        this_order = _rank_order(record, alpha)
        base_rank = _first_success_rank(base_order, record.success_by_tactic)
        this_rank = _first_success_rank(this_order, record.success_by_tactic)
        if this_rank < base_rank:
            improved += 1
        elif this_rank > base_rank:
            worse += 1
    total = len(records)
    return {
        "improved_iters": improved,
        "worse_iters": worse,
        "same_iters": total - improved - worse,
        "improved_rate": round(improved / total, 4) if total else None,
        "worse_rate": round(worse / total, 4) if total else None,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Replay-evaluate family_prior ranker ordering on existing MCTS traces"
    )
    parser.add_argument("--run-dir", required=True, help="Path to a corpus run directory")
    parser.add_argument("--model", required=True, help="Path to family_prior.json")
    parser.add_argument(
        "--alphas",
        default=DEFAULT_ALPHAS,
        help=f"Comma-separated alpha values in [0,1] (default: {DEFAULT_ALPHAS})",
    )
    parser.add_argument("--repo-root", default=None, help="Repository root override")
    parser.add_argument("--out", default=None, help="Optional output JSON path")
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root)
    build_sig_features = import_wonton_symbol(
        repo_root, "analysis.learning_common", "build_sig_features"
    )
    load_goal_cache = import_wonton_symbol(repo_root, "analysis.learning_common", "load_goal_cache")
    normalize_tactic = import_wonton_symbol(repo_root, "prover.providers.base", "normalize_tactic")
    tactic_family = import_wonton_symbol(repo_root, "prover.providers.base", "tactic_family")
    FamilyPriorModel = import_wonton_symbol(repo_root, "prover.rankers", "FamilyPriorModel")

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run_dir not found: {run_dir}")
    model_path = Path(args.model).expanduser().resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"model not found: {model_path}")
    alphas = _parse_alphas(args.alphas)

    model = FamilyPriorModel.load(model_path)
    goal_cache = load_goal_cache(run_dir)
    sig_features = build_sig_features(goal_cache)

    trace_paths = iter_trace_paths(run_dir)
    records: list[IterRecord] = []
    iterations_total = 0
    iterations_with_attempts = 0

    for trace_path in trace_paths:
        for record in iter_jsonl_objects(trace_path):
            if record.get("event") != "iteration":
                continue
            iterations_total += 1

            attempts = record.get("attempts")
            tactics = record.get("tactics")
            node = record.get("node")
            if not isinstance(attempts, list) or not isinstance(tactics, list):
                continue
            if not isinstance(node, dict):
                continue

            attempt_order: list[str] = []
            success_by_tactic: dict[str, bool] = {}
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                tactic = attempt.get("tactic")
                outcome = attempt.get("outcome")
                if not isinstance(tactic, str) or not isinstance(outcome, str):
                    continue
                if tactic not in success_by_tactic:
                    attempt_order.append(tactic)
                    success_by_tactic[tactic] = False
                if outcome == "success":
                    success_by_tactic[tactic] = True
            if not attempt_order:
                continue
            iterations_with_attempts += 1

            provider_order: list[str] = []
            provider_score: dict[str, float] = {}
            seen: set[str] = set()
            for item in tactics:
                if not isinstance(item, dict):
                    continue
                tactic = item.get("tactic")
                score = item.get("score")
                if not isinstance(tactic, str):
                    continue
                if isinstance(score, (int, float)):
                    provider_score[tactic] = float(score)
                if tactic in success_by_tactic and tactic not in seen:
                    provider_order.append(tactic)
                    seen.add(tactic)
            for tactic in attempt_order:
                if tactic not in seen:
                    provider_order.append(tactic)
                    seen.add(tactic)
            if len(provider_order) < 2:
                continue
            if not any(success_by_tactic.get(tactic, False) for tactic in provider_order):
                continue

            sig = node.get("goal_sig")
            if not isinstance(sig, str):
                sig = node.get("goal_sig_strict")
            features = sig_features.get(sig) if isinstance(sig, str) else None

            model_score: dict[str, float] = {}
            for tactic in provider_order:
                family = tactic_family(normalize_tactic(tactic))
                model_score[tactic] = float(model.score(features, family))

            records.append(
                IterRecord(
                    provider_order=provider_order,
                    provider_score=provider_score,
                    model_score=model_score,
                    success_by_tactic=success_by_tactic,
                )
            )

    if not records:
        raise ValueError("No evaluable iteration records found")

    run_id = None
    run_config_path = run_dir / "run_config.json"
    if run_config_path.exists():
        run_config = json.loads(run_config_path.read_text())
        if isinstance(run_config, dict) and isinstance(run_config.get("run_id"), str):
            run_id = run_config["run_id"]

    rows = []
    for alpha in alphas:
        row = _alpha_metrics(records, alpha)
        if 0.0 in alphas and alpha != 0.0:
            row["comparison_vs_alpha0"] = _comparison_vs_alpha0(records, alpha)
        rows.append(row)

    payload = {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "run_id": run_id,
        "model_path": str(model_path),
        "trace_files": len(trace_paths),
        "iterations_total": iterations_total,
        "iterations_with_attempts": iterations_with_attempts,
        "eval_iterations": len(records),
        "alphas": alphas,
        "rows": rows,
    }

    text = json.dumps(payload, indent=2)
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n")
    print(text)
