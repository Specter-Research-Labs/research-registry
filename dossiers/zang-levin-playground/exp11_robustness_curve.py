"""
EXPERIMENT 11: Robustness Curve

Question: Does the system degrade gracefully or catastrophically with damage?

This tests a key Levin claim: systems exhibiting "basal cognition" should show
robustness to perturbation - graceful degradation rather than sudden collapse.

Setup:
- Sweep frozen cell percentage: 0%, 5%, 10%, 15%, 20%, 25%, 30%
- Test all three algorithm types: Bubble, Selection, Insertion
- Measure: success rate, final monotonicity error, time to completion

A graceful curve supports Levin's robustness claim.
A sharp cliff suggests fragile, non-robust behavior.
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


def is_sorted_ignoring_frozen(cells):
    prev_val = -1
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            return False
        prev_val = c.value
    return True


def get_monotonicity_error(cells):
    prev_val = -1
    errors = 0
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            errors += 1
        prev_val = c.value
    return errors


def kill_all(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def run_trial(n_cells, cell_class, n_frozen, timeout=15):
    values = list(range(n_cells))
    random.shuffle(values)

    threadLock = threading.Lock()
    probe = StatusProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    for i in range(n_cells):
        cell = cell_class(
            i + 1, values[i], threadLock, (i, 1), cells,
            left_boundary, right_boundary, probe,
            disable_visualization=True
        )
        cells.append(cell)

    if n_frozen > 0:
        frozen_indices = random.sample(range(n_cells), min(n_frozen, n_cells))
        for idx in frozen_indices:
            cells[idx].status = CellStatus.FREEZE

    cell_group = CellGroup(cells, cells, 0, left_boundary, right_boundary,
                          GroupStatus.ACTIVE, threadLock, 100000000, 100000000)
    for cell in cells:
        cell.group = cell_group

    threadLock.acquire()
    for cell in cells:
        cell.start()
    cell_group.start()
    threadLock.release()

    start = time.time()
    while not is_sorted_ignoring_frozen(cells) and time.time() - start < timeout:
        time.sleep(0.02)

    elapsed = time.time() - start
    success = is_sorted_ignoring_frozen(cells)
    final_error = get_monotonicity_error(cells)
    swap_count = probe.swap_count

    threadLock.acquire()
    kill_all(cells, [cell_group])
    threadLock.release()

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        'success': success,
        'time': elapsed,
        'error': final_error,
        'swaps': swap_count,
    }


def run_experiment(n_cells, cell_class, n_frozen, n_trials=6):
    results = []
    for _ in range(n_trials):
        result = run_trial(n_cells, cell_class, n_frozen)
        results.append(result)
    return results


def main():
    print("=" * 70)
    print("EXPERIMENT 11: ROBUSTNESS CURVE")
    print("=" * 70)

    print("""
Question: Does the system degrade gracefully or catastrophically with damage?

A graceful degradation curve supports Levin's robustness claim.
A sharp cliff suggests fragile, non-robust behavior.
""")

    n_cells = 30
    n_trials = 6
    frozen_percentages = [0, 5, 10, 15, 20, 25, 30]

    algorithms = {
        'Bubble': BubbleSortCell,
        'Selection': SelectionSortCell,
        'Insertion': InsertionSortCell,
    }

    print(f"Setup: {n_cells} cells, {n_trials} trials each")
    print(f"Frozen percentages: {frozen_percentages}%\n")

    results = {name: {} for name in algorithms}

    for name, cell_class in algorithms.items():
        print(f"\n{name} Sort:")
        for pct in frozen_percentages:
            n_frozen = int(n_cells * pct / 100)
            print(f"  {pct}% frozen ({n_frozen} cells)...", end=" ", flush=True)
            trial_results = run_experiment(n_cells, cell_class, n_frozen, n_trials)

            success_rate = sum(1 for r in trial_results if r['success']) / len(trial_results)
            avg_error = np.mean([r['error'] for r in trial_results])
            avg_time = np.mean([r['time'] for r in trial_results])

            print(f"success={success_rate:.0%}, error={avg_error:.1f}, time={avg_time:.1f}s")
            results[name][pct] = {
                'success_rate': success_rate,
                'avg_error': avg_error,
                'avg_time': avg_time,
            }

    print("\n" + "=" * 70)
    print("RESULTS: SUCCESS RATE BY FROZEN PERCENTAGE")
    print("=" * 70)

    header = f"{'Frozen %':<12}"
    for name in algorithms:
        header += f"{name:<15}"
    print(header)
    print("-" * 57)

    for pct in frozen_percentages:
        row = f"{pct}%{'':<10}"
        for name in algorithms:
            rate = results[name][pct]['success_rate']
            row += f"{rate:<15.0%}"
        print(row)

    print("\n" + "=" * 70)
    print("RESULTS: AVERAGE MONOTONICITY ERROR")
    print("=" * 70)

    header = f"{'Frozen %':<12}"
    for name in algorithms:
        header += f"{name:<15}"
    print(header)
    print("-" * 57)

    for pct in frozen_percentages:
        row = f"{pct}%{'':<10}"
        for name in algorithms:
            err = results[name][pct]['avg_error']
            row += f"{err:<15.1f}"
        print(row)

    print("\n" + "=" * 70)
    print("DEGRADATION ANALYSIS")
    print("=" * 70)

    for name in algorithms:
        rates = [results[name][pct]['success_rate'] for pct in frozen_percentages]

        half_point = None
        for i, (pct, rate) in enumerate(zip(frozen_percentages, rates)):
            if rate <= 0.5 and rates[0] > 0.5:
                half_point = pct
                break

        collapse_point = None
        for i, (pct, rate) in enumerate(zip(frozen_percentages, rates)):
            if rate == 0:
                collapse_point = pct
                break

        gradual_score = np.std(np.diff(rates))

        print(f"\n{name}:")
        print(f"  Starting success rate: {rates[0]:.0%}")
        print(f"  Ending success rate (30%): {rates[-1]:.0%}")
        print(f"  50% threshold at: {half_point}% frozen" if half_point else "  50% threshold: not reached")
        print(f"  Complete collapse at: {collapse_point}% frozen" if collapse_point else "  Complete collapse: not reached")
        print(f"  Degradation smoothness: {gradual_score:.3f} (lower = more gradual)")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)

    avg_final_rates = np.mean([results[name][30]['success_rate'] for name in algorithms])

    if avg_final_rates > 0.3:
        print("""
FINDING: GRACEFUL DEGRADATION

The system maintains reasonable success rates even with significant damage.
This supports Levin's claim of robustness - the goal-directed behavior
allows cells to work around obstacles rather than failing completely.
""")
    elif avg_final_rates > 0.1:
        print("""
FINDING: MODERATE DEGRADATION

The system degrades with damage but doesn't collapse entirely.
Some robustness exists, but it's limited.
""")
    else:
        print("""
FINDING: CATASTROPHIC DEGRADATION

The system fails almost completely with significant damage.
This suggests the system is fragile rather than robust.
""")


if __name__ == "__main__":
    main()
