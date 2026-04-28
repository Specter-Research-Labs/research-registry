"""Debug script to understand WHY Bubble2D gets stuck."""

import random
from collections import defaultdict


class Grid2D:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cells = {}

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


class Cell2D:
    def __init__(self, value, position):
        self.value = value
        self.position = position
        self.grid = None

    def get_distance(self, pos=None):
        if pos is None:
            pos = self.position
        return pos[0] ** 2 + pos[1] ** 2

    def get_neighbors(self):
        neighbors = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = self.position[0] + dx, self.position[1] + dy
            if 0 <= nx < self.grid.width and 0 <= ny < self.grid.height:
                neighbor = self.grid.get_cell_at(nx, ny)
                if neighbor:
                    neighbors.append(neighbor)
        return neighbors

    def should_swap_with(self, neighbor):
        my_dist = self.get_distance()
        their_dist = neighbor.get_distance(neighbor.position)

        if my_dist < their_dist:
            return self.value > neighbor.value
        elif my_dist > their_dist:
            return self.value < neighbor.value
        return False


def create_stuck_grid():
    grid = Grid2D(6, 6)
    final_values = [
        [0, 1, 4, 5, 6, 28],
        [2, 7, 11, 13, 24, 31],
        [3, 8, 14, 15, 26, 32],
        [9, 12, 17, 20, 27, 33],
        [10, 16, 18, 22, 29, 34],
        [19, 21, 23, 25, 30, 35],
    ]

    for y in range(6):
        for x in range(6):
            cell = Cell2D(final_values[y][x], (x, y))
            grid.add_cell(cell)

    return grid


def print_grid_with_distances(grid):
    print("\nGrid values:")
    for y in range(6):
        row = []
        for x in range(6):
            cell = grid.get_cell_at(x, y)
            row.append(f"{cell.value:2d}")
        print("  " + " ".join(row))

    print("\nDistance from origin:")
    for y in range(6):
        row = []
        for x in range(6):
            dist = x**2 + y**2
            row.append(f"{dist:2d}")
        print("  " + " ".join(row))


def find_all_inversions(grid):
    cells_by_dist = defaultdict(list)
    for cell in grid.get_all_cells():
        dist = cell.get_distance()
        cells_by_dist[dist].append(cell)

    inversions = []
    sorted_dists = sorted(cells_by_dist.keys())

    for i, d1 in enumerate(sorted_dists):
        for d2 in sorted_dists[i+1:]:
            for c1 in cells_by_dist[d1]:
                for c2 in cells_by_dist[d2]:
                    if c1.value > c2.value:
                        inversions.append((c1, c2, d1, d2))

    return inversions


def are_neighbors(c1, c2):
    dx = abs(c1.position[0] - c2.position[0])
    dy = abs(c1.position[1] - c2.position[1])
    return (dx == 1 and dy == 0) or (dx == 0 and dy == 1)


def find_any_valid_swap(grid):
    for cell in grid.get_all_cells():
        for neighbor in cell.get_neighbors():
            if cell.should_swap_with(neighbor):
                return (cell, neighbor)
    return None


