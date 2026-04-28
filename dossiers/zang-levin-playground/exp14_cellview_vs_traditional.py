"""Experiment 14: Cell-view vs traditional implementations under immovable frozen indices.

Question:
Does the multithreaded "cell-view" implementation provide robustness advantages over
centralized baselines when both are constrained by the same immovable frozen indices?

Semantics:
Frozen indices are immovable obstacles: no swap may involve a frozen index.

Method:
For each trial, we generate a single initial permutation and a single frozen-index set,
then run:
- a centralized (traditional) implementation
- a cell-view (distributed) implementation
using the same initial state and obstacle set.

Usage (paper run):
  uv run python exp14_cellview_vs_traditional.py \
    --seed 42 --n-cells 30 --n-trials 12 --timeout 10 \
    --out paper/results/exp14_seed42_n12_t10.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import StatusProbe


class _SwapBlockedByFrozenMixin:
    """Blocks swaps that would move a frozen index."""

    def swap(self, target_position, skip_stats: bool = False):  # type: ignore[override]
        target_cell = self.cells[int(target_position[0])]
        if self.status == CellStatus.FREEZE or target_cell.status == CellStatus.FREEZE:
            if not self.tried_to_swap_with_frozen:
                self.status_probe.count_frozen_cell_attempt()
                self.tried_to_swap_with_frozen = True
            return
        super().swap(target_position, skip_stats=skip_stats)


class ImmovableBubbleCell(_SwapBlockedByFrozenMixin, BubbleSortCell):
    pass


class ImmovableSelectionCell(_SwapBlockedByFrozenMixin, SelectionSortCell):
    pass


class ImmovableInsertionCell(_SwapBlockedByFrozenMixin, InsertionSortCell):
    pass


def _monotonicity_error(arr: list[int], frozen_indices: set[int]) -> int:
    prev = -1
    errors = 0
    for i, val in enumerate(arr):
        if i in frozen_indices:
            continue
        if val < prev:
            errors += 1
        prev = val
    return errors


def _traditional_bubble_sort(arr: list[int], frozen_indices: set[int], max_iterations: int = 10000):
    arr = list(arr)
    n = len(arr)
    for iteration in range(max_iterations):
        swapped = False
        for i in range(n - 1):
            if i in frozen_indices or (i + 1) in frozen_indices:
                continue
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swapped = True
        if not swapped:
            return arr, iteration + 1
    return arr, max_iterations


def _traditional_selection_sort(
    arr: list[int],
    frozen_indices: set[int],
    max_iterations: int = 10000,
):
    arr = list(arr)
    n = len(arr)
    for i in range(n - 1):
        if i in frozen_indices:
            continue
        min_idx = i
        for j in range(i + 1, n):
            if j in frozen_indices:
                continue
            if arr[j] < arr[min_idx]:
                min_idx = j
        if min_idx != i and min_idx not in frozen_indices:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr, n


def _traditional_insertion_sort(
    arr: list[int],
    frozen_indices: set[int],
    max_iterations: int = 10000,
):
    arr = list(arr)
    n = len(arr)
    for i in range(1, n):
        if i in frozen_indices:
            continue
        key = arr[i]
        j = i - 1
        while j >= 0 and j not in frozen_indices and arr[j] > key:
            if (j + 1) not in frozen_indices:
                arr[j + 1] = arr[j]
            j -= 1
        if (j + 1) not in frozen_indices:
            arr[j + 1] = key
    return arr, n


def _run_traditional_trial(
    *,
    sort_fn,
    values: list[int],
    frozen_indices: set[int],
) -> dict:
    final_arr, _ = sort_fn(values, frozen_indices)
    err = _monotonicity_error(final_arr, frozen_indices)
    return {"success": err == 0, "error": int(err)}


def _run_cellview_trial(
    *,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    timeout: float,
) -> dict:
    n_cells = len(values)

    thread_lock = threading.Lock()
    probe = StatusProbe()

    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    for i in range(n_cells):
        cell = cell_class(
            i + 1,
            values[i],
            thread_lock,
            (i, 1),
            cells,
            left_boundary,
            right_boundary,
            probe,
            disable_visualization=True,
        )
        cells.append(cell)

    for idx in frozen_indices:
        cells[idx].set_cell_to_freeze()

    cell_group = CellGroup(
        cells,
        cells,
        0,
        left_boundary,
        right_boundary,
        GroupStatus.ACTIVE,
        thread_lock,
        100000000,
        100000000,
    )
    for cell in cells:
        cell.group = cell_group

    def is_done_under_lock() -> bool:
        prev_val = -1
        for c in cells:
            if c.status == CellStatus.FREEZE:
                continue
            if c.value < prev_val:
                return False
            prev_val = c.value
        return True

    with thread_lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start = time.time()
    done = False
    while time.time() - start < timeout:
        with thread_lock:
            done = is_done_under_lock()
        if done:
            break
        time.sleep(0.02)

    with thread_lock:
        final_arr = [c.value for c in cells]
        err = _monotonicity_error(final_arr, frozen_indices)
        for c in cells:
            c.status = CellStatus.INACTIVE
        cell_group.status = GroupStatus.MERGED

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {"success": err == 0, "error": int(err)}


def _parse_int_list(arg: str) -> list[int]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("expected a comma-separated list of integers")
    try:
        return [int(p) for p in parts]
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Exp14: cell-view vs traditional")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-cells", type=int, default=30)
    p.add_argument("--n-trials", type=int, default=12)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--frozen-counts", type=_parse_int_list, default=[0, 1, 3, 6, 9])
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    seed = int(args.seed)
    rng = random.Random(seed)

    n_cells = int(args.n_cells)
    n_trials = int(args.n_trials)
    timeout = float(args.timeout)
    frozen_counts = list(args.frozen_counts)

    algorithms = {
        "Bubble": {
            "traditional": _traditional_bubble_sort,
            "cellview": ImmovableBubbleCell,
        },
        "Selection": {
            "traditional": _traditional_selection_sort,
            "cellview": ImmovableSelectionCell,
        },
        "Insertion": {
            "traditional": _traditional_insertion_sort,
            "cellview": ImmovableInsertionCell,
        },
    }

    print("=" * 70)
    print("EXPERIMENT 14: CELL-VIEW VS TRADITIONAL")
    print("=" * 70)
    print(f"Setup: n_cells={n_cells}, n_trials={n_trials}, timeout={timeout}s, seed={seed}")
    print(f"Frozen counts: {frozen_counts}")
    print("Semantics: immovable frozen indices (no swaps involving frozen indices)\n")

    out_algos: dict[str, dict] = {}

    for algo_name, cfg in algorithms.items():
        print(f"{algo_name}:")
        out_algos[algo_name] = {"traditional": {}, "cellview": {}}

        for n_frozen in frozen_counts:
            trad = []
            cell = []

            for _ in range(n_trials):
                values = list(range(n_cells))
                rng.shuffle(values)
                frozen_indices = set(rng.sample(range(n_cells), min(n_frozen, n_cells)))

                trad.append(
                    _run_traditional_trial(
                        sort_fn=cfg["traditional"],
                        values=values,
                        frozen_indices=frozen_indices,
                    )
                )
                cell.append(
                    _run_cellview_trial(
                        cell_class=cfg["cellview"],
                        values=values,
                        frozen_indices=frozen_indices,
                        timeout=timeout,
                    )
                )

            trad_success = float(np.mean([1.0 if r["success"] else 0.0 for r in trad]))
            trad_error = float(np.mean([r["error"] for r in trad]))

            cell_success = float(np.mean([1.0 if r["success"] else 0.0 for r in cell]))
            cell_error = float(np.mean([r["error"] for r in cell]))

            print(
                f"  frozen={n_frozen:<2} "
                f"traditional={trad_success:.0%} (err={trad_error:.2f}), "
                f"cell-view={cell_success:.0%} (err={cell_error:.2f}), "
                f"diff={cell_success - trad_success:+.0%}"
            )

            out_algos[algo_name]["traditional"][str(n_frozen)] = {
                "success": trad_success,
                "error": trad_error,
            }
            out_algos[algo_name]["cellview"][str(n_frozen)] = {
                "success": cell_success,
                "error": cell_error,
            }

        print("")

    out_obj = {
        "seed": seed,
        "n_cells": n_cells,
        "n_trials": n_trials,
        "timeout": timeout,
        "frozen_counts": frozen_counts,
        "algorithms": out_algos,
    }

    if args.out is not None:
        out_path: Path = args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_obj, indent=2))
        print(f"Wrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
