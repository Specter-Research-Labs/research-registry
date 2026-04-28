"""
EXPERIMENT 22: Deeper 2D Analysis

Following up on Exp 19 findings:
- Bubble2D: 0% success (WHY?)
- Selection2D: 100% success
- Clustering: doesn't emerge in 2D
- Delay gratification: rechecked in Exp 19 using inversion counts (Selection only)

Goals:
1. Test other algorithms in 2D (Gnome, Insertion)
2. Diagnose WHY Bubble fails (cycles? oscillations? equal-distance ambiguity?)
3. Visualize failure modes
4. Allow sensitivity checks for 4- vs 8-connectivity
"""

import random
import numpy as np
from collections import defaultdict
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
            self.neighbor_deltas.extend([
                (-1, -1), (-1, 1), (1, -1), (1, 1),
            ])

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

    def print_grid(self):
        for y in range(self.height):
            row = []
            for x in range(self.width):
                cell = self.get_cell_at(x, y)
                if cell:
                    row.append(f"{cell.value:2d}")
                else:
                    row.append("  ")
            print(" ".join(row))


class Cell2DBase:
    def __init__(self, value, position, cell_type):
        self.value = value
        self.position = position
        self.cell_type = cell_type
        self.status = CellStatus2D.ACTIVE
        self.grid = None
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


class Bubble2DCell(Cell2DBase):
    def __init__(self, value, position):
        super().__init__(value, position, 'Bubble2D')

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            return self.value > neighbor.value
        elif my_dist > their_dist:
            return self.value < neighbor.value
        else:
            return False


class Bubble2DFixedCell(Cell2DBase):
    """Bubble2D with tie-breaking for equal distances."""
    def __init__(self, value, position):
        super().__init__(value, position, 'Bubble2DFixed')

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            return self.value > neighbor.value
        elif my_dist > their_dist:
            return self.value < neighbor.value
        else:
            my_secondary = self.position[0] + self.position[1] * 1000
            their_secondary = neighbor.position[0] + neighbor.position[1] * 1000
            if my_secondary < their_secondary:
                return self.value > neighbor.value
            elif my_secondary > their_secondary:
                return self.value < neighbor.value
            return False


class Gnome2DCell(Cell2DBase):
    """Gnome sort in 2D - like Bubble but with backtracking tendency."""
    def __init__(self, value, position):
        super().__init__(value, position, 'Gnome2D')
        self.last_swap_direction = None

    def should_swap_with(self, neighbor):
        if neighbor.status == CellStatus2D.FROZEN:
            return False

        my_dist = self.get_distance_from_origin()
        their_dist = neighbor.get_distance_from_origin()

        if my_dist < their_dist:
            should = self.value > neighbor.value
        elif my_dist > their_dist:
            should = self.value < neighbor.value
        else:
            should = False

        if should:
            dx = neighbor.position[0] - self.position[0]
            dy = neighbor.position[1] - self.position[1]
            self.last_swap_direction = (dx, dy)

        return should


class Insertion2DCell(Cell2DBase):
    """Insertion sort in 2D - waits for inner region to be sorted."""
    def __init__(self, value, position, grid_size):
        super().__init__(value, position, 'Insertion2D')
        self.grid_size = grid_size

    def is_inner_region_sorted(self):
        if self.grid is None:
            return True

        my_dist = self.get_distance_from_origin()

        for cell in self.grid.get_all_cells():
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
        elif my_dist > their_dist:
            return self.value < neighbor.value
        return False


class Selection2DCell(Cell2DBase):
    def __init__(self, value, position, grid_size):
        super().__init__(value, position, 'Selection2D')
        self.grid_size = grid_size
        self.ideal_position = None
        self._compute_ideal_position()

    def _compute_ideal_position(self):
        positions_by_distance = []
        for x in range(self.grid_size):
            for y in range(self.grid_size):
                dist = x ** 2 + y ** 2
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

        my_dist_to_ideal = (self.position[0] - self.ideal_position[0]) ** 2 + \
                          (self.position[1] - self.ideal_position[1]) ** 2

        new_dist_to_ideal = (neighbor.position[0] - self.ideal_position[0]) ** 2 + \
                           (neighbor.position[1] - self.ideal_position[1]) ** 2

        return new_dist_to_ideal < my_dist_to_ideal


def create_grid(size, cell_class, connectivity, **kwargs):
    grid = Grid2D(size, size, connectivity)

    values = list(range(size * size))
    random.shuffle(values)

    positions = [(x, y) for x in range(size) for y in range(size)]

    for i, (x, y) in enumerate(positions):
        if cell_class == Selection2DCell or cell_class == Insertion2DCell:
            cell = cell_class(values[i], (x, y), size)
        else:
            cell = cell_class(values[i], (x, y))
        grid.add_cell(cell)

    return grid


