from __future__ import annotations

from collections import Counter
from typing import cast

from graph import ImplicationGraph
from laws import LawCatalog
from matching import (
    find_contextual_instance,
    find_substitution_instance,
)
from proof_catalog import ConstructiveProofCatalog
from public_benchmark import PublicProblem
from rewriting import find_equation_rewrite_path
from source_row_semantics import (
    TwoElementTheory,
    fingerprint_for_source_law,
    predicted_targets_for_source_law,
)
from syntax import Binary, Equation, Term, Variable


def _combined_decision_surface(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
    theorem_backed_true_rules: dict[str, object],
    theories: tuple[TwoElementTheory, ...],
    exact_source_ids: set[int],
    false_covered_ids: set[str],
) -> dict[str, object]:
    theorem_true_ids = set(
        cast(list[str], theorem_backed_true_rules["combined_true_problem_ids"])
    )
    exact_true_ids: set[str] = set()
    for problem in problems:
        if not problem.answer or problem.equation1_id not in exact_source_ids:
            continue
        predicted_targets = predicted_targets_for_source_law(
            problem.equation1_id,
            theories,
            graph.law_count,
        )
        if problem.equation2_id in predicted_targets:
            exact_true_ids.add(problem.problem_id)

    decided_problem_ids = theorem_true_ids | exact_true_ids | false_covered_ids
    remaining_true = [
        _problem_case_record(
            problem,
            fingerprint_for_source_law(problem.equation1_id, theories),
        )
        for problem in problems
        if problem.answer and problem.problem_id not in decided_problem_ids
    ]
    remaining_false = [
        _problem_case_record(
            problem,
            fingerprint_for_source_law(problem.equation1_id, theories),
        )
        for problem in problems
        if not problem.answer and problem.problem_id not in decided_problem_ids
    ]
    return {
        "decided_problem_count": len(decided_problem_ids),
        "decided_problem_rate": round(len(decided_problem_ids) / len(problems), 4),
        "remaining_problem_count": len(problems) - len(decided_problem_ids),
        "remaining_true_problem_count": len(remaining_true),
        "remaining_false_problem_count": len(remaining_false),
        "remaining_true_cases": remaining_true,
        "remaining_false_cases": remaining_false,
    }


def _kernel_bridge_candidate_surface(
    combined_decision_surface: dict[str, object],
    kernel_bridge_analysis: dict[str, object],
) -> dict[str, object]:
    decided_problem_count = cast(int, combined_decision_surface["decided_problem_count"]) + cast(
        int,
        kernel_bridge_analysis["covered_public_problem_count"],
    )
    remaining_true_problem_count = cast(
        int,
        combined_decision_surface["remaining_true_problem_count"],
    ) - cast(int, kernel_bridge_analysis["covered_public_problem_count"])
    remaining_false_problem_count = cast(
        int,
        combined_decision_surface["remaining_false_problem_count"],
    )
    total_problem_count = (
        cast(int, combined_decision_surface["decided_problem_count"])
        + cast(int, combined_decision_surface["remaining_problem_count"])
    )
    return {
        "decided_problem_count": decided_problem_count,
        "decided_problem_rate": round(decided_problem_count / total_problem_count, 4),
        "remaining_problem_count": total_problem_count - decided_problem_count,
        "remaining_true_problem_count": remaining_true_problem_count,
        "remaining_false_problem_count": remaining_false_problem_count,
    }


