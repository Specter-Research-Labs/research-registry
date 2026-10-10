from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exp27_timing_interventions import METRIC_DEFINITION, summarize_pair
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.GnomeSortCell import GnomeSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.ShakerSortCell import ShakerSortCell
from modules.multithread.StatusProbe import ExtendedStatusProbe
from paper.clustering_null import adjacent_match_fraction, score_trajectory

CELL_CLASSES = {
    "Bubble": BubbleSortCell,
    "Selection": SelectionSortCell,
    "Insertion": InsertionSortCell,
    "Gnome": GnomeSortCell,
    "Shaker": ShakerSortCell,
}

DEFAULT_PAIRS = [f"{left}+{right}" for left, right in combinations(CELL_CLASSES, 2)]


def _trial_setup(
    pair_label: str,
    *,
    n_cells: int,
    trial_seed: int,
) -> tuple[list, list[str], list[int], ExtendedStatusProbe, threading.Lock, CellGroup]:
    left_name, right_name = pair_label.split("+", maxsplit=1)
    left_class = CELL_CLASSES[left_name]
    right_class = CELL_CLASSES[right_name]

    random.seed(trial_seed)
    lock = threading.Lock()
    probe = ExtendedStatusProbe()
    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)

    values = list(range(n_cells))
    random.shuffle(values)

    type_counts = [n_cells // 2, n_cells - n_cells // 2]
    algotypes = [left_name] * type_counts[0] + [right_name] * type_counts[1]
    random.shuffle(algotypes)

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

    return cells, algotypes, values, probe, lock, cell_group


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
    cells, algotypes, values, probe, lock, cell_group = _trial_setup(
        pair_label,
        n_cells=n_cells,
        trial_seed=trial_seed,
    )

    baseline = sum((algotypes.count(name) / n_cells) ** 2 for name in set(algotypes))
    value_trajectory = [list(values)]

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
            value_trajectory.append([cell[2] for cell in snapshot])
        value_trajectory.append([cell.value for cell in cells])
        _kill_all(cells, cell_group)

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    value_labels = dict(zip(values, algotypes))
    scores = score_trajectory(value_trajectory, value_labels, permutation_seed=trial_seed)
    n_swaps = len(probe.swap_events)
    trial_result = {
        "success": success,
        "n_swaps": n_swaps,
        "initial_clustering": adjacent_match_fraction(algotypes),
        "final_clustering": adjacent_match_fraction(
            [value_labels[v] for v in value_trajectory[-1]]
        ),
        "baseline_clustering": baseline,
        "clustering_increase": scores["max_clustering"] - baseline,
        **scores,
    }
    if n_swaps == 0:
        return {**trial_result, "usable": False}

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
        return {**trial_result, "usable": False}

    left_mean = float(np.mean(left_times))
    right_mean = float(np.mean(right_times))
    return {
        **trial_result,
        "usable": True,
        "temporal_separation": abs(left_mean - right_mean),
        "mean_move_time_left": left_mean,
        "mean_move_time_right": right_mean,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute Figure 1 temporal separation vs clustering"
    )
    parser.add_argument("--n-cells", type=int, default=30)
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--base-seed", type=int, default=20260306)
    parser.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/fig1_temporal_vs_clustering.json"),
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
                {
                    "pair": pair_label,
                    "left_algotype": left_name,
                    "right_algotype": right_name,
                    "trial_index": trial_index,
                    "trial_seed": trial_seed,
                    **result,
                }
            )
        trial_rows.extend(pair_trials)
        row = summarize_pair(pair_label, pair_trials)
        rows.append(row)
        print(
            f"  separation={row['temporal_separation_mean']:.3f}, "
            f"excess={row['excess_max_mean']:+.3f}, "
            f"raw dC={row['clustering_increase_mean']:.3f}"
        )

    rows.sort(key=lambda row: row["excess_max_mean"], reverse=True)

    def pearson(subset: list[dict], y_key: str) -> float:
        x = np.array([row["temporal_separation_mean"] for row in subset], dtype=np.float64)
        y = np.array([row[y_key] for row in subset], dtype=np.float64)
        return round(float(np.corrcoef(x, y)[0, 1]), 6)

    with_insertion = [row for row in rows if "Insertion" in row["pair"]]
    without_insertion = [row for row in rows if "Insertion" not in row["pair"]]
    correlations = {
        y_key: {
            "all_pairs": pearson(rows, y_key),
            "insertion_pairs": pearson(with_insertion, y_key),
            "non_insertion_pairs": pearson(without_insertion, y_key),
        }
        for y_key in ("excess_max_mean", "clustering_increase_mean")
    }

    out_obj = {
        "n_trials_per_pair": args.n_trials,
        "pearson_r": correlations,
        "rows": rows,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "paper/compute_fig1_temporal_clustering.py",
            "n_cells": args.n_cells,
            "n_trials": args.n_trials,
            "timeout": args.timeout,
            "base_seed": args.base_seed,
            "pairs": args.pairs,
            "metric_definition": METRIC_DEFINITION,
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
