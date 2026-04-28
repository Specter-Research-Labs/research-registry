from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from atp.coq.process_trace import CoqProcessTrace
from corpus.artifacts import timestamp, write_json_atomic
from prover.expr import ExprDAG
from prover.proof import (
    GRAPH_FAMILY_EXTERNAL_PROOF,
    GRAPH_FAMILY_SEARCH_TRACE,
    ProofGraph,
    canonical_edge_match,
    canonical_node_match,
)


@dataclass
class ExternalProof:
    graph: ProofGraph
    solved: bool
    proof_term: ExprDAG | None = None
    iterations: int | None = None
    metrics_overrides: dict[str, Any] = field(default_factory=dict)
    trace_graph: ProofGraph | None = None
    process_trace: CoqProcessTrace | None = None
    trace_source: str | None = None
    trace_completeness: str | None = None


@dataclass
class ExternalInterventionResult:
    name: str
    proof: ExternalProof
    blocked: list[str] = field(default_factory=list)
    is_control: bool = False
    ged: float | None = None
    axiom_delta: list[str] | None = None
    axiom_removed: list[str] | None = None


@dataclass
class ExternalTheoremResult:
    name: str
    wild_type: ExternalProof
    interventions: list[ExternalInterventionResult] = field(default_factory=list)


def _tactic_diversity(graph: ProofGraph) -> int | None:
    if graph.graph.number_of_edges() == 0:
        return 0
    tactics = set()
    for _, _, data in graph.graph.edges(data=True):
        tactic_norm = data.get("tactic_norm")
        tactic = data.get("tactic")
        if tactic_norm:
            tactics.add(tactic_norm)
        elif tactic:
            tactics.add(tactic)
    return len(tactics) if tactics else None


def _build_metrics(proof: ExternalProof) -> dict[str, Any]:
    graph_stats = proof.graph.stats()
    trajectory = {
        "total_iterations": proof.iterations,
        "max_depth_reached": graph_stats.get("max_depth"),
        "backtrack_count": None,
        "unique_goals_visited": graph_stats.get("nodes"),
        "tactic_diversity": _tactic_diversity(proof.graph),
    }
    detour = {
        "failure_ratio": None,
    }
    metrics = {
        "trajectory": trajectory,
        "detour": detour,
        "proof_term": proof.proof_term.metrics() if proof.proof_term else None,
        "solution_path": None,
        "tactic_fingerprint": None,
        "proof_term_pretty": None,
    }
    if proof.metrics_overrides:
        metrics.update(proof.metrics_overrides)
    return metrics


def _compute_pairwise_ged(result: ExternalTheoremResult) -> dict[str, Any]:
    variants: list[tuple[str, ProofGraph]] = [("wild_type", result.wild_type.graph)]
    for intervention in result.interventions:
        variants.append((intervention.name, intervention.proof.graph))

    matrix: dict[str, dict[str, float | None]] = {}
    for name1, graph1 in variants:
        matrix[name1] = {}
        for name2, graph2 in variants:
            if name1 == name2:
                matrix[name1][name2] = 0.0
                continue
            try:
                ged = nx.graph_edit_distance(
                    graph1.to_canonical(),
                    graph2.to_canonical(),
                    node_match=canonical_node_match,
                    edge_match=canonical_edge_match,
                    timeout=5.0,
                )
                matrix[name1][name2] = ged
            except (nx.NetworkXError, TypeError, ValueError):
                matrix[name1][name2] = None

    return {
        "theorem": result.name,
        "variants": [v[0] for v in variants],
        "ged_matrix": matrix,
    }


def _build_ged_entry(
    value: float | None,
    *,
    normalized: float | None,
    trace_source: str,
    trace_completeness: str,
    valid: bool,
    validity_notes: list[str] | None = None,
) -> dict | None:
    if value is None:
        return None
    notes = validity_notes or []
    return {
        "value": value,
        "normalized": normalized,
        "valid": valid,
        "validity_notes": notes,
        "trace_source": trace_source,
        "trace_completeness": trace_completeness,
    }


