"""Aggregate the canonical 2D raw trial archive into paper-facing summaries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paper.exp2d_core import frozen_counts_for_size


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate canonical 2D trial rows for Figure 3")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("paper/results/exp28_2d_canonical_trials.json"),
    )
    parser.add_argument(
        "--heatmap-out",
        type=Path,
        default=Path("paper/results/fig3_2d_success_heatmaps.json"),
    )
    parser.add_argument(
        "--alt-out",
        type=Path,
        default=Path("paper/results/fig3b_alt_orderings.json"),
    )
    return parser.parse_args(argv)


def _success_rate(rows: list[dict]) -> float:
    return float(np.mean([1.0 if row["sorted"] else 0.0 for row in rows])) if rows else float("nan")


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent
    input_path = args.input.resolve()
    try:
        raw_trials_ref = str(input_path.relative_to(repo_root))
    except ValueError:
        raw_trials_ref = str(input_path)
    raw = json.loads(args.input.read_text())
    rows = raw["trial_rows"]

    shell_rows = [row for row in rows if row["suite"] == "shell"]
    alt_rows = [row for row in rows if row["suite"] == "alt"]

    heatmap_summary: dict[str, dict[str, list[float] | list[int]]] = {}
    shell_groups: dict[tuple[int, int, str, int], list[dict]] = defaultdict(list)
    for row in shell_rows:
        shell_groups[
            (row["grid_size"], row["connectivity"], row["algorithm"], row["n_frozen"])
        ].append(row)

    for size in raw["grid_sizes"]:
        frozen_counts = frozen_counts_for_size(size)
        for connectivity in raw["connectivities"]:
            key = f"grid{size}_conn{connectivity}"
            block: dict[str, list[float] | list[int]] = {"frozen": frozen_counts}
            for algorithm in ["Bubble2D", "Selection2D"]:
                block[algorithm] = [
                    round(
                        _success_rate(shell_groups[(size, connectivity, algorithm, n_frozen)]),
                        6,
                    )
                    for n_frozen in frozen_counts
                ]
            heatmap_summary[key] = block

    alt_condition_summary: dict[str, dict] = {}
    alt_groups: dict[tuple[int, int, str, str, int], list[dict]] = defaultdict(list)
    for row in alt_rows:
        alt_groups[
            (
                row["grid_size"],
                row["connectivity"],
                row["order_mode"],
                row["algorithm"],
                row["n_frozen"],
            )
        ].append(row)

    for size in raw["grid_sizes"]:
        frozen_counts = frozen_counts_for_size(size)
        delay_frozen = frozen_counts[1]
        for connectivity in raw["connectivities"]:
            for order_mode in raw["alt_modes"]:
                condition_key = f"{size}x{size}_{connectivity}_{order_mode}"
                condition_block: dict[str, dict] = {}
                for algorithm in ["LocalOrder2D", "SelectionOrder2D"]:
                    navigation = {
                        str(n_frozen): round(
                            _success_rate(
                                alt_groups[
                                    (size, connectivity, order_mode, algorithm, n_frozen)
                                ]
                            ),
                            6,
                        )
                        for n_frozen in frozen_counts
                    }
                    delay_rows = alt_groups[
                        (size, connectivity, order_mode, algorithm, delay_frozen)
                    ]
                    condition_block[algorithm] = {
                        "navigation": navigation,
                        "delay": {
                            "frozen": delay_frozen,
                            "dip_rate": round(
                                float(
                                    np.mean(
                                        [1.0 if row["has_dip"] else 0.0 for row in delay_rows]
                                    )
                                ),
                                6,
                            ),
                            "avg_dips": round(
                                float(np.mean([row["dip_count"] for row in delay_rows])),
                                6,
                            ),
                            "success": round(_success_rate(delay_rows), 6),
                        },
                    }
                alt_condition_summary[condition_key] = condition_block

    heatmap_obj = {
        "source": "exp28_2d_canonical.py raw trial archive",
        "raw_trials": raw_trials_ref,
        "success_2d": heatmap_summary,
        "provenance": {
            "generator": "paper/aggregate_fig3_2d.py",
            "shell_trials": raw["shell_trials"],
            "grid_sizes": raw["grid_sizes"],
            "connectivities": raw["connectivities"],
        },
    }
    alt_obj = {
        "source": "exp28_2d_canonical.py raw trial archive",
        "raw_trials": raw_trials_ref,
        "conditions": alt_condition_summary,
        "provenance": {
            "generator": "paper/aggregate_fig3_2d.py",
            "alt_trials": raw["alt_trials"],
            "grid_sizes": raw["grid_sizes"],
            "connectivities": raw["connectivities"],
            "alt_modes": raw["alt_modes"],
        },
    }

    args.heatmap_out.parent.mkdir(parents=True, exist_ok=True)
    args.heatmap_out.write_text(json.dumps(heatmap_obj, indent=2) + "\n")
    args.alt_out.parent.mkdir(parents=True, exist_ok=True)
    args.alt_out.write_text(json.dumps(alt_obj, indent=2) + "\n")

    print(f"Wrote {args.heatmap_out}")
    print(f"Wrote {args.alt_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
