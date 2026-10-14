"""
EXPERIMENT 24: Pattern-Guided 2D Sorting

Purpose:
- Test whether a fixed internal pattern stream helps local-only 2D algorithms
  escape local minima without adding explicit global targets.

Usage:
  uv run python exp24_pattern_guided_2d.py
  uv run python exp24_pattern_guided_2d.py --suite full
"""

from __future__ import annotations

import argparse
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class CellStatus2D(Enum):
    ACTIVE = 1
    FROZEN = 2


class Grid2D:
    def __init__(self, width, height, connectivity):
        if connectivity not in (4, 8):
            raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
        self.width = width
        self.height = height
        self.cells = {}
        self.swap_history = []
        self.connectivity = connectivity
        self.neighbor_deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if connectivity == 8:
            self.neighbor_deltas.extend(
                [
                    (-1, -1),
                    (-1, 1),
                    (1, -1),
                    (1, 1),
                ]
            )

    def add_cell(self, cell):
        self.cells[cell.position] = cell
        cell.grid = self

    def get_cell_at(self, x, y):
        return self.cells.get((x, y))

    def swap_cells(self, cell1, cell2):
        pos1, pos2 = cell1.position, cell2.position
        self.swap_history.append((cell1.value, pos1, pos2))
        cell1.position, cell2.position = pos2, pos1
        self.cells[pos1] = cell2
        self.cells[pos2] = cell1

    def get_all_cells(self):
        return list(self.cells.values())

    def get_state_hash(self):
        return tuple(sorted((c.value, c.position) for c in self.cells.values()))


class Cell2DBase:
    def __init__(self, value, position, cell_type):
        self.value = value
        self.position = position
        self.cell_type = cell_type
        self.status = CellStatus2D.ACTIVE
        self.grid: Grid2D | None = None
        self.position_history = [position]

    def get_distance_from_origin(self, pos=None):
        if pos is None:
            pos = self.position
        return pos[0] ** 2 + pos[1] ** 2

    def get_neighbors(self):
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

    def record_position(self):
        self.position_history.append(self.position)

    def count_revisits(self):
        seen = set()
        revisits = 0
        for pos in self.position_history:
            if pos in seen:
                revisits += 1
            seen.add(pos)
        return revisits

    def should_swap_with(self, neighbor):
        raise NotImplementedError


class Bubble2DCell(Cell2DBase):
    def __init__(self, value, position):
        super().__init__(value, position, "Bubble2D")

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            return self.value > neighbor.value
        if my_dist > their_dist:
            return self.value < neighbor.value
        return False


class Gnome2DCell(Cell2DBase):
    def __init__(self, value, position):
        super().__init__(value, position, "Gnome2D")

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            return self.value > neighbor.value
        if my_dist > their_dist:
            return self.value < neighbor.value
        return False


class Insertion2DCell(Cell2DBase):
    def __init__(self, value, position, grid_size):
        super().__init__(value, position, "Insertion2D")
        self.grid_size = grid_size

    def is_inner_region_sorted(self):
        grid = self.grid
        if grid is None:
            return True

        my_dist = self.get_distance_from_origin()

        for cell in grid.get_all_cells():
            if cell is self:
                continue
            cell_dist = self.get_distance_from_origin(cell.position)
            if cell_dist < my_dist:
                for neighbor in cell.get_neighbors():
                    if neighbor is self:
                        continue
                    neighbor_dist = self.get_distance_from_origin(neighbor.position)
                    if neighbor_dist < my_dist:
                        if cell_dist < neighbor_dist and cell.value > neighbor.value:
                            return False
                        if cell_dist > neighbor_dist and cell.value < neighbor.value:
                            return False
        return True

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        if not self.is_inner_region_sorted():
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            return self.value > neighbor.value
        if my_dist > their_dist:
            return self.value < neighbor.value
        return False


