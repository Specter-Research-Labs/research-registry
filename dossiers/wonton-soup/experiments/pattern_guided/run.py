#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    raise SystemExit(
        "Run from dossiers/wonton-soup with "
        "`uv run python -m experiments.pattern_guided.run ...`."
    )

from orchestrator.lean import run_corpus
from orchestrator.lean_options import parse_budget
from runtime_paths import resolve_logs_root

from .patterns import make_pattern_stream
from .policy import PatternPolicy


@dataclass
class PatternTraceWriter:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._handle.write(_to_json(record))
        self._handle.write("\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def _to_json(record: dict[str, Any]) -> str:
    import json

    return json.dumps(record, ensure_ascii=True)


def _make_tactic_ranker(stream, policy, trace: PatternTraceWriter | None):
    def ranker(
        tactics_with_probs: list[tuple[str, float]],
        iteration: int,
        node,
    ) -> list[tuple[str, float]]:
        if not tactics_with_probs:
            return tactics_with_probs
        label = stream.label_at(iteration)
        idx = policy.choose_index(label, len(tactics_with_probs))
        chosen = tactics_with_probs[idx]
        reordered = [chosen] + [
            item for i, item in enumerate(tactics_with_probs) if i != idx
        ]
        if trace is not None:
            trace.write(
                {
                    "event": "tactic_rank",
                    "iteration": iteration,
                    "label": label,
                    "candidate_count": len(tactics_with_probs),
                    "chosen_index": idx,
                    "chosen_tactic": chosen[0],
                    "node": {
                        "mvar_id": node.mvar_id,
                        "goal_sig": node.goal_sig,
                        "goal_sig_strict": node.goal_sig_strict,
                        "goal_type": node.goal_type,
                    },
                }
            )
        return reordered

    return ranker


def _make_tie_breaker(stream, policy, trace: PatternTraceWriter | None):
    def breaker(candidates: list[tuple[str, Any]], iteration: int) -> tuple[str, Any]:
        label = stream.label_at(iteration)
        idx = policy.choose_index(label, len(candidates))
        chosen = candidates[idx]
        if trace is not None:
            trace.write(
                {
                    "event": "tie_break",
                    "iteration": iteration,
                    "label": label,
                    "candidate_count": len(candidates),
                    "chosen_index": idx,
                    "chosen_tactic": chosen[0],
                }
            )
        return chosen

    return breaker


def _make_agent_streams(pattern: str, length: int, label_count: int, seed: int, agents: int):
    streams = []
    for agent_id in range(agents):
        streams.append(
            make_pattern_stream(
                pattern,
                length=length,
                label_count=label_count,
                seed=seed + agent_id * 101,
            )
        )
    return streams


def _make_tactic_ranker_agent(streams, policy, trace: PatternTraceWriter | None):
    def ranker(
        tactics_with_probs: list[tuple[str, float]],
        iteration: int,
        node,
        agent_id: int,
    ) -> list[tuple[str, float]]:
        if not tactics_with_probs:
            return tactics_with_probs
        stream = streams[agent_id]
        label = stream.label_at(iteration)
        idx = policy.choose_index(label, len(tactics_with_probs))
        chosen = tactics_with_probs[idx]
        reordered = [chosen] + [
            item for i, item in enumerate(tactics_with_probs) if i != idx
        ]
        if trace is not None:
            trace.write(
                {
                    "event": "tactic_rank",
                    "iteration": iteration,
                    "label": label,
                    "candidate_count": len(tactics_with_probs),
                    "chosen_index": idx,
                    "chosen_tactic": chosen[0],
                    "agent_id": agent_id,
                    "node": {
                        "mvar_id": node.mvar_id,
                        "goal_sig": node.goal_sig,
                        "goal_sig_strict": node.goal_sig_strict,
                        "goal_type": node.goal_type,
                    },
                }
            )
        return reordered

    return ranker


def _make_tie_breaker_agent(streams, policy, trace: PatternTraceWriter | None):
    def breaker(
        candidates: list[tuple[str, Any]],
        iteration: int,
        agent_id: int,
    ) -> tuple[str, Any]:
        stream = streams[agent_id]
        label = stream.label_at(iteration)
        idx = policy.choose_index(label, len(candidates))
        chosen = candidates[idx]
        if trace is not None:
            trace.write(
                {
                    "event": "tie_break",
                    "iteration": iteration,
                    "label": label,
                    "candidate_count": len(candidates),
                    "chosen_index": idx,
                    "chosen_tactic": chosen[0],
                    "agent_id": agent_id,
                }
            )
        return chosen

    return breaker


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pattern-guided exploration experiment (tactic reorder/tie-break)."
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
    wild_group = parser.add_mutually_exclusive_group()
    wild_group.add_argument(
        "--wild-only",
        action="store_true",
        default=None,
        dest="wild_only",
    )
    wild_group.add_argument(
        "--interventions",
        action="store_false",
        default=None,
        dest="wild_only",
    )
    parser.add_argument(
        "--mcts-mode",
        choices=["centralized", "distributed"],
        default="centralized",
    )
    parser.add_argument("--mcts-agents", type=int, default=None)
    parser.add_argument("--mcts-inflight", type=int, default=None)
    parser.add_argument("--mcts-block-fraction", type=float, default=None)
    parser.add_argument("--mcts-block-duration", type=int, default=None)
    parser.add_argument("--mcts-block-seed", type=int, default=None)
    parser.add_argument("--mcts-virtual-loss", type=int, default=None)
    parser.add_argument("--mcts-depth-bias", type=float, default=None)
    parser.add_argument("--mcts-path-bias", type=float, default=None)
    parser.add_argument("--mcts-history-cache", action="store_true")

    parser.add_argument(
        "--pattern",
        choices=["structured", "shuffled", "noise"],
        default="structured",
    )
    parser.add_argument("--pattern-seed", type=int, default=0)
    parser.add_argument("--labels", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument(
        "--stream-scope",
        choices=["shared", "per-theorem"],
        default="shared",
        help="Pattern stream shared across corpus or reset per theorem",
    )
    parser.add_argument(
        "--mode",
        choices=["tactic-rank", "tie-break"],
        default="tactic-rank",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    project_path = args.project_path or os.environ.get("LEAN_PROJECT_PATH")
    if project_path is None:
        raise SystemExit("LEAN_PROJECT_PATH not set and --project-path not provided")

    budget_tiers = parse_budget(args.budget)
    total_budget = sum(budget_tiers)
    if total_budget <= 0:
        raise SystemExit("budget must be > 0")

    policy = PatternPolicy(label_count=args.labels, top_k=args.top_k)
    distributed_settings: dict[str, Any] | None = None
    if args.mcts_mode == "distributed":
        if args.mcts_agents is None or args.mcts_inflight is None:
            raise SystemExit("--mcts-agents and --mcts-inflight are required for distributed")
        block_fraction = args.mcts_block_fraction
        block_duration = args.mcts_block_duration
        block_seed = args.mcts_block_seed
        if block_fraction is None:
            if block_duration is not None or block_seed is not None:
                raise SystemExit("--mcts-block-* options require --mcts-block-fraction")
        else:
            if not (0.0 < block_fraction < 1.0):
                raise SystemExit("--mcts-block-fraction must be between 0 and 1 (exclusive)")
            if block_duration is None:
                raise SystemExit(
                    "--mcts-block-duration is required when --mcts-block-fraction is set"
                )
            if block_duration == 0:
                raise SystemExit("--mcts-block-duration must be non-zero")
            if block_seed is None:
                raise SystemExit("--mcts-block-seed is required when --mcts-block-fraction is set")
        if args.mcts_virtual_loss is None:
            virtual_loss = 0
        else:
            if args.mcts_virtual_loss < 0:
                raise SystemExit("--mcts-virtual-loss must be >= 0")
            virtual_loss = args.mcts_virtual_loss
        if args.mcts_depth_bias is None:
            depth_bias = 0.0
        else:
            if args.mcts_depth_bias < 0:
                raise SystemExit("--mcts-depth-bias must be >= 0")
            depth_bias = args.mcts_depth_bias
        if args.mcts_path_bias is None:
            path_bias = 0.0
        else:
            if args.mcts_path_bias < 0:
                raise SystemExit("--mcts-path-bias must be >= 0")
            path_bias = args.mcts_path_bias
        distributed_settings = {
            "agents": args.mcts_agents,
            "inflight": args.mcts_inflight,
            "block_fraction": block_fraction,
            "block_duration": block_duration,
            "block_seed": block_seed,
            "virtual_loss": virtual_loss,
            "depth_bias": depth_bias,
            "path_bias": path_bias,
            "history_cache": args.mcts_history_cache,
        }
    else:
        if (
            args.mcts_agents is not None
            or args.mcts_inflight is not None
            or args.mcts_block_fraction is not None
            or args.mcts_block_duration is not None
            or args.mcts_block_seed is not None
            or args.mcts_virtual_loss is not None
            or args.mcts_depth_bias is not None
            or args.mcts_path_bias is not None
            or args.mcts_history_cache
        ):
            raise SystemExit("distributed options require --mcts-mode distributed")

    logs_dir = resolve_logs_root()
    log_dir = logs_dir / args.run_id
    trace = PatternTraceWriter(log_dir / "pattern_trace.jsonl")

    def build_rankers(seed: int) -> tuple[
        Callable[[list[tuple[str, float]], int, Any], list[tuple[str, float]]] | None,
        Callable[[list[tuple[str, float]], int, Any, int], list[tuple[str, float]]] | None,
        Callable[[list[tuple[str, Any]], int], tuple[str, Any]] | None,
        Callable[[list[tuple[str, Any]], int, int], tuple[str, Any]] | None,
    ]:
        if args.mcts_mode == "distributed":
            if args.mcts_agents is None:
                raise SystemExit("pattern streams not initialized for distributed mode")
            streams = _make_agent_streams(
                args.pattern,
                length=total_budget,
                label_count=args.labels,
                seed=seed,
                agents=args.mcts_agents,
            )
            if args.mode == "tactic-rank":
                return None, _make_tactic_ranker_agent(streams, policy, trace), None, None
            return None, None, None, _make_tie_breaker_agent(streams, policy, trace)

        stream = make_pattern_stream(
            args.pattern,
            length=total_budget,
            label_count=args.labels,
            seed=seed,
        )
        if args.mode == "tactic-rank":
            return _make_tactic_ranker(stream, policy, trace), None, None, None
        return None, None, _make_tie_breaker(stream, policy, trace), None

    def stream_seed_for(theorem_idx: int) -> int:
        return args.pattern_seed + theorem_idx

    def record_stream_reset(theorem, idx: int, seed: int) -> None:
        trace.write(
            {
                "event": "stream_reset",
                "pattern": args.pattern,
                "stream_scope": args.stream_scope,
                "seed": seed,
                "theorem": theorem.name,
                "theorem_idx": idx,
            }
        )

    tactic_ranker = None
    tactic_ranker_agent = None
    tie_breaker = None
    tie_breaker_agent = None
    tactic_ranker_factory = None
    tactic_ranker_agent_factory = None
    tie_breaker_factory = None
    tie_breaker_agent_factory = None

    if args.stream_scope == "shared":
        (
            tactic_ranker,
            tactic_ranker_agent,
            tie_breaker,
            tie_breaker_agent,
        ) = build_rankers(args.pattern_seed)
    elif args.mode == "tactic-rank":
        if args.mcts_mode == "distributed":
            def make_ranker_agent(theorem, idx: int):
                seed = stream_seed_for(idx)
                record_stream_reset(theorem, idx, seed)
                return build_rankers(seed)[1]

            tactic_ranker_agent_factory = make_ranker_agent
        else:
            def make_ranker(theorem, idx: int):
                seed = stream_seed_for(idx)
                record_stream_reset(theorem, idx, seed)
                return build_rankers(seed)[0]

            tactic_ranker_factory = make_ranker
    else:
        if args.mcts_mode == "distributed":
            def make_breaker_agent(theorem, idx: int):
                seed = stream_seed_for(idx)
                record_stream_reset(theorem, idx, seed)
                return build_rankers(seed)[3]

            tie_breaker_agent_factory = make_breaker_agent
        else:
            def make_breaker(theorem, idx: int):
                seed = stream_seed_for(idx)
                record_stream_reset(theorem, idx, seed)
                return build_rankers(seed)[2]

            tie_breaker_factory = make_breaker

    wild_only = args.wild_only if args.wild_only is not None else False
    block_easy = not args.allow_easy
    try:
        asyncio.run(
            run_corpus(
                project_path=project_path,
                budget_tiers=budget_tiers,
                provider_name=args.provider,
                corpus=args.corpus,
                limit=args.limit,
                offset=args.offset,
                sample=args.sample,
                seed=args.seed,
                run_id=args.run_id,
                num_workers=args.workers,
                trace_mcts=args.trace_mcts,
                skip_interventions=wild_only,
                block_easy=block_easy,
                mcts_mode=args.mcts_mode,
                distributed_settings=distributed_settings,
                mode="pattern_guided",
                mode_defaults={},
                cli_args=vars(args),
                tactic_ranker=tactic_ranker,
                tactic_ranker_agent=tactic_ranker_agent,
                tactic_ranker_factory=tactic_ranker_factory,
                tactic_ranker_agent_factory=tactic_ranker_agent_factory,
                tie_breaker=tie_breaker,
                tie_breaker_agent=tie_breaker_agent,
                tie_breaker_factory=tie_breaker_factory,
                tie_breaker_agent_factory=tie_breaker_agent_factory,
            )
        )
    finally:
        trace.close()


if __name__ == "__main__":
    main()
