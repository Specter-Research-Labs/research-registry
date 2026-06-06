from __future__ import annotations

import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from prover.goal_signature import GoalSignatureConfig, compute_goal_signature_strict
from prover.history import (
    ExplorationHistory,
    IterationRecord,
    TacticAttempt,
    TacticOutcome,
)
from prover.intervention import BlockedTactic
from prover.providers.base import goal_signature, normalize_tactic, tactic_family

if TYPE_CHECKING:
    from prover.adapters.lean import LeanAdapter
    from prover.goal_cache import GoalCache
    from prover.proof import ProofGraph
    from prover.providers.base import TacticProvider

TACTIC_FAMILIES = [
    "simplify", "rewrite", "intro", "split", "cases",
    "closer", "contradiction", "arith", "automation", "other",
]


def _family_index(fam: str) -> int:
    try:
        return TACTIC_FAMILIES.index(fam)
    except ValueError:
        return len(TACTIC_FAMILIES) - 1


def _get_goal_sigs(
    goal,
    mvar_id: str,
    cache: GoalCache | None,
    sig_config: GoalSignatureConfig,
) -> tuple[str, str]:
    hyp_types = [h.type for h in goal.hypotheses]
    hyp_exprs = [h.type_expr for h in goal.hypotheses]

    if cache is None:
        coarse = goal_signature(goal, sig_config)
    else:
        coarse = cache.add_goal(
            mvar_id=mvar_id,
            type_str=goal.type,
            type_expr=goal.type_expr,
            hyp_types=hyp_types,
            hyp_exprs=hyp_exprs,
        )

    strict = compute_goal_signature_strict(
        type_str=goal.type,
        type_expr=goal.type_expr,
        hyp_types=hyp_types,
        hyp_exprs=hyp_exprs,
        config=sig_config,
    )
    return coarse, strict


class BackpropStrategy(Enum):
    UNIFORM = "uniform"
    AND_MIN = "and_min"


class SearchPolicy(Enum):
    UCB1 = "ucb1"
    BLIND_UNIFORM = "blind_uniform"


class ExpansionPolicy(Enum):
    FIRST_SUCCESS = "first-success"
    ALL_SUCCESSES = "all-successes"


def coerce_expansion_policy(value: ExpansionPolicy | str) -> ExpansionPolicy:
    if isinstance(value, ExpansionPolicy):
        return value
    try:
        return ExpansionPolicy(value)
    except ValueError as exc:
        valid = ", ".join(policy.value for policy in ExpansionPolicy)
        raise ValueError(f"Unknown expansion_policy: {value!r}. Valid values: {valid}") from exc


