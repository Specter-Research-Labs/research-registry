#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any, Iterable

if __package__ in {None, ""}:
    raise SystemExit(
        "Run from dossiers/wonton-soup with "
        "`uv run python -m experiments.distributed_mcts.run ...`."
    )

from orchestrator.lean import run_corpus
from orchestrator.lean_options import parse_budget


@dataclass(frozen=True)
class Scenario:
    name: str
    settings: dict[str, Any]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Distributed MCTS robustness sweeps (baseline, damage, adaptation)."
    )
    parser.add_argument("--project-path", type=str, default=None)
    parser.add_argument("--budget", type=str, default="standard")
    parser.add_argument("--provider", type=str, default="reprover")
    parser.add_argument("--corpus", type=str, default="research")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--run-id", type=str, required=True)
    trace_group = parser.add_mutually_exclusive_group()
    trace_group.add_argument("--trace-mcts", action="store_true", dest="trace_mcts")
    trace_group.add_argument("--no-trace-mcts", action="store_false", dest="trace_mcts")
    parser.set_defaults(trace_mcts=True)
    parser.add_argument(
        "--allow-easy",
        action="store_true",
        help="Allow simp/omega/decide/rfl tactics (blocked by default)",
    )

    parser.add_argument("--mcts-agents", type=int, required=True)
    parser.add_argument(
        "--mcts-expansion-policy",
        choices=("first-success", "all-successes"),
        default="all-successes",
    )
    parser.add_argument("--mcts-inflight", type=int, required=True)
    parser.add_argument("--mcts-virtual-loss", type=int, default=0)
    parser.add_argument("--mcts-depth-bias", type=float, default=0.0)
    parser.add_argument("--mcts-path-bias", type=float, default=0.0)
    parser.add_argument("--mcts-history-cache", action="store_true")

    parser.add_argument("--block-fractions", type=float, nargs="*", default=None)
    parser.add_argument("--block-duration", type=int, default=None)
    parser.add_argument("--block-seed", type=int, default=None)
    parser.add_argument("--block-immovable-fraction", type=float, default=None)

    parser.add_argument("--delay-probabilities", type=float, nargs="*", default=None)
    parser.add_argument("--delay-duration", type=int, default=None)
    parser.add_argument("--delay-seed", type=int, default=None)

    parser.add_argument("--adaptation", action="store_true")
    parser.add_argument("--reroute-max", type=int, default=None)
    parser.add_argument("--unfreeze-after", type=int, default=None)
    parser.add_argument("--unfreeze-prob", type=float, default=None)

    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    if args.block_fractions is None and args.delay_probabilities is None:
        raise SystemExit("Provide --block-fractions and/or --delay-probabilities for a sweep")

    if args.block_fractions is not None:
        if args.block_duration is None:
            raise SystemExit("--block-duration is required with --block-fractions")
        if args.block_duration == 0:
            raise SystemExit("--block-duration must be non-zero")
        if args.block_seed is None:
            raise SystemExit("--block-seed is required with --block-fractions")
        for value in args.block_fractions:
            if not (0.0 < value < 1.0):
                raise SystemExit("--block-fractions values must be in (0, 1)")
        if args.block_immovable_fraction is not None:
            if not (0.0 <= args.block_immovable_fraction <= 1.0):
                raise SystemExit("--block-immovable-fraction must be between 0 and 1")
            if args.block_duration < 0:
                raise SystemExit(
                    "--block-immovable-fraction requires positive --block-duration"
                )

    if args.delay_probabilities is not None:
        if args.delay_duration is None or args.delay_seed is None:
            raise SystemExit(
                "--delay-duration and --delay-seed are required with --delay-probabilities"
            )
        if args.delay_duration < 1:
            raise SystemExit("--delay-duration must be >= 1")
        if args.delay_seed < 0:
            raise SystemExit("--delay-seed must be >= 0")
        for value in args.delay_probabilities:
            if not (0.0 < value < 1.0):
                raise SystemExit("--delay-probabilities values must be in (0, 1)")

    if args.adaptation:
        if args.block_fractions is None:
            raise SystemExit("--adaptation requires --block-fractions")
        if args.reroute_max is None and args.unfreeze_after is None and args.unfreeze_prob is None:
            raise SystemExit(
                "--adaptation requires --reroute-max or --unfreeze-after/--unfreeze-prob"
            )
        if args.reroute_max is not None and args.reroute_max < 1:
            raise SystemExit("--reroute-max must be >= 1")
        if args.unfreeze_after is not None and args.unfreeze_after < 1:
            raise SystemExit("--unfreeze-after must be >= 1")
        if args.unfreeze_prob is not None and not (0.0 < args.unfreeze_prob <= 1.0):
            raise SystemExit("--unfreeze-prob must be in (0, 1]")


