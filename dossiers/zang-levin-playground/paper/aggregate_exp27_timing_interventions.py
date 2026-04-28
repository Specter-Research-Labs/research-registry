"""Aggregate Exp27 per-seed timing-intervention archives into one paper-level summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


def _ci_95(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    arr = np.array(values, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    radius = 1.96 * std / np.sqrt(len(arr))
    return mean - radius, mean + radius


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Exp27 timing-intervention runs")
    parser.add_argument("--inputs", nargs="+", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/exp27_timing_interventions_aggregate.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    pair_trials: dict[str, list[dict]] = defaultdict(list)
    trial_rows = []
    input_paths = []
    base_seeds = []
    n_cells = None
    timeout = None

    for path in args.inputs:
        obj = json.loads(path.read_text())
        input_paths.append(str(path))
        base_seeds.append(obj["provenance"]["base_seed"])
        n_cells = obj["provenance"]["n_cells"]
        timeout = obj["provenance"]["timeout"]
        for trial in obj["trial_rows"]:
            pair_trials[trial["pair"]].append(trial)
            trial_rows.append(trial)

    rows = []
    for pair, trials in pair_trials.items():
        clustering_values = [float(trial["clustering_increase"]) for trial in trials]
        separation_trials = [trial for trial in trials if trial["usable"]]
        separation_values = [float(trial["temporal_separation"]) for trial in separation_trials]
        left_move_times = [float(trial["mean_move_time_left"]) for trial in separation_trials]
        right_move_times = [float(trial["mean_move_time_right"]) for trial in separation_trials]
        ci_lo, ci_hi = _ci_95(clustering_values)
        sep_ci_lo, sep_ci_hi = _ci_95(separation_values)
        left_name, right_name = pair.split("+", maxsplit=1)
        rows.append(
            {
                "pair": pair,
                "left_algotype": left_name,
                "right_algotype": right_name,
                "intervention": "synthetic_delay" if "Delayed" in pair else "reference",
                "temporal_separation": round(float(np.mean(separation_values)), 6),
                "temporal_separation_std": round(
                    float(np.std(separation_values, ddof=1)) if len(separation_values) > 1 else 0.0,
                    6,
                ),
                "temporal_separation_ci_lo": round(sep_ci_lo, 6),
                "temporal_separation_ci_hi": round(sep_ci_hi, 6),
                "clustering_increase_mean": round(float(np.mean(clustering_values)), 6),
                "clustering_increase_std": round(
                    float(np.std(clustering_values, ddof=1)) if len(clustering_values) > 1 else 0.0,
                    6,
                ),
                "clustering_increase_ci_lo": round(ci_lo, 6),
                "clustering_increase_ci_hi": round(ci_hi, 6),
                "left_mean_move_time": round(float(np.mean(left_move_times)), 6),
                "right_mean_move_time": round(float(np.mean(right_move_times)), 6),
                "success_rate": round(
                    sum(1 for trial in trials if trial["success"]) / len(trials),
                    6,
                ),
                "usable_trials": len(separation_trials),
            }
        )

    rows.sort(key=lambda row: row["clustering_increase_mean"], reverse=True)

    out_obj = {
        "inputs": input_paths,
        "n_trials_total_per_pair": len(next(iter(pair_trials.values()))) if pair_trials else 0,
        "rows": rows,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "paper/aggregate_exp27_timing_interventions.py",
            "base_seeds": base_seeds,
            "n_cells": n_cells,
            "timeout": timeout,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
