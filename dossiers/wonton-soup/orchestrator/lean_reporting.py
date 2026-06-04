from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from analysis.attractors import cluster_proof_structures
from corpus.artifacts import write_json_atomic
from orchestrator import lean_checkpoints as _lean_checkpoints
from orchestrator import lean_runner as _lean_runner
from prover import ExprDAG, ProofGraph

if TYPE_CHECKING:
    from corpus.lean.theorems import Theorem
    from orchestrator.lean import (
        CrashedTheorem,
        InterventionResult,
        RunLifecycle,
        RunResult,
        TheoremResult,
    )
    from orchestrator.lean_progress import CorpusProgress
    from prover import GoalCache
    from prover.goal_signature import GoalSignatureConfig


def _lean_helpers():
    from orchestrator import lean as lean_mod

    return lean_mod


def _optional_nonnegative_int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(value, 0)


def _optional_positive_int_env(name: str) -> int | None:
    value = _optional_nonnegative_int_env(name)
    if value is None or value == 0:
        return None
    return value


def _graph_size(graph: ProofGraph) -> tuple[int, int]:
    return graph.graph.number_of_nodes(), graph.graph.number_of_edges()


def compute_pairwise_ged(result: TheoremResult) -> dict[str, Any]:
    variants = [("wild_type", result.wild_type.graph)]
    for int_result in result.interventions:
        variants.append((int_result.intervention.name, int_result.intervention_run.graph))

    max_variants = _optional_nonnegative_int_env("WONTON_SUMMARY_MAX_PAIRWISE_GED_VARIANTS")
    max_nodes = _optional_positive_int_env("WONTON_SUMMARY_MAX_PAIRWISE_GED_NODES")
    max_edges = _optional_positive_int_env("WONTON_SUMMARY_MAX_PAIRWISE_GED_EDGES")
    run_skip_reason = None
    if max_variants is not None and len(variants) > max_variants:
        run_skip_reason = f"variant_count>{max_variants}"

    graph_sizes = {name: _graph_size(graph) for name, graph in variants}
    skipped_pairs = 0
    matrix: dict[str, dict[str, float | None]] = {}
    for name1, graph1 in variants:
        matrix[name1] = {}
        for name2, graph2 in variants:
            if name1 == name2:
                matrix[name1][name2] = 0.0
            elif run_skip_reason is not None:
                matrix[name1][name2] = None
                skipped_pairs += 1
            else:
                nodes1, edges1 = graph_sizes[name1]
                nodes2, edges2 = graph_sizes[name2]
                if max_nodes is not None and max(nodes1, nodes2) > max_nodes:
                    matrix[name1][name2] = None
                    skipped_pairs += 1
                    continue
                if max_edges is not None and max(edges1, edges2) > max_edges:
                    matrix[name1][name2] = None
                    skipped_pairs += 1
                    continue
                try:
                    matrix[name1][name2] = _lean_runner._canonical_graph_edit_distance(
                        graph1.to_canonical(),
                        graph2.to_canonical(),
                    )
                except Exception:
                    matrix[name1][name2] = None

    return {
        "theorem": result.theorem.name,
        "variants": [variant[0] for variant in variants],
        "ged_matrix": matrix,
        "ged_policy": {
            "max_variants": max_variants,
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "skip_reason": run_skip_reason,
            "skipped_pairs": skipped_pairs,
        },
    }


def _build_ged_entry(
    value: float | None,
    *,
    normalized: float | None,
    trace_source: str,
    trace_completeness: str,
    valid: bool,
    validity_notes: list[str] | None = None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "value": value,
        "normalized": normalized,
        "valid": valid,
        "validity_notes": validity_notes or [],
        "trace_source": trace_source,
        "trace_completeness": trace_completeness,
    }


def _extract_root_goal_sigs(graph: ProofGraph) -> list[str]:
    graph_nx = graph.to_networkx()
    roots = [node for node in graph_nx.nodes if graph_nx.in_degree(node) == 0]
    sigs: list[str] = []
    for node in roots:
        sig = graph_nx.nodes[node].get("goal_sig")
        if isinstance(sig, str):
            sigs.append(sig)
    return sorted(set(sigs))


def _merge_goal_type_tactic_matrix(
    aggregate: dict[str, dict[str, dict[str, int]]],
    matrix: dict[str, dict[str, dict[str, int]]],
) -> None:
    for goal_type, tactics in matrix.items():
        aggregate_goal_type = aggregate.setdefault(goal_type, {})
        for tactic, counts in tactics.items():
            aggregate_counts = aggregate_goal_type.setdefault(
                tactic,
                {"success": 0, "failure": 0, "blocked": 0},
            )
            for outcome, count in counts.items():
                aggregate_counts[outcome] += count


