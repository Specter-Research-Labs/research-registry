"""
EXPERIMENT 15: Delay Gratification Analysis

Question: Do cells exhibit "delay gratification" - temporarily reducing sortedness
to navigate around obstacles?

The paper claims cells "temporarily decrease sortedness to navigate around obstacles."
This is an EMERGENT property - no cell is programmed to "reduce global monotonicity
strategically" - they all try to improve their local situation.

We measure:
1. Monotonicity trajectory over time
2. "Dip" events where monotonicity temporarily increases (gets worse) before improving
3. Whether dips correlate with successful outcomes
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


def get_monotonicity(arr):
    if len(arr) < 2:
        return 0
    prev = arr[0]
    errors = 0
    for i in range(1, len(arr)):
        if arr[i] < prev:
            errors += 1
        prev = arr[i]
    return errors


class TrackingProbe(StatusProbe):
    def __init__(self):
        super().__init__()
        self.monotonicity_history = []

    def record_sorting_step(self, step):
        super().record_sorting_step(step)
        mono = get_monotonicity(step)
        self.monotonicity_history.append(mono)


def find_dips(trajectory):
    if len(trajectory) < 3:
        return []

    dips = []
    i = 0
    while i < len(trajectory) - 2:
        if trajectory[i+1] > trajectory[i]:
            start_val = trajectory[i]
            peak_val = trajectory[i+1]
            peak_idx = i + 1

            j = i + 2
            while j < len(trajectory) and trajectory[j] >= trajectory[j-1]:
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
                        'end_idx': min(end_idx, len(trajectory)-1),
                        'start_val': start_val,
                        'peak_val': peak_val,
                        'depth': peak_val - start_val,
                    })
            i = j
        else:
            i += 1

    return dips


def run_trial(n_cells, cell_class, n_frozen, timeout=20):
    values = list(range(n_cells))
    random.shuffle(values)

    threadLock = threading.Lock()
    probe = TrackingProbe()

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

    frozen_indices = set()
    if n_frozen > 0:
        frozen_indices = set(random.sample(range(n_cells), n_frozen))
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

    def is_done():
        prev = -1
        for c in cells:
            if c.status == CellStatus.FREEZE:
                continue
            if c.value < prev:
                return False
            prev = c.value
        return True

    start = time.time()
    while not is_done() and time.time() - start < timeout:
        time.sleep(0.02)

    success = is_done()
    trajectory = probe.monotonicity_history.copy()

    threadLock.acquire()
    for c in cells:
        c.status = CellStatus.INACTIVE
    cell_group.status = GroupStatus.MERGED
    threadLock.release()

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    dips = find_dips(trajectory)

    return {
        'success': success,
        'trajectory': trajectory,
        'dips': dips,
        'num_dips': len(dips),
        'total_depth': sum(d['depth'] for d in dips) if dips else 0,
        'max_depth': max(d['depth'] for d in dips) if dips else 0,
    }


def main():
    print("=" * 70)
    print("EXPERIMENT 15: DELAY GRATIFICATION ANALYSIS")
    print("=" * 70)

    print("""
Question: Do cells exhibit "delay gratification" - temporarily reducing
sortedness to navigate around obstacles?

