"""Canonical 2D engine for paper-facing experiments and summaries.

This module is the single source of truth for the paper's 2D ordering semantics:
- shell ordering by squared distance from origin
- row-major ordering
- serpentine ordering

It also centralizes the paper's four 2D algorithm surfaces:
- Bubble2D
- Selection2D
- LocalOrder2D
- SelectionOrder2D
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CellStatus2D(Enum):
    ACTIVE = 1
    FROZEN = 2


class OrderMode(str, Enum):
    SHELL = "shell"
    ROW_MAJOR = "row_major"
    SERPENTINE = "serpentine"


def positions_row_major(size: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(size) for x in range(size)]


def positions_serpentine(size: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for y in range(size):
        xs = range(size) if y % 2 == 0 else range(size - 1, -1, -1)
        for x in xs:
            positions.append((x, y))
    return positions


def shell_order_positions(size: int) -> list[tuple[int, int]]:
    positions: list[tuple[int, int, int]] = []
    for x in range(size):
        for y in range(size):
            positions.append((x * x + y * y, x, y))
    positions.sort()
    return [(x, y) for _, x, y in positions]


def order_positions_for_mode(size: int, order_mode: str | OrderMode) -> list[tuple[int, int]]:
    mode = OrderMode(order_mode)
    if mode == OrderMode.SHELL:
        return shell_order_positions(size)
    if mode == OrderMode.ROW_MAJOR:
        return positions_row_major(size)
    if mode == OrderMode.SERPENTINE:
        return positions_serpentine(size)
    raise ValueError(f"unsupported order mode: {order_mode}")


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


@dataclass(frozen=True)
class TrialSetup2D:
    size: int
    connectivity: int
    order_mode: str
    n_frozen: int
    trial_seed: int
    max_steps: int
    initial_grid_values: list[int]
    frozen_positions: list[tuple[int, int]]


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
        self.order_index = {position: index for index, position in enumerate(order_positions)}
        self.cells: dict[tuple[int, int], Cell2DBase] = {}
        self.neighbor_deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if connectivity == 8:
            self.neighbor_deltas.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])

    def add_cell(self, cell: "Cell2DBase") -> None:
        self.cells[cell.position] = cell
        cell.grid = self

    def get_cell_at(self, x: int, y: int) -> "Cell2DBase | None":
        return self.cells.get((x, y))

    def swap_cells(self, cell_a: "Cell2DBase", cell_b: "Cell2DBase") -> None:
        pos_a, pos_b = cell_a.position, cell_b.position
        cell_a.position, cell_b.position = pos_b, pos_a
        self.cells[pos_a] = cell_b
        self.cells[pos_b] = cell_a

    def get_all_cells(self) -> list["Cell2DBase"]:
        return list(self.cells.values())

    def values_by_position(self) -> list[int]:
        return [
            self.cells[(x, y)].value
            for y in range(self.height)
            for x in range(self.width)
        ]


class Cell2DBase:
    def __init__(self, value: int, position: tuple[int, int], cell_type: str):
        self.value = value
        self.position = position
        self.cell_type = cell_type
        self.status = CellStatus2D.ACTIVE
        self.grid: Grid2D | None = None
        self.ideal_position: tuple[int, int] | None = None

    def distance_from_origin(self) -> int:
        return self.position[0] * self.position[0] + self.position[1] * self.position[1]

    def get_neighbors(self) -> list["Cell2DBase"]:
        if self.grid is None:
            return []
        neighbors = []
        for dx, dy in self.grid.neighbor_deltas:
            nx = self.position[0] + dx
            ny = self.position[1] + dy
            if 0 <= nx < self.grid.width and 0 <= ny < self.grid.height:
                neighbor = self.grid.get_cell_at(nx, ny)
                if neighbor is not None:
                    neighbors.append(neighbor)
        return neighbors

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        raise NotImplementedError


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


class LocalOrder2DCell(Cell2DBase):
    def __init__(self, value: int, position: tuple[int, int]):
        super().__init__(value, position, "LocalOrder2D")

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if self.grid is None or neighbor.status == CellStatus2D.FROZEN:
            return False
        my_rank = self.grid.order_index[self.position]
        their_rank = self.grid.order_index[neighbor.position]
        if my_rank < their_rank:
            return self.value > neighbor.value
        if my_rank > their_rank:
            return self.value < neighbor.value
        return False


class _SelectionOrderCell(Cell2DBase):
    def __init__(
        self,
        value: int,
        position: tuple[int, int],
        order_positions: list[tuple[int, int]],
        cell_type: str,
    ):
        super().__init__(value, position, cell_type)
        self.ideal_position = order_positions[value]

    def should_swap_with(self, neighbor: "Cell2DBase") -> bool:
        if neighbor.status == CellStatus2D.FROZEN or self.ideal_position is None:
            return False
        my_dist = (self.position[0] - self.ideal_position[0]) ** 2 + (
            self.position[1] - self.ideal_position[1]
        ) ** 2
        new_dist = (neighbor.position[0] - self.ideal_position[0]) ** 2 + (
            neighbor.position[1] - self.ideal_position[1]
        ) ** 2
        return new_dist < my_dist


class Selection2DCell(_SelectionOrderCell):
    def __init__(
        self,
        value: int,
        position: tuple[int, int],
        order_positions: list[tuple[int, int]],
    ):
        super().__init__(value, position, order_positions, "Selection2D")


class SelectionOrder2DCell(_SelectionOrderCell):
    def __init__(
        self,
        value: int,
        position: tuple[int, int],
        order_positions: list[tuple[int, int]],
    ):
        super().__init__(value, position, order_positions, "SelectionOrder2D")


def algorithm_labels_for_mode(order_mode: str | OrderMode) -> list[str]:
    mode = OrderMode(order_mode)
    if mode == OrderMode.SHELL:
        return ["Bubble2D", "Selection2D"]
    return ["LocalOrder2D", "SelectionOrder2D"]


def generate_trial_setup(
    *,
    size: int,
    connectivity: int,
    order_mode: str | OrderMode,
    n_frozen: int,
    trial_seed: int,
    max_steps: int,
) -> TrialSetup2D:
    rng = random.Random(trial_seed)
    initial_grid_values = list(range(size * size))
    rng.shuffle(initial_grid_values)
    positions = positions_row_major(size)
    frozen_positions = sorted(rng.sample(positions, min(n_frozen, len(positions))))
    return TrialSetup2D(
        size=size,
        connectivity=connectivity,
        order_mode=OrderMode(order_mode).value,
        n_frozen=n_frozen,
        trial_seed=trial_seed,
        max_steps=max_steps,
        initial_grid_values=initial_grid_values,
        frozen_positions=frozen_positions,
    )


def _make_cell(
    *,
    algorithm: str,
    value: int,
    position: tuple[int, int],
    order_positions: list[tuple[int, int]],
) -> Cell2DBase:
    if algorithm == "Bubble2D":
        return Bubble2DCell(value, position)
    if algorithm == "Selection2D":
        return Selection2DCell(value, position, order_positions)
    if algorithm == "LocalOrder2D":
        return LocalOrder2DCell(value, position)
    if algorithm == "SelectionOrder2D":
        return SelectionOrder2DCell(value, position, order_positions)
    raise ValueError(f"unsupported 2D algorithm: {algorithm}")


def build_grid_from_setup(setup: TrialSetup2D, algorithm: str) -> Grid2D:
    order_positions = order_positions_for_mode(setup.size, setup.order_mode)
    grid = Grid2D(setup.size, setup.size, setup.connectivity, order_positions)
    for position, value in zip(
        positions_row_major(setup.size), setup.initial_grid_values, strict=True
    ):
        grid.add_cell(
            _make_cell(
                algorithm=algorithm,
                value=value,
                position=position,
                order_positions=order_positions,
            )
        )
    frozen_set = set(setup.frozen_positions)
    for position in frozen_set:
        grid.cells[position].status = CellStatus2D.FROZEN
    return grid


def inversion_count(grid: Grid2D, order_mode: str | OrderMode) -> int:
    mode = OrderMode(order_mode)
    if mode == OrderMode.SHELL:
        cells_by_distance: dict[int, list[int]] = {}
        for cell in grid.get_all_cells():
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

    ordered_values = []
    for position in grid.order_positions:
        cell = grid.get_cell_at(*position)
        if cell is None or cell.status == CellStatus2D.FROZEN:
            continue
        ordered_values.append(cell.value)

    inversions = 0
    for index, value_left in enumerate(ordered_values):
        for value_right in ordered_values[index + 1 :]:
            if value_left > value_right:
                inversions += 1
    return inversions


def row_col_violations(grid: Grid2D) -> int:
    violations = 0
    for y in range(grid.height):
        for x in range(grid.width):
            cell = grid.get_cell_at(x, y)
            if cell is None or cell.status == CellStatus2D.FROZEN:
                continue
            right = grid.get_cell_at(x + 1, y)
            if (
                right is not None
                and right.status != CellStatus2D.FROZEN
                and cell.value > right.value
            ):
                violations += 1
            down = grid.get_cell_at(x, y + 1)
            if (
                down is not None
                and down.status != CellStatus2D.FROZEN
                and cell.value > down.value
            ):
                violations += 1
    return violations


def find_dips(trajectory: list[int]) -> list[dict[str, int]]:
    if len(trajectory) < 3:
        return []

    dips: list[dict[str, int]] = []
    index = 0
    while index < len(trajectory) - 2:
        if trajectory[index + 1] > trajectory[index]:
            start_val = trajectory[index]
            peak_val = trajectory[index + 1]
            peak_idx = index + 1
            cursor = index + 2

            while cursor < len(trajectory) and trajectory[cursor] >= trajectory[cursor - 1]:
                if trajectory[cursor] > peak_val:
                    peak_val = trajectory[cursor]
                    peak_idx = cursor
                cursor += 1

            if cursor < len(trajectory):
                end_idx = cursor
                if trajectory[end_idx] <= start_val:
                    dips.append(
                        {
                            "start_idx": index,
                            "peak_idx": peak_idx,
                            "end_idx": end_idx,
                            "start_val": start_val,
                            "peak_val": peak_val,
                            "depth": peak_val - start_val,
                        }
                    )
            index = cursor
        else:
            index += 1
    return dips


def _ideal_position_for_value(grid: Grid2D, value: int) -> tuple[int, int]:
    return grid.order_positions[value]


def run_trial_from_setup(
    setup: TrialSetup2D,
    *,
    algorithm: str,
    collect_trajectory: bool = False,
    collect_swap_pairs: bool = False,
    collect_directed_flow: bool = False,
) -> dict[str, Any]:
    grid = build_grid_from_setup(setup, algorithm)
    schedule_rng = random.Random(setup.trial_seed ^ 0x5F3759DF)
    order_mode = setup.order_mode
    current_error = inversion_count(grid, order_mode)
    trajectory = [current_error]
    swap_pairs: list[tuple[int, int]] = []
    forward_swaps = 0
    backward_swaps = 0
    swap_count = 0
    termination = "max_steps"

    for _ in range(setup.max_steps):
        made_swap = False
        cells = grid.get_all_cells()
        schedule_rng.shuffle(cells)

        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue
            neighbors = cell.get_neighbors()
            schedule_rng.shuffle(neighbors)
            for neighbor in neighbors:
                if cell.should_swap_with(neighbor):
                    if collect_swap_pairs:
                        swap_pairs.append((cell.value, neighbor.value))
                    if collect_directed_flow:
                        ideal_position = _ideal_position_for_value(grid, cell.value)
                        before = abs(cell.position[0] - ideal_position[0]) + abs(
                            cell.position[1] - ideal_position[1]
                        )
                        after = abs(neighbor.position[0] - ideal_position[0]) + abs(
                            neighbor.position[1] - ideal_position[1]
                        )
                        if after < before:
                            forward_swaps += 1
                        else:
                            backward_swaps += 1
                    grid.swap_cells(cell, neighbor)
                    swap_count += 1
                    made_swap = True
                    break
            if made_swap:
                break

        current_error = inversion_count(grid, order_mode)
        trajectory.append(current_error)
        if current_error == 0:
            termination = "sorted"
            break
        if not made_swap:
            termination = "stalled"
            break
    else:
        termination = "max_steps"

    dips = find_dips(trajectory)
    result: dict[str, Any] = {
        "algorithm": algorithm,
        "order_mode": setup.order_mode,
        "grid_size": setup.size,
        "connectivity": setup.connectivity,
        "n_frozen": setup.n_frozen,
        "trial_seed": setup.trial_seed,
        "max_steps": setup.max_steps,
        "initial_grid_values": setup.initial_grid_values,
        "frozen_positions": [list(position) for position in setup.frozen_positions],
        "final_grid_values": grid.values_by_position(),
        "sorted": current_error == 0,
        "final_error": current_error,
        "swap_count": swap_count,
        "steps": len(trajectory) - 1,
        "termination": termination,
        "dip_count": len(dips),
        "has_dip": bool(dips),
    }
    if collect_trajectory:
        result["trajectory"] = trajectory
        result["dips"] = dips
    if collect_swap_pairs:
        result["swap_pairs"] = [list(pair) for pair in swap_pairs]
    if collect_directed_flow:
        result["forward_swaps"] = forward_swaps
        result["backward_swaps"] = backward_swaps
    if setup.order_mode == OrderMode.ROW_MAJOR.value:
        result["row_col_violations"] = row_col_violations(grid)
    return result
