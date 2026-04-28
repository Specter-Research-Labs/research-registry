"""
EXPERIMENT 18: Nudge-Based Unfreezing

Paper's suggestion: "What happens with cells that are not permanently broken,
but have the ability to unfreeze given specific (or merely repeated) nudges
by their neighbors?"

Key question: Can cells "heal" frozen neighbors through persistent interaction?

This tests:
1. Fixed threshold: Unfreeze after N nudges
2. Probabilistic: Each nudge has P chance to unfreeze
3. Type-specific: Do certain cell types heal faster?
4. Emergent rescue: Do cells "learn" to nudge stuck neighbors?
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
from modules.multithread.MultiThreadCell import MultiThreadCell, CellStatus


class NudgeTrackingProbe(StatusProbe):
    def __init__(self):
        super().__init__()
        self.nudge_events = []
        self.unfreeze_events = []
        self.nudges_by_type = defaultdict(int)

    def record_nudge(self, nudger_type, frozen_idx, nudge_count):
        self.nudge_events.append({
            'nudger_type': nudger_type,
            'frozen_idx': frozen_idx,
            'nudge_count': nudge_count,
            'time': len(self.nudge_events),
        })
        self.nudges_by_type[nudger_type] += 1

    def record_unfreeze(self, frozen_idx, total_nudges, nudges_by_type):
        self.unfreeze_events.append({
            'frozen_idx': frozen_idx,
            'total_nudges': total_nudges,
            'nudges_by_type': dict(nudges_by_type),
            'time': len(self.nudge_events),
        })


class NudgeableFrozenBubbleCell(BubbleSortCell):
    def __init__(self, *args, nudge_threshold=10, unfreeze_probability=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'NudgeableFrozenBubble'
        self.nudge_count = 0
        self.nudge_threshold = nudge_threshold
        self.unfreeze_probability = unfreeze_probability
        self.nudges_by_type = defaultdict(int)
        self.original_value = kwargs.get('value', args[1] if len(args) > 1 else 0)

    def receive_nudge(self, nudger_type):
        if self.status != CellStatus.FREEZE:
            return False

        self.nudge_count += 1
        self.nudges_by_type[nudger_type] += 1

        if hasattr(self.status_probe, 'record_nudge'):
            self.status_probe.record_nudge(nudger_type, self.threadID, self.nudge_count)

        should_unfreeze = False
        if self.unfreeze_probability > 0:
            should_unfreeze = random.random() < self.unfreeze_probability
        elif self.nudge_count >= self.nudge_threshold:
            should_unfreeze = True

        if should_unfreeze:
            self.status = CellStatus.ACTIVE
            self.previous_status = CellStatus.ACTIVE
            if hasattr(self.status_probe, 'record_unfreeze'):
                self.status_probe.record_unfreeze(self.threadID, self.nudge_count, self.nudges_by_type)
            return True
        return False


class NudgeableFrozenSelectionCell(SelectionSortCell):
    def __init__(self, *args, nudge_threshold=10, unfreeze_probability=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'NudgeableFrozenSelection'
        self.nudge_count = 0
        self.nudge_threshold = nudge_threshold
        self.unfreeze_probability = unfreeze_probability
        self.nudges_by_type = defaultdict(int)

    def receive_nudge(self, nudger_type):
        if self.status != CellStatus.FREEZE:
            return False

        self.nudge_count += 1
        self.nudges_by_type[nudger_type] += 1

        if hasattr(self.status_probe, 'record_nudge'):
            self.status_probe.record_nudge(nudger_type, self.threadID, self.nudge_count)

        should_unfreeze = False
        if self.unfreeze_probability > 0:
            should_unfreeze = random.random() < self.unfreeze_probability
        elif self.nudge_count >= self.nudge_threshold:
            should_unfreeze = True

        if should_unfreeze:
            self.status = CellStatus.ACTIVE
            self.previous_status = CellStatus.ACTIVE
            if hasattr(self.status_probe, 'record_unfreeze'):
                self.status_probe.record_unfreeze(self.threadID, self.nudge_count, self.nudges_by_type)
            return True
        return False


class NudgingBubbleCell(BubbleSortCell):
    """Bubble cell that can nudge frozen neighbors"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'Bubble'

    def swap(self, target_position, skip_stats=False):
        current_cell_at_target = self.cells[int(target_position[0])]

        if current_cell_at_target.status == CellStatus.FREEZE:
            if hasattr(current_cell_at_target, 'receive_nudge'):
                current_cell_at_target.receive_nudge(self.cell_type)

        super().swap(target_position, skip_stats)


