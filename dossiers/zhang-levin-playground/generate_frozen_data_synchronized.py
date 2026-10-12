"""
Synchronized version of generate_frozen_data.py for race condition analysis.

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


def create_cells_within_one_group(value_list, threadLock, status_probe, cell_type, frozen_cell_number):
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

    period = 1000000000
    start_count_down = 1000000000
    cell_group = CellGroup(cells, cells, 0, left_boundary, right_boundary, GroupStatus.ACTIVE, threadLock, start_count_down, period)
    for cell in cells:
        cell.group = cell_group
    for _ in range(frozen_cell_number):
        cells[random.randint(0, len(cells) - 1)].set_cell_to_freeze()

    return cells, [cell_group]


def no_cells_should_move(cells):
    for c in cells:
        if c.status in (CellStatus.SLEEP, CellStatus.MOVING):
            return False
        if c.status == CellStatus.ACTIVE and c.should_move():
            return False
    return True


def verify_stable(cells):
    values = [c.value for c in cells]
    for i in range(len(values) - 1):
        left_frozen = cells[i].status == CellStatus.FREEZE
        right_frozen = cells[i + 1].status == CellStatus.FREEZE
        if values[i] > values[i + 1] and not (left_frozen or right_frozen):
            return False
    return True


def kill_all_thread(cells, groups):
    for c in cells:
        if c.status != CellStatus.FREEZE:
            c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def activate(cells, cell_groups):
    for cell in cells:
        if cell.status != CellStatus.FREEZE:
            cell.start()
    for group in cell_groups:
        group.start()


def run_experiment(sorting_list, threadLock, cell_type, frozen_cell_num):
    status_probe = StatusProbe()
    cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, cell_type, frozen_cell_num)

    threadLock.acquire()
    activate(cells, cell_groups)
    threadLock.release()

    while True:
        with threadLock:
            done = no_cells_should_move(cells)
        if done:
            break
        time.sleep(0.001)

    with threadLock:
        kill_all_thread(cells, cell_groups)
        ground_truth_stable = verify_stable(cells)

    time.sleep(0.1)
    return (
        status_probe.sorting_steps,
        status_probe.frozen_swap_attempts,
        status_probe.cell_types,
        ground_truth_stable,
    )


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_experiments = 100
    ground_truth_failures = []

    for frozen_cell_num in [0, 1, 2, 3, 4, 5]:
        sorting_list = [i for i in range(100)]

        for cell_type in ['bubble', 'selection', 'insertion']:
            sorting_steps = []
            sorting_frozen_swap_count = []
            sorting_cell_types = []

            for i in range(num_experiments):
                threadLock = threading.Lock()
                random.shuffle(sorting_list)
                initial_state = sorting_list.copy()

                print(f">>>>>>>>>>>>>>>>> {cell_type} with {frozen_cell_num} frozen: experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
                steps, frozen_swaps, cell_types, stable_ok = run_experiment(
                    sorting_list.copy(), threadLock, cell_type, frozen_cell_num
                )

                sorting_steps.append(steps)
                sorting_frozen_swap_count.append(frozen_swaps)
                sorting_cell_types.append(cell_types)

                if not stable_ok:
                    ground_truth_failures.append((cell_type, frozen_cell_num, i, initial_state))

                print("Sorting complete.\n")

            sorting_process_steps = np.array(sorting_steps, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_cannot_move_steps_100exps_seed{seed}', sorting_process_steps)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_steps_100exps_seed{seed}', sorting_process_steps)

            sorting_frozen_swap = np.array(sorting_frozen_swap_count, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_frozen_swap_count_100exps_seed{seed}', sorting_frozen_swap)

            sorting_cell_types_arr = np.array(sorting_cell_types, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_steps_cell_type_100exps_seed{seed}', sorting_cell_types_arr)

    if ground_truth_failures:
        print(f"\nWARNING: {len(ground_truth_failures)} ground truth failures detected!")
        for alg, frozen, exp_idx, _ in ground_truth_failures:
            print(f"  - {alg} ({frozen} frozen) experiment {exp_idx}")

    print(f"\nData saved to {DATA_DIR} (seed={seed})")


if __name__ == "__main__":
    main(sys.argv[1:])
