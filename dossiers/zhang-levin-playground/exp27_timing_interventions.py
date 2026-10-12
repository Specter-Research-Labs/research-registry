from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.multithread.BubbleCloneCell import BubbleCloneCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.DelayedBubbleCell import DelayedBubbleCell
from modules.multithread.DelayedGnomeCell import DelayedGnomeCell
from modules.multithread.GnomeCloneCell import GnomeCloneCell
from modules.multithread.GnomeSortCell import GnomeSortCell
from modules.multithread.InsertionNoWaitCell import InsertionNoWaitCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.StatusProbe import ExtendedStatusProbe

CELL_CLASSES = {
    "Bubble": BubbleSortCell,
    "BubbleClone": BubbleCloneCell,
    "DelayedBubble": DelayedBubbleCell,
    "Insertion": InsertionSortCell,
    "InsertionNoWait": InsertionNoWaitCell,
    "Gnome": GnomeSortCell,
    "GnomeClone": GnomeCloneCell,
    "DelayedGnome": DelayedGnomeCell,
}

DEFAULT_PAIRS = [
    "Bubble+Insertion",
    "Bubble+InsertionNoWait",
    "Bubble+BubbleClone",
    "Bubble+DelayedBubble",
    "Gnome+GnomeClone",
    "Gnome+DelayedGnome",
]


def _adjacent_match_fraction(labels: list[object]) -> float:
    if len(labels) < 2:
        return 0.0
    matches = sum(1 for index in range(len(labels) - 1) if labels[index] == labels[index + 1])
    return matches / (len(labels) - 1)


