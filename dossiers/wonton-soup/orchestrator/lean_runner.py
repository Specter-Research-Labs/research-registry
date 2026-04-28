from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import networkx as nx
from leantree.repl_adapter.interaction import LeanInteractionException, LeanProcessException

from analysis.trajectory import compare_trajectories, extract_solution_goal_sigs
from corpus.lean.theorems import Intervention, Theorem
from experiments.distributed_mcts import distributed_mcts_search
from prover import (
    ExplorationHistory,
    FilteredTacticProvider,
    GoalCache,
    LeanAdapter,
    MCTSTraceWriter,
    MCTSTree,
    ProofGraph,
    canonical_edge_match,
    canonical_node_match,
    mcts_search,
)
from prover.goal_signature import GoalSignatureConfig
from prover.mcts import SearchPolicy
from prover.providers import TacticProvider

if TYPE_CHECKING:
    from orchestrator.lean import (
        RunResult,
        TacticRanker,
        TacticRankerAgent,
        TheoremResult,
        TieBreaker,
        TieBreakerAgent,
    )
    from orchestrator.lean_progress import CorpusProgress

from orchestrator.lean_metadata import build_distributed_config


def _lean_helpers():
    from orchestrator import lean as lean_mod

    return lean_mod


def _derive_search_seed(base_seed: int, *parts: str) -> int:
    digest = hashlib.sha256()
    digest.update(str(base_seed).encode("utf-8"))
    for part in parts:
        digest.update(b"\0")
        digest.update(part.encode("utf-8"))
    return int.from_bytes(digest.digest()[:4], "big")


def _reset_provider_for_seed(provider: TacticProvider, seed: int | None) -> None:
    if seed is None:
        return
    clear_cache = getattr(provider, "clear_cache", None)
    if callable(clear_cache):
        clear_cache()
    set_seed = getattr(provider, "set_seed", None)
    if callable(set_seed):
        set_seed(seed)


def make_unique_name(theorem: Theorem, suffix: str) -> str:
    tmpl = theorem.statement
    if "{name}" not in tmpl:
        raise ValueError(f"Theorem statement missing {{name}} placeholder: {theorem.name}")
    return tmpl.replace("{name}", f"{theorem.name}_{suffix}")


def _solution_goal_sigs(run_result: RunResult) -> list[str]:
    if not (
        run_result.solved
        and run_result.mcts_tree
        and run_result.history.solution_path
    ):
        return []
    return extract_solution_goal_sigs(
        run_result.history.solution_path,
        run_result.mcts_tree,
    )


async def run_worker_phase(
    *,
    entries: list[tuple[int, Theorem]],
    num_workers: int,
    project_path: str | Path,
    logger: logging.Logger,
    base_provider: TacticProvider,
    provider_factory: Callable[[], TacticProvider],
    progress: CorpusProgress,
    state_lock: asyncio.Lock,
    crashed: list[Any],
    record_lean_exception: Callable[
        [LeanInteractionException | LeanProcessException, str],
        Any,
    ],
    crash_from_error: Callable[[str, Exception], Any],
    record_failure: Callable[[Exception], None],
    pool_label: str | None = None,
    worker_label: str,
    fatal_message: str,
    failure_message: str,
    run_item: Callable[[LeanAdapter, TacticProvider, int, Theorem, int], Awaitable[None]],
) -> None:
    adapters: list[LeanAdapter] = []
    abort_event = asyncio.Event()
    theorem_queues = [entries[i::num_workers] for i in range(num_workers)]
    try:
        if num_workers > 1:
            prefix = f"{pool_label} " if pool_label else ""
            logger.info(f"Creating {num_workers} {prefix}Lean REPL workers...")
        adapters = [await LeanAdapter.create(project_path) for _ in range(num_workers)]
        providers = (
            [base_provider]
            if num_workers == 1
            else [provider_factory() for _ in range(num_workers)]
        )
        for adapter in adapters:
            await adapter.__aenter__()
        progress.provider = providers[0] if providers else progress.provider

        async def run_queue(worker_idx: int, queue: list[tuple[int, Theorem]]) -> None:
            adapter = adapters[worker_idx]
            provider = providers[worker_idx]
            for idx, theorem in queue:
                if abort_event.is_set():
                    break
                try:
                    await run_item(adapter, provider, idx, theorem, worker_idx)
                except (LeanInteractionException, LeanProcessException) as exc:
                    async with state_lock:
                        crashed.append(record_lean_exception(exc, theorem.name))
                    if isinstance(exc, LeanProcessException):
                        progress.record_repl_restart(str(exc))
                        if num_workers == 1:
                            logger.info("Reinitializing Lean adapter...")
                        else:
                            logger.info(f"Reinitializing {worker_label} {worker_idx}...")
                        await adapter.__aexit__(None, None, None)
                        adapters[worker_idx] = await LeanAdapter.create(project_path)
                        await adapters[worker_idx].__aenter__()
                        adapter = adapters[worker_idx]
                except Exception as exc:
                    async with state_lock:
                        record_failure(exc)
                        crashed.append(crash_from_error(theorem.name, exc))
                    abort_event.set()
                    logger.exception(fatal_message)
                    break

        await asyncio.gather(*(run_queue(i, queue) for i, queue in enumerate(theorem_queues)))
    except Exception as exc:
        record_failure(exc)
        logger.exception(failure_message)
    finally:
        for adapter in reversed(adapters):
            await adapter.__aexit__(None, None, None)


