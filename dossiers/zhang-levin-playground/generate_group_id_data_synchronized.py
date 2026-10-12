"""
Synchronized version of generate_group_id_data.py for race condition analysis.

Differences from original:
1. Lock around no_cells_should_move() completion check
2. Lock around snapshot extraction
3. no_cells_should_move() now checks for MOVING status
4. Deterministic seeding via command-line arg
5. Ground truth verification after threads stop
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
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data") / "synchronized"

CELL_TYPE_BUBBLE = 1
CELL_TYPE_SELECTION = 0


def create_mixed_cells(value_list, threadLock, status_probe):
    if len(value_list) == 0:
        return [], []

    left_boundary = (0, 1)
    right_boundary = (len(value_list) - 1, 1)
    cells = []

    num_bubble = len(value_list) // 2
    type_assignments = [CELL_TYPE_BUBBLE] * num_bubble + [CELL_TYPE_SELECTION] * (len(value_list) - num_bubble)
    random.shuffle(type_assignments)

    for i in range(len(value_list)):
        cell_type = type_assignments[i]

        if cell_type == CELL_TYPE_BUBBLE:
            cell = BubbleSortCell(
                i + 1, value_list[i], threadLock, (i, 1), cells,
                left_boundary, right_boundary, status_probe,
                disable_visualization=True, label=CELL_TYPE_BUBBLE
            )
        else:
            cell = SelectionSortCell(
                i + 1, value_list[i], threadLock, (i, 1), cells,
                left_boundary, right_boundary, status_probe,
                disable_visualization=True, label=CELL_TYPE_SELECTION
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

    return cells, [cell_group], type_assignments


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


def extract_group_cell_type_pairs(cells, type_assignments):
    return [[cells[i].group.group_id, type_assignments[i]] for i in range(len(cells))]


def run_experiment(sorting_list, max_steps=15000):
    threadLock = threading.Lock()
    status_probe = StatusProbe()

    random.shuffle(sorting_list)
    cells, cell_groups, type_assignments = create_mixed_cells(
        sorting_list, threadLock, status_probe
    )

    snapshots = []
    with threadLock:
        snapshots.append(extract_group_cell_type_pairs(cells, type_assignments))

    threadLock.acquire()
    activate(cells, cell_groups)
    threadLock.release()

    prev_step_count = 0
    while True:
        with threadLock:
            done = no_cells_should_move(cells) or len(status_probe.sorting_steps) >= max_steps
            current_step_count = len(status_probe.sorting_steps)
            if current_step_count > prev_step_count:
                snapshots.append(extract_group_cell_type_pairs(cells, type_assignments))
                prev_step_count = current_step_count
        if done:
            break
        time.sleep(0.001)

    with threadLock:
        snapshots.append(extract_group_cell_type_pairs(cells, type_assignments))
        kill_all_thread(cells, cell_groups)
        ground_truth_sorted = verify_sorted(cells)

    time.sleep(0.05)

    return snapshots, ground_truth_sorted


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_cells = 100
    num_experiments = 1000
    sorting_list = list(range(num_cells))

    target_dir = DATA_DIR / f"cell_type_with_group_id_random_dist_1000_tests_seed{seed}"
    target_dir.mkdir(exist_ok=True)

    print(f"Generating synchronized group_id distribution data: {num_experiments} experiments")
    print(f"Output: {target_dir}")
    print(f"Seed: {seed}")

    ground_truth_failures = []

    for i in range(num_experiments):
        if (i + 1) % 50 == 0:
            print(f"  Experiment {i + 1}/{num_experiments}")

        snapshots, sorted_ok = run_experiment(sorting_list.copy())

        if not sorted_ok:
            ground_truth_failures.append(i)

        np.save(target_dir / f"exp_{i}.npy", np.array(snapshots, dtype=object))

    if ground_truth_failures:
        print(f"\nWARNING: {len(ground_truth_failures)} ground truth failures detected!")
        for exp_idx in ground_truth_failures[:10]:
            print(f"  - experiment {exp_idx}")
        if len(ground_truth_failures) > 10:
            print(f"  ... and {len(ground_truth_failures) - 10} more")

    print(f"\nGroup ID data generation complete: {num_experiments} experiments saved (seed={seed}).")


if __name__ == "__main__":
    main(sys.argv[1:])