A "dip" = monotonicity temporarily INCREASES (worse) before DECREASING (better)
This is the paper's key claim about emergent problem-solving.
""")

    n_cells = 30
    n_trials = 10
    frozen_counts = [0, 3, 6]

    algorithms = {
        'Bubble': BubbleSortCell,
        'Selection': SelectionSortCell,
        'Insertion': InsertionSortCell,
    }

    print(f"Setup: {n_cells} cells, {n_trials} trials each")
    print(f"Frozen counts: {frozen_counts}\n")

    results = {name: {} for name in algorithms}
    sample_trajectories = {}

    for algo_name, cell_class in algorithms.items():
        print(f"\n{algo_name} Sort:")

        for n_frozen in frozen_counts:
            trial_results = []
            for trial in range(n_trials):
                result = run_trial(n_cells, cell_class, n_frozen)
                trial_results.append(result)

                if trial == 0 and n_frozen == 3:
                    sample_trajectories[algo_name] = result['trajectory']

            success_rate = sum(1 for r in trial_results if r['success']) / len(trial_results)
            avg_dips = np.mean([r['num_dips'] for r in trial_results])
            avg_depth = np.mean([r['total_depth'] for r in trial_results])
            max_depth = max(r['max_depth'] for r in trial_results)

            trials_with_dips = sum(1 for r in trial_results if r['num_dips'] > 0)
            dip_rate = trials_with_dips / len(trial_results)

            print(f"  {n_frozen} frozen: success={success_rate:.0%}, dip_rate={dip_rate:.0%}, avg_dips={avg_dips:.1f}, max_depth={max_depth}")

            results[algo_name][n_frozen] = {
                'success_rate': success_rate,
                'dip_rate': dip_rate,
                'avg_dips': avg_dips,
                'avg_depth': avg_depth,
                'max_depth': max_depth,
                'trials': trial_results,
            }

    print("\n" + "=" * 70)
    print("SAMPLE TRAJECTORIES (3 frozen cells)")
    print("=" * 70)

    for algo_name, traj in sample_trajectories.items():
        if len(traj) > 0:
            traj_str = " ".join(str(m) for m in traj[:50])
            if len(traj) > 50:
                traj_str += f" ... ({len(traj)} total steps)"
            print(f"\n{algo_name}: {traj_str}")

            dips = find_dips(traj)
            if dips:
                print(f"  Dips found: {len(dips)}")
                for i, d in enumerate(dips[:3]):
                    print(f"    Dip {i+1}: mono {d['start_val']} -> {d['peak_val']} -> recovered (depth={d['depth']})")

    print("\n" + "=" * 70)
    print("DELAY GRATIFICATION SUMMARY")
    print("=" * 70)

    print(f"\n{'Algorithm':<12} {'Frozen':<8} {'Success':<10} {'Dip Rate':<10} {'Avg Dips':<10} {'Max Depth':<10}")
    print("-" * 60)

    for algo_name in algorithms:
        for n_frozen in frozen_counts:
            r = results[algo_name][n_frozen]
            print(f"{algo_name:<12} {n_frozen:<8} {r['success_rate']:<10.0%} {r['dip_rate']:<10.0%} {r['avg_dips']:<10.1f} {r['max_depth']:<10}")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)

    has_dips = any(
        results[algo][frozen]['dip_rate'] > 0.3
        for algo in algorithms
        for frozen in frozen_counts if frozen > 0
    )

    frozen_increases_dips = all(
        results[algo][3]['avg_dips'] > results[algo][0]['avg_dips']
        for algo in algorithms
    )

    if has_dips:
        print(f"""
FINDING: DELAY GRATIFICATION IS OBSERVABLE

Cells do temporarily increase monotonicity (make things "worse") before
improving. This supports the paper's claim about emergent problem-solving.

Key observations:""")

        if frozen_increases_dips:
            print("""
- Frozen cells INCREASE dip frequency (more obstacles = more navigation)
- This suggests dips are related to obstacle navigation, not random noise""")

        for algo in algorithms:
            if results[algo][3]['dip_rate'] > 0.5:
                print(f"- {algo} shows high dip rate ({results[algo][3]['dip_rate']:.0%}) with frozen cells")

        print("""
The "delay gratification" is emergent: no cell is programmed to "temporarily
make things worse." Each cell optimizes locally, but global monotonicity
can temporarily decrease as cells rearrange around obstacles.
""")
    else:
        print("""
FINDING: MINIMAL DELAY GRATIFICATION OBSERVED

Dips are rare or shallow. The "delay gratification" phenomenon may be
overstated in the paper, or may require specific conditions we didn't test.
""")


if __name__ == "__main__":
    main()