class Selection2DCell(Cell2DBase):
    def __init__(self, value, position, grid_size):
        super().__init__(value, position, "Selection2D")
        self.grid_size = grid_size
        self.ideal_position = None
        self._compute_ideal_position()

    def _compute_ideal_position(self):
        positions_by_distance = []
        for x in range(self.grid_size):
            for y in range(self.grid_size):
                dist = x**2 + y**2
                positions_by_distance.append((dist, x, y))
        positions_by_distance.sort()

        rank = self.value
        if rank < len(positions_by_distance):
            _, x, y = positions_by_distance[rank]
            self.ideal_position = (x, y)
        else:
            self.ideal_position = (self.grid_size - 1, self.grid_size - 1)

    def should_swap_with(self, neighbor):
        if self.ideal_position is None:
            return False

        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist_to_ideal = (self.position[0] - self.ideal_position[0]) ** 2 + (
            self.position[1] - self.ideal_position[1]
        ) ** 2

        new_dist_to_ideal = (neighbor.position[0] - self.ideal_position[0]) ** 2 + (
            neighbor.position[1] - self.ideal_position[1]
        ) ** 2

        return new_dist_to_ideal < my_dist_to_ideal


@dataclass(frozen=True)
class PatternConfig:
    pattern_mode: str
    pattern_type: str
    decision_mode: str
    pattern_weight: float
    seed: int

    def label(self):
        if self.pattern_mode == "none":
            return "baseline"
        return (
            f"{self.pattern_mode}/{self.pattern_type}/{self.decision_mode}/w{self.pattern_weight}"
        )


class PatternContext:
    VALID_PATTERN_MODES = {"none", "temporal", "spatial", "mixed"}
    VALID_PATTERN_TYPES = {"structured", "shuffled", "noise", "shells"}
    VALID_DECISION_MODES = {"baseline", "order", "gate", "order_gate"}

    def __init__(self, config: PatternConfig, grid_size, temporal_length):
        self._validate_config(config)
        self.config = config
        self.grid_size = grid_size
        self.temporal_length = temporal_length
        self.temporal_sequence = None
        self.spatial_field = None

        if config.pattern_mode in {"temporal", "mixed"}:
            self.temporal_sequence = build_temporal_sequence(
                temporal_length, config.pattern_type, config.seed
            )
        if config.pattern_mode in {"spatial", "mixed"}:
            self.spatial_field = build_spatial_field(grid_size, config.pattern_type, config.seed)

    def _validate_config(self, config):
        if config.pattern_mode not in self.VALID_PATTERN_MODES:
            raise ValueError(f"invalid pattern_mode: {config.pattern_mode}")
        if config.pattern_type not in self.VALID_PATTERN_TYPES:
            raise ValueError(f"invalid pattern_type: {config.pattern_type}")
        if config.decision_mode not in self.VALID_DECISION_MODES:
            raise ValueError(f"invalid decision_mode: {config.decision_mode}")
        if not 0.0 <= config.pattern_weight <= 1.0:
            raise ValueError(f"invalid pattern_weight: {config.pattern_weight}")
        if config.pattern_mode == "none" and config.decision_mode != "baseline":
            raise ValueError("baseline decision_mode required for pattern_mode=none")
        if config.pattern_type == "shells" and config.pattern_mode != "spatial":
            raise ValueError("pattern_type=shells requires pattern_mode=spatial")

    def value_at(self, position, step):
        if self.config.pattern_mode == "none":
            return 0

        temporal_value = 0
        spatial_value = 0

        if self.temporal_sequence is not None:
            temporal_value = self.temporal_sequence[step % self.temporal_length]
        if self.spatial_field is not None:
            spatial_value = self.spatial_field[position[1]][position[0]]

        if self.config.pattern_mode == "temporal":
            return temporal_value
        if self.config.pattern_mode == "spatial":
            return spatial_value
        return (temporal_value + spatial_value) % 4

    def gate_on(self, position, step):
        weight = self.config.pattern_weight
        if weight <= 0.0:
            return False
        if weight >= 1.0:
            return True
        return (self.value_at(position, step) / 3.0) <= weight