def _run_result_metrics(
    run_result: RunResult,
    *,
    include_root_goal_sigs: bool = False,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "trajectory": run_result.history.trajectory_metrics(),
        "detour": run_result.history.detour_metrics(),
        "proof_term": run_result.proof_term.metrics() if run_result.proof_term else None,
        "solution_path": run_result.mcts_tree.extract_winning_tactics()
        if run_result.mcts_tree
        else None,
        "proof_term_pretty": run_result.proof_term.to_lean_string()
        if run_result.proof_term
        else None,
    }
    if include_root_goal_sigs:
        metrics["tactic_fingerprint"] = (
            run_result.history.tactic_fingerprint() if run_result.solved else None
        )
        metrics["root_goal_sigs"] = _extract_root_goal_sigs(run_result.graph)
    return metrics


def _write_run_result_artifacts(
    theorem_dir: Path,
    *,
    stem: str,
    run_result: RunResult,
    include_root_goal_sigs: bool = False,
) -> dict[str, Any]:
    write_json_atomic(theorem_dir / f"{stem}_graph.json", run_result.graph.serialize())
    write_json_atomic(theorem_dir / f"{stem}_history.json", run_result.history.serialize())

    if run_result.assembly_trace:
        _lean_checkpoints._write_json_gz_atomic(
            theorem_dir / f"{stem}_assembly.json.gz",
            run_result.assembly_trace.serialize(),
            indent=None,
        )

    if run_result.proof_term:
        _lean_checkpoints._write_json_gz_atomic(
            theorem_dir / f"{stem}_proof_term.json.gz",
            run_result.proof_term.serialize(),
            indent=None,
        )

    if run_result.mcts_tree:
        write_json_atomic(theorem_dir / f"{stem}_mcts_tree.json", run_result.mcts_tree.serialize())

    metrics = _run_result_metrics(
        run_result,
        include_root_goal_sigs=include_root_goal_sigs,
    )
    write_json_atomic(theorem_dir / f"{stem}_metrics.json", metrics)
    return metrics


_POSTPROCESS_PENDING_NOTE = (
    "not computed in-run; run `wonton.py postprocess` to fill this metric"
)


@dataclass(frozen=True)
class _ProofTermSnapshot:
    term: ExprDAG | None
    structural_hash: str | None
    axioms: dict[str, Any] | None


def _proof_term_snapshot(term: ExprDAG | None) -> _ProofTermSnapshot:
    if term is None:
        return _ProofTermSnapshot(term=None, structural_hash=None, axioms=None)
    return _ProofTermSnapshot(
        term=term,
        structural_hash=term.structural_hash(),
        axioms=term.axiom_fingerprint(),
    )


def _axiom_delta(
    baseline_axioms: dict[str, Any] | None,
    variant_axioms: dict[str, Any] | None,
) -> tuple[list[str] | None, list[str] | None]:
    if baseline_axioms is None or variant_axioms is None:
        return None, None
    baseline_all = baseline_axioms.get("all")
    variant_all = variant_axioms.get("all")
    if not isinstance(baseline_all, list) or not isinstance(variant_all, list):
        return None, None
    baseline_set = {str(item) for item in baseline_all}
    variant_set = {str(item) for item in variant_all}
    return sorted(variant_set - baseline_set), sorted(baseline_set - variant_set)


def _compare_proof_terms(
    baseline: _ProofTermSnapshot,
    variant: _ProofTermSnapshot,
    *,
    graph_distance: float,
) -> dict[str, Any]:
    axiom_delta, axiom_removed = _axiom_delta(baseline.axioms, variant.axioms)
    hash_mismatch = (
        baseline.structural_hash != variant.structural_hash
        if baseline.structural_hash and variant.structural_hash
        else None
    )
    proof_term_diff = None
    if (graph_distance > 0 or hash_mismatch) and baseline.term and variant.term:
        proof_term_diff = baseline.term.structural_diff(variant.term)
    return {
        "wild_type_hash": baseline.structural_hash,
        "intervention_hash": variant.structural_hash,
        "hash_mismatch": hash_mismatch,
        "wild_type_axioms": baseline.axioms,
        "intervention_axioms": variant.axioms,
        "axiom_delta": axiom_delta,
        "axiom_removed": axiom_removed,
        "proof_term_diff": proof_term_diff,
    }


def _pending_ged_search_graph_soft() -> dict[str, Any]:
    return {
        "value": None,
        "normalized": None,
        "valid": False,
        "validity_notes": [_POSTPROCESS_PENDING_NOTE],
        "trace_source": "mcts",
        "trace_completeness": "full",
    }


def _pending_goal_novelty() -> dict[str, Any]:
    return {
        "valid": False,
        "validity_notes": [_POSTPROCESS_PENDING_NOTE],
    }


def _pending_solution_path_soft_distance(
    *,
    wild_len: int,
    intervention_len: int,
) -> dict[str, Any]:
    return {
        "value": None,
        "valid": False,
        "validity_notes": [_POSTPROCESS_PENDING_NOTE],
        "wild_len": wild_len,
        "intervention_len": intervention_len,
        "dp_cells": wild_len * intervention_len,
    }