def main():
    print("=" * 70)
    print("DEBUG: Understanding why Bubble2D gets stuck")
    print("=" * 70)

    grid = create_stuck_grid()
    print_grid_with_distances(grid)

    print("\n" + "=" * 50)
    print("Looking for inversions...")
    print("=" * 50)

    inversions = find_all_inversions(grid)
    print(f"\nTotal inversions found: {len(inversions)}")

    if inversions:
        print("\nInversions (cell at closer distance has HIGHER value than cell farther):")
        for c1, c2, d1, d2 in inversions:
            neighbors = "NEIGHBORS" if are_neighbors(c1, c2) else "NOT neighbors"
            print(f"  Value {c1.value} at {c1.position} (dist={d1}) > Value {c2.value} at {c2.position} (dist={d2}) [{neighbors}]")

    print("\n" + "=" * 50)
    print("Looking for valid swaps...")
    print("=" * 50)

    swap = find_any_valid_swap(grid)
    if swap:
        c1, c2 = swap
        print(f"\nFound valid swap: {c1.value} at {c1.position} with {c2.value} at {c2.position}")
    else:
        print("\nNO VALID SWAPS EXIST")
        print("This is why Bubble2D is stuck!")

    print("\n" + "=" * 50)
    print("Analysis of each inversion:")
    print("=" * 50)

    for c1, c2, d1, d2 in inversions:
        print(f"\nInversion: val {c1.value} at {c1.position} (d={d1}) should be AFTER val {c2.value} at {c2.position} (d={d2})")

        if are_neighbors(c1, c2):
            print("  They ARE neighbors - should be able to swap directly!")
            if c1.should_swap_with(c2):
                print("  should_swap_with returns TRUE")
            else:
                print("  should_swap_with returns FALSE - BUG?")
        else:
            print("  NOT neighbors - need intermediate swaps")

            c1_neighbors = c1.get_neighbors()
            c2_neighbors = c2.get_neighbors()

            print(f"  {c1.value}'s neighbors: {[(n.value, n.position) for n in c1_neighbors]}")
            print(f"  {c2.value}'s neighbors: {[(n.value, n.position) for n in c2_neighbors]}")

            can_c1_swap = any(c1.should_swap_with(n) for n in c1_neighbors)
            can_c2_swap = any(c2.should_swap_with(n) for n in c2_neighbors)

            print(f"  Can {c1.value} swap with any neighbor? {can_c1_swap}")
            print(f"  Can {c2.value} swap with any neighbor? {can_c2_swap}")


def trace_path_between(grid, c1, c2):
    """Try to find a path of valid swaps from c1 to c2."""
    print(f"\n  Tracing path from {c1.value} at {c1.position} to {c2.value} at {c2.position}")

    from collections import deque

    pos1, pos2 = c1.position, c2.position

    visited = {pos1}
    queue = deque([(pos1, [pos1])])

    while queue:
        current_pos, path = queue.popleft()

        if current_pos == pos2:
            print(f"    Path found: {path}")
            return path

        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = current_pos[0] + dx, current_pos[1] + dy
            if 0 <= nx < 6 and 0 <= ny < 6 and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append(((nx, ny), path + [(nx, ny)]))

    print("    No path found")
    return None


def analyze_one_inversion_deeply(grid):
    print("\n" + "=" * 60)
    print("DEEP DIVE: One specific inversion")
    print("=" * 60)

    c7 = grid.get_cell_at(1, 1)
    c4 = grid.get_cell_at(2, 0)

    print(f"\nInversion: {c7.value} at (1,1) [dist=2] vs {c4.value} at (2,0) [dist=4]")
    print(f"  Cell 7 should move farther from origin, or Cell 4 should move closer")

    trace_path_between(grid, c7, c4)

    print("\n  Looking at the path (1,1) -> (2,1) -> (2,0):")

    c_mid = grid.get_cell_at(2, 1)
    print(f"    (1,1) has value {c7.value}, dist=2")
    print(f"    (2,1) has value {c_mid.value}, dist=5")
    print(f"    (2,0) has value {c4.value}, dist=4")

    print(f"\n  For 7 to move from (1,1) to (2,1):")
    print(f"    7 at dist=2, 11 at dist=5")
    print(f"    Since 2 < 5 (7 is closer), swap if 7 > 11? {c7.value} > {c_mid.value}? {c7.value > c_mid.value}")
    print(f"    --> 7 > 11 is FALSE, so NO SWAP")

    print(f"\n  The problem: 7 needs to move outward to make room for 4,")
    print(f"  but 11 is already 'larger' so 7 won't swap with 11.")
    print(f"  The intermediate cell (11) is correctly ordered relative to both!")

    print(f"\n  This is the local minimum trap:")
    print(f"    - (1,1) with value 7 is LOCALLY correct relative to neighbors 2,11,1,8")
    print(f"    - (2,0) with value 4 is LOCALLY correct relative to neighbors 1,5,11")
    print(f"    - But GLOBALLY, 7 should be farther than 4")
    print(f"    - The cells between them (like 11) block the swap path")


if __name__ == "__main__":
    main()
    grid = create_stuck_grid()
    analyze_one_inversion_deeply(grid)
