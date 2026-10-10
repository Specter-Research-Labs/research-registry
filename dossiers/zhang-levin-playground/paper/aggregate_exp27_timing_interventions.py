"""Aggregate Exp27 per-seed timing-intervention archives into one paper-level summary."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp27_timing_interventions import METRIC_DEFINITION, summarize_pair


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
    input_paths = []
    base_seeds = []
    provenances = []

    for path in args.inputs:
        obj = json.loads(path.read_text())
        input_paths.append(str(path))
        base_seeds.append(obj["provenance"]["base_seed"])
        provenances.append(
            {key: obj["provenance"][key] for key in ("n_cells", "timeout", "n_trials")}
        )
        for trial in obj["trial_rows"]:
            pair_trials[trial["pair"]].append(trial)

    if any(p != provenances[0] for p in provenances):
        raise ValueError(f"inputs disagree on n_cells/timeout/n_trials: {provenances}")

    rows = [summarize_pair(pair, trials) for pair, trials in pair_trials.items()]
    rows.sort(key=lambda row: row["excess_max_mean"], reverse=True)

    out_obj = {
        "inputs": input_paths,
        "rows": rows,
        "provenance": {
            "generator": "paper/aggregate_exp27_timing_interventions.py",
            "base_seeds": base_seeds,
            "n_cells": provenances[0]["n_cells"],
            "timeout": provenances[0]["timeout"],
            "metric_definition": METRIC_DEFINITION,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
