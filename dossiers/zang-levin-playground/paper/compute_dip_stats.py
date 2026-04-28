"""Compute dip statistics and fixed-seed exemplar trajectories for the paper.

Usage:
  uv run python paper/compute_dip_stats.py

Default conditions:
  1D Bubble    (n=30, 3 movable frozen)
  1D Selection (n=30, 3 movable frozen)
  2D Bubble    (grid=6, 3 immovable frozen, conn=4, shell ordering)
  2D Selection (grid=6, 3 immovable frozen, conn=4, shell ordering)

Outputs:
  paper/results/dip_stats.json
  paper/results/fig4_dip_trajectories.json
"""

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
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import StatusProbe


def find_dips(trajectory: list[int]) -> list[dict]:
    if len(trajectory) < 3:
        return []

    from scipy.signal import find_peaks

    arr = np.array(trajectory)
    peaks, _ = find_peaks(arr, prominence=1)

    dips = []
    for peak_idx in peaks:
        peak_val = int(arr[peak_idx])

        start_idx = peak_idx
        while start_idx > 0 and arr[start_idx - 1] < arr[start_idx]:
            start_idx -= 1
        start_val = int(arr[start_idx])

        end_idx = peak_idx
        while end_idx < len(arr) and arr[end_idx] > start_val:
            end_idx += 1

        if end_idx < len(arr):
            dips.append(
                {
                    "start_idx": int(start_idx),
                    "peak_idx": int(peak_idx),
                    "end_idx": int(end_idx),
                    "start_val": start_val,
                    "peak_val": peak_val,
                    "depth": peak_val - start_val,
                }
            )

    return dips


def get_monotonicity(arr: list[int]) -> int:
    if len(arr) < 2:
        return 0
    errors = 0
    prev = arr[0]
    for idx in range(1, len(arr)):
        if arr[idx] < prev:
            errors += 1
        prev = arr[idx]
    return errors


class TrackingProbe(StatusProbe):
    def __init__(self) -> None:
        super().__init__()
        self.monotonicity_history: list[int] = []

    def record_sorting_step(self, step) -> None:
        super().record_sorting_step(step)
        self.monotonicity_history.append(get_monotonicity(step))


def run_1d_trial(
    *,
    n_cells: int,
    cell_class: type,
    n_frozen: int,
    timeout: float,
    trial_seed: int,
) -> dict:
    random.seed(trial_seed)
    values = list(range(n_cells))
    random.shuffle(values)

    lock = threading.Lock()
    probe = TrackingProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells: list = []

    for idx in range(n_cells):
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

    if n_frozen > 0:
        frozen_indices = set(random.sample(range(n_cells), n_frozen))
        for idx in frozen_indices:
            cells[idx].set_cell_to_freeze()

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

    def is_done() -> bool:
        prev = -1
        for cell in cells:
            if cell.status == CellStatus.FREEZE:
                continue
            if cell.value < prev:
                return False
            prev = cell.value
        return True

    start = time.time()
    while not is_done() and time.time() - start < timeout:
        time.sleep(0.02)

    success = is_done()
    trajectory = probe.monotonicity_history.copy()

    with lock:
        for cell in cells:
            cell.status = CellStatus.INACTIVE
        cell_group.status = GroupStatus.MERGED

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        "success": success,
        "trajectory": trajectory,
        "dips": find_dips(trajectory),
        "n_frozen": n_frozen,
        "trial_seed": trial_seed,
    }


class CellStatus2D:
    ACTIVE = 1
    FROZEN = 2


def shell_order_positions(size: int) -> list[tuple[int, int]]:
    positions_by_distance = []
    for x in range(size):
        for y in range(size):
            positions_by_distance.append((x**2 + y**2, x, y))
    positions_by_distance.sort()
    return [(x, y) for _, x, y in positions_by_distance]


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
    def __init__(
        self,
        value: int,
        position: tuple[int, int],
        order_positions: list[tuple[int, int]],
    ):
        super().__init__(value, position, "Selection2D")
        self.ideal_position = order_positions[value]

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
    def __init__(
        self,
        width: int,
        height: int,
        connectivity: int,
        order_positions: list[tuple[int, int]],
    ):
        if connectivity not in (4, 8):
            raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
        self.width = width
        self.height = height
        self.connectivity = connectivity
        self.order_positions = order_positions
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

    def get_all_cells(self) -> list[Cell2DBase]:
        return list(self.cells.values())


