import sys
import getopt
import threading
import time
from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus
import random
import numpy as np
from pathlib import Path
from paths import resolve_artifact_dir

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data")


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


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    sorting_list = [i for i in range(100)]
    sorting_steps_for_each_run_bubble = []
    sorting_steps_for_each_run_selection = []
    sorting_steps_for_each_run_insertion = []

    num_experiments = 100

    for i in range(num_experiments):
        threadLock = threading.Lock()
        random.shuffle(sorting_list)

        print(f">>>>>>>>>>>>>>>>> Bubble experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        status_probe = StatusProbe()
        cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, 'bubble')
        threadLock.acquire()
        activate(cells, cell_groups)
        threadLock.release()

        while not is_sorted(cells):
            time.sleep(0.0001)
        threadLock.acquire()
        kill_all_thread(cells, cell_groups)
        threadLock.release()
        sorting_steps_for_each_run_bubble.append(status_probe.sorting_steps)
        print("Sorting complete.\n")
        time.sleep(0.1)

        print(f">>>>>>>>>>>>>>>>> Selection experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        status_probe = StatusProbe()
        cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, 'selection')
        threadLock.acquire()
        activate(cells, cell_groups)
        threadLock.release()

        while not is_sorted(cells):
            time.sleep(0.0001)
        threadLock.acquire()
        kill_all_thread(cells, cell_groups)
        threadLock.release()
        sorting_steps_for_each_run_selection.append(status_probe.sorting_steps)
        print("Sorting complete.\n")
        time.sleep(0.1)

        print(f">>>>>>>>>>>>>>>>> Insertion experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
        status_probe = StatusProbe()
        cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, 'insertion')
        threadLock.acquire()
        activate(cells, cell_groups)
        threadLock.release()

        while not is_sorted(cells):
            time.sleep(0.0001)
        threadLock.acquire()
        kill_all_thread(cells, cell_groups)
        threadLock.release()
        sorting_steps_for_each_run_insertion.append(status_probe.sorting_steps)
        print("Sorting complete.\n")
        time.sleep(0.1)

    sorting_process_steps_bubble = np.array(sorting_steps_for_each_run_bubble, dtype=object)
    np.save(DATA_DIR / f'bubble_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_bubble)

    sorting_process_steps_selection = np.array(sorting_steps_for_each_run_selection, dtype=object)
    np.save(DATA_DIR / f'selection_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_selection)

    sorting_process_steps_insertion = np.array(sorting_steps_for_each_run_insertion, dtype=object)
    np.save(DATA_DIR / f'insertion_sort_sorting_steps_100exps_seed{seed}', sorting_process_steps_insertion)

    print(f"Data saved to {DATA_DIR} (seed={seed})")


if __name__ == "__main__":
    main(sys.argv[1:])
