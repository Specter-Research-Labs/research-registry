from __future__ import annotations

import asyncio
import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, cast

from prover.goal_signature import GoalSignatureConfig, compute_goal_signature_strict
from prover.history import ExplorationHistory, IterationRecord, TacticAttempt, TacticOutcome
from prover.intervention import BlockedTactic
from prover.mcts import (
    BackpropStrategy,
    ExpansionPolicy,
    MCTSNode,
    MCTSTraceWriter,
    MCTSTree,
    ProgressCallback,
    _blocked_goal_sigs_for_expansion,
    _family_index,
    _get_path_to_root,
    coerce_expansion_policy,
)
from prover.providers.base import goal_signature, normalize_tactic, tactic_family

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter
    from prover.goal_cache import GoalCache
    from prover.proof import ProofGraph
    from prover.providers.base import TacticProvider


@dataclass(frozen=True)
class DistributedMCTSConfig:
    agents: int
    max_iterations: int
    max_inflight_expansions: int
    c: float
    backprop_strategy: BackpropStrategy
    virtual_loss: int
    adapter_mode: str
    block_policy: "DistributedBlockPolicy | None" = None
    reroute_policy: "DistributedReroutePolicy | None" = None
    delay_policy: "DistributedDelayPolicy | None" = None
    depth_bias: float = 0.0
    path_bias: float = 0.0
    history_cache: bool = False
    deterministic_inference: bool = False
    expansion_policy: ExpansionPolicy | str = ExpansionPolicy.ALL_SUCCESSES


@dataclass(frozen=True)
class DistributedBlockPolicy:
    fraction: float
    duration: int
    seed: int
    immovable_fraction: float | None = None
    unfreeze_after: int | None = None
    unfreeze_prob: float | None = None


@dataclass(frozen=True)
class DistributedReroutePolicy:
    max_attempts: int


@dataclass(frozen=True)
class DistributedDelayPolicy:
    probability: float
    duration: int
    seed: int


@dataclass(frozen=True)
class HistoryStats:
    visit_count: int
    success_count: int
    and_min_value: float


class AgentHistoryCache:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._cache: dict[str, HistoryStats] = {}

    def get_stats(self, node: MCTSNode) -> HistoryStats:
        if not self._enabled:
            return HistoryStats(
                visit_count=node.visit_count,
                success_count=node.success_count,
                and_min_value=node.and_min_value(),
            )
        cached = self._cache.get(node.mvar_id)
        if cached is not None:
            return cached
        fresh = HistoryStats(
            visit_count=node.visit_count,
            success_count=node.success_count,
            and_min_value=node.and_min_value(),
        )
        self._cache[node.mvar_id] = fresh
        return fresh

    def update_node(self, node: MCTSNode) -> None:
        if not self._enabled:
            return
        self._cache[node.mvar_id] = HistoryStats(
            visit_count=node.visit_count,
            success_count=node.success_count,
            and_min_value=node.and_min_value(),
        )

    def update_path(self, node: MCTSNode) -> None:
        if not self._enabled:
            return
        current: MCTSNode | None = node
        while current is not None:
            self.update_node(current)
            current = current.parent


class BlockSchedule:
    def __init__(self, policy: DistributedBlockPolicy) -> None:
        self._policy = policy
        self._rng = random.Random(policy.seed)
        self._blocked_until: dict[str, int] = {}
        self._decided: set[str] = set()
        self._blocked_hits: dict[str, int] = {}

    def _expire_if_needed(self, mvar_id: str, iteration: int) -> bool:
        until = self._blocked_until.get(mvar_id)
        if until is None:
            return False
        if until < 0 or iteration <= until:
            return True
        del self._blocked_until[mvar_id]
        self._blocked_hits.pop(mvar_id, None)
        return False

    def is_blocked(self, mvar_id: str, iteration: int) -> bool:
        if self._expire_if_needed(mvar_id, iteration):
            immovable = self._blocked_until.get(mvar_id, 0) < 0
            if self._should_unfreeze(mvar_id, immovable=immovable):
                return False
            return True
        if mvar_id in self._decided:
            return False
        self._decided.add(mvar_id)
        if self._rng.random() < self._policy.fraction:
            until = self._block_until(iteration)
            self._blocked_until[mvar_id] = until
            return True
        return False

    def _block_until(self, iteration: int) -> int:
        if self._policy.immovable_fraction is not None:
            if self._rng.random() < self._policy.immovable_fraction:
                return -1
            return iteration + self._policy.duration
        if self._policy.duration < 0:
            return -1
        return iteration + self._policy.duration

    def _should_unfreeze(self, mvar_id: str, immovable: bool) -> bool:
        if immovable:
            return False
        if self._policy.unfreeze_after is None and self._policy.unfreeze_prob is None:
            return False
        hits = self._blocked_hits.get(mvar_id, 0) + 1
        self._blocked_hits[mvar_id] = hits
        if self._policy.unfreeze_after is not None and hits >= self._policy.unfreeze_after:
            self._blocked_until.pop(mvar_id, None)
            self._blocked_hits.pop(mvar_id, None)
            return True
        if self._policy.unfreeze_prob is not None:
            if self._rng.random() < self._policy.unfreeze_prob:
                self._blocked_until.pop(mvar_id, None)
                self._blocked_hits.pop(mvar_id, None)
                return True
        return False

    def block_snapshot(self, mvar_id: str, iteration: int) -> dict[str, Any] | None:
        until = self._blocked_until.get(mvar_id)
        if until is None:
            return None
        remaining = None if until < 0 else max(0, until - iteration)
        return {
            "until": until,
            "remaining": remaining,
            "duration": self._policy.duration,
            "immovable": until < 0,
        }


