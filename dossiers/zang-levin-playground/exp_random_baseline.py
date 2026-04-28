"""Random-swap baseline for K-computation.

Runs RandomSwapCell (no sorting logic) under the same conditions as Exp 10/14
to measure tau_blind empirically. Combined with the analytical formula
E[swaps] ~ 0.5 * n^2 * H_n for cross-validation.

Usage:
  uv run python exp_random_baseline.py --seed 42 --n-cells 30 --n-trials 100 \
    --timeout 30 --out paper/results/random_baseline.json
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
from modules.multithread.random_swap_cell import RandomSwapCell
from modules.multithread.StatusProbe import StatusProbe


def _is_sorted_ignoring_frozen(cells) -> bool:
    prev_val = -1
    for c in cells:
        if c.status == CellStatus.FREEZE:
            continue
        if c.value < prev_val:
            return False
        prev_val = c.value
    return True


def _kill_all(cells, groups) -> None:
    for c in cells:
        c.status = CellStatus.INACTIVE
    for g in groups:
        g.status = GroupStatus.MERGED


def _run_trial(
    *,
    n_cells: int,
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
        cell = RandomSwapCell(
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
        cells, cells, 0, left_boundary, right_boundary,
        GroupStatus.ACTIVE, thread_lock, 100000000, 100000000,
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
        swap_count = probe.swap_count
        _kill_all(cells, [cell_group])

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        "success": bool(success),
        "time": float(elapsed),
        "swaps": int(swap_count),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Random-swap baseline for K-computation")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--n-cells", type=int, default=30)
    p.add_argument("--n-trials", type=int, default=100)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--frozen-counts", type=str, default="0,3,6,9")
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    seed = int(args.seed)
    rng = random.Random(seed)
    n_cells = int(args.n_cells)
    n_trials = int(args.n_trials)
    timeout = float(args.timeout)
    frozen_counts = [int(x.strip()) for x in args.frozen_counts.split(",")]

    print("=" * 70)
    print("RANDOM-SWAP BASELINE FOR K-COMPUTATION")
    print("=" * 70)
    print(f"Setup: n_cells={n_cells}, n_trials={n_trials}, timeout={timeout}s, seed={seed}")
    print(f"Frozen counts: {frozen_counts}\n")

    results: dict[int, dict] = {}

    for n_frozen in frozen_counts:
        print(f"n_frozen = {n_frozen}...")

        setups: list[tuple[list[int], set[int]]] = []
        for _ in range(n_trials):
            values = list(range(n_cells))
            rng.shuffle(values)
            frozen_indices = set(rng.sample(range(n_cells), min(n_frozen, n_cells)))
            setups.append((values, frozen_indices))

        trial_results = [
            _run_trial(
                n_cells=n_cells,
                values=values,
                frozen_indices=frozen_indices,
                timeout=timeout,
            )
            for values, frozen_indices in setups
        ]

        success_rate = sum(1 for r in trial_results if r["success"]) / len(trial_results)
        avg_time = float(np.mean([r["time"] for r in trial_results]))
        avg_swaps = float(np.mean([r["swaps"] for r in trial_results]))

        print(
            f"  RandomSwap: success={success_rate:.0%}, "
            f"time={avg_time:.1f}s, swaps={avg_swaps:.0f}"
        )

        results[n_frozen] = {
            "success_rate": success_rate,
            "avg_time": avg_time,
            "avg_swaps": avg_swaps,
            "results": trial_results,
        }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Frozen':<10} {'Success':<12} {'Avg Swaps':<12} {'Avg Time':<12}")
    print("-" * 46)
    for n_frozen in frozen_counts:
        r = results[n_frozen]
        print(
            f"{n_frozen:<10} {r['success_rate']:<12.0%} "
            f"{r['avg_swaps']:<12.0f} {r['avg_time']:<12.1f}s"
        )

    out_obj = {
        "seed": seed,
        "n_cells": n_cells,
        "n_trials": n_trials,
        "timeout": timeout,
        "frozen_counts": frozen_counts,
        "results": {str(k): v for k, v in results.items()},
    }

    if args.out is not None:
        out_path: Path = args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_obj, indent=2))
        print(f"\nWrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