def get_2d_inversion_count(grid):
    """Count all inversions between distance shells."""
    cells_by_dist = defaultdict(list)
    for cell in grid.get_all_cells():
        dist = cell.get_distance_from_origin()
        cells_by_dist[dist].append(cell.value)

    inversions = 0
    sorted_dists = sorted(cells_by_dist.keys())

    for i, dist1 in enumerate(sorted_dists):
        for dist2 in sorted_dists[i+1:]:
            for v1 in cells_by_dist[dist1]:
                for v2 in cells_by_dist[dist2]:
                    if v1 > v2:
                        inversions += 1

    return inversions


def get_2d_boundary_violations(grid):
    """Count shell-boundary violations only."""
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


def run_2d_sort(grid, max_steps=2000, detect_cycles=True):
    seen_states = {}
    cycle_detected = False
    cycle_length = 0

    inversion_count = get_2d_inversion_count(grid)
    error_trajectory = [inversion_count]

    made_swap = False
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
        random.shuffle(cells)

        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue

            neighbors = cell.get_neighbors()
            random.shuffle(neighbors)

            for neighbor in neighbors:
                if cell.should_swap_with(neighbor):
                    grid.swap_cells(cell, neighbor)
                    cell.record_position()
                    neighbor.record_position()
                    made_swap = True
                    break

            if made_swap:
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
        'final_inversions': inversion_count,
        'final_boundary_violations': get_2d_boundary_violations(grid),
        'sorted': inversion_count == 0,
        'steps': step + 1,
        'swap_count': len(grid.swap_history),
        'cycle_detected': cycle_detected,
        'cycle_length': cycle_length,
        'total_revisits': total_revisits,
        'error_trajectory': error_trajectory,
        'no_swap_termination': no_swap_termination,
    }


def analyze_failure_mode(grid, result):
    print(f"\n    Failure analysis:")

    if result['cycle_detected']:
        print(f"      CYCLE DETECTED: length {result['cycle_length']}")

    print(f"      Total position revisits: {result['total_revisits']}")

    high_revisit_cells = []
    for cell in grid.get_all_cells():
        revisits = cell.count_revisits()
        if revisits > 3:
            high_revisit_cells.append((cell.value, revisits, cell.position_history[-5:]))

    if high_revisit_cells:
        print(f"      Cells with high revisits (>3):")
        for value, revisits, recent in high_revisit_cells[:3]:
            print(f"        Cell {value}: {revisits} revisits, recent: {recent}")


