#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    raise SystemExit(
        "Run from dossiers/wonton-soup with "
        "`uv run python -m experiments.causal_contrast.run ...`."
    )

from orchestrator.lean import run_corpus
from orchestrator.lean_options import parse_budget
from runtime_paths import resolve_logs_root

from .summary import MODES, build_paired_contrast_summary


def _parse_csv(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def _has_ymd_prefix(value: str) -> bool:
    head = value.split("/", 1)[0]
    if len(head) < 11:
        return False
    return (
        head[0:4].isdigit()
        and head[4] == "-"
        and head[5:7].isdigit()
        and head[7] == "-"
        and head[8:10].isdigit()
        and head[10] == "-"
    )


def _normalize_root_run_id(value: str | None) -> str:
    raw = value.strip() if value else "causal-contrast"
    if not raw:
        raw = "causal-contrast"
    if raw.startswith("corpus-") or _has_ymd_prefix(raw):
        return raw
    return f"{datetime.now().strftime('%Y-%m-%d')}-{raw}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Paired centralized-vs-distributed MCTS causal contrast."
    )
    parser.add_argument("--project-path", type=str, default=None)
    parser.add_argument("--providers", type=str, default="heuristic")
    parser.add_argument("--corpus", type=str, default="easy")
    parser.add_argument("--mode", type=str, default="causal_contrast")
    parser.add_argument("--budget", type=str, default="quick")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--seed", type=int, default=20260602)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--analysis", action="store_true")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument(
        "--no-postprocess-metrics",
        action="store_false",
        dest="postprocess_metrics",
        help="Skip expensive post-run soft-metric enrichment.",
    )
    parser.set_defaults(postprocess_metrics=True)
    parser.add_argument("--allow-easy", action="store_true")
    parser.add_argument(
        "--baseline-solved-only",
        action="store_true",
        help="Run interventions only for theorems solved by the wild-type baseline.",
    )
    parser.add_argument("--deepseek-model-path", type=str, default=None)
    parser.add_argument(
        "--deepseek-backend",
        choices=("mlx", "transformers"),
        default="mlx",
    )
    parser.add_argument(
        "--deepseek-device",
        choices=("cpu", "mps", "cuda"),
        default=None,
        help="Explicit transformers device for DeepSeek runs.",
    )
    parser.add_argument("--deepseek-samples", type=int, default=None)
    trace_group = parser.add_mutually_exclusive_group()
    trace_group.add_argument("--trace-mcts", action="store_true", dest="trace_mcts")
    trace_group.add_argument("--no-trace-mcts", action="store_false", dest="trace_mcts")
    parser.set_defaults(trace_mcts=True)
    intervention_group = parser.add_mutually_exclusive_group()
    intervention_group.add_argument(
        "--with-interventions",
        action="store_true",
        dest="with_interventions",
    )
    intervention_group.add_argument("--wild-only", action="store_false", dest="with_interventions")
    parser.set_defaults(with_interventions=True)

    parser.add_argument("--mcts-agents", type=int, default=4)
    parser.add_argument(
        "--mcts-expansion-policy",
        choices=("first-success", "all-successes"),
        default="all-successes",
    )
    parser.add_argument("--mcts-inflight", type=int, default=16)
    parser.add_argument("--mcts-virtual-loss", type=int, default=1)
    parser.add_argument("--mcts-depth-bias", type=float, default=0.0)
    parser.add_argument("--mcts-path-bias", type=float, default=0.0)
    parser.add_argument("--mcts-history-cache", action="store_true")
    parser.add_argument("--mcts-deterministic-inference", action="store_true")
    parser.add_argument("--mcts-block-fraction", type=float, default=None)
    parser.add_argument("--mcts-block-duration", type=int, default=None)
    parser.add_argument("--mcts-block-seed", type=int, default=None)
    parser.add_argument("--mcts-block-immovable-fraction", type=float, default=None)
    parser.add_argument("--mcts-unfreeze-after", type=int, default=None)
    parser.add_argument("--mcts-unfreeze-prob", type=float, default=None)
    parser.add_argument("--mcts-reroute-max", type=int, default=None)
    parser.add_argument("--mcts-delay-prob", type=float, default=None)
    parser.add_argument("--mcts-delay-duration", type=int, default=None)
    parser.add_argument("--mcts-delay-seed", type=int, default=None)
    return parser.parse_args()