class FenwickTree:
    def __init__(self, size: int) -> None:
        self.size = size
        self.tree = [0] * (size + 1)

    def add(self, index: int, delta: int) -> None:
        index += 1
        while index <= self.size:
            self.tree[index] += delta
            index += index & -index

    def prefix_sum(self, index: int) -> int:
        total = 0
        index += 1
        while index > 0:
            total += self.tree[index]
            index -= index & -index
        return total


def shell_inversion_count(grid: Grid2D) -> int:
    cells_by_distance: dict[int, list[int]] = {}
    for cell in grid.get_all_cells():
        if cell.status == CellStatus2D.FROZEN:
            continue
        cells_by_distance.setdefault(cell.distance_from_origin(), []).append(cell.value)

    if not cells_by_distance:
        return 0

    max_value = max(
        value for values in cells_by_distance.values() for value in values
    ) + 1
    seen = FenwickTree(max_value)
    seen_count = 0
    inversions = 0

    for distance in sorted(cells_by_distance):
        group_values = cells_by_distance[distance]
        for value in group_values:
            inversions += seen_count - seen.prefix_sum(value)
        for value in group_values:
            seen.add(value, 1)
            seen_count += 1

    return inversions


def create_2d_grid(
    size: int,
    n_frozen: int,
    cell_class: type[Cell2DBase],
    *,
    connectivity: int,
    trial_seed: int,
) -> Grid2D:
    random.seed(trial_seed)
    order_positions = shell_order_positions(size)
    grid = Grid2D(size, size, connectivity, order_positions)

    values = list(range(size * size))
    random.shuffle(values)
    positions = [(x, y) for x in range(size) for y in range(size)]
    random.shuffle(positions)

    for idx, position in enumerate(positions):
        if cell_class is Selection2DCell:
            cell = cell_class(values[idx], position, order_positions)
        else:
            cell = cell_class(values[idx], position)
        grid.add_cell(cell)

    if n_frozen > 0:
        cells = grid.get_all_cells()
        for cell in random.sample(cells, min(n_frozen, len(cells))):
            cell.status = CellStatus2D.FROZEN

    return grid


def run_2d_trial(
    *,
    size: int,
    n_frozen: int,
    cell_class: type[Cell2DBase],
    connectivity: int,
    max_steps: int,
    trial_seed: int,
) -> dict:
    grid = create_2d_grid(
        size,
        n_frozen,
        cell_class,
        connectivity=connectivity,
        trial_seed=trial_seed,
    )

    inversion_count = shell_inversion_count(grid)
    trajectory = [inversion_count]

    for _ in range(max_steps):
        made_swap = False
        cells = grid.get_all_cells()
        random.shuffle(cells)

        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue
            neighbors = cell.get_neighbors()
            random.shuffle(neighbors)
            for neighbor in neighbors:
                if cell.should_swap_with(neighbor):
                    grid.swap_cells(cell, neighbor)
                    made_swap = True
                    break
            if made_swap:
                break

        inversion_count = shell_inversion_count(grid)
        trajectory.append(inversion_count)

        if inversion_count == 0 or not made_swap:
            break

    return {
        "sorted": inversion_count == 0,
        "trajectory": trajectory,
        "dips": find_dips(trajectory),
        "grid_size": size,
        "n_frozen": n_frozen,
        "connectivity": connectivity,
        "trial_seed": trial_seed,
    }


def compute_condition_stats(trial_results: list[dict]) -> dict:
    all_dips = []
    for result in trial_results:
        all_dips.extend(result["dips"])

    trials_with_dips = sum(1 for result in trial_results if result["dips"])
    dip_counts = [len(result["dips"]) for result in trial_results]
    recovery_steps = [dip["end_idx"] - dip["peak_idx"] for dip in all_dips]

    return {
        "n_trials": len(trial_results),
        "dip_rate": trials_with_dips / len(trial_results),
        "mean_dip_count": float(np.mean(dip_counts)),
        "mean_dip_depth": float(np.mean([dip["depth"] for dip in all_dips])) if all_dips else 0.0,
        "mean_recovery_steps": float(np.mean(recovery_steps)) if recovery_steps else 0.0,
    }


