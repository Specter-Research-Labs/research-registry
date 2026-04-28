"""Experiment 26: substrate-matched cell-view baselines for 1D sorting cells.

Question:
When operator semantics are held fixed, does the multithreaded cell-view substrate behave
differently from a single-thread scheduler that steps the same cell policies? For the original
Bubble / Insertion / Selection trio, how do both compare to textbook centralized baselines?

Method:
For each paired trial (same initial permutation and same frozen-index set), run:
- threaded_cellview: the original multithreaded implementation
- sequential_cellview: the same cell objects, stepped by one single-thread scheduler
- textbook_centralized: only for Bubble / Insertion / Selection, reported as a reference surface

Semantics:
Default is immovable frozen indices, because this is the regime where Exp25 and Exp14 are sharpest.

Interpretation:
Only threaded_cellview vs sequential_cellview is a substrate-matched comparison. The textbook
implementations do not share the same scheduler or cell policy and are included as a reference
surface rather than part of the matched substrate claim.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from modules.multithread.AdjacentSelectionCell import AdjacentSelectionCell
from modules.multithread.AdjacentStubbornSelectionCell import AdjacentStubbornSelectionCell
from modules.multithread.BubbleSortCell import BubbleSortCell
from modules.multithread.CellGroup import CellGroup, GroupStatus
from modules.multithread.InsertionSortCell import InsertionSortCell
from modules.multithread.MultiThreadCell import CellStatus
from modules.multithread.SelectionSortCell import SelectionSortCell
from modules.multithread.StatusProbe import ExtendedStatusProbe
from modules.multithread.StubbornSelectionCell import StubbornSelectionCell


class BudgetedStatusProbe(ExtendedStatusProbe):
    """Stops recording new move attempts after a matched compare budget is exhausted."""

    def __init__(self, max_compare_and_swap: int):
        super().__init__()
        self.max_compare_and_swap = max_compare_and_swap
        self.stop_requested = False

    def record_compare_and_swap(self):
        if self.stop_requested:
            return
        super().record_compare_and_swap()
        if self.compare_and_swap_count >= self.max_compare_and_swap:
            self.stop_requested = True


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


class _BudgetAwareMoveMixin:
    """Stops cell activity once the shared probe budget is exhausted."""

    def move(self):  # type: ignore[override]
        if getattr(self.status_probe, "stop_requested", False):
            return
        super().move()


class ImmovableBubbleCell(_BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, BubbleSortCell):
    pass


class ImmovableInsertionCell(_BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, InsertionSortCell):
    pass


class ImmovableSelectionCell(_BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, SelectionSortCell):
    pass


class ImmovableStubbornSelectionCell(
    _BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, StubbornSelectionCell
):
    pass


class ImmovableAdjacentSelectionCell(
    _BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, AdjacentSelectionCell
):
    pass


class ImmovableAdjacentStubbornSelectionCell(
    _BudgetAwareMoveMixin, _SwapBlockedByFrozenMixin, AdjacentStubbornSelectionCell
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


def _parse_semantics(arg: str) -> str:
    semantics = arg.strip().lower()
    if semantics not in {"immovable", "movable"}:
        raise argparse.ArgumentTypeError("semantics must be 'immovable' or 'movable'")
    return semantics


def _parse_str_list(arg: str) -> list[str]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("expected a comma-separated list of names")
    return parts


def _monotonicity_error(cells_or_values, *, frozen_indices: set[int], is_cells: bool) -> int:
    prev = -1
    errors = 0
    for i, item in enumerate(cells_or_values):
        if i in frozen_indices:
            continue
        value = item.value if is_cells else item
        if value < prev:
            errors += 1
        prev = value
    return errors


def _is_sorted_cells(cells, *, frozen_indices: set[int]) -> bool:
    return _monotonicity_error(cells, frozen_indices=frozen_indices, is_cells=True) == 0


def _movement_metrics(probe: ExtendedStatusProbe, cell_type: str) -> dict[str, float]:
    distances = probe.movement_by_type.get(cell_type, [])
    total_move_distance = float(sum(distances))
    mean_move_distance = float(np.mean(distances)) if distances else 0.0
    weighted_mean_swap_span = (
        total_move_distance / (2.0 * probe.swap_count) if probe.swap_count > 0 else 0.0
    )
    return {
        "total_move_distance": total_move_distance,
        "mean_move_distance": mean_move_distance,
        "weighted_mean_swap_span": weighted_mean_swap_span,
    }


def _kill_all(cells: list[Any], groups: list[Any]) -> None:
    for cell in cells:
        cell.status = CellStatus.INACTIVE
    for group in groups:
        group.status = GroupStatus.MERGED


def _build_cells(
    *,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    probe: BudgetedStatusProbe,
) -> tuple[list[Any], CellGroup]:
    thread_lock = threading.Lock()
    n_cells = len(values)
    left_boundary = (0, 1)
    right_boundary = (n_cells - 1, 1)
    cells = []

    for i, value in enumerate(values):
        cell = cell_class(
            i + 1,
            value,
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

    return cells, cell_group


def _run_threaded_cellview_trial(
    *,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    timeout: float,
    max_compare_and_swap: int,
    trial_seed: int,
) -> dict[str, Any]:
    random.seed(trial_seed)
    probe = BudgetedStatusProbe(max_compare_and_swap)
    cells, cell_group = _build_cells(
        cell_class=cell_class,
        values=values,
        frozen_indices=frozen_indices,
        probe=probe,
    )
    thread_lock = cells[0].lock

    with thread_lock:
        for cell in cells:
            cell.start()
        cell_group.start()

    start = time.time()
    success = False
    termination = "wall_timeout"
    while time.time() - start < timeout:
        with thread_lock:
            success = _is_sorted_cells(cells, frozen_indices=frozen_indices)
            budget_exhausted = probe.stop_requested
        if success:
            termination = "success"
            break
        if budget_exhausted:
            termination = "compare_budget"
            break
        time.sleep(0.0005)

    elapsed = time.time() - start

    with thread_lock:
        final_error = _monotonicity_error(cells, frozen_indices=frozen_indices, is_cells=True)
        metrics = _movement_metrics(probe, cells[0].cell_type)
        result = {
            "success": bool(success),
            "error": int(final_error),
            "time": float(elapsed),
            "swaps": int(probe.swap_count),
            "compare_and_swap_count": int(probe.compare_and_swap_count),
            "frozen_swap_attempts": int(probe.frozen_swap_attempts),
            "total_move_distance": round(metrics["total_move_distance"], 6),
            "mean_move_distance": round(metrics["mean_move_distance"], 6),
            "weighted_mean_swap_span": round(metrics["weighted_mean_swap_span"], 6),
            "termination": termination,
        }
        _kill_all(cells, [cell_group])

    for cell in cells:
        cell.join(timeout=1)
    cell_group.join(timeout=1)

    return result


def _run_sequential_cellview_trial(
    *,
    cell_class,
    values: list[int],
    frozen_indices: set[int],
    timeout: float,
    max_compare_and_swap: int,
    trial_seed: int,
) -> dict[str, Any]:
    random.seed(trial_seed)
    schedule_rng = random.Random(trial_seed ^ 0x5F3759DF)
    probe = BudgetedStatusProbe(max_compare_and_swap)
    cells, cell_group = _build_cells(
        cell_class=cell_class,
        values=values,
        frozen_indices=frozen_indices,
        probe=probe,
    )

    start = time.time()
    success = False
    scheduler_sweeps = 0
    termination = "wall_timeout"
    while time.time() - start < timeout:
        if _is_sorted_cells(cells, frozen_indices=frozen_indices):
            success = True
            termination = "success"
            break
        if probe.stop_requested:
            termination = "compare_budget"
            break
        schedule = list(cells)
        schedule_rng.shuffle(schedule)
        for cell in schedule:
            cell.move()
        scheduler_sweeps += 1

    elapsed = time.time() - start
    final_error = _monotonicity_error(cells, frozen_indices=frozen_indices, is_cells=True)
    metrics = _movement_metrics(probe, cells[0].cell_type)

    return {
        "success": bool(success),
        "error": int(final_error),
        "time": float(elapsed),
        "swaps": int(probe.swap_count),
        "compare_and_swap_count": int(probe.compare_and_swap_count),
        "frozen_swap_attempts": int(probe.frozen_swap_attempts),
        "total_move_distance": round(metrics["total_move_distance"], 6),
        "mean_move_distance": round(metrics["mean_move_distance"], 6),
        "weighted_mean_swap_span": round(metrics["weighted_mean_swap_span"], 6),
        "scheduler_sweeps": int(scheduler_sweeps),
        "termination": termination,
    }


def _traditional_bubble_sort(arr: list[int], frozen_indices: set[int], max_iterations: int = 10000):
    arr = list(arr)
    n = len(arr)
    swap_count = 0
    compare_count = 0
    total_move_distance = 0
    for iteration in range(max_iterations):
        swapped = False
        for i in range(n - 1):
            if i in frozen_indices or (i + 1) in frozen_indices:
                continue
            compare_count += 1
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swapped = True
                swap_count += 1
                total_move_distance += 2
        if not swapped:
            return arr, swap_count, compare_count, total_move_distance
    return arr, swap_count, compare_count, total_move_distance


def _traditional_selection_sort(
    arr: list[int],
    frozen_indices: set[int],
    max_iterations: int = 10000,
):
    arr = list(arr)
    n = len(arr)
    swap_count = 0
    compare_count = 0
    total_move_distance = 0
    for i in range(n - 1):
        if i in frozen_indices:
            continue
        min_idx = i
        for j in range(i + 1, n):
            if j in frozen_indices:
                continue
            compare_count += 1
            if arr[j] < arr[min_idx]:
                min_idx = j
        if min_idx != i and min_idx not in frozen_indices:
            arr[i], arr[min_idx] = arr[min_idx], arr[i]
            swap_count += 1
            total_move_distance += 2 * abs(min_idx - i)
    return arr, swap_count, compare_count, total_move_distance


def _traditional_insertion_sort(
    arr: list[int],
    frozen_indices: set[int],
    max_iterations: int = 10000,
):
    arr = list(arr)
    n = len(arr)
    writes = 0
    compare_count = 0
    total_move_distance = 0
    for i in range(1, n):
        if i in frozen_indices:
            continue
        key = arr[i]
        j = i - 1
        insert_index = i
        while j >= 0 and j not in frozen_indices:
            compare_count += 1
            if arr[j] <= key:
                break
            if (j + 1) not in frozen_indices:
                arr[j + 1] = arr[j]
                writes += 1
                total_move_distance += 2
                insert_index = j
            j -= 1
        if (j + 1) not in frozen_indices:
            arr[j + 1] = key
            writes += 1
            if insert_index != i:
                total_move_distance += 2 * abs(i - insert_index)
    return arr, writes, compare_count, total_move_distance


def _run_traditional_trial(
    *,
    sort_fn,
    values: list[int],
    frozen_indices: set[int],
) -> dict[str, Any]:
    start = time.time()
    final_arr, swap_like_count, compare_count, total_move_distance = sort_fn(values, frozen_indices)
    elapsed = time.time() - start
    final_error = _monotonicity_error(final_arr, frozen_indices=frozen_indices, is_cells=False)
    return {
        "success": final_error == 0,
        "error": int(final_error),
        "time": float(elapsed),
        "swaps": int(swap_like_count),
        "compare_and_swap_count": int(compare_count),
        "total_move_distance": round(float(total_move_distance), 6),
        "weighted_mean_swap_span": round(
            total_move_distance / (2.0 * swap_like_count) if swap_like_count > 0 else 0.0,
            6,
        ),
        "termination": "completed",
    }


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}
    termination_counts: dict[str, int] = {}
    for result in results:
        termination = result.get("termination")
        if termination is not None:
            termination_counts[termination] = termination_counts.get(termination, 0) + 1
    out: dict[str, Any] = {
        "n_trials": float(len(results)),
        "success_count": float(sum(1 if r["success"] else 0 for r in results)),
        "success_rate": float(np.mean([1.0 if r["success"] else 0.0 for r in results])),
        "avg_error": float(np.mean([r["error"] for r in results])),
        "avg_time": float(np.mean([r["time"] for r in results])),
    }
    for key in [
        "swaps",
        "compare_and_swap_count",
        "frozen_swap_attempts",
        "total_move_distance",
        "mean_move_distance",
        "weighted_mean_swap_span",
        "scheduler_sweeps",
    ]:
        vals = [float(r[key]) for r in results if key in r]
        if vals:
            out[f"avg_{key}"] = float(np.mean(vals))
    if termination_counts:
        out["termination_counts"] = termination_counts  # type: ignore[assignment]
    return out


def _pairwise_match_rate(
    paired_trials: list[dict[str, Any]],
    lhs_key: str,
    rhs_key: str,
    metric: str,
) -> float | None:
    matches = []
    for trial in paired_trials:
        lhs = trial.get(lhs_key)
        rhs = trial.get(rhs_key)
        if lhs is None or rhs is None:
            continue
        matches.append(1.0 if lhs[metric] == rhs[metric] else 0.0)
    if not matches:
        return None
    return float(np.mean(matches))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exp26: substrate-matched baselines")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-cells", type=int, default=30)
    parser.add_argument("--n-trials", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-compare-and-swap", type=int, default=200000)
    parser.add_argument("--semantics", type=_parse_semantics, default="immovable")
    parser.add_argument("--frozen-counts", type=_parse_int_list, default=[0, 1, 3, 6, 9])
    parser.add_argument("--algorithms", type=_parse_str_list, default=None)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    if args.semantics != "immovable":
        raise ValueError("Exp26 currently supports only immovable semantics")

    seed = int(args.seed)
    rng = random.Random(seed)
    n_cells = int(args.n_cells)
    n_trials = int(args.n_trials)
    timeout = float(args.timeout)
    max_compare_and_swap = int(args.max_compare_and_swap)
    frozen_counts = list(args.frozen_counts)

    algorithms: dict[str, dict[str, Any]] = {
        "Bubble": {
            "cell_class": ImmovableBubbleCell,
            "traditional_fn": _traditional_bubble_sort,
        },
        "Insertion": {
            "cell_class": ImmovableInsertionCell,
            "traditional_fn": _traditional_insertion_sort,
        },
        "Selection": {
            "cell_class": ImmovableSelectionCell,
            "traditional_fn": _traditional_selection_sort,
        },
        "StubbornSelection": {
            "cell_class": ImmovableStubbornSelectionCell,
            "traditional_fn": None,
        },
        "AdjacentSelection": {
            "cell_class": ImmovableAdjacentSelectionCell,
            "traditional_fn": None,
        },
        "AdjacentStubbornSelection": {
            "cell_class": ImmovableAdjacentStubbornSelectionCell,
            "traditional_fn": None,
        },
    }
    if args.algorithms is not None:
        requested = set(args.algorithms)
        unknown = sorted(requested.difference(algorithms))
        if unknown:
            raise ValueError(f"unknown algorithms: {unknown}")
        algorithms = {name: algorithms[name] for name in algorithms if name in requested}

    print("=" * 70)
    print("EXPERIMENT 26: SUBSTRATE-MATCHED BASELINES")
    print("=" * 70)
    print(
        f"Setup: n_cells={n_cells}, n_trials={n_trials}, timeout={timeout}s, "
        f"max_compare_and_swap={max_compare_and_swap}, seed={seed}, "
        f"semantics={args.semantics}"
    )
    print(f"Frozen counts: {frozen_counts}\n")
    print("Interpretation: threaded vs sequential is matched; textbook is reference-only.\n")

    trial_setups: dict[int, list[dict[str, Any]]] = {}
    for n_frozen in frozen_counts:
        setups = []
        for trial_id in range(n_trials):
            values = list(range(n_cells))
            rng.shuffle(values)
            frozen_indices = set(rng.sample(range(n_cells), min(n_frozen, n_cells)))
            trial_seed = rng.randrange(1 << 30)
            setups.append(
                {
                    "trial_id": int(trial_id),
                    "initial_values": values,
                    "frozen_indices": sorted(frozen_indices),
                    "trial_seed": int(trial_seed),
                }
            )
        trial_setups[n_frozen] = setups

    output_algorithms: dict[str, Any] = {}

    for algo_name, cfg in algorithms.items():
        print(f"{algo_name}:")
        output_algorithms[algo_name] = {
            "threaded_cellview": {},
            "sequential_cellview": {},
            "textbook_centralized": {},
            "paired_trials": {},
            "pairwise_matches": {},
        }

        for n_frozen in frozen_counts:
            paired_trials = []
            for setup in trial_setups[n_frozen]:
                frozen_indices = set(setup["frozen_indices"])
                values = list(setup["initial_values"])
                trial_seed = int(setup["trial_seed"])

                threaded = _run_threaded_cellview_trial(
                    cell_class=cfg["cell_class"],
                    values=values,
                    frozen_indices=frozen_indices,
                    timeout=timeout,
                    max_compare_and_swap=max_compare_and_swap,
                    trial_seed=trial_seed,
                )
                sequential = _run_sequential_cellview_trial(
                    cell_class=cfg["cell_class"],
                    values=values,
                    frozen_indices=frozen_indices,
                    timeout=timeout,
                    max_compare_and_swap=max_compare_and_swap,
                    trial_seed=trial_seed,
                )
                centralized = None
                if cfg["traditional_fn"] is not None:
                    centralized = _run_traditional_trial(
                        sort_fn=cfg["traditional_fn"],
                        values=values,
                        frozen_indices=frozen_indices,
                    )

                paired_trials.append(
                    {
                        "trial_id": setup["trial_id"],
                        "trial_seed": trial_seed,
                        "initial_values": values,
                        "frozen_indices": setup["frozen_indices"],
                        "threaded_cellview": threaded,
                        "sequential_cellview": sequential,
                        "textbook_centralized": centralized,
                    }
                )

            threaded_results = [trial["threaded_cellview"] for trial in paired_trials]
            sequential_results = [trial["sequential_cellview"] for trial in paired_trials]
            centralized_results = [
                trial["textbook_centralized"]
                for trial in paired_trials
                if trial["textbook_centralized"] is not None
            ]

            threaded_summary = _summarize_results(threaded_results)
            sequential_summary = _summarize_results(sequential_results)
            centralized_summary = _summarize_results(centralized_results)

            output_algorithms[algo_name]["threaded_cellview"][str(n_frozen)] = threaded_summary
            output_algorithms[algo_name]["sequential_cellview"][str(n_frozen)] = sequential_summary
            output_algorithms[algo_name]["textbook_centralized"][str(n_frozen)] = (
                centralized_summary if centralized_results else None
            )
            output_algorithms[algo_name]["paired_trials"][str(n_frozen)] = paired_trials

            threaded_vs_sequential_success = _pairwise_match_rate(
                paired_trials, "threaded_cellview", "sequential_cellview", "success"
            )
            threaded_vs_sequential_error = _pairwise_match_rate(
                paired_trials, "threaded_cellview", "sequential_cellview", "error"
            )
            pairwise_matches = {
                "threaded_vs_sequential_success_match_rate": threaded_vs_sequential_success,
                "threaded_vs_sequential_error_match_rate": threaded_vs_sequential_error,
            }
            if centralized_results:
                pairwise_matches["threaded_vs_textbook_success_match_rate"] = _pairwise_match_rate(
                    paired_trials, "threaded_cellview", "textbook_centralized", "success"
                )
                pairwise_matches["threaded_vs_textbook_error_match_rate"] = _pairwise_match_rate(
                    paired_trials, "threaded_cellview", "textbook_centralized", "error"
                )
                pairwise_matches["sequential_vs_textbook_success_match_rate"] = (
                    _pairwise_match_rate(
                        paired_trials, "sequential_cellview", "textbook_centralized", "success"
                    )
                )
                pairwise_matches["sequential_vs_textbook_error_match_rate"] = (
                    _pairwise_match_rate(
                        paired_trials, "sequential_cellview", "textbook_centralized", "error"
                    )
                )
            output_algorithms[algo_name]["pairwise_matches"][str(n_frozen)] = pairwise_matches

            print(
                f"  frozen={n_frozen:<2} "
                f"threaded={threaded_summary['success_rate']:.0%} "
                f"(err={threaded_summary['avg_error']:.2f}), "
                f"sequential={sequential_summary['success_rate']:.0%} "
                f"(err={sequential_summary['avg_error']:.2f}), "
                f"match_s={threaded_vs_sequential_success:.0%} "
                f"match_e={threaded_vs_sequential_error:.0%}"
            )
            if centralized_results:
                print(
                    f"             textbook={centralized_summary['success_rate']:.0%} "
                    f"(err={centralized_summary['avg_error']:.2f}), "
                    f"seq_vs_text_s={pairwise_matches['sequential_vs_textbook_success_match_rate']:.0%}"
                )

        print("")

    out_obj = {
        "seed": seed,
        "n_cells": n_cells,
        "n_trials": n_trials,
        "timeout": timeout,
        "max_compare_and_swap": max_compare_and_swap,
        "semantics": args.semantics,
        "matched_substrates": ["threaded_cellview", "sequential_cellview"],
        "textbook_centralized_is_reference_only": True,
        "algorithm_order": list(algorithms.keys()),
        "frozen_counts": frozen_counts,
        "algorithms": output_algorithms,
    }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
        print(f"Wrote: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
