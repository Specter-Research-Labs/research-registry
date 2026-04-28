"""
EXPERIMENT 1: How do frozen (damaged) cells affect clustering?

The paper claims arrays with frozen cells still sort successfully.
Question: Do frozen cells affect clustering? Act as barriers? Nucleation points?
"""

import threading
import time
import random
import numpy as np
from collections import defaultdict

from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.GnomeSortCell import GnomeSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus


def is_sorted_ignoring_frozen(cells):
    prev_val = -1
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            return False
        prev_val = c.value
    return True


def kill_all(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def measure_clustering(cells):
    active_cells = [c for c in cells if c.status != CellStatus.FREEZE]
    if len(active_cells) < 2:
        return 0.5
    types = [c.cell_type for c in active_cells]
    same = sum(1 for i in range(len(types)-1) if types[i] == types[i+1])
    return same / (len(types) - 1)


CELL_CLASSES = {
    'Bubble': BubbleSortCell,
    'Selection': SelectionSortCell,
    'Insertion': InsertionSortCell,
    'Gnome': GnomeSortCell,
}


def create_cell(cell_type, i, value, threadLock, cells, left_boundary, right_boundary, probe):
    cls = CELL_CLASSES[cell_type]
    return cls(i + 1, value, threadLock, (i, 1), cells,
               left_boundary, right_boundary, probe,
               disable_visualization=True)


def run_experiment(n_cells, type1, type2, n_frozen=0, n_trials=15):
    results = []

    for trial in range(n_trials):
        values = list(range(n_cells))
        random.shuffle(values)

        types = [type1] * (n_cells // 2) + [type2] * (n_cells - n_cells // 2)
        random.shuffle(types)

        threadLock = threading.Lock()
        probe = StatusProbe()

        left_boundary = (0, 1)
        right_boundary = (n_cells - 1, 1)
        cells = []

        for i in range(n_cells):
            cell = create_cell(types[i], i, values[i], threadLock, cells,
                              left_boundary, right_boundary, probe)
            cells.append(cell)

        if n_frozen > 0:
            frozen_indices = random.sample(range(n_cells), min(n_frozen, n_cells))
            for idx in frozen_indices:
                cells[idx].status = CellStatus.FREEZE

        if type1 == 'Insertion' or type2 == 'Insertion':
            for c in cells:
                if c.cell_type == 'Insertion' and c.status != CellStatus.FREEZE:
                    c.enable_to_move = True
                    break

        cell_group = CellGroup(cells, cells, 0, left_boundary, right_boundary,
                              GroupStatus.ACTIVE, threadLock, 100000000, 100000000)
        for cell in cells:
            cell.group = cell_group

        init_clustering = measure_clustering(cells)

        threadLock.acquire()
        for cell in cells:
            cell.start()
        cell_group.start()
        threadLock.release()

        start = time.time()
        max_clustering = init_clustering
        while not is_sorted_ignoring_frozen(cells) and time.time() - start < 60:
            c = measure_clustering(cells)
            max_clustering = max(max_clustering, c)
            time.sleep(0.02)

        final_clustering = measure_clustering(cells)
        max_clustering = max(max_clustering, final_clustering)

        threadLock.acquire()
        kill_all(cells, [cell_group])
        threadLock.release()

        for cell in cells:
            cell.join(timeout=1)
        cell_group.join(timeout=1)

        results.append({
            'max_clustering': max_clustering,
            'clustering_increase': max_clustering - 0.5,
        })

    return results


def main():
    print("="*70)
    print("EXPERIMENT 1: FROZEN CELLS EFFECT ON CLUSTERING")
    print("="*70)

    n_cells = 30
    n_trials = 10
    frozen_counts = [0, 3, 6, 9]

    test_combos = [
        ('Bubble', 'Insertion'),
        ('Bubble', 'Gnome'),
    ]

    print(f"\nSetup: {n_cells} cells, {n_trials} trials each")
    print(f"Testing frozen counts: {frozen_counts}")
    print(f"Combinations: {test_combos}\n")

    all_results = []

    for type1, type2 in test_combos:
        print(f"\n{type1} + {type2}:")
        for n_frozen in frozen_counts:
            results = run_experiment(n_cells, type1, type2, n_frozen, n_trials)
            avg = np.mean([r['clustering_increase'] for r in results])
            std = np.std([r['clustering_increase'] for r in results])
            print(f"  {n_frozen:2d} frozen: clustering = {avg:+.3f} (+/-{std:.3f})")
            all_results.append({
                'combo': f"{type1}+{type2}",
                'n_frozen': n_frozen,
                'clustering': avg,
            })

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    print(f"\n{'Combination':<25} {'0 frozen':>12} {'3 frozen':>12} {'6 frozen':>12} {'9 frozen':>12}")
    print("-"*75)

    for combo in [f"{t1}+{t2}" for t1, t2 in test_combos]:
        row = f"{combo:<25}"
        for n_frozen in frozen_counts:
            val = next((r['clustering'] for r in all_results
                       if r['combo'] == combo and r['n_frozen'] == n_frozen), None)
            row += f" {val:>+11.3f}" if val else "         N/A"
        print(row)

    print("\n" + "="*70)
    print("INTERPRETATION")
    print("="*70)

    for combo in [f"{t1}+{t2}" for t1, t2 in test_combos]:
        vals = [r['clustering'] for r in all_results if r['combo'] == combo]
        trend = vals[-1] - vals[0]
        print(f"\n{combo}:")
        if trend > 0.02:
            print(f"  Clustering INCREASES with frozen cells ({trend:+.3f})")
            print(f"  Frozen cells may act as nucleation points")
        elif trend < -0.02:
            print(f"  Clustering DECREASES with frozen cells ({trend:+.3f})")
            print(f"  Frozen cells may disrupt clustering")
        else:
            print(f"  No significant effect ({trend:+.3f})")


if __name__ == "__main__":
    main()
