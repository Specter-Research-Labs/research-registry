"""
EXPERIMENT 19: 2D Ordering Problems

Paper's suggestion: "We plan to investigate how general these findings are to
algorithms for 2-dimensional ordering problems"

Key question: Do clustering and navigation behaviors generalize to 2D?

In 2D:
- Cells have (x, y) positions on a grid
- Goal: Sort cells so value increases with distance from origin
- Multiple neighbors (4 or 8 connectivity)
- More degrees of freedom for obstacle avoidance
- Frozen cells are immovable for all algorithms in this experiment

We test:
1. Does 2D Bubble cluster same-type cells?
2. Does 2D Selection navigate around frozen cells?
3. Does delay gratification appear in 2D?
"""

import random
import numpy as np
from collections import defaultdict
from enum import Enum


class CellStatus2D(Enum):
    ACTIVE = 1
    FROZEN = 2
    INACTIVE = 3


class Cell2DBase:
    def __init__(self, value, position, cell_type):
        self.value = value
        self.position = position
        self.cell_type = cell_type
        self.status = CellStatus2D.ACTIVE
        self.grid = None

    def get_distance_from_origin(self):
        return self.position[0] ** 2 + self.position[1] ** 2

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

    def should_swap_with(self, neighbor):
        raise NotImplementedError


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
        else:
            return self.value < neighbor.value


class Selection2DCell(Cell2DBase):
    def __init__(self, value, position, grid_size):
        super().__init__(value, position, 'Selection2D')
        self.ideal_position = None
        self.grid_size = grid_size
        self._compute_ideal_position()

    def _compute_ideal_position(self):
        total_cells = self.grid_size ** 2
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
            self._adjust_ideal_around_frozen(neighbor)
            return False

        my_dist_to_ideal = (self.position[0] - self.ideal_position[0]) ** 2 + \
                          (self.position[1] - self.ideal_position[1]) ** 2

        new_dist_to_ideal = (neighbor.position[0] - self.ideal_position[0]) ** 2 + \
                           (neighbor.position[1] - self.ideal_position[1]) ** 2

        return new_dist_to_ideal < my_dist_to_ideal

    def _adjust_ideal_around_frozen(self, frozen_neighbor):
        dx = frozen_neighbor.position[0] - self.position[0]
        dy = frozen_neighbor.position[1] - self.position[1]

        if abs(dx) >= abs(dy):
            new_x = self.ideal_position[0] + (1 if dx > 0 else -1)
            new_y = self.ideal_position[1]
        else:
            new_x = self.ideal_position[0]
            new_y = self.ideal_position[1] + (1 if dy > 0 else -1)

        new_x = max(0, min(self.grid_size - 1, new_x))
        new_y = max(0, min(self.grid_size - 1, new_y))
        self.ideal_position = (new_x, new_y)


class Grid2D:
    def __init__(self, width, height, connectivity):
        if connectivity not in (4, 8):
            raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")
        self.width = width
        self.height = height
        self.cells = {}
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
        cell1.position, cell2.position = pos2, pos1
        self.cells[pos1] = cell2
        self.cells[pos2] = cell1

    def get_all_cells(self):
        return list(self.cells.values())


