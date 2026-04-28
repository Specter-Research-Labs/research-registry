from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

RAW_ARTIFACT_CAPABILITY_KEYS = (
    "has_search_graph",
    "has_proof_graph",
    "has_trace_graph",
    "has_history",
    "has_goal_cache",
    "has_mcts_tree",
    "has_mcts_trace",
    "has_process_trace",
)

CONDITIONAL_OUTPUT_CAPABILITY_KEYS = (
    "has_proof_term",
    "has_proof_term_pretty",
    "has_assembly_trace",
    "has_proof_term_metrics",
)

RUN_CAPABILITY_KEYS = RAW_ARTIFACT_CAPABILITY_KEYS + CONDITIONAL_OUTPUT_CAPABILITY_KEYS


def default_run_capabilities() -> dict[str, bool]:
    return {key: False for key in RUN_CAPABILITY_KEYS}


def normalize_run_capabilities(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    normalized = default_run_capabilities()
    if raw is None:
        return normalized

    extras: dict[str, bool] = {}
    for key, value in raw.items():
        key_str = str(key)
        if key_str in normalized:
            normalized[key_str] = bool(value)
        else:
            # Preserve forward-compatible flags so status rewrites do not erase them.
            extras[key_str] = bool(value)
    normalized.update(extras)
    return normalized


def build_lean_run_capabilities(
    results: list[Any],
    *,
    has_goal_cache: bool,
    has_mcts_trace: bool,
) -> dict[str, bool]:
    def any_artifact(predicate: Callable[[Any], bool]) -> bool:
        return any(
            predicate(result.wild_type)
            or any(
                predicate(intervention.intervention_run)
                for intervention in result.interventions
            )
            for result in results
        )

    has_proof_term = any_artifact(lambda run: bool(run.proof_term))
    has_assembly_trace = any_artifact(lambda run: bool(run.assembly_trace))
    has_mcts_tree = any_artifact(lambda run: bool(run.mcts_tree))
    has_history = any_artifact(lambda run: bool(run.history))
    return normalize_run_capabilities(
        {
            "has_search_graph": bool(results),
            "has_proof_graph": False,
            "has_trace_graph": False,
            "has_history": has_history,
            "has_goal_cache": has_goal_cache,
            "has_mcts_tree": has_mcts_tree,
            "has_mcts_trace": has_mcts_trace and bool(results),
            "has_proof_term": has_proof_term,
            "has_proof_term_pretty": has_proof_term,
            "has_assembly_trace": has_assembly_trace,
            "has_proof_term_metrics": has_proof_term,
        }
    )
