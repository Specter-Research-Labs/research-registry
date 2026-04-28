from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import networkx as nx

from analysis.external_statement_similarity import (
    compute_external_statement_similarity,
    compute_tptp_statement_similarity_from_logs,
)
from analysis.logs import (
    ProviderRun,
    extract_solution_steps,
    family_index,
    iter_provider_runs,
    read_json,
    read_json_gz,
    sha256_file,
    utc_timestamp,
    write_json_atomic,
    write_json_gz_atomic,
)
from analysis.root_goal_similarity import compute_root_goal_similarity
from prover.goal_cache import GoalCache
from prover.goal_distance import GoalSigTedDistance, normalized_sequence_edit_distance
from prover.k import k_log10_ratio
from prover.mcts import TACTIC_FAMILIES as MCTS_TACTIC_FAMILIES
from prover.proof import ProofGraph
from prover.providers.base import normalize_tactic, tactic_family

# These are intentionally conservative defaults. They keep postprocess deterministic and
# bounded even when proof graphs are large.
DEFAULT_MAX_SOFT_GED_NODES = 60
DEFAULT_MAX_SOFT_GED_EDGES = 120
DEFAULT_MAX_NOVELTY_PAIRS = 200_000
DEFAULT_MAX_PATH_DP_CELLS = 2_000_000
DEFAULT_MAX_ROOT_GOAL_THEOREMS = 400
DEFAULT_MAX_ROOT_GOAL_KNN_THEOREMS = 2000
DEFAULT_ROOT_GOAL_KNN_K = 12
DEFAULT_ROOT_GOAL_KNN_SAMPLE = 200
DEFAULT_ROOT_GOAL_SAMPLE_SIZE = 400
DEFAULT_ROOT_GOAL_MODE = "auto"
DEFAULT_EXTERNAL_STATEMENT_MAX_FULL = 400
DEFAULT_EXTERNAL_STATEMENT_MAX_KNN = 2000
DEFAULT_EXTERNAL_STATEMENT_KNN_K = 12
DEFAULT_EXTERNAL_STATEMENT_KNN_SAMPLE = 200
DEFAULT_EXTERNAL_STATEMENT_SAMPLE_SIZE = 400
DEFAULT_EXTERNAL_STATEMENT_MODE = "auto"


def _load_graph(path: Path) -> ProofGraph:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Graph file must be a JSON object: {path}")
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError(f"Graph file missing nodes/edges lists: {path}")
    return ProofGraph.deserialize({"nodes": nodes, "edges": edges})


def _solution_goal_sigs_from_files(history_path: Path, mcts_tree_path: Path) -> list[str]:
    if not history_path.exists() or not mcts_tree_path.exists():
        return []

    history = read_json(history_path)
    if not isinstance(history, dict):
        return []
    solution_path = history.get("solution_path")
    if not isinstance(solution_path, list):
        return []

    tree = read_json(mcts_tree_path)
    if not isinstance(tree, dict):
        return []
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        return []

    goal_sig_by_mvar: dict[str, str] = {}
    for mvar_id, node_data in nodes.items():
        if not isinstance(mvar_id, str) or not isinstance(node_data, dict):
            continue
        sig = node_data.get("goal_sig")
        if isinstance(sig, str) and sig:
            goal_sig_by_mvar[mvar_id] = sig

    goal_sigs: list[str] = []
    for step in solution_path:
        if not isinstance(step, dict):
            continue
        mvar_id = step.get("mvar_id")
        if not isinstance(mvar_id, str) or not mvar_id:
            continue
        sig = goal_sig_by_mvar.get(mvar_id)
        if sig:
            goal_sigs.append(sig)
    return goal_sigs


def _distance_stats(values: list[float]) -> dict[str, float | int] | None:
    if not values:
        return None
    values_sorted = sorted(values)
    n = len(values_sorted)

    def q(p: float) -> float:
        if n == 1:
            return float(values_sorted[0])
        idx = int((n - 1) * p)
        return float(values_sorted[idx])

    mean = sum(values_sorted) / n
    return {
        "count": n,
        "mean": round(mean, 6),
        "p50": round(q(0.5), 6),
        "p90": round(q(0.9), 6),
        "min": round(float(values_sorted[0]), 6),
        "max": round(float(values_sorted[-1]), 6),
    }


def _compute_family_priors(cache: GoalCache) -> dict[str, float]:
    """Laplace-smoothed p(success|family) aggregated across the whole run."""

    priors: dict[str, float] = {}
    for fam in MCTS_TACTIC_FAMILIES:
        idx = family_index(fam)
        attempts = 0
        successes = 0
        for entry in cache.entries.values():
            for occ in entry.occurrences.values():
                outcomes = occ.outcomes.get(idx, [])
                attempts += len(outcomes)
                successes += int(sum(1 for x in outcomes if x))
        priors[fam] = (successes + 1) / (attempts + 2)
    return priors


def _p_success_sig_family(
    cache: GoalCache,
    sig: str,
    fam: str,
    *,
    family_priors: dict[str, float],
) -> float:
    """Return p(success | goal_sig=sig, tactic_family=fam) with empirical fallback."""

    # Unknown tactic families are bucketed to "other" in prover/mcts.py and recorded that way in
    # goal_cache outcomes. Mirror that here so the prior is consistent with the observation index.
    fam_key = fam if fam in MCTS_TACTIC_FAMILIES else "other"
    prior = family_priors.get(fam_key, 0.5)
    entry = cache.entries.get(sig)
    if entry is None:
        return float(prior)
    idx = family_index(fam)
    attempts = 0
    successes = 0
    for occ in entry.occurrences.values():
        outcomes = occ.outcomes.get(idx, [])
        attempts += len(outcomes)
        successes += int(sum(1 for x in outcomes if x))
    if attempts <= 0:
        return float(prior)
    return (successes + 1) / (attempts + 2)