def _distributed_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.mcts_agents < 1:
        raise SystemExit("--mcts-agents must be >= 1")
    if args.mcts_inflight < 1:
        raise SystemExit("--mcts-inflight must be >= 1")
    if args.mcts_virtual_loss < 0:
        raise SystemExit("--mcts-virtual-loss must be >= 0")
    if args.mcts_depth_bias < 0:
        raise SystemExit("--mcts-depth-bias must be >= 0")
    if args.mcts_path_bias < 0:
        raise SystemExit("--mcts-path-bias must be >= 0")
    if args.mcts_block_fraction is None:
        block_args = (
            args.mcts_block_duration,
            args.mcts_block_seed,
            args.mcts_block_immovable_fraction,
            args.mcts_unfreeze_after,
            args.mcts_unfreeze_prob,
        )
        if any(value is not None for value in block_args):
            raise SystemExit("--mcts-block-* and --mcts-unfreeze-* require --mcts-block-fraction")
    else:
        if not (0.0 < args.mcts_block_fraction < 1.0):
            raise SystemExit("--mcts-block-fraction must be between 0 and 1")
        if args.mcts_block_duration is None:
            raise SystemExit("--mcts-block-duration is required with --mcts-block-fraction")
        if args.mcts_block_duration == 0:
            raise SystemExit("--mcts-block-duration must be non-zero")
        if args.mcts_block_seed is None:
            raise SystemExit("--mcts-block-seed is required with --mcts-block-fraction")
        if args.mcts_block_immovable_fraction is not None:
            if not (0.0 <= args.mcts_block_immovable_fraction <= 1.0):
                raise SystemExit("--mcts-block-immovable-fraction must be between 0 and 1")
            if args.mcts_block_duration < 0:
                raise SystemExit(
                    "--mcts-block-immovable-fraction requires positive --mcts-block-duration"
                )
        if args.mcts_unfreeze_after is not None and args.mcts_unfreeze_after < 1:
            raise SystemExit("--mcts-unfreeze-after must be >= 1")
        if args.mcts_unfreeze_prob is not None and not (0.0 < args.mcts_unfreeze_prob <= 1.0):
            raise SystemExit("--mcts-unfreeze-prob must be in (0, 1]")
    if args.mcts_reroute_max is not None and args.mcts_reroute_max < 1:
        raise SystemExit("--mcts-reroute-max must be >= 1")
    if any(
        value is not None
        for value in (args.mcts_delay_prob, args.mcts_delay_duration, args.mcts_delay_seed)
    ):
        if (
            args.mcts_delay_prob is None
            or args.mcts_delay_duration is None
            or args.mcts_delay_seed is None
        ):
            raise SystemExit(
                "--mcts-delay-prob, --mcts-delay-duration, and --mcts-delay-seed "
                "must be set together"
            )
        if not (0.0 < args.mcts_delay_prob < 1.0):
            raise SystemExit("--mcts-delay-prob must be between 0 and 1")
        if args.mcts_delay_duration < 1:
            raise SystemExit("--mcts-delay-duration must be >= 1")
        if args.mcts_delay_seed < 0:
            raise SystemExit("--mcts-delay-seed must be >= 0")
    return {
        "agents": args.mcts_agents,
        "inflight": args.mcts_inflight,
        "virtual_loss": args.mcts_virtual_loss,
        "depth_bias": args.mcts_depth_bias,
        "path_bias": args.mcts_path_bias,
        "history_cache": bool(args.mcts_history_cache),
        "deterministic_inference": bool(args.mcts_deterministic_inference),
        "block_fraction": args.mcts_block_fraction,
        "block_duration": args.mcts_block_duration,
        "block_seed": args.mcts_block_seed,
        "block_immovable_fraction": args.mcts_block_immovable_fraction,
        "block_unfreeze_after": args.mcts_unfreeze_after,
        "block_unfreeze_prob": args.mcts_unfreeze_prob,
        "reroute_max_attempts": args.mcts_reroute_max,
        "delay_probability": args.mcts_delay_prob,
        "delay_duration": args.mcts_delay_duration,
        "delay_seed": args.mcts_delay_seed,
    }


