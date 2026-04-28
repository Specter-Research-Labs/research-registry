"""Aggregate Exp25 per-seed JSON archives into one paper-level summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Exp25 factorization runs")
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/exp25_selection_factorization_aggregate.json"),
    )
    return parser.parse_args(argv)


def _empty_metrics() -> dict[str, float]:
    return {
        "n_trials": 0,
        "success_count": 0,
        "time_sum": 0.0,
        "error_sum": 0.0,
        "swap_sum": 0.0,
        "compare_and_swap_sum": 0.0,
        "frozen_attempt_sum": 0.0,
        "total_move_distance_sum": 0.0,
        "mean_move_distance_sum": 0.0,
        "mean_swap_span_sum": 0.0,
    }


def _summarize(acc: dict[str, float]) -> dict[str, float]:
    n_trials = int(acc["n_trials"])
    if n_trials == 0:
        return {
            "n_trials": 0,
            "success_count": 0,
            "success_rate": float("nan"),
            "avg_time": float("nan"),
            "avg_error": float("nan"),
            "avg_swaps": float("nan"),
            "avg_compare_and_swap_count": float("nan"),
            "avg_frozen_swap_attempts": float("nan"),
            "avg_total_move_distance": float("nan"),
            "avg_mean_move_distance": float("nan"),
            "avg_mean_swap_span": float("nan"),
            "weighted_mean_swap_span": float("nan"),
        }

    avg_swaps = acc["swap_sum"] / n_trials
    avg_total_move_distance = acc["total_move_distance_sum"] / n_trials
    return {
        "n_trials": n_trials,
        "success_count": int(acc["success_count"]),
        "success_rate": round(acc["success_count"] / n_trials, 6),
        "avg_time": round(acc["time_sum"] / n_trials, 6),
        "avg_error": round(acc["error_sum"] / n_trials, 6),
        "avg_swaps": round(avg_swaps, 6),
        "avg_compare_and_swap_count": round(acc["compare_and_swap_sum"] / n_trials, 6),
        "avg_frozen_swap_attempts": round(acc["frozen_attempt_sum"] / n_trials, 6),
        "avg_total_move_distance": round(avg_total_move_distance, 6),
        "avg_mean_move_distance": round(acc["mean_move_distance_sum"] / n_trials, 6),
        "avg_mean_swap_span": round(acc["mean_swap_span_sum"] / n_trials, 6),
        "weighted_mean_swap_span": round(
            avg_total_move_distance / (2.0 * avg_swaps) if avg_swaps > 0 else 0.0,
            6,
        ),
    }


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    datasets = []
    for path in args.inputs:
        if not path.exists():
            raise FileNotFoundError(path)
        datasets.append(json.loads(path.read_text()))

    first = datasets[0]
    expected_variants = first["variants"]
    expected_semantics = first["semantics"]
    expected_n_cells = first["n_cells"]
    expected_timeout = first["timeout"]

    for data in datasets[1:]:
        if data["variants"] != expected_variants:
            raise ValueError("Exp25 inputs disagree on variants")
        if data["semantics"] != expected_semantics:
            raise ValueError("Exp25 inputs disagree on semantics")
        if data["n_cells"] != expected_n_cells:
            raise ValueError("Exp25 inputs disagree on n_cells")
        if data["timeout"] != expected_timeout:
            raise ValueError("Exp25 inputs disagree on timeout")

    accumulators: dict[str, dict[str, dict[str, dict[str, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(_empty_metrics))
    )

    for data in datasets:
        for semantics in expected_semantics:
            for variant in expected_variants:
                for frozen, block in data["results"][semantics][variant].items():
                    acc = accumulators[semantics][variant][frozen]
                    for trial in block["results"]:
                        acc["n_trials"] += 1
                        acc["success_count"] += int(trial["success"])
                        acc["time_sum"] += float(trial["time"])
                        acc["error_sum"] += float(trial["error"])
                        acc["swap_sum"] += float(trial["swaps"])
                        acc["compare_and_swap_sum"] += float(trial["compare_and_swap_count"])
                        acc["frozen_attempt_sum"] += float(trial["frozen_swap_attempts"])
                        acc["total_move_distance_sum"] += float(trial["total_move_distance"])
                        acc["mean_move_distance_sum"] += float(trial["mean_move_distance"])
                        acc["mean_swap_span_sum"] += float(trial["mean_swap_span"])

    summary = {
        semantics: {
            variant: {
                frozen: _summarize(acc)
                for frozen, acc in sorted(frozen_map.items(), key=lambda item: int(item[0]))
            }
            for variant, frozen_map in variant_map.items()
        }
        for semantics, variant_map in accumulators.items()
    }

    out_obj = {
        "inputs": [str(path) for path in args.inputs],
        "seeds": [int(data["seed"]) for data in datasets],
        "n_cells": expected_n_cells,
        "timeout": expected_timeout,
        "semantics": expected_semantics,
        "variants": expected_variants,
        "frozen_counts": first["frozen_counts"],
        "summary": summary,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")

    for semantics in expected_semantics:
        print("=" * 70)
        print(f"AGGREGATED EXP25: {semantics}")
        print("=" * 70)
        for variant in expected_variants:
            print(variant)
            for frozen, block in summary[semantics][variant].items():
                print(
                    f"  frozen={frozen:<2} success={block['success_rate']:.0%} "
                    f"err={block['avg_error']:.2f} swaps={block['avg_swaps']:.1f} "
                    f"move_span={block['weighted_mean_swap_span']:.2f}"
                )
            print("")

    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