def _trajectory_diff(
    baseline_trajectory: dict[str, Any],
    variant_trajectory: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration_diff": variant_trajectory["total_iterations"]
        - baseline_trajectory["total_iterations"],
        "backtrack_diff": variant_trajectory["backtrack_count"]
        - baseline_trajectory["backtrack_count"],
    }


def _build_intervention_outputs(
    *,
    baseline_result: TheoremResult,
    intervention_result: InterventionResult,
    intervention_metrics: dict[str, Any],
    baseline_trajectory: dict[str, Any],
    baseline_solution_goal_sigs: list[str],
    baseline_proof: _ProofTermSnapshot,
) -> tuple[dict[str, Any], dict[str, Any]]:
    blocked = sorted(intervention_result.intervention.blocked)
    status = "solved" if intervention_result.intervention_run.solved else "failed"
    ged_search_graph = _build_ged_entry(
        intervention_result.ged,
        normalized=intervention_result.ged_normalized,
        trace_source="mcts",
        trace_completeness="full",
        valid=True,
        validity_notes=[],
    )
    ged_search_graph_soft = _pending_ged_search_graph_soft()
    goal_novelty = _pending_goal_novelty()
    variant_trajectory = intervention_result.intervention_run.history.trajectory_metrics()
    intervention_solution_goal_sigs = _lean_runner._solution_goal_sigs(
        intervention_result.intervention_run
    )
    solution_path_soft_distance = _pending_solution_path_soft_distance(
        wild_len=len(baseline_solution_goal_sigs),
        intervention_len=len(intervention_solution_goal_sigs),
    )
    proof_term_comparison = _compare_proof_terms(
        baseline_proof,
        _proof_term_snapshot(intervention_result.intervention_run.proof_term),
        graph_distance=intervention_result.ged,
    )
    comparison = {
        "name": intervention_result.intervention.name,
        "blocked": blocked,
        "solved": intervention_result.intervention_run.solved,
        "status": status,
        "ged_search_graph": ged_search_graph,
        "ged_search_graph_soft": ged_search_graph_soft,
        "ged_proof_graph": None,
        "ged_trace_graph": None,
        "goal_novelty": goal_novelty,
        "solution_path_soft_distance": solution_path_soft_distance,
        "trajectory_diff": _trajectory_diff(baseline_trajectory, variant_trajectory),
        "trajectory_comparison": intervention_result.trajectory_comparison.serialize()
        if intervention_result.trajectory_comparison
        else None,
        **proof_term_comparison,
    }
    summary = {
        "name": intervention_result.intervention.name,
        "blocked": blocked,
        "is_control": intervention_result.intervention.is_control,
        "baseline_solved": baseline_result.wild_type.solved,
        "solved": intervention_result.intervention_run.solved,
        "status": status,
        "ged_search_graph": ged_search_graph,
        "ged_search_graph_soft": ged_search_graph_soft,
        "ged_proof_graph": None,
        "ged_trace_graph": None,
        "axiom_delta": proof_term_comparison["axiom_delta"],
        "axiom_removed": proof_term_comparison["axiom_removed"],
        "goal_novelty": goal_novelty,
        "solution_path_soft_distance": solution_path_soft_distance,
        "metrics": intervention_metrics,
    }
    return comparison, summary


_GED_VALIDITY_KEYS = (
    "ged_search_graph",
    "ged_search_graph_soft",
    "ged_proof_graph",
    "ged_trace_graph",
)


def _empty_ged_validity() -> dict[str, dict[str, int]]:
    return {key: {"valid": 0, "invalid": 0} for key in _GED_VALIDITY_KEYS}


def _update_ged_validity(
    ged_validity: dict[str, dict[str, int]],
    intervention_summary: dict[str, Any],
) -> None:
    for key in _GED_VALIDITY_KEYS:
        entry = intervention_summary.get(key)
        if not isinstance(entry, dict):
            continue
        bucket = "valid" if entry.get("valid") is True else "invalid"
        ged_validity[key][bucket] += 1


def _build_theorem_summary(
    *,
    result: TheoremResult,
    wild_metrics: dict[str, Any],
    intervention_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": result.theorem.name,
        "search_seed": result.search_seed,
        "wild_type": {
            "solved": result.wild_type.solved,
            "iterations": result.wild_type.history.trajectory_metrics()["total_iterations"],
            "proof_term_hash": result.wild_type.proof_term.structural_hash()
            if result.wild_type.proof_term
            else None,
            "metrics": wild_metrics,
        },
        "interventions": intervention_summaries,
    }