def _kernel_micro_rewrite_candidate_surface(
    kernel_bridge_candidate_surface: dict[str, object],
    kernel_micro_rewrite_analysis: dict[str, object],
) -> dict[str, object]:
    decided_problem_count = cast(
        int,
        kernel_bridge_candidate_surface["decided_problem_count"],
    ) + cast(int, kernel_micro_rewrite_analysis["covered_public_problem_count"])
    remaining_true_problem_count = cast(
        int,
        kernel_bridge_candidate_surface["remaining_true_problem_count"],
    ) - cast(int, kernel_micro_rewrite_analysis["covered_public_problem_count"])
    remaining_false_problem_count = cast(
        int,
        kernel_bridge_candidate_surface["remaining_false_problem_count"],
    )
    total_problem_count = (
        cast(int, kernel_bridge_candidate_surface["decided_problem_count"])
        + cast(int, kernel_bridge_candidate_surface["remaining_problem_count"])
    )
    return {
        "decided_problem_count": decided_problem_count,
        "decided_problem_rate": round(decided_problem_count / total_problem_count, 4),
        "remaining_problem_count": total_problem_count - decided_problem_count,
        "remaining_true_problem_count": remaining_true_problem_count,
        "remaining_false_problem_count": remaining_false_problem_count,
    }


def _law_sort_key(catalog: LawCatalog, law_id: int) -> tuple[int, int, int, int]:
    features = catalog.law_features(law_id)
    return (
        features.operation_count,
        features.depth,
        features.distinct_variables,
        law_id,
    )


def _canonical_equivalent_law_id(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    law_id: int,
) -> int:
    equivalent_ids = [
        candidate_id
        for candidate_id in range(1, graph.law_count + 1)
        if graph.truth(law_id, candidate_id) is True and graph.truth(candidate_id, law_id) is True
    ]
    if not equivalent_ids:
        return law_id
    return min(equivalent_ids, key=lambda candidate_id: _law_sort_key(catalog, candidate_id))


def _residual_false_pair_canonicalization(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    combined_decision_surface: dict[str, object],
    size5_sat_search: dict[str, object],
) -> dict[str, object]:
    remaining_false_cases = cast(
        list[dict[str, object]],
        combined_decision_surface["remaining_false_cases"],
    )
    pair_groups: dict[tuple[int, int], dict[str, object]] = {}
    for case in remaining_false_cases:
        key = (cast(int, case["equation1_id"]), cast(int, case["equation2_id"]))
        entry = pair_groups.setdefault(
            key,
            {
                "problem_ids": [],
                "source_fingerprint": case["source_fingerprint"],
            },
        )
        cast(list[str], entry["problem_ids"]).append(cast(str, case["problem_id"]))

    size5_status_by_pair = {
        (
            cast(int, entry["equation1_id"]),
            cast(int, entry["equation2_id"]),
        ): cast(str, entry["status"])
        for entry in cast(list[dict[str, object]], size5_sat_search.get("pair_statuses", []))
    }

    canonical_pairs = []
    source_changed_count = 0
    target_changed_count = 0
    for (source_id, target_id), entry in sorted(pair_groups.items()):
        canonical_source_id = _canonical_equivalent_law_id(catalog, graph, source_id)
        canonical_target_id = _canonical_equivalent_law_id(catalog, graph, target_id)
        source_changed = canonical_source_id != source_id
        target_changed = canonical_target_id != target_id
        source_changed_count += int(source_changed)
        target_changed_count += int(target_changed)
        canonical_pairs.append(
            {
                "equation1_id": source_id,
                "equation2_id": target_id,
                "source_equation": catalog.law_text(source_id),
                "target_equation": catalog.law_text(target_id),
                "canonical_equation1_id": canonical_source_id,
                "canonical_equation2_id": canonical_target_id,
                "canonical_source_equation": catalog.law_text(canonical_source_id),
                "canonical_target_equation": catalog.law_text(canonical_target_id),
                "source_changed": source_changed,
                "target_changed": target_changed,
                "problem_ids": sorted(cast(list[str], entry["problem_ids"])),
                "source_fingerprint": cast(list[str], entry["source_fingerprint"]),
                "size5_status": size5_status_by_pair.get((source_id, target_id)),
            }
        )

    return {
        "residual_unique_pair_count": len(canonical_pairs),
        "source_changed_pair_count": source_changed_count,
        "target_changed_pair_count": target_changed_count,
        "pairs": canonical_pairs,
    }


