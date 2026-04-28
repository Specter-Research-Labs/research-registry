"""Experiment 10: Goal-adjustment ablation under immovable frozen indices.

Question:
SelectionSortCell adjusts its ideal_position when blocked by a frozen index. Does that
heuristic actually matter, or would a "stubborn" variant (no goal adjustment when
blocked by frozen indices) perform similarly?

Semantics:
We treat frozen indices as immovable obstacles: no swap may involve a frozen index.
(We implement this by blocking swaps whenever either endpoint is a frozen cell.)

Usage (paper run):
  uv run python exp10_ablation_goal_adjustment.py \
    --seed 42 --n-cells 30 --n-trials 30 --timeout 10 \
    --out paper/results/exp10_seed42_n30_t10.json
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

from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import StatusProbe
from modules.multithread.StubbornSelectionCell import StubbornSelectionCell


class _SwapBlockedByFrozenMixin:
    """Blocks swaps that would move a frozen index.

    Invariant: if a cell is frozen, it cannot move *and* no other cell may swap with it.
    """

    def swap(self, target_position, skip_stats: bool = False):  # type: ignore[override]
        target_cell = self.cells[int(target_position[0])]
        if self.status == CellStatus.FREEZE or target_cell.status == CellStatus.FREEZE:
            if not self.tried_to_swap_with_frozen:
                self.status_probe.count_frozen_cell_attempt()
                self.tried_to_swap_with_frozen = True
            return
        super().swap(target_position, skip_stats=skip_stats)


class ImmovableSelectionCell(_SwapBlockedByFrozenMixin, SelectionSortCell):
    pass


class ImmovableStubbornSelectionCell(_SwapBlockedByFrozenMixin, StubbornSelectionCell):
    pass


def _monotonicity_error_ignoring_frozen(cells) -> int:
    prev_val = -1
    errors = 0
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            errors += 1
        prev_val = c.value
    return errors


def _is_sorted_ignoring_frozen(cells) -> bool:
    return _monotonicity_error_ignoring_frozen(cells) == 0


def _kill_all(cells, groups) -> None:
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def _run_trial(
    *,
    n_cells: int,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    timeout: float,
) -> dict:
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

    with thread_lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start = time.time()
    success = False
    while time.time() - start < timeout:
        with thread_lock:
            success = _is_sorted_ignoring_frozen(cells)
        if success:
            break
        time.sleep(0.02)

    elapsed = time.time() - start

    with thread_lock:
        final_error = _monotonicity_error_ignoring_frozen(cells)
        swap_count = probe.swap_count
        _kill_all(cells, [cell_group])

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        "success": bool(success),
        "time": float(elapsed),
        "error": int(final_error),
        "swaps": int(swap_count),
    }


def _parse_int_list(arg: str) -> list[int]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("expected a comma-separated list of integers")
    try:
        return [int(p) for p in parts]
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Exp10: goal-adjustment ablation")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-cells", type=int, default=30)
    p.add_argument("--n-trials", type=int, default=30)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--frozen-counts", type=_parse_int_list, default=[0, 3, 6, 9])
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

    print("=" * 70)
    print("EXPERIMENT 10: ABLATION STUDY - GOAL ADJUSTMENT")
    print("=" * 70)
    print(f"Setup: n_cells={n_cells}, n_trials={n_trials}, timeout={timeout}s, seed={seed}")
    print(f"Frozen counts: {frozen_counts}")
    print("Semantics: immovable frozen indices (no swaps involving frozen indices)\n")

    results_adaptive: dict[int, dict] = {}
    results_stubborn: dict[int, dict] = {}

    for n_frozen in frozen_counts:
        print(f"n_frozen = {n_frozen}...")

        setups: list[tuple[list[int], set[int]]] = []
        for _ in range(n_trials):
            values = list(range(n_cells))
            rng.shuffle(values)
            frozen_indices = set(rng.sample(range(n_cells), min(n_frozen, n_cells)))
            setups.append((values, frozen_indices))

        adaptive_results = [
            _run_trial(
                n_cells=n_cells,
                cell_class=ImmovableSelectionCell,
                values=values,
                frozen_indices=frozen_indices,
                timeout=timeout,
            )
            for values, frozen_indices in setups
        ]
        stubborn_results = [
            _run_trial(
                n_cells=n_cells,
                cell_class=ImmovableStubbornSelectionCell,
                values=values,
                frozen_indices=frozen_indices,
                timeout=timeout,
            )
            for values, frozen_indices in setups
        ]

        def summarize(rs: list[dict]) -> tuple[float, float, float]:
            success_rate = sum(1 for r in rs if r["success"]) / len(rs)
            avg_time = float(np.mean([r["time"] for r in rs]))
            avg_swaps = float(np.mean([r["swaps"] for r in rs]))
            return success_rate, avg_time, avg_swaps

        a_success, a_time, a_swaps = summarize(adaptive_results)
        s_success, s_time, s_swaps = summarize(stubborn_results)

        print(
            "  Adaptive Selection: "
            f"success={a_success:.0%}, time={a_time:.1f}s, swaps={a_swaps:.0f}"
        )
        print(
            "  Stubborn Selection: "
            f"success={s_success:.0%}, time={s_time:.1f}s, swaps={s_swaps:.0f}"
        )

        results_adaptive[n_frozen] = {
            "success_rate": a_success,
            "avg_time": a_time,
            "avg_swaps": a_swaps,
            "results": adaptive_results,
        }
        results_stubborn[n_frozen] = {
            "success_rate": s_success,
            "avg_time": s_time,
            "avg_swaps": s_swaps,
            "results": stubborn_results,
        }

    print("\n" + "=" * 70)
    print("RESULTS COMPARISON")
    print("=" * 70)
    print(f"{'Frozen':<10} {'Adaptive':<12} {'Stubborn':<12} {'Diff':<8}")
    print("-" * 46)
    for n_frozen in frozen_counts:
        a = results_adaptive[n_frozen]["success_rate"]
        s = results_stubborn[n_frozen]["success_rate"]
        print(f"{n_frozen:<10} {a:<12.0%} {s:<12.0%} {a - s:+.0%}")

    out_obj = {
        "seed": seed,
        "n_cells": n_cells,
        "n_trials": n_trials,
        "timeout": timeout,
        "frozen_counts": frozen_counts,
        "adaptive": {str(k): v for k, v in results_adaptive.items()},
        "stubborn": {str(k): v for k, v in results_stubborn.items()},
    }

    if args.out is not None:
        out_path: Path = args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_obj, indent=2))
        print(f"\nWrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
