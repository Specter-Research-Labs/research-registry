"""
EXPERIMENT 17: Duplicate Values (Dissociating Sorting from Clustering)

Paper's claim: "By allowing repeated digits, we were able to partially dissociate
the pressures of the explicit algorithm (to sort elements based on numerical value)
from the tendencies of the emergent aspect of the Algotype (to cluster with
like-minded elements)"

Key insight: With duplicates, multiple valid sorted orderings exist.
Among cells with the same value, their relative order is arbitrary for sorting.
If same-type cells cluster among same-value cells, that's emergence BEYOND sorting.

We test:
1. Multiple duplicate density levels
2. Whether clustering persists among same-value cells
3. Type-clustering vs value-clustering separation
"""

import threading
import time
import random
import numpy as np
from collections import defaultdict

from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus


def is_sorted(cells):
    prev = cells[0]
    for c in cells:
        if c.value < prev.value:
            return False
        prev = c
    return True


def kill_all(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def measure_type_clustering(cells):
    types = [c.cell_type for c in cells]
    same = sum(1 for i in range(len(types)-1) if types[i] == types[i+1])
    return same / (len(types) - 1) if len(types) > 1 else 0


def measure_intra_value_clustering(cells):
    """
    Measure clustering among cells with the same value.
    For each group of same-value cells, measure if same-type cells are adjacent.
    This is the key metric: if same-type cells cluster WITHIN value groups,
    that's emergence beyond sorting pressure.
    """
    value_groups = defaultdict(list)
    for i, c in enumerate(cells):
        value_groups[c.value].append((i, c.cell_type))

    total_pairs = 0
    same_type_pairs = 0

    for value, positions in value_groups.items():
        if len(positions) < 2:
            continue
        positions.sort(key=lambda x: x[0])
        for i in range(len(positions) - 1):
            pos1, type1 = positions[i]
            pos2, type2 = positions[i + 1]
            if pos2 - pos1 == 1:
                total_pairs += 1
                if type1 == type2:
                    same_type_pairs += 1

    if total_pairs == 0:
        return None
    return same_type_pairs / total_pairs


def generate_values(n_cells, mode):
    """Generate values with different duplicate densities"""
    if mode == 'unique':
        return list(range(n_cells))
    elif mode == 'low':
        return [random.randint(0, n_cells // 2) for _ in range(n_cells)]
    elif mode == 'high':
        return [random.randint(0, n_cells // 4) for _ in range(n_cells)]
    elif mode == 'extreme':
        return [random.randint(0, n_cells // 10) for _ in range(n_cells)]
    else:
        raise ValueError(f"Unknown mode: {mode}")


def create_cell(cell_type, i, value, threadLock, cells, left_boundary, right_boundary, status_probe):
    if cell_type == 'Bubble':
        return BubbleSortCell(i + 1, value, threadLock, (i, 1), cells,
                             left_boundary, right_boundary, status_probe,
                             disable_visualization=True)
    elif cell_type == 'Selection':
        return SelectionSortCell(i + 1, value, threadLock, (i, 1), cells,
                                left_boundary, right_boundary, status_probe,
                                disable_visualization=True)
    elif cell_type == 'Insertion':
        return InsertionSortCell(i + 1, value, threadLock, (i, 1), cells,
                                left_boundary, right_boundary, status_probe,
                                disable_visualization=True)


def run_trial(n_cells, type1, type2, value_mode, timeout=30):
    values = generate_values(n_cells, value_mode)
    random.shuffle(values)

    unique_values = len(set(values))

    types = [type1] * (n_cells // 2) + [type2] * (n_cells - n_cells // 2)
    random.shuffle(types)

    threadLock = threading.Lock()
    status_probe = StatusProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    for i in range(n_cells):
        cell = create_cell(types[i], i, values[i], threadLock, cells,
                          left_boundary, right_boundary, status_probe)
        cells.append(cell)

    if type1 == 'Insertion' or type2 == 'Insertion':
        for c in cells:
            if c.cell_type == 'Insertion':
                c.enable_to_move = True
                break

    cell_group = CellGroup(cells, cells, 0, left_boundary, right_boundary,
                          GroupStatus.ACTIVE, threadLock, 100000000, 100000000)
    for cell in cells:
        cell.group = cell_group

    initial_type_clustering = measure_type_clustering(cells)
    initial_intra_value = measure_intra_value_clustering(cells)

    threadLock.acquire()
    for cell in cells:
        cell.start()
    cell_group.start()
    threadLock.release()

    type_trajectory = [initial_type_clustering]
    intra_trajectory = [initial_intra_value]

    start = time.time()
    last_swaps = 0
    while not is_sorted(cells) and time.time() - start < timeout:
        current_swaps = status_probe.swap_count
        if current_swaps > last_swaps + 3:
            type_trajectory.append(measure_type_clustering(cells))
            intra_trajectory.append(measure_intra_value_clustering(cells))
            last_swaps = current_swaps
        time.sleep(0.02)

    final_type_clustering = measure_type_clustering(cells)
    final_intra_value = measure_intra_value_clustering(cells)

    type_trajectory.append(final_type_clustering)
    intra_trajectory.append(final_intra_value)

    threadLock.acquire()
    kill_all(cells, [cell_group])
    threadLock.release()

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        'success': is_sorted(cells),
        'value_mode': value_mode,
        'unique_values': unique_values,
        'initial_type_clustering': initial_type_clustering,
        'final_type_clustering': final_type_clustering,
        'max_type_clustering': max(type_trajectory),
        'initial_intra_value': initial_intra_value,
        'final_intra_value': final_intra_value,
        'type_increase': final_type_clustering - initial_type_clustering,
        'intra_trajectory': [x for x in intra_trajectory if x is not None],
        'swap_count': status_probe.swap_count,
    }


def main():
    print("=" * 70)
    print("EXPERIMENT 17: DUPLICATE VALUES AND CLUSTERING")
    print("=" * 70)

    print("""
Paper's claim: "By allowing repeated digits, we were able to partially dissociate
the pressures of the explicit algorithm (to sort elements based on numerical
value) from the tendencies of the emergent aspect of the Algotype (to cluster
with like-minded elements)"

Key question: Does type-clustering persist among cells with the SAME value?
If yes -> clustering is emergent, not a sorting artifact
If no  -> clustering was just a side effect of racing to positions
""")

    n_cells = 30
    n_trials = 8
    value_modes = ['unique', 'low', 'high', 'extreme']

    combinations = [
        ('Bubble', 'Selection'),
        ('Bubble', 'Insertion'),
        ('Selection', 'Insertion'),
    ]

    print(f"Setup: {n_cells} cells, {n_trials} trials each")
    print(f"Value modes: {value_modes}")
    print(f"Combinations: {combinations}\n")

    all_results = {}

    for type1, type2 in combinations:
        combo_name = f"{type1}+{type2}"
        print(f"\n{'='*60}")
        print(f"Testing: {combo_name}")
        print(f"{'='*60}")

        all_results[combo_name] = {}

        for mode in value_modes:
            print(f"\n  {mode.upper()} values:")
            trial_results = []

            for trial in range(n_trials):
                result = run_trial(n_cells, type1, type2, mode)
                trial_results.append(result)
                status = "OK" if result['success'] else "FAIL"
                print(f"    Trial {trial+1}: {status}, type_clust={result['final_type_clustering']:.2f}, "
                      f"intra={result['final_intra_value']:.2f}" if result['final_intra_value'] else
                      f"    Trial {trial+1}: {status}, type_clust={result['final_type_clustering']:.2f}, intra=N/A")

            success_rate = sum(1 for r in trial_results if r['success']) / len(trial_results)
            avg_type_clustering = np.mean([r['final_type_clustering'] for r in trial_results])
            avg_type_increase = np.mean([r['type_increase'] for r in trial_results])

            intra_values = [r['final_intra_value'] for r in trial_results if r['final_intra_value'] is not None]
            avg_intra = np.mean(intra_values) if intra_values else None

            unique_avg = np.mean([r['unique_values'] for r in trial_results])

            print(f"\n  Summary: success={success_rate:.0%}, unique_vals={unique_avg:.0f}/{n_cells}")
            print(f"           type_clust={avg_type_clustering:.3f}, type_increase={avg_type_increase:+.3f}")
            if avg_intra is not None:
                print(f"           intra_value_clust={avg_intra:.3f}")

            all_results[combo_name][mode] = {
                'success_rate': success_rate,
                'avg_type_clustering': avg_type_clustering,
                'avg_type_increase': avg_type_increase,
                'avg_intra_value': avg_intra,
                'unique_values': unique_avg,
            }

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print(f"\n{'Combo':<20} {'Mode':<10} {'Success':<10} {'Type Clust':<12} {'Type Inc':<10} {'Intra-Val':<12}")
    print("-" * 74)

    for combo_name in all_results:
        for mode in value_modes:
            r = all_results[combo_name][mode]
            intra_str = f"{r['avg_intra_value']:.3f}" if r['avg_intra_value'] is not None else "N/A"
            print(f"{combo_name:<20} {mode:<10} {r['success_rate']:<10.0%} "
                  f"{r['avg_type_clustering']:<12.3f} {r['avg_type_increase']:<+10.3f} {intra_str:<12}")

    print("\n" + "=" * 70)
    print("ANALYSIS: DOES CLUSTERING PERSIST WITH DUPLICATES?")
    print("=" * 70)

    for combo_name in all_results:
        unique_clust = all_results[combo_name]['unique']['avg_type_clustering']
        extreme_clust = all_results[combo_name]['extreme']['avg_type_clustering']

        unique_inc = all_results[combo_name]['unique']['avg_type_increase']
        extreme_inc = all_results[combo_name]['extreme']['avg_type_increase']

        print(f"\n{combo_name}:")
        print(f"  Unique:  final_clust={unique_clust:.3f}, increase={unique_inc:+.3f}")
        print(f"  Extreme: final_clust={extreme_clust:.3f}, increase={extreme_inc:+.3f}")

        if extreme_inc > 0.05 and extreme_inc >= unique_inc * 0.5:
            print(f"  FINDING: Clustering PERSISTS with duplicates")
            print(f"           -> Supports emergent 'racing efficiency' hypothesis")
        elif extreme_inc < unique_inc * 0.3:
            print(f"  FINDING: Clustering REDUCED with duplicates")
            print(f"           -> Clustering partly due to position-racing")
        else:
            print(f"  FINDING: Clustering PARTIALLY persists")
            print(f"           -> Mixed: some emergence, some position effect")

    print("\n" + "=" * 70)
    print("INTRA-VALUE CLUSTERING (KEY TEST)")
    print("=" * 70)
    print("""
This measures clustering AMONG cells with the same value.
Since same-value cells can end up in any relative order (all orderings valid),
clustering here is PURE emergence - not a sorting artifact.
""")

    for combo_name in all_results:
        print(f"\n{combo_name}:")
        for mode in ['low', 'high', 'extreme']:
            intra = all_results[combo_name][mode]['avg_intra_value']
            if intra is not None:
                baseline = 0.5
                print(f"  {mode}: intra-value clustering = {intra:.3f}", end="")
                if intra > baseline + 0.1:
                    print(" -> SIGNIFICANT clustering among same-value cells!")
                elif intra < baseline - 0.1:
                    print(" -> Below random (possible anti-clustering)")
                else:
                    print(" -> Near random baseline")
            else:
                print(f"  {mode}: N/A (no adjacent same-value cells)")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)

    any_significant_intra = any(
        all_results[combo][mode]['avg_intra_value'] is not None and
        all_results[combo][mode]['avg_intra_value'] > 0.6
        for combo in all_results
        for mode in ['low', 'high', 'extreme']
    )

    clustering_persists = any(
        all_results[combo]['extreme']['avg_type_increase'] > 0.05
        for combo in all_results
    )

    if any_significant_intra:
        print("""
FINDING: STRONG EVIDENCE FOR EMERGENT CLUSTERING

Same-type cells cluster even among cells with IDENTICAL values, where the
sorting algorithm imposes no ordering pressure. This is genuine emergence:
- Not an artifact of value->position mapping
- Must be due to movement dynamics (faster algorithms cluster)
- Supports the paper's 'Algotype' concept as meaningful
""")
    elif clustering_persists:
        print("""
FINDING: MODERATE EVIDENCE FOR CLUSTERING

Overall type-clustering persists with duplicates, but intra-value clustering
is not significant. This suggests:
- Some clustering is emergent from movement dynamics
- Some is still tied to value-position racing
- The 'Algotype' concept has partial validity
""")
    else:
        print("""
FINDING: CLUSTERING IS MOSTLY A SORTING ARTIFACT

Clustering disappears or significantly reduces with duplicates.
The 'Algotype' clustering may be primarily an artifact of:
- Deterministic value->position mapping
- Racing to specific positions, not emergent grouping
""")


if __name__ == "__main__":
    main()
