"""
EXPERIMENT 16: Movable vs Immovable Frozen Cells

Question: Does Bubble perform better with MOVABLE frozen cells, and Selection
with IMMOVABLE?

The paper distinguishes:
- Movable: Can be pushed by other cells, but can't initiate swaps
- Immovable: Complete roadblocks, can't be moved at all

Current implementation:
- Bubble: CAN push frozen cells (movable behavior)
- Selection: Treats frozen as immovable, adjusts goal instead of pushing

We test:
1. Bubble with movable vs immovable
2. Selection with movable vs immovable
"""

import threading
import time
import random
import numpy as np

from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import MultiThreadCell, CellStatus


class ImmovableBubbleCell(BubbleSortCell):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'ImmovableBubble'

    def should_move_to(self, target_position, check_right):
        if (
            self.status == CellStatus.ACTIVE
            and self.within_boundary(target_position)
            and self.cells[int(target_position[0])].status == CellStatus.ACTIVE
        ):
            if self.reverse_direction:
                return self.value < self.cells[int(target_position[0])].value if check_right else self.value > self.cells[int(target_position[0])].value
            return self.value > self.cells[int(target_position[0])].value if check_right else self.value < self.cells[int(target_position[0])].value
        return False


class MovableSelectionCell(SelectionSortCell):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'MovableSelection'

    def should_move_to(self, target_position):
        if not self.within_boundary(target_position):
            return False

        target_cell = self.cells[int(target_position[0])]

        if target_cell.status == CellStatus.FREEZE:
            if self.value < target_cell.value:
                return True
            else:
                if self.reverse_direction:
                    self.ideal_position = (self.ideal_position[0] - 1, self.ideal_position[1])
                else:
                    self.ideal_position = (self.ideal_position[0] + 1, self.ideal_position[1])
                return False

        if (
            self.status == CellStatus.ACTIVE
            and self.current_position != self.ideal_position
            and target_cell.status == CellStatus.ACTIVE
        ):
            if self.value >= target_cell.value:
                if self.reverse_direction:
                    self.ideal_position = (self.ideal_position[0] - 1, self.ideal_position[1])
                else:
                    self.ideal_position = (self.ideal_position[0] + 1, self.ideal_position[1])
                return False
            return True

        return False


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


def run_trial(n_cells, cell_class, n_frozen, timeout=8):
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


