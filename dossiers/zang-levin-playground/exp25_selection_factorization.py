"""Experiment 25: factorizing Selection into action range and frozen-target rerouting.

Question:
Which part of 1D Selection's robustness comes from long-range transpositions, and which
part comes from rerouting when the ideal target is blocked?

We compare four variants:
- long_range_rerouting: original SelectionSortCell
- long_range_stubborn: original StubbornSelectionCell
- adjacent_rerouting: adjacent-only step toward the same ideal target
- adjacent_stubborn: adjacent-only step without frozen-target rerouting

Semantics:
- movable: original-paper damaged-cell regime; frozen cells do not initiate swaps but can
  still be moved by active neighbors.
- immovable: no swap may involve a frozen index.
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

from modules.multithread.AdjacentSelectionCell import AdjacentSelectionCell
from modules.multithread.AdjacentStubbornSelectionCell import AdjacentStubbornSelectionCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import ExtendedStatusProbe
from modules.multithread.StubbornSelectionCell import StubbornSelectionCell


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


class ImmovableSelectionCell(_SwapBlockedByFrozenMixin, SelectionSortCell):
    pass


class ImmovableStubbornSelectionCell(_SwapBlockedByFrozenMixin, StubbornSelectionCell):
    pass


class ImmovableAdjacentSelectionCell(_SwapBlockedByFrozenMixin, AdjacentSelectionCell):
    pass


class ImmovableAdjacentStubbornSelectionCell(
    _SwapBlockedByFrozenMixin, AdjacentStubbornSelectionCell
):
    pass


def _parse_int_list(arg: str) -> list[int]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("expected a comma-separated list of integers")
    try:
        return [int(p) for p in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_semantics(arg: str) -> list[str]:
    parts = [p.strip().lower() for p in arg.split(",") if p.strip()]
    allowed = {"movable", "immovable"}
    invalid = [part for part in parts if part not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"unsupported semantics {invalid}; expected any of {sorted(allowed)}"
        )
    if not parts:
        raise argparse.ArgumentTypeError("expected at least one semantics value")
    return parts


def _monotonicity_error(cells, *, ignore_frozen: bool) -> int:
    prev_val = -1
    errors = 0
    for cell in cells:
        if ignore_frozen and cell.status == CellStatus.FREEZE:
            continue
        if cell.value < prev_val:
            errors += 1
        prev_val = cell.value
    return errors


def _is_sorted(cells, *, ignore_frozen: bool) -> bool:
    return _monotonicity_error(cells, ignore_frozen=ignore_frozen) == 0


def _kill_all(cells, groups) -> None:
    for cell in cells:
        cell.status = CellStatus.INACTIVE
    for group in groups:
        group.status = GroupStatus.MERGED


def _movement_metrics(probe: ExtendedStatusProbe, cell_type: str) -> dict[str, float]:
    distances = probe.movement_by_type.get(cell_type, [])
    total_move_distance = float(sum(distances))
    mean_move_distance = float(np.mean(distances)) if distances else 0.0
    mean_swap_span = (
        total_move_distance / (2.0 * probe.swap_count) if probe.swap_count > 0 else 0.0
    )
    return {
        "total_move_distance": total_move_distance,
        "mean_move_distance": mean_move_distance,
        "mean_swap_span": mean_swap_span,
    }


def _run_trial(
    *,
    n_cells: int,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    timeout: float,
    ignore_frozen_in_error: bool,
    trial_id: int,
) -> dict:
    thread_lock = threading.Lock()
    probe = ExtendedStatusProbe()

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
            success = _is_sorted(cells, ignore_frozen=ignore_frozen_in_error)
        if success:
            break
        time.sleep(0.02)

    elapsed = time.time() - start

    with thread_lock:
        final_error = _monotonicity_error(cells, ignore_frozen=ignore_frozen_in_error)
        metrics = _movement_metrics(probe, cells[0].cell_type)
        frozen_attempts = probe.frozen_swap_attempts
        compare_and_swap_count = probe.compare_and_swap_count
        _kill_all(cells, [cell_group])

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return {
        "trial_id": int(trial_id),
        "initial_values": list(values),
        "frozen_indices": sorted(frozen_indices),
        "success": bool(success),
        "time": float(elapsed),
        "error": int(final_error),
        "swaps": int(probe.swap_count),
        "compare_and_swap_count": int(compare_and_swap_count),
        "frozen_swap_attempts": int(frozen_attempts),
        "total_move_distance": round(metrics["total_move_distance"], 6),
        "mean_move_distance": round(metrics["mean_move_distance"], 6),
        "mean_swap_span": round(metrics["mean_swap_span"], 6),
    }


def _summarize(results: list[dict]) -> dict[str, float]:
    avg_swaps = float(np.mean([r["swaps"] for r in results]))
    avg_total_move_distance = float(np.mean([r["total_move_distance"] for r in results]))
    mean_swap_span_weighted = (
        avg_total_move_distance / (2.0 * avg_swaps) if avg_swaps > 0 else 0.0
    )
    return {
        "success_rate": float(np.mean([1.0 if r["success"] else 0.0 for r in results])),
        "avg_time": float(np.mean([r["time"] for r in results])),
        "avg_error": float(np.mean([r["error"] for r in results])),
        "avg_swaps": avg_swaps,
        "avg_compare_and_swap_count": float(
            np.mean([r["compare_and_swap_count"] for r in results])
        ),
        "avg_frozen_swap_attempts": float(np.mean([r["frozen_swap_attempts"] for r in results])),
        "avg_total_move_distance": avg_total_move_distance,
        "avg_mean_move_distance": float(np.mean([r["mean_move_distance"] for r in results])),
        "avg_mean_swap_span": float(np.mean([r["mean_swap_span"] for r in results])),
        "weighted_mean_swap_span": mean_swap_span_weighted,
    }


def _variant_classes_for_semantics(semantics: str) -> dict[str, type]:
    if semantics == "movable":
        return {
            "long_range_rerouting": SelectionSortCell,
            "long_range_stubborn": StubbornSelectionCell,
            "adjacent_rerouting": AdjacentSelectionCell,
            "adjacent_stubborn": AdjacentStubbornSelectionCell,
        }
    if semantics == "immovable":
        return {
            "long_range_rerouting": ImmovableSelectionCell,
            "long_range_stubborn": ImmovableStubbornSelectionCell,
            "adjacent_rerouting": ImmovableAdjacentSelectionCell,
            "adjacent_stubborn": ImmovableAdjacentStubbornSelectionCell,
        }
    raise ValueError(f"unknown semantics: {semantics}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exp25: Selection factorization")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-cells", type=int, default=30)
    parser.add_argument("--n-trials", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--semantics", type=_parse_semantics, default=["immovable", "movable"])
    parser.add_argument(
        "--immovable-frozen-counts",
        type=_parse_int_list,
        default=[0, 3, 6, 9],
    )
    parser.add_argument(
        "--movable-frozen-counts",
        type=_parse_int_list,
        default=[0, 1, 2, 3],
    )
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    seed = int(args.seed)
    rng = random.Random(seed)

    n_cells = int(args.n_cells)
    n_trials = int(args.n_trials)
    timeout = float(args.timeout)
    semantics_to_run = list(args.semantics)

    print("=" * 70)
    print("EXPERIMENT 25: SELECTION FACTORIZATION")
    print("=" * 70)
    print(f"Setup: n_cells={n_cells}, n_trials={n_trials}, timeout={timeout}s, seed={seed}")
    print(f"Semantics: {semantics_to_run}\n")

    results_by_semantics: dict[str, dict[str, dict[int, dict]]] = {}

    for semantics in semantics_to_run:
        frozen_counts = (
            list(args.immovable_frozen_counts)
            if semantics == "immovable"
            else list(args.movable_frozen_counts)
        )
        ignore_frozen_in_error = semantics == "immovable"
        variant_classes = _variant_classes_for_semantics(semantics)
        results_by_semantics[semantics] = {}

        print("-" * 70)
        print(f"SEMANTICS: {semantics}")
        print(f"Frozen counts: {frozen_counts}")
        print("-" * 70)

        paired_setups: dict[int, list[tuple[list[int], set[int]]]] = {}
        for n_frozen in frozen_counts:
            setups: list[tuple[list[int], set[int]]] = []
            for _ in range(n_trials):
                values = list(range(n_cells))
                rng.shuffle(values)
                frozen_indices = set(rng.sample(range(n_cells), min(n_frozen, n_cells)))
                setups.append((values, frozen_indices))
            paired_setups[n_frozen] = setups

        for variant_name, cell_class in variant_classes.items():
            results_by_semantics[semantics][variant_name] = {}
            print(f"{variant_name}:")
            for n_frozen in frozen_counts:
                setups = paired_setups[n_frozen]
                trial_results = [
                    _run_trial(
                        n_cells=n_cells,
                        cell_class=cell_class,
                        values=values,
                        frozen_indices=frozen_indices,
                        timeout=timeout,
                        ignore_frozen_in_error=ignore_frozen_in_error,
                        trial_id=trial_id,
                    )
                    for trial_id, (values, frozen_indices) in enumerate(setups)
                ]
                summary = _summarize(trial_results)
                print(
                    f"  frozen={n_frozen:<2} success={summary['success_rate']:.0%} "
                    f"err={summary['avg_error']:.2f} swaps={summary['avg_swaps']:.1f} "
                    f"move_span={summary['weighted_mean_swap_span']:.2f}"
                )
                results_by_semantics[semantics][variant_name][n_frozen] = {
                    **summary,
                    "results": trial_results,
                }
            print("")

    out_obj = {
        "seed": seed,
        "n_cells": n_cells,
        "n_trials": n_trials,
        "timeout": timeout,
        "semantics": semantics_to_run,
        "frozen_counts": {
            "immovable": list(args.immovable_frozen_counts),
            "movable": list(args.movable_frozen_counts),
        },
        "variants": [
            "long_range_rerouting",
            "long_range_stubborn",
            "adjacent_rerouting",
            "adjacent_stubborn",
        ],
        "results": {
            semantics: {
                variant: {str(frozen): payload for frozen, payload in frozen_map.items()}
                for variant, frozen_map in variant_map.items()
            }
            for semantics, variant_map in results_by_semantics.items()
        },
    }

    if args.out is not None:
        out_path: Path = args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_obj, indent=2))
        print(f"Wrote: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