async def _run_theorem_variant(
    *,
    adapter: LeanAdapter,
    theorem: Theorem,
    provider: TacticProvider,
    statement: str,
    variant_seed_key: str,
    trace_filename: str,
    budget_tiers: list[int],
    goal_cache: GoalCache | None,
    goal_sig_config: GoalSignatureConfig,
    mcts_mode: str,
    distributed_settings: dict[str, Any] | None,
    progress: CorpusProgress | None,
    log_dir: Path | None,
    trace_mcts: bool,
    theorem_search_seed: int | None,
    blocked_tactics: set[str] | None = None,
    tactic_ranker: TacticRanker | None = None,
    tactic_ranker_agent: TacticRankerAgent | None = None,
    tie_breaker: TieBreaker | None = None,
    tie_breaker_agent: TieBreakerAgent | None = None,
    collect_solution_artifacts: bool = True,
) -> RunResult:
    variant_seed = (
        _derive_search_seed(theorem_search_seed, variant_seed_key)
        if theorem_search_seed is not None
        else None
    )
    _reset_provider_for_seed(provider, variant_seed)
    rng = random.Random(variant_seed) if variant_seed is not None else None
    with _lean_helpers()._open_mcts_trace_writer(
        enabled=trace_mcts,
        log_dir=log_dir,
        theorem_name=theorem.name,
        filename=trace_filename,
    ) as trace:
        return await run_single(
            adapter,
            statement,
            provider,
            budget_tiers,
            blocked_tactics=blocked_tactics,
            goal_cache=goal_cache,
            goal_sig_config=goal_sig_config,
            mcts_mode=mcts_mode,
            distributed_settings=distributed_settings,
            progress=progress,
            trace=trace,
            rng=rng,
            tactic_ranker=tactic_ranker,
            tactic_ranker_agent=tactic_ranker_agent,
            tie_breaker=tie_breaker,
            tie_breaker_agent=tie_breaker_agent,
            collect_solution_artifacts=collect_solution_artifacts,
        )


def _canonical_graph_edit_distance(graph1: Any, graph2: Any) -> float | None:
    return nx.graph_edit_distance(
        graph1,
        graph2,
        node_match=canonical_node_match,
        edge_match=canonical_edge_match,
        timeout=5.0,
    )


