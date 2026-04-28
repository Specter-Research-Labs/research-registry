"""
Generate small-scale sorting data for point cloud analysis.

Usage: uv run python generate_20point_data.py --seed 42

"20 points" = 20 experiments with 10 cells each (smaller scale for visualization).
Used by analysis/points_cloud_size_change.py to study how the "cloud" of cell
states evolves during sorting.

Produces:
- bubble_sort_20_points_sorting_steps_seed{seed}.npy
- selection_sort_20_points_sorting_steps_seed{seed}.npy
"""

import sys
import argparse
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

DATA_DIR = resolve_artifact_dir("data", Path(__file__).parent / "data")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Generate 20-point sorting data")
    parser.add_argument("--seed", type=int, required=True, help="Random seed")
    return parser.parse_args(argv)


def create_cells_within_one_group(value_list, threadLock, status_probe, cell_type):
    if len(value_list) == 0:
        return []
    left_boundary = (0, 1)
    right_boundary = (len(value_list) - 1, 1)
    cells = []

    for i in range(len(value_list)):
        if cell_type == 'bubble':
            cell = BubbleSortCell(
                i + 1, value_list[i], threadLock, (i, 1), cells,
                left_boundary, right_boundary, status_probe, disable_visualization=True
            )
        else:
            cell = SelectionSortCell(
                i + 1, value_list[i], threadLock, (i, 1), cells,
                left_boundary, right_boundary, status_probe, disable_visualization=True
            )
        cells.append(cell)

    period = 100000000
    start_count_down = 100000000
    cell_group = CellGroup(
        cells, cells, 0, left_boundary, right_boundary,
        GroupStatus.ACTIVE, threadLock, start_count_down, period
    )
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
    args = parse_args(argv)
    seed = args.seed
    random.seed(seed)
    np.random.seed(seed)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    num_cells = 10
    num_experiments = 20

    sorting_list = list(range(num_cells))

    print(f"Generating 20-point data: {num_experiments} experiments with {num_cells} cells each, seed {seed}")
    print(f"Output: {DATA_DIR}")

    for cell_type in ['bubble', 'selection']:
        sorting_steps_all = []

        for i in range(num_experiments):
            threadLock = threading.Lock()
            random.shuffle(sorting_list)

            print(f"  {cell_type} experiment {i + 1}/{num_experiments}")
            status_probe = StatusProbe()
            cells, cell_groups = create_cells_within_one_group(
                sorting_list, threadLock, status_probe, cell_type
            )

            threadLock.acquire()
            activate(cells, cell_groups)
            threadLock.release()

            while not is_sorted(cells):
                time.sleep(0.0001)

            threadLock.acquire()
            kill_all_thread(cells, cell_groups)
            threadLock.release()

            sorting_steps_all.append(status_probe.sorting_steps)
            time.sleep(0.1)

        sorting_process_steps = np.array(sorting_steps_all, dtype=object)
        np.save(DATA_DIR / f'{cell_type}_sort_20_points_sorting_steps_seed{seed}', sorting_process_steps)
        print(f"  Saved {cell_type}_sort_20_points_sorting_steps_seed{seed}.npy")

    print("\n20-point data generation complete.")


if __name__ == "__main__":
    main(sys.argv[1:])