class DelaySchedule:
    def __init__(self, policy: DistributedDelayPolicy) -> None:
        self._policy = policy
        self._rng = random.Random(policy.seed)
        self._delayed_until: dict[str, int] = {}

    def _expire_if_needed(self, mvar_id: str, iteration: int) -> bool:
        until = self._delayed_until.get(mvar_id)
        if until is None:
            return False
        if iteration <= until:
            return True
        del self._delayed_until[mvar_id]
        return False

    def is_delayed(self, mvar_id: str, iteration: int) -> bool:
        if self._expire_if_needed(mvar_id, iteration):
            return True
        if self._rng.random() < self._policy.probability:
            until = iteration + self._policy.duration
            self._delayed_until[mvar_id] = until
            return True
        return False

    def delay_snapshot(self, mvar_id: str, iteration: int) -> dict[str, Any] | None:
        until = self._delayed_until.get(mvar_id)
        if until is None:
            return None
        remaining = max(0, until - iteration)
        return {
            "until": until,
            "remaining": remaining,
            "duration": self._policy.duration,
        }


def _validate_config(config: DistributedMCTSConfig) -> None:
    if config.agents < 1:
        raise ValueError("distributed MCTS requires at least one agent")
    if config.max_iterations < 0:
        raise ValueError("max_iterations must be >= 0")
    if config.max_inflight_expansions < 1:
        raise ValueError("max_inflight_expansions must be >= 1")
    if config.virtual_loss < 0:
        raise ValueError("virtual_loss must be >= 0")
    if config.adapter_mode != "single":
        raise NotImplementedError("only adapter_mode='single' is supported in distributed MCTS")
    coerce_expansion_policy(config.expansion_policy)
    if config.block_policy is not None:
        if not (0.0 < config.block_policy.fraction < 1.0):
            raise ValueError("block_policy.fraction must be between 0 and 1 (exclusive)")
        if config.block_policy.duration == 0:
            raise ValueError("block_policy.duration must be non-zero")
        if config.block_policy.seed < 0:
            raise ValueError("block_policy.seed must be >= 0")
        if config.block_policy.immovable_fraction is not None:
            if not (0.0 <= config.block_policy.immovable_fraction <= 1.0):
                raise ValueError("block_policy.immovable_fraction must be between 0 and 1")
            if config.block_policy.duration < 0:
                raise ValueError(
                    "block_policy.immovable_fraction requires a positive duration"
                )
        if (
            config.block_policy.unfreeze_after is not None
            and config.block_policy.unfreeze_after < 1
        ):
            raise ValueError("block_policy.unfreeze_after must be >= 1")
        if config.block_policy.unfreeze_prob is not None:
            if not (0.0 < config.block_policy.unfreeze_prob <= 1.0):
                raise ValueError("block_policy.unfreeze_prob must be in (0, 1]")
    if config.reroute_policy is not None:
        if config.reroute_policy.max_attempts < 1:
            raise ValueError("reroute_policy.max_attempts must be >= 1")
    if config.delay_policy is not None:
        if not (0.0 < config.delay_policy.probability < 1.0):
            raise ValueError("delay_policy.probability must be between 0 and 1 (exclusive)")
        if config.delay_policy.duration < 1:
            raise ValueError("delay_policy.duration must be >= 1")
        if config.delay_policy.seed < 0:
            raise ValueError("delay_policy.seed must be >= 0")
    if config.depth_bias < 0.0:
        raise ValueError("depth_bias must be >= 0")
    if config.path_bias < 0.0:
        raise ValueError("path_bias must be >= 0")


class OrderedIterationWriter:
    def __init__(self, start_iteration: int, write_fn: Callable[[Any], None]) -> None:
        self._next_iteration = start_iteration
        self._buffer: dict[int, Any] = {}
        self._write_fn = write_fn
        self._lock = asyncio.Lock()

    async def submit(self, iteration: int, record: Any) -> None:
        async with self._lock:
            self._buffer[iteration] = record
            while self._next_iteration in self._buffer:
                item = self._buffer.pop(self._next_iteration)
                self._write_fn(item)
                self._next_iteration += 1

    async def flush(self) -> None:
        async with self._lock:
            for iteration in sorted(self._buffer):
                self._write_fn(self._buffer[iteration])
            self._buffer.clear()


