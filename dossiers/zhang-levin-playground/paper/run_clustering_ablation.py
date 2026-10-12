from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.GnomeSortCell import GnomeSortCell
from modules.multithread.InsertionNoWaitCell import InsertionNoWaitCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.StatusProbe import ExtendedStatusProbe

PAIR_SPECS = [
    ("Bubble+Insertion", [BubbleSortCell, InsertionSortCell]),
    ("Bubble+InsertionNoWait", [BubbleSortCell, InsertionNoWaitCell]),
    ("Bubble+Gnome", [BubbleSortCell, GnomeSortCell]),
]


def measure_type_clustering(cells: list) -> float:
    adjacent = sum(1 for i in range(len(cells) - 1) if cells[i].cell_type == cells[i + 1].cell_type)
    return adjacent / (len(cells) - 1)


def run_clustering_trial(
    cell_classes: list[type],
    *,
    n_cells: int,
    timeout: float,
    trial_seed: int,
) -> dict:
    rng = random.Random(trial_seed)
    thread_lock = threading.Lock()
    probe = ExtendedStatusProbe()
    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)

    values = list(range(n_cells))
    rng.shuffle(values)

    type_counts = [n_cells // 2, n_cells - n_cells // 2]
    types = [0] * type_counts[0] + [1] * type_counts[1]
    rng.shuffle(types)

    cells = []
    type2_str = None
    for i in range(n_cells):
        cls = cell_classes[types[i]]
        cell = cls(
            i + 1,
            values[i],
            thread_lock,
            (i, 1),
            cells,
            left_boundary,
            right_boundary,
            probe,
            disable_visualization=True,
        )
        if types[i] == 1:
            type2_str = cell.cell_type
        cells.append(cell)

    cell_group = CellGroup(
        cells,
        cells,
        0,
        left_boundary,
        right_boundary,
        GroupStatus.ACTIVE,
        thread_lock,
        100000000,
        100000000,
    )
    for cell in cells:
        cell.group = cell_group

    initial_clustering = measure_type_clustering(cells)
    clustering_trajectory = [initial_clustering]

    with thread_lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start_time = time.time()
    success = False
    while time.time() - start_time < timeout:
        time.sleep(0.02)
        with thread_lock:
            clustering_trajectory.append(measure_type_clustering(cells))
            is_sorted = True
            prev = -1
            for cell in cells:
                if cell.value < prev:
                    is_sorted = False
                    break
                prev = cell.value
        if is_sorted:
            success = True
            break

    with thread_lock:
        clustering_trajectory.append(measure_type_clustering(cells))
        for cell in cells:
            cell.status = CellStatus.INACTIVE
        cell_group.status = GroupStatus.MERGED

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    swaps = probe.swap_events
    n_swaps = len(swaps)
    type2_indices = []
    for index, event in enumerate(swaps):
        if event[3] == type2_str or event[4] == type2_str:
            type2_indices.append(index)

    if n_swaps > 1 and type2_indices:
        type2_avg_time = float(np.mean(type2_indices) / (n_swaps - 1))
        usable = True
    else:
        type2_avg_time = float("nan")
        usable = False

    baseline_clustering = sum((type_counts[t] / n_cells) ** 2 for t in [0, 1])
    max_clustering = max(clustering_trajectory)
    return {
        "success": success,
        "usable": usable,
        "n_swaps": n_swaps,
        "initial_clustering": initial_clustering,
        "final_clustering": clustering_trajectory[-1],
        "max_clustering": max_clustering,
        "baseline_clustering": baseline_clustering,
        "clustering": max_clustering - baseline_clustering,
        "type2_avg_time": type2_avg_time,
    }


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

    print("Running Clustering Ablation (Figure 2)")
    out_rows = []
    trial_rows = []

    for label, cell_classes in PAIR_SPECS:
        print(f"Running {label} for {args.n_trials} trials...")
        trial_clustering = []
        trial_time2 = []
        success_count = 0
        usable_trials = 0

        for trial_index in range(args.n_trials):
            trial_seed = rng.randrange(2**32)
            result = run_clustering_trial(
                cell_classes,
                n_cells=args.n_cells,
                timeout=args.timeout,
                trial_seed=trial_seed,
            )
            trial_rows.append(
                {
                    "label": label,
                    "trial_index": trial_index,
                    "trial_seed": trial_seed,
                    **result,
                }
            )

            if result["success"]:
                success_count += 1
            if result["usable"]:
                usable_trials += 1
                trial_clustering.append(float(result["clustering"]))
                trial_time2.append(float(result["type2_avg_time"]))

            if (trial_index + 1) % 5 == 0:
                print(f"  {trial_index + 1}/{args.n_trials}")

        mean_clustering = float(np.mean(trial_clustering))
        std_clustering = (
            float(np.std(trial_clustering, ddof=1)) if len(trial_clustering) > 1 else 0.0
        )
        mean_time2 = float(np.mean(trial_time2))

        print(
            "  Result: "
            f"clustering={mean_clustering:.3f} +- {std_clustering:.3f}, "
            f"type2_time={mean_time2:.3f}, "
            f"success={success_count / args.n_trials:.0%}"
        )

        out_rows.append(
            {
                "label": label,
                "clustering": round(mean_clustering, 3),
                "clustering_std": round(std_clustering, 3),
                "type2_avg_time": round(mean_time2, 3),
                "success_rate": round(success_count / args.n_trials, 3),
                "usable_trials": usable_trials,
            }
        )

    out_obj = {
        "n_trials": args.n_trials,
        "n_cells": args.n_cells,
        "rows": out_rows,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "paper/run_clustering_ablation.py",
            "n_trials": args.n_trials,
            "n_cells": args.n_cells,
            "timeout": args.timeout,
            "base_seed": args.base_seed,
            "pairs": [label for label, _ in PAIR_SPECS],
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
