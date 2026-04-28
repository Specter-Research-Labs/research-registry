"""Experiment 28: canonical 2D pipeline for paper-facing results.

This script writes one raw trial-level archive for the paper's 2D section.
It covers:
- shell-order heatmaps for Bubble2D and Selection2D
- alternate row-major / serpentine targets for LocalOrder2D and SelectionOrder2D
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from paper.exp2d_core import (
    OrderMode,
    algorithm_labels_for_mode,
    frozen_counts_for_size,
    generate_trial_setup,
    run_trial_from_setup,
)


def _parse_int_list(arg: str) -> list[int]:
    return [int(part.strip()) for part in arg.split(",") if part.strip()]


def _parse_modes(arg: str) -> list[str]:
    modes = [part.strip().lower() for part in arg.split(",") if part.strip()]
    allowed = {mode.value for mode in OrderMode}
    invalid = sorted(set(modes).difference(allowed))
    if invalid:
        raise argparse.ArgumentTypeError(f"unsupported order modes: {invalid}")
    return modes


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exp28: canonical 2D paper pipeline")
    parser.add_argument("--base-seed", type=int, default=20260324)
    parser.add_argument("--grid-sizes", type=_parse_int_list, default=[6, 8])
    parser.add_argument("--connectivities", type=_parse_int_list, default=[4, 8])
    parser.add_argument("--shell-trials", type=int, default=100)
    parser.add_argument("--alt-trials", type=int, default=50)
    parser.add_argument(
        "--alt-modes",
        type=_parse_modes,
        default=[OrderMode.ROW_MAJOR.value, OrderMode.SERPENTINE.value],
    )
    parser.add_argument("--max-step-factor", type=int, default=30)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/exp28_2d_canonical_trials.json"),
    )
    return parser.parse_args(argv)


def _condition_key(size: int, connectivity: int, order_mode: str, n_frozen: int) -> str:
    return f"{size}x{size}_conn{connectivity}_{order_mode}_frozen{n_frozen}"


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    rng = random.Random(args.base_seed)

    trial_rows = []
    shell_conditions = 0
    alt_conditions = 0

    print("=" * 70)
    print("EXPERIMENT 28: CANONICAL 2D PIPELINE")
    print("=" * 70)
    print(
        f"grid_sizes={args.grid_sizes}, connectivities={args.connectivities}, "
        f"shell_trials={args.shell_trials}, alt_trials={args.alt_trials}, "
        f"base_seed={args.base_seed}"
    )

    for size in args.grid_sizes:
        frozen_counts = frozen_counts_for_size(size)
        max_steps = args.max_step_factor * size * size

        for connectivity in args.connectivities:
            for n_frozen in frozen_counts:
                shell_conditions += 1
                for trial_index in range(args.shell_trials):
                    trial_seed = rng.randrange(2**32)
                    setup = generate_trial_setup(
                        size=size,
                        connectivity=connectivity,
                        order_mode=OrderMode.SHELL.value,
                        n_frozen=n_frozen,
                        trial_seed=trial_seed,
                        max_steps=max_steps,
                    )
                    pair_id = (
                        f"{_condition_key(size, connectivity, OrderMode.SHELL.value, n_frozen)}"
                        f"_trial{trial_index}"
                    )
                    for algorithm in algorithm_labels_for_mode(OrderMode.SHELL):
                        result = run_trial_from_setup(setup, algorithm=algorithm)
                        result["suite"] = "shell"
                        result["pair_id"] = pair_id
                        result["trial_index"] = trial_index
                        trial_rows.append(result)

            for order_mode in args.alt_modes:
                for n_frozen in frozen_counts:
                    alt_conditions += 1
                    for trial_index in range(args.alt_trials):
                        trial_seed = rng.randrange(2**32)
                        setup = generate_trial_setup(
                            size=size,
                            connectivity=connectivity,
                            order_mode=order_mode,
                            n_frozen=n_frozen,
                            trial_seed=trial_seed,
                            max_steps=max_steps,
                        )
                        pair_id = (
                            f"{_condition_key(size, connectivity, order_mode, n_frozen)}"
                            f"_trial{trial_index}"
                        )
                        for algorithm in algorithm_labels_for_mode(order_mode):
                            result = run_trial_from_setup(setup, algorithm=algorithm)
                            result["suite"] = "alt"
                            result["pair_id"] = pair_id
                            result["trial_index"] = trial_index
                            trial_rows.append(result)

    out_obj = {
        "base_seed": args.base_seed,
        "grid_sizes": args.grid_sizes,
        "connectivities": args.connectivities,
        "shell_trials": args.shell_trials,
        "alt_trials": args.alt_trials,
        "alt_modes": args.alt_modes,
        "max_step_factor": args.max_step_factor,
        "shell_conditions": shell_conditions,
        "alt_conditions": alt_conditions,
        "trial_rows": trial_rows,
        "provenance": {
            "generator": "exp28_2d_canonical.py",
            "description": (
                "Canonical paired 2D raw-trial archive for shell and alternate "
                "ordering targets"
            ),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, indent=2) + "\n")
    print(f"Wrote {args.out}")
    print(f"Shell rows: {sum(1 for row in trial_rows if row['suite'] == 'shell')}")
    print(f"Alt rows: {sum(1 for row in trial_rows if row['suite'] == 'alt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