def main():
    print("=" * 70)
    print("EXPERIMENT 16: MOVABLE VS IMMOVABLE FROZEN CELLS")
    print("=" * 70)

    print("""
Question: Does Bubble perform better with MOVABLE frozen cells,
and Selection with IMMOVABLE?

Configurations:
- Bubble (movable): Original - can push frozen cells
- Bubble (immovable): Modified - skips frozen cells
- Selection (immovable): Original - adjusts goal when blocked
- Selection (movable): Modified - can push frozen cells
""")

    n_cells = 30
    n_trials = 6
    frozen_counts = [0, 3, 6, 9]

    configs = {
        'Bubble-movable': BubbleSortCell,
        'Bubble-immovable': ImmovableBubbleCell,
        'Selection-immovable': SelectionSortCell,
        'Selection-movable': MovableSelectionCell,
    }

    print(f"Setup: {n_cells} cells, {n_trials} trials each")
    print(f"Frozen counts: {frozen_counts}\n")

    results = {name: {} for name in configs}

    import sys
    for config_name, cell_class in configs.items():
        print(f"\n{config_name}:", flush=True)

        for n_frozen in frozen_counts:
            trial_results = []
            for trial_num in range(n_trials):
                print(f"    Trial {trial_num+1}/{n_trials} (frozen={n_frozen})...", end=" ", flush=True)
                result = run_trial(n_cells, cell_class, n_frozen)
                print(f"{'OK' if result['success'] else 'FAIL'} ({result['time']:.1f}s)", flush=True)
                trial_results.append(result)

            success_rate = sum(1 for r in trial_results if r['success']) / len(trial_results)
            avg_time = np.mean([r['time'] for r in trial_results])
            avg_swaps = np.mean([r['swaps'] for r in trial_results])

            print(f"  {n_frozen} frozen: success={success_rate:.0%}, time={avg_time:.1f}s, swaps={avg_swaps:.0f}")

            results[config_name][n_frozen] = {
                'success_rate': success_rate,
                'avg_time': avg_time,
                'avg_swaps': avg_swaps,
            }

    print("\n" + "=" * 70)
    print("RESULTS COMPARISON")
    print("=" * 70)

    print(f"\n{'Config':<22} {'0 frozen':<12} {'3 frozen':<12} {'6 frozen':<12} {'9 frozen':<12}")
    print("-" * 70)

    for config_name in configs:
        row = f"{config_name:<22}"
        for n_frozen in frozen_counts:
            rate = results[config_name][n_frozen]['success_rate']
            row += f"{rate:<12.0%}"
        print(row)

    print("\n" + "=" * 70)
    print("BUBBLE: MOVABLE VS IMMOVABLE")
    print("=" * 70)

    bubble_mov_avg = np.mean([results['Bubble-movable'][f]['success_rate'] for f in frozen_counts if f > 0])
    bubble_imm_avg = np.mean([results['Bubble-immovable'][f]['success_rate'] for f in frozen_counts if f > 0])

    print(f"""
Bubble with movable frozen:   {bubble_mov_avg:.0%} avg success
Bubble with immovable frozen: {bubble_imm_avg:.0%} avg success
Difference:                   {bubble_mov_avg - bubble_imm_avg:+.0%}
""")

    if bubble_mov_avg > bubble_imm_avg + 0.1:
        print("FINDING: Bubble performs BETTER with movable frozen cells.")
        print("Pushing obstacles out of the way helps Bubble sort.")
    elif bubble_imm_avg > bubble_mov_avg + 0.1:
        print("FINDING: Bubble performs BETTER with immovable frozen cells.")
    else:
        print("FINDING: Bubble shows similar performance with both types.")

    print("\n" + "=" * 70)
    print("SELECTION: MOVABLE VS IMMOVABLE")
    print("=" * 70)

    sel_mov_avg = np.mean([results['Selection-movable'][f]['success_rate'] for f in frozen_counts if f > 0])
    sel_imm_avg = np.mean([results['Selection-immovable'][f]['success_rate'] for f in frozen_counts if f > 0])

    print(f"""
Selection with movable frozen:   {sel_mov_avg:.0%} avg success
Selection with immovable frozen: {sel_imm_avg:.0%} avg success
Difference:                      {sel_mov_avg - sel_imm_avg:+.0%}
""")

    if sel_imm_avg > sel_mov_avg + 0.1:
        print("FINDING: Selection performs BETTER with immovable frozen cells.")
        print("Goal adjustment (navigation) is more effective than pushing.")
    elif sel_mov_avg > sel_imm_avg + 0.1:
        print("FINDING: Selection performs BETTER with movable frozen cells.")
    else:
        print("FINDING: Selection shows similar performance with both types.")

    print("\n" + "=" * 70)
    print("PAPER'S CLAIM VALIDATION")
    print("=" * 70)

    paper_claim = (bubble_mov_avg > bubble_imm_avg) and (sel_imm_avg >= sel_mov_avg - 0.05)

    if paper_claim:
        print("""
FINDING: Paper's claim is SUPPORTED.

The paper claims:
- Bubble performs best with MOVABLE obstacles (can push them)
- Selection handles IMMOVABLE obstacles better (goal adjustment)

Our results confirm this pattern. Different algorithms are optimized for
different types of perturbation.
""")
    else:
        print("""
FINDING: Paper's claim is NOT fully supported.

The pattern doesn't match the paper's claim. Either:
- Our implementation differs from theirs
- The effect is smaller than claimed
- Other factors are involved
""")


if __name__ == "__main__":
    main()