def _observed_families_for_sig(cache: GoalCache, sig: str) -> list[str]:
    entry = cache.entries.get(sig)
    if entry is None:
        return []
    families: list[str] = []
    for fam in MCTS_TACTIC_FAMILIES:
        idx = family_index(fam)
        attempts = 0
        for occ in entry.occurrences.values():
            attempts += len(occ.outcomes.get(idx, []))
        if attempts > 0:
            families.append(fam)
    return families


def compute_k_search_efficiency_from_logs(
    *,
    theorem_dir: Path,
    variant: str,
    goal_cache: GoalCache | None,
    family_priors: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compute K-style search-efficiency metrics for a solved Lean variant."""

    if goal_cache is None:
        return {
            "schema_version": 1,
            "valid": False,
            "validity_notes": ["missing goal_cache.json.gz"],
        }

    ext = extract_solution_steps(
        theorem_dir=theorem_dir,
        variant=variant,
        mvar_to_sig=goal_cache.mvar_to_sig,
    )
    if not ext.valid:
        return {
            "schema_version": 1,
            "valid": False,
            "validity_notes": ext.validity_notes,
        }

    notes = list(ext.validity_notes)
    assert ext.tau_agent is not None
    tau_agent = ext.tau_agent
    step_specs = ext.step_specs
    expected_steps = ext.expected_steps
    dropped_steps = ext.dropped_steps
    candidates_by_iter = ext.candidates_by_iter

    if family_priors is None:
        family_priors = _compute_family_priors(goal_cache)

    def _mean(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def compute_totals(*, mode: str, metric: str) -> tuple[float | None, list[str]]:
        tau_blind = 0.0
        local_notes: list[str] = []
        for spec in step_specs:
            it = spec["iteration"]
            sig = spec["goal_sig"]
            used_fam = spec["tactic_family"]
            candidates = candidates_by_iter.get(it)
            fams: list[str] = []
            if candidates:
                fams = [tactic_family(normalize_tactic(c)) for c in candidates]
                if not fams:
                    local_notes.append(f"empty_candidates: iteration={it}")
                    return None, local_notes
            elif mode == "blind_uniform_family":
                fams = _observed_families_for_sig(goal_cache, sig)
                if not fams:
                    local_notes.append(
                        f"missing_candidates_and_no_observed_fams: iteration={it}"
                    )
                    return None, local_notes
                local_notes.append(f"fallback_operator_alphabet: observed_families iteration={it}")
            else:
                local_notes.append(f"missing_candidates: iteration={it}")
                return None, local_notes

            if mode == "blind_uniform_candidate":
                p_step = _mean(
                    [
                        _p_success_sig_family(goal_cache, sig, fam, family_priors=family_priors)
                        for fam in fams
                    ]
                )
                if metric == "used_operator":
                    used_count = sum(1 for fam in fams if fam == used_fam)
                    if used_count <= 0:
                        local_notes.append(f"used_family_missing_from_candidates: iteration={it}")
                        return None, local_notes
                    p_used = _p_success_sig_family(
                        goal_cache, sig, used_fam, family_priors=family_priors
                    )
                    p_step = (used_count / len(fams)) * p_used
            elif mode == "blind_uniform_family":
                uniq = sorted(set(fams))
                p_step = _mean(
                    [
                        _p_success_sig_family(goal_cache, sig, fam, family_priors=family_priors)
                        for fam in uniq
                    ]
                )
                if metric == "used_operator":
                    if used_fam not in uniq:
                        local_notes.append(f"used_family_missing_from_families: iteration={it}")
                        return None, local_notes
                    p_used = _p_success_sig_family(
                        goal_cache, sig, used_fam, family_priors=family_priors
                    )
                    p_step = (1 / len(uniq)) * p_used
            else:
                raise ValueError(f"Unknown null model: {mode}")

            if p_step is None or p_step <= 0.0:
                local_notes.append(f"invalid_step_probability: iteration={it} p={p_step!r}")
                return None, local_notes
            tau_blind += 1.0 / p_step
        return tau_blind, local_notes

    variants: dict[str, dict[str, dict[str, Any]]] = {
        "any_success": {},
        "used_operator": {},
    }
    for metric in ("any_success", "used_operator"):
        for mode in ("blind_uniform_candidate", "blind_uniform_family"):
            tau_blind, local_notes = compute_totals(mode=mode, metric=metric)
            if tau_blind is None:
                variants[metric][mode] = {
                    "tau_blind": None,
                    "K": None,
                    "valid": False,
                    "validity_notes": local_notes,
                }
                continue
            k_value = k_log10_ratio(tau_blind=tau_blind, tau_agent=tau_agent)
            variants[metric][mode] = {
                "tau_blind": round(float(tau_blind), 6),
                "K": round(float(k_value), 6) if k_value is not None else None,
                "valid": k_value is not None,
                "validity_notes": local_notes,
            }

    primary = variants["any_success"]["blind_uniform_candidate"]
    primary_null = "blind_uniform_candidate"
    if not primary.get("valid"):
        primary = variants["any_success"]["blind_uniform_family"]
        primary_null = "blind_uniform_family"
        notes.append("primary_fallback: used blind_uniform_family due to trace/candidate issues")

    trace_path = theorem_dir / f"{variant}_mcts_trace.jsonl"
    history_path = theorem_dir / f"{variant}_history.json"
    tree_path = theorem_dir / f"{variant}_mcts_tree.json"
    # Mark invalid if we couldn't map every solution step to an iteration/candidate set. This keeps
    # the metric comparable across runs and prevents partial-path scoring against full tau_agent.
    complete = (expected_steps == len(step_specs))
    return {
        "schema_version": 1,
        "valid": bool(primary.get("valid")) and complete,
        "validity_notes": notes,
        "w_unit": "tactic_attempt",
        "tau_agent": int(tau_agent),
        "primary": {
            "metric": "any_success",
            "null_model": primary_null,
            "tau_blind": primary.get("tau_blind"),
            "K": primary.get("K"),
        },
        "variants": variants,
        "steps": {
            "count": len(step_specs),
            "expected": expected_steps,
            "dropped": dropped_steps,
            "trace_path": trace_path.name,
            "history_path": history_path.name,
            "tree_path": tree_path.name,
        },
    }


def _k_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": entry.get("schema_version"),
        "valid": entry.get("valid"),
        "validity_notes": entry.get("validity_notes"),
        "w_unit": entry.get("w_unit"),
        "tau_agent": entry.get("tau_agent"),
        "primary": entry.get("primary"),
        "variants": entry.get("variants"),
        "steps": {"count": entry.get("steps", {}).get("count")},
    }


def compute_goal_novelty(
    wild: ProofGraph,
    intervention: ProofGraph,
    *,
    goal_sig_ted: GoalSigTedDistance | None,
    max_pairs: int = DEFAULT_MAX_NOVELTY_PAIRS,
) -> dict[str, Any]:
    if goal_sig_ted is None:
        return {
            "valid": False,
            "validity_notes": ["missing goal cache / goal signature TED"],
        }

    wild_sigs = {
        attrs.get("goal_sig")
        for _, attrs in wild.to_networkx().nodes(data=True)
        if isinstance(attrs.get("goal_sig"), str)
    }
    int_sigs = {
        attrs.get("goal_sig")
        for _, attrs in intervention.to_networkx().nodes(data=True)
        if isinstance(attrs.get("goal_sig"), str)
    }

    novel = sorted(int_sigs - wild_sigs)
    dropped = sorted(wild_sigs - int_sigs)

    def min_distances(
        sources: list[str],
        targets: list[str],
    ) -> tuple[list[float], list[str]]:
        if not sources or not targets:
            return [], []
        pairs = len(sources) * len(targets)
        notes: list[str] = []
        if pairs > max_pairs:
            per_source = max(1, max_pairs // len(sources))
            targets = targets[:per_source]
            notes.append(
                f"capped_comparisons: pairs={pairs} > {max_pairs}; "
                f"targets_truncated_to={len(targets)}"
            )

        dists: list[float] = []
        checked: set[str] = set()
        sig_errors: dict[str, str] = {}

        def ensure_tree(sig: str) -> None:
            if sig in checked:
                return
            checked.add(sig)
            if goal_sig_ted.tree(sig) is None:
                sig_errors[sig] = goal_sig_ted.tree_errors.get(sig, "tree_build_failed")

        for t in targets:
            ensure_tree(t)
        for s in sources:
            ensure_tree(s)
            best = 1.0
            for t in targets:
                best = min(best, goal_sig_ted.normalized_distance(s, t))
                if best == 0.0:
                    break
            dists.append(best)
        if sig_errors:
            examples = list(sorted(sig_errors.items()))[:5]
            notes.append(f"goal_tree_errors={len(sig_errors)}; examples={examples}")
        return dists, notes

    novel_dists, novel_notes = min_distances(novel, sorted(wild_sigs))
    dropped_dists, dropped_notes = min_distances(dropped, sorted(int_sigs))

    validity_notes: list[str] = [*novel_notes, *dropped_notes]
    valid = not validity_notes
    return {
        "valid": valid,
        "validity_notes": validity_notes,
        "novel_goal_count": len(novel),
        "dropped_goal_count": len(dropped),
        "novel_min_distance": _distance_stats(novel_dists),
        "dropped_min_distance": _distance_stats(dropped_dists),
    }


def compute_soft_search_graph_ged(
    wild: ProofGraph,
    intervention: ProofGraph,
    *,
    goal_sig_ted: GoalSigTedDistance | None,
    max_nodes: int = DEFAULT_MAX_SOFT_GED_NODES,
    max_edges: int = DEFAULT_MAX_SOFT_GED_EDGES,
) -> dict[str, Any]:
    if goal_sig_ted is None:
        return {
            "value": None,
            "normalized": None,
            "valid": False,
            "validity_notes": ["missing goal cache / goal signature TED"],
            "trace_source": "mcts",
            "trace_completeness": "full",
        }

    wild_canonical = wild.to_canonical()
    int_canonical = intervention.to_canonical()

    wild_nodes = wild_canonical.number_of_nodes()
    wild_edges = wild_canonical.number_of_edges()
    int_nodes = int_canonical.number_of_nodes()
    int_edges = int_canonical.number_of_edges()

    if max(wild_nodes, int_nodes) > max_nodes or max(wild_edges, int_edges) > max_edges:
        return {
            "value": None,
            "normalized": None,
            "valid": False,
            "validity_notes": [
                "skipped: graph too large for soft GED",
                f"wild_nodes={wild_nodes} wild_edges={wild_edges}",
                f"int_nodes={int_nodes} int_edges={int_edges}",
                f"max_nodes={max_nodes} max_edges={max_edges}",
            ],
            "trace_source": "mcts",
            "trace_completeness": "full",
        }

    def node_subst_cost(a: dict, b: dict) -> float:
        sig1 = a.get("goal_sig")
        sig2 = b.get("goal_sig")
        if not isinstance(sig1, str) or not isinstance(sig2, str):
            return 1.0
        return float(goal_sig_ted.normalized_distance(sig1, sig2))

    def node_del_cost(_: dict) -> float:
        return 1.0

    def node_ins_cost(_: dict) -> float:
        return 1.0

    def edge_subst_cost(a: dict, b: dict) -> float:
        t1 = a.get("tactic_norm")
        t2 = b.get("tactic_norm")
        f1 = tactic_family(t1) if isinstance(t1, str) and t1 else ""
        f2 = tactic_family(t2) if isinstance(t2, str) and t2 else ""
        return 0.0 if f1 == f2 else 1.0

    def edge_del_cost(_: dict) -> float:
        return 1.0

    def edge_ins_cost(_: dict) -> float:
        return 1.0

    validity_notes: list[str] = []
    sig_errors: dict[str, str] = {}
    for _, attrs in wild_canonical.nodes(data=True):
        sig = attrs.get("goal_sig")
        if not isinstance(sig, str):
            continue
        if goal_sig_ted.tree(sig) is None:
            sig_errors[sig] = goal_sig_ted.tree_errors.get(sig, "tree_build_failed")

    for _, attrs in int_canonical.nodes(data=True):
        sig = attrs.get("goal_sig")
        if not isinstance(sig, str):
            continue
        if goal_sig_ted.tree(sig) is None:
            sig_errors[sig] = goal_sig_ted.tree_errors.get(sig, "tree_build_failed")

    ged = nx.graph_edit_distance(
        wild_canonical,
        int_canonical,
        node_subst_cost=node_subst_cost,
        node_del_cost=node_del_cost,
        node_ins_cost=node_ins_cost,
        edge_subst_cost=edge_subst_cost,
        edge_del_cost=edge_del_cost,
        edge_ins_cost=edge_ins_cost,
    )

    if sig_errors:
        examples = list(sorted(sig_errors.items()))[:5]
        validity_notes.append(f"goal_tree_errors={len(sig_errors)}; examples={examples}")

    wild_size = wild_nodes + wild_edges
    int_size = int_nodes + int_edges
    max_size = max(wild_size, int_size)
    normalized = (ged / max_size) if ged is not None and max_size > 0 else None
    valid = ged is not None and not bool(sig_errors)
    return {
        "value": ged,
        "normalized": normalized,
        "valid": valid,
        "validity_notes": validity_notes,
        "trace_source": "mcts",
        "trace_completeness": "full",
    }


def compute_solution_path_soft_distance(
    wild_solution_goal_sigs: list[str],
    intervention_solution_goal_sigs: list[str],
    *,
    goal_sig_ted: GoalSigTedDistance | None,
    max_dp_cells: int = DEFAULT_MAX_PATH_DP_CELLS,
) -> dict[str, Any]:
    notes: list[str] = []
    value: float | None = None

    if not wild_solution_goal_sigs:
        notes.append("wild_type has no solution_path goal sigs")
    if not intervention_solution_goal_sigs:
        notes.append("intervention has no solution_path goal sigs")
    if goal_sig_ted is None:
        notes.append("missing goal cache / goal signature TED")
    wild_len = len(wild_solution_goal_sigs)
    int_len = len(intervention_solution_goal_sigs)
    dp_cells = wild_len * int_len
    if dp_cells > max_dp_cells:
        notes.append(
            f"dp_too_large: cells={dp_cells} > {max_dp_cells} "
            f"(wild_len={wild_len} intervention_len={int_len})"
        )

    if not notes:
        value = normalized_sequence_edit_distance(
            wild_solution_goal_sigs,
            intervention_solution_goal_sigs,
            subst_cost=goal_sig_ted.normalized_distance,
        )

    return {
        "value": value,
        "valid": value is not None and not notes,
        "validity_notes": notes,
        "wild_len": wild_len,
        "intervention_len": int_len,
        "dp_cells": dp_cells,
    }


@dataclass(frozen=True)
class PostprocessParams:
    max_soft_ged_nodes: int = DEFAULT_MAX_SOFT_GED_NODES
    max_soft_ged_edges: int = DEFAULT_MAX_SOFT_GED_EDGES
    max_novelty_pairs: int = DEFAULT_MAX_NOVELTY_PAIRS
    max_path_dp_cells: int = DEFAULT_MAX_PATH_DP_CELLS
    max_root_goal_theorems: int = DEFAULT_MAX_ROOT_GOAL_THEOREMS
    max_root_goal_knn_theorems: int = DEFAULT_MAX_ROOT_GOAL_KNN_THEOREMS
    root_goal_knn_k: int = DEFAULT_ROOT_GOAL_KNN_K
    root_goal_knn_sample: int = DEFAULT_ROOT_GOAL_KNN_SAMPLE
    root_goal_sample_size: int = DEFAULT_ROOT_GOAL_SAMPLE_SIZE
    root_goal_mode: str = DEFAULT_ROOT_GOAL_MODE
    external_statement_max_full: int = DEFAULT_EXTERNAL_STATEMENT_MAX_FULL
    external_statement_max_knn: int = DEFAULT_EXTERNAL_STATEMENT_MAX_KNN
    external_statement_knn_k: int = DEFAULT_EXTERNAL_STATEMENT_KNN_K
    external_statement_knn_sample: int = DEFAULT_EXTERNAL_STATEMENT_KNN_SAMPLE
    external_statement_sample_size: int = DEFAULT_EXTERNAL_STATEMENT_SAMPLE_SIZE
    external_statement_mode: str = DEFAULT_EXTERNAL_STATEMENT_MODE
    resume: bool = True


_PENDING_NOTE = "not computed in-run; run `wonton.py postprocess` to fill this metric"


def _is_pending_metric_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return True
    notes = entry.get("validity_notes")
    if not isinstance(notes, list):
        return True
    return any(isinstance(n, str) and _PENDING_NOTE in n for n in notes)


def _staleness_params(params: PostprocessParams) -> dict[str, Any]:
    return {
        "max_soft_ged_nodes": params.max_soft_ged_nodes,
        "max_soft_ged_edges": params.max_soft_ged_edges,
        "max_novelty_pairs": params.max_novelty_pairs,
        "max_path_dp_cells": params.max_path_dp_cells,
        "max_root_goal_theorems": params.max_root_goal_theorems,
        "max_root_goal_knn_theorems": params.max_root_goal_knn_theorems,
        "root_goal_knn_k": params.root_goal_knn_k,
        "root_goal_knn_sample": params.root_goal_knn_sample,
        "root_goal_sample_size": params.root_goal_sample_size,
        "root_goal_mode": params.root_goal_mode,
        "external_statement_max_full": params.external_statement_max_full,
        "external_statement_max_knn": params.external_statement_max_knn,
        "external_statement_knn_k": params.external_statement_knn_k,
        "external_statement_knn_sample": params.external_statement_knn_sample,
        "external_statement_sample_size": params.external_statement_sample_size,
        "external_statement_mode": params.external_statement_mode,
    }


def _soft_ged_exception_entry(exc: Exception) -> dict[str, Any]:
    return {
        "value": None,
        "normalized": None,
        "valid": False,
        "validity_notes": [f"exception: {type(exc).__name__}: {exc}"],
        "trace_source": "mcts",
        "trace_completeness": "full",
    }


def _goal_novelty_exception_entry(exc: Exception) -> dict[str, Any]:
    return {
        "valid": False,
        "validity_notes": [f"exception: {type(exc).__name__}: {exc}"],
    }


def _solution_path_exception_entry(
    exc: Exception,
    *,
    wild_len: int,
    intervention_len: int,
) -> dict[str, Any]:
    return {
        "value": None,
        "valid": False,
        "validity_notes": [f"exception: {type(exc).__name__}: {exc}"],
        "wild_len": wild_len,
        "intervention_len": intervention_len,
        "dp_cells": wild_len * intervention_len,
    }


def _pending_soft_ged_entry() -> dict[str, Any]:
    return {
        "value": None,
        "normalized": None,
        "valid": False,
        "validity_notes": [
            "not computed in-run; run `wonton.py postprocess` to fill this metric"
        ],
        "trace_source": "mcts",
        "trace_completeness": "full",
    }


def _pending_goal_novelty_entry() -> dict[str, Any]:
    return {
        "valid": False,
        "validity_notes": [
            "not computed in-run; run `wonton.py postprocess` to fill this metric"
        ],
    }


def _pending_solution_path_entry() -> dict[str, Any]:
    return {
        "value": None,
        "valid": False,
        "validity_notes": [
            "not computed in-run; run `wonton.py postprocess` to fill this metric"
        ],
        "wild_len": 0,
        "intervention_len": 0,
        "dp_cells": 0,
    }


def _unsupported_external_statement_similarity(
    *,
    corpus: str,
    root: Path | None,
    selected_count: int,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "valid": False,
        "validity_notes": [reason],
        "corpus": corpus,
        "root": str(root) if root is not None else None,
        "problem_count_total": selected_count,
        "matrix_mode": None,
    }


def postprocess_provider_run(
    run: ProviderRun,
    *,
    params: PostprocessParams,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    run_dir = run.run_dir
    summary_path = run_dir / "summary.json.gz"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing summary.json.gz: {summary_path}")

    summary = read_json_gz(summary_path)
    if not isinstance(summary, dict):
        raise ValueError("summary.json.gz must contain a JSON object")

    run_config_path = run_dir / "run_config.json"
    run_config = read_json(run_config_path) if run_config_path.exists() else {}
    if not isinstance(run_config, dict):
        run_config = {}

    if run_config.get("mode") == "external":
        corpus = run_config.get("corpus")
        corpus_meta = run_config.get("corpus_meta", {})
        if not isinstance(corpus, str) or not corpus.strip():
            raise ValueError("run_config.corpus must be a non-empty string for external runs")
        if not isinstance(corpus_meta, dict):
            raise ValueError("run_config.corpus_meta must be an object for external runs")

        stmt_report: dict[str, Any]
        if corpus in {"tptp", "smtlib"}:
            selection = run_config.get("problem_selection", {})
            root_raw = corpus_meta.get("root")
            if not isinstance(root_raw, str) or not root_raw.strip():
                raise ValueError("run_config.corpus_meta.root missing for external runs")
            root = Path(root_raw).expanduser().resolve()
            selected = selection.get("selected_problems") if isinstance(selection, dict) else None
            if not isinstance(selected, list) or not all(isinstance(n, str) for n in selected):
                raise ValueError(
                    "run_config.problem_selection.selected_problems missing for external runs"
                )

            if corpus == "tptp" and not root.exists():
                stmt_report = compute_tptp_statement_similarity_from_logs(
                    run_dir,
                    selected_names=selected,
                    mode=params.external_statement_mode,
                    max_theorems_full=params.external_statement_max_full,
                    max_knn_theorems=params.external_statement_max_knn,
                    knn_k=params.external_statement_knn_k,
                    knn_sample_size=params.external_statement_knn_sample,
                    sample_size=params.external_statement_sample_size,
                )
            else:
                stmt_report = compute_external_statement_similarity(
                    corpus=corpus,
                    root=root,
                    selected_names=selected,
                    mode=params.external_statement_mode,
                    max_theorems_full=params.external_statement_max_full,
                    max_knn_theorems=params.external_statement_max_knn,
                    knn_k=params.external_statement_knn_k,
                    knn_sample_size=params.external_statement_knn_sample,
                    sample_size=params.external_statement_sample_size,
                )
        elif corpus in {"coq", "coq-stdlib"}:
            selection = run_config.get("theorem_selection", {})
            selected = selection.get("selected_theorems") if isinstance(selection, dict) else None
            if not isinstance(selected, list) or not all(isinstance(n, str) for n in selected):
                raise ValueError(
                    "run_config.theorem_selection.selected_theorems missing for Coq external runs"
                )
            root = None
            root_raw = corpus_meta.get("stdlib_root")
            if isinstance(root_raw, str) and root_raw.strip():
                root = Path(root_raw).expanduser().resolve()
            stmt_report = _unsupported_external_statement_similarity(
                corpus=corpus,
                root=root,
                selected_count=len(selected),
                reason=(
                    f"statement similarity is not implemented for external corpus {corpus!r}; "
                    "metric intentionally not computed"
                ),
            )
        else:
            raise ValueError(f"unsupported external corpus: {corpus!r}")
        write_json_atomic(run_dir / "external_statement_similarity.json", stmt_report)

        return {
            "run_dir": str(run_dir),
            "provider": run.provider,
            "mode": "external",
            "corpus": corpus,
            "external_statement_similarity": {
                "valid": bool(stmt_report.get("valid")),
                "matrix_mode": stmt_report.get("matrix_mode"),
                "problem_count_total": stmt_report.get("problem_count_total"),
            },
            "errors": [],
        }

    goal_sig_scheme = summary.get("goal_sig_scheme") or run_config.get("goal_sig_scheme")
    goal_sig_ted: GoalSigTedDistance | None = None
    ted_error: str | None = None
    goal_cache: GoalCache | None = None
    goal_cache_error: str | None = None
    try:
        goal_cache = GoalCache.load(run_dir / "goal_cache.json")
    except Exception as e:
        goal_cache_error = f"{type(e).__name__}: {e}"
        goal_cache = None
    family_priors = _compute_family_priors(goal_cache) if goal_cache is not None else None

    if goal_sig_scheme == "ast":
        try:
            if goal_cache is None:
                raise RuntimeError(goal_cache_error or "missing goal_cache")
            goal_sig_ted = GoalSigTedDistance(goal_cache)
        except Exception as e:
            ted_error = f"{type(e).__name__}: {e}"

    theorems_raw = summary.get("theorems", [])
    if not isinstance(theorems_raw, list):
        raise ValueError("summary.theorems must be a list")

    updated_interventions = 0
    skipped_interventions = 0
    errors: list[dict[str, Any]] = []
    metrics_computed = {
        "ged_search_graph_soft": 0,
        "goal_novelty": 0,
        "solution_path_soft_distance": 0,
        "k_search_efficiency": 0,
    }
    metrics_skipped = {
        "ged_search_graph_soft": 0,
        "goal_novelty": 0,
        "solution_path_soft_distance": 0,
        "k_search_efficiency": 0,
    }

    def _note_metrics_for_intervention(
        *,
        soft_ged: dict[str, Any] | None = None,
        novelty: dict[str, Any] | None = None,
        path_dist: dict[str, Any] | None = None,
        skipped: bool = False,
    ) -> None:
        if skipped:
            for key in metrics_skipped:
                metrics_skipped[key] += 1
            return
        if soft_ged is not None:
            if soft_ged.get("value") is None:
                metrics_skipped["ged_search_graph_soft"] += 1
            else:
                metrics_computed["ged_search_graph_soft"] += 1
        if novelty is not None:
            if "novel_goal_count" in novelty or "dropped_goal_count" in novelty:
                metrics_computed["goal_novelty"] += 1
            else:
                metrics_skipped["goal_novelty"] += 1
        if path_dist is not None:
            if path_dist.get("value") is None:
                metrics_skipped["solution_path_soft_distance"] += 1
            else:
                metrics_computed["solution_path_soft_distance"] += 1

    theorem_entries: list[tuple[str, dict[str, Any], list[dict[str, Any]], Path]] = []
    for entry in theorems_raw:
        if not isinstance(entry, dict):
            continue
        theorem_name = entry.get("name")
        if not isinstance(theorem_name, str) or not theorem_name:
            continue
        interventions_raw = entry.get("interventions", [])
        if not isinstance(interventions_raw, list):
            continue
        interventions: list[dict[str, Any]] = [
            x for x in interventions_raw if isinstance(x, dict)
        ]
        theorem_dir = run_dir / theorem_name
        if not theorem_dir.exists():
            continue
        theorem_entries.append((theorem_name, entry, interventions, theorem_dir))

    total_theorems = len(theorem_entries)
    for theorem_idx, (theorem_name, entry, interventions, theorem_dir) in enumerate(
        theorem_entries, 1
    ):
        # K-style search efficiency for wild-type (write compact summary into summary.json.gz).
        k_wild = compute_k_search_efficiency_from_logs(
            theorem_dir=theorem_dir,
            variant="wild_type",
            goal_cache=goal_cache,
            family_priors=family_priors,
        )
        wild_entry = entry.get("wild_type")
        if isinstance(wild_entry, dict):
            wild_entry["k_search_efficiency"] = _k_summary(k_wild)
        if isinstance(k_wild, dict) and k_wild.get("valid") is True:
            metrics_computed["k_search_efficiency"] += 1
        else:
            metrics_skipped["k_search_efficiency"] += 1

        try:
            wild_graph = _load_graph(theorem_dir / "wild_type_graph.json")
        except Exception as e:
            errors.append(
                {
                    "theorem": theorem_name,
                    "error": f"wild_graph: {type(e).__name__}: {e}",
                }
            )
            for int_entry in interventions_raw:
                if not isinstance(int_entry, dict):
                    continue
                name = int_entry.get("name")
                if not isinstance(name, str) or not name:
                    continue
                _note_metrics_for_intervention(skipped=True)
            continue

        wild_solution_goal_sigs = _solution_goal_sigs_from_files(
            theorem_dir / "wild_type_history.json",
            theorem_dir / "wild_type_mcts_tree.json",
        )

        for int_entry in interventions:
            name = int_entry.get("name")
            if not isinstance(name, str) or not name:
                continue

            comparison_path = theorem_dir / f"{name}_comparison.json"
            if not comparison_path.exists():
                skipped_interventions += 1
                _note_metrics_for_intervention(skipped=True)
                continue
            try:
                comparison = read_json(comparison_path)
            except Exception as e:
                errors.append(
                    {
                        "theorem": theorem_name,
                        "intervention": name,
                        "error": f"comparison_read: {type(e).__name__}: {e}",
                    }
                )
                skipped_interventions += 1
                _note_metrics_for_intervention(skipped=True)
                continue
            if not isinstance(comparison, dict):
                skipped_interventions += 1
                _note_metrics_for_intervention(skipped=True)
                continue

            try:
                int_graph = _load_graph(theorem_dir / f"{name}_graph.json")
            except Exception as e:
                errors.append(
                    {
                        "theorem": theorem_name,
                        "intervention": name,
                        "error": f"int_graph: {type(e).__name__}: {e}",
                    }
                )
                skipped_interventions += 1
                _note_metrics_for_intervention(skipped=True)
                continue

            intervention_solution_goal_sigs = _solution_goal_sigs_from_files(
                theorem_dir / f"{name}_history.json",
                theorem_dir / f"{name}_mcts_tree.json",
            )

            k_entry = compute_k_search_efficiency_from_logs(
                theorem_dir=theorem_dir,
                variant=name,
                goal_cache=goal_cache,
                family_priors=family_priors,
            )

            if goal_sig_ted is None:
                soft_ged = _pending_soft_ged_entry()
                novelty = _pending_goal_novelty_entry()
                path_dist = _pending_solution_path_entry()
                if goal_sig_scheme != "ast":
                    scheme_note = f"goal_sig_scheme={goal_sig_scheme!r}; requires 'ast'"
                    soft_ged["validity_notes"].append(scheme_note)
                    novelty["validity_notes"].append(scheme_note)
                    path_dist["validity_notes"].append(scheme_note)
                if ted_error:
                    err_note = f"goal_sig_ted_init_error: {ted_error}"
                    soft_ged["validity_notes"].append(err_note)
                    novelty["validity_notes"].append(err_note)
                    path_dist["validity_notes"].append(err_note)
            else:
                existing_soft_ged = comparison.get("ged_search_graph_soft")
                existing_novelty = comparison.get("goal_novelty")
                existing_path_dist = comparison.get("solution_path_soft_distance")

                if params.resume and not _is_pending_metric_entry(existing_soft_ged):
                    soft_ged = existing_soft_ged  # type: ignore[assignment]
                else:
                    try:
                        soft_ged = compute_soft_search_graph_ged(
                            wild_graph,
                            int_graph,
                            goal_sig_ted=goal_sig_ted,
                            max_nodes=params.max_soft_ged_nodes,
                            max_edges=params.max_soft_ged_edges,
                        )
                    except Exception as e:
                        soft_ged = _soft_ged_exception_entry(e)

                if params.resume and not _is_pending_metric_entry(existing_novelty):
                    novelty = existing_novelty  # type: ignore[assignment]
                else:
                    try:
                        novelty = compute_goal_novelty(
                            wild_graph,
                            int_graph,
                            goal_sig_ted=goal_sig_ted,
                            max_pairs=params.max_novelty_pairs,
                        )
                    except Exception as e:
                        novelty = _goal_novelty_exception_entry(e)

                if params.resume and not _is_pending_metric_entry(existing_path_dist):
                    path_dist = existing_path_dist  # type: ignore[assignment]
                else:
                    try:
                        path_dist = compute_solution_path_soft_distance(
                            wild_solution_goal_sigs,
                            intervention_solution_goal_sigs,
                            goal_sig_ted=goal_sig_ted,
                            max_dp_cells=params.max_path_dp_cells,
                        )
                    except Exception as e:
                        path_dist = _solution_path_exception_entry(
                            e,
                            wild_len=len(wild_solution_goal_sigs),
                            intervention_len=len(intervention_solution_goal_sigs),
                        )

            changed = False
            if comparison.get("ged_search_graph_soft") != soft_ged:
                comparison["ged_search_graph_soft"] = soft_ged
                changed = True
            if comparison.get("goal_novelty") != novelty:
                comparison["goal_novelty"] = novelty
                changed = True
            if comparison.get("solution_path_soft_distance") != path_dist:
                comparison["solution_path_soft_distance"] = path_dist
                changed = True
            if comparison.get("k_search_efficiency") != k_entry:
                comparison["k_search_efficiency"] = k_entry
                changed = True
            if changed:
                write_json_atomic(comparison_path, comparison)

            int_entry["ged_search_graph_soft"] = soft_ged
            int_entry["goal_novelty"] = novelty
            int_entry["solution_path_soft_distance"] = path_dist
            int_entry["k_search_efficiency"] = _k_summary(k_entry)
            if isinstance(k_entry, dict) and k_entry.get("valid") is True:
                metrics_computed["k_search_efficiency"] += 1
            else:
                metrics_skipped["k_search_efficiency"] += 1
            updated_interventions += 1
            _note_metrics_for_intervention(
                soft_ged=soft_ged,
                novelty=novelty,
                path_dist=path_dist,
            )

        if progress_cb is not None:
            progress_cb(
                {
                    "event": "postprocess_progress",
                    "run_dir": str(run_dir),
                    "theorem_idx": theorem_idx,
                    "theorems_total": total_theorems,
                    "theorem": theorem_name,
                    "updated_interventions": updated_interventions,
                    "skipped_interventions": skipped_interventions,
                    "metrics_computed": dict(metrics_computed),
                    "metrics_skipped": dict(metrics_skipped),
                }
            )

    # Recompute validity counts based on the updated summary payload.
    ged_validity = summary.get("aggregates", {}).get("ged_validity")
    if isinstance(ged_validity, dict) and "ged_search_graph_soft" in ged_validity:
        valid = 0
        invalid = 0
        for theorem in theorems_raw:
            if not isinstance(theorem, dict):
                continue
            for intervention in theorem.get("interventions", []):
                if not isinstance(intervention, dict):
                    continue
                entry = intervention.get("ged_search_graph_soft")
                if not isinstance(entry, dict):
                    invalid += 1
                elif entry.get("valid") is True:
                    valid += 1
                else:
                    invalid += 1
        ged_validity["ged_search_graph_soft"] = {"valid": valid, "invalid": invalid}

    write_json_gz_atomic(summary_path, summary)

    root_goal_similarity_path = run_dir / "root_goal_similarity.json"
    try:
        root_report = compute_root_goal_similarity(
            run_dir,
            max_theorems=params.max_root_goal_theorems,
            max_knn_theorems=params.max_root_goal_knn_theorems,
            knn_k=params.root_goal_knn_k,
            knn_sample_size=params.root_goal_knn_sample,
            sample_size=params.root_goal_sample_size,
            mode=params.root_goal_mode,
        )
    except Exception as e:
        root_report = {
            "schema_version": 1,
            "valid": False,
            "validity_notes": [f"exception: {type(e).__name__}: {e}"],
        }
    write_json_atomic(root_goal_similarity_path, root_report)

    return {
        "run_dir": str(run_dir),
        "provider": run.provider,
        "goal_sig_scheme": goal_sig_scheme,
        "updated_interventions": updated_interventions,
        "skipped_interventions": skipped_interventions,
        "metrics": {
            "computed": sum(metrics_computed.values()),
            "skipped": sum(metrics_skipped.values()),
            "by_metric": {
                "ged_search_graph_soft": {
                    "computed": metrics_computed["ged_search_graph_soft"],
                    "skipped": metrics_skipped["ged_search_graph_soft"],
                },
                "goal_novelty": {
                    "computed": metrics_computed["goal_novelty"],
                    "skipped": metrics_skipped["goal_novelty"],
                },
                "solution_path_soft_distance": {
                    "computed": metrics_computed["solution_path_soft_distance"],
                    "skipped": metrics_skipped["solution_path_soft_distance"],
                },
                "k_search_efficiency": {
                    "computed": metrics_computed["k_search_efficiency"],
                    "skipped": metrics_skipped["k_search_efficiency"],
                },
            },
        },
        "errors": errors,
    }


def postprocess_run(
    log_dir: Path,
    *,
    params: PostprocessParams | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Compute heavy metrics after the fact and write results into the run directory."""

    params = params or PostprocessParams()
    provider_runs = iter_provider_runs(log_dir)

    runs_report: list[dict[str, Any]] = []
    for run in provider_runs:
        runs_report.append(
            postprocess_provider_run(run, params=params, progress_cb=progress_cb)
        )

    summary_sha = sha256_file(log_dir / "summary.json.gz")
    goal_cache_sha = sha256_file(log_dir / "goal_cache.json.gz")
    metrics_total = {
        "ged_search_graph_soft": {"computed": 0, "skipped": 0},
        "goal_novelty": {"computed": 0, "skipped": 0},
        "solution_path_soft_distance": {"computed": 0, "skipped": 0},
        "k_search_efficiency": {"computed": 0, "skipped": 0},
    }
    for run in runs_report:
        metrics = run.get("metrics")
        if not isinstance(metrics, dict):
            continue
        by_metric = metrics.get("by_metric")
        if not isinstance(by_metric, dict):
            continue
        for key, agg in metrics_total.items():
            data = by_metric.get(key)
            if not isinstance(data, dict):
                continue
            computed = data.get("computed")
            skipped = data.get("skipped")
            if isinstance(computed, int):
                agg["computed"] += computed
            if isinstance(skipped, int):
                agg["skipped"] += skipped
    total_computed = sum(v["computed"] for v in metrics_total.values())
    total_skipped = sum(v["skipped"] for v in metrics_total.values())

    report = {
        "schema_version": 1,
        "valid": True,
        "computed_at": utc_timestamp(),
        "params": {
            "max_soft_ged_nodes": params.max_soft_ged_nodes,
            "max_soft_ged_edges": params.max_soft_ged_edges,
            "max_novelty_pairs": params.max_novelty_pairs,
            "max_path_dp_cells": params.max_path_dp_cells,
            "max_root_goal_theorems": params.max_root_goal_theorems,
            "max_root_goal_knn_theorems": params.max_root_goal_knn_theorems,
            "root_goal_knn_k": params.root_goal_knn_k,
            "root_goal_knn_sample": params.root_goal_knn_sample,
            "root_goal_sample_size": params.root_goal_sample_size,
            "root_goal_mode": params.root_goal_mode,
            "external_statement_max_full": params.external_statement_max_full,
            "external_statement_max_knn": params.external_statement_max_knn,
            "external_statement_knn_k": params.external_statement_knn_k,
            "external_statement_knn_sample": params.external_statement_knn_sample,
            "external_statement_sample_size": params.external_statement_sample_size,
            "external_statement_mode": params.external_statement_mode,
            "resume": params.resume,
        },
        "inputs": {
            "summary_sha256": summary_sha,
            "goal_cache_sha256": goal_cache_sha,
        },
        "metrics": {
            "computed": total_computed,
            "skipped": total_skipped,
            "by_metric": metrics_total,
        },
        "runs": runs_report,
    }
    return report
