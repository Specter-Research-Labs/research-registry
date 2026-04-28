#!/usr/bin/env python3
"""
Analyze corpus experiment results for platonic pattern classification.

Classifies interventions into:
- TYPE_A_ISOMORPHIC: Same proof structure, tactics are superficial variants
- TYPE_B_ANISOMORPHIC: Fundamentally different proof approaches
- TYPE_C_PSEUDO_ISOMORPHIC: Same proof principle, different tactical decomposition depth
- UNSOLVED: No solution path for intervention
- UNKNOWN: Cannot classify (missing data)

Usage:
    python analyze_corpus.py logs/corpus-2025-12-28-195745/
"""

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from analysis.logs import ged_value, read_json_auto
from prover import ExprDAG, compute_complexity, metrics_to_dict


class Classification(Enum):
    TYPE_A_ISOMORPHIC = "TYPE_A_ISOMORPHIC"
    TYPE_B_ANISOMORPHIC = "TYPE_B_ANISOMORPHIC"
    TYPE_C_PSEUDO_ISOMORPHIC = "TYPE_C_PSEUDO_ISOMORPHIC"
    UNSOLVED = "UNSOLVED"
    UNKNOWN = "UNKNOWN"


@dataclass
class InterventionAnalysis:
    theorem: str
    intervention: str
    classification: Classification
    reason: str
    wild_type_nodes: int | None
    intervention_nodes: int | None
    node_ratio: float | None
    ged: float | None
    axiom_delta: list[str] | None
    axiom_removed: list[str] | None
    wild_type_iterations: int | None
    intervention_iterations: int | None
    consts_only_in_wild: list[str]
    consts_only_in_intervention: list[str]
    wild_complexity: dict = field(default_factory=dict)
    intervention_complexity: dict = field(default_factory=dict)


def load_json(path: Path) -> dict | None:
    gz_path = path.with_suffix(path.suffix + ".gz")
    if gz_path.exists():
        return read_json_auto(gz_path)
    if path.exists():
        return read_json_auto(path)
    return None


PSEUDO_ISO_MAX_GED = 3.0
PSEUDO_ISO_NODE_RATIO_RANGE = (0.5, 2.0)
SIMPLER_THRESHOLD = 0.3
COMPLEX_THRESHOLD = 3.0


def classify_intervention(
    comparison: dict,
    wild_metrics: dict,
    int_metrics: dict,
) -> tuple[Classification, str]:
    int_solution = int_metrics.get("solution_path")
    if int_solution is None:
        return Classification.UNSOLVED, "no solution_path"

    ged = ged_value(comparison.get("ged_search_graph"))
    proof_term_diff = comparison.get("proof_term_diff")
    axiom_delta = comparison.get("axiom_delta") or []
    axiom_removed = comparison.get("axiom_removed") or []

    wild_pt = wild_metrics.get("proof_term")
    int_pt = int_metrics.get("proof_term")

    if wild_pt is None or int_pt is None:
        return Classification.UNKNOWN, "missing proof term data"
    if ged is None:
        return Classification.UNKNOWN, "missing ged_search_graph"

    wild_nodes = wild_pt.get("node_count", 0)
    int_nodes = int_pt.get("node_count", 0)

    if wild_nodes == 0 or int_nodes == 0:
        return Classification.UNKNOWN, "zero node count"

    node_ratio = int_nodes / wild_nodes

    if proof_term_diff and proof_term_diff.get("identical"):
        return Classification.TYPE_A_ISOMORPHIC, "identical proof terms"

    if comparison.get("wild_type_hash") == comparison.get("intervention_hash"):
        return Classification.TYPE_A_ISOMORPHIC, "matching structural hash"

    if ged == 0:
        return Classification.TYPE_A_ISOMORPHIC, "ged=0"

    lo, hi = PSEUDO_ISO_NODE_RATIO_RANGE
    if ged is not None and ged < PSEUDO_ISO_MAX_GED and lo < node_ratio < hi:
        return (
            Classification.TYPE_C_PSEUDO_ISOMORPHIC,
            f"ged={ged:.1f}, node_ratio={node_ratio:.2f}",
        )

    if node_ratio < SIMPLER_THRESHOLD:
        return (
            Classification.TYPE_C_PSEUDO_ISOMORPHIC,
            f"intervention much simpler ({int_nodes} vs {wild_nodes} nodes)",
        )

    if node_ratio > COMPLEX_THRESHOLD:
        return (
            Classification.TYPE_C_PSEUDO_ISOMORPHIC,
            f"intervention more complex ({int_nodes} vs {wild_nodes} nodes)",
        )

    reason = f"ged={ged:.1f}, node_ratio={node_ratio:.2f}, different approach"
    if axiom_delta or axiom_removed:
        axiom_parts = []
        if axiom_delta:
            axiom_parts.append(f"+{','.join(axiom_delta)}")
        if axiom_removed:
            axiom_parts.append(f"-{','.join(axiom_removed)}")
        reason = f"{reason}, axiom_change={''.join(axiom_parts)}"
    return Classification.TYPE_B_ANISOMORPHIC, reason


