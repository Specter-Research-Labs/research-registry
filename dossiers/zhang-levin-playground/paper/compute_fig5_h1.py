from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from enum import Enum
from pathlib import Path

import numpy as np
from ripser import ripser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.GnomeSortCell import GnomeSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import ExtendedStatusProbe

ONE_D_CLASSES = {
    "Bubble": BubbleSortCell,
    "Selection": SelectionSortCell,
    "Insertion": InsertionSortCell,
    "Gnome": GnomeSortCell,
}


class CellStatus2D(Enum):
    ACTIVE = 1
    FROZEN = 2


class Cell2DBase:
    def __init__(self, value: int, position: tuple[int, int], cell_type: str):
        self.value = value
        self.position = position
        self.cell_type = cell_type
        self.status = CellStatus2D.ACTIVE
        self.grid: Grid2D | None = None

    def get_neighbors(self) -> list["Cell2DBase"]:
        if self.grid is None:
            return []
        neighbors = []
        for dx, dy in self.grid.neighbor_deltas:
            nx, ny = self.position[0] + dx, self.position[1] + dy
            if 0 <= nx < self.grid.width and 0 <= ny < self.grid.height:
                neighbor = self.grid.get_cell_at(nx, ny)
                if neighbor is not None:
                    neighbors.append(neighbor)
        return neighbors

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        raise NotImplementedError

    def distance_from_origin(self) -> int:
        return self.position[0] ** 2 + self.position[1] ** 2


class Bubble2DCell(Cell2DBase):
    def __init__(self, value: int, position: tuple[int, int]):
        super().__init__(value, position, "Bubble2D")

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if neighbor.status == CellStatus2D.FROZEN:
            return False
        my_dist = self.distance_from_origin()
        their_dist = neighbor.distance_from_origin()
        if my_dist < their_dist:
            return self.value > neighbor.value
        return self.value < neighbor.value


class Selection2DCell(Cell2DBase):
    def __init__(self, value: int, position: tuple[int, int], grid_size: int):
        super().__init__(value, position, "Selection2D")
        positions_by_distance = []
        for x in range(grid_size):
            for y in range(grid_size):
                positions_by_distance.append((x**2 + y**2, x, y))
        positions_by_distance.sort()
        _, ideal_x, ideal_y = positions_by_distance[value]
        self.ideal_position = (ideal_x, ideal_y)

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if neighbor.status == CellStatus2D.FROZEN:
            return False
        my_dist = (self.position[0] - self.ideal_position[0]) ** 2 + (
            self.position[1] - self.ideal_position[1]
        ) ** 2
        new_dist = (neighbor.position[0] - self.ideal_position[0]) ** 2 + (
            neighbor.position[1] - self.ideal_position[1]
        ) ** 2
        return new_dist < my_dist


class Grid2D:
    def __init__(self, width: int, height: int, connectivity: int):
        if connectivity not in (4, 8):
            raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
        self.width = width
        self.height = height
        self.cells: dict[tuple[int, int], Cell2DBase] = {}
        self.neighbor_deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if connectivity == 8:
            self.neighbor_deltas.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])

    def add_cell(self, cell: Cell2DBase) -> None:
        self.cells[cell.position] = cell
        cell.grid = self

    def get_cell_at(self, x: int, y: int) -> Cell2DBase | None:
        return self.cells.get((x, y))

    def swap_cells(self, cell_a: Cell2DBase, cell_b: Cell2DBase) -> None:
        pos_a, pos_b = cell_a.position, cell_b.position
        cell_a.position, cell_b.position = pos_b, pos_a
        self.cells[pos_a] = cell_b
        self.cells[pos_b] = cell_a

    def all_cells(self) -> list[Cell2DBase]:
        return list(self.cells.values())


def _kill_all(cells: list, cell_group: CellGroup) -> None:
    for cell in cells:
        cell.status = CellStatus.INACTIVE
    cell_group.status = GroupStatus.MERGED