def _merge_interventions(
    auto_interventions: list[Intervention],
    extra_interventions: list[Intervention],
) -> list[Intervention]:
    merged: list[Intervention] = []
    by_name: dict[str, Intervention] = {}
    for intervention in auto_interventions:
        merged.append(intervention)
        by_name[intervention.name] = intervention
    for intervention in extra_interventions:
        existing = by_name.get(intervention.name)
        if existing is None:
            merged.append(intervention)
            by_name[intervention.name] = intervention
            continue
        if (
            existing.blocked != intervention.blocked
            or existing.is_control != intervention.is_control
        ):
            raise ValueError(
                f"Conflicting interventions share the same name: {intervention.name!r}"
            )
    return merged


def _select_interventions(
    interventions: list[Intervention],
    requested_names: list[str] | None,
) -> list[Intervention]:
    if not requested_names:
        return interventions
    by_name = {intervention.name: intervention for intervention in interventions}
    missing = [name for name in requested_names if name not in by_name]
    if missing:
        available = sorted(by_name)[:10]
        suffix = "..." if len(by_name) > 10 else ""
        raise ValueError(
            f"Requested intervention(s) not available: {missing}. Available: {available}{suffix}"
        )
    selected: list[Intervention] = []
    seen: set[str] = set()
    for name in requested_names:
        if name in seen:
            continue
        selected.append(by_name[name])
        seen.add(name)
    return selected


async def _run_search_budget(
    *,
    statement: str,
    adapter: LeanAdapter,
    provider: TacticProvider,
    graph: ProofGraph,
    history: ExplorationHistory,
    goal_cache: GoalCache | None,
    goal_sig_config: GoalSignatureConfig,
    mcts_mode: str,
    budget: int,
    tree: MCTSTree | None,
    distributed_settings: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    trace: MCTSTraceWriter | None = None,
    trace_context: dict[str, Any] | None = None,
    rng: random.Random | None = None,
    tactic_ranker: TacticRanker | None = None,
    tactic_ranker_agent: TacticRankerAgent | None = None,
    tie_breaker: TieBreaker | None = None,
    tie_breaker_agent: TieBreakerAgent | None = None,
    search_policy: SearchPolicy = SearchPolicy.UCB1,
) -> MCTSTree:
    if mcts_mode == "distributed":
        if distributed_settings is None:
            raise ValueError("distributed_settings is required for distributed MCTS")
        return await distributed_mcts_search(
            statement,
            adapter,
            provider,
            graph,
            history,
            goal_cache=goal_cache,
            warmstart_tree=tree,
            progress_callback=progress_callback,
            trace=trace,
            trace_context=trace_context,
            goal_sig_config=goal_sig_config,
            rng=rng,
            tactic_ranker=tactic_ranker,
            tactic_ranker_agent=tactic_ranker_agent,
            tie_breaker=tie_breaker,
            tie_breaker_agent=tie_breaker_agent,
            config=build_distributed_config(distributed_settings, budget),
        )
    if mcts_mode == "centralized":
        return await mcts_search(
            statement,
            adapter,
            provider,
            graph,
            history,
            goal_cache=goal_cache,
            max_iterations=budget,
            search_policy=search_policy,
            warmstart_tree=tree,
            progress_callback=progress_callback,
            trace=trace,
            trace_context=trace_context,
            goal_sig_config=goal_sig_config,
            rng=rng,
            tactic_ranker=tactic_ranker,
            tie_breaker=tie_breaker,
        )
    raise ValueError(f"Unknown mcts_mode: {mcts_mode}")