def _write_proof_term(path: Path, proof_term: ExprDAG) -> None:
    with gzip.open(path.with_suffix(path.suffix + ".gz"), "wt") as f:
        json.dump(proof_term.serialize(), f)


def _write_process_trace(path: Path, process_trace: CoqProcessTrace) -> None:
    with gzip.open(path.with_suffix(path.suffix + ".gz"), "wt") as f:
        json.dump(process_trace.serialize(), f)


def _write_proof_graph(path: Path, graph: ProofGraph, graph_kind: str) -> None:
    with open(path, "w") as f:
        data = graph.serialize()
        if "graph_family" not in data or data["graph_family"] == "unknown":
            data["graph_family"] = GRAPH_FAMILY_EXTERNAL_PROOF
            data["graph_backend"] = data.get("graph_backend") or "unknown"
            data["graph_provenance"] = "proof_object"
        data["graph_kind"] = graph_kind
        json.dump(data, f, indent=2)


def _write_trace_graph(
    path: Path,
    graph: ProofGraph,
    trace_source: str,
    trace_completeness: str,
) -> None:
    with open(path, "w") as f:
        data = graph.serialize()
        if "graph_family" not in data or data["graph_family"] == "unknown":
            data["graph_family"] = GRAPH_FAMILY_SEARCH_TRACE
            data["graph_backend"] = data.get("graph_backend") or "unknown"
            data["graph_provenance"] = "proxy"
        data["graph_kind"] = "trace_graph"
        data["trace_source"] = trace_source
        data["trace_completeness"] = trace_completeness
        data["valid"] = True
        data["validity_notes"] = []
        json.dump(data, f, indent=2)


