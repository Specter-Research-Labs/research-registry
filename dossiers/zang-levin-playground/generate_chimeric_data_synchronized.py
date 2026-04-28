"""
Synchronized version of generate_chimeric_data.py for race condition analysis.

Differences from original:
1. Lock around no_cells_should_move() completion check
2. no_cells_should_move() now checks for MOVING status
3. Deterministic seeding via command-line arg
4. Ground truth verification after threads stop
"""

import sys
import threading
import time
import random
import numpy as np
from pathlib import Path
from paths import resolve_artifact_dir

from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data") / "synchronized"


def create_chimeric_cells(value_list, threadLock, status_probe, cell_types_to_use):
    if len(value_list) == 0:
        return [], []

    left_boundary = (0, 1)
    right_boundary = (len(value_list) - 1, 1)
    cells = []

    cell_classes = {
        'bubble': BubbleSortCell,
        'selection': SelectionSortCell,
        'insertion': InsertionSortCell
    }

    cells_per_type = len(value_list) // len(cell_types_to_use)
    type_assignments = []
    for cell_type in cell_types_to_use:
        type_assignments.extend([cell_type] * cells_per_type)

    while len(type_assignments) < len(value_list):
        type_assignments.append(random.choice(cell_types_to_use))

    random.shuffle(type_assignments)

    for i in range(len(value_list)):
        cell_type = type_assignments[i]
        cell_class = cell_classes[cell_type]

        reverse = (cell_type == 'selection')

        cell = cell_class(
            i + 1, value_list[i], threadLock, (i, 1), cells,
            left_boundary, right_boundary, status_probe,
            disable_visualization=True, reverse_direction=reverse
        )
        cells.append(cell)

    period = 1000000000
    start_count_down = 1000000000
    cell_group = CellGroup(
        cells, cells, 0, left_boundary, right_boundary,
        GroupStatus.ACTIVE, threadLock, start_count_down, period
    )
    for cell in cells:
        cell.group = cell_group

    return cells, [cell_group]


def no_cells_should_move(cells):
    for c in cells:
        if c.status in (CellStatus.SLEEP, CellStatus.MOVING):
            return False
        if c.status == CellStatus.ACTIVE and c.should_move():
            return False
    return True


def verify_sorted(cells):
    values = [c.value for c in cells]
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def kill_all_thread(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def activate(cells, cell_groups):
    for cell in cells:
        cell.start()
    for group in cell_groups:
        group.start()


def run_chimeric_experiment(sorting_list, cell_types_to_use, max_steps=15000):
    threadLock = threading.Lock()
    status_probe = StatusProbe()

    random.shuffle(sorting_list)
    cells, cell_groups = create_chimeric_cells(
        sorting_list, threadLock, status_probe, cell_types_to_use
    )

    threadLock.acquire()
    activate(cells, cell_groups)
    threadLock.release()

    while True:
        with threadLock:
            done = no_cells_should_move(cells) or len(status_probe.sorting_steps) >= max_steps
        if done:
            break
        time.sleep(0.001)

    with threadLock:
        kill_all_thread(cells, cell_groups)
        ground_truth_sorted = verify_sorted(cells)

    time.sleep(0.1)

    return status_probe.cell_types, status_probe.sorting_steps, ground_truth_sorted


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_cells = 100
    num_experiments = 100
    sorting_list = list(range(num_cells))

    configs = [
        ("cell_type_aggregation_random_dist_100_tests", ["bubble", "selection"]),
        ("cell_type_aggregation_random_dist_100_tests_bubble_insertion", ["bubble", "insertion"]),
        ("cell_type_aggregation_random_dist_100_tests_selection_insertion", ["selection", "insertion"]),
        ("cell_type_aggregation_random_dist_100_tests_bubble_selection_insertion", ["bubble", "selection", "insertion"]),
    ]

    print(f"Generating synchronized chimeric data: {num_experiments} experiments with {num_cells} cells each")
    print(f"Output: {DATA_DIR}")
    print(f"Seed: {seed}")

    ground_truth_failures = []

    for dir_name, cell_types in configs:
        target_dir = DATA_DIR / f"{dir_name}_seed{seed}"
        target_dir.mkdir(exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Config: {dir_name}")
        print(f"Cell types: {cell_types}")
        print(f"{'='*60}")

        for i in range(num_experiments):
            if (i + 1) % 10 == 0:
                print(f"  Experiment {i + 1}/{num_experiments}")

            cell_types_data, sorting_steps, sorted_ok = run_chimeric_experiment(
                sorting_list.copy(), cell_types
            )

            if not sorted_ok:
                ground_truth_failures.append((dir_name, i))

            np.save(target_dir / f"exp_{i}.npy", np.array(cell_types_data, dtype=object))

        print(f"  Saved {num_experiments} experiments to {target_dir.name}/")

    if ground_truth_failures:
        print(f"\nWARNING: {len(ground_truth_failures)} ground truth failures detected!")
        for config, exp_idx in ground_truth_failures:
            print(f"  - {config} experiment {exp_idx}")

    print(f"\nChimeric data generation complete (seed={seed}).")


if __name__ == "__main__":
    main(sys.argv[1:])