async def run_single(
    adapter: LeanAdapter,
    statement: str,
    provider,
    budget_tiers: list[int],
    blocked_tactics: set[str] | None = None,
    goal_cache: GoalCache | None = None,
    goal_sig_config: GoalSignatureConfig | None = None,
    mcts_mode: str = "centralized",
    distributed_settings: dict[str, Any] | None = None,
    progress: CorpusProgress | None = None,
    trace: MCTSTraceWriter | None = None,
    rng: random.Random | None = None,
    provenance: str = "mcts",
    search_policy: SearchPolicy = SearchPolicy.UCB1,
    tactic_ranker: TacticRanker | None = None,
    tactic_ranker_agent: TacticRankerAgent | None = None,
    tie_breaker: TieBreaker | None = None,
    tie_breaker_agent: TieBreakerAgent | None = None,
    collect_solution_artifacts: bool = True,
) -> RunResult:
    graph = ProofGraph.for_search_trace(backend="lean", provenance=provenance)
    history = ExplorationHistory.create(statement, blocked_tactics)
    tree = None
    solved_at_tier = None
    progress_callback = progress.make_callback() if progress else None

    if goal_sig_config is None:
        raise ValueError("goal_sig_config is required")

    for tier_idx, budget in enumerate(budget_tiers):
        if progress:
            progress.start_tier(tier_idx, budget)
        trace_context = {"tier": tier_idx, "budget": budget} if trace else None
        tree = await _run_search_budget(
            statement=statement,
            adapter=adapter,
            provider=provider,
            graph=graph,
            history=history,
            goal_cache=goal_cache,
            goal_sig_config=goal_sig_config,
            mcts_mode=mcts_mode,
            budget=budget,
            tree=tree,
            distributed_settings=distributed_settings,
            progress_callback=progress_callback,
            trace=trace,
            trace_context=trace_context,
            rng=rng,
            search_policy=search_policy,
            tactic_ranker=tactic_ranker,
            tactic_ranker_agent=tactic_ranker_agent,
            tie_breaker=tie_breaker,
            tie_breaker_agent=tie_breaker_agent,
        )
        if tree.is_solved():
            solved_at_tier = tier_idx
            break

    if tree is None:
        raise RuntimeError("No budget tiers provided for theorem run")

    proof_term = None
    if tree.is_solved():
        solution_path = tree.extract_winning_tactics()
        if solution_path is None:
            raise ValueError("Solved tree missing solution path")
        history.solution_path = solution_path
        if collect_solution_artifacts:
            proof_term = adapter.get_proof_term()
            if proof_term is None:
                proof_term = await adapter.reconstruct_proof_term(solution_path=solution_path)
    assembly_trace = (
        adapter.get_assembly_trace() if tree.is_solved() and collect_solution_artifacts else None
    )
    stats = tree.stats()
    stats["solved_at_tier"] = solved_at_tier
    stats["budget_tiers"] = budget_tiers
    return _lean_helpers().RunResult(
        solved=tree.is_solved(),
        stats=stats,
        graph=graph,
        history=history,
        proof_term=proof_term,
        assembly_trace=assembly_trace,
        mcts_tree=tree,
    )


