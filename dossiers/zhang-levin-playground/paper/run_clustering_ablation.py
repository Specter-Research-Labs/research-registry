"""Figure 2: Insertion waiting-gate ablation, scored per swap against a label-permutation null.

Trials reuse the Exp27 runner so that C(t) is sampled after every swap. An earlier version
sampled every 0.02 s of wall-clock time, which gave slow conditions (gated Insertion spinning
while it waits) more samples and therefore a higher max, inflating the gap to NoWait and Gnome.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp27_timing_interventions import METRIC_DEFINITION, run_trial, summarize_pair

PAIRS = ["Bubble+Insertion", "Bubble+InsertionNoWait", "Bubble+Gnome"]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Figure 2 clustering ablation with trial rows")
    parser.add_argument("--n-trials", type=int, default=20)
    parser.add_argument("--n-cells", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--base-seed", type=int, default=20260324)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/fig2_clustering_ablation.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    rng = random.Random(args.base_seed)

    rows = []
    trial_rows = []
    for pair_label in PAIRS:
        print(f"Running {pair_label} for {args.n_trials} trials...")
        pair_trials = []
        for trial_index in range(args.n_trials):
            trial_seed = rng.randrange(2**32)
            result = run_trial(
                pair_label,
                n_cells=args.n_cells,
                timeout=args.timeout,
                trial_seed=trial_seed,
            )
            pair_trials.append(
                {"pair": pair_label, "trial_index": trial_index, "trial_seed": trial_seed, **result}
            )
        trial_rows.extend(pair_trials)
        row = summarize_pair(pair_label, pair_trials)
        rows.append(row)
        print(
            f"  excess={row['excess_max_mean']:+.3f} raw dC={row['clustering_increase_mean']:.3f} "
            f"type2 time={row['right_mean_move_time']:.3f}"
        )

    out_obj = {
        "rows": rows,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "paper/run_clustering_ablation.py",
            "sampling": "per swap (Exp27 runner)",
            "n_trials": args.n_trials,
            "n_cells": args.n_cells,
            "timeout": args.timeout,
            "base_seed": args.base_seed,
            "pairs": PAIRS,
            "metric_definition": METRIC_DEFINITION,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