def _is_sorted_1d(cells: list) -> bool:
    prev_val = -1
    for cell in cells:
        if cell.status == CellStatus.FREEZE:
            continue
        if cell.value < prev_val:
            return False
        prev_val = cell.value
    return True


def _interaction_distance_matrix(probe: ExtendedStatusProbe, n_cells: int) -> np.ndarray:
    interaction_matrix = np.zeros((n_cells, n_cells), dtype=np.float64)
    for (id_a, id_b), count in probe.interaction_graph.items():
        index_a = id_a - 1
        index_b = id_b - 1
        if 0 <= index_a < n_cells and 0 <= index_b < n_cells:
            interaction_matrix[index_a, index_b] += count
            interaction_matrix[index_b, index_a] += count
    distances = 1.0 / (1.0 + interaction_matrix)
    np.fill_diagonal(distances, 0.0)
    return distances


def _h1_count(distance_matrix: np.ndarray) -> int:
    result = ripser(distance_matrix, maxdim=1, distance_matrix=True)
    return int(len(result["dgms"][1]))


def run_1d_trial(
    cell_types: list[str],
    *,
    n_cells: int,
    timeout: float,
    trial_seed: int,
) -> int:
    random.seed(trial_seed)
    probe = ExtendedStatusProbe()
    lock = threading.Lock()
    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)

    values = list(range(n_cells))
    random.shuffle(values)

    type_assignment = []
    for idx, cell_type in enumerate(cell_types):
        count = n_cells // len(cell_types)
        if idx < n_cells % len(cell_types):
            count += 1
        type_assignment.extend([cell_type] * count)
    random.shuffle(type_assignment)

    cells: list = []
    for idx, cell_type in enumerate(type_assignment):
        cell_class = ONE_D_CLASSES[cell_type]
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

    with lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start = time.time()
    while time.time() - start < timeout:
        with lock:
            done = _is_sorted_1d(cells)
        if done:
            break
        time.sleep(0.02)

    with lock:
        _kill_all(cells, cell_group)

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return _h1_count(_interaction_distance_matrix(probe, n_cells))


def create_2d_grid(
    size: int,
    *,
    connectivity: int,
    cell_class: type[Cell2DBase],
    trial_seed: int,
) -> Grid2D:
    random.seed(trial_seed)
    grid = Grid2D(size, size, connectivity)

    values = list(range(size * size))
    random.shuffle(values)
    positions = [(x, y) for x in range(size) for y in range(size)]
    random.shuffle(positions)

    for idx, position in enumerate(positions):
        if cell_class is Selection2DCell:
            cell = cell_class(values[idx], position, size)
        else:
            cell = cell_class(values[idx], position)
        grid.add_cell(cell)

    return grid


def shell_inversion_count(grid: Grid2D) -> int:
    cells_by_distance: dict[int, list[int]] = {}
    for cell in grid.all_cells():
        if cell.status == CellStatus2D.FROZEN:
            continue
        cells_by_distance.setdefault(cell.distance_from_origin(), []).append(cell.value)

    inversions = 0
    sorted_distances = sorted(cells_by_distance)
    for index, dist_left in enumerate(sorted_distances):
        for dist_right in sorted_distances[index + 1 :]:
            for value_left in cells_by_distance[dist_left]:
                for value_right in cells_by_distance[dist_right]:
                    if value_left > value_right:
                        inversions += 1
    return inversions