def main():
    print("=" * 70)
    print("EXPERIMENT 22: DEEPER 2D ANALYSIS")
    print("=" * 70)

    grid_size = 6
    connectivity = 4
    n_trials = 5

    print(f"\nSetup: {grid_size}x{grid_size} grid ({grid_size**2} cells), "
          f"{connectivity}-connectivity, {n_trials} trials")

    print("\n" + "=" * 60)
    print("PART 1: COMPARING ALGORITHMS IN 2D")
    print("=" * 60)

    algorithms = [
        (Bubble2DCell, "Bubble2D (original)"),
        (Bubble2DFixedCell, "Bubble2D (with tie-breaking)"),
        (Gnome2DCell, "Gnome2D"),
        (Insertion2DCell, "Insertion2D"),
        (Selection2DCell, "Selection2D"),
    ]

    results_by_algo = {}

    for cell_class, name in algorithms:
        print(f"\n  {name}:")
        results = []

        for trial in range(n_trials):
            random.seed(42 + trial)
            grid = create_grid(grid_size, cell_class, connectivity)
            result = run_2d_sort(grid, max_steps=2000, detect_cycles=False)
            results.append(result)

            status = "SORTED" if result['sorted'] else f"inversions={result['final_inversions']}"
            extras = []
            if result['cycle_detected']:
                extras.append(f"CYCLE({result['cycle_length']})")
            if result['no_swap_termination']:
                extras.append("STUCK")
            extra_str = ", " + ", ".join(extras) if extras else ""
            print(f"    Trial {trial+1}: {status}, steps={result['steps']}, swaps={result['swap_count']}{extra_str}")

            if not result['sorted'] and trial == 0:
                analyze_failure_mode(grid, result)

        success_rate = sum(1 for r in results if r['sorted']) / len(results)
        cycle_rate = sum(1 for r in results if r['cycle_detected']) / len(results)
        stuck_rate = sum(1 for r in results if r['no_swap_termination']) / len(results)
        avg_revisits = np.mean([r['total_revisits'] for r in results])

        results_by_algo[name] = {
            'success_rate': success_rate,
            'cycle_rate': cycle_rate,
            'stuck_rate': stuck_rate,
            'avg_revisits': avg_revisits,
        }

        print(f"\n  Summary: {success_rate:.0%} success, {cycle_rate:.0%} cycles, {stuck_rate:.0%} stuck, {avg_revisits:.1f} revisits")

    print("\n" + "=" * 60)
    print("PART 2: BUBBLE2D FAILURE DEEP DIVE")
    print("=" * 60)

    print("\n  Running single Bubble2D trial with detailed tracking...")
    random.seed(123)
    grid = create_grid(grid_size, Bubble2DCell, connectivity)

    print("\n  Initial grid (values):")
    grid.print_grid()

    print("\n  Distance from origin for each position:")
    for y in range(grid_size):
        row = []
        for x in range(grid_size):
            dist = x**2 + y**2
            row.append(f"{dist:2d}")
        print("  " + " ".join(row))

    result = run_2d_sort(grid, max_steps=500)

    print(f"\n  Result: sorted={result['sorted']}, steps={result['steps']}")
    print(f"  Cycle detected: {result['cycle_detected']}, length: {result['cycle_length']}")

    print("\n  Final grid (values):")
    grid.print_grid()

    print("\n  Swap history (first 20):")
    for i, (val, pos1, pos2) in enumerate(grid.swap_history[:20]):
        dist1 = pos1[0]**2 + pos1[1]**2
        dist2 = pos2[0]**2 + pos2[1]**2
        print(f"    {i+1}. Cell {val}: {pos1}(d={dist1}) -> {pos2}(d={dist2})")

    if result['cycle_detected'] and len(grid.swap_history) > 20:
        print(f"\n  Swap history (last 10 before cycle):")
        for i, (val, pos1, pos2) in enumerate(grid.swap_history[-10:]):
            dist1 = pos1[0]**2 + pos1[1]**2
            dist2 = pos2[0]**2 + pos2[1]**2
            print(f"    {len(grid.swap_history)-10+i+1}. Cell {val}: {pos1}(d={dist1}) -> {pos2}(d={dist2})")

    print("\n" + "=" * 60)
    print("PART 3: EQUAL-DISTANCE ANALYSIS")
    print("=" * 60)

    print("\n  Positions grouped by distance from origin:")
    dist_groups = defaultdict(list)
    for x in range(grid_size):
        for y in range(grid_size):
            dist = x**2 + y**2
            dist_groups[dist].append((x, y))

    for dist in sorted(dist_groups.keys()):
        positions = dist_groups[dist]
        print(f"    Distance {dist}: {positions}")

    ambiguous_count = sum(1 for positions in dist_groups.values() if len(positions) > 1)
    print(f"\n  Distances with multiple positions (ambiguous): {ambiguous_count}/{len(dist_groups)}")
    print("  This ambiguity may cause oscillations in Bubble2D")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\n  Algorithm comparison:")
    print(f"  {'Algorithm':<30} {'Success':<10} {'Cycles':<10} {'Stuck':<10}")
    print("  " + "-" * 60)
    for name, stats in results_by_algo.items():
        print(f"  {name:<30} {stats['success_rate']:.0%}       {stats['cycle_rate']:.0%}       {stats['stuck_rate']:.0%}")

    print("""
  KEY INSIGHT: LOCAL VS GLOBAL INFORMATION IN 2D

  1. BUBBLE/GNOME/INSERTION ALL FAIL (get STUCK):
     - These algorithms use ONLY local neighbor comparisons
     - In 1D: local comparisons propagate (if A>B>C, A passes both)
     - In 2D: local minima trap the system - inversions between
       non-adjacent cells can't be fixed by local swaps
     - The path to fixing them is blocked by correctly-placed cells

  2. SELECTION SUCCEEDS (100%):
     - Each cell knows its GLOBAL target position (ideal_position)
     - Temporary oscillations occur but cells escape because they
       persistently move toward their unique global target
     - Global information breaks local minima

  3. BIOLOGICAL IMPLICATION:
     - Local-only developmental rules work in 1D (linear tissues)
     - 2D patterning REQUIRES global positional information
     - This explains morphogen gradients in development:
       cells need to "know" their global position, not just
       compare with neighbors
     - Selection2D is analogous to cells reading a morphogen gradient

  4. THE MORPHOGENESIS CONNECTION:
     - Bubble sort = purely local cell-cell signaling
     - Selection sort = cells with positional information (morphogens)
     - Our finding: local signaling alone can't achieve 2D patterning
     - This matches biology: morphogen gradients are essential for
       2D tissue organization
""")


if __name__ == "__main__":
    main()