def _canonical_size5_unknown_followup(
    catalog: LawCatalog,
    size5_sat_search: dict[str, object],
    residual_false_pair_canonicalization: dict[str, object],
) -> dict[str, object]:
    if not bool(size5_sat_search.get("enabled")):
        return {
            "enabled": False,
        }

    timeout_ms = cast(int, size5_sat_search["timeout_ms"])
    if timeout_ms <= 0:
        return {
            "enabled": False,
        }

    from sat_countermodels import search_sat_countermodel

    followups = []
    status_counts: Counter[str] = Counter()
    for entry in cast(list[dict[str, object]], residual_false_pair_canonicalization["pairs"]):
        if entry["size5_status"] != "unknown":
            continue
        source = catalog.law_equation(cast(int, entry["canonical_equation1_id"]))
        target = catalog.law_equation(cast(int, entry["canonical_equation2_id"]))
        search = search_sat_countermodel(
            source=source,
            target=target,
            size=5,
            timeout_ms=timeout_ms,
        )
        status_counts[search.status] += 1
        followups.append(
            {
                "equation1_id": entry["equation1_id"],
                "equation2_id": entry["equation2_id"],
                "canonical_equation1_id": entry["canonical_equation1_id"],
                "canonical_equation2_id": entry["canonical_equation2_id"],
                "problem_ids": entry["problem_ids"],
                "original_status": entry["size5_status"],
                "canonical_status": search.status,
                "source_changed": entry["source_changed"],
                "target_changed": entry["target_changed"],
            }
        )

    return {
        "enabled": True,
        "timeout_ms": timeout_ms,
        "rechecked_pair_count": len(followups),
        "pair_status_counts": {
            status: status_counts[status] for status in sorted(status_counts)
        },
        "pairs": followups,
    }


def _two_element_fingerprint_collision_analysis(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
    theories: tuple[TwoElementTheory, ...],
    combined_decision_surface: dict[str, object],
) -> dict[str, object]:
    fingerprint_rows: dict[tuple[str, ...], dict[bytes, list[int]]] = {}
    for law_id in range(1, graph.law_count + 1):
        fingerprint = fingerprint_for_source_law(law_id, theories)
        row = graph.statuses[(law_id - 1) * graph.law_count : law_id * graph.law_count]
        row_buckets = fingerprint_rows.setdefault(fingerprint, {})
        row_buckets.setdefault(row, []).append(law_id)

    bucket_summaries = []
    for fingerprint, row_buckets in fingerprint_rows.items():
        bucket_summaries.append(
            {
                "fingerprint": list(fingerprint),
                "law_count": sum(len(law_ids) for law_ids in row_buckets.values()),
                "row_signature_count": len(row_buckets),
                "max_row_class_size": max(len(law_ids) for law_ids in row_buckets.values()),
            }
        )
    bucket_summaries.sort(
        key=lambda item: (
            cast(int, item["row_signature_count"]),
            cast(int, item["law_count"]),
        ),
        reverse=True,
    )

    residual_source_ids = {
        cast(int, case["equation1_id"])
        for case in cast(list[dict[str, object]], combined_decision_surface["remaining_true_cases"])
    }
    residual_sources = []
    for law_id in sorted(residual_source_ids):
        fingerprint = fingerprint_for_source_law(law_id, theories)
        summary = next(
            item
            for item in bucket_summaries
            if cast(list[str], item["fingerprint"]) == list(fingerprint)
        )
        residual_sources.append(
            {
                "law_id": law_id,
                "equation": catalog.law_text(law_id),
                "fingerprint": list(fingerprint),
                "fingerprint_law_count": summary["law_count"],
                "fingerprint_row_signature_count": summary["row_signature_count"],
            }
        )

    exact_bucket_count = sum(
        1 for item in bucket_summaries if cast(int, item["row_signature_count"]) == 1
    )
    return {
        "fingerprint_bucket_count": len(bucket_summaries),
        "single_row_bucket_count": exact_bucket_count,
        "divergent_bucket_count": len(bucket_summaries) - exact_bucket_count,
        "laws_in_single_row_buckets": sum(
            cast(int, item["law_count"])
            for item in bucket_summaries
            if cast(int, item["row_signature_count"]) == 1
        ),
        "laws_in_divergent_buckets": sum(
            cast(int, item["law_count"])
            for item in bucket_summaries
            if cast(int, item["row_signature_count"]) > 1
        ),
        "top_divergent_buckets": bucket_summaries[:12],
        "residual_true_source_fingerprints": residual_sources,
    }