def build_temporal_sequence(length, pattern_type, seed):
    if length <= 0:
        raise ValueError("temporal length must be positive")

    if pattern_type == "structured":
        sequence = generate_structured_temporal_sequence(length)
    elif pattern_type == "noise":
        rng = random.Random(seed)
        sequence = [rng.randrange(4) for _ in range(length)]
    elif pattern_type == "shuffled":
        sequence = generate_structured_temporal_sequence(length)
        rng = random.Random(seed)
        rng.shuffle(sequence)
    elif pattern_type == "shells":
        raise ValueError("pattern_type=shells is spatial-only")
    else:
        raise ValueError(f"invalid pattern_type: {pattern_type}")

    return sequence


def generate_structured_temporal_sequence(length):
    rules = {
        0: (0, 1),
        1: (0, 2),
        2: (1, 3),
        3: (2, 0),
    }
    sequence = [0]
    while len(sequence) < length:
        expanded = []
        for value in sequence:
            expanded.extend(rules[value])
        sequence = expanded
    return sequence[:length]


def build_spatial_field(size, pattern_type, seed):
    if pattern_type == "structured":
        field = generate_structured_spatial_field(size)
    elif pattern_type == "noise":
        rng = random.Random(seed)
        field = [[rng.randrange(4) for _ in range(size)] for _ in range(size)]
    elif pattern_type == "shuffled":
        field = generate_structured_spatial_field(size)
        rng = random.Random(seed)
        flat = [value for row in field for value in row]
        rng.shuffle(flat)
        field = [flat[i * size : (i + 1) * size] for i in range(size)]
    elif pattern_type == "shells":
        field = generate_shells_spatial_field(size)
    else:
        raise ValueError(f"invalid pattern_type: {pattern_type}")

    return field


def generate_structured_spatial_field(size):
    field = []
    for y in range(size):
        row = []
        for x in range(size):
            bit_a = (x & y) & 1
            bit_b = (x ^ y) & 1
            row.append(bit_a + 2 * bit_b)
        field.append(row)
    return field


def generate_shells_spatial_field(size):
    distances = []
    for x in range(size):
        for y in range(size):
            distances.append(x**2 + y**2)
    unique_distances = sorted(set(distances))
    rank_by_distance = {dist: idx for idx, dist in enumerate(unique_distances)}

    field = []
    for y in range(size):
        row = []
        for x in range(size):
            dist = x**2 + y**2
            row.append(rank_by_distance[dist] % 4)
        field.append(row)
    return field


def create_grid(size, cell_class, connectivity, rng, n_frozen):
    grid = Grid2D(size, size, connectivity)

    values = list(range(size * size))
    rng.shuffle(values)

    positions = [(x, y) for x in range(size) for y in range(size)]
    rng.shuffle(positions)

    for i, (x, y) in enumerate(positions):
        if cell_class in {Selection2DCell, Insertion2DCell}:
            cell = cell_class(values[i], (x, y), size)
        else:
            cell = cell_class(values[i], (x, y))
        grid.add_cell(cell)

    if n_frozen > 0:
        frozen_cells = rng.sample(grid.get_all_cells(), min(n_frozen, len(grid.get_all_cells())))
        for cell in frozen_cells:
            cell.status = CellStatus2D.FROZEN

    return grid


def get_2d_inversion_count(grid):
    cells_by_dist = defaultdict(list)
    for cell in grid.get_all_cells():
        dist = cell.get_distance_from_origin()
        cells_by_dist[dist].append(cell.value)

    inversions = 0
    sorted_dists = sorted(cells_by_dist.keys())

    for i, dist1 in enumerate(sorted_dists):
        for dist2 in sorted_dists[i + 1 :]:
            for v1 in cells_by_dist[dist1]:
                for v2 in cells_by_dist[dist2]:
                    if v1 > v2:
                        inversions += 1

    return inversions


def get_2d_boundary_violations(grid):
    cells_by_dist = defaultdict(list)
    for cell in grid.get_all_cells():
        dist = cell.get_distance_from_origin()
        cells_by_dist[dist].append(cell.value)

    errors = 0
    sorted_dists = sorted(cells_by_dist.keys())
    prev_max = -1

    for dist in sorted_dists:
        values = cells_by_dist[dist]
        min_val = min(values)
        if min_val < prev_max:
            errors += 1
        prev_max = max(values)

    return errors


