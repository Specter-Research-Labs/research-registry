"""Compute matched exact state-space K for the Selection factorization.

This uses a family-matched analysis in the immovable factorization regime, where frozen indices are
fixed and operator classes are explicit.

Definitions used here:

- Problem spaces are restricted to immovable factorization trials.
- Long-range family:
  - operators are active-active transpositions
  - operator cost is swap span w(o) = |i - j|
  - reachable state count is (n_active)!
- Adjacent family:
  - operators are adjacent active-active swaps
  - operator cost is w(o) = 1
  - reachable state count is prod_r (segment_r)!

Exact maximal-entropy operator-walk hitting times are intractable at n=30, so we report an exact
matched state-space null:

  tau_blind_state = |S_reachable| * mean_operator_cost

This is exact for a null that proposes reachable states uniformly at random and pays the matched
mean operator cost per proposal. The same quantity can also be read conservatively under an
operator-walk interpretation, because graph geometry can only make blind hitting harder.

Agent cost uses the realized span-weighted movement cost per attempt:

  cost_attempt = total_move_distance / 2

To fold failures into the denominator, we use an effective cost-to-first-success over reachable
trial instances:

  tau_agent_eff = mean(cost_attempt) / p_success

where p_success is the empirical success rate over reachable trial instances. If p_success = 0,
K is undefined.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_INPUT_GLOB = "exp25_seed*_n30_t5_immovable.json"
VARIANT_ORDER = [
    "long_range_rerouting",
    "long_range_stubborn",
    "adjacent_rerouting",
    "adjacent_stubborn",
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute matched state-space K for the factorization"
    )
    parser.add_argument(
        "--inputs-glob",
        default=DEFAULT_INPUT_GLOB,
        help="Glob under paper/results/ for immovable factorization raw JSON files.",
    )
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "fig6_k_values.json")
    return parser.parse_args(argv)


def _segment_lengths(n_cells: int, frozen_indices: list[int]) -> list[int]:
    frozen = set(frozen_indices)
    lengths: list[int] = []
    run = 0
    for index in range(n_cells):
        if index in frozen:
            if run:
                lengths.append(run)
                run = 0
            continue
        run += 1
    if run:
        lengths.append(run)
    return lengths


def _adjacent_reachable(values: list[int], frozen_indices: list[int]) -> bool:
    n_cells = len(values)
    segments: list[list[int]] = []
    frozen = set(frozen_indices)
    current: list[int] = []
    for index in range(n_cells):
        if index in frozen:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(index)
    if current:
        segments.append(current)

    active_values = [values[index] for index in range(n_cells) if index not in frozen]
    target = sorted(active_values)
    cursor = 0
    for segment in segments:
        segment_values = sorted(values[index] for index in segment)
        target_slice = target[cursor: cursor + len(segment)]
        if segment_values != target_slice:
            return False
        cursor += len(segment)
    return True


def _mean_long_range_span(n_cells: int, frozen_indices: list[int]) -> float:
    frozen = set(frozen_indices)
    active_positions = [index for index in range(n_cells) if index not in frozen]
    if len(active_positions) < 2:
        return 0.0
    total_span = 0
    operator_count = 0
    for source in active_positions:
        for target in active_positions:
            if source == target:
                continue
            total_span += abs(source - target)
            operator_count += 1
    return total_span / operator_count


def _trial_blind_lower(
    *,
    n_cells: int,
    family: str,
    frozen_indices: list[int],
) -> tuple[int, float, float, list[int]]:
    if family == "long_range":
        n_active = n_cells - len(frozen_indices)
        state_count = math.factorial(n_active)
        mean_operator_cost = _mean_long_range_span(n_cells, frozen_indices)
        return state_count, mean_operator_cost, state_count * mean_operator_cost, [n_active]

    if family == "adjacent":
        segment_lengths = _segment_lengths(n_cells, frozen_indices)
        state_count = 1
        for length in segment_lengths:
            state_count *= math.factorial(length)
        mean_operator_cost = 1.0
        return state_count, mean_operator_cost, float(state_count), segment_lengths

    raise ValueError(f"unknown family: {family}")


def _variant_family(variant: str) -> str:
    if variant.startswith("long_range"):
        return "long_range"
    if variant.startswith("adjacent"):
        return "adjacent"
    raise ValueError(f"unknown variant: {variant}")


def _load_trial_rows(
    inputs_glob: str,
) -> tuple[list[str], dict[str, dict[str, list[dict[str, Any]]]]]:
    paths = sorted(RESULTS_DIR.glob(inputs_glob))
    if not paths:
        raise FileNotFoundError(f"no input files matched {RESULTS_DIR / inputs_glob}")

    conditions: dict[str, dict[str, list[dict[str, Any]]]] = {
        variant: {} for variant in VARIANT_ORDER
    }

    for path in paths:
        data = json.loads(path.read_text())
        seed = int(data["seed"])
        n_cells = int(data["n_cells"])
        immovable = data["results"]["immovable"]

        for variant in VARIANT_ORDER:
            family = _variant_family(variant)
            for frozen_count, block in immovable[variant].items():
                bucket = conditions[variant].setdefault(frozen_count, [])
                for row in block["results"]:
                    frozen_indices = list(row["frozen_indices"])
                    reachable = (
                        True
                        if family == "long_range"
                        else _adjacent_reachable(row["initial_values"], frozen_indices)
                    )
                    (
                        state_count,
                        mean_operator_cost,
                        tau_blind_lower,
                        segment_lengths,
                    ) = _trial_blind_lower(
                        n_cells=n_cells,
                        family=family,
                        frozen_indices=frozen_indices,
                    )
                    bucket.append(
                        {
                            "seed": seed,
                            "trial_id": int(row["trial_id"]),
                            "family": family,
                            "frozen_count": int(frozen_count),
                            "initial_values": list(row["initial_values"]),
                            "frozen_indices": frozen_indices,
                            "reachable": bool(reachable),
                            "agent_success": bool(row["success"]),
                            "agent_move_cost": float(row["total_move_distance"]) / 2.0,
                            "state_count": int(state_count),
                            "state_count_log10": (
                                float(math.log10(state_count))
                                if state_count > 0
                                else float("nan")
                            ),
                            "mean_operator_cost": float(mean_operator_cost),
                            "tau_blind_lower": float(tau_blind_lower),
                            "segment_lengths": segment_lengths,
                        }
                    )

    return [path.name for path in paths], conditions


def _condition_summary(
    trial_rows: list[dict[str, Any]],
    *,
    n_boot: int,
    seed: int,
) -> dict[str, Any]:
    total_rows = len(trial_rows)
    reachable_rows = [row for row in trial_rows if row["reachable"]]
    reachable_count = len(reachable_rows)
    success_count_all = sum(1 for row in trial_rows if row["agent_success"])
    success_count_reachable = sum(1 for row in reachable_rows if row["agent_success"])
    success_rate_all = success_count_all / total_rows if total_rows else float("nan")
    success_rate_reachable = (
        success_count_reachable / reachable_count if reachable_count else float("nan")
    )
    avg_agent_move_cost = (
        float(np.mean([row["agent_move_cost"] for row in reachable_rows]))
        if reachable_rows
        else float("nan")
    )
    avg_tau_blind_lower = (
        float(np.mean([row["tau_blind_lower"] for row in reachable_rows]))
        if reachable_rows
        else float("nan")
    )
    avg_state_count_log10 = (
        float(np.mean([row["state_count_log10"] for row in reachable_rows]))
        if reachable_rows
        else float("nan")
    )
    avg_mean_operator_cost = (
        float(np.mean([row["mean_operator_cost"] for row in reachable_rows]))
        if reachable_rows
        else float("nan")
    )

    tau_agent_effective = float("nan")
    k_lower = float("nan")
    k_ci_lo = float("nan")
    k_ci_hi = float("nan")

    if reachable_rows and success_rate_reachable > 0:
        tau_agent_effective = avg_agent_move_cost / success_rate_reachable
        k_lower = math.log10(avg_tau_blind_lower / tau_agent_effective)

        rng = random.Random(seed)
        boot_samples: list[float] = []
        for _ in range(n_boot):
            sample = [
                reachable_rows[rng.randrange(reachable_count)]
                for _ in range(reachable_count)
            ]
            sample_success_rate = float(
                np.mean([1.0 if row["agent_success"] else 0.0 for row in sample])
            )
            if sample_success_rate <= 0:
                continue
            sample_agent = float(np.mean([row["agent_move_cost"] for row in sample]))
            sample_blind = float(np.mean([row["tau_blind_lower"] for row in sample]))
            tau_agent_sample = sample_agent / sample_success_rate
            boot_samples.append(math.log10(sample_blind / tau_agent_sample))

        if boot_samples:
            k_ci_lo = float(np.percentile(boot_samples, 2.5))
            k_ci_hi = float(np.percentile(boot_samples, 97.5))

    sample_segment_patterns = sorted(
        {tuple(row["segment_lengths"]) for row in reachable_rows}
    )
    sample_segment_patterns = sample_segment_patterns[:5]

    return {
        "n_trials": total_rows,
        "reachable_trial_count": reachable_count,
        "unreachable_trial_count": total_rows - reachable_count,
        "reachable_fraction": reachable_count / total_rows if total_rows else float("nan"),
        "success_count_all_trials": success_count_all,
        "success_rate_all_trials": success_rate_all,
        "success_count_reachable_trials": success_count_reachable,
        "success_rate_reachable_trials": success_rate_reachable,
        "avg_agent_move_cost_reachable": avg_agent_move_cost,
        "tau_agent_effective": tau_agent_effective,
        "avg_tau_blind_lower": avg_tau_blind_lower,
        "avg_state_count_log10": avg_state_count_log10,
        "avg_mean_operator_cost": avg_mean_operator_cost,
        "k_lower": k_lower,
        "k_ci_lo": k_ci_lo,
        "k_ci_hi": k_ci_hi,
        "sample_segment_patterns": [list(pattern) for pattern in sample_segment_patterns],
    }


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    input_names, conditions = _load_trial_rows(args.inputs_glob)

    frozen_counts = sorted(
        {int(frozen_count) for variant in conditions.values() for frozen_count in variant}
    )

    summaries: dict[str, dict[str, Any]] = {}
    for variant in VARIANT_ORDER:
        summaries[variant] = {}
        for frozen_count in frozen_counts:
            rows = conditions[variant][str(frozen_count)]
            summaries[variant][str(frozen_count)] = _condition_summary(
                rows,
                n_boot=int(args.n_boot),
                seed=int(args.seed) + frozen_count + 1000 * VARIANT_ORDER.index(variant),
            )

    out_obj = {
        "metric_name": "matched_state_space_k",
        "semantics": "immovable",
        "variants": VARIANT_ORDER,
        "frozen_counts": frozen_counts,
        "cost_model": {
            "operator_cost": "swap span w(o)=|i-j|",
            "agent_attempt_cost": "total_move_distance / 2",
            "tau_agent_effective": (
                "mean(agent_attempt_cost over reachable trials) / "
                "success_rate_reachable"
            ),
        },
        "blind_baseline": {
            "definition": "tau_blind_state = |S_reachable| * mean_operator_cost",
            "note": (
                "This quantity is exact for a uniform reachable-state proposal null with matched "
                "mean operator cost, and conservative if one instead insists on a blind "
                "operator-walk interpretation. Exact operator-walk hitting times are intractable "
                "at n=30."
            ),
            "long_range_state_count": "(n_active)!",
            "adjacent_state_count": "product_r (segment_r)!",
        },
        "inputs": input_names,
        "conditions": summaries,
        "trial_rows": conditions,
        "provenance": {
            "generator": "paper/compute_k.py",
            "source_surface": "immovable factorization raw trial archives",
            "inputs_glob": args.inputs_glob,
            "n_boot": int(args.n_boot),
            "seed": int(args.seed),
        },
    }

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, indent=2))
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv[1:]))
