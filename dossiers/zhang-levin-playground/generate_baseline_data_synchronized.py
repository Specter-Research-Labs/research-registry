"""
Synchronized version of generate_baseline_data.py for race condition analysis.

Differences from original:
1. Lock around is_sorted() completion check
2. Deterministic seeding via command-line arg
3. Ground truth verification after threads stop
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


def create_cells_within_one_group(value_list, threadLock, status_probe, cell_type):
    if len(value_list) == 0:
        return []
    left_boundary = (0, 1)
    right_boundary = (len(value_list) - 1, 1)
    cells = []
    for i in range(0, len(value_list)):
        cell = None
        if cell_type == 'selection':
            cell = SelectionSortCell(i + 1, value_list[i], threadLock, (i, 1), cells, left_boundary, right_boundary, status_probe, disable_visualization=True)
        if cell_type == 'bubble':
            cell = BubbleSortCell(i + 1, value_list[i], threadLock, (i, 1), cells, left_boundary, right_boundary, status_probe, disable_visualization=True)
        if cell_type == 'insertion':
            cell = InsertionSortCell(i + 1, value_list[i], threadLock, (i, 1), cells, left_boundary, right_boundary, status_probe, disable_visualization=True)
        cells.append(cell)
        if cell_type == 'insertion':
            cells[0].enable_to_move = True

    period = 100000000
    start_count_down = 100000000
    cell_group = CellGroup(cells, cells, 0, left_boundary, right_boundary, GroupStatus.ACTIVE, threadLock, start_count_down, period)
    for cell in cells:
        cell.group = cell_group
    return cells, [cell_group]


def is_sorted(cells):
    prev_cell = cells[0]
    for c in cells:
        if c.value < prev_cell.value:
            return False
        prev_cell = c
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


def run_experiment(sorting_list, threadLock, cell_type):
    status_probe = StatusProbe()
    cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, cell_type)

    threadLock.acquire()
    activate(cells, cell_groups)
    threadLock.release()

    while True:
        with threadLock:
            done = is_sorted(cells)
        if done:
            break
        time.sleep(0.0001)

    with threadLock:
        kill_all_thread(cells, cell_groups)
        ground_truth_sorted = verify_sorted(cells)

    time.sleep(0.1)
    return status_probe.sorting_steps, ground_truth_sorted


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sorting_list = [i for i in range(100)]
    sorting_steps_for_each_run_bubble = []
    sorting_steps_for_each_run_selection = []
    sorting_steps_for_each_run_insertion = []
    ground_truth_failures = []

    num_experiments = 100

    for i in range(num_experiments):
        threadLock = threading.Lock()
        random.shuffle(sorting_list)
        initial_state = sorting_list.copy()

        print(f">>>>>>>>>>>>>>>>> Bubble experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        steps, sorted_ok = run_experiment(sorting_list.copy(), threadLock, 'bubble')
        sorting_steps_for_each_run_bubble.append(steps)
        if not sorted_ok:
            ground_truth_failures.append(('bubble', i, initial_state))
        print("Sorting complete.\n")

        print(f">>>>>>>>>>>>>>>>> Selection experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        steps, sorted_ok = run_experiment(sorting_list.copy(), threadLock, 'selection')
        sorting_steps_for_each_run_selection.append(steps)
        if not sorted_ok:
            ground_truth_failures.append(('selection', i, initial_state))
        print("Sorting complete.\n")

        print(f">>>>>>>>>>>>>>>>> Insertion experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        steps, sorted_ok = run_experiment(sorting_list.copy(), threadLock, 'insertion')
        sorting_steps_for_each_run_insertion.append(steps)
        if not sorted_ok:
            ground_truth_failures.append(('insertion', i, initial_state))
        print("Sorting complete.\n")

    sorting_process_steps_bubble = np.array(sorting_steps_for_each_run_bubble, dtype=object)
    np.save(DATA_DIR / f'bubble_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_bubble)

    sorting_process_steps_selection = np.array(sorting_steps_for_each_run_selection, dtype=object)
    np.save(DATA_DIR / f'selection_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_selection)

    sorting_process_steps_insertion = np.array(sorting_steps_for_each_run_insertion, dtype=object)
    np.save(DATA_DIR / f'insertion_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_insertion)

    if ground_truth_failures:
        print(f"\nWARNING: {len(ground_truth_failures)} ground truth failures detected!")
        for alg, exp_idx, _ in ground_truth_failures:
            print(f"  - {alg} experiment {exp_idx}")

    print(f"\nData saved to {DATA_DIR} (seed={seed})")


if __name__ == "__main__":
    main(sys.argv[1:])