def order_neighbors(neighbors, pattern_value):
    if not neighbors:
        return neighbors
    shift = pattern_value % len(neighbors)
    return neighbors[shift:] + neighbors[:shift]


def choose_swap(cell, neighbors, pattern_context, step, decision_mode, rng):
    if not neighbors:
        return None

    pattern_value = pattern_context.value_at(cell.position, step)

    if decision_mode in {"order", "order_gate"}:
        neighbors = order_neighbors(neighbors, pattern_value)
    else:
        rng.shuffle(neighbors)

    for neighbor in neighbors:
        if cell.should_swap_with(neighbor):
            return neighbor

    if decision_mode in {"gate", "order_gate"}:
        if pattern_context.gate_on(cell.position, step):
            for neighbor in neighbors:
                if neighbor.status == CellStatus2D.ACTIVE:
                    return neighbor

    return None


def run_2d_sort(grid, max_steps, pattern_context, decision_mode, rng, detect_cycles):
    seen_states = {}
    cycle_detected = False
    cycle_length = 0

    inversion_count = get_2d_inversion_count(grid)
    error_trajectory = [inversion_count]

    made_swap = False
    step = -1
    for step in range(max_steps):
        if detect_cycles:
            state = grid.get_state_hash()
            if state in seen_states:
                cycle_detected = True
                cycle_length = step - seen_states[state]
                break
            seen_states[state] = step

        made_swap = False
        cells = grid.get_all_cells()
        rng.shuffle(cells)

        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue

            neighbors = cell.get_neighbors()
            if not neighbors:
                continue

            neighbor = choose_swap(cell, neighbors, pattern_context, step, decision_mode, rng)
            if neighbor is None:
                continue

            grid.swap_cells(cell, neighbor)
            cell.record_position()
            neighbor.record_position()
            made_swap = True
            break

        inversion_count = get_2d_inversion_count(grid)
        error_trajectory.append(inversion_count)

        if inversion_count == 0:
            break
        if not made_swap:
            break

    total_revisits = sum(c.count_revisits() for c in grid.get_all_cells())
    no_swap_termination = (not made_swap) and (inversion_count > 0) and (not cycle_detected)

    return {
        "final_inversions": inversion_count,
        "final_boundary_violations": get_2d_boundary_violations(grid),
        "sorted": inversion_count == 0,
        "steps": step + 1,
        "swap_count": len(grid.swap_history),
        "cycle_detected": cycle_detected,
        "cycle_length": cycle_length,
        "total_revisits": total_revisits,
        "error_trajectory": error_trajectory,
        "no_swap_termination": no_swap_termination,
    }


def summarize_results(results):
    success_rate = sum(1 for r in results if r["sorted"]) / len(results)
    cycle_rate = sum(1 for r in results if r["cycle_detected"]) / len(results)
    stuck_rate = sum(1 for r in results if r["no_swap_termination"]) / len(results)
    avg_revisits = statistics.mean(r["total_revisits"] for r in results)
    avg_steps = statistics.mean(r["steps"] for r in results)
    avg_inversions = statistics.mean(r["final_inversions"] for r in results)

    return {
        "success_rate": success_rate,
        "cycle_rate": cycle_rate,
        "stuck_rate": stuck_rate,
        "avg_revisits": avg_revisits,
        "avg_steps": avg_steps,
        "avg_inversions": avg_inversions,
    }