def _select_available_node(
    tree: MCTSTree,
    inflight: set[str],
    blocked: set[str] | None,
    score_fn: Callable[[MCTSNode, MCTSNode], float],
    rng: random.Random | None,
    tie_breaker: Callable[[list[tuple[str, MCTSNode]], int], tuple[str, MCTSNode]] | None,
    tie_breaker_agent: Callable[
        [list[tuple[str, MCTSNode]], int, int], tuple[str, MCTSNode]
    ]
    | None,
    schedule_iteration: int,
    agent_id: int,
) -> MCTSNode | None:
    node = tree.root
    while True:
        if node.mvar_id in inflight or (blocked is not None and node.mvar_id in blocked):
            return None
        if node.is_terminal or node.is_dead or not node.children:
            return node

        candidates: list[tuple[str, MCTSNode]] = []
        best_score = float("-inf")
        has_live_child = False
        has_available_child = False

        for tactic, child_nodes in node.children.items():
            for child in child_nodes:
                if child.is_dead or child.is_terminal:
                    continue
                has_live_child = True
                if child.mvar_id in inflight or (
                    blocked is not None and child.mvar_id in blocked
                ):
                    continue
                has_available_child = True
                score = score_fn(child, node)
                if score > best_score:
                    best_score = score
                    candidates = [(tactic, child)]
                elif score == best_score:
                    candidates.append((tactic, child))

        if not has_live_child:
            node.is_dead = True
            return node

        if not has_available_child:
            return None

        if len(candidates) == 1:
            _, node = candidates[0]
            continue

        if tie_breaker_agent is not None:
            selected = tie_breaker_agent(candidates, schedule_iteration, agent_id)
            if selected not in candidates:
                raise ValueError("tie_breaker_agent returned a non-candidate")
            _, node = selected
            continue

        if tie_breaker is not None:
            selected = tie_breaker(candidates, schedule_iteration)
            if selected not in candidates:
                raise ValueError("tie_breaker returned a non-candidate")
            _, node = selected
            continue

        if rng is None:
            _, node = candidates[0]
        else:
            _, node = rng.choice(candidates)