@dataclass
class MCTSNode:
    mvar_id: str
    goal_type: str
    goal_sig: str = ""
    goal_sig_strict: str = ""
    goal_features: list[float] | None = None
    parent: MCTSNode | None = None
    children: dict[str, list[MCTSNode]] = field(default_factory=dict)
    visit_count: int = 0
    success_count: int = 0
    is_terminal: bool = False
    is_dead: bool = False
    dead_reason: str | None = None
    depth: int = 0
    expansion_order: int = 0

    def value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.success_count / self.visit_count

    def and_min_value(self) -> float:
        if self.is_terminal:
            return 1.0
        if self.is_dead:
            return 0.0
        if not self.children:
            return self.value()

        best_tactic_value = 0.0
        for tactic, child_nodes in self.children.items():
            if not child_nodes:
                continue
            child_values = [c.and_min_value() for c in child_nodes]
            tactic_value = min(child_values) if child_values else 0.0
            best_tactic_value = max(best_tactic_value, tactic_value)
        return best_tactic_value

    def ucb1(
        self, c: float = math.sqrt(2), strategy: BackpropStrategy = BackpropStrategy.UNIFORM
    ) -> float:
        if self.visit_count == 0:
            return float("inf")
        if self.parent is None:
            return 0.0
        if strategy == BackpropStrategy.AND_MIN:
            exploitation = self.and_min_value()
        else:
            exploitation = self.success_count / self.visit_count
        exploration = c * math.sqrt(math.log(self.parent.visit_count) / self.visit_count)
        return exploitation + exploration

    def best_child_by_ucb1(
        self,
        c: float = math.sqrt(2),
        strategy: BackpropStrategy = BackpropStrategy.UNIFORM,
        rng: random.Random | None = None,
        tie_breaker: Callable[[list[tuple[str, "MCTSNode"]]], tuple[str, "MCTSNode"]] | None = None,
    ) -> tuple[str, MCTSNode] | None:
        if not self.children:
            return None

        candidates: list[tuple[str, MCTSNode]] = []
        best_ucb = float("-inf")

        for tactic, child_nodes in self.children.items():
            for node in child_nodes:
                if node.is_dead or node.is_terminal:
                    continue
                ucb = node.ucb1(c, strategy)
                if ucb > best_ucb:
                    best_ucb = ucb
                    candidates = [(tactic, node)]
                elif ucb == best_ucb:
                    candidates.append((tactic, node))

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if tie_breaker is not None:
            selected = tie_breaker(candidates)
            if selected not in candidates:
                raise ValueError("tie_breaker returned a non-candidate")
            return selected
        if rng is None:
            return candidates[0]
        return rng.choice(candidates)

    def best_child_by_visits(self) -> tuple[str, MCTSNode] | None:
        if not self.children:
            return None

        best: tuple[str, MCTSNode] | None = None
        best_visits = -1

        for tactic, child_nodes in self.children.items():
            for node in child_nodes:
                if node.visit_count > best_visits:
                    best_visits = node.visit_count
                    best = (tactic, node)

        return best

    def serialize(self) -> dict:
        return {
            "mvar_id": self.mvar_id,
            "goal_type": self.goal_type,
            "goal_sig": self.goal_sig,
            "goal_sig_strict": self.goal_sig_strict,
            "visit_count": self.visit_count,
            "success_count": self.success_count,
            "is_terminal": self.is_terminal,
            "is_dead": self.is_dead,
            "depth": self.depth,
            "expansion_order": self.expansion_order,
            "children": {
                tactic: [child.mvar_id for child in children]
                for tactic, children in self.children.items()
            },
        }