def _problem_case_record(
    problem: PublicProblem,
    fingerprint: tuple[str, ...],
) -> dict[str, object]:
    return {
        "problem_id": problem.problem_id,
        "difficulty": problem.difficulty,
        "equation1_id": problem.equation1_id,
        "equation2_id": problem.equation2_id,
        "equation1": problem.equation1,
        "equation2": problem.equation2,
        "source_fingerprint": list(fingerprint),
    }


def _kernel_bridge_analysis(
    catalog: LawCatalog,
    combined_decision_surface: dict[str, object],
    proof_catalog: ConstructiveProofCatalog,
) -> dict[str, object]:
    remaining_true_cases = cast(
        list[dict[str, object]],
        combined_decision_surface["remaining_true_cases"],
    )
    pair_groups: dict[tuple[int, int], list[str]] = {}
    for case in remaining_true_cases:
        key = (cast(int, case["equation1_id"]), cast(int, case["equation2_id"]))
        pair_groups.setdefault(key, []).append(cast(str, case["problem_id"]))

    kernel_public_problem_counts: Counter[int] = Counter()
    kernel_pair_sets: dict[int, set[tuple[int, int]]] = {}
    kernel_match_modes: dict[int, set[str]] = {}
    source_rule_problem_counts: Counter[tuple[int, int]] = Counter()
    source_rule_pair_sets: dict[tuple[int, int], set[tuple[int, int]]] = {}
    source_rule_match_modes: dict[tuple[int, int], set[str]] = {}
    pair_bridges = []
    uncovered_pairs = []

    for (source_id, target_id), problem_ids in sorted(pair_groups.items()):
        target = catalog.law_equation(target_id)
        matches = []
        pair_key = (source_id, target_id)
        for rule in proof_catalog.direct_rules_for_source(source_id):
            kernel = catalog.law_equation(rule.kernel_id)
            modes: list[str] = []
            if find_substitution_instance(kernel, target) is not None:
                modes.append("substitution")
            if find_contextual_instance(kernel, target) is not None:
                modes.append("context")
            if not modes:
                continue
            kernel_public_problem_counts[rule.kernel_id] += len(problem_ids)
            kernel_pair_sets.setdefault(rule.kernel_id, set()).add(pair_key)
            kernel_match_modes.setdefault(rule.kernel_id, set()).update(modes)
            source_rule_problem_counts[(rule.source_id, rule.kernel_id)] += len(problem_ids)
            source_rule_pair_sets.setdefault(
                (rule.source_id, rule.kernel_id),
                set(),
            ).add(pair_key)
            source_rule_match_modes.setdefault(
                (rule.source_id, rule.kernel_id),
                set(),
            ).update(modes)
            feature = catalog.law_features(rule.kernel_id)
            matches.append(
                {
                    "source_rule": "exact_source_match",
                    "kernel_id": rule.kernel_id,
                    "equation": catalog.law_text(rule.kernel_id),
                    "operation_count": feature.operation_count,
                    "distinct_variables": feature.distinct_variables,
                    "match_modes": modes,
                }
            )
        if matches:
            pair_bridges.append(
                {
                    "equation1_id": source_id,
                    "equation2_id": target_id,
                    "problem_ids": list(problem_ids),
                    "source_equation": catalog.law_text(source_id),
                    "target_equation": catalog.law_text(target_id),
                    "kernels": matches[:8],
                }
            )
        else:
            uncovered_pairs.append(
                {
                    "equation1_id": source_id,
                    "equation2_id": target_id,
                    "problem_ids": list(problem_ids),
                    "source_equation": catalog.law_text(source_id),
                    "target_equation": catalog.law_text(target_id),
                }
            )

    top_kernels = []
    for kernel_id, public_problem_count in kernel_public_problem_counts.most_common(20):
        feature = catalog.law_features(kernel_id)
        top_kernels.append(
            {
                "kernel_id": kernel_id,
                "equation": catalog.law_text(kernel_id),
                "operation_count": feature.operation_count,
                "distinct_variables": feature.distinct_variables,
                "covered_public_problem_count": public_problem_count,
                "covered_unique_pair_count": len(kernel_pair_sets[kernel_id]),
                "match_modes": sorted(kernel_match_modes[kernel_id]),
            }
        )

    source_rules = []
    for rule in proof_catalog.direct_kernel_rules:
        feature = catalog.law_features(rule.kernel_id)
        rule_key = (rule.source_id, rule.kernel_id)
        source_rules.append(
            {
                "source_equation": rule.source_equation,
                "kernel_equation": rule.kernel_equation,
                "kernel_operation_count": feature.operation_count,
                "kernel_distinct_variables": feature.distinct_variables,
                "covered_public_problem_count": source_rule_problem_counts[rule_key],
                "covered_unique_pair_count": len(source_rule_pair_sets.get(rule_key, set())),
                "match_modes": sorted(source_rule_match_modes.get(rule_key, set())),
            }
        )

    return {
        "candidate_kernel_count": len(proof_catalog.direct_kernel_rules),
        "remaining_true_problem_count": len(remaining_true_cases),
        "remaining_true_unique_pair_count": len(pair_groups),
        "covered_public_problem_count": sum(len(item["problem_ids"]) for item in pair_bridges),
        "covered_unique_pair_count": len(pair_bridges),
        "source_rules": source_rules,
        "top_kernels": top_kernels,
        "pair_bridges": pair_bridges,
        "uncovered_pairs": uncovered_pairs,
    }