async def distributed_mcts_search(
    theorem: str,
    adapter: LeanAdapter,
    tactic_provider: TacticProvider,
    graph: ProofGraph | None = None,
    history: ExplorationHistory | None = None,
    goal_cache: GoalCache | None = None,
    warmstart_tree: MCTSTree | None = None,
    progress_callback: ProgressCallback | None = None,
    trace: MCTSTraceWriter | None = None,
    trace_context: dict[str, Any] | None = None,
    goal_sig_config: GoalSignatureConfig | None = None,
    rng: random.Random | None = None,
    tactic_ranker: Callable[
        [list[tuple[str, float]], int, MCTSNode],
        list[tuple[str, float]],
    ]
    | None = None,
    tactic_ranker_agent: Callable[
        [list[tuple[str, float]], int, MCTSNode, int],
        list[tuple[str, float]],
    ]
    | None = None,
    tie_breaker: Callable[[list[tuple[str, MCTSNode]], int], tuple[str, MCTSNode]]
    | None = None,
    tie_breaker_agent: Callable[
        [list[tuple[str, MCTSNode]], int, int], tuple[str, MCTSNode]
    ]
    | None = None,
    config: DistributedMCTSConfig | None = None,
) -> MCTSTree:
    import logging

    logger = logging.getLogger(__name__)

    if goal_sig_config is None:
        raise ValueError("goal_sig_config is required")
    if config is None:
        raise ValueError("distributed MCTS config is required")

    _validate_config(config)
    expansion_policy = coerce_expansion_policy(config.expansion_policy)

    if warmstart_tree is not None:
        tree = warmstart_tree
        start_iteration = tree.root.visit_count
        logger.debug("Warmstarting distributed MCTS from iteration %s", start_iteration)
        if goal_cache is not None and tree.root.goal_sig and tree.root.goal_features is None:
            tree.root.goal_features = goal_cache.get_features(tree.root.goal_sig).tolist()
    else:
        initial_mvars = await adapter.initialize(theorem)
        if not initial_mvars:
            raise ValueError("No initial goals from theorem")

        root_mvar = initial_mvars[0]
        root_goal = adapter.get_goal(root_mvar)
        if root_goal is None:
            raise ValueError(f"No goal found for initial mvar_id: {root_mvar}")
        root_goal_type = root_goal.type
        root_hyp_types = [h.type for h in root_goal.hypotheses]
        root_hyp_exprs = [h.type_expr for h in root_goal.hypotheses]
        if goal_cache is None:
            root_goal_sig = goal_signature(root_goal, goal_sig_config)
        else:
            root_goal_sig = goal_cache.add_goal(
                mvar_id=root_mvar,
                type_str=root_goal.type,
                type_expr=root_goal.type_expr,
                hyp_types=root_hyp_types,
                hyp_exprs=root_hyp_exprs,
            )
        root_goal_sig_strict = compute_goal_signature_strict(
            type_str=root_goal.type,
            type_expr=root_goal.type_expr,
            hyp_types=root_hyp_types,
            hyp_exprs=root_hyp_exprs,
            config=goal_sig_config,
        )
        tree = MCTSTree.create(
            root_mvar,
            root_goal_type,
            goal_sig=root_goal_sig,
            goal_sig_strict=root_goal_sig_strict,
        )
        if goal_cache is not None:
            tree.root.goal_features = goal_cache.get_features(root_goal_sig).tolist()

        if graph is not None:
            graph.add_node(root_mvar, goal_type=root_goal_type, depth=0, goal_sig=root_goal_sig)
        start_iteration = 0

    if config.max_iterations == 0:
        return tree

    iteration_limit = start_iteration + config.max_iterations
    iteration_counter = start_iteration
    last_tactic: str | None = None
    last_goal_sig: str | None = None

    tree_lock = asyncio.Lock()
    expansion_lock = asyncio.Lock()
    progress_lock = asyncio.Lock()
    trace_lock = asyncio.Lock()
    inflight: set[str] = set()
    inflight_counts: dict[str, int] = {}
    stop_event = asyncio.Event()
    block_schedule = BlockSchedule(config.block_policy) if config.block_policy else None
    delay_schedule = DelaySchedule(config.delay_policy) if config.delay_policy else None
    history_caches = {
        agent_id: AgentHistoryCache(config.history_cache) for agent_id in range(config.agents)
    }
    last_paths: dict[int, list[str]] = {}
    agent_iterations: dict[int, int] = {agent_id: 0 for agent_id in range(config.agents)}
    history_writer = (
        OrderedIterationWriter(start_iteration, history.record_iteration)
        if history is not None
        else None
    )
    trace_writer = (
        OrderedIterationWriter(start_iteration, trace.write)
        if trace is not None
        else None
    )

    def serialize_attempts(items: list[TacticAttempt]) -> list[dict[str, Any]]:
        return [
            {
                "tactic": a.tactic,
                "outcome": a.outcome.value,
                "child_mvar_ids": a.child_mvar_ids,
                "timestamp_ms": a.timestamp_ms,
                "tactic_norm": a.tactic_norm,
                "goal_sig": a.goal_sig,
                "goal_sig_strict": a.goal_sig_strict,
                "goal_type": a.goal_type,
                "peg_id": a.peg_id,
                "peg_kind": a.peg_kind,
                "block_reason": a.block_reason,
                "provider_id": a.provider_id,
            }
            for a in items
        ]

    def node_snapshot(current: MCTSNode) -> dict[str, Any]:
        return {
            "mvar_id": current.mvar_id,
            "goal_type": current.goal_type,
            "goal_sig": current.goal_sig,
            "goal_sig_strict": current.goal_sig_strict,
            "visit_count": current.visit_count,
            "success_count": current.success_count,
            "is_terminal": current.is_terminal,
            "is_dead": current.is_dead,
            "depth": current.depth,
        }

    def tree_snapshot(solved: bool, inflight_count: int | None = None) -> dict[str, Any]:
        max_depth = max((n.depth for n in tree.nodes_by_mvar.values()), default=0)
        snapshot = {
            "nodes": len(tree.nodes_by_mvar),
            "expansions": tree.expansion_count,
            "max_depth": max_depth,
            "solved": solved,
            "aborted": tree.aborted,
        }
        if inflight_count is not None:
            snapshot["inflight"] = inflight_count
        return snapshot

    def trace_iteration_record(
        iteration: int,
        reason: str,
        agent_id: int | None,
        current_node: dict[str, Any],
        selected_path: list[str],
        attempts: list[TacticAttempt],
        tactics_with_probs: list[tuple[str, float]],
        expanded: bool | None,
        terminal_reached: bool,
        backprop_success: bool,
        tree_state: dict[str, Any],
        block_info: dict[str, Any] | None = None,
        delay_info: dict[str, Any] | None = None,
        reroute_info: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {}
        if trace_context:
            record.update(trace_context)
        record.update(
            {
                "event": "iteration",
                "iteration": iteration,
                "reason": reason,
                "agent_id": agent_id,
                "selected_path": selected_path,
                "node": current_node,
                "tactics": [
                    {"tactic": tactic, "score": float(score)}
                    for tactic, score in tactics_with_probs
                ],
                "attempts": serialize_attempts(attempts),
                "expanded": expanded,
                "terminal_reached": terminal_reached,
                "backprop_success": backprop_success,
                "tree": tree_state,
            }
        )
        if block_info is not None:
            record["block"] = block_info
        if delay_info is not None:
            record["delay"] = delay_info
        if reroute_info is not None:
            record["reroute"] = reroute_info
        return record

    async def next_iteration() -> int | None:
        nonlocal iteration_counter
        async with tree_lock:
            if iteration_counter >= iteration_limit:
                return None
            value = iteration_counter
            iteration_counter += 1
            return value

    async def check_abort(iteration: int) -> bool:
        if progress_callback is None:
            return False
        async with tree_lock:
            nodes = list(tree.nodes_by_mvar.values())
            leaves = sum(1 for n in nodes if not n.children and not n.is_terminal)
            max_depth = max((n.depth for n in nodes), default=0)
            last_tactic_local = last_tactic
            last_goal_sig_local = last_goal_sig
        async with progress_lock:
            should_abort = progress_callback(
                iteration,
                iteration_limit,
                len(nodes),
                leaves,
                max_depth,
                last_tactic_local,
                last_goal_sig_local,
            )
        if should_abort:
            async with tree_lock:
                tree.aborted = True
                snapshot = tree_snapshot(tree.is_solved(), inflight_count=len(inflight))
            if trace is not None:
                record: dict[str, Any] = {}
                if trace_context:
                    record.update(trace_context)
                record.update(
                    {
                        "event": "abort",
                        "iteration": iteration,
                        "tree": snapshot,
                    }
                )
                async with trace_lock:
                    trace.write(record)
            stop_event.set()
        return should_abort

    def _effective_counts(
        node: MCTSNode,
        parent: MCTSNode,
        cache: AgentHistoryCache,
    ) -> tuple[HistoryStats, int]:
        stats = cache.get_stats(node)
        parent_stats = cache.get_stats(parent)
        parent_visit = parent_stats.visit_count
        if config.virtual_loss > 0:
            parent_visit += inflight_counts.get(parent.mvar_id, 0) * config.virtual_loss
        return stats, parent_visit

    def _score_node(
        node: MCTSNode,
        parent: MCTSNode,
        cache: AgentHistoryCache,
        preferred_path: list[str] | None,
    ) -> float:
        stats, parent_visit = _effective_counts(node, parent, cache)
        inflight_weight = (
            inflight_counts.get(node.mvar_id, 0) * config.virtual_loss
            if config.virtual_loss > 0
            else 0
        )
        if node.visit_count == 0 and inflight_weight == 0:
            base = float("inf")
        else:
            effective_visits = stats.visit_count + inflight_weight
            if effective_visits <= 0:
                effective_visits = 1
            if config.backprop_strategy == BackpropStrategy.AND_MIN:
                exploitation = stats.and_min_value
            else:
                effective_success = stats.success_count - inflight_weight
                exploitation = effective_success / effective_visits
            if parent_visit <= 1:
                exploration = 0.0
            else:
                exploration = config.c * math.sqrt(math.log(parent_visit) / effective_visits)
            base = exploitation + exploration
        if config.depth_bias:
            base += config.depth_bias * node.depth
        if config.path_bias and preferred_path is not None:
            if node.mvar_id in preferred_path:
                base += config.path_bias
        return base

    def _bump_inflight(path: list[str], delta: int) -> None:
        for mvar_id in path:
            current = inflight_counts.get(mvar_id, 0) + delta
            if current <= 0:
                inflight_counts.pop(mvar_id, None)
            else:
                inflight_counts[mvar_id] = current

    async def reserve_node(
        iteration: int,
        schedule_iteration: int,
        agent_id: int,
    ) -> tuple[
        MCTSNode | None,
        bool,
        dict[str, Any] | None,
        dict[str, Any] | None,
        list[dict[str, Any]] | None,
    ]:
        reroute_info: list[dict[str, Any]] = []
        skipped: set[str] = set()
        attempts = 0
        max_attempts = config.reroute_policy.max_attempts if config.reroute_policy else 0
        fallback_node: MCTSNode | None = None
        fallback_block_info: dict[str, Any] | None = None
        fallback_delay_info: dict[str, Any] | None = None
        cache = history_caches[agent_id]
        preferred_path = last_paths.get(agent_id)
        while True:
            async with tree_lock:
                if tree.is_solved() or tree.root.is_dead:
                    stop_event.set()
                    return None, False, None, None, None
                if len(inflight) >= config.max_inflight_expansions:
                    return None, False, None, None, None
                def score_fn(child: MCTSNode, parent: MCTSNode) -> float:
                    return _score_node(child, parent, cache, preferred_path)
                node = _select_available_node(
                    tree,
                    inflight,
                    skipped if skipped else None,
                    score_fn,
                    rng,
                    tie_breaker,
                    tie_breaker_agent,
                    schedule_iteration,
                    agent_id,
                )
                if node is None:
                    if fallback_node is not None:
                        return (
                            fallback_node,
                            False,
                            fallback_block_info,
                            fallback_delay_info,
                            reroute_info or None,
                        )
                    return None, False, None, None, None

                if block_schedule is not None and block_schedule.is_blocked(
                    node.mvar_id, iteration
                ):
                    block_info = block_schedule.block_snapshot(node.mvar_id, iteration)
                    if attempts < max_attempts:
                        fallback_node = node
                        fallback_block_info = block_info
                        fallback_delay_info = None
                        reroute_info.append(
                            {
                                "mvar_id": node.mvar_id,
                                "reason": "blocked",
                                "block": block_info,
                            }
                        )
                        skipped.add(node.mvar_id)
                        attempts += 1
                        continue
                    return node, False, block_info, None, reroute_info or None

                if delay_schedule is not None and delay_schedule.is_delayed(
                    node.mvar_id, iteration
                ):
                    delay_info = delay_schedule.delay_snapshot(node.mvar_id, iteration)
                    if attempts < max_attempts:
                        fallback_node = node
                        fallback_block_info = None
                        fallback_delay_info = delay_info
                        reroute_info.append(
                            {
                                "mvar_id": node.mvar_id,
                                "reason": "delayed",
                                "delay": delay_info,
                            }
                        )
                        skipped.add(node.mvar_id)
                        attempts += 1
                        continue
                    return node, False, None, delay_info, reroute_info or None

                inflight.add(node.mvar_id)
                selected_path = _get_path_to_root(node)
                _bump_inflight(selected_path, 1)
                last_paths[agent_id] = selected_path
                return node, True, None, None, reroute_info or None

    async def record_iteration(
        iteration: int,
        reason: str,
        agent_id: int | None,
        node: MCTSNode,
        selected_path: list[str],
        attempts: list[TacticAttempt],
        tactics_with_probs: list[tuple[str, float]],
        expanded: bool | None,
        terminal_reached: bool,
        backprop_success: bool,
        solved: bool,
        block_info: dict[str, Any] | None = None,
        delay_info: dict[str, Any] | None = None,
        reroute_info: list[dict[str, Any]] | None = None,
    ) -> None:
        async with tree_lock:
            node_state = node_snapshot(node)
            tree_state = tree_snapshot(solved, inflight_count=len(inflight))
        if history_writer is not None:
            await history_writer.submit(
                iteration,
                IterationRecord(
                    iteration=iteration,
                    selected_path=selected_path,
                    attempts=attempts,
                    backprop_success=backprop_success,
                    terminal_reached=terminal_reached,
                ),
            )
        if trace_writer is not None:
            await trace_writer.submit(
                iteration,
                trace_iteration_record(
                    iteration,
                    reason,
                    agent_id,
                    node_state,
                    selected_path,
                    attempts,
                    tactics_with_probs,
                    expanded,
                    terminal_reached,
                    backprop_success,
                    tree_state,
                    block_info,
                    delay_info,
                    reroute_info,
                ),
            )

    async def agent_loop(agent_id: int) -> None:
        nonlocal last_tactic, last_goal_sig
        while not stop_event.is_set():
            iteration = await next_iteration()
            if iteration is None:
                return
            schedule_iteration = agent_iterations[agent_id]
            agent_iterations[agent_id] += 1
            if iteration % 10 == 0:
                async with tree_lock:
                    n_nodes = len(tree.nodes_by_mvar)
                logger.debug(
                    "distributed MCTS iteration %s/%s, nodes=%s",
                    iteration,
                    iteration_limit,
                    n_nodes,
                )

            if await check_abort(iteration):
                empty_attempts: list[TacticAttempt] = []
                async with tree_lock:
                    solved_now = tree.is_solved()
                await record_iteration(
                    iteration,
                    "abort",
                    agent_id,
                    tree.root,
                    [],
                    empty_attempts,
                    [],
                    None,
                    False,
                    False,
                    solved_now,
                )
                return

            node: MCTSNode | None = None
            reserved = False
            block_info: dict[str, Any] | None = None
            delay_info: dict[str, Any] | None = None
            reroute_info: list[dict[str, Any]] | None = None
            while node is None and not stop_event.is_set():
                node, reserved, block_info, delay_info, reroute_info = await reserve_node(
                    iteration,
                    schedule_iteration,
                    agent_id,
                )
                if node is None:
                    await asyncio.sleep(0.002)

            if node is None:
                return

            async with tree_lock:
                path_for_inflight = _get_path_to_root(node)
                selected_path = path_for_inflight if history is not None else []

            if not reserved:
                async with tree_lock:
                    solved_now = tree.is_solved()
                reason = "delayed" if delay_info is not None else "blocked"
                await record_iteration(
                    iteration,
                    reason,
                    agent_id,
                    node,
                    selected_path,
                    [],
                    [],
                    None,
                    False,
                    False,
                    solved_now,
                    block_info,
                    delay_info,
                    reroute_info,
                )
                continue

            attempts: list[TacticAttempt] = []
            tactics_with_probs: list[tuple[str, float]] = []
            expanded: bool | None = None
            terminal_reached = False
            backprop_success = False
            solved_now = False
            reason = "expanded"

            try:
                async with tree_lock:
                    if node.is_terminal:
                        terminal_reached = True
                        backprop_success = True
                        tree.backpropagate(node, success=True)
                        solved_now = tree.is_solved()
                        if solved_now:
                            stop_event.set()
                        reason = "terminal_node"
                    elif node.is_dead:
                        tree.backpropagate(node, success=False)
                        solved_now = tree.is_solved()
                        if tree.root.is_dead:
                            stop_event.set()
                        reason = "dead_node"

                if reason in ("terminal_node", "dead_node"):
                    await record_iteration(
                        iteration,
                        reason,
                        agent_id,
                        node,
                        selected_path,
                        attempts,
                        tactics_with_probs,
                        expanded,
                        terminal_reached,
                        backprop_success,
                        solved_now,
                    )
                    if reason == "dead_node":
                        async with tree_lock:
                            if tree.root.is_dead:
                                stop_event.set()
                    if solved_now:
                        stop_event.set()
                    continue

                async with expansion_lock:
                    goal = adapter.get_goal(node.mvar_id)
                    if goal is None:
                        async with tree_lock:
                            node.is_dead = True
                            tree.backpropagate(node, success=False)
                            solved_now = tree.is_solved()
                            if tree.root.is_dead:
                                stop_event.set()
                        reason = "no_goal"
                        await record_iteration(
                            iteration,
                            reason,
                            agent_id,
                            node,
                            selected_path,
                            attempts,
                            tactics_with_probs,
                            expanded,
                            terminal_reached,
                            backprop_success,
                            solved_now,
                        )
                        if solved_now:
                            stop_event.set()
                        continue

                    goal_sig = node.goal_sig
                    goal_sig_strict = node.goal_sig_strict
                    if not goal_sig or not goal_sig_strict or node.goal_features is None:
                        hyp_types = [h.type for h in goal.hypotheses]
                        hyp_exprs = [h.type_expr for h in goal.hypotheses]
                        if not goal_sig:
                            if goal_cache is None:
                                goal_sig = goal_signature(goal, goal_sig_config)
                            else:
                                goal_sig = goal_cache.add_goal(
                                    mvar_id=node.mvar_id,
                                    type_str=goal.type,
                                    type_expr=goal.type_expr,
                                    hyp_types=hyp_types,
                                    hyp_exprs=hyp_exprs,
                                )
                        if not goal_sig_strict:
                            goal_sig_strict = compute_goal_signature_strict(
                                type_str=goal.type,
                                type_expr=goal.type_expr,
                                hyp_types=hyp_types,
                                hyp_exprs=hyp_exprs,
                                config=goal_sig_config,
                            )
                        async with tree_lock:
                            node.goal_sig = goal_sig
                            node.goal_sig_strict = goal_sig_strict
                            if node.goal_features is None and goal_sig and goal_cache is not None:
                                node.goal_features = goal_cache.get_features(goal_sig).tolist()

                    async with tree_lock:
                        last_goal_sig = goal_sig

                    provider_id = getattr(tactic_provider, "provider_id", None)
                    record_attempt = getattr(tactic_provider, "record_attempt", None)
                    tactics_with_probs = await tactic_provider.suggest_tactics_with_probs_async(
                        goal, node.mvar_id, adapter
                    )
                    tactics_with_probs.sort(key=lambda x: x[1], reverse=True)
                    if tactic_ranker_agent is not None:
                        ranked = tactic_ranker_agent(
                            tactics_with_probs, schedule_iteration, node, agent_id
                        )
                        if len(ranked) != len(tactics_with_probs):
                            raise ValueError(
                                "tactic_ranker_agent must return the same number of tactics"
                            )
                        if Counter(ranked) != Counter(tactics_with_probs):
                            raise ValueError(
                                "tactic_ranker_agent must return the same tactics with new ordering"
                            )
                        tactics_with_probs = ranked
                    elif tactic_ranker is not None:
                        ranked = tactic_ranker(tactics_with_probs, schedule_iteration, node)
                        if len(ranked) != len(tactics_with_probs):
                            raise ValueError(
                                "tactic_ranker must return the same number of tactics"
                            )
                        if Counter(ranked) != Counter(tactics_with_probs):
                            raise ValueError(
                                "tactic_ranker must return the same tactics with new ordering"
                            )
                        tactics_with_probs = ranked
                    tactics = [t for t, _ in tactics_with_probs]

                    blocked_list: list[BlockedTactic | str] = getattr(
                        tactic_provider, "last_blocked", []
                    )
                    if history is not None and blocked_list:
                        for blocked_tactic in blocked_list:
                            if isinstance(blocked_tactic, BlockedTactic):
                                attempts.append(
                                    TacticAttempt(
                                        iteration=iteration,
                                        node_mvar_id=node.mvar_id,
                                        tactic=blocked_tactic.tactic,
                                        outcome=TacticOutcome.BLOCKED,
                                        child_mvar_ids=[],
                                        timestamp_ms=history.elapsed_ms(),
                                        tactic_norm=blocked_tactic.tactic_norm,
                                        goal_sig=blocked_tactic.goal_sig,
                                        goal_sig_strict=goal_sig_strict,
                                        goal_type=node.goal_type,
                                        peg_id=blocked_tactic.peg_id,
                                        peg_kind=blocked_tactic.peg_kind,
                                        block_reason=blocked_tactic.block_reason,
                                        provider_id=blocked_tactic.provider_id,
                                    )
                                )
                            else:
                                attempts.append(
                                    TacticAttempt(
                                        iteration=iteration,
                                        node_mvar_id=node.mvar_id,
                                        tactic=blocked_tactic,
                                        outcome=TacticOutcome.BLOCKED,
                                        child_mvar_ids=[],
                                        timestamp_ms=history.elapsed_ms(),
                                        tactic_norm=normalize_tactic(blocked_tactic),
                                        goal_sig=goal_sig,
                                        goal_sig_strict=goal_sig_strict,
                                        goal_type=node.goal_type,
                                        provider_id=provider_id,
                                    )
                                )

                    expanded = False
                    pending_expansions = []

                    for tactic in tactics:
                        async with tree_lock:
                            if tactic in node.children:
                                continue

                        preview = await adapter.preview_tactic(node.mvar_id, tactic)
                        if record_attempt is not None:
                            record_attempt(
                                tactic=tactic, goal_sig=goal_sig, budget_key=node.mvar_id
                            )

                        if preview is None:
                            tactic_norm = normalize_tactic(tactic)
                            if goal_cache is not None:
                                fam = tactic_family(tactic_norm)
                                goal_cache.record_outcome(
                                    node.mvar_id, _family_index(fam), success=False
                                )
                            if history is not None:
                                attempts.append(
                                    TacticAttempt(
                                        iteration=iteration,
                                        node_mvar_id=node.mvar_id,
                                        tactic=tactic,
                                        outcome=TacticOutcome.FAILURE,
                                        child_mvar_ids=[],
                                        timestamp_ms=history.elapsed_ms(),
                                        tactic_norm=tactic_norm,
                                        goal_sig=goal_sig,
                                        goal_sig_strict=goal_sig_strict,
                                        goal_type=node.goal_type,
                                        provider_id=provider_id,
                                    )
                                )
                            continue

                        tactic_norm = normalize_tactic(tactic)

                        if len(preview.child_mvar_ids) == 0:
                            if history is not None:
                                attempts.append(
                                    TacticAttempt(
                                        iteration=iteration,
                                        node_mvar_id=node.mvar_id,
                                        tactic=tactic,
                                        outcome=TacticOutcome.SUCCESS,
                                        child_mvar_ids=[],
                                        timestamp_ms=history.elapsed_ms(),
                                        tactic_norm=tactic_norm,
                                        goal_sig=goal_sig,
                                        goal_sig_strict=goal_sig_strict,
                                        goal_type=node.goal_type,
                                        provider_id=provider_id,
                                    )
                                )
                            pending_expansions.append(
                                (tactic, tactic_norm, preview, [], [], [], [], True)
                            )
                            if expansion_policy == ExpansionPolicy.FIRST_SUCCESS:
                                break
                            continue

                        novel_mvars: list[str] = []
                        novel_goal_types: list[str] = []
                        novel_goal_sigs: list[str] = []
                        novel_goal_sigs_strict: list[str] = []
                        blocked_goal_sigs = _blocked_goal_sigs_for_expansion(node)

                        for state_id, child_goal in zip(
                            preview.child_mvar_ids, preview.child_goals
                        ):
                            if child_goal.mvar_id is None:
                                raise ValueError(
                                    f"Child goal has no mvar_id: {child_goal.type}"
                                )
                            hyp_types = [h.type for h in child_goal.hypotheses]
                            hyp_exprs = [h.type_expr for h in child_goal.hypotheses]
                            if goal_cache is None:
                                sig = goal_signature(child_goal, goal_sig_config)
                            else:
                                sig = goal_cache.add_goal(
                                    mvar_id=state_id,
                                    type_str=child_goal.type,
                                    type_expr=child_goal.type_expr,
                                    hyp_types=hyp_types,
                                    hyp_exprs=hyp_exprs,
                                )
                            sig_strict = compute_goal_signature_strict(
                                type_str=child_goal.type,
                                type_expr=child_goal.type_expr,
                                hyp_types=hyp_types,
                                hyp_exprs=hyp_exprs,
                                config=goal_sig_config,
                            )
                            if sig in blocked_goal_sigs:
                                continue
                            novel_mvars.append(state_id)
                            novel_goal_types.append(child_goal.type)
                            novel_goal_sigs.append(sig)
                            novel_goal_sigs_strict.append(sig_strict)
                            blocked_goal_sigs.add(sig)

                        if not novel_mvars:
                            if history is not None:
                                attempts.append(
                                    TacticAttempt(
                                        iteration=iteration,
                                        node_mvar_id=node.mvar_id,
                                        tactic=tactic,
                                        outcome=TacticOutcome.SUCCESS,
                                        child_mvar_ids=list(preview.child_mvar_ids),
                                        timestamp_ms=history.elapsed_ms(),
                                        tactic_norm=tactic_norm,
                                        goal_sig=goal_sig,
                                        goal_sig_strict=goal_sig_strict,
                                        goal_type=node.goal_type,
                                        provider_id=provider_id,
                                    )
                                )
                            continue

                        if history is not None:
                            attempts.append(
                                TacticAttempt(
                                    iteration=iteration,
                                    node_mvar_id=node.mvar_id,
                                    tactic=tactic,
                                    outcome=TacticOutcome.SUCCESS,
                                    child_mvar_ids=list(novel_mvars),
                                    timestamp_ms=history.elapsed_ms(),
                                    tactic_norm=tactic_norm,
                                    goal_sig=goal_sig,
                                    goal_sig_strict=goal_sig_strict,
                                    goal_type=node.goal_type,
                                    provider_id=provider_id,
                                )
                            )

                        pending_expansions.append(
                            (
                                tactic,
                                tactic_norm,
                                preview,
                                novel_mvars,
                                novel_goal_types,
                                novel_goal_sigs,
                                novel_goal_sigs_strict,
                                False,
                            )
                        )
                        if expansion_policy == ExpansionPolicy.FIRST_SUCCESS:
                            break

                    for (
                        tactic,
                        tactic_norm,
                        preview,
                        novel_mvars,
                        novel_goal_types,
                        novel_goal_sigs,
                        novel_goal_sigs_strict,
                        closes_goal,
                    ) in pending_expansions:
                        adapter.commit_tactic(preview)
                        expanded = True
                        reason = "expanded"
                        async with tree_lock:
                            last_tactic = tactic
                        if closes_goal:
                            terminal_reached = True
                        if goal_cache is not None:
                            fam = tactic_family(tactic_norm)
                            goal_cache.record_outcome(
                                node.mvar_id, _family_index(fam), success=True
                            )

                        async with tree_lock:
                            tree.expand(
                                node,
                                tactic,
                                novel_mvars,
                                novel_goal_types,
                                novel_goal_sigs,
                                novel_goal_sigs_strict,
                            )
                            if graph is not None:
                                graph.add_expansion(
                                    node.mvar_id,
                                    tactic,
                                    novel_mvars,
                                    novel_goal_types,
                                    cast(list[str | None], novel_goal_sigs),
                                    action_attrs=preview.action_metadata(
                                        expanded_child_count=len(novel_mvars)
                                    ),
                                )

                    if expanded:
                        backprop_success = True
                        async with tree_lock:
                            tree.backpropagate(node, success=True)
                            solved_now = tree.is_solved()
                            if solved_now:
                                stop_event.set()

                    if expanded is False:
                        async with tree_lock:
                            node.is_dead = True
                            tree.backpropagate(node, success=False)
                            solved_now = tree.is_solved()
                            if tree.root.is_dead:
                                stop_event.set()
                        reason = "no_expansion"

                await record_iteration(
                    iteration,
                    reason,
                    agent_id,
                    node,
                    selected_path,
                    attempts,
                    tactics_with_probs,
                    expanded,
                    terminal_reached,
                    backprop_success,
                    solved_now,
                    reroute_info=reroute_info,
                )

                if solved_now:
                    stop_event.set()
            finally:
                async with tree_lock:
                    inflight.discard(node.mvar_id)
                    _bump_inflight(path_for_inflight, -1)
                history_caches[agent_id].update_path(node)

    tasks = [asyncio.create_task(agent_loop(agent_id)) for agent_id in range(config.agents)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if history_writer is not None:
            await history_writer.flush()
        if trace_writer is not None:
            await trace_writer.flush()

    return tree