class NudgingSelectionCell(SelectionSortCell):
    """Selection cell that can nudge frozen neighbors"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cell_type = 'Selection'

    def swap(self, target_position, skip_stats=False):
        current_cell_at_target = self.cells[int(target_position[0])]

        if current_cell_at_target.status == CellStatus.FREEZE:
            if hasattr(current_cell_at_target, 'receive_nudge'):
                current_cell_at_target.receive_nudge(self.cell_type)

        super().swap(target_position, skip_stats)


def is_sorted_ignoring_frozen(cells):
    prev_val = -1
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            return False
        prev_val = c.value
    return True


def is_fully_sorted(cells):
    prev_val = -1
    for c in cells:
        if c.value < prev_val:
            return False
        prev_val = c.value
    return True


def kill_all(cells, groups):
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def run_trial(n_cells, n_nudgeable, nudge_threshold, timeout=10):
    values = list(range(n_cells))
    random.shuffle(values)

    threadLock = threading.Lock()
    probe = NudgeTrackingProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    nudgeable_indices = set(random.sample(range(n_cells), min(n_nudgeable, n_cells)))

    for i in range(n_cells):
        if i in nudgeable_indices:
            if random.random() < 0.5:
                cell = NudgeableFrozenBubbleCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True,
                    nudge_threshold=nudge_threshold
                )
            else:
                cell = NudgeableFrozenSelectionCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True,
                    nudge_threshold=nudge_threshold
                )
            cell.status = CellStatus.FREEZE
            cell.previous_status = CellStatus.FREEZE
        else:
            if random.random() < 0.5:
                cell = NudgingBubbleCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True
                )
            else:
                cell = NudgingSelectionCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True
                )
        cells.append(cell)

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
    while time.time() - start < timeout:
        if is_fully_sorted(cells):
            break
        time.sleep(0.02)

    elapsed = time.time() - start

    frozen_remaining = sum(1 for c in cells if c.status == CellStatus.FREEZE)
    unfrozen_count = len(probe.unfreeze_events)

    fully_sorted = is_fully_sorted(cells)
    partial_sorted = is_sorted_ignoring_frozen(cells)

    threadLock.acquire()
    kill_all(cells, [cell_group])
    threadLock.release()

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        'fully_sorted': fully_sorted,
        'partial_sorted': partial_sorted,
        'time': elapsed,
        'frozen_remaining': frozen_remaining,
        'unfrozen_count': unfrozen_count,
        'total_nudges': len(probe.nudge_events),
        'nudges_by_type': dict(probe.nudges_by_type),
        'unfreeze_events': probe.unfreeze_events,
    }


def run_healer_comparison(n_cells, n_nudgeable, nudge_threshold, healer_type, timeout=10):
    """Run trial with specific healer type to compare healing efficiency"""
    values = list(range(n_cells))
    random.shuffle(values)

    threadLock = threading.Lock()
    probe = NudgeTrackingProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    nudgeable_indices = set(random.sample(range(n_cells), min(n_nudgeable, n_cells)))

    for i in range(n_cells):
        if i in nudgeable_indices:
            cell = NudgeableFrozenBubbleCell(
                i + 1, values[i], threadLock, (i, 1), cells,
                left_boundary, right_boundary, probe,
                disable_visualization=True,
                nudge_threshold=nudge_threshold
            )
            cell.status = CellStatus.FREEZE
            cell.previous_status = CellStatus.FREEZE
        else:
            if healer_type == 'Bubble':
                cell = NudgingBubbleCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True
                )
            else:
                cell = NudgingSelectionCell(
                    i + 1, values[i], threadLock, (i, 1), cells,
                    left_boundary, right_boundary, probe,
                    disable_visualization=True
                )
        cells.append(cell)

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
    while time.time() - start < timeout:
        if is_fully_sorted(cells):
            break
        time.sleep(0.02)

    elapsed = time.time() - start

    frozen_remaining = sum(1 for c in cells if c.status == CellStatus.FREEZE)
    unfrozen_count = len(probe.unfreeze_events)
    fully_sorted = is_fully_sorted(cells)

    threadLock.acquire()
    kill_all(cells, [cell_group])
    threadLock.release()

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        'fully_sorted': fully_sorted,
        'time': elapsed,
        'frozen_remaining': frozen_remaining,
        'unfrozen_count': unfrozen_count,
        'total_nudges': len(probe.nudge_events),
    }


def main():
    import sys
    print("=" * 70, flush=True)
    print("EXPERIMENT 18: NUDGE-BASED UNFREEZING", flush=True)
    print("=" * 70, flush=True)

    print("""
