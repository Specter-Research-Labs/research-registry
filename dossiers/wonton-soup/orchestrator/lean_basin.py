from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atp.compare_hash import hash_goal_sig
from corpus.lean.theorems import Theorem
from orchestrator.lean_progress import CorpusProgress
from orchestrator.lean_runner import (
    _reset_provider_for_seed,
    make_unique_name,
    run_single,
)
from prover import GoalCache, LeanAdapter
from prover.goal_signature import GoalSignatureConfig
from prover.k import k_log10_ratio
from prover.mcts import ExpansionPolicy, SearchPolicy
from prover.providers import TacticProvider


@dataclass
class SeedRunResult:
    seed: int
    solved: bool
    structure_hash: str | None
    iterations_to_solve: int | None
    attempts_total: int | None = None
    blind_solved: bool | None = None
    blind_structure_hash: str | None = None
    blind_iterations_to_solve: int | None = None
    blind_attempts_total: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SeedRunResult":
        seed = payload.get("seed")
        solved = payload.get("solved")
        structure_hash = payload.get("structure_hash")
        iterations_to_solve = payload.get("iterations_to_solve")
        attempts_total = payload.get("attempts_total")
        blind_solved = payload.get("blind_solved")
        blind_structure_hash = payload.get("blind_structure_hash")
        blind_iterations_to_solve = payload.get("blind_iterations_to_solve")
        blind_attempts_total = payload.get("blind_attempts_total")

        if not isinstance(seed, int):
            raise ValueError("seed must be an int")
        if not isinstance(solved, bool):
            raise ValueError("solved must be a bool")
        if structure_hash is not None and not isinstance(structure_hash, str):
            raise ValueError("structure_hash must be str | None")
        if iterations_to_solve is not None and not isinstance(iterations_to_solve, int):
            raise ValueError("iterations_to_solve must be int | None")
        if attempts_total is not None and not isinstance(attempts_total, int):
            raise ValueError("attempts_total must be int | None")
        if blind_solved is not None and not isinstance(blind_solved, bool):
            raise ValueError("blind_solved must be bool | None")
        if blind_structure_hash is not None and not isinstance(blind_structure_hash, str):
            raise ValueError("blind_structure_hash must be str | None")
        if blind_iterations_to_solve is not None and not isinstance(blind_iterations_to_solve, int):
            raise ValueError("blind_iterations_to_solve must be int | None")
        if blind_attempts_total is not None and not isinstance(blind_attempts_total, int):
            raise ValueError("blind_attempts_total must be int | None")

        return cls(
            seed=seed,
            solved=solved,
            structure_hash=structure_hash,
            iterations_to_solve=iterations_to_solve,
            attempts_total=attempts_total,
            blind_solved=blind_solved,
            blind_structure_hash=blind_structure_hash,
            blind_iterations_to_solve=blind_iterations_to_solve,
            blind_attempts_total=blind_attempts_total,
        )

    def serialize(self) -> dict:
        payload = {
            "seed": self.seed,
            "solved": self.solved,
            "structure_hash": self.structure_hash,
            "iterations_to_solve": self.iterations_to_solve,
        }
        if self.attempts_total is not None:
            payload["attempts_total"] = self.attempts_total
        if self.blind_solved is not None:
            payload["blind_solved"] = self.blind_solved
        if self.blind_structure_hash is not None:
            payload["blind_structure_hash"] = self.blind_structure_hash
        if self.blind_iterations_to_solve is not None:
            payload["blind_iterations_to_solve"] = self.blind_iterations_to_solve
        if self.blind_attempts_total is not None:
            payload["blind_attempts_total"] = self.blind_attempts_total
        return payload


def _load_seed_results(payload: dict[str, Any]) -> list[SeedRunResult]:
    raw_results = payload.get("seed_results")
    if not isinstance(raw_results, list):
        return []
    parsed: list[SeedRunResult] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        try:
            parsed.append(SeedRunResult.from_payload(raw))
        except ValueError:
            continue
    return parsed


def _has_blind_result(result: SeedRunResult) -> bool:
    return (
        result.blind_solved is not None
        or result.blind_structure_hash is not None
        or result.blind_iterations_to_solve is not None
        or result.blind_attempts_total is not None
    )


def _basin_resume_complete(
    seed_results: list[SeedRunResult],
    seeds: list[int],
    include_blind: bool,
) -> bool:
    expected = set(seeds)
    present = {result.seed for result in seed_results}
    if expected - present:
        return False
    if not include_blind:
        return True
    for seed in expected:
        if not any(_has_blind_result(result) for result in seed_results if result.seed == seed):
            return False
    return True


