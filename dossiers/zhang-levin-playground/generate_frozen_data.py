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
    for i in range(frozen_cell_number):
        cells[random.randint(0, len(cells) - 1)].set_cell_to_freeze()

    return cells, [cell_group]


def no_cells_should_move(cells):
    for c in cells:
        if c.status == CellStatus.SLEEP:
            return False
        if c.status == CellStatus.ACTIVE and c.should_move():
            return False
    return True


def kill_all_thread(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE

    for g in groups:
        g.status = GroupStatus.MERGED


def activate(cells, cell_groups):
    for cell in cells:
        if cell.status != CellStatus.FREEZE:
            cell.start()

    for group in cell_groups:
        group.start()


def main(argv):
    seed = int(argv[0]) if argv else 42
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_experiments = 100

    for frozen_cell_num in [0, 1, 2, 3, 4, 5]:
        sorting_list = [i for i in range(100)]

        for cell_type in ['bubble', 'selection', 'insertion']:
            sorting_steps = []
            sorting_frozen_swap_count = []
            sorting_cell_types = []

            for i in range(num_experiments):
                threadLock = threading.Lock()
                random.shuffle(sorting_list)

                print(f">>>>>>>>>>>>>>>>> {cell_type} with {frozen_cell_num} frozen: experiment {i + 1}/{num_experiments} <<<<<<<<<<<<<<<<<<<<")
                status_probe = StatusProbe()
                cells, cell_groups = create_cells_within_one_group(sorting_list, threadLock, status_probe, cell_type, frozen_cell_num)

                threadLock.acquire()
                activate(cells, cell_groups)
                threadLock.release()

                while not no_cells_should_move(cells):
                    time.sleep(0.001)

                threadLock.acquire()
                kill_all_thread(cells, cell_groups)
                threadLock.release()

                sorting_steps.append(status_probe.sorting_steps)
                sorting_frozen_swap_count.append(status_probe.frozen_swap_attempts)
                sorting_cell_types.append(status_probe.cell_types)

                print("Sorting complete.\n")
                time.sleep(0.1)

            sorting_process_steps = np.array(sorting_steps, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_cannot_move_steps_100exps_seed{seed}', sorting_process_steps)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_steps_100exps_seed{seed}', sorting_process_steps)

            sorting_frozen_swap = np.array(sorting_frozen_swap_count, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_frozen_swap_count_100exps_seed{seed}', sorting_frozen_swap)

            sorting_cell_types_arr = np.array(sorting_cell_types, dtype=object)
            np.save(DATA_DIR / f'{cell_type}_sort_sorting_with_{frozen_cell_num}frozen_steps_cell_type_100exps_seed{seed}', sorting_cell_types_arr)

    print(f"Data saved to {DATA_DIR} (seed={seed})")


if __name__ == "__main__":
    main(sys.argv[1:])