@dataclass
class MCTSTree:
    root: MCTSNode
    nodes_by_mvar: dict[str, MCTSNode] = field(default_factory=dict)
    expansion_count: int = 0
    aborted: bool = False

    @classmethod
    def create(
        cls,
        root_mvar_id: str,
        goal_type: str,
        goal_sig: str = "",
        goal_sig_strict: str = "",
    ) -> MCTSTree:
        root = MCTSNode(
            mvar_id=root_mvar_id,
            goal_type=goal_type,
            goal_sig=goal_sig,
            goal_sig_strict=goal_sig_strict,
            depth=0,
        )
        tree = cls(root=root)
        tree.nodes_by_mvar[root_mvar_id] = root
        return tree

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> MCTSTree:
        if not isinstance(data, dict):
            raise ValueError("MCTSTree payload must be an object")
        nodes_payload = data.get("nodes")
        root_mvar_id = data.get("root_mvar_id")
        if not isinstance(nodes_payload, dict):
            raise ValueError("MCTSTree payload missing nodes")
        if not isinstance(root_mvar_id, str) or root_mvar_id not in nodes_payload:
            raise ValueError("MCTSTree payload missing root node")

        nodes_by_mvar: dict[str, MCTSNode] = {}
        for mvar_id, node_data in nodes_payload.items():
            if not isinstance(node_data, dict):
                raise ValueError(f"MCTSTree node payload must be an object: {mvar_id}")
            nodes_by_mvar[str(mvar_id)] = MCTSNode(
                mvar_id=str(node_data.get("mvar_id", mvar_id)),
                goal_type=str(node_data.get("goal_type", "")),
                goal_sig=str(node_data.get("goal_sig", "")),
                goal_sig_strict=str(node_data.get("goal_sig_strict", "")),
                visit_count=int(node_data.get("visit_count", 0)),
                success_count=int(node_data.get("success_count", 0)),
                is_terminal=bool(node_data.get("is_terminal")),
                is_dead=bool(node_data.get("is_dead")),
                depth=int(node_data.get("depth", 0)),
                expansion_order=int(node_data.get("expansion_order", 0)),
            )

        for mvar_id, node_data in nodes_payload.items():
            node = nodes_by_mvar[str(mvar_id)]
            raw_children = node_data.get("children", {})
            if not isinstance(raw_children, dict):
                continue
            children: dict[str, list[MCTSNode]] = {}
            for tactic, child_ids in raw_children.items():
                if not isinstance(tactic, str) or not isinstance(child_ids, list):
                    continue
                resolved_children = [
                    nodes_by_mvar[str(child_id)]
                    for child_id in child_ids
                    if str(child_id) in nodes_by_mvar
                ]
                for child in resolved_children:
                    child.parent = node
                children[tactic] = resolved_children
            node.children = children

        return cls(
            root=nodes_by_mvar[root_mvar_id],
            nodes_by_mvar=nodes_by_mvar,
            expansion_count=int(data.get("expansion_count", 0)),
            aborted=bool(data.get("aborted")),
        )

    def select(
        self,
        c: float = math.sqrt(2),
        strategy: BackpropStrategy = BackpropStrategy.UNIFORM,
        rng: random.Random | None = None,
        tie_breaker: Callable[[list[tuple[str, MCTSNode]]], tuple[str, MCTSNode]] | None = None,
    ) -> MCTSNode:
        node = self.root
        while node.children and not node.is_terminal and not node.is_dead:
            result = node.best_child_by_ucb1(c, strategy, rng, tie_breaker=tie_breaker)
            if result is None:
                node.is_dead = True
                break
            _, child = result
            node = child
        return node

    def select_leaf_uniform(self, rng: random.Random) -> MCTSNode:
        leaves = [
            n
            for n in self.nodes_by_mvar.values()
            if (not n.children) and (not n.is_terminal) and (not n.is_dead)
        ]
        if leaves:
            return rng.choice(leaves)
        self.root.is_dead = True
        return self.root

    def expand(
        self,
        node: MCTSNode,
        tactic: str,
        child_mvar_ids: list[str],
        goal_types: list[str],
        goal_sigs: list[str] | None = None,
        goal_sigs_strict: list[str] | None = None,
    ) -> list[MCTSNode]:
        if tactic in node.children:
            return node.children[tactic]

        self.expansion_count += 1
        new_nodes = []

        if not child_mvar_ids:
            node.is_terminal = True
            node.children[tactic] = []
        else:
            if len(child_mvar_ids) != len(goal_types):
                raise ValueError("Child mvar_ids and goal_types length mismatch")
            if goal_sigs is None:
                goal_sigs = [""] * len(child_mvar_ids)
            if len(goal_sigs) != len(child_mvar_ids):
                raise ValueError("goal_sigs length mismatch")
            if goal_sigs_strict is None:
                goal_sigs_strict = [""] * len(child_mvar_ids)
            if len(goal_sigs_strict) != len(child_mvar_ids):
                raise ValueError("goal_sigs_strict length mismatch")
            for mvar_id, goal_type, goal_sig, goal_sig_strict in zip(
                child_mvar_ids, goal_types, goal_sigs, goal_sigs_strict
            ):
                if mvar_id in self.nodes_by_mvar:
                    raise ValueError(f"Duplicate mvar_id in MCTS tree: {mvar_id}")
                child = MCTSNode(
                    mvar_id=mvar_id,
                    goal_type=goal_type,
                    goal_sig=goal_sig,
                    goal_sig_strict=goal_sig_strict,
                    parent=node,
                    depth=node.depth + 1,
                    expansion_order=self.expansion_count,
                )
                self.nodes_by_mvar[mvar_id] = child
                new_nodes.append(child)
            node.children[tactic] = new_nodes

        return new_nodes

    def backpropagate(self, node: MCTSNode, success: bool):
        current: MCTSNode | None = node
        while current is not None:
            current.visit_count += 1
            if success:
                current.success_count += 1
            current = current.parent

    def is_solved(self) -> bool:
        memo: dict[str, bool] = {}
        stack: list[tuple[MCTSNode, bool]] = [(self.root, False)]

        while stack:
            node, processed = stack.pop()

            if node.mvar_id in memo:
                continue

            if node.is_terminal:
                memo[node.mvar_id] = True
                continue

            if node.is_dead or not node.children:
                memo[node.mvar_id] = False
                continue

            if not processed:
                all_children = [c for cs in node.children.values() for c in cs]
                unprocessed = [c for c in all_children if c.mvar_id not in memo]
                if unprocessed:
                    stack.append((node, True))
                    for child in unprocessed:
                        stack.append((child, False))
                    continue

            for tactic, children in node.children.items():
                if all(memo.get(c.mvar_id, False) for c in children):
                    memo[node.mvar_id] = True
                    break
            else:
                memo[node.mvar_id] = False

        return memo.get(self.root.mvar_id, False)

    def serialize(self) -> dict:
        return {
            "root_mvar_id": self.root.mvar_id,
            "expansion_count": self.expansion_count,
            "nodes": {mvar_id: node.serialize() for mvar_id, node in self.nodes_by_mvar.items()},
        }

    def stats(self) -> dict:
        terminal_count = sum(1 for n in self.nodes_by_mvar.values() if n.is_terminal)
        dead_count = sum(1 for n in self.nodes_by_mvar.values() if n.is_dead)
        max_depth = max((n.depth for n in self.nodes_by_mvar.values()), default=0)
        total_visits = self.root.visit_count
        return {
            "nodes": len(self.nodes_by_mvar),
            "expansions": self.expansion_count,
            "terminal_nodes": terminal_count,
            "dead_nodes": dead_count,
            "max_depth": max_depth,
            "total_visits": total_visits,
            "solved": self.is_solved(),
        }

    def extract_winning_tactics(self) -> list[dict] | None:
        if not self.is_solved():
            return None

        result: list[dict] = []

        def find_solution(node: MCTSNode) -> bool:
            if node.is_terminal:
                for tactic, children in node.children.items():
                    if not children:
                        result.append({
                            "goal": node.goal_type,
                            "tactic": tactic,
                            "mvar_id": node.mvar_id,
                        })
                        return True
                return False

            for tactic, children in node.children.items():
                if all(find_solution(child) for child in children):
                    result.append({
                        "goal": node.goal_type,
                        "tactic": tactic,
                        "mvar_id": node.mvar_id,
                    })
                    return True

            return False

        find_solution(self.root)
        result.reverse()
        return result