def select_exemplar(trial_results: list[dict]) -> dict:
    for result in trial_results:
        if result["dips"]:
            return result
    return trial_results[0]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute aggregate dip statistics")
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--base-seed", type=int, default=20260306)
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=["1d_bubble", "1d_selection", "2d_bubble", "2d_selection"],
        default=None,
        help="Optional subset of conditions to run.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Print progress every N trials.",
    )
    parser.add_argument("--n-cells-1d", type=int, default=30)
    parser.add_argument("--n-frozen-1d", type=int, default=3)
    parser.add_argument("--timeout-1d", type=float, default=20.0)
    parser.add_argument("--grid-size", type=int, default=6)
    parser.add_argument("--n-frozen-2d", type=int, default=3)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument("--max-steps-2d", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("paper/results/dip_stats.json"))
    parser.add_argument(
        "--traj-out",
        type=Path,
        default=Path("paper/results/fig4_dip_trajectories.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rng = random.Random(args.base_seed)
    max_steps_2d = args.max_steps_2d or (30 * args.grid_size * args.grid_size)

    conditions = [
        {
            "label": "1d_bubble",
            "dim": "1d",
            "key": ("1d", "bubble"),
            "cell_class": BubbleSortCell,
            "n_cells": args.n_cells_1d,
            "n_frozen": args.n_frozen_1d,
            "timeout": args.timeout_1d,
        },
        {
            "label": "1d_selection",
            "dim": "1d",
            "key": ("1d", "selection"),
            "cell_class": SelectionSortCell,
            "n_cells": args.n_cells_1d,
            "n_frozen": args.n_frozen_1d,
            "timeout": args.timeout_1d,
        },
        {
            "label": "2d_bubble",
            "dim": "2d",
            "key": ("2d", "bubble"),
            "cell_class": Bubble2DCell,
            "grid_size": args.grid_size,
            "n_frozen": args.n_frozen_2d,
            "connectivity": args.connectivity,
            "max_steps": max_steps_2d,
        },
        {
            "label": "2d_selection",
            "dim": "2d",
            "key": ("2d", "selection"),
            "cell_class": Selection2DCell,
            "grid_size": args.grid_size,
            "n_frozen": args.n_frozen_2d,
            "connectivity": args.connectivity,
            "max_steps": max_steps_2d,
        },
    ]

    if args.conditions is not None:
        selected = set(args.conditions)
        conditions = [condition for condition in conditions if condition["label"] in selected]

    all_stats: dict[str, dict] = {}
    fig4_payload: dict[str, dict] = {"1d": {}, "2d": {}}

    for condition in conditions:
        label = condition["label"]
        print(f"Running {label} ({args.n_trials} trials)...", flush=True)

        trial_results = []
        for trial_idx in range(args.n_trials):
            trial_seed = rng.randrange(2**32)
            if condition["dim"] == "1d":
                result = run_1d_trial(
                    n_cells=condition["n_cells"],
                    cell_class=condition["cell_class"],
                    n_frozen=condition["n_frozen"],
                    timeout=condition["timeout"],
                    trial_seed=trial_seed,
                )
            else:
                result = run_2d_trial(
                    size=condition["grid_size"],
                    n_frozen=condition["n_frozen"],
                    cell_class=condition["cell_class"],
                    connectivity=condition["connectivity"],
                    max_steps=condition["max_steps"],
                    trial_seed=trial_seed,
                )
            trial_results.append(result)
            if (trial_idx + 1) % args.progress_every == 0 or trial_idx + 1 == args.n_trials:
                print(f"  {trial_idx + 1}/{args.n_trials}", flush=True)

        stats = compute_condition_stats(trial_results)
        all_stats[label] = stats
        exemplar = select_exemplar(trial_results)
        fig4_payload[condition["key"][0]][condition["key"][1]] = exemplar

        print(
            f"  dip_rate={stats['dip_rate']:.2f}  "
            f"mean_count={stats['mean_dip_count']:.2f}  "
            f"mean_depth={stats['mean_dip_depth']:.2f}  "
            f"mean_recovery={stats['mean_recovery_steps']:.2f}",
            flush=True,
        )

    provenance = {
        "generator": "paper/compute_dip_stats.py",
        "n_trials": args.n_trials,
        "base_seed": args.base_seed,
        "conditions": [condition["label"] for condition in conditions],
        "one_d": {
            "n_cells": args.n_cells_1d,
            "n_frozen": args.n_frozen_1d,
            "timeout": args.timeout_1d,
            "semantics": "movable frozen cells",
        },
        "two_d": {
            "grid_size": args.grid_size,
            "n_frozen": args.n_frozen_2d,
            "connectivity": args.connectivity,
            "max_steps": max_steps_2d,
            "ordering": "shell ordering by squared distance from origin",
            "semantics": "immovable frozen cells",
        },
    }

    dip_stats_payload = {**all_stats, "provenance": provenance}
    fig4_payload["provenance"] = provenance

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dip_stats_payload, indent=2) + "\n")

    args.traj_out.parent.mkdir(parents=True, exist_ok=True)
    args.traj_out.write_text(json.dumps(fig4_payload, indent=2) + "\n")

    print(f"Wrote {args.out}", flush=True)
    print(f"Wrote {args.traj_out}", flush=True)


if __name__ == "__main__":
    main()
