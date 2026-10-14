"""Compute directed flow on the paper's shell-order 2D condition."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from paper.compute_dip_stats import (
    Bubble2DCell,
    CellStatus2D,
    Selection2DCell,
    create_2d_grid,
    shell_inversion_count,
)


def get_dist(cell_value: int, position: tuple[int, int], grid) -> int:
    ideal = grid.order_positions[cell_value]
    return abs(position[0] - ideal[0]) + abs(position[1] - ideal[1])


def run_2d_initiator_flow_trial(
    *,
    size: int,
    connectivity: int,
    cell_class: type,
    max_steps: int,
    trial_seed: int,
) -> dict:
    grid = create_2d_grid(
        size,
        0,
        cell_class,
        connectivity=connectivity,
        trial_seed=trial_seed,
    )

    forward_swaps = 0
    backward_swaps = 0

    for _ in range(max_steps):
        made_swap = False
        cells = grid.get_all_cells()
        random.shuffle(cells)

        for cell in cells:
            if cell.status != CellStatus2D.ACTIVE:
                continue
            neighbors = cell.get_neighbors()
            random.shuffle(neighbors)
            for neighbor in neighbors:
                if cell.should_swap_with(neighbor):
                    dist_before = get_dist(cell.value, cell.position, grid)
                    dist_after = get_dist(cell.value, neighbor.position, grid)
                    if dist_after < dist_before:
                        forward_swaps += 1
                    else:
                        backward_swaps += 1
                    grid.swap_cells(cell, neighbor)
                    made_swap = True
                    break
            if made_swap:
                break

        if shell_inversion_count(grid) == 0 or not made_swap:
            break

    return {
        "forward": forward_swaps,
        "backward": backward_swaps,
        "sorted": shell_inversion_count(grid) == 0,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute directed flow for shell-order 2D")
    parser.add_argument("--n-trials", type=int, default=30)
    parser.add_argument("--base-seed", type=int, default=20260306)
    parser.add_argument("--grid-size", type=int, default=6)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("paper/results/fig5_directed_flow.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rng = random.Random(args.base_seed)
    max_steps = args.max_steps or (30 * args.grid_size * args.grid_size)

    conditions = [
        ("2d_bubble", Bubble2DCell),
        ("2d_selection", Selection2DCell),
    ]

    results = {}
    for label, cell_class in conditions:
        print(f"Running {label} for {args.n_trials} trials...")
        forward_total = 0
        backward_total = 0
        success_count = 0

        for _ in range(args.n_trials):
            result = run_2d_initiator_flow_trial(
                size=args.grid_size,
                connectivity=args.connectivity,
                cell_class=cell_class,
                max_steps=max_steps,
                trial_seed=rng.randrange(2**32),
            )
            forward_total += result["forward"]
            backward_total += result["backward"]
            success_count += int(result["sorted"])

        ratio = forward_total / max(1, backward_total)
        results[label] = {
            "forward": forward_total,
            "backward": backward_total,
            "ratio": ratio,
            "success_rate": success_count / args.n_trials,
        }
        print(
            f"  {label}: forward={forward_total}, backward={backward_total}, "
            f"ratio={ratio:.3f}, success={success_count}/{args.n_trials}"
        )

    results["provenance"] = {
        "generator": "paper/compute_directed_flow.py",
        "n_trials": args.n_trials,
        "base_seed": args.base_seed,
        "grid_size": args.grid_size,
        "connectivity": args.connectivity,
        "max_steps": max_steps,
        "ordering": "shell ordering by squared distance from origin",
        "n_frozen": 0,
        "distance_metric": "initiator Manhattan distance to ideal position",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