def load_complexity(proof_term_path: Path) -> dict:
    if not proof_term_path.exists():
        return {}
    data = load_json(proof_term_path)
    if data is None:
        return {}
    dag = ExprDAG.from_json(data)
    return metrics_to_dict(compute_complexity(dag))


def analyze_theorem(theorem_dir: Path) -> list[InterventionAnalysis]:
    results = []

    wild_metrics = load_json(theorem_dir / "wild_type_metrics.json")
    if wild_metrics is None:
        return results

    wild_complexity = load_complexity(theorem_dir / "wild_type_proof_term.json")

    for comparison_file in theorem_dir.glob("*_comparison.json"):
        intervention_name = comparison_file.stem.replace("_comparison", "")
        comparison = load_json(comparison_file)
        int_metrics = load_json(theorem_dir / f"{intervention_name}_metrics.json")

        if comparison is None or int_metrics is None:
            continue

        int_complexity = load_complexity(
            theorem_dir / f"{intervention_name}_proof_term.json"
        )

        classification, reason = classify_intervention(
            comparison, wild_metrics, int_metrics
        )

        wild_pt = wild_metrics.get("proof_term") or {}
        int_pt = int_metrics.get("proof_term") or {}
        wild_traj = wild_metrics.get("trajectory") or {}
        int_traj = int_metrics.get("trajectory") or {}
        proof_term_diff = comparison.get("proof_term_diff") or {}

        wild_nodes = wild_pt.get("node_count")
        int_nodes = int_pt.get("node_count")
        node_ratio = None
        if wild_nodes and int_nodes:
            node_ratio = int_nodes / wild_nodes

        results.append(
            InterventionAnalysis(
                theorem=theorem_dir.name,
                intervention=intervention_name,
                classification=classification,
                reason=reason,
                wild_type_nodes=wild_nodes,
                intervention_nodes=int_nodes,
                node_ratio=node_ratio,
                ged=ged_value(comparison.get("ged_search_graph")),
                axiom_delta=comparison.get("axiom_delta"),
                axiom_removed=comparison.get("axiom_removed"),
                wild_type_iterations=wild_traj.get("total_iterations"),
                intervention_iterations=int_traj.get("total_iterations"),
                consts_only_in_wild=proof_term_diff.get("consts_only_in_self", []),
                consts_only_in_intervention=proof_term_diff.get("consts_only_in_other", []),
                wild_complexity=wild_complexity,
                intervention_complexity=int_complexity,
            )
        )

    return results


def generate_report(analyses: list[InterventionAnalysis], log_dir: Path) -> dict:
    summary = {c.value: 0 for c in Classification}
    for a in analyses:
        summary[a.classification.value] += 1

    by_theorem: dict[str, list[dict]] = {}
    for a in analyses:
        if a.theorem not in by_theorem:
            by_theorem[a.theorem] = []
        by_theorem[a.theorem].append(
            {
                "name": a.intervention,
                "classification": a.classification.value,
                "reason": a.reason,
                "proof_term_comparison": {
                    "wild_nodes": a.wild_type_nodes,
                    "intervention_nodes": a.intervention_nodes,
                    "node_ratio": a.node_ratio,
                    "consts_only_in_wild": a.consts_only_in_wild,
                    "consts_only_in_intervention": a.consts_only_in_intervention,
                },
                "complexity": {
                    "wild": a.wild_complexity,
                    "intervention": a.intervention_complexity,
                },
                "search_dynamics": {
                    "wild_iterations": a.wild_type_iterations,
                    "intervention_iterations": a.intervention_iterations,
                    "ged_search_graph": a.ged,
                    "axiom_delta": a.axiom_delta,
                    "axiom_removed": a.axiom_removed,
                },
            }
        )

    return {
        "log_dir": str(log_dir),
        "classification_summary": summary,
        "total_interventions": len(analyses),
        "by_theorem": [
            {"theorem": theorem, "interventions": interventions}
            for theorem, interventions in sorted(by_theorem.items())
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_corpus.py <log_dir>")
        sys.exit(1)

    log_dir = Path(sys.argv[1])
    if not log_dir.exists():
        print(f"Error: {log_dir} does not exist")
        sys.exit(1)

    analyses = []
    for theorem_dir in log_dir.iterdir():
        if theorem_dir.is_dir() and not theorem_dir.name.startswith("."):
            analyses.extend(analyze_theorem(theorem_dir))

    report = generate_report(analyses, log_dir)

    with open(log_dir / "analysis_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"Analysis complete: {len(analyses)} interventions analyzed")
    print("Results saved to:")
    print(f"  {log_dir / 'analysis_report.json'}")
    print()
    print("Summary:")
    for classification, count in report["classification_summary"].items():
        print(f"  {classification}: {count}")


if __name__ == "__main__":
    main()