def save_results(
    log_dir: Path,
    results: list[TheoremResult],
    crashed: list[CrashedTheorem] | None = None,
    goal_sig_config: GoalSignatureConfig | None = None,
) -> None:
    all_ged_matrices = []
    summary_theorems = []
    aggregate_goal_type_matrix: dict[str, dict[str, dict[str, int]]] = {}
    ged_validity = _empty_ged_validity()
    wild_solved = 0
    total_interventions = 0
    solved_interventions = 0

    for result in results:
        theorem_dir = log_dir / result.theorem.name
        theorem_dir.mkdir(parents=True, exist_ok=True)
        if result.wild_type.solved:
            wild_solved += 1

        wild_metrics = _write_run_result_artifacts(
            theorem_dir,
            stem="wild_type",
            run_result=result.wild_type,
            include_root_goal_sigs=True,
        )
        _merge_goal_type_tactic_matrix(
            aggregate_goal_type_matrix,
            result.wild_type.history.goal_type_tactic_matrix(),
        )

        intervention_summaries: list[dict[str, Any]] = []
        wild_traj = result.wild_type.history.trajectory_metrics()
        wild_solution_goal_sigs = _lean_runner._solution_goal_sigs(result.wild_type)
        wild_proof = _proof_term_snapshot(result.wild_type.proof_term)

        for int_result in result.interventions:
            name = int_result.intervention.name
            int_metrics = _write_run_result_artifacts(
                theorem_dir,
                stem=name,
                run_result=int_result.intervention_run,
            )
            comparison, intervention_summary = _build_intervention_outputs(
                baseline_result=result,
                intervention_result=int_result,
                intervention_metrics=int_metrics,
                baseline_trajectory=wild_traj,
                baseline_solution_goal_sigs=wild_solution_goal_sigs,
                baseline_proof=wild_proof,
            )
            write_json_atomic(theorem_dir / f"{name}_comparison.json", comparison)

            intervention_summaries.append(intervention_summary)
            total_interventions += 1
            if int_result.intervention_run.solved:
                solved_interventions += 1
            _update_ged_validity(ged_validity, intervention_summary)

            _merge_goal_type_tactic_matrix(
                aggregate_goal_type_matrix,
                int_result.intervention_run.history.goal_type_tactic_matrix(),
            )

        summary_theorems.append(
            _build_theorem_summary(
                result=result,
                wild_metrics=wild_metrics,
                intervention_summaries=intervention_summaries,
            )
        )

        ged_matrix = compute_pairwise_ged(result)
        write_json_atomic(theorem_dir / "ged_matrix.json", ged_matrix)
        all_ged_matrices.append(ged_matrix)

        if len(ged_matrix["variants"]) >= 2:
            attractor_analysis = cluster_proof_structures(
                ged_matrix["ged_matrix"],
                distance_threshold=3.0,
                theorem_name=result.theorem.name,
            )
            write_json_atomic(
                theorem_dir / "attractor_clusters.json",
                attractor_analysis.serialize(),
            )

    write_json_atomic(log_dir / "all_ged_matrices.json", all_ged_matrices)

    crashed_list = [crash.serialize() for crash in (crashed or [])]
    run_stats = _compute_run_stats(results, crashed)

    summary = {
        "run_id": log_dir.name,
        "theorems": summary_theorems,
        "crashed": crashed_list,
        "goal_sig_scheme": goal_sig_config.scheme if goal_sig_config else None,
        "goal_sig_stats": {
            "ast_missing": goal_sig_config.stats.ast_missing,
        }
        if goal_sig_config
        else None,
        "aggregates": {
            "theorem_count": len(results),
            "crashed_count": len(crashed_list),
            "wild_type_solve_rate": wild_solved / len(results) if results else 0,
            "intervention_count": total_interventions,
            "intervention_solve_rate": solved_interventions / total_interventions
            if total_interventions
            else 0,
            "ged_validity": ged_validity,
            "goal_type_tactic_matrix": aggregate_goal_type_matrix,
            "run_stats": run_stats,
        },
    }
    _lean_checkpoints._write_json_gz_atomic(log_dir / "summary.json.gz", summary, indent=None)


def _list_theorem_dirs(log_dir: Path) -> list[Path]:
    return [
        theorem_dir
        for theorem_dir in sorted(log_dir.iterdir())
        if theorem_dir.is_dir() and not theorem_dir.name.startswith(".")
    ]


def run_post_analysis(log_dir: Path) -> None:
    from analysis.corpus import analyze_theorem
    from analysis.corpus import generate_report as corpus_report
    from analysis.failures import analyze_failed_theorem
    from analysis.failures import generate_report as failure_report

    failures: list = []
    analyses = []
    for theorem_dir in _list_theorem_dirs(log_dir):
        result = analyze_failed_theorem(theorem_dir)
        if result is not None:
            failures.append(result)
        analyses.extend(analyze_theorem(theorem_dir))
    if failures:
        report = failure_report(failures, log_dir)
        write_json_atomic(log_dir / "failure_analysis.json", report)

    if analyses:
        report = corpus_report(analyses, log_dir)
        write_json_atomic(log_dir / "analysis_report.json", report)


