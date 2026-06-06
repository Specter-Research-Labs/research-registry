from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from analysis.trajectory import TrajectoryComparison
from corpus.lean.theorems import Intervention, Theorem
from orchestrator.lean_metadata import (
    load_existing_run_config as _load_existing_run_config,
)
from prover import (
    ExplorationHistory,
    ExprDAG,
    GoalCache,
    MCTSTree,
    ProofAssemblyTrace,
    ProofGraph,
)
from prover.goal_signature import GoalSignatureConfig

if TYPE_CHECKING:
    from orchestrator.lean import InterventionResult, RunResult, TheoremResult


THEOREM_RESULT_CHECKPOINT_NAME = "theorem_result.checkpoint.json.gz"


def _lean_helpers():
    from orchestrator import lean as lean_mod

    return lean_mod


def _run_result_type():
    return _lean_helpers().RunResult


def _intervention_result_type():
    return _lean_helpers().InterventionResult


def _theorem_result_type():
    return _lean_helpers().TheoremResult


def _trajectory_comparison_from_payload(data: Mapping[str, Any]) -> TrajectoryComparison:
    return TrajectoryComparison(
        wild_solution_goal_sigs=[str(item) for item in data.get("wild_solution_goal_sigs", [])],
        intervention_goal_sequence=[
            str(item) for item in data.get("intervention_goal_sequence", [])
        ],
        divergence_iteration=(
            int(data["divergence_iteration"])
            if isinstance(data.get("divergence_iteration"), int)
            else None
        ),
        reconvergence_iteration=(
            int(data["reconvergence_iteration"])
            if isinstance(data.get("reconvergence_iteration"), int)
            else None
        ),
        recovery_iterations=(
            int(data["recovery_iterations"])
            if isinstance(data.get("recovery_iterations"), int)
            else None
        ),
        shared_prefix_length=int(data.get("shared_prefix_length", 0)),
        reconverged=bool(data.get("reconverged")),
    )


def _run_result_payload(result: RunResult) -> dict[str, Any]:
    return {
        "solved": result.solved,
        "stats": result.stats,
        "graph": result.graph.serialize(),
        "history": result.history.serialize(),
        "proof_term": result.proof_term.serialize() if result.proof_term is not None else None,
        "assembly_trace": (
            result.assembly_trace.serialize() if result.assembly_trace is not None else None
        ),
        "mcts_tree": result.mcts_tree.serialize() if result.mcts_tree is not None else None,
    }


def _run_result_from_payload(data: Mapping[str, Any]) -> RunResult:
    graph_payload = data.get("graph")
    history_payload = data.get("history")
    if not isinstance(graph_payload, dict):
        raise ValueError("RunResult payload missing graph")
    if not isinstance(history_payload, dict):
        raise ValueError("RunResult payload missing history")
    proof_term_payload = data.get("proof_term")
    assembly_payload = data.get("assembly_trace")
    mcts_tree_payload = data.get("mcts_tree")
    return _run_result_type()(
        solved=bool(data.get("solved")),
        stats=dict(data.get("stats") or {}),
        graph=ProofGraph.deserialize(graph_payload),
        history=ExplorationHistory.from_json(history_payload),
        proof_term=ExprDAG.from_json(proof_term_payload)
        if isinstance(proof_term_payload, dict)
        else None,
        assembly_trace=ProofAssemblyTrace.from_json(assembly_payload)
        if isinstance(assembly_payload, dict)
        else None,
        mcts_tree=MCTSTree.deserialize(mcts_tree_payload)
        if isinstance(mcts_tree_payload, dict)
        else None,
    )


def _intervention_payload(intervention: Intervention) -> dict[str, Any]:
    return {
        "name": intervention.name,
        "blocked": sorted(intervention.blocked),
        "is_control": intervention.is_control,
    }


def _intervention_from_payload(data: Mapping[str, Any]) -> Intervention:
    return Intervention(
        name=str(data["name"]),
        blocked={str(item) for item in data.get("blocked", [])},
        is_control=bool(data.get("is_control")),
    )


def _intervention_result_payload(result: InterventionResult) -> dict[str, Any]:
    return {
        "intervention": _intervention_payload(result.intervention),
        "wild_type": _run_result_payload(result.wild_type),
        "intervention_run": _run_result_payload(result.intervention_run),
        "ged": result.ged,
        "ged_normalized": result.ged_normalized,
        "trajectory_comparison": (
            result.trajectory_comparison.serialize()
            if result.trajectory_comparison is not None
            else None
        ),
    }


def _intervention_result_from_payload(data: Mapping[str, Any]) -> InterventionResult:
    intervention_payload = data.get("intervention")
    wild_type_payload = data.get("wild_type")
    intervention_run_payload = data.get("intervention_run")
    if not isinstance(intervention_payload, dict):
        raise ValueError("InterventionResult payload missing intervention")
    if not isinstance(wild_type_payload, dict):
        raise ValueError("InterventionResult payload missing wild_type")
    if not isinstance(intervention_run_payload, dict):
        raise ValueError("InterventionResult payload missing intervention_run")
    trajectory_payload = data.get("trajectory_comparison")
    return _intervention_result_type()(
        intervention=_intervention_from_payload(intervention_payload),
        wild_type=_run_result_from_payload(wild_type_payload),
        intervention_run=_run_result_from_payload(intervention_run_payload),
        ged=(
            float(data["ged"])
            if isinstance(data.get("ged"), (int, float))
            else None
        ),
        ged_normalized=(
            float(data["ged_normalized"])
            if isinstance(data.get("ged_normalized"), (int, float))
            else None
        ),
        trajectory_comparison=_trajectory_comparison_from_payload(trajectory_payload)
        if isinstance(trajectory_payload, dict)
        else None,
    )


