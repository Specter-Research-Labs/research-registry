"""
EXPERIMENT 23: Alternate 2D Ordering Targets

We test alternate 2D ordering targets:
1) Row-major (monotone rows and columns)
2) Serpentine (boustrophedon space-filling path)
We also report row/col monotone success for row-major runs.

Algorithms:
- LocalOrder2D: local neighbor swap based on target order
- SelectionOrder2D: global target position based on target order
"""

from __future__ import annotations

import random
from enum import Enum

import numpy as np


class OrderMode(Enum):
    ROW_MAJOR = "row_major"
    SERPENTINE = "serpentine"


class CellStatus2D(Enum):
    ACTIVE = 1
    FROZEN = 2


def positions_row_major(size: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(size) for x in range(size)]


def positions_serpentine(size: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for y in range(size):
        xs = range(size) if y % 2 == 0 else range(size - 1, -1, -1)
        for x in xs:
            positions.append((x, y))
    return positions


def positions_for_mode(size: int, mode: OrderMode) -> list[tuple[int, int]]:
    if mode == OrderMode.ROW_MAJOR:
        return positions_row_major(size)
    if mode == OrderMode.SERPENTINE:
        return positions_serpentine(size)
    raise ValueError(f"unknown order mode: {mode}")


class Grid2D:
    def __init__(self, width: int, height: int, connectivity: int, order_positions: list[tuple[int, int]]):
        if connectivity not in (4, 8):
            raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
        self.width = width
        self.height = height
        self.connectivity = connectivity
        self.cells: dict[tuple[int, int], Cell2DBase] = {}
        self.order_positions = order_positions
        self.order_index = {pos: idx for idx, pos in enumerate(order_positions)}
        self.neighbor_deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if connectivity == 8:
            self.neighbor_deltas.extend([
                (-1, -1), (-1, 1), (1, -1), (1, 1),
            ])

    def add_cell(self, cell: "Cell2DBase") -> None:
        self.cells[cell.position] = cell
        cell.grid = self

    def get_cell_at(self, x: int, y: int) -> "Cell2DBase | None":
        return self.cells.get((x, y))

    def swap_cells(self, cell1: "Cell2DBase", cell2: "Cell2DBase") -> None:
        pos1, pos2 = cell1.position, cell2.position
        cell1.position, cell2.position = pos2, pos1
        self.cells[pos1] = cell2
        self.cells[pos2] = cell1

    def get_all_cells(self) -> list["Cell2DBase"]:
        return list(self.cells.values())


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


class LocalOrder2DCell(Cell2DBase):
    def __init__(self, value: int, position: tuple[int, int]):
        super().__init__(value, position, "LocalOrder2D")

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if self.grid is None:
            return False
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_rank = self.grid.order_index[self.position]
        their_rank = self.grid.order_index[neighbor.position]

        if my_rank < their_rank:
            return self.value > neighbor.value
        if my_rank > their_rank:
            return self.value < neighbor.value
        return False


class SelectionOrder2DCell(Cell2DBase):
    def __init__(self, value: int, position: tuple[int, int], size: int, order_positions: list[tuple[int, int]]):
        super().__init__(value, position, "SelectionOrder2D")
        if value < 0 or value >= size * size:
            raise ValueError(f"value out of range for size {size}: {value}")
        self.grid_size = size
        self.ideal_position = order_positions[value]

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if self.grid is None:
            return False
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = (self.position[0] - self.ideal_position[0]) ** 2 + (
            self.position[1] - self.ideal_position[1]
        ) ** 2
        new_dist = (neighbor.position[0] - self.ideal_position[0]) ** 2 + (
            neighbor.position[1] - self.ideal_position[1]
        ) ** 2
        return new_dist < my_dist

def create_grid(size: int, mode: OrderMode, connectivity: int, n_frozen: int, cell_class):
    order_positions = positions_for_mode(size, mode)
    grid = Grid2D(size, size, connectivity, order_positions)

    values = list(range(size * size))
    random.shuffle(values)

    positions = [(x, y) for x in range(size) for y in range(size)]
    random.shuffle(positions)

    for i, (x, y) in enumerate(positions):
        if cell_class == SelectionOrder2DCell:
            cell = cell_class(values[i], (x, y), size, order_positions)
        else:
            cell = cell_class(values[i], (x, y))
        grid.add_cell(cell)

    if n_frozen > 0:
        cells = grid.get_all_cells()
        frozen_cells = random.sample(cells, min(n_frozen, len(cells)))
        for cell in frozen_cells:
            cell.status = CellStatus2D.FROZEN

    return grid


def get_inversion_count(grid: Grid2D) -> int:
    ordered_values = []
    for pos in grid.order_positions:
        cell = grid.get_cell_at(*pos)
        if cell is None or cell.status == CellStatus2D.FROZEN:
            continue
        ordered_values.append(cell.value)

    inversions = 0
    for i in range(len(ordered_values)):
        for j in range(i + 1, len(ordered_values)):
            if ordered_values[i] > ordered_values[j]:
                inversions += 1
    return inversions


def get_row_col_violations(grid: Grid2D) -> int:
    violations = 0
    for y in range(grid.height):
        for x in range(grid.width):
            cell = grid.get_cell_at(x, y)
            if cell is None or cell.status == CellStatus2D.FROZEN:
                continue
            right = grid.get_cell_at(x + 1, y)
            if right is not None and right.status != CellStatus2D.FROZEN:
                if cell.value > right.value:
                    violations += 1
            down = grid.get_cell_at(x, y + 1)
            if down is not None and down.status != CellStatus2D.FROZEN:
                if cell.value > down.value:
                    violations += 1
    return violations


def run_2d_sort(grid: Grid2D, max_steps: int) -> dict:
    inversion_count = get_inversion_count(grid)
    inversion_trajectory = [inversion_count]
    swap_count = 0

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
                    swap_count += 1
                    made_swap = True
                    break
            if made_swap:
                break

        inversion_count = get_inversion_count(grid)
        inversion_trajectory.append(inversion_count)

        if inversion_count == 0:
            break
        if not made_swap:
            break

    return {
        "final_inversions": inversion_count,
        "swap_count": swap_count,
        "inversion_trajectory": inversion_trajectory,
        "steps": len(inversion_trajectory) - 1,
        "sorted": inversion_count == 0,
    }


def find_dips(trajectory: list[int]) -> list[dict]:
    if len(trajectory) < 3:
        return []

    dips = []
    i = 0
    while i < len(trajectory) - 2:
        if trajectory[i + 1] > trajectory[i]:
            start_val = trajectory[i]
            peak_val = trajectory[i + 1]
            peak_idx = i + 1

            j = i + 2
            while j < len(trajectory) and trajectory[j] >= trajectory[j - 1]:
                if trajectory[j] > peak_val:
                    peak_val = trajectory[j]
                    peak_idx = j
                j += 1

            if j < len(trajectory):
                end_idx = j
                while end_idx < len(trajectory) and trajectory[end_idx] <= start_val:
                    end_idx += 1
                    break

                if end_idx <= len(trajectory):
                    dips.append({
                        "start_idx": i,
                        "peak_idx": peak_idx,
                        "end_idx": min(end_idx, len(trajectory) - 1),
                        "start_val": start_val,
                        "peak_val": peak_val,
                        "depth": peak_val - start_val,
                    })
            i = j
        else:
            i += 1
    return dips


def frozen_counts_for_size(size: int) -> list[int]:
    ratios = [0.0, 3 / 36, 6 / 36, 9 / 36]
    total = size * size
    counts = []
    for ratio in ratios:
        if ratio == 0:
            counts.append(0)
        else:
            counts.append(max(1, int(round(total * ratio))))
    return counts


def summarize_results(label: str, dip_rate: float, avg_dips: float, success_rate: float) -> str:
    return f"{label}: dip_rate={dip_rate:.1%}, avg_dips={avg_dips:.2f}, success={success_rate:.1%}"


def summarize_row_col(label: str, success_rate: float, avg_violations: float) -> str:
    return f"{label}: success={success_rate:.1%}, avg_violations={avg_violations:.2f}"


def main() -> None:
    print("=" * 70)
    print("EXPERIMENT 23: ALTERNATE 2D ORDERING TARGETS")
    print("=" * 70)

    grid_sizes = [6, 8]
    connectivities = [4, 8]
    modes = [OrderMode.ROW_MAJOR, OrderMode.SERPENTINE]
    n_trials = 50

    print(f"Trials per config: {n_trials}")

    for size in grid_sizes:
        frozen_counts = frozen_counts_for_size(size)
        delay_frozen = frozen_counts[1]
        max_steps = size * size * 30
        for connectivity in connectivities:
            for mode in modes:
                print("\n" + "-" * 60)
                print(f"GRID={size} CONNECTIVITY={connectivity} MODE={mode.value}")
                print(f"frozen_counts={frozen_counts}, delay_frozen={delay_frozen}, max_steps={max_steps}")

                for cell_class, name in [
                    (LocalOrder2DCell, "LocalOrder2D"),
                    (SelectionOrder2DCell, "SelectionOrder2D"),
                ]:
                    dip_counts = []
                    success_flags = []
                    for trial in range(n_trials):
                        random.seed(1000 + trial)
                        grid = create_grid(
                            size, mode, connectivity, delay_frozen, cell_class
                        )
                        result = run_2d_sort(grid, max_steps=max_steps)
                        dips = find_dips(result["inversion_trajectory"])
                        dip_counts.append(len(dips))
                        success_flags.append(result["sorted"])
                    dip_rate = sum(1 for d in dip_counts if d > 0) / n_trials
                    avg_dips = float(np.mean(dip_counts))
                    success_rate = sum(success_flags) / n_trials
                    print("  Delay", summarize_results(name, dip_rate, avg_dips, success_rate))

                if mode == OrderMode.ROW_MAJOR:
                    for cell_class, name in [
                        (LocalOrder2DCell, "LocalOrder2D"),
                        (SelectionOrder2DCell, "SelectionOrder2D"),
                    ]:
                        violations = []
                        success_flags = []
                        for trial in range(n_trials):
                            random.seed(2000 + trial)
                            grid = create_grid(
                                size, mode, connectivity, 0, cell_class
                            )
                            run_2d_sort(grid, max_steps=max_steps)
                            violation_count = get_row_col_violations(grid)
                            violations.append(violation_count)
                            success_flags.append(violation_count == 0)
                        success_rate = sum(success_flags) / n_trials
                        avg_violation = float(np.mean(violations)) if violations else 0.0
                        print("  Row/col monotone", summarize_row_col(
                            name, success_rate, avg_violation
                        ))

                for cell_class, name in [
                    (LocalOrder2DCell, "LocalOrder2D"),
                    (SelectionOrder2DCell, "SelectionOrder2D"),
                ]:
                    nav_results = {}
                    for n_frozen in frozen_counts:
                        success_flags = []
                        for trial in range(n_trials):
                            random.seed(3000 + n_frozen * 1000 + trial)
                            grid = create_grid(
                                size, mode, connectivity, n_frozen, cell_class
                            )
                            result = run_2d_sort(grid, max_steps=max_steps)
                            success_flags.append(result["sorted"])
                        nav_results[n_frozen] = sum(success_flags) / n_trials
                    rates = ", ".join(f"{n}:{rate:.0%}" for n, rate in nav_results.items())
                    print(f"  Navigation {name}: {rates}")


if __name__ == "__main__":
    main()