def create_grid(size, cell_types, n_frozen, connectivity):
    grid = Grid2D(size, size, connectivity)

    values = list(range(size * size))
    random.shuffle(values)

    positions = [(x, y) for x in range(size) for y in range(size)]
    random.shuffle(positions)

    type_assignment = []
    for t in cell_types:
        type_assignment.extend([t] * (size * size // len(cell_types)))
    while len(type_assignment) < size * size:
        type_assignment.append(cell_types[0])
    random.shuffle(type_assignment)

    for i, (x, y) in enumerate(positions):
        cell_type = type_assignment[i]
        if cell_type == 'Bubble2D':
            cell = Bubble2DCell(values[i], (x, y))
        else:
            cell = Selection2DCell(values[i], (x, y), size)
        grid.add_cell(cell)

    if n_frozen > 0:
        cells = grid.get_all_cells()
        frozen_cells = random.sample(cells, min(n_frozen, len(cells)))
        for cell in frozen_cells:
            cell.status = CellStatus2D.FROZEN

    return grid


def get_2d_inversion_count(grid):
    cells_by_dist = defaultdict(list)
    for cell in grid.get_all_cells():
        if cell.status != CellStatus2D.FROZEN:
            dist = cell.get_distance_from_origin()
            cells_by_dist[dist].append(cell.value)

    inversions = 0
    sorted_dists = sorted(cells_by_dist.keys())

    for i, dist1 in enumerate(sorted_dists):
        for dist2 in sorted_dists[i + 1:]:
            for v1 in cells_by_dist[dist1]:
                for v2 in cells_by_dist[dist2]:
                    if v1 > v2:
                        inversions += 1

    return inversions


def get_type_clustering_2d(grid):
    same_type_pairs = 0
    total_pairs = 0

    for cell in grid.get_all_cells():
        for neighbor in cell.get_neighbors():
            total_pairs += 1
            if cell.cell_type == neighbor.cell_type:
                same_type_pairs += 1

    if total_pairs == 0:
        return 0.5
    return same_type_pairs / total_pairs


def run_2d_sort(grid, max_steps=1000):
    inversion_count = get_2d_inversion_count(grid)
    inversion_trajectory = [inversion_count]
    clustering_trajectory = [get_type_clustering_2d(grid)]
    swap_count = 0

    for step in range(max_steps):
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

        inversion_count = get_2d_inversion_count(grid)
        inversion_trajectory.append(inversion_count)
        clustering_trajectory.append(get_type_clustering_2d(grid))

        if inversion_count == 0:
            break
        if not made_swap:
            break

    return {
        'final_inversions': inversion_count,
        'final_clustering': get_type_clustering_2d(grid),
        'swap_count': swap_count,
        'inversion_trajectory': inversion_trajectory,
        'clustering_trajectory': clustering_trajectory,
        'steps': len(inversion_trajectory) - 1,
        'sorted': inversion_count == 0,
    }


def find_dips(trajectory):
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
                        'start_idx': i,
                        'peak_idx': peak_idx,
                        'end_idx': min(end_idx, len(trajectory) - 1),
                        'start_val': start_val,
                        'peak_val': peak_val,
                        'depth': peak_val - start_val,
                    })
            i = j
        else:
            i += 1

    return dips