def _write_postprocess_metrics(
    log_dir: Path,
    *,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    from analysis.postprocess_metrics import PostprocessParams, postprocess_run

    report = postprocess_run(log_dir, params=PostprocessParams(), progress_cb=progress_cb)
    write_json_atomic(log_dir / "postprocess_metrics.json", report)
    return report


def _compute_run_stats(
    results: list[TheoremResult],
    crashed: list[CrashedTheorem] | None = None,
) -> dict:
    crashed_count = len(crashed) if crashed else 0
    total = len(results)
    wild_solved = sum(1 for r in results if r.wild_type.solved)
    wild_aborted = sum(
        1 for r in results if r.wild_type.mcts_tree and r.wild_type.mcts_tree.aborted
    )
    total_interventions = sum(len(r.interventions) for r in results)
    solved_interventions = sum(
        1 for r in results for i in r.interventions if i.intervention_run.solved
    )
    wild_iters = [
        r.wild_type.history.trajectory_metrics().get("total_iterations", 0) for r in results
    ]
    avg_iters = round(sum(wild_iters) / len(wild_iters)) if wild_iters else None
    return {
        "theorem_total": total,
        "crashed": crashed_count,
        "wild_solved": wild_solved,
        "wild_aborted": wild_aborted,
        "intervention_total": total_interventions,
        "intervention_solved": solved_interventions,
        "avg_iters": avg_iters,
    }


def _summarize_from_summary(summary: dict) -> dict:
    aggregates = summary.get("aggregates")
    if isinstance(aggregates, dict):
        run_stats = aggregates.get("run_stats")
        required = (
            "theorem_total",
            "crashed",
            "wild_solved",
            "wild_aborted",
            "intervention_total",
            "intervention_solved",
        )
        if isinstance(run_stats, dict) and all(
            isinstance(run_stats.get(key), int) for key in required
        ):
            avg_iters = run_stats.get("avg_iters")
            if avg_iters is None or isinstance(avg_iters, int):
                return {key: run_stats[key] for key in required} | {"avg_iters": avg_iters}

    theorems = summary.get("theorems", [])
    crashed = summary.get("crashed", [])
    wild_solved = sum(1 for t in theorems if t.get("wild_type", {}).get("solved"))
    wild_iters = []
    for t in theorems:
        metrics = t.get("wild_type", {}).get("metrics", {})
        traj = metrics.get("trajectory", {})
        wild_iters.append(traj.get("total_iterations", 0))
    avg_iters = round(sum(wild_iters) / len(wild_iters)) if wild_iters else None

    total_interventions = 0
    solved_interventions = 0
    for t in theorems:
        for i in t.get("interventions", []):
            total_interventions += 1
            if i.get("solved"):
                solved_interventions += 1

    return {
        "theorem_total": len(theorems),
        "crashed": len(crashed),
        "wild_solved": wild_solved,
        "wild_aborted": 0,
        "intervention_total": total_interventions,
        "intervention_solved": solved_interventions,
        "avg_iters": avg_iters,
    }


def _ged_value(entry: Any) -> float | None:
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_wild_metrics(entry: dict) -> tuple[dict[str, Any], dict[str, Any]]:
    wild_raw = entry.get("wild_type")
    wild: dict[str, Any] = wild_raw if isinstance(wild_raw, dict) else {}
    metrics_raw = wild.get("metrics")
    metrics: dict[str, Any] = metrics_raw if isinstance(metrics_raw, dict) else {}
    trajectory_raw = metrics.get("trajectory")
    trajectory: dict[str, Any] = trajectory_raw if isinstance(trajectory_raw, dict) else {}
    proof_raw = metrics.get("proof_term")
    proof: dict[str, Any] = proof_raw if isinstance(proof_raw, dict) else {}
    iterations = wild.get("iterations")
    if not isinstance(iterations, (int, float)):
        iterations = trajectory.get("total_iterations")
    ged_values = []
    interventions = entry.get("interventions", [])
    if not isinstance(interventions, list):
        interventions = []
    for intervention in interventions:
        if not isinstance(intervention, dict):
            continue
        ged_value = _ged_value(intervention.get("ged_search_graph"))
        if isinstance(ged_value, (int, float)):
            ged_values.append(float(ged_value))
    mean_ged = sum(ged_values) / len(ged_values) if ged_values else None
    return (
        {
            "solved": bool(wild.get("solved")),
            "iterations": iterations,
            "max_depth": trajectory.get("max_depth_reached"),
            "backtracks": trajectory.get("backtrack_count"),
            "unique_goals": trajectory.get("unique_goals_visited"),
            "tactic_diversity": trajectory.get("tactic_diversity"),
            "node_count": proof.get("node_count"),
            "mean_ged": mean_ged,
        },
        trajectory,
    )


def _extract_intervention_metrics(
    entry: dict,
    wild_trajectory: dict[str, Any],
) -> dict[str, Any]:
    metrics_raw = entry.get("metrics")
    metrics: dict[str, Any] = metrics_raw if isinstance(metrics_raw, dict) else {}
    trajectory_raw = metrics.get("trajectory")
    trajectory: dict[str, Any] = trajectory_raw if isinstance(trajectory_raw, dict) else {}
    iteration_diff = None
    backtrack_diff = None
    if wild_trajectory and trajectory:
        wild_iters = wild_trajectory.get("total_iterations")
        int_iters = trajectory.get("total_iterations")
        if isinstance(wild_iters, (int, float)) and isinstance(int_iters, (int, float)):
            iteration_diff = int_iters - wild_iters
        wild_back = wild_trajectory.get("backtrack_count")
        int_back = trajectory.get("backtrack_count")
        if isinstance(wild_back, (int, float)) and isinstance(int_back, (int, float)):
            backtrack_diff = int_back - wild_back
    axiom_delta = entry.get("axiom_delta")
    axiom_delta_count = len(axiom_delta) if isinstance(axiom_delta, list) else 0
    return {
        "baseline_solved": entry.get("baseline_solved"),
        "solved": entry.get("solved"),
        "ged": _ged_value(entry.get("ged_search_graph")),
        "iteration_diff": iteration_diff,
        "backtrack_diff": backtrack_diff,
        "axiom_delta_count": axiom_delta_count,
    }


def _build_providers_theorem_summary(
    base_dir: Path,
    run_config: dict[str, Any],
    providers: list[str],
) -> dict[str, Any]:
    provider_meta: list[dict[str, Any]] = []
    provider_theorems: dict[str, dict[str, Any]] = {}
    for provider in providers:
        provider_dir = base_dir / f"provider={provider}"
        summary = _load_summary(provider_dir)
        provider_theorems[provider] = {t.get("name"): t for t in summary.get("theorems", [])}
        provider_config_path = provider_dir / "run_config.json"
        label = provider
        description = None
        if provider_config_path.exists():
            try:
                provider_config = json.loads(provider_config_path.read_text())
                label = provider_config.get("provider_label") or provider
                description = provider_config.get("provider_desc")
            except (OSError, json.JSONDecodeError):
                pass
        provider_meta.append(
            {
                "name": provider,
                "label": label,
                "description": description,
            }
        )

    selection = run_config.get("theorem_selection", {})
    selected = selection.get("selected_theorems") if isinstance(selection, dict) else None
    theorem_names = selected if isinstance(selected, list) else []
    if not theorem_names:
        theorem_names = sorted(
            {name for entries in provider_theorems.values() for name in entries.keys()}
        )

    theorem_rows = []
    for name in theorem_names:
        provider_rows: dict[str, Any] = {}
        for provider in providers:
            entry = provider_theorems.get(provider, {}).get(name)
            if not entry:
                continue
            wild_metrics, wild_traj = _extract_wild_metrics(entry)
            interventions = {}
            for intervention in entry.get("interventions", []):
                if not isinstance(intervention, dict):
                    continue
                int_name = intervention.get("name")
                if not int_name:
                    continue
                interventions[int_name] = _extract_intervention_metrics(intervention, wild_traj)
            provider_rows[provider] = {
                "wild": wild_metrics,
                "interventions": interventions,
            }
        theorem_rows.append({"name": name, "providers": provider_rows})

    return {
        "run_id": run_config.get("run_id"),
        "providers": provider_meta,
        "theorems": theorem_rows,
    }


def _load_summary(log_dir: Path) -> dict:
    summary_path = log_dir / "summary.json.gz"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json.gz in {log_dir}")
    with gzip.open(summary_path, "rt") as f:
        return json.load(f)


def _format_run_summary(
    provider_label: str,
    corpus: str,
    budget_tiers: list[int],
    wild_only: bool,
    trace_mcts: bool,
    stats: dict,
    log_dir: Path,
) -> str:
    lines = [f"Summary: {provider_label}"]
    lines.append(
        f"  corpus: {corpus} | budget: {_lean_helpers()._format_budget_tiers(budget_tiers)}"
    )
    lines.append(f"  theorems: {stats['theorem_total']} (crashed {stats['crashed']})")
    wild_line = f"  wild: {stats['wild_solved']}/{stats['theorem_total']} solved"
    if stats["wild_aborted"] > 0:
        wild_line += f", {stats['wild_aborted']} aborted"
    lines.append(wild_line)
    if stats["intervention_total"] > 0:
        lines.append(
            f"  interventions: {stats['intervention_solved']}/{stats['intervention_total']} solved"
        )
    if stats["avg_iters"] is not None:
        lines.append(f"  avg iters (wild): {stats['avg_iters']}")
    lines.append(
        f"  interventions: {'off' if wild_only else 'on'} | trace: {'on' if trace_mcts else 'off'}"
    )
    lines.append(f"  logs: {log_dir / 'corpus.log'}")
    lines.append(f"  report: {log_dir / 'report.md'}")
    return "\n".join(lines)


def _format_provider_table(rows: list[dict]) -> str:
    headers = ["provider", "wild", "interventions", "crashed", "avg iters"]
    table_rows = []
    for row in rows:
        wild = f"{row['wild_solved']}/{row['theorem_total']}"
        if row["wild_aborted"] > 0:
            wild = f"{wild} (+{row['wild_aborted']} aborted)"
        interventions = (
            f"{row['intervention_solved']}/{row['intervention_total']}"
            if row["intervention_total"] > 0
            else "-"
        )
        table_rows.append(
            [
                row["provider"],
                wild,
                interventions,
                str(row["crashed"]),
                str(row["avg_iters"]) if row["avg_iters"] is not None else "-",
            ]
        )

    widths = [len(h) for h in headers]
    for row in table_rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(col))

    def fmt_row(values: list[str]) -> str:
        padded = [values[i].ljust(widths[i]) for i in range(len(values))]
        return "  " + "  ".join(padded)

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines.extend(fmt_row(row) for row in table_rows)
    return "\n".join(lines)