def _read_basin_resume_seed_results(basin_path: Path) -> list[SeedRunResult] | None:
    try:
        existing = json.loads(basin_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _load_seed_results(existing) if isinstance(existing, dict) else []


def prefilter_resumed_theorems(
    indexed_theorems: list[tuple[int, Theorem]],
    *,
    log_dir: Path,
    seeds: list[int],
    include_blind: bool,
) -> tuple[list[tuple[int, Theorem]], int, int]:
    pending: list[tuple[int, Theorem]] = []
    resumed_theorems = 0
    resumed_solves = 0
    for idx, theorem in indexed_theorems:
        basin_path = log_dir / theorem.name / "basin_analysis.json"
        existing_seed_results = _read_basin_resume_seed_results(basin_path)
        if existing_seed_results is None or not _basin_resume_complete(
            existing_seed_results,
            seeds=seeds,
            include_blind=include_blind,
        ):
            pending.append((idx, theorem))
            continue
        resumed_theorems += 1
        resumed_solves += sum(1 for result in existing_seed_results if result.solved)
    return pending, resumed_theorems, resumed_solves


@dataclass
class BasinAnalysis:
    theorem_name: str
    seeds: list[int]
    seed_results: list[SeedRunResult]
    solve_rate: float
    unique_structures: int
    dominant_structure_frequency: float
    structure_distribution: dict[str, int]
    blind_solve_rate: float | None = None
    paper_k: dict[str, Any] | None = None

    def serialize(self) -> dict:
        payload = {
            "theorem_name": self.theorem_name,
            "seeds": self.seeds,
            "seed_results": [r.serialize() for r in self.seed_results],
            "solve_rate": self.solve_rate,
            "unique_structures": self.unique_structures,
            "dominant_structure_frequency": self.dominant_structure_frequency,
            "structure_distribution": self.structure_distribution,
        }
        if self.blind_solve_rate is not None:
            payload["blind_solve_rate"] = self.blind_solve_rate
        if self.paper_k is not None:
            payload["paper_k"] = self.paper_k
        return payload


async def run_basin_analysis(
    adapter: LeanAdapter,
    theorem: Theorem,
    base_provider: TacticProvider,
    budget_tiers: list[int],
    seeds: list[int],
    include_blind: bool = False,
    mcts_mode: str = "centralized",
    expansion_policy: ExpansionPolicy | str = ExpansionPolicy.ALL_SUCCESSES,
    distributed_settings: dict[str, Any] | None = None,
    goal_cache: GoalCache | None = None,
    goal_sig_config: GoalSignatureConfig | None = None,
    progress: CorpusProgress | None = None,
    progress_worker_id: int | None = None,
) -> BasinAnalysis:
    seed_results = []
    counter = [0]

    if include_blind and mcts_mode != "centralized":
        raise ValueError("include_blind basin analysis currently requires centralized MCTS")

    goal_cache_for_run = None if include_blind else goal_cache

    async def _run_policy(
        *,
        seed: int,
        policy: SearchPolicy,
    ) -> tuple[bool, str | None, int | None, int]:
        _reset_provider_for_seed(base_provider, seed)
        rng = random.Random(seed)
        counter[0] += 1
        statement = make_unique_name(theorem, f"basin_{seed}_{policy.value}_{counter[0]}")
        run_result = await run_single(
            adapter,
            statement,
            base_provider,
            budget_tiers,
            goal_cache=goal_cache_for_run,
            goal_sig_config=goal_sig_config,
            mcts_mode=mcts_mode,
            expansion_policy=expansion_policy,
            distributed_settings=distributed_settings,
            rng=rng,
            provenance="basin_mcts",
            search_policy=policy,
            collect_solution_artifacts=False,
        )

        solved = run_result.solved
        structure_hash = hash_goal_sig(run_result.graph) if solved else None
        iterations_to_solve = (
            run_result.mcts_tree.root.visit_count
            if solved and run_result.mcts_tree is not None
            else None
        )
        attempts_total = int(run_result.history.detour_metrics().get("total_attempts") or 0)
        return solved, structure_hash, iterations_to_solve, attempts_total

    for seed in seeds:
        solved, structure_hash, iterations_to_solve, attempts_total = await _run_policy(
            seed=seed,
            policy=SearchPolicy.UCB1,
        )
        blind_result: tuple[bool | None, str | None, int | None, int | None] = (
            None,
            None,
            None,
            None,
        )
        if include_blind:
            blind_result = await _run_policy(
                seed=seed,
                policy=SearchPolicy.BLIND_UNIFORM,
            )
        seed_result = SeedRunResult(
            seed=seed,
            solved=solved,
            structure_hash=structure_hash,
            iterations_to_solve=iterations_to_solve,
            attempts_total=attempts_total,
            blind_solved=blind_result[0],
            blind_structure_hash=blind_result[1],
            blind_iterations_to_solve=blind_result[2],
            blind_attempts_total=blind_result[3],
        )
        seed_results.append(seed_result)

        if progress:
            progress.update_basin_seed(
                seed,
                seed_result.solved,
                seed_result.structure_hash,
                worker_id=progress_worker_id,
            )

    solved_results = [r for r in seed_results if r.solved]
    structure_counts: dict[str, int] = {}
    for r in solved_results:
        h = r.structure_hash
        if h:
            structure_counts[h] = structure_counts.get(h, 0) + 1

    dominant_freq = max(structure_counts.values()) / len(solved_results) if solved_results else 0.0

    blind_solved_results = [r for r in seed_results if r.blind_solved]
    blind_solve_rate = len(blind_solved_results) / len(seeds) if seeds else 0.0

    paper_k: dict[str, Any] | None = None
    if include_blind and seeds:
        total_budget = sum(budget_tiers)
        if total_budget <= 0:
            raise ValueError("budget_tiers must sum to > 0 for paper_k")

        agent_capped = [
            r.iterations_to_solve
            if r.solved and isinstance(r.iterations_to_solve, int)
            else total_budget
            for r in seed_results
        ]
        blind_capped = [
            r.blind_iterations_to_solve
            if r.blind_solved and isinstance(r.blind_iterations_to_solve, int)
            else total_budget
            for r in seed_results
        ]
        tau_agent_mean_lb = sum(agent_capped) / len(agent_capped)
        tau_blind_mean_lb = sum(blind_capped) / len(blind_capped)

        K_lb = None
        if tau_agent_mean_lb > 0 and tau_blind_mean_lb > 0:
            K_lb = k_log10_ratio(tau_blind=tau_blind_mean_lb, tau_agent=tau_agent_mean_lb)

        both_solved = [
            r
            for r in seed_results
            if r.solved
            and r.blind_solved
            and isinstance(r.iterations_to_solve, int)
            and isinstance(r.blind_iterations_to_solve, int)
        ]
        tau_agent_mean_both = None
        tau_blind_mean_both = None
        K_both = None
        if both_solved:
            tau_agent_mean_both = sum(r.iterations_to_solve for r in both_solved) / len(both_solved)
            tau_blind_mean_both = sum(r.blind_iterations_to_solve for r in both_solved) / len(
                both_solved
            )
            if tau_agent_mean_both > 0 and tau_blind_mean_both > 0:
                K_both = k_log10_ratio(tau_blind=tau_blind_mean_both, tau_agent=tau_agent_mean_both)

        paper_k = {
            "schema_version": 1,
            "K": {
                "lower_bound_censored_at_H": round(float(K_lb), 6) if K_lb is not None else None,
                "conditional_on_both_solved": (
                    round(float(K_both), 6) if K_both is not None else None
                ),
            },
            "problem_space": {
                "H_unit": "mcts_iteration",
                "H": total_budget,
                "w_unit": "mcts_iteration",
                "w": 1,
            },
            "policies": {
                "agent": SearchPolicy.UCB1.value,
                "blind": SearchPolicy.BLIND_UNIFORM.value,
            },
            "tau": {
                "agent_mean_censored": round(float(tau_agent_mean_lb), 6),
                "blind_mean_censored": round(float(tau_blind_mean_lb), 6),
                "agent_mean_both_solved": (
                    round(float(tau_agent_mean_both), 6)
                    if tau_agent_mean_both is not None
                    else None
                ),
                "blind_mean_both_solved": (
                    round(float(tau_blind_mean_both), 6)
                    if tau_blind_mean_both is not None
                    else None
                ),
            },
            "solve_rates": {
                "agent": round(len(solved_results) / len(seeds), 6) if seeds else 0.0,
                "blind": round(blind_solve_rate, 6),
                "both_solved": round(len(both_solved) / len(seeds), 6) if seeds else 0.0,
            },
            "notes": [
                "lower_bound_censored_at_H sets tau=H when a policy fails to solve within budget; "
                "this makes K a conservative lower bound when blind fails.",
            ],
        }

    return BasinAnalysis(
        theorem_name=theorem.name,
        seeds=seeds,
        seed_results=seed_results,
        solve_rate=len(solved_results) / len(seeds) if seeds else 0.0,
        unique_structures=len(structure_counts),
        dominant_structure_frequency=round(dominant_freq, 3),
        structure_distribution=structure_counts,
        blind_solve_rate=blind_solve_rate if include_blind else None,
        paper_k=paper_k,
    )
