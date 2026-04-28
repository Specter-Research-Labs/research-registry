from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from prover.providers.base import normalize_tactic


class TacticOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"


@dataclass(slots=True)
class TacticAttempt:
    iteration: int
    node_mvar_id: str
    tactic: str
    outcome: TacticOutcome
    child_mvar_ids: list[str]
    timestamp_ms: int
    tactic_norm: str | None = None
    goal_sig: str | None = None
    goal_sig_strict: str | None = None
    goal_type: str | None = None
    peg_id: str | None = None
    peg_kind: str | None = None
    block_reason: str | None = None
    provider_id: str | None = None


@dataclass(slots=True)
class IterationRecord:
    iteration: int
    selected_path: list[str]
    attempts: list[TacticAttempt]
    backprop_success: bool
    terminal_reached: bool


@dataclass
class ExplorationHistory:
    theorem: str
    blocked_tactics: set[str]
    iterations: list[IterationRecord] = field(default_factory=list)
    start_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    solution_path: list[dict] | None = None

    @classmethod
    def create(
        cls,
        theorem: str,
        blocked_tactics: set[str] | None = None,
    ) -> ExplorationHistory:
        return cls(
            theorem=theorem,
            blocked_tactics=blocked_tactics or set(),
            iterations=[],
            start_time_ms=int(time.time() * 1000),
        )

    @classmethod
    def from_json(cls, data: dict) -> ExplorationHistory:
        if not isinstance(data, dict):
            raise ValueError("ExplorationHistory payload must be an object")

        theorem = data.get("theorem")
        if not isinstance(theorem, str) or not theorem:
            raise ValueError("ExplorationHistory payload missing theorem")

        blocked_raw = data.get("blocked_tactics", [])
        blocked_tactics = {
            str(item)
            for item in blocked_raw
            if isinstance(item, str) and item
        }

        iterations: list[IterationRecord] = []
        for record_data in data.get("iterations", []):
            if not isinstance(record_data, dict):
                continue
            iteration = int(record_data.get("iteration", 0))
            attempts: list[TacticAttempt] = []
            for attempt_data in record_data.get("attempts", []):
                if not isinstance(attempt_data, dict):
                    continue
                try:
                    outcome = TacticOutcome(str(attempt_data.get("outcome", "failure")))
                except ValueError:
                    outcome = TacticOutcome.FAILURE
                attempts.append(
                    TacticAttempt(
                        iteration=iteration,
                        node_mvar_id=str(attempt_data.get("node_mvar_id", "")),
                        tactic=str(attempt_data.get("tactic", "")),
                        outcome=outcome,
                        child_mvar_ids=[
                            str(item)
                            for item in attempt_data.get("child_mvar_ids", [])
                            if isinstance(item, str)
                        ],
                        timestamp_ms=int(attempt_data.get("timestamp_ms", 0)),
                        tactic_norm=(
                            str(attempt_data["tactic_norm"])
                            if isinstance(attempt_data.get("tactic_norm"), str)
                            else None
                        ),
                        goal_sig=(
                            str(attempt_data["goal_sig"])
                            if isinstance(attempt_data.get("goal_sig"), str)
                            else None
                        ),
                        goal_sig_strict=(
                            str(attempt_data["goal_sig_strict"])
                            if isinstance(attempt_data.get("goal_sig_strict"), str)
                            else None
                        ),
                        goal_type=(
                            str(attempt_data["goal_type"])
                            if isinstance(attempt_data.get("goal_type"), str)
                            else None
                        ),
                        peg_id=(
                            str(attempt_data["peg_id"])
                            if isinstance(attempt_data.get("peg_id"), str)
                            else None
                        ),
                        peg_kind=(
                            str(attempt_data["peg_kind"])
                            if isinstance(attempt_data.get("peg_kind"), str)
                            else None
                        ),
                        block_reason=(
                            str(attempt_data["block_reason"])
                            if isinstance(attempt_data.get("block_reason"), str)
                            else None
                        ),
                        provider_id=(
                            str(attempt_data["provider_id"])
                            if isinstance(attempt_data.get("provider_id"), str)
                            else None
                        ),
                    )
                )
            iterations.append(
                IterationRecord(
                    iteration=iteration,
                    selected_path=[
                        str(item)
                        for item in record_data.get("selected_path", [])
                        if isinstance(item, str)
                    ],
                    attempts=attempts,
                    backprop_success=bool(record_data.get("backprop_success")),
                    terminal_reached=bool(record_data.get("terminal_reached")),
                )
            )

        start_time_ms = data.get("start_time_ms")
        solution_path = data.get("solution_path")
        return cls(
            theorem=theorem,
            blocked_tactics=blocked_tactics,
            iterations=iterations,
            start_time_ms=int(start_time_ms) if isinstance(start_time_ms, int) else 0,
            solution_path=solution_path if isinstance(solution_path, list) else None,
        )

    def elapsed_ms(self) -> int:
        return int(time.time() * 1000) - self.start_time_ms

    def record_iteration(self, record: IterationRecord) -> None:
        self.iterations.append(record)

    def detour_metrics(self) -> dict:
        if not self.iterations:
            return {
                "total_iterations": 0,
                "total_attempts": 0,
                "success_count": 0,
                "failure_count": 0,
                "blocked_count": 0,
                "failure_ratio": 0.0,
                "max_depth": 0,
                "depth_at_solution": 0,
                "terminal_iteration": None,
            }

        total_attempts = 0
        success_count = 0
        failure_count = 0
        blocked_count = 0
        max_depth = 0
        terminal_iteration = None

        for record in self.iterations:
            depth = len(record.selected_path)
            if depth > max_depth:
                max_depth = depth

            for attempt in record.attempts:
                total_attempts += 1
                if attempt.outcome == TacticOutcome.SUCCESS:
                    success_count += 1
                elif attempt.outcome == TacticOutcome.FAILURE:
                    failure_count += 1
                elif attempt.outcome == TacticOutcome.BLOCKED:
                    blocked_count += 1

            if record.terminal_reached and terminal_iteration is None:
                terminal_iteration = record.iteration

        depth_at_solution = 0
        if terminal_iteration is not None:
            for record in self.iterations:
                if record.iteration == terminal_iteration:
                    depth_at_solution = len(record.selected_path)
                    break

        failure_ratio = failure_count / total_attempts if total_attempts > 0 else 0.0

        return {
            "total_iterations": len(self.iterations),
            "total_attempts": total_attempts,
            "success_count": success_count,
            "failure_count": failure_count,
            "blocked_count": blocked_count,
            "failure_ratio": round(failure_ratio, 3),
            "max_depth": max_depth,
            "depth_at_solution": depth_at_solution,
            "terminal_iteration": terminal_iteration,
        }

    def serialize(self) -> dict:
        return {
            "theorem": self.theorem,
            "blocked_tactics": sorted(self.blocked_tactics),
            "iteration_count": len(self.iterations),
            "detour_metrics": self.detour_metrics(),
            "solution_path": self.solution_path,
            "iterations": [
                {
                    "iteration": r.iteration,
                    "selected_path": r.selected_path,
                    "attempts": [
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
                        for a in r.attempts
                    ],
                    "backprop_success": r.backprop_success,
                    "terminal_reached": r.terminal_reached,
                }
                for r in self.iterations
            ],
        }

    def trajectory_metrics(self) -> dict:
        if not self.iterations:
            return {
                "total_iterations": 0,
                "backtrack_count": 0,
                "max_depth_reached": 0,
                "depth_at_solution": 0,
                "unique_goals_visited": 0,
                "tactic_diversity": 0,
            }

        backtrack_count = 0
        prev_depth = 0
        unique_goals: set[str] = set()
        unique_tactics: set[str] = set()
        max_depth = 0
        depth_at_solution = 0
        solution_found = False

        for record in self.iterations:
            depth = len(record.selected_path)
            if depth > max_depth:
                max_depth = depth
            if depth < prev_depth:
                backtrack_count += 1
            prev_depth = depth

            for mvar_id in record.selected_path:
                unique_goals.add(mvar_id)

            for attempt in record.attempts:
                if attempt.tactic_norm:
                    unique_tactics.add(attempt.tactic_norm)

            if record.terminal_reached and not solution_found:
                depth_at_solution = depth
                solution_found = True

        return {
            "total_iterations": len(self.iterations),
            "backtrack_count": backtrack_count,
            "max_depth_reached": max_depth,
            "depth_at_solution": depth_at_solution,
            "unique_goals_visited": len(unique_goals),
            "tactic_diversity": len(unique_tactics),
        }

    def goal_type_tactic_matrix(self) -> dict[str, dict[str, dict[str, int]]]:
        matrix: dict[str, dict[str, dict[str, int]]] = {}

        for record in self.iterations:
            for attempt in record.attempts:
                if not attempt.goal_type or not attempt.tactic_norm:
                    continue

                goal_type = attempt.goal_type
                tactic = attempt.tactic_norm
                outcome = attempt.outcome.value

                if goal_type not in matrix:
                    matrix[goal_type] = {}
                if tactic not in matrix[goal_type]:
                    matrix[goal_type][tactic] = {"success": 0, "failure": 0, "blocked": 0}

                matrix[goal_type][tactic][outcome] += 1

        return matrix

    def tactic_usage_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.iterations:
            for attempt in record.attempts:
                if not attempt.tactic_norm:
                    continue
                counts[attempt.tactic_norm] = counts.get(attempt.tactic_norm, 0) + 1
        return counts

    def attempted_tactics(self) -> set[str]:
        tactics = set()
        for record in self.iterations:
            for attempt in record.attempts:
                if attempt.tactic_norm:
                    tactics.add(attempt.tactic_norm)
        return tactics

    def successful_tactics(self) -> set[str]:
        tactics = set()
        for record in self.iterations:
            for attempt in record.attempts:
                if attempt.outcome != TacticOutcome.SUCCESS:
                    continue
                if attempt.tactic_norm:
                    tactics.add(attempt.tactic_norm)
        return tactics

    def tactics_on_solution_path(self) -> list[str]:
        if self.solution_path is None:
            raise ValueError("solution_path is required to compute solution tactics")
        tactics = []
        for step in self.solution_path:
            tactic = step.get("tactic")
            if not tactic:
                raise ValueError("solution_path entry missing tactic")
            tactics.append(normalize_tactic(tactic))
        return tactics

    def solution_path_tactics(self) -> set[str]:
        if self.solution_path is None:
            return set()
        return set(self.tactics_on_solution_path())

    def tactic_fingerprint(self) -> dict:
        solution_tactics = self.solution_path_tactics()
        return {
            "attempted_tactics": sorted(self.attempted_tactics()),
            "successful_tactics": sorted(self.successful_tactics()),
            "solution_path_tactics": sorted(solution_tactics),
            "tactic_counts": self.tactic_usage_counts(),
        }