def _format_multi_provider_summary(
    run_id: str,
    rows: list[dict],
    log_dir: Path,
) -> str:
    lines = [f"Multi-provider summary: {run_id}"]
    lines.append(f"  logs: {log_dir}")
    lines.append("")
    lines.append(_format_provider_table(rows))
    lines.append("")
    lines.append("Reports:")
    for row in rows:
        lines.append(f"  - {row['report_path']}")
    return "\n".join(lines)


def generate_report(
    results: list[TheoremResult],
    crashed: list[CrashedTheorem] | None = None,
) -> str:
    lines = ["# Corpus Experiment Results\n"]
    stats = _compute_run_stats(results, crashed)

    lines.append("## Summary\n")
    lines.append(f"- Theorems attempted: {stats['theorem_total'] + stats['crashed']}")
    if stats["crashed"] > 0:
        lines.append(f"- Theorems crashed: {stats['crashed']} (runtime failures)")
    lines.append(f"- Wild type solved: {stats['wild_solved']}/{stats['theorem_total']}")
    lines.append(f"- Total interventions: {stats['intervention_total']}")
    lines.append(
        f"- Interventions solved: {stats['intervention_solved']}/{stats['intervention_total']}"
    )
    lines.append("")

    if crashed:
        lines.append("## Crashed Theorems\n")
        lines.append("The following theorems crashed during execution and were skipped:\n")
        for c in crashed:
            lines.append(f"- **{c.theorem_name}**: {c.display_error()}")
        lines.append("")

    lines.append("## Results by Theorem\n")

    for result in results:
        lines.append(f"### {result.theorem.name}\n")

        wild_metrics = result.wild_type.history.detour_metrics()
        tier_info = ""
        if (
            "solved_at_tier" in result.wild_type.stats
            and result.wild_type.stats["solved_at_tier"] is not None
        ):
            tier_idx = result.wild_type.stats["solved_at_tier"]
            budget_tiers = result.wild_type.stats.get("budget_tiers", [])
            if budget_tiers:
                tier_budget = budget_tiers[tier_idx]
                tier_info = f", tier {tier_idx + 1}/{len(budget_tiers)} (budget={tier_budget})"
        wild_status = "SOLVED" if result.wild_type.solved else "FAILED"
        lines.append(
            f"Wild type: {wild_status} ({result.wild_type.stats['nodes']} nodes, "
            f"{wild_metrics['total_iterations']} iters, "
            f"fail ratio {wild_metrics['failure_ratio']:.0%}{tier_info})\n"
        )

        if result.interventions:
            lines.append("| Intervention | Blocked | Solved | GED | Notes |")
            lines.append("|--------------|---------|--------|-----|-------|")

            for int_result in result.interventions:
                blocked = ", ".join(sorted(int_result.intervention.blocked))
                solved = "Yes" if int_result.intervention_run.solved else "No"
                ged = f"{int_result.ged:.1f}"

                if not int_result.intervention_run.solved:
                    notes = "Tactic essential"
                elif int_result.ged == 0:
                    notes = "Same structure"
                elif int_result.ged < 3:
                    notes = "Minor structural change"
                else:
                    notes = "Major structural change"

                lines.append(
                    f"| {int_result.intervention.name} | {blocked} | {solved} | {ged} | {notes} |"
                )

            lines.append("")

    return "\n".join(lines)