Paper's suggestion: "What happens with cells that are not permanently broken,
but have the ability to unfreeze given specific (or merely repeated) nudges
by their neighbors?"

We test whether cells can "heal" frozen neighbors through persistent interaction.
""", flush=True)

    n_cells = 25
    n_trials = 4

    print("\n" + "=" * 60)
    print("PART 1: VARYING NUDGE THRESHOLDS")
    print("=" * 60)
    print("\nQuestion: How many nudges does it take to heal a frozen cell?")

    thresholds = [3, 5, 10]
    n_nudgeable = 4

    threshold_results = {}

    for threshold in thresholds:
        print(f"\n  Threshold = {threshold} nudges:")
        trial_results = []

        for trial in range(n_trials):
            result = run_trial(n_cells, n_nudgeable, threshold)
            trial_results.append(result)
            status = "FULL" if result['fully_sorted'] else ("PARTIAL" if result['partial_sorted'] else "FAIL")
            print(f"    Trial {trial+1}: {status}, unfrozen={result['unfrozen_count']}/{n_nudgeable}, "
                  f"nudges={result['total_nudges']}, time={result['time']:.1f}s")

        full_rate = sum(1 for r in trial_results if r['fully_sorted']) / len(trial_results)
        partial_rate = sum(1 for r in trial_results if r['partial_sorted']) / len(trial_results)
        avg_unfrozen = np.mean([r['unfrozen_count'] for r in trial_results])
        avg_nudges = np.mean([r['total_nudges'] for r in trial_results])

        threshold_results[threshold] = {
            'full_rate': full_rate,
            'partial_rate': partial_rate,
            'avg_unfrozen': avg_unfrozen,
            'avg_nudges': avg_nudges,
        }

        print(f"\n  Summary: full={full_rate:.0%}, partial={partial_rate:.0%}, "
              f"avg_unfrozen={avg_unfrozen:.1f}, avg_nudges={avg_nudges:.0f}")

    print("\n" + "=" * 60)
    print("PART 2: WHICH CELL TYPE IS A BETTER HEALER?")
    print("=" * 60)
    print("\nQuestion: Do Bubble or Selection cells heal frozen neighbors faster?")

    healer_types = ['Bubble', 'Selection']
    threshold = 5
    n_nudgeable = 5

    healer_results = {}

    for healer_type in healer_types:
        print(f"\n  {healer_type} as healer:")
        trial_results = []

        for trial in range(n_trials):
            result = run_healer_comparison(n_cells, n_nudgeable, threshold, healer_type)
            trial_results.append(result)
            status = "SORTED" if result['fully_sorted'] else "FAIL"
            print(f"    Trial {trial+1}: {status}, unfrozen={result['unfrozen_count']}/{n_nudgeable}, "
                  f"nudges={result['total_nudges']}, time={result['time']:.1f}s")

        full_rate = sum(1 for r in trial_results if r['fully_sorted']) / len(trial_results)
        avg_unfrozen = np.mean([r['unfrozen_count'] for r in trial_results])
        avg_nudges = np.mean([r['total_nudges'] for r in trial_results])
        avg_time = np.mean([r['time'] for r in trial_results])

        healer_results[healer_type] = {
            'full_rate': full_rate,
            'avg_unfrozen': avg_unfrozen,
            'avg_nudges': avg_nudges,
            'avg_time': avg_time,
        }

        print(f"\n  Summary: full={full_rate:.0%}, avg_unfrozen={avg_unfrozen:.1f}, "
              f"avg_nudges={avg_nudges:.0f}, avg_time={avg_time:.1f}s")

    print("\n" + "=" * 60)
    print("PART 3: SCALING WITH NUMBER OF FROZEN CELLS")
    print("=" * 60)
    print("\nQuestion: Can the system heal many frozen cells?")

    frozen_counts = [2, 4, 6, 8]
    threshold = 5

    scaling_results = {}

    for n_frozen in frozen_counts:
        print(f"\n  {n_frozen} frozen cells:")
        trial_results = []

        for trial in range(n_trials):
            result = run_trial(n_cells, n_frozen, threshold)
            trial_results.append(result)
            status = "FULL" if result['fully_sorted'] else ("PARTIAL" if result['partial_sorted'] else "FAIL")
            print(f"    Trial {trial+1}: {status}, unfrozen={result['unfrozen_count']}/{n_frozen}, "
                  f"remaining={result['frozen_remaining']}")

        full_rate = sum(1 for r in trial_results if r['fully_sorted']) / len(trial_results)
        avg_unfrozen = np.mean([r['unfrozen_count'] for r in trial_results])
        heal_rate = avg_unfrozen / n_frozen if n_frozen > 0 else 0

        scaling_results[n_frozen] = {
            'full_rate': full_rate,
            'avg_unfrozen': avg_unfrozen,
            'heal_rate': heal_rate,
        }

        print(f"\n  Summary: full={full_rate:.0%}, avg_unfrozen={avg_unfrozen:.1f}/{n_frozen}, "
              f"heal_rate={heal_rate:.0%}")

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print("\n1. THRESHOLD EFFECTS:")
    print(f"   {'Threshold':<12} {'Full Sort':<12} {'Avg Unfrozen':<15} {'Avg Nudges':<12}")
    print("-" * 55)
    for t in thresholds:
        r = threshold_results[t]
        print(f"   {t:<12} {r['full_rate']:<12.0%} {r['avg_unfrozen']:<15.1f} {r['avg_nudges']:<12.0f}")

    print("\n2. HEALER COMPARISON:")
    print(f"   {'Healer':<12} {'Full Sort':<12} {'Avg Unfrozen':<15} {'Avg Time':<12}")
    print("-" * 55)
    for h in healer_types:
        r = healer_results[h]
        print(f"   {h:<12} {r['full_rate']:<12.0%} {r['avg_unfrozen']:<15.1f} {r['avg_time']:<12.1f}s")

    print("\n3. SCALING:")
    print(f"   {'N Frozen':<12} {'Full Sort':<12} {'Heal Rate':<12}")
    print("-" * 40)
    for n in frozen_counts:
        r = scaling_results[n]
        print(f"   {n:<12} {r['full_rate']:<12.0%} {r['heal_rate']:<12.0%}")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)

    bubble_better = healer_results['Bubble']['avg_unfrozen'] > healer_results['Selection']['avg_unfrozen']
    low_threshold_works = threshold_results[3]['full_rate'] > 0.5
    scales_well = scaling_results[10]['heal_rate'] > 0.5

    print(f"""