def build_default_configs(suite, seed):
    configs = [
        PatternConfig(
            pattern_mode="none",
            pattern_type="structured",
            decision_mode="baseline",
            pattern_weight=0.0,
            seed=seed,
        )
    ]

    pattern_types = ["structured", "noise"]
    if suite == "full":
        pattern_types.append("shuffled")

    gate_weights = [0.1, 0.25, 0.5]

    for pattern_type in pattern_types:
        for weight in gate_weights:
            configs.append(
                PatternConfig(
                    pattern_mode="temporal",
                    pattern_type=pattern_type,
                    decision_mode="gate",
                    pattern_weight=weight,
                    seed=seed,
                )
            )

    for pattern_type in pattern_types:
        configs.append(
            PatternConfig(
                pattern_mode="temporal",
                pattern_type=pattern_type,
                decision_mode="order",
                pattern_weight=0.0,
                seed=seed,
            )
        )

    for pattern_type in pattern_types:
        for weight in gate_weights:
            configs.append(
                PatternConfig(
                    pattern_mode="spatial",
                    pattern_type=pattern_type,
                    decision_mode="order_gate",
                    pattern_weight=weight,
                    seed=seed,
                )
            )

    for pattern_type in pattern_types:
        configs.append(
            PatternConfig(
                pattern_mode="spatial",
                pattern_type=pattern_type,
                decision_mode="order",
                pattern_weight=0.0,
                seed=seed,
            )
        )

    for weight in gate_weights:
        configs.append(
            PatternConfig(
                pattern_mode="spatial",
                pattern_type="shells",
                decision_mode="order_gate",
                pattern_weight=weight,
                seed=seed,
            )
        )

    configs.append(
        PatternConfig(
            pattern_mode="spatial",
            pattern_type="shells",
            decision_mode="order",
            pattern_weight=0.0,
            seed=seed,
        )
    )

    return configs


def run_suite(grid_size, connectivity, trials, max_steps, n_frozen, suite, seed, detect_cycles):
    algorithms = [
        (Bubble2DCell, "Bubble2D"),
        (Gnome2DCell, "Gnome2D"),
        (Insertion2DCell, "Insertion2D"),
        (Selection2DCell, "Selection2D"),
    ]

    configs = build_default_configs(suite, seed)
    print("=" * 70)
    print("EXPERIMENT 24: PATTERN-GUIDED 2D SORTING")
    print("=" * 70)
    print(
        f"Setup: {grid_size}x{grid_size}, connectivity={connectivity}, "
        f"trials={trials}, frozen={n_frozen}, suite={suite}"
    )

    for cell_class, name in algorithms:
        print("\n" + "-" * 60)
        print(f"Algorithm: {name}")
        print("-" * 60)

        for config in configs:
            pattern_context = PatternContext(config, grid_size, max_steps + 1)
            results = []

            for trial in range(trials):
                rng = random.Random(seed + trial)
                grid = create_grid(grid_size, cell_class, connectivity, rng, n_frozen)
                result = run_2d_sort(
                    grid,
                    max_steps=max_steps,
                    pattern_context=pattern_context,
                    decision_mode=config.decision_mode,
                    rng=rng,
                    detect_cycles=detect_cycles,
                )
                results.append(result)

            summary = summarize_results(results)
            print(
                f"  {config.label()}: "
                f"success={summary['success_rate']:.0%}, "
                f"cycles={summary['cycle_rate']:.0%}, "
                f"stuck={summary['stuck_rate']:.0%}, "
                f"avg_steps={summary['avg_steps']:.0f}, "
                f"avg_revisits={summary['avg_revisits']:.1f}, "
                f"avg_inversions={summary['avg_inversions']:.1f}"
            )


def parse_args():
    parser = argparse.ArgumentParser(description="Pattern-guided 2D sorting experiment")
    parser.add_argument("--grid-size", type=int, default=6)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument("--trials", type=int, default=6)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--frozen", type=int, default=0)
    parser.add_argument("--suite", choices=["lite", "full"], default="lite")
    parser.add_argument("--detect-cycles", action="store_true", default=False)
    parser.add_argument("--seed", type=int, default=123)
    return parser.parse_args()


def main():
    args = parse_args()
    max_steps = args.max_steps
    if max_steps is None:
        max_steps = args.grid_size * args.grid_size * 30

    run_suite(
        grid_size=args.grid_size,
        connectivity=args.connectivity,
        trials=args.trials,
        max_steps=max_steps,
        n_frozen=args.frozen,
        suite=args.suite,
        seed=args.seed,
        detect_cycles=args.detect_cycles,
    )


if __name__ == "__main__":
    main()
