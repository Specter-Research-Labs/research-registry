#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    raise SystemExit(
        "Run from dossiers/wonton-soup with "
        "`uv run python -m experiments.cellular_sheaf.run <corpus_dir>`."
    )

from prover import GoalCache
from prover.mcts import TACTIC_FAMILIES, _family_index
from prover.providers.base import tactic_family

from .sheaves import EquivalenceSheaf, TacticTransformSheaf


@dataclass
class SheafReport:
    unique_sigs: int
    total_mvar_ids: int
    collapse_ratio: float
    edge_total: int
    edge_used: int
    edge_missing_parent_sig: int
    edge_missing_child_sig: int
    edges_by_family: dict[str, int]
    unique_sigs_in_edges: int
    edge_sig_coverage: float
    equiv_consistency: float
    inconsistent_cases: list[tuple[str, int, float]]
    tactic_residual: float
    per_family_residual: dict[int, float]
    intervention_deltas: dict[str, float]


@dataclass
class EdgeStats:
    total_success_edges: int = 0
    missing_parent_sig: int = 0
    missing_child_sig: int = 0


def load_cache(corpus_dir: Path) -> GoalCache | None:
    cache_path = corpus_dir / "goal_cache.json"
    cache_gz = corpus_dir / "goal_cache.json.gz"
    if not cache_path.exists() and not cache_gz.exists():
        return None
    try:
        return GoalCache.load(cache_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Goal cache load failed: {exc}")
        return None


def load_edges_from_history(
    corpus_dir: Path, cache: GoalCache
) -> tuple[
    list[tuple[str, str, int]],
    dict[str, list[tuple[str, str, int]]],
    EdgeStats,
]:
    wild_edges = []
    intervention_edges: dict[str, list[tuple[str, str, int]]] = {}
    stats = EdgeStats()

    for history_file in corpus_dir.glob("*/wild_type_history.json"):
        edges, edge_stats = extract_edges_from_file(history_file, cache)
        wild_edges.extend(edges)
        stats.total_success_edges += edge_stats.total_success_edges
        stats.missing_parent_sig += edge_stats.missing_parent_sig
        stats.missing_child_sig += edge_stats.missing_child_sig

    for history_file in corpus_dir.glob("*/block_*_history.json"):
        int_name = history_file.stem.replace("_history", "")
        edges, edge_stats = extract_edges_from_file(history_file, cache)
        if int_name not in intervention_edges:
            intervention_edges[int_name] = []
        intervention_edges[int_name].extend(edges)

    return wild_edges, intervention_edges, stats


def extract_edges_from_file(
    history_file: Path, cache: GoalCache
) -> tuple[list[tuple[str, str, int]], EdgeStats]:
    edges: list[tuple[str, str, int]] = []
    stats = EdgeStats()
    with open(history_file) as f:
        data = json.load(f)

    for it_data in data.get("iterations", []):
        selected_path = it_data.get("selected_path", [])
        if not selected_path:
            continue
        parent_mvar = selected_path[-1]

        for attempt in it_data.get("attempts", []):
            if attempt.get("outcome") != "success":
                continue
            tactic_norm = attempt.get("tactic_norm", "")
            fam = tactic_family(tactic_norm)
            fam_idx = _family_index(fam)

            parent_sig = cache.get_sig(parent_mvar)
            child_mvars = attempt.get("child_mvar_ids", [])
            if not child_mvars:
                continue
            stats.total_success_edges += len(child_mvars)
            if parent_sig is None:
                stats.missing_parent_sig += len(child_mvars)
                continue

            for child_mvar in child_mvars:
                child_sig = cache.get_sig(child_mvar)
                if not child_sig:
                    stats.missing_child_sig += 1
                    continue
                edges.append((parent_sig, child_sig, fam_idx))

    return edges, stats


def analyze_corpus(corpus_dir: Path) -> SheafReport | None:
    cache = load_cache(corpus_dir)
    if cache is None:
        print(f"No goal_cache.json found in {corpus_dir}")
        return None

    wild_edges, intervention_edges, edge_stats = load_edges_from_history(
        corpus_dir, cache
    )

    equiv = EquivalenceSheaf.from_cache(cache)
    tactic = TacticTransformSheaf.from_edges(wild_edges, cache)

    intervention_deltas = {}
    for name, int_edges in intervention_edges.items():
        delta = tactic.intervention_delta(int_edges, cache)
        intervention_deltas[name] = delta

    unique_sigs = len(cache.entries)
    total_mvar_ids = len(cache.mvar_to_sig)
    edges_by_family_idx: dict[int, int] = {}
    sigs_in_edges: set[str] = set()
    for parent_sig, child_sig, fam_idx in wild_edges:
        edges_by_family_idx[fam_idx] = edges_by_family_idx.get(fam_idx, 0) + 1
        sigs_in_edges.add(parent_sig)
        sigs_in_edges.add(child_sig)
    edges_by_family = {
        TACTIC_FAMILIES[k]: v for k, v in sorted(edges_by_family_idx.items())
    }
    unique_sigs_in_edges = len(sigs_in_edges)
    edge_sig_coverage = (
        unique_sigs_in_edges / unique_sigs if unique_sigs > 0 else 0.0
    )

    return SheafReport(
        unique_sigs=unique_sigs,
        total_mvar_ids=total_mvar_ids,
        collapse_ratio=total_mvar_ids / unique_sigs if unique_sigs > 0 else 1.0,
        edge_total=edge_stats.total_success_edges,
        edge_used=len(wild_edges),
        edge_missing_parent_sig=edge_stats.missing_parent_sig,
        edge_missing_child_sig=edge_stats.missing_child_sig,
        edges_by_family=edges_by_family,
        unique_sigs_in_edges=unique_sigs_in_edges,
        edge_sig_coverage=edge_sig_coverage,
        equiv_consistency=equiv.consistency(min_occurrences=2, min_attempts=3),
        inconsistent_cases=equiv.inconsistent_sigs(threshold=0.2),
        tactic_residual=tactic.residual_energy(cache),
        per_family_residual=tactic.per_family_residual(cache),
        intervention_deltas=intervention_deltas,
    )


def report_to_dict(report: SheafReport) -> dict:
    return {
        "unique_sigs": report.unique_sigs,
        "total_mvar_ids": report.total_mvar_ids,
        "collapse_ratio": report.collapse_ratio,
        "edge_total": report.edge_total,
        "edge_used": report.edge_used,
        "edge_missing_parent_sig": report.edge_missing_parent_sig,
        "edge_missing_child_sig": report.edge_missing_child_sig,
        "edges_by_family": report.edges_by_family,
        "unique_sigs_in_edges": report.unique_sigs_in_edges,
        "edge_sig_coverage": report.edge_sig_coverage,
        "equiv_consistency": report.equiv_consistency,
        "inconsistent_cases": [
            {"sig": sig, "family": fam, "variance": var}
            for sig, fam, var in report.inconsistent_cases
        ],
        "tactic_residual": report.tactic_residual,
        "per_family_residual": {
            TACTIC_FAMILIES[k]: v for k, v in report.per_family_residual.items()
        },
        "intervention_deltas": report.intervention_deltas,
    }


def print_report(report: SheafReport):
    print("=" * 60)
    print("SHEAF ANALYSIS REPORT")
    print("=" * 60)

    print("\nGoal Space:")
    print(f"  Unique signatures: {report.unique_sigs}")
    print(f"  Total occurrences: {report.total_mvar_ids}")
    print(f"  Collapse ratio:    {report.collapse_ratio:.2f}")

    print("\nEdge Coverage (wild type):")
    print(f"  Success edges:     {report.edge_total}")
    print(f"  Edges used:        {report.edge_used}")
    print(f"  Missing parent sig: {report.edge_missing_parent_sig}")
    print(f"  Missing child sig:  {report.edge_missing_child_sig}")
    print(f"  Sig coverage:      {report.edge_sig_coverage:.2f}")
    if report.edges_by_family:
        print("  Edges by family:")
        for fam, count in report.edges_by_family.items():
            print(f"    {fam:<15}: {count}")

    print("\nEquivalence Sheaf:")
    print(f"  Consistency: {report.equiv_consistency:.3f}")
    if report.inconsistent_cases:
        print("  Inconsistent (sig, family, variance):")
        for sig, fam, var in report.inconsistent_cases[:5]:
            print(f"    {sig[:8]}... family={TACTIC_FAMILIES[fam]}: {var:.3f}")
        if len(report.inconsistent_cases) > 5:
            print(f"    ... and {len(report.inconsistent_cases) - 5} more")

    print("\nTactic Transform Sheaf:")
    print(f"  Overall residual: {report.tactic_residual:.3f}")
    if report.per_family_residual:
        print("  Per-family residual:")
        for fam_idx, residual in sorted(report.per_family_residual.items()):
            print(f"    {TACTIC_FAMILIES[fam_idx]:<15}: {residual:.3f}")

    if report.intervention_deltas:
        print("\nIntervention Deltas (positive = worse fit):")
        for name, delta in sorted(
            report.intervention_deltas.items(), key=lambda x: -abs(x[1])
        ):
            sign = "+" if delta >= 0 else ""
            print(f"  {name:<25}: {sign}{delta:.3f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m experiments.cellular_sheaf.run <corpus_dir>")
        print("Example: python -m experiments.cellular_sheaf.run logs/corpus-2025-12-29-024205")
        sys.exit(1)

    corpus_dir = Path(sys.argv[1])
    if not corpus_dir.exists():
        print(f"Corpus directory not found: {corpus_dir}")
        sys.exit(1)

    report = analyze_corpus(corpus_dir)
    if report is None:
        print("Analysis failed - no cache found")
        sys.exit(1)
    assert report is not None

    output_path = corpus_dir / "sheaf_analysis.json"
    with open(output_path, "w") as f:
        json.dump(report_to_dict(report), f, indent=2)

    print(f"Analysis written to {output_path}\n")
    print_report(report)


if __name__ == "__main__":
    main()