def _get_path_to_root(node: MCTSNode) -> list[str]:
    path = []
    current: MCTSNode | None = node
    while current is not None:
        path.append(current.mvar_id)
        current = current.parent
    path.reverse()
    return path


def _blocked_goal_sigs_for_expansion(node: MCTSNode) -> set[str]:
    blocked: set[str] = set()
    current: MCTSNode | None = node
    while current is not None:
        if current.goal_sig:
            blocked.add(current.goal_sig)
        current = current.parent
    return blocked


ProgressCallback = Callable[[int, int, int, int, int, str | None, str | None], bool]


class MCTSTraceWriter:
    def __init__(
        self,
        path: Path,
        *,
        flush_every: int = 256,
        flush_interval_s: float = 1.0,
    ) -> None:
        self.path = path
        # Writing an MCTS trace can be very write-heavy. Flushing each record can
        # dominate runtime on slower volumes (e.g. mounted archives). Buffer writes
        # and flush periodically so tracing stays usable without stalling search.
        self.handle = path.open("w", encoding="utf-8", buffering=1024 * 1024)
        self._flush_every = flush_every if flush_every > 0 else 0
        self._flush_interval_s = max(0.0, float(flush_interval_s))
        self._records_since_flush = 0
        self._last_flush = time.monotonic()

    def write(self, record: dict[str, Any]) -> None:
        json.dump(record, self.handle, ensure_ascii=True)
        self.handle.write("\n")
        self._records_since_flush += 1
        if self._flush_every and (self._records_since_flush % self._flush_every == 0):
            self.handle.flush()
            self._last_flush = time.monotonic()
            return
        if (
            self._flush_interval_s
            and (time.monotonic() - self._last_flush) >= self._flush_interval_s
        ):
            self.handle.flush()
            self._last_flush = time.monotonic()

    def close(self) -> None:
        try:
            self.handle.flush()
        except Exception:
            pass
        self.handle.close()

    def __enter__(self) -> "MCTSTraceWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