class ExternalRunWriter:
    def __init__(
        self,
        log_dir: Path,
        run_config: dict[str, Any],
        goal_sig_scheme: str | None = None,
        goal_sig_stats: dict[str, Any] | None = None,
    ) -> None:
        self.log_dir = log_dir
        self.goal_sig_scheme = goal_sig_scheme
        self.goal_sig_stats = goal_sig_stats
        self.log_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.log_dir / "run_config.json", run_config)

    def write_run_status(
        self,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        partial_results: bool = False,
        capabilities: dict[str, bool] | None = None,
    ) -> None:
        existing_payload: dict[str, Any] | None = None
        status_path = self.log_dir / "run_status.json"
        if status_path.exists():
            try:
                loaded = json.loads(status_path.read_text())
            except Exception:
                loaded = None
            if isinstance(loaded, dict):
                existing_payload = loaded
        if started_at is None and existing_payload is not None:
            existing_started_at = existing_payload.get("started_at")
            if isinstance(existing_started_at, str) and existing_started_at:
                started_at = existing_started_at
        if capabilities is None:
            existing_capabilities = (
                existing_payload.get("capabilities") if existing_payload is not None else None
            )
            if isinstance(existing_capabilities, dict):
                capabilities = {
                    str(key): bool(value)
                    for key, value in existing_capabilities.items()
                }
            else:
                capabilities = {
                    "has_proof_term": False,
                    "has_proof_term_pretty": False,
                    "has_assembly_trace": False,
                    "has_process_trace": False,
                    "has_proof_term_metrics": False,
                }
        payload = {
            "status": status,
            "started_at": started_at or timestamp(),
            "completed_at": completed_at,
            "goal_id_scheme": "external",
            "partial_results": partial_results,
            "capabilities": capabilities,
        }
        write_json_atomic(status_path, payload)

    def write_results(
        self,
        results: list[ExternalTheoremResult],
        crashed: list[dict[str, Any]] | None = None,
    ) -> None:
        summary_theorems = []
        all_ged_matrices = []
        for result in results:
            theorem_dir = self.log_dir / result.name
            theorem_dir.mkdir(parents=True, exist_ok=True)

            _write_proof_graph(
                theorem_dir / "wild_type_graph.json",
                result.wild_type.graph,
                "proof_graph",
            )
            wild_metrics = _build_metrics(result.wild_type)
            with open(theorem_dir / "wild_type_metrics.json", "w") as f:
                json.dump(wild_metrics, f, indent=2)

            if result.wild_type.proof_term:
                _write_proof_term(
                    theorem_dir / "wild_type_proof_term.json", result.wild_type.proof_term
                )
            if result.wild_type.process_trace:
                _write_process_trace(
                    theorem_dir / "wild_type_process_trace.json",
                    result.wild_type.process_trace,
                )

            wild_trace = result.wild_type.trace_graph
            wild_trace_source = result.wild_type.trace_source or "tstp"
            wild_trace_completeness = result.wild_type.trace_completeness or "proxy"
            if wild_trace:
                _write_trace_graph(
                    theorem_dir / "wild_type_search_trace_graph.json",
                    wild_trace,
                    wild_trace_source,
                    wild_trace_completeness,
                )

            wild_canonical = result.wild_type.graph.to_canonical()
            wild_size = wild_canonical.number_of_nodes() + wild_canonical.number_of_edges()
            wild_trace_canonical = (
                wild_trace.to_canonical() if wild_trace is not None else None
            )
            wild_trace_size = (
                wild_trace_canonical.number_of_nodes() + wild_trace_canonical.number_of_edges()
                if wild_trace_canonical is not None
                else None
            )

            intervention_summaries = []
            for intervention in result.interventions:
                name = intervention.name
                _write_proof_graph(
                    theorem_dir / f"{name}_graph.json",
                    intervention.proof.graph,
                    "proof_graph",
                )
                int_metrics = _build_metrics(intervention.proof)
                with open(theorem_dir / f"{name}_metrics.json", "w") as f:
                    json.dump(int_metrics, f, indent=2)
                if intervention.proof.proof_term:
                    _write_proof_term(
                        theorem_dir / f"{name}_proof_term.json", intervention.proof.proof_term
                    )
                if intervention.proof.process_trace:
                    _write_process_trace(
                        theorem_dir / f"{name}_process_trace.json",
                        intervention.proof.process_trace,
                    )

                if intervention.proof.trace_graph:
                    _write_trace_graph(
                        theorem_dir / f"{name}_search_trace_graph.json",
                        intervention.proof.trace_graph,
                        intervention.proof.trace_source or wild_trace_source,
                        intervention.proof.trace_completeness or wild_trace_completeness,
                    )

                int_canonical = intervention.proof.graph.to_canonical()
                int_size = int_canonical.number_of_nodes() + int_canonical.number_of_edges()
                max_size = max(wild_size, int_size)
                normalized = (
                    intervention.ged / max_size
                    if intervention.ged is not None and max_size > 0
                    else None
                )
                ged_proof_graph = _build_ged_entry(
                    intervention.ged,
                    normalized=normalized,
                    trace_source="proof_object",
                    trace_completeness="full",
                    valid=True,
                    validity_notes=[],
                )
                ged_trace_graph = None
                trace_ged = None
                if wild_trace_canonical is not None and intervention.proof.trace_graph is not None:
                    trace_canonical = intervention.proof.trace_graph.to_canonical()
                    trace_size = (
                        trace_canonical.number_of_nodes()
                        + trace_canonical.number_of_edges()
                    )
                    trace_max = max(wild_trace_size or 0, trace_size)
                    try:
                        trace_ged = nx.graph_edit_distance(
                            wild_trace_canonical,
                            trace_canonical,
                            node_match=canonical_node_match,
                            edge_match=canonical_edge_match,
                            timeout=5.0,
                        )
                    except (nx.NetworkXError, TypeError, ValueError):
                        trace_ged = None
                if trace_ged is not None:
                    ged_trace_graph = _build_ged_entry(
                        trace_ged,
                        normalized=trace_ged / trace_max if trace_max > 0 else None,
                        trace_source=intervention.proof.trace_source
                        or wild_trace_source,
                        trace_completeness=intervention.proof.trace_completeness
                        or wild_trace_completeness,
                        valid=True,
                        validity_notes=[],
                    )
                status = "solved" if intervention.proof.solved else "failed"
                intervention_summaries.append(
                    {
                        "name": name,
                        "blocked": sorted(intervention.blocked),
                        "is_control": intervention.is_control,
                        "baseline_solved": result.wild_type.solved,
                        "solved": intervention.proof.solved,
                        "status": status,
                        "ged_search_graph": None,
                        "ged_proof_graph": ged_proof_graph,
                        "ged_trace_graph": ged_trace_graph,
                        "axiom_delta": intervention.axiom_delta,
                        "axiom_removed": intervention.axiom_removed,
                        "metrics": int_metrics,
                    }
                )

            summary_theorems.append(
                {
                    "name": result.name,
                    "wild_type": {
                        "solved": result.wild_type.solved,
                        "iterations": result.wild_type.iterations,
                        "proof_term_hash": result.wild_type.proof_term.structural_hash()
                        if result.wild_type.proof_term
                        else None,
                        "metrics": wild_metrics,
                    },
                    "interventions": intervention_summaries,
                }
            )

            ged_matrix = _compute_pairwise_ged(result)
            with open(theorem_dir / "ged_matrix.json", "w") as f:
                json.dump(ged_matrix, f, indent=2)
            all_ged_matrices.append(ged_matrix)

        with open(self.log_dir / "all_ged_matrices.json", "w") as f:
            json.dump(all_ged_matrices, f, indent=2)

        crashed_list = crashed or []
        total_interventions = sum(len(t.interventions) for t in results)
        solved_interventions = sum(
            1 for t in results for i in t.interventions if i.proof.solved
        )
        ged_validity = {
            "ged_search_graph": {"valid": 0, "invalid": 0},
            "ged_proof_graph": {"valid": 0, "invalid": 0},
            "ged_trace_graph": {"valid": 0, "invalid": 0},
        }
        for theorem in summary_theorems:
            for intervention in theorem.get("interventions", []):
                if not isinstance(intervention, dict):
                    continue
                for key in ("ged_search_graph", "ged_proof_graph", "ged_trace_graph"):
                    entry = intervention.get(key)
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("valid") is True:
                        ged_validity[key]["valid"] += 1
                    else:
                        ged_validity[key]["invalid"] += 1
        summary = {
            "run_id": self.log_dir.name,
            "theorems": summary_theorems,
            "crashed": crashed_list,
            "goal_sig_scheme": self.goal_sig_scheme,
            "goal_sig_stats": self.goal_sig_stats,
            "aggregates": {
                "theorem_count": len(results),
                "crashed_count": len(crashed_list),
                "wild_type_solve_rate": sum(1 for r in results if r.wild_type.solved)
                / len(results)
                if results
                else 0,
                "intervention_count": total_interventions,
                "intervention_solve_rate": solved_interventions / total_interventions
                if total_interventions
                else 0,
                "ged_validity": ged_validity,
                "goal_type_tactic_matrix": {},
            },
        }

        with gzip.open(self.log_dir / "summary.json.gz", "wt") as f:
            json.dump(summary, f)

        has_any_proof_term = any(
            bool(r.wild_type.proof_term)
            or any(bool(i.proof.proof_term) for i in r.interventions)
            for r in results
        )
        capabilities = {
            "has_proof_term": has_any_proof_term,
            "has_proof_term_pretty": False,
            "has_assembly_trace": False,
            "has_process_trace": any(
                bool(r.wild_type.process_trace)
                or any(bool(i.proof.process_trace) for i in r.interventions)
                for r in results
            ),
            "has_proof_term_metrics": has_any_proof_term,
        }
        status_path = self.log_dir / "run_status.json"
        if status_path.exists():
            status_data = json.loads(status_path.read_text())
            if isinstance(status_data, dict):
                status_data["capabilities"] = capabilities
                write_json_atomic(status_path, status_data)
        else:
            self.write_run_status(
                status="completed",
                completed_at=timestamp(),
                partial_results=False,
                capabilities=capabilities,
            )