async def _run() -> None:
    args = _parse_args()
    project_path = args.project_path or os.environ.get("LEAN_PROJECT_PATH")
    if project_path is None:
        local_project = Path("lean_project")
        if local_project.exists():
            project_path = str(local_project)
        else:
            raise SystemExit("LEAN_PROJECT_PATH not set and --project-path not provided")

    providers = _parse_csv(args.providers)
    if not providers:
        raise SystemExit("--providers must name at least one provider")
    if args.deepseek_samples is not None and args.deepseek_samples < 1:
        raise SystemExit("--deepseek-samples must be >= 1")
    if args.deepseek_model_path is not None and not Path(args.deepseek_model_path).exists():
        raise SystemExit(f"DeepSeek model not found: {args.deepseek_model_path}")
    budget_tiers = parse_budget(args.budget)
    if sum(budget_tiers) <= 0:
        raise SystemExit("budget must be > 0")
    root_run_id = _normalize_root_run_id(args.run_id)
    logs_dir = resolve_logs_root().resolve()
    root_dir = logs_dir / root_run_id
    root_dir.mkdir(parents=True, exist_ok=True)
    dist_settings = _distributed_settings(args)
    block_easy = not args.allow_easy
    run_dirs: dict[str, dict[str, Path]] = {provider: {} for provider in providers}

    experiment = {
        "providers": providers,
        "corpus": args.corpus,
        "budget": args.budget,
        "budget_tiers": budget_tiers,
        "limit": args.limit,
        "offset": args.offset,
        "sample": args.sample,
        "seed": args.seed,
        "workers": args.workers,
        "with_interventions": args.with_interventions,
        "baseline_solved_only": args.baseline_solved_only,
        "trace_mcts": args.trace_mcts,
        "plain": args.plain,
        "postprocess_metrics": args.postprocess_metrics,
        "block_easy": block_easy,
        "deepseek_backend": args.deepseek_backend,
        "deepseek_model_path": args.deepseek_model_path,
        "deepseek_device": args.deepseek_device,
        "deepseek_samples": args.deepseek_samples,
        "mcts_expansion_policy": args.mcts_expansion_policy,
        "distributed_settings": dist_settings,
    }

    for provider in providers:
        for mode in MODES:
            child_run_id = f"{root_run_id}/provider={provider}/mcts={mode}"
            run_dirs[provider][mode] = logs_dir / child_run_id
            await run_corpus(
                project_path=project_path,
                budget_tiers=budget_tiers,
                budget_label=args.budget,
                provider_name=provider,
                corpus=args.corpus,
                limit=args.limit,
                offset=args.offset,
                sample=args.sample,
                seed=args.seed,
                num_workers=args.workers,
                run_id=child_run_id,
                trace_mcts=args.trace_mcts,
                skip_interventions=not args.with_interventions,
                skip_interventions_after_wild_failure=args.baseline_solved_only,
                block_easy=block_easy,
                mcts_mode=mode,
                expansion_policy=args.mcts_expansion_policy,
                distributed_settings=dist_settings if mode == "distributed" else None,
                provider_label=f"{provider}+{mode}",
                mode=args.mode,
                mode_defaults={"budget": args.budget},
                cli_args=experiment | {"provider": provider, "mcts_mode": mode},
                run_analysis=args.analysis,
                postprocess_metrics=args.postprocess_metrics,
                plain=args.plain,
                device=args.deepseek_device if provider == "deepseek" else None,
                deepseek_backend=args.deepseek_backend,
                deepseek_model_path=args.deepseek_model_path,
                deepseek_num_samples=args.deepseek_samples,
                resume=args.resume,
                no_sync=args.no_sync,
            )

    payload = build_paired_contrast_summary(
        root_dir=root_dir,
        logs_dir=logs_dir,
        run_id=root_run_id,
        providers=providers,
        run_dirs=run_dirs,
        experiment=experiment,
    )
    print(root_dir / "paired_contrast_summary.json")
    print(
        "paired contrast complete: "
        + ", ".join(
            f"{row['provider']} recovery_delta={row['delta']['recovery_rate']}"
            for row in payload["providers"]
        )
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