async def mcts_search(
    theorem: str,
    adapter: LeanAdapter,
    tactic_provider: TacticProvider,
    graph: ProofGraph | None = None,
    history: ExplorationHistory | None = None,
    goal_cache: GoalCache | None = None,
    max_iterations: int = 1000,
    c: float = math.sqrt(2),
    backprop_strategy: BackpropStrategy = BackpropStrategy.UNIFORM,
    search_policy: SearchPolicy = SearchPolicy.UCB1,
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
    tie_breaker: Callable[[list[tuple[str, MCTSNode]], int], tuple[str, MCTSNode]]
    | None = None,
    expansion_policy: ExpansionPolicy | str = ExpansionPolicy.ALL_SUCCESSES,
) -> MCTSTree:
    import logging
    logger = logging.getLogger(__name__)

    if goal_sig_config is None:
        raise ValueError("goal_sig_config is required")
    expansion_policy = coerce_expansion_policy(expansion_policy)

    def mark_dead(node: MCTSNode, reason: str) -> None:
        node.is_dead = True
        node.dead_reason = reason

    if warmstart_tree is not None:
        tree = warmstart_tree
        start_iteration = tree.root.visit_count
        logger.debug("Warmstarting MCTS from iteration %s", start_iteration)
    else:
        initial_mvars = await adapter.initialize(theorem)
        if not initial_mvars:
            raise ValueError("No initial goals from theorem")

        root_mvar = initial_mvars[0]
        root_goal = adapter.get_goal(root_mvar)
        if root_goal is None:
            raise ValueError(f"No goal found for initial mvar_id: {root_mvar}")
        root_goal_type = root_goal.type
        root_goal_sig, root_goal_sig_strict = _get_goal_sigs(
            root_goal,
            root_mvar,
            goal_cache,
            goal_sig_config,
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

    last_tactic: str | None = None
    last_goal_sig: str | None = None

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

    def tree_snapshot(solved: bool) -> dict[str, Any]:
        max_depth = max((n.depth for n in tree.nodes_by_mvar.values()), default=0)
        return {
            "nodes": len(tree.nodes_by_mvar),
            "expansions": tree.expansion_count,
            "max_depth": max_depth,
            "solved": solved,
            "aborted": tree.aborted,
        }

    def trace_iteration(
        iteration: int,
        reason: str,
        current_node: MCTSNode,
        selected_path: list[str],
        attempts: list[TacticAttempt],
        tactics_with_probs: list[tuple[str, float]],
        expanded: bool | None,
        terminal_reached: bool,
        backprop_success: bool,
        solved: bool,
    ) -> None:
        if trace is None:
            return
        record: dict[str, Any] = {}
        if trace_context:
            record.update(trace_context)
        record.update(
            {
                "event": "iteration",
                "iteration": iteration,
                "reason": reason,
                "selected_path": selected_path,
                "node": node_snapshot(current_node),
                "tactics": [
                    {"tactic": tactic, "score": float(score)}
                    for tactic, score in tactics_with_probs
                ],
                "attempts": serialize_attempts(attempts),
                "expanded": expanded,
                "terminal_reached": terminal_reached,
                "backprop_success": backprop_success,
                "tree": tree_snapshot(solved),
            }
        )
        trace.write(record)

    for iteration in range(start_iteration, start_iteration + max_iterations):
        if iteration % 10 == 0:
            n_nodes = len(tree.nodes_by_mvar)
            logger.debug(f"    MCTS iteration {iteration}/{max_iterations}, nodes={n_nodes}")
        if progress_callback:
            nodes = tree.nodes_by_mvar.values()
            leaves = sum(1 for n in nodes if not n.children and not n.is_terminal)
            max_depth = max((n.depth for n in nodes), default=0)
            should_abort = progress_callback(
                iteration,
                start_iteration + max_iterations,
                len(tree.nodes_by_mvar),
                leaves,
                max_depth,
                last_tactic,
                last_goal_sig,
            )
            if should_abort:
                logger.warning(f"    MCTS aborted at iteration {iteration} - degenerate search")
                if trace is not None:
                    record: dict[str, Any] = {}
                    if trace_context:
                        record.update(trace_context)
                    record.update(
                        {
                            "event": "abort",
                            "iteration": iteration,
                            "tree": tree_snapshot(tree.is_solved()),
                        }
                    )
                    trace.write(record)
                tree.aborted = True
                break
        if search_policy == SearchPolicy.UCB1:
            if tie_breaker is None:
                node = tree.select(c, backprop_strategy, rng)
            else:
                node = tree.select(
                    c,
                    backprop_strategy,
                    rng,
                    tie_breaker=lambda candidates, it=iteration: tie_breaker(candidates, it),
                )
        elif search_policy == SearchPolicy.BLIND_UNIFORM:
            if rng is None:
                raise ValueError("rng is required for blind_uniform search_policy")
            node = tree.select_leaf_uniform(rng)
        else:
            raise ValueError(f"Unknown search_policy: {search_policy!r}")
        selected_path = _get_path_to_root(node) if history else []
        attempts: list[TacticAttempt] = []
        backprop_success = False
        terminal_reached = False
        expanded: bool | None = None
        tactics_with_probs: list[tuple[str, float]] = []

        if node.is_terminal:
            terminal_reached = True
            backprop_success = True
            tree.backpropagate(node, success=True)
            if history:
                history.record_iteration(
                    IterationRecord(
                        iteration=iteration,
                        selected_path=selected_path,
                        attempts=attempts,
                        backprop_success=backprop_success,
                        terminal_reached=terminal_reached,
                    )
                )
            solved_now = tree.is_solved()
            trace_iteration(
                iteration,
                "terminal_node",
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
                break
            continue

        if node.is_dead:
            tree.backpropagate(node, success=False)
            if history:
                history.record_iteration(
                    IterationRecord(
                        iteration=iteration,
                        selected_path=selected_path,
                        attempts=attempts,
                        backprop_success=False,
                        terminal_reached=False,
                    )
                )
            if tree.root.is_dead:
                solved_now = tree.is_solved()
                trace_iteration(
                    iteration,
                    "dead_node",
                    node,
                    selected_path,
                    attempts,
                    tactics_with_probs,
                    expanded,
                    terminal_reached,
                    backprop_success,
                    solved_now,
                )
                logger.debug(f"    MCTS stopped at iteration {iteration} - root is dead")
                break
            solved_now = tree.is_solved()
            trace_iteration(
                iteration,
                "dead_node",
                node,
                selected_path,
                attempts,
                tactics_with_probs,
                expanded,
                terminal_reached,
                backprop_success,
                solved_now,
            )
            continue

        try:
            goal = adapter.get_goal(node.mvar_id)
        except Exception:
            mark_dead(node, "adapter_exception:get_goal")
            logger.exception(
                "MCTS adapter.get_goal failed for mvar_id=%s; treating as no-moves",
                node.mvar_id,
            )
            tree.backpropagate(node, success=False)
            if history:
                history.record_iteration(
                    IterationRecord(
                        iteration=iteration,
                        selected_path=selected_path,
                        attempts=attempts,
                        backprop_success=False,
                        terminal_reached=False,
                    )
                )
            solved_now = tree.is_solved()
            trace_iteration(
                iteration,
                "adapter_exception",
                node,
                selected_path,
                attempts,
                tactics_with_probs,
                expanded,
                terminal_reached,
                backprop_success,
                solved_now,
            )
            continue
        if goal is None:
            mark_dead(node, "missing_goal")
            tree.backpropagate(node, success=False)
            if history:
                history.record_iteration(
                    IterationRecord(
                        iteration=iteration,
                        selected_path=selected_path,
                        attempts=attempts,
                        backprop_success=False,
                        terminal_reached=False,
                    )
                )
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
                node.goal_sig = goal_sig
            if node.goal_features is None and goal_sig:
                if goal_cache is not None:
                    node.goal_features = goal_cache.get_features(goal_sig).tolist()
            if not goal_sig_strict:
                goal_sig_strict = compute_goal_signature_strict(
                    type_str=goal.type,
                    type_expr=goal.type_expr,
                    hyp_types=hyp_types,
                    hyp_exprs=hyp_exprs,
                    config=goal_sig_config,
                )
                node.goal_sig_strict = goal_sig_strict
        last_goal_sig = goal_sig
        provider_id = getattr(tactic_provider, "provider_id", None)
        record_attempt = getattr(tactic_provider, "record_attempt", None)
        try:
            tactics_with_probs = await tactic_provider.suggest_tactics_with_probs_async(
                goal, node.mvar_id, adapter
            )
        except Exception:
            mark_dead(node, "provider_exception")
            logger.exception(
                "MCTS tactic provider failed for mvar_id=%s provider=%s; treating as no-moves",
                node.mvar_id,
                tactic_provider.describe(),
            )
            tree.backpropagate(node, success=False)
            expanded = False
            if history:
                history.record_iteration(
                    IterationRecord(
                        iteration=iteration,
                        selected_path=selected_path,
                        attempts=attempts,
                        backprop_success=False,
                        terminal_reached=False,
                    )
                )
            solved_now = tree.is_solved()
            trace_iteration(
                iteration,
                "provider_exception",
                node,
                selected_path,
                attempts,
                [],
                expanded,
                terminal_reached,
                backprop_success,
                solved_now,
            )
            continue
        if search_policy == SearchPolicy.UCB1:
            tactics_with_probs.sort(key=lambda x: x[1], reverse=True)
            if tactic_ranker is not None:
                ranked = tactic_ranker(tactics_with_probs, iteration, node)
                if len(ranked) != len(tactics_with_probs):
                    raise ValueError("tactic_ranker must return the same number of tactics")
                if Counter(ranked) != Counter(tactics_with_probs):
                    raise ValueError("tactic_ranker must return the same tactics with new ordering")
                tactics_with_probs = ranked
            tactics = [t for t, _ in tactics_with_probs]
        elif search_policy == SearchPolicy.BLIND_UNIFORM:
            if rng is None:
                raise ValueError("rng is required for blind_uniform search_policy")
            tactics = [t for t, _ in tactics_with_probs]
            rng.shuffle(tactics)
        else:
            raise ValueError(f"Unknown search_policy: {search_policy!r}")

        blocked_list: list[BlockedTactic | str] = getattr(tactic_provider, "last_blocked", [])
        if history and blocked_list:
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
            if tactic in node.children:
                continue

            try:
                preview = await adapter.preview_tactic(node.mvar_id, tactic)
            except Exception:
                logger.exception(
                    "MCTS adapter.preview_tactic failed for mvar_id=%s tactic=%s; "
                    "treating as failure",
                    node.mvar_id,
                    tactic,
                )
                preview = None
            if record_attempt is not None:
                record_attempt(tactic=tactic, goal_sig=goal_sig, budget_key=node.mvar_id)

            if preview is None:
                tactic_norm = normalize_tactic(tactic)
                if goal_cache is not None:
                    fam = tactic_family(tactic_norm)
                    goal_cache.record_outcome(node.mvar_id, _family_index(fam), success=False)
                if history:
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
                if history:
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
                pending_expansions.append((tactic, tactic_norm, preview, [], [], [], [], True))
                if expansion_policy == ExpansionPolicy.FIRST_SUCCESS:
                    break
                continue

            novel_mvars = []
            novel_goal_types = []
            novel_goal_sigs = []
            novel_goal_sigs_strict = []
            blocked_goal_sigs = _blocked_goal_sigs_for_expansion(node)
            for state_id, child_goal in zip(preview.child_mvar_ids, preview.child_goals):
                if child_goal.mvar_id is None:
                    raise ValueError(f"Child goal has no mvar_id: {child_goal.type}")
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
                if sig in blocked_goal_sigs:
                    continue
                sig_strict = compute_goal_signature_strict(
                    type_str=child_goal.type,
                    type_expr=child_goal.type_expr,
                    hyp_types=hyp_types,
                    hyp_exprs=hyp_exprs,
                    config=goal_sig_config,
                )
                novel_mvars.append(state_id)
                novel_goal_types.append(child_goal.type)
                novel_goal_sigs.append(sig)
                novel_goal_sigs_strict.append(sig_strict)
                blocked_goal_sigs.add(sig)

            if not novel_mvars:
                if history:
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

            if history:
                attempts.append(
                    TacticAttempt(
                        iteration=iteration,
                        node_mvar_id=node.mvar_id,
                        tactic=tactic,
                        outcome=TacticOutcome.SUCCESS,
                        # Record only novel/deduped children expanded into the tree/graph.
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
            try:
                adapter.commit_tactic(preview)
            except Exception:
                logger.exception(
                    "MCTS adapter.commit_tactic failed for mvar_id=%s tactic=%s; "
                    "skipping this branch",
                    node.mvar_id,
                    tactic,
                )
                continue
            expanded = True
            last_tactic = tactic
            if closes_goal:
                terminal_reached = True

            if goal_cache is not None:
                fam = tactic_family(tactic_norm)
                goal_cache.record_outcome(node.mvar_id, _family_index(fam), success=True)

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
                    novel_goal_sigs,
                    action_attrs=preview.action_metadata(expanded_child_count=len(novel_mvars)),
                )

        if expanded:
            backprop_success = True
            tree.backpropagate(node, success=True)

        if not expanded:
            node.is_dead = True
            tree.backpropagate(node, success=False)

        if history:
            history.record_iteration(
                IterationRecord(
                    iteration=iteration,
                    selected_path=selected_path,
                    attempts=attempts,
                    backprop_success=backprop_success,
                    terminal_reached=terminal_reached,
                )
            )

        solved_now = tree.is_solved()
        trace_iteration(
            iteration,
            "expanded" if expanded else "no_expansion",
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
            break

    return tree
