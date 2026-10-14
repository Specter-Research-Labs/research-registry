"""
Generate traditional (centralized) sorting data for comparison with cell-view.

Usage: uv run python generate_traditional_data.py --seed 42

Produces:
- original_{algo}_sort_with_{N}frozen_steps_100exps_seed{seed}.npy (monotonicity sequences)
- original_{algo}_sort_with_{N}frozen_cannot_move_sorting_steps_100exps_seed{seed}.npy (same)
- original_{algo}_sort_with_{N}frozen_cannot_move_sorting_records_100exps_seed{seed}.npy (array snapshots)
"""

import sys
import argparse
import random
import numpy as np
from pathlib import Path
from paths import resolve_artifact_dir

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Generate traditional sorting data")
    parser.add_argument("--seed", type=int, required=True, help="Random seed")
    return parser.parse_args(argv)


def get_monotonicity(arr):
    monotonicity_value = 1
    prev = arr[0]
    for i in range(1, len(arr)):
        if arr[i] >= prev:
            monotonicity_value += 1
        prev = arr[i]
    return (monotonicity_value / len(arr)) * 100


def traditional_bubble_sort_with_recording(arr, frozen_indices, max_iterations=10000):
    arr = list(arr)
    records = [list(arr)]
    steps = [get_monotonicity(arr)]
    n = len(arr)

    for _ in range(max_iterations):
        swapped = False
        for i in range(n - 1):
            if i in frozen_indices or (i + 1) in frozen_indices:
                continue
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swapped = True
                records.append(list(arr))
                steps.append(get_monotonicity(arr))
        if not swapped:
            break

    return steps, records


def traditional_selection_sort_with_recording(arr, frozen_indices, max_iterations=10000):
    arr = list(arr)
    records = [list(arr)]
    steps = [get_monotonicity(arr)]
    n = len(arr)

    for i in range(n - 1):
        if i in frozen_indices:
            continue

        min_idx = i
        for j in range(i + 1, n):
            if j in frozen_indices:
                continue
            if arr[j] < arr[min_idx]:
                min_idx = j

        if min_idx != i and min_idx not in frozen_indices:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
            records.append(list(arr))
            steps.append(get_monotonicity(arr))

    return steps, records


def traditional_insertion_sort_with_recording(arr, frozen_indices, max_iterations=10000):
    arr = list(arr)
    records = [list(arr)]
    steps = [get_monotonicity(arr)]
    n = len(arr)

    for i in range(1, n):
        if i in frozen_indices:
            continue
        key = arr[i]
        key_pos = i
        j = i - 1

        while j >= 0 and arr[j] > key:
            if j in frozen_indices:
                break
            if (j + 1) not in frozen_indices:
                arr[j + 1] = arr[j]
                key_pos = j
            j -= 1

        if key_pos not in frozen_indices:
            arr[key_pos] = key
            records.append(list(arr))
            steps.append(get_monotonicity(arr))

    return steps, records


def main(argv):
    args = parse_args(argv)
    seed = args.seed
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_experiments = 100
    num_cells = 100
    frozen_counts = [0, 1, 2, 3, 4, 5]

    algorithms = {
        'bubble': traditional_bubble_sort_with_recording,
        'selection': traditional_selection_sort_with_recording,
        'insertion': traditional_insertion_sort_with_recording
    }

    print(f"Generating traditional sorting data in {DATA_DIR}...")
    print(f"Config: {num_cells} cells, {num_experiments} experiments, frozen counts {frozen_counts}, seed {seed}")

    for frozen_num in frozen_counts:
        print(f"\n{'='*60}")
        print(f"Processing {frozen_num} frozen cells...")
        print(f"{'='*60}")

        for algo_name, sort_func in algorithms.items():
            all_steps = []
            all_records = []

            for exp_idx in range(num_experiments):
                if (exp_idx + 1) % 20 == 0:
                    print(f"  {algo_name} experiment {exp_idx + 1}/{num_experiments}")

                sorting_list = list(range(num_cells))
                random.shuffle(sorting_list)

                if frozen_num > 0:
                    frozen_indices = set(random.sample(range(num_cells), frozen_num))
                else:
                    frozen_indices = set()

                steps, records = sort_func(sorting_list, frozen_indices)
                all_steps.append(steps)
                all_records.append(records)

            steps_arr = np.array(all_steps, dtype=object)
            records_arr = np.array(all_records, dtype=object)

            base = f"original_{algo_name}_sort"
            suffix = f"_seed{seed}.npy"

            np.save(DATA_DIR / f"{base}_with_{frozen_num}frozen_steps_100exps{suffix}", steps_arr)
            np.save(DATA_DIR / f"{base}_with_{frozen_num}frozen_cannot_move_sorting_steps_100exps{suffix}", steps_arr)
            np.save(DATA_DIR / f"{base}_with_{frozen_num}frozen_cannot_move_sorting_records_100exps{suffix}", records_arr)

            print(f"  Saved {algo_name} with {frozen_num} frozen")

    print(f"\nTraditional data saved to {DATA_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