async def run_theorem(
    adapter: LeanAdapter,
    theorem: Theorem,
    base_provider: TacticProvider,
    budget_tiers: list[int],
    counter: list[int],
    skip_interventions: bool = False,
    goal_cache: GoalCache | None = None,
    goal_sig_config: GoalSignatureConfig | None = None,
    mcts_mode: str = "centralized",
    distributed_settings: dict[str, Any] | None = None,
    progress: CorpusProgress | None = None,
    log_dir: Path | None = None,
    theorem_idx: int = 0,
    trace_mcts: bool = False,
    search_seed: int | None = None,
    intervention_names: list[str] | None = None,
    extra_interventions: list[Intervention] | None = None,
    tactic_ranker: TacticRanker | None = None,
    tactic_ranker_agent: TacticRankerAgent | None = None,
    tie_breaker: TieBreaker | None = None,
    tie_breaker_agent: TieBreakerAgent | None = None,
    collect_solution_artifacts: bool = True,
) -> TheoremResult | None:
    logger = logging.getLogger("orchestrator.lean")
    logger.info(f"Running theorem: {theorem.name}")

    if goal_sig_config is None:
        raise ValueError("goal_sig_config is required")

    if progress:
        progress.start_theorem(theorem.name, theorem_idx, len(budget_tiers))

    if trace_mcts and log_dir is None:
        raise ValueError("log_dir is required when trace_mcts is enabled")

    theorem_search_seed = (
        _derive_search_seed(search_seed, theorem.name) if search_seed is not None else None
    )
    variant_kwargs: dict[str, Any] = {
        "adapter": adapter,
        "theorem": theorem,
        "budget_tiers": budget_tiers,
        "goal_cache": goal_cache,
        "goal_sig_config": goal_sig_config,
        "mcts_mode": mcts_mode,
        "distributed_settings": distributed_settings,
        "progress": progress,
        "log_dir": log_dir,
        "trace_mcts": trace_mcts,
        "theorem_search_seed": theorem_search_seed,
        "tactic_ranker": tactic_ranker,
        "tactic_ranker_agent": tactic_ranker_agent,
        "tie_breaker": tie_breaker,
        "tie_breaker_agent": tie_breaker_agent,
        "collect_solution_artifacts": collect_solution_artifacts,
    }
    counter[0] += 1
    wild_statement = make_unique_name(theorem, f"w{counter[0]}")
    wild_result = await _run_theorem_variant(
        provider=base_provider,
        statement=wild_statement,
        variant_seed_key="wild",
        trace_filename="wild_type_mcts_trace.jsonl",
        **variant_kwargs,
    )
    was_aborted = wild_result.mcts_tree is not None and wild_result.mcts_tree.aborted
    if was_aborted:
        logger.warning("  Wild type: ABORTED (degenerate search)")
    else:
        logger.info(f"  Wild type: {'SOLVED' if wild_result.solved else 'FAILED'}")

    if progress:
        progress.end_theorem(wild_result.solved, aborted=was_aborted)

    result = _lean_helpers().TheoremResult(
        theorem=theorem,
        wild_type=wild_result,
        search_seed=theorem_search_seed,
    )

    if not wild_result.solved:
        if was_aborted:
            logger.warning("  Skipping interventions - wild type aborted")
            return result
        logger.warning("  Wild type failed; running interventions anyway")

    if skip_interventions:
        return result

    interventions = theorem.generate_interventions(wild_result.history)
    interventions = _merge_interventions(interventions, list(extra_interventions or []))
    interventions = _select_interventions(interventions, intervention_names)
    if not interventions:
        logger.warning("  No interventions generated")
        return result

    wild_solution_goal_sigs = _solution_goal_sigs(wild_result)

    for intervention in interventions:
        counter[0] += 1
        int_statement = make_unique_name(theorem, f"i{counter[0]}")
        filtered = FilteredTacticProvider(
            base_provider,
            intervention.blocked,
            goal_sig_config=goal_sig_config,
        )
        logger.info(f"  {intervention.name}: using {filtered.describe()}")

        if progress:
            progress.start_intervention(intervention.name)

        int_result = await _run_theorem_variant(
            provider=filtered,
            statement=int_statement,
            variant_seed_key=intervention.name,
            trace_filename=f"{intervention.name}_mcts_trace.jsonl",
            blocked_tactics=intervention.blocked,
            **variant_kwargs,
        )

        wild_canonical = wild_result.graph.to_canonical()
        int_canonical = int_result.graph.to_canonical()
        ged = _canonical_graph_edit_distance(wild_canonical, int_canonical)
        if ged is None:
            raise TimeoutError("Graph edit distance computation timed out")
        wild_size = wild_canonical.number_of_nodes() + wild_canonical.number_of_edges()
        int_size = int_canonical.number_of_nodes() + int_canonical.number_of_edges()
        max_size = max(wild_size, int_size)
        normalized_ged = ged / max_size if max_size > 0 else None

        status = "SOLVED" if int_result.solved else "FAILED"
        logger.info(f"  {intervention.name}: {status}, GED={ged:.1f}")

        if progress:
            progress.end_theorem(int_result.solved)

        trajectory_comp = None
        if wild_solution_goal_sigs and int_result.mcts_tree:
            trajectory_comp = compare_trajectories(
                wild_solution_goal_sigs,
                int_result.history,
                int_result.mcts_tree,
            )

        result.interventions.append(
            _lean_helpers().InterventionResult(
                intervention=intervention,
                wild_type=wild_result,
                intervention_run=int_result,
                ged=ged,
                ged_normalized=normalized_ged,
                trajectory_comparison=trajectory_comp,
            )
        )

    return result