def _base_settings(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "agents": args.mcts_agents,
        "inflight": args.mcts_inflight,
        "virtual_loss": args.mcts_virtual_loss,
        "depth_bias": args.mcts_depth_bias,
        "path_bias": args.mcts_path_bias,
        "history_cache": args.mcts_history_cache,
    }


def _block_settings(args: argparse.Namespace, fraction: float) -> dict[str, Any]:
    return {
        "block_fraction": fraction,
        "block_duration": args.block_duration,
        "block_seed": args.block_seed,
        "block_immovable_fraction": args.block_immovable_fraction,
        "block_unfreeze_after": None,
        "block_unfreeze_prob": None,
    }


def _delay_settings(args: argparse.Namespace, probability: float) -> dict[str, Any]:
    return {
        "delay_probability": probability,
        "delay_duration": args.delay_duration,
        "delay_seed": args.delay_seed,
    }


def _format_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _scenarios(args: argparse.Namespace) -> list[Scenario]:
    base = _base_settings(args)
    scenarios: list[Scenario] = [Scenario(name="baseline", settings=dict(base))]

    if args.block_fractions is not None:
        for frac in args.block_fractions:
            damage = dict(base)
            damage.update(_block_settings(args, frac))
            scenarios.append(Scenario(name=f"damage-block-f{_format_float(frac)}", settings=damage))

            if args.adaptation:
                adapt = dict(damage)
                if args.reroute_max is not None:
                    adapt["reroute_max_attempts"] = args.reroute_max
                if args.unfreeze_after is not None:
                    adapt["block_unfreeze_after"] = args.unfreeze_after
                if args.unfreeze_prob is not None:
                    adapt["block_unfreeze_prob"] = args.unfreeze_prob
                scenarios.append(
                    Scenario(
                        name=f"adapt-block-f{_format_float(frac)}",
                        settings=adapt,
                    )
                )

    if args.delay_probabilities is not None:
        for prob in args.delay_probabilities:
            damage = dict(base)
            damage.update(_delay_settings(args, prob))
            scenarios.append(
                Scenario(name=f"damage-delay-p{_format_float(prob)}", settings=damage)
            )

    return scenarios


async def _run_scenarios(args: argparse.Namespace, scenarios: Iterable[Scenario]) -> None:
    project_path = args.project_path or os.environ.get("LEAN_PROJECT_PATH")
    if project_path is None:
        raise SystemExit("LEAN_PROJECT_PATH not set and --project-path not provided")

    budget_tiers = parse_budget(args.budget)
    total_budget = sum(budget_tiers)
    if total_budget <= 0:
        raise SystemExit("budget must be > 0")

    block_easy = not args.allow_easy

    for scenario in scenarios:
        run_id = f"{args.run_id}-{scenario.name}"
        await run_corpus(
            project_path=project_path,
            budget_tiers=budget_tiers,
            provider_name=args.provider,
            corpus=args.corpus,
            limit=args.limit,
            offset=args.offset,
            sample=args.sample,
            seed=args.seed,
            num_workers=args.workers,
            run_id=run_id,
            trace_mcts=args.trace_mcts,
            skip_interventions=False,
            block_easy=block_easy,
            mcts_mode="distributed",
            expansion_policy=args.mcts_expansion_policy,
            distributed_settings=scenario.settings,
            provider_label=f"{args.provider}+{scenario.name}",
            mode="distributed_mcts_sweep",
            mode_defaults={"budget": args.budget},
            cli_args={
                "scenario": scenario.name,
                "mcts_expansion_policy": args.mcts_expansion_policy,
                "block_fractions": args.block_fractions,
                "delay_probabilities": args.delay_probabilities,
                "adaptation": args.adaptation,
                "reroute_max": args.reroute_max,
                "unfreeze_after": args.unfreeze_after,
                "unfreeze_prob": args.unfreeze_prob,
            },
        )


def main() -> None:
    args = _parse_args()
    _validate_args(args)
    scenarios = _scenarios(args)
    asyncio.run(_run_scenarios(args, scenarios))


if __name__ == "__main__":
    main()