def _kernel_micro_rewrite_analysis(
    catalog: LawCatalog,
    kernel_bridge_analysis: dict[str, object],
    proof_catalog: ConstructiveProofCatalog,
) -> dict[str, object]:
    uncovered_pairs = cast(list[dict[str, object]], kernel_bridge_analysis["uncovered_pairs"])

    pair_rewrites = []
    covered_public_problem_count = 0
    helper_public_problem_counts: Counter[int] = Counter()
    helper_pair_sets: dict[int, set[tuple[int, int]]] = {}
    helper_match_counts: Counter[int] = Counter()
    helper_match_modes: dict[int, set[str]] = {}
    source_rule_problem_counts: Counter[tuple[int, int, int]] = Counter()
    source_rule_pair_sets: dict[tuple[int, int, int], set[tuple[int, int]]] = {}

    for pair in uncovered_pairs:
        source_id = cast(int, pair["equation1_id"])
        target_id = cast(int, pair["equation2_id"])
        target = catalog.law_equation(target_id)
        problem_ids = cast(list[str], pair["problem_ids"])
        matches = []
        pair_key = (source_id, target_id)
        for rule in proof_catalog.micro_rules_for_source(source_id):
            base = catalog.law_equation(rule.base_kernel_id)
            helper = catalog.law_equation(rule.helper_kernel_id)
            rewrite_path = find_equation_rewrite_path(
                start=base,
                target=target,
                helper=helper,
                max_steps=2,
            )
            if rewrite_path is None:
                continue
            base_features = catalog.law_features(rule.base_kernel_id)
            helper_features = catalog.law_features(rule.helper_kernel_id)
            match_modes = {"rewrite"}
            helper_public_problem_counts[rule.helper_kernel_id] += len(problem_ids)
            helper_match_counts[rule.helper_kernel_id] += 1
            helper_pair_sets.setdefault(rule.helper_kernel_id, set()).add(pair_key)
            helper_match_modes.setdefault(rule.helper_kernel_id, set()).update(match_modes)
            rule_key = (rule.source_id, rule.base_kernel_id, rule.helper_kernel_id)
            source_rule_problem_counts[rule_key] += len(problem_ids)
            source_rule_pair_sets.setdefault(rule_key, set()).add(pair_key)
            matches.append(
                {
                    "source_rule": "exact_source_match",
                    "base_kernel_id": rule.base_kernel_id,
                    "base_equation": catalog.law_text(rule.base_kernel_id),
                    "base_operation_count": base_features.operation_count,
                    "helper_kernel_id": rule.helper_kernel_id,
                    "helper_equation": catalog.law_text(rule.helper_kernel_id),
                    "helper_operation_count": helper_features.operation_count,
                    "rewrite_step_count": len(rewrite_path) - 1,
                    "rewrite_path": [_render_equation(equation) for equation in rewrite_path],
                    "match_modes": sorted(match_modes),
                }
            )
        if not matches:
            continue
        matches.sort(
            key=lambda item: (
                cast(int, item["base_operation_count"])
                + cast(int, item["helper_operation_count"]),
                cast(int, item["base_operation_count"]),
                cast(int, item["helper_operation_count"]),
                cast(int, item["base_kernel_id"]),
                cast(int, item["helper_kernel_id"]),
            )
        )
        covered_public_problem_count += len(problem_ids)
        pair_rewrites.append(
            {
                "equation1_id": source_id,
                "equation2_id": target_id,
                "problem_ids": problem_ids,
                "source_equation": cast(str, pair["source_equation"]),
                "target_equation": cast(str, pair["target_equation"]),
                "matches": matches[:8],
            }
        )

    top_helpers = []
    for helper_id, public_problem_count in helper_public_problem_counts.most_common(12):
        helper_features = catalog.law_features(helper_id)
        top_helpers.append(
            {
                "helper_kernel_id": helper_id,
                "equation": catalog.law_text(helper_id),
                "operation_count": helper_features.operation_count,
                "distinct_variables": helper_features.distinct_variables,
                "covered_public_problem_count": public_problem_count,
                "covered_unique_pair_count": len(helper_pair_sets[helper_id]),
                "covered_match_count": helper_match_counts[helper_id],
                "match_modes": sorted(helper_match_modes[helper_id]),
            }
        )

    source_rules = []
    for rule in proof_catalog.micro_rewrite_rules:
        rule_key = (rule.source_id, rule.base_kernel_id, rule.helper_kernel_id)
        source_rules.append(
            {
                "source_equation": rule.source_equation,
                "base_equation": rule.base_equation,
                "helper_equation": rule.helper_equation,
                "covered_public_problem_count": source_rule_problem_counts[rule_key],
                "covered_unique_pair_count": len(source_rule_pair_sets.get(rule_key, set())),
            }
        )

    return {
        "candidate_base_kernel_count": len(proof_catalog.micro_rewrite_rules),
        "candidate_helper_kernel_count": len(
            {rule.helper_kernel_id for rule in proof_catalog.micro_rewrite_rules}
        ),
        "remaining_true_problem_count": cast(
            int,
            kernel_bridge_analysis["remaining_true_problem_count"],
        )
        - cast(int, kernel_bridge_analysis["covered_public_problem_count"]),
        "remaining_true_unique_pair_count": len(uncovered_pairs),
        "covered_public_problem_count": covered_public_problem_count,
        "covered_unique_pair_count": len(pair_rewrites),
        "source_rules": source_rules,
        "top_helpers": top_helpers,
        "pair_rewrites": pair_rewrites,
        "uncovered_pairs": [
            pair
            for pair in uncovered_pairs
            if (pair["equation1_id"], pair["equation2_id"])
            not in {
                (item["equation1_id"], item["equation2_id"]) for item in pair_rewrites
            }
        ],
    }


def _render_equation(equation: Equation) -> str:
    return f"{_render_term(equation.left)} = {_render_term(equation.right)}"


def _render_term(term: Term) -> str:
    if isinstance(term, Variable):
        return term.name
    if isinstance(term, Binary):
        return f"({_render_term(term.left)} ◇ {_render_term(term.right)})"
    raise TypeError(f"unsupported term: {term!r}")