def _theorem_result_payload(result: TheoremResult) -> dict[str, Any]:
    return {
        "format_version": 1,
        "theorem": {
            "name": result.theorem.name,
            "statement": result.theorem.statement,
        },
        "wild_type": _run_result_payload(result.wild_type),
        "interventions": [_intervention_result_payload(item) for item in result.interventions],
        "search_seed": result.search_seed,
    }


def _theorem_result_from_payload(data: Mapping[str, Any]) -> TheoremResult:
    theorem_payload = data.get("theorem")
    wild_type_payload = data.get("wild_type")
    if not isinstance(theorem_payload, dict):
        raise ValueError("TheoremResult payload missing theorem")
    if not isinstance(wild_type_payload, dict):
        raise ValueError("TheoremResult payload missing wild_type")
    theorem = Theorem(
        name=str(theorem_payload["name"]),
        statement=str(theorem_payload["statement"]),
    )
    return _theorem_result_type()(
        theorem=theorem,
        wild_type=_run_result_from_payload(wild_type_payload),
        interventions=[
            _intervention_result_from_payload(item)
            for item in data.get("interventions", [])
            if isinstance(item, dict)
        ],
        search_seed=(
            int(data["search_seed"]) if isinstance(data.get("search_seed"), int) else None
        ),
    )


def _theorem_result_checkpoint_path(log_dir: Path, theorem_name: str) -> Path:
    return log_dir / theorem_name / THEOREM_RESULT_CHECKPOINT_NAME


def _write_json_gz_atomic(path: Path, payload: Any, *, indent: int | None = 2) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=indent)
    tmp_path.replace(path)
    if not path.exists():
        raise RuntimeError(f"Missing after atomic write: {path}")


def _write_theorem_result_checkpoint(log_dir: Path, result: TheoremResult) -> Path:
    theorem_dir = log_dir / result.theorem.name
    theorem_dir.mkdir(parents=True, exist_ok=True)
    path = _theorem_result_checkpoint_path(log_dir, result.theorem.name)
    _write_json_gz_atomic(path, _theorem_result_payload(result))
    return path


def _load_theorem_result_checkpoint(path: Path) -> TheoremResult:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid theorem checkpoint payload: {path}")
    return _theorem_result_from_payload(payload)


def _goal_cache_exists(log_dir: Path) -> bool:
    return (log_dir / "goal_cache.json").exists() or (log_dir / "goal_cache.json.gz").exists()


def _load_resume_goal_cache(
    log_dir: Path,
    goal_sig_config: GoalSignatureConfig,
    *,
    logger: logging.Logger,
) -> GoalCache:
    if not _goal_cache_exists(log_dir):
        return GoalCache(goal_sig_config)
    try:
        goal_cache = GoalCache.load(log_dir / "goal_cache.json", goal_sig_config)
        logger.info(
            "Resume prefilter: loaded goal cache with %s signatures and %s occurrences",
            len(goal_cache.entries),
            len(goal_cache.mvar_to_sig),
        )
        return goal_cache
    except Exception as exc:
        logger.warning("Ignoring invalid goal cache for resume: %s", exc)
        return GoalCache(goal_sig_config)


def _resume_checkpointed_theorems(
    indexed_theorems: list[tuple[int, Theorem]],
    *,
    log_dir: Path,
    logger: logging.Logger,
) -> tuple[list[tuple[int, Theorem]], list[TheoremResult]]:
    pending_theorems: list[tuple[int, Theorem]] = []
    resumed_results: list[TheoremResult] = []
    for idx, theorem in indexed_theorems:
        checkpoint_path = _theorem_result_checkpoint_path(log_dir, theorem.name)
        if not checkpoint_path.exists():
            pending_theorems.append((idx, theorem))
            continue
        try:
            checkpoint_result = _load_theorem_result_checkpoint(checkpoint_path)
        except Exception as exc:
            logger.warning(
                "Ignoring invalid theorem checkpoint for %s: %s",
                theorem.name,
                exc,
            )
            pending_theorems.append((idx, theorem))
            continue
        if (
            checkpoint_result.theorem.name != theorem.name
            or checkpoint_result.theorem.statement != theorem.statement
        ):
            logger.warning(
                "Ignoring theorem checkpoint with mismatched theorem payload: %s",
                checkpoint_path,
            )
            pending_theorems.append((idx, theorem))
            continue
        resumed_results.append(checkpoint_result)
    return pending_theorems, resumed_results


def _resume_selected_theorems(
    theorem_corpus: list[Theorem],
    *,
    log_dir: Path,
    corpus: str,
) -> tuple[list[Theorem], int | None] | None:
    run_config = _load_existing_run_config(log_dir)
    if run_config is None:
        return None
    saved_corpus = run_config.get("corpus_spec")
    if saved_corpus != corpus:
        raise ValueError(
            "resume run_config corpus_spec mismatch: "
            f"saved={saved_corpus!r} current={corpus!r}"
        )
    selection = run_config.get("theorem_selection")
    if not isinstance(selection, dict):
        return None
    selected = selection.get("selected_theorems")
    if not isinstance(selected, list) or not selected:
        return None
    if not all(isinstance(item, str) and item for item in selected):
        raise ValueError("resume run_config selected_theorems must be a non-empty string list")

    theorem_by_name = {theorem.name: theorem for theorem in theorem_corpus}
    missing = [name for name in selected if name not in theorem_by_name]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "..." if len(missing) > 5 else ""
        raise ValueError(
            "resume selected_theorems missing from current corpus: "
            f"{preview}{suffix}"
        )
    raw_seed = selection.get("selection_seed")
    selection_seed = raw_seed if isinstance(raw_seed, int) else None
    return [theorem_by_name[name] for name in selected], selection_seed