def complete_corpus_run(
    *,
    lifecycle: RunLifecycle,
    progress: CorpusProgress,
    results: list[TheoremResult],
    crashed: list[CrashedTheorem],
    theorem_corpus: list[Theorem],
    goal_cache: GoalCache,
    goal_sig_config: GoalSignatureConfig,
    provider_label: str,
    corpus: str,
    budget_tiers: list[int],
    skip_interventions: bool,
    run_analysis: bool,
) -> list[TheoremResult]:
    logger = lifecycle.logger

    progress.print_summary()

    if crashed:
        logger.warning("%s theorems crashed and were skipped:", len(crashed))
        for crashed_theorem in crashed:
            logger.warning(
                "  - %s: %s",
                crashed_theorem.theorem_name,
                crashed_theorem.display_error(),
            )
    if lifecycle.failed and run_analysis:
        logger.warning("Post-analysis skipped because run failed")
        run_analysis = False

    goal_cache.save(lifecycle.log_dir / "goal_cache.json")
    logger.info(
        "Goal cache saved: %s unique sigs, %s occurrences",
        len(goal_cache.entries),
        len(goal_cache.mvar_to_sig),
    )
    logger.info(
        "Goal signature: scheme=%s, ast_missing=%s",
        goal_sig_config.scheme,
        goal_sig_config.stats.ast_missing,
    )

    theorem_order = {theorem.name: idx for idx, theorem in enumerate(theorem_corpus)}
    results.sort(key=lambda item: theorem_order.get(item.theorem.name, len(theorem_order)))

    _lean_helpers().save_results(lifecycle.log_dir, results, crashed, goal_sig_config)

    report = generate_report(results, crashed)
    with open(lifecycle.log_dir / "report.md", "w") as handle:
        handle.write(report)

    if run_analysis:
        progress.set_phase_progress(
            "analysis",
            stage_label="reports",
            stage_step=0,
            stage_total=1,
            stage_note="failure and corpus summaries",
        )
        run_post_analysis(lifecycle.log_dir)
    if not lifecycle.failed:
        try:
            progress.set_phase_progress(
                "postprocess",
                stage_label="theorems",
                stage_step=0,
                stage_total=max(len(results), 1),
                stage_note="soft metrics and completeness checks",
            )
            last_logged_postprocess_idx = 0

            def _postprocess_progress(event: dict[str, Any]) -> None:
                nonlocal last_logged_postprocess_idx
                theorem_idx_raw = event.get("theorem_idx")
                theorem_total_raw = event.get("theorems_total")
                theorem_name = event.get("theorem")
                updated_raw = event.get("updated_interventions")
                skipped_raw = event.get("skipped_interventions")
                theorem_idx = theorem_idx_raw if isinstance(theorem_idx_raw, int) else 0
                theorem_total = theorem_total_raw if isinstance(theorem_total_raw, int) else 0
                updated = updated_raw if isinstance(updated_raw, int) else 0
                skipped = skipped_raw if isinstance(skipped_raw, int) else 0
                note = f"updated={updated} skipped={skipped}"
                progress.set_phase_progress(
                    "postprocess",
                    theorem=theorem_name if isinstance(theorem_name, str) else "",
                    theorem_idx=theorem_idx,
                    stage_label="theorems",
                    stage_step=theorem_idx,
                    stage_total=theorem_total if theorem_total > 0 else max(len(results), 1),
                    stage_note=note,
                )
                if (
                    theorem_idx > 0
                    and (
                        theorem_idx == 1
                        or theorem_idx == theorem_total
                        or theorem_idx - last_logged_postprocess_idx >= 25
                    )
                ):
                    logger.info(
                        "Postprocess [%s/%s]: %s (%s)",
                        theorem_idx,
                        theorem_total,
                        theorem_name or "<unknown>",
                        note,
                    )
                    last_logged_postprocess_idx = theorem_idx

            _write_postprocess_metrics(
                lifecycle.log_dir,
                progress_cb=_postprocess_progress,
            )
        except Exception as exc:
            lifecycle.record_failure(exc)
            logger.exception("Postprocess failed; aborting run")

    logger.info("Results saved to %s", lifecycle.log_dir)

    stats = _compute_run_stats(results, crashed)
    summary_block = _format_run_summary(
        provider_label=provider_label,
        corpus=corpus,
        budget_tiers=budget_tiers,
        wild_only=skip_interventions,
        trace_mcts=lifecycle.trace_mcts,
        stats=stats,
        log_dir=lifecycle.log_dir,
    )
    logger.info("\n%s", summary_block)

    if lifecycle.failed and lifecycle.error is not None:
        lifecycle.finalize(
            status_value="failed",
            error=lifecycle.error,
            partial_results=bool(results or crashed),
            sync_reason="run-failed-after-save",
            traceback_text=lifecycle.error_trace,
        )
        raise lifecycle.error

    lifecycle.finalize(
        status_value="completed",
        partial_results=bool(crashed),
        sync_reason="run-completed",
    )
    return results
