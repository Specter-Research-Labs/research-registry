from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from analysis.kernel import (
    _canonical_equivalent_law_id,  # noqa: F401
    _canonical_size5_unknown_followup,
    _combined_decision_surface,
    _kernel_bridge_analysis,
    _kernel_bridge_candidate_surface,
    _kernel_micro_rewrite_analysis,
    _kernel_micro_rewrite_candidate_surface,
    _residual_false_pair_canonicalization,
    _two_element_fingerprint_collision_analysis,
)
from analysis.search import (
    _candidate_feature_rules,
    _greedy_two_element_cover,
    _problem_features,
    _public_pair_duplicates,
    _size4_sat_search,
    _size5_sat_search,
    _source_law_strength,
    _three_element_countermodel_search,
    _top_feature_signals,
    _two_element_pair_evaluator,
    _two_element_source_row_semantics,
)
from analysis.theorems import _theorem_backed_true_rules
from graph import ImplicationGraph, status_counts
from laws import LawCatalog
from proof_catalog import build_constructive_proof_catalog
from public_benchmark import PublicProblem
from source_row_semantics import (
    build_two_element_theories,
    source_row_is_exact_under_two_element_theories,
)


def write_public_analysis(
    path: Path,
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
    size4_sat_timeout_ms: int = 0,
    size5_sat_timeout_ms: int = 0,
) -> dict[str, object]:
    analysis = build_public_analysis(
        catalog=catalog,
        graph=graph,
        problems=problems,
        size4_sat_timeout_ms=size4_sat_timeout_ms,
        size5_sat_timeout_ms=size5_sat_timeout_ms,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return analysis


def build_public_analysis(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
    size4_sat_timeout_ms: int = 0,
    size5_sat_timeout_ms: int = 0,
) -> dict[str, object]:
    graph_counts = status_counts(graph)
    by_difficulty = Counter(problem.difficulty for problem in problems)
    by_answer = Counter(problem.answer for problem in problems)
    by_status = Counter(problem.graph_status_name for problem in problems)
    false_problems = [problem for problem in problems if not problem.answer]
    theorem_backed_true_rules = _theorem_backed_true_rules(catalog, problems)
    proof_catalog = build_constructive_proof_catalog(catalog)
    two_element_theories = build_two_element_theories(catalog)
    exact_source_ids = {
        law_id
        for law_id in range(1, graph.law_count + 1)
        if source_row_is_exact_under_two_element_theories(
            law_id,
            two_element_theories,
            graph,
        )
    }
    problem_feature_rows = [(problem, _problem_features(catalog, problem)) for problem in problems]

    mapped_correctly = sum(
        1
        for problem in problems
        if (
            (problem.graph_status_name.endswith("_true") and problem.answer)
            or (problem.graph_status_name.endswith("_false") and not problem.answer)
        )
    )

    top_feature_signals = _top_feature_signals(catalog, problems)
    cover_entries = _greedy_two_element_cover(catalog, false_problems)
    two_element_covered_ids = {
        problem_id
        for entry in cover_entries
        for problem_id in entry.covered_problem_ids
    }
    two_element_covered = len(two_element_covered_ids)
    pair_evaluator = _two_element_pair_evaluator(
        catalog=catalog,
        false_problems=false_problems,
        theories=two_element_theories,
        greedy_cover_problem_ids=two_element_covered_ids,
    )
    three_element_countermodel_search = _three_element_countermodel_search(
        catalog,
        false_problems,
        two_element_covered_ids,
    )
    size4_sat_search = _size4_sat_search(
        catalog,
        false_problems,
        two_element_covered_ids,
        _coerce_problem_ids(three_element_countermodel_search["covered_problem_ids"]),
        size4_sat_timeout_ms,
    )
    size5_sat_search = _size5_sat_search(
        catalog,
        false_problems,
        two_element_covered_ids,
        _coerce_problem_ids(three_element_countermodel_search["covered_problem_ids"]),
        _coerce_problem_ids(size4_sat_search.get("covered_problem_ids", [])),
        size5_sat_timeout_ms,
    )
    false_covered_ids = (
        two_element_covered_ids
        | set(_coerce_problem_ids(three_element_countermodel_search["covered_problem_ids"]))
        | set(_coerce_problem_ids(size4_sat_search.get("covered_problem_ids", [])))
        | set(_coerce_problem_ids(size5_sat_search.get("covered_problem_ids", [])))
    )
    combined_decision_surface = _combined_decision_surface(
        catalog=catalog,
        graph=graph,
        problems=problems,
        theorem_backed_true_rules=theorem_backed_true_rules,
        theories=two_element_theories,
        exact_source_ids=exact_source_ids,
        false_covered_ids=false_covered_ids,
    )
    kernel_bridge_analysis = _kernel_bridge_analysis(
        catalog=catalog,
        combined_decision_surface=combined_decision_surface,
        proof_catalog=proof_catalog,
    )
    kernel_bridge_candidate_surface = _kernel_bridge_candidate_surface(
        combined_decision_surface=combined_decision_surface,
        kernel_bridge_analysis=kernel_bridge_analysis,
    )
    kernel_micro_rewrite_analysis = _kernel_micro_rewrite_analysis(
        catalog=catalog,
        kernel_bridge_analysis=kernel_bridge_analysis,
        proof_catalog=proof_catalog,
    )
    residual_false_pair_canonicalization = _residual_false_pair_canonicalization(
        catalog=catalog,
        graph=graph,
        combined_decision_surface=combined_decision_surface,
        size5_sat_search=size5_sat_search,
    )

    return {
        "problem_count": len(problems),
        "difficulty_counts": {
            difficulty: by_difficulty[difficulty] for difficulty in sorted(by_difficulty)
        },
        "answer_counts": {str(answer).lower(): by_answer[answer] for answer in sorted(by_answer)},
        "public_pair_duplicates": _public_pair_duplicates(problems),
        "public_graph_status_counts": {
            status: by_status[status] for status in sorted(by_status)
        },
        "graph_status_counts": graph_counts,
        "source_law_strength": _source_law_strength(catalog, graph),
        "theorem_backed_true_rules": theorem_backed_true_rules,
        "two_element_pair_evaluator": pair_evaluator,
        "two_element_source_row_semantics": _two_element_source_row_semantics(
            catalog=catalog,
            graph=graph,
            problems=problems,
            theories=two_element_theories,
            exact_source_ids=exact_source_ids,
        ),
        "two_element_fingerprint_collision_analysis": _two_element_fingerprint_collision_analysis(
            catalog=catalog,
            graph=graph,
            problems=problems,
            theories=two_element_theories,
            combined_decision_surface=combined_decision_surface,
        ),
        "kernel_bridge_analysis": kernel_bridge_analysis,
        "kernel_bridge_candidate_surface": kernel_bridge_candidate_surface,
        "kernel_micro_rewrite_analysis": kernel_micro_rewrite_analysis,
        "kernel_micro_rewrite_candidate_surface": _kernel_micro_rewrite_candidate_surface(
            kernel_bridge_candidate_surface=kernel_bridge_candidate_surface,
            kernel_micro_rewrite_analysis=kernel_micro_rewrite_analysis,
        ),
        "combined_decision_surface": combined_decision_surface,
        "residual_false_pair_canonicalization": residual_false_pair_canonicalization,
        "canonical_size5_unknown_followup": _canonical_size5_unknown_followup(
            catalog=catalog,
            size5_sat_search=size5_sat_search,
            residual_false_pair_canonicalization=residual_false_pair_canonicalization,
        ),
        "mapped_label_agreement": {
            "correct": mapped_correctly,
            "total": len(problems),
        },
        "pair_feature_signals": top_feature_signals,
        "candidate_feature_rules": _candidate_feature_rules(problem_feature_rows),
        "two_element_countermodel_cover": {
            "false_problem_count": len(false_problems),
            "covered_false_problem_count": two_element_covered,
            "entries": [asdict(entry) for entry in cover_entries],
        },
        "three_element_countermodel_search": three_element_countermodel_search,
        "size4_sat_search": size4_sat_search,
        "size5_sat_search": size5_sat_search,
        "sample_problems": [problem.to_dict() for problem in problems[:10]],
    }


def _coerce_problem_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [problem_id for problem_id in value if isinstance(problem_id, str)]
