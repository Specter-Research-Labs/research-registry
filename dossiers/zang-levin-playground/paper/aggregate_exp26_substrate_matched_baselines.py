"""Aggregate Exp26 per-seed archives into one paper-level summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Exp26 substrate-matched runs")
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/exp26_substrate_matched_baselines_aggregate.json"),
    )
    return parser.parse_args(argv)


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}
    termination_counts: dict[str, int] = {}
    for result in results:
        termination = result.get("termination")
        if termination is not None:
            termination_counts[termination] = termination_counts.get(termination, 0) + 1
    out: dict[str, Any] = {
        "n_trials": int(len(results)),
        "success_count": int(sum(1 if r["success"] else 0 for r in results)),
        "success_rate": round(float(np.mean([1.0 if r["success"] else 0.0 for r in results])), 6),
        "avg_error": round(float(np.mean([r["error"] for r in results])), 6),
        "avg_time": round(float(np.mean([r["time"] for r in results])), 6),
    }
    for key in [
        "swaps",
        "compare_and_swap_count",
        "frozen_swap_attempts",
        "total_move_distance",
        "mean_move_distance",
        "weighted_mean_swap_span",
        "scheduler_sweeps",
    ]:
        vals = [float(r[key]) for r in results if key in r]
        if vals:
            out[f"avg_{key}"] = round(float(np.mean(vals)), 6)
    if termination_counts:
        out["termination_counts"] = termination_counts
    return out


def _pairwise_match_rate(
    paired_trials: list[dict[str, Any]],
    lhs_key: str,
    rhs_key: str,
    metric: str,
) -> float | None:
    matches = []
    for trial in paired_trials:
        lhs = trial.get(lhs_key)
        rhs = trial.get(rhs_key)
        if lhs is None or rhs is None:
            continue
        matches.append(1.0 if lhs[metric] == rhs[metric] else 0.0)
    if not matches:
        return None
    return round(float(np.mean(matches)), 6)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    datasets = []
    for path in args.inputs:
        if not path.exists():
            raise FileNotFoundError(path)
        datasets.append(json.loads(path.read_text()))

    first = datasets[0]
    for data in datasets[1:]:
        for key in [
            "n_cells",
            "n_trials",
            "timeout",
            "max_compare_and_swap",
            "semantics",
            "frozen_counts",
            "algorithm_order",
        ]:
            if data[key] != first[key]:
                raise ValueError(f"Exp26 inputs disagree on {key}")

    algorithm_order = list(first["algorithm_order"])
    frozen_counts = [str(v) for v in first["frozen_counts"]]

    output_algorithms: dict[str, Any] = {}
    for algo_name in algorithm_order:
        output_algorithms[algo_name] = {
            "threaded_cellview": {},
            "sequential_cellview": {},
            "textbook_centralized": {},
            "pairwise_matches": {},
        }
        for frozen in frozen_counts:
            paired_trials = []
            for data in datasets:
                paired_trials.extend(data["algorithms"][algo_name]["paired_trials"][frozen])

            threaded_results = [trial["threaded_cellview"] for trial in paired_trials]
            sequential_results = [trial["sequential_cellview"] for trial in paired_trials]
            centralized_results = [
                trial["textbook_centralized"]
                for trial in paired_trials
                if trial["textbook_centralized"] is not None
            ]

            output_algorithms[algo_name]["threaded_cellview"][frozen] = _summarize_results(
                threaded_results
            )
            output_algorithms[algo_name]["sequential_cellview"][frozen] = _summarize_results(
                sequential_results
            )
            output_algorithms[algo_name]["textbook_centralized"][frozen] = (
                _summarize_results(centralized_results) if centralized_results else None
            )

            pairwise_matches = {
                "threaded_vs_sequential_success_match_rate": _pairwise_match_rate(
                    paired_trials, "threaded_cellview", "sequential_cellview", "success"
                ),
                "threaded_vs_sequential_error_match_rate": _pairwise_match_rate(
                    paired_trials, "threaded_cellview", "sequential_cellview", "error"
                ),
            }
            if centralized_results:
                pairwise_matches["threaded_vs_textbook_success_match_rate"] = (
                    _pairwise_match_rate(
                        paired_trials, "threaded_cellview", "textbook_centralized", "success"
                    )
                )
                pairwise_matches["threaded_vs_textbook_error_match_rate"] = _pairwise_match_rate(
                    paired_trials, "threaded_cellview", "textbook_centralized", "error"
                )
                pairwise_matches["sequential_vs_textbook_success_match_rate"] = (
                    _pairwise_match_rate(
                        paired_trials, "sequential_cellview", "textbook_centralized", "success"
                    )
                )
                pairwise_matches["sequential_vs_textbook_error_match_rate"] = _pairwise_match_rate(
                    paired_trials, "sequential_cellview", "textbook_centralized", "error"
                )
            output_algorithms[algo_name]["pairwise_matches"][frozen] = pairwise_matches

    out_obj = {
        "inputs": [str(path) for path in args.inputs],
        "seeds": [int(data["seed"]) for data in datasets],
        "n_cells": int(first["n_cells"]),
        "n_trials_per_seed": int(first["n_trials"]),
        "timeout": float(first["timeout"]),
        "max_compare_and_swap": int(first["max_compare_and_swap"]),
        "semantics": first["semantics"],
        "matched_substrates": list(first["matched_substrates"]),
        "textbook_centralized_is_reference_only": bool(
            first["textbook_centralized_is_reference_only"]
        ),
        "algorithm_order": algorithm_order,
        "frozen_counts": first["frozen_counts"],
        "algorithms": output_algorithms,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")

    print("=" * 70)
    print("AGGREGATED EXP26: SUBSTRATE-MATCHED CELL-VIEW")
    print("=" * 70)
    print(
        f"Setup: n_cells={out_obj['n_cells']}, n_trials_per_seed={out_obj['n_trials_per_seed']}, "
        f"timeout={out_obj['timeout']}s, max_compare_and_swap={out_obj['max_compare_and_swap']}, "
        f"seeds={out_obj['seeds']}"
    )
    print(f"Frozen counts: {out_obj['frozen_counts']}\n")

    for algo_name in algorithm_order:
        print(algo_name)
        for frozen in frozen_counts:
            threaded = output_algorithms[algo_name]["threaded_cellview"][frozen]
            sequential = output_algorithms[algo_name]["sequential_cellview"][frozen]
            match = output_algorithms[algo_name]["pairwise_matches"][frozen]
            threaded_cmp = threaded.get("avg_compare_and_swap_count", float("nan"))
            sequential_cmp = sequential.get("avg_compare_and_swap_count", float("nan"))
            print(
                f"  frozen={frozen:<2} threaded={threaded['success_rate']:.0%} "
                f"(err={threaded['avg_error']:.2f}, cmp={threaded_cmp:.1f}) "
                f"sequential={sequential['success_rate']:.0%} "
                f"(err={sequential['avg_error']:.2f}, cmp={sequential_cmp:.1f}) "
                f"match_s={match['threaded_vs_sequential_success_match_rate']:.0%}"
            )
            centralized = output_algorithms[algo_name]["textbook_centralized"][frozen]
            if centralized is not None:
                centralized_cmp = centralized.get("avg_compare_and_swap_count", float("nan"))
                print(
                    f"             textbook={centralized['success_rate']:.0%} "
                    f"(err={centralized['avg_error']:.2f}, cmp={centralized_cmp:.1f})"
                )
        print("")

    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