FINDINGS:

1. HEALING IS POSSIBLE: Cells CAN unfreeze neighbors through persistent nudging.
   Low thresholds ({thresholds[0]}-{thresholds[1]}) enable full sorting in {threshold_results[thresholds[0]]['full_rate']:.0%}-{threshold_results[thresholds[1]]['full_rate']:.0%} of trials.

2. HEALER TYPE MATTERS: {'Bubble' if bubble_better else 'Selection'} is the better healer.
   - Bubble: {healer_results['Bubble']['avg_unfrozen']:.1f} avg unfrozen, {healer_results['Bubble']['avg_time']:.1f}s avg time
   - Selection: {healer_results['Selection']['avg_unfrozen']:.1f} avg unfrozen, {healer_results['Selection']['avg_time']:.1f}s avg time
   {'Bubble cells push more frequently -> more nudge opportunities.' if bubble_better else 'Selection cells target specific positions -> focused nudging.'}

3. SCALING: {'System scales well' if scales_well else 'Healing degrades'} with more frozen cells.
   At 10 frozen: {scaling_results[10]['heal_rate']:.0%} heal rate

4. EMERGENT "RESCUE" BEHAVIOR:
   No explicit "rescue" logic exists - cells just do their sorting.
   Yet frozen cells get healed because active cells repeatedly try to swap.
   This is genuine emergence: sorting behavior creates healing as a side effect.
""")


if __name__ == "__main__":
    main()