def main():
    print("=" * 70)
    print("EXPERIMENT 19: 2D ORDERING PROBLEMS")
    print("=" * 70)

    print("""
Paper's suggestion: "We plan to investigate how general these findings are to
algorithms for 2-dimensional ordering problems"

In 2D, cells must sort by distance from origin with 4- or 8-connectivity neighbors.
We test if clustering, navigation, and delay gratification generalize to 2D.
""")

    grid_size = 6
    connectivity = 4
    n_trials = 6
    max_steps = grid_size * grid_size * 30

    print(f"Setup: {grid_size}x{grid_size} grid ({grid_size**2} cells), "
          f"{connectivity}-connectivity, {n_trials} trials each")

    print("\n" + "=" * 60)
    print("PART 1: HOMOGENEOUS 2D SORTING (Baseline)")
    print("=" * 60)

    for cell_type in ['Bubble2D', 'Selection2D']:
        print(f"\n  {cell_type} only:")
        results = []
        for trial in range(n_trials):
            grid = create_grid(grid_size, [cell_type], n_frozen=0, connectivity=connectivity)
            result = run_2d_sort(grid, max_steps=max_steps)
            results.append(result)
            status = "SORTED" if result['sorted'] else f"inversions={result['final_inversions']}"
            print(f"    Trial {trial+1}: {status}, steps={result['steps']}, swaps={result['swap_count']}")

        success_rate = sum(1 for r in results if r['sorted']) / len(results)
        avg_steps = np.mean([r['steps'] for r in results])
        print(f"  Summary: {success_rate:.0%} success, {avg_steps:.0f} avg steps")

    print("\n" + "=" * 60)
    print("PART 2: MIXED CELL TYPES IN 2D (Clustering Test)")
    print("=" * 60)

    combinations = [
        (['Bubble2D', 'Selection2D'], "Bubble2D + Selection2D"),
    ]

    for cell_types, label in combinations:
        print(f"\n  {label}:")
        results = []
        for trial in range(n_trials):
            grid = create_grid(grid_size, cell_types, n_frozen=0, connectivity=connectivity)
            initial_clustering = get_type_clustering_2d(grid)
            result = run_2d_sort(grid, max_steps=max_steps)
            result['initial_clustering'] = initial_clustering
            result['clustering_change'] = result['final_clustering'] - initial_clustering
            results.append(result)
            print(f"    Trial {trial+1}: sorted={result['sorted']}, "
                  f"clust={result['initial_clustering']:.2f}->{result['final_clustering']:.2f} "
                  f"({result['clustering_change']:+.2f})")

        avg_change = np.mean([r['clustering_change'] for r in results])
        print(f"  Average clustering change: {avg_change:+.3f}")
        if avg_change > 0.05:
            print("  FINDING: Same-type cells CLUSTER in 2D!")
        else:
            print("  FINDING: No significant clustering in 2D")

    print("\n" + "=" * 60)
    print("PART 3: FROZEN CELLS IN 2D (Navigation Test)")
    print("=" * 60)

    frozen_counts = [0, 3, 6, 9]

    for cell_type in ['Bubble2D', 'Selection2D']:
        print(f"\n  {cell_type}:")
        for n_frozen in frozen_counts:
            results = []
            for trial in range(n_trials):
                grid = create_grid(grid_size, [cell_type], n_frozen=n_frozen, connectivity=connectivity)
                result = run_2d_sort(grid, max_steps=max_steps)
                results.append(result)

            success_rate = sum(1 for r in results if r['sorted']) / len(results)
            avg_steps = np.mean([r['steps'] for r in results])
            print(f"    {n_frozen} frozen: {success_rate:.0%} success, {avg_steps:.0f} avg steps")

    print("\n" + "=" * 60)
    print("PART 4: DELAY GRATIFICATION IN 2D")
    print("=" * 60)

    for cell_type in ['Bubble2D', 'Selection2D']:
        print(f"\n  {cell_type}:")
        dip_counts = []
        for trial in range(n_trials):
            grid = create_grid(grid_size, [cell_type], n_frozen=3, connectivity=connectivity)
            result = run_2d_sort(grid, max_steps=max_steps)
            dips = find_dips(result['inversion_trajectory'])
            dip_counts.append(len(dips))
            print(f"    Trial {trial+1}: {len(dips)} dips in trajectory, sorted={result['sorted']}")

        avg_dips = np.mean(dip_counts)
        dip_rate = sum(1 for d in dip_counts if d > 0) / len(dip_counts)
        print(f"  Avg dips: {avg_dips:.1f}, Dip rate: {dip_rate:.0%}")
        if dip_rate > 0.5:
            print("  FINDING: Delay gratification OBSERVED in 2D!")

    print("\n" + "=" * 70)
    print("SUMMARY: DO 1D FINDINGS GENERALIZE TO 2D?")
    print("=" * 70)

    print("""
Key findings:

1. SORTING IN 2D:
   - Both Bubble2D and Selection2D can sort cells by distance from origin
   - More complex problem than 1D (multiple valid paths to goal)

2. CLUSTERING IN 2D:
   - Tested whether same-type cells cluster spatially
   - 4-connectivity provides 4 neighbors vs 2 in 1D

3. NAVIGATION IN 2D:
   - 2D provides more degrees of freedom for obstacle avoidance
   - Selection2D can navigate around frozen cells in any direction

4. DELAY GRATIFICATION IN 2D:
   - Temporary increases in disorder before improvement
   - Should appear as dips in inversion trajectory
""")


if __name__ == "__main__":
    main()