def run_2d_trial(
    *,
    size: int,
    connectivity: int,
    cell_class: type[Cell2DBase],
    max_steps: int,
    trial_seed: int,
) -> dict:
    grid = create_2d_grid(
        size,
        connectivity=connectivity,
        cell_class=cell_class,
        trial_seed=trial_seed,
    )
    swap_pairs: list[tuple[int, int]] = []

    for _ in range(max_steps):
        made_swap = False
        cells = grid.all_cells()
        random.shuffle(cells)
        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue
            neighbors = cell.get_neighbors()
            random.shuffle(neighbors)
            for neighbor in neighbors:
                if cell.should_swap_with(neighbor):
                    swap_pairs.append((cell.value, neighbor.value))
                    grid.swap_cells(cell, neighbor)
                    made_swap = True
                    break
            if made_swap:
                break
        if shell_inversion_count(grid) == 0 or not made_swap:
            break

    interaction_matrix = np.zeros((size * size, size * size), dtype=np.float64)
    for value_a, value_b in swap_pairs:
        interaction_matrix[value_a, value_b] += 1
        interaction_matrix[value_b, value_a] += 1
    distances = 1.0 / (1.0 + interaction_matrix)
    np.fill_diagonal(distances, 0.0)

    return {
        "sorted": shell_inversion_count(grid) == 0,
        "h1_count": _h1_count(distances),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute Figure 5 H1 summary directly")
    parser.add_argument("--n-cells", type=int, default=30)
    parser.add_argument("--n-trials-1d", type=int, default=30)
    parser.add_argument("--timeout-1d", type=float, default=3.0)
    parser.add_argument("--grid-size", type=int, default=6)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument("--n-trials-2d", type=int, default=30)
    parser.add_argument("--max-steps-2d", type=int, default=None)
    parser.add_argument("--base-seed", type=int, default=20260306)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/fig5_h1_bar.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    rng = random.Random(args.base_seed)

    one_d_configs = [
        (["Bubble"], "Pure Bubble"),
        (["Selection"], "Pure Selection"),
        (["Insertion"], "Pure Insertion"),
        (["Gnome"], "Pure Gnome"),
        (["Bubble", "Selection"], "Bubble+Selection"),
    ]

    h1_1d = []
    for cell_types, label in one_d_configs:
        print(f"Running 1D {label} ({args.n_trials_1d} trials)...")
        counts = []
        for _ in range(args.n_trials_1d):
            counts.append(
                run_1d_trial(
                    cell_types,
                    n_cells=args.n_cells,
                    timeout=args.timeout_1d,
                    trial_seed=rng.randrange(2**32),
                )
            )
        h1_1d.append(
            {
                "label": label,
                "mean": round(float(np.mean(counts)), 6),
                "std": round(float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0, 6),
                "n_trials": args.n_trials_1d,
            }
        )

    max_steps_2d = args.max_steps_2d or (30 * args.grid_size * args.grid_size)
    two_d_configs = [
        (Bubble2DCell, "Bubble2D"),
        (Selection2DCell, "Selection2D"),
    ]

    h1_2d = []
    for cell_class, label in two_d_configs:
        print(f"Running 2D {label} ({args.n_trials_2d} trials)...")
        counts = []
        successes = 0
        for _ in range(args.n_trials_2d):
            result = run_2d_trial(
                size=args.grid_size,
                connectivity=args.connectivity,
                cell_class=cell_class,
                max_steps=max_steps_2d,
                trial_seed=rng.randrange(2**32),
            )
            counts.append(result["h1_count"])
            successes += int(result["sorted"])
        h1_2d.append(
            {
                "label": label,
                "mean": round(float(np.mean(counts)), 6),
                "std": round(float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0, 6),
                "success": round(successes / args.n_trials_2d, 6),
                "n_trials": args.n_trials_2d,
            }
        )

    out_obj = {
        "h1_1d": h1_1d,
        "h1_2d": h1_2d,
        "provenance": {
            "generator": "paper/compute_fig5_h1.py",
            "n_cells": args.n_cells,
            "n_trials_1d": args.n_trials_1d,
            "timeout_1d": args.timeout_1d,
            "grid_size": args.grid_size,
            "connectivity": args.connectivity,
            "n_trials_2d": args.n_trials_2d,
            "max_steps_2d": max_steps_2d,
            "base_seed": args.base_seed,
            "distance_metric": "1 / (1 + swap_count)",
            "homology": "H1 count from ripser with maxdim=1",
            "two_d_target": "shell ordering by squared distance from origin",
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