def _trial_setup(
    pair_label: str,
    *,
    n_cells: int,
    trial_seed: int,
) -> tuple[list, list[str], ExtendedStatusProbe, threading.Lock, CellGroup]:
    left_name, right_name = pair_label.split("+", maxsplit=1)
    left_class = CELL_CLASSES[left_name]
    right_class = CELL_CLASSES[right_name]

    rng = random.Random(trial_seed)
    lock = threading.Lock()
    probe = ExtendedStatusProbe()
    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)

    values = list(range(n_cells))
    rng.shuffle(values)

    type_counts = [n_cells // 2, n_cells - n_cells // 2]
    algotypes = [left_name] * type_counts[0] + [right_name] * type_counts[1]
    rng.shuffle(algotypes)

    cells: list = []
    for idx, algotype in enumerate(algotypes):
        cell_class = left_class if algotype == left_name else right_class
        cell = cell_class(
            idx + 1,
            values[idx],
            lock,
            (idx, 1),
            cells,
            left_boundary,
            right_boundary,
            probe,
            disable_visualization=True,
        )
        cells.append(cell)

    cell_group = CellGroup(
        cells,
        cells,
        0,
        left_boundary,
        right_boundary,
        GroupStatus.ACTIVE,
        lock,
        100000000,
        100000000,
    )
    for cell in cells:
        cell.group = cell_group

    return cells, algotypes, probe, lock, cell_group


def _is_sorted(cells: list) -> bool:
    prev_val = -1
    for cell in cells:
        if cell.status == CellStatus.FREEZE:
            continue
        if cell.value < prev_val:
            return False
        prev_val = cell.value
    return True


def _kill_all(cells: list, cell_group: CellGroup) -> None:
    for cell in cells:
        cell.status = CellStatus.INACTIVE
    cell_group.status = GroupStatus.MERGED


def run_trial(
    pair_label: str,
    *,
    n_cells: int,
    timeout: float,
    trial_seed: int,
) -> dict:
    cells, algotypes, probe, lock, cell_group = _trial_setup(
        pair_label,
        n_cells=n_cells,
        trial_seed=trial_seed,
    )

    baseline = sum((algotypes.count(name) / n_cells) ** 2 for name in set(algotypes))
    clustering_trajectory = [_adjacent_match_fraction(algotypes)]

    with lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start_time = time.time()
    success = False
    while time.time() - start_time < timeout:
        with lock:
            success = _is_sorted(cells)
        if success:
            break
        time.sleep(0.02)

    with lock:
        for snapshot in probe.cell_types:
            clustering_trajectory.append(_adjacent_match_fraction([cell[1] for cell in snapshot]))
        final_labels = [cell.cell_type for cell in cells]
        clustering_trajectory.append(_adjacent_match_fraction(final_labels))
        _kill_all(cells, cell_group)

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    n_swaps = len(probe.swap_events)
    trial_result = {
        "success": success,
        "usable": False,
        "n_swaps": n_swaps,
        "initial_clustering": clustering_trajectory[0],
        "final_clustering": clustering_trajectory[-1],
        "max_clustering": max(clustering_trajectory),
        "baseline_clustering": baseline,
        "clustering_increase": max(clustering_trajectory) - baseline,
    }
    if n_swaps == 0:
        return trial_result

    normalizer = max(1, n_swaps - 1)
    move_times: dict[str, list[float]] = {}
    for index, (_, _, _, left_type, right_type) in enumerate(probe.swap_events):
        normalized_index = index / normalizer
        move_times.setdefault(left_type, []).append(normalized_index)
        move_times.setdefault(right_type, []).append(normalized_index)

    left_name, right_name = pair_label.split("+", maxsplit=1)
    left_times = move_times.get(left_name, [])
    right_times = move_times.get(right_name, [])
    if not left_times or not right_times:
        return trial_result

    left_mean = float(np.mean(left_times))
    right_mean = float(np.mean(right_times))
    return {
        **trial_result,
        "usable": True,
        "temporal_separation": abs(left_mean - right_mean),
        "mean_move_time_left": left_mean,
        "mean_move_time_right": right_mean,
    }


def _ci_95(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    arr = np.array(values, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    radius = 1.96 * std / np.sqrt(len(arr))
    return mean - radius, mean + radius


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exp27: synthetic timing interventions")
    parser.add_argument("--n-cells", type=int, default=50)
    parser.add_argument("--n-trials", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--base-seed", type=int, default=20260324)
    parser.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/exp27_timing_interventions.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    rng = random.Random(args.base_seed)

    rows = []
    trial_rows = []
    for pair_label in args.pairs:
        if pair_label not in DEFAULT_PAIRS:
            raise ValueError(f"unsupported pair label: {pair_label}")
        left_name, right_name = pair_label.split("+", maxsplit=1)

        print(f"Running {pair_label} ({args.n_trials} trials)...")
        clustering_values: list[float] = []
        separation_values: list[float] = []
        left_move_times: list[float] = []
        right_move_times: list[float] = []
        success_count = 0
        usable_trials = 0

        for trial_index in range(args.n_trials):
            trial_seed = rng.randrange(2**32)
            result = run_trial(
                pair_label,
                n_cells=args.n_cells,
                timeout=args.timeout,
                trial_seed=trial_seed,
            )
            trial_rows.append(
                {
                    "pair": pair_label,
                    "left_algotype": left_name,
                    "right_algotype": right_name,
                    "trial_index": trial_index,
                    "trial_seed": trial_seed,
                    **result,
                }
            )
            if result["success"]:
                success_count += 1
            clustering_values.append(float(result["clustering_increase"]))
            if result["usable"]:
                usable_trials += 1
                separation_values.append(float(result["temporal_separation"]))
                left_move_times.append(float(result["mean_move_time_left"]))
                right_move_times.append(float(result["mean_move_time_right"]))

        if not separation_values:
            raise RuntimeError(f"{pair_label} produced no usable temporal-separation trials")

        ci_lo, ci_hi = _ci_95(clustering_values)
        sep_ci_lo, sep_ci_hi = _ci_95(separation_values)
        rows.append(
            {
                "pair": pair_label,
                "left_algotype": left_name,
                "right_algotype": right_name,
                "intervention": "synthetic_delay" if "Delayed" in pair_label else "reference",
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
                "success_rate": round(success_count / args.n_trials, 6),
                "usable_trials": usable_trials,
            }
        )

    rows.sort(key=lambda row: row["clustering_increase_mean"], reverse=True)

    out_obj = {
        "n_trials_per_pair": args.n_trials,
        "rows": rows,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "exp27_timing_interventions.py",
            "n_cells": args.n_cells,
            "n_trials": args.n_trials,
            "timeout": args.timeout,
            "base_seed": args.base_seed,
            "pairs": args.pairs,
            "metric_definition": {
                "clustering_increase": "max adjacent-match fraction minus random-mixing baseline",
                "temporal_separation": (
                    "absolute difference in per-algotype normalized mean swap index"
                ),
            },
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
