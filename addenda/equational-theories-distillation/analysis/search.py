from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import cast

from analysis.types import (
    THEORY_REPRESENTATIVE_OPERATIONS,
    CountermodelCoverEntry,
    ProblemPairGroup,
)
from graph import TRUE_STATUSES, ImplicationGraph
from laws import LawCatalog
from matching import (
    find_contextual_instance,
    find_substitution_instance,
)
from public_benchmark import PublicProblem
from sat_countermodels import search_sat_countermodel
from small_models import (
    all_two_element_operations,
    equation_holds_universally,
    find_countermodels,
    find_two_element_countermodels,
)
from source_patterns import (
    has_internal_singleton_self_reference,
    has_mixed_self_reference_with_singleton,
    is_collapse_source_law,
)
from source_row_semantics import (
    TwoElementTheory,
    fingerprint_for_source_law,
    predicted_targets_for_source_law,
)
from syntax import (
    Variable,
    count_variable_occurrences,
    leftmost_variable_name,
)


def _public_pair_duplicates(problems: list[PublicProblem]) -> dict[str, object]:
    pair_counts = Counter(
        (problem.equation1_id, problem.equation2_id, problem.answer)
        for problem in problems
    )
    repeated = [count for count in pair_counts.values() if count > 1]
    return {
        "unique_pair_count": len(pair_counts),
        "duplicate_instance_count": len(problems) - len(pair_counts),
        "repeated_pair_type_count": len(repeated),
        "max_pair_multiplicity": max(pair_counts.values()),
    }


def _two_element_pair_evaluator(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
    theories: tuple[TwoElementTheory, ...],
    greedy_cover_problem_ids: set[str],
) -> dict[str, object]:
    operations_by_name = {
        operation.name: operation for operation in all_two_element_operations()
    }
    representatives = []
    representative_operations = []
    for theory in theories:
        operation_name = THEORY_REPRESENTATIVE_OPERATIONS[theory.name]
        operation = operations_by_name[operation_name]
        representatives.append(
            {
                "theory_name": theory.name,
                "operation_name": operation.name,
                "bits": operation.bits,
            }
        )
        representative_operations.append(operation)

    separated_problem_ids = []
    for problem in false_problems:
        source = catalog.law_equation(problem.equation1_id)
        target = catalog.law_equation(problem.equation2_id)
        if any(
            equation_holds_universally(source, operation)
            and not equation_holds_universally(target, operation)
            for operation in representative_operations
        ):
            separated_problem_ids.append(problem.problem_id)

    separated_ids = set(separated_problem_ids)
    additional_ids = sorted(separated_ids - greedy_cover_problem_ids)
    return {
        "representative_count": len(representatives),
        "representatives": representatives,
        "false_problem_count": len(false_problems),
        "false_separated_problem_count": len(separated_ids),
        "false_separated_problem_ids": sorted(separated_ids),
        "additional_over_greedy_cover_count": len(additional_ids),
        "additional_over_greedy_cover_problem_ids": additional_ids,
    }


def _two_element_source_row_semantics(
    catalog: LawCatalog,
    graph: ImplicationGraph,
    problems: list[PublicProblem],
    theories: tuple[TwoElementTheory, ...],
    exact_source_ids: set[int],
) -> dict[str, object]:
    source_fingerprints = {
        law_id: fingerprint_for_source_law(law_id, theories)
        for law_id in range(1, graph.law_count + 1)
    }
    exact_fingerprint_source_counts = Counter(
        source_fingerprints[law_id] for law_id in exact_source_ids
    )

    public_exact_problem_count = 0
    public_exact_true_count = 0
    public_exact_false_count = 0
    theorem_residual_true_ids: set[str] = set()
    theorem_residual_true_exact_count = 0
    public_exact_fingerprint_stats: dict[tuple[str, ...], dict[str, int]] = {}

    for problem in problems:
        source = catalog.law_equation(problem.equation1_id)
        target = catalog.law_equation(problem.equation2_id)
        theorem_backed = (
            is_collapse_source_law(source)
            or has_mixed_self_reference_with_singleton(source)
            or find_contextual_instance(source, target) is not None
        )
        if problem.answer and not theorem_backed:
            theorem_residual_true_ids.add(problem.problem_id)

        if problem.equation1_id not in exact_source_ids:
            continue
        fingerprint = source_fingerprints[problem.equation1_id]
        bucket = public_exact_fingerprint_stats.setdefault(
            fingerprint,
            {
                "problem_count": 0,
                "true_count": 0,
                "false_count": 0,
                "theorem_residual_true_count": 0,
            },
        )
        bucket["problem_count"] += 1
        bucket["true_count"] += int(problem.answer)
        bucket["false_count"] += int(not problem.answer)
        if problem.problem_id in theorem_residual_true_ids:
            bucket["theorem_residual_true_count"] += 1
        predicted_targets = predicted_targets_for_source_law(
            problem.equation1_id,
            theories,
            graph.law_count,
        )
        predicted_answer = problem.equation2_id in predicted_targets
        if predicted_answer != problem.answer:
            continue
        public_exact_problem_count += 1
        public_exact_true_count += int(problem.answer)
        public_exact_false_count += int(not problem.answer)
        if problem.problem_id in theorem_residual_true_ids:
            theorem_residual_true_exact_count += 1

    theory_rows = []
    for theory in theories:
        theory_rows.append(
            {
                "name": theory.name,
                "operation_names": list(theory.operation_names),
                "law_count": len(theory.law_ids),
            }
        )

    exact_source_examples = []
    for law_id in sorted(exact_source_ids)[:12]:
        exact_source_examples.append(
            {
                "law_id": law_id,
                "equation": catalog.law_text(law_id),
                "fingerprint": list(source_fingerprints[law_id]),
                "predicted_target_count": len(
                    predicted_targets_for_source_law(law_id, theories, graph.law_count)
                ),
                "actual_target_count": sum(
                    graph.truth(law_id, target_id) is True
                    for target_id in range(1, graph.law_count + 1)
                ),
            }
        )
    exact_fingerprint_buckets = [
        {
            "fingerprint": list(fingerprint),
            "source_law_count": exact_fingerprint_source_counts[fingerprint],
            **stats,
        }
        for fingerprint, stats in sorted(
            public_exact_fingerprint_stats.items(),
            key=lambda item: (
                item[1]["theorem_residual_true_count"],
                item[1]["problem_count"],
                item[1]["true_count"],
            ),
            reverse=True,
        )
    ]

    return {
        "theory_count": len(theories),
        "theories": theory_rows,
        "exact_source_row_count": len(exact_source_ids),
        "exact_source_row_rate": round(len(exact_source_ids) / graph.law_count, 4),
        "public_exact_problem_count": public_exact_problem_count,
        "public_exact_true_count": public_exact_true_count,
        "public_exact_false_count": public_exact_false_count,
        "theorem_residual_true_count": len(theorem_residual_true_ids),
        "theorem_residual_true_exact_count": theorem_residual_true_exact_count,
        "exact_source_law_ids": sorted(exact_source_ids),
        "exact_fingerprint_buckets": exact_fingerprint_buckets,
        "exact_source_examples": exact_source_examples,
    }


def _source_law_strength(
    catalog: LawCatalog,
    graph: ImplicationGraph,
) -> dict[str, object]:
    out_degree = _row_true_counts(graph)
    excludes_lhs_total = 0
    excludes_lhs_all_true = 0
    mixed_self_reference_total = 0
    mixed_self_reference_all_true = 0
    leftmost_is_lhs_total = 0
    leftmost_is_lhs_all_true = 0
    occurs_once_not_leftmost_total = 0
    occurs_once_not_leftmost_all_true = 0

    for law_id in range(1, graph.law_count + 1):
        equation = catalog.law_equation(law_id)
        if not isinstance(equation.left, Variable):
            continue
        lhs = equation.left.name
        occurrences = count_variable_occurrences(equation.right, lhs)
        is_all_true = out_degree[law_id - 1] == graph.law_count
        if occurrences == 0:
            excludes_lhs_total += 1
            excludes_lhs_all_true += int(is_all_true)
        if has_mixed_self_reference_with_singleton(equation):
            mixed_self_reference_total += 1
            mixed_self_reference_all_true += int(is_all_true)
        if leftmost_variable_name(equation.right) == lhs:
            leftmost_is_lhs_total += 1
            leftmost_is_lhs_all_true += int(is_all_true)
        if occurrences == 1 and leftmost_variable_name(equation.right) != lhs:
            occurs_once_not_leftmost_total += 1
            occurs_once_not_leftmost_all_true += int(is_all_true)

    top_sources = []
    top_indices = sorted(
        range(graph.law_count),
        key=lambda idx: out_degree[idx],
        reverse=True,
    )[:12]
    for law_index in top_indices:
        top_sources.append(
            {
                "law_id": law_index + 1,
                "out_degree": out_degree[law_index],
                "equation": catalog.law_text(law_index + 1),
            }
        )

    return {
        "lhs_var_rhs_excludes_lhs": {
            "law_count": excludes_lhs_total,
            "all_targets_count": excludes_lhs_all_true,
            "all_targets_rate": round(excludes_lhs_all_true / excludes_lhs_total, 4),
        },
        "lhs_var_rhs_mixed_self_reference_with_singleton": {
            "law_count": mixed_self_reference_total,
            "all_targets_count": mixed_self_reference_all_true,
            "all_targets_rate": round(
                mixed_self_reference_all_true / mixed_self_reference_total,
                4,
            ),
        },
        "lhs_var_rhs_leftmost_is_lhs": {
            "law_count": leftmost_is_lhs_total,
            "all_targets_count": leftmost_is_lhs_all_true,
            "all_targets_rate": round(leftmost_is_lhs_all_true / leftmost_is_lhs_total, 4),
        },
        "lhs_var_rhs_occurs_once_not_leftmost": {
            "law_count": occurs_once_not_leftmost_total,
            "all_targets_count": occurs_once_not_leftmost_all_true,
            "all_targets_rate": round(
                occurs_once_not_leftmost_all_true / occurs_once_not_leftmost_total,
                4,
            ),
        },
        "top_source_laws": top_sources,
    }


def _row_true_counts(graph: ImplicationGraph) -> list[int]:
    row_counts: list[int] = []
    row_size = graph.law_count
    for row_index in range(graph.law_count):
        start = row_index * row_size
        end = start + row_size
        row = graph.statuses[start:end]
        row_counts.append(sum(status in TRUE_STATUSES for status in row))
    return row_counts


def _group_problems_by_pair(problems: list[PublicProblem]) -> list[ProblemPairGroup]:
    grouped: dict[tuple[int, int], list[str]] = {}
    for problem in problems:
        grouped.setdefault((problem.equation1_id, problem.equation2_id), []).append(
            problem.problem_id
        )
    return [
        ProblemPairGroup(
            equation1_id=equation1_id,
            equation2_id=equation2_id,
            problem_ids=tuple(sorted(problem_ids)),
        )
        for (equation1_id, equation2_id), problem_ids in sorted(grouped.items())
    ]


def _top_feature_signals(
    catalog: LawCatalog,
    problems: list[PublicProblem],
) -> list[dict[str, object]]:
    feature_names = (
        "same_left_shape",
        "same_right_shape",
        "target_uses_more_variables",
        "source_uses_more_variables",
        "target_uses_more_operations",
        "source_uses_more_operations",
        "target_has_deeper_equation",
        "source_has_deeper_equation",
        "source_repeats_variables_more",
        "target_repeats_variables_more",
    )

    buckets = {name: {"count": 0, "true": 0} for name in feature_names}
    for problem in problems:
        signals = _problem_features(catalog, problem)
        translated = {
            "same_left_shape": signals["same_left_shape"],
            "same_right_shape": signals["same_right_shape"],
            "target_uses_more_variables": signals["target_more_vars"],
            "source_uses_more_variables": signals["source_more_vars"],
            "target_uses_more_operations": signals["target_more_ops"],
            "source_uses_more_operations": signals["source_more_ops"],
            "target_has_deeper_equation": signals["target_deeper"],
            "source_has_deeper_equation": signals["source_deeper"],
            "source_repeats_variables_more": signals["source_more_repetition"],
            "target_repeats_variables_more": signals["target_more_repetition"],
        }
        for name, enabled in translated.items():
            if not enabled:
                continue
            buckets[name]["count"] += 1
            buckets[name]["true"] += int(problem.answer)

    ranked = []
    for name, bucket in buckets.items():
        count = bucket["count"]
        if count == 0:
            continue
        true_rate = bucket["true"] / count
        ranked.append(
            {
                "feature": name,
                "count": count,
                "true_rate": round(true_rate, 4),
                "lift_from_balance": round(abs(true_rate - 0.5), 4),
            }
        )
    ranked.sort(key=lambda item: (item["lift_from_balance"], item["count"]), reverse=True)
    return ranked[:8]


def _problem_features(catalog: LawCatalog, problem: PublicProblem) -> dict[str, bool]:
    source = catalog.law_features(problem.equation1_id)
    target = catalog.law_features(problem.equation2_id)
    source_eq = catalog.law_equation(problem.equation1_id)
    target_eq = catalog.law_equation(problem.equation2_id)
    source_repetition = sum(source.variable_multiplicity) - source.distinct_variables
    target_repetition = sum(target.variable_multiplicity) - target.distinct_variables
    return {
        "collapse_source": is_collapse_source_law(source_eq),
        "mixed_self_reference_with_singleton": has_mixed_self_reference_with_singleton(source_eq),
        "internal_singleton_self_reference": has_internal_singleton_self_reference(source_eq),
        "leftmost_source": isinstance(source_eq.left, Variable)
        and leftmost_variable_name(source_eq.right) == source_eq.left.name,
        "substitution_instance": find_substitution_instance(source_eq, target_eq) is not None,
        "contextual_instance": find_contextual_instance(source_eq, target_eq) is not None,
        "same_left_shape": source.left_shape == target.left_shape,
        "same_right_shape": source.right_shape == target.right_shape,
        "source_more_vars": source.distinct_variables > target.distinct_variables,
        "target_more_vars": target.distinct_variables > source.distinct_variables,
        "source_more_ops": source.operation_count > target.operation_count,
        "target_more_ops": target.operation_count > source.operation_count,
        "source_deeper": source.depth > target.depth,
        "target_deeper": target.depth > source.depth,
        "source_more_repetition": source_repetition > target_repetition,
        "target_more_repetition": target_repetition > source_repetition,
        "source_left_var": isinstance(source_eq.left, Variable),
        "target_left_var": isinstance(target_eq.left, Variable),
        "source_two_vars": source.distinct_variables == 2,
        "source_three_vars": source.distinct_variables == 3,
        "source_four_vars": source.distinct_variables == 4,
        "target_two_vars": target.distinct_variables == 2,
        "target_three_vars": target.distinct_variables == 3,
        "target_four_vars": target.distinct_variables == 4,
        "same_operation_count": source.operation_count == target.operation_count,
    }


def _candidate_feature_rules(
    problem_feature_rows: list[tuple[PublicProblem, dict[str, bool]]],
) -> dict[str, object]:
    feature_names = tuple(
        name
        for name in sorted(problem_feature_rows[0][1])
        if name
        not in {
            "collapse_source",
            "mixed_self_reference_with_singleton",
            "internal_singleton_self_reference",
            "substitution_instance",
            "contextual_instance",
        }
    )
    candidates: list[dict[str, object]] = []
    for size in (1, 2, 3):
        for combo in combinations(feature_names, size):
            matched = [
                problem
                for problem, features in problem_feature_rows
                if (
                    not features["collapse_source"]
                    and not features["mixed_self_reference_with_singleton"]
                    and not features["internal_singleton_self_reference"]
                    and all(features[name] for name in combo)
                )
            ]
            if len(matched) < 15:
                continue
            true_count = sum(int(problem.answer) for problem in matched)
            true_rate = true_count / len(matched)
            if not (true_rate >= 0.94 or true_rate <= 0.06):
                continue
            candidates.append(
                {
                    "features": list(combo),
                    "count": len(matched),
                    "true_rate": round(true_rate, 4),
                    "sample_problem_ids": [problem.problem_id for problem in matched[:5]],
                }
            )
    candidates.sort(
        key=lambda item: (abs(item["true_rate"] - 0.5), item["count"]),
        reverse=True,
    )
    return {
        "non_collapse_true_rules": [
            item for item in candidates if cast(float, item["true_rate"]) > 0.5
        ][:8],
        "non_collapse_false_rules": [
            item for item in candidates if cast(float, item["true_rate"]) < 0.5
        ][:8],
    }


def _greedy_two_element_cover(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
) -> list[CountermodelCoverEntry]:
    coverage: dict[tuple[str, str], set[str]] = {}
    for problem in false_problems:
        witnesses = find_two_element_countermodels(
            catalog,
            source_law_id=problem.equation1_id,
            target_law_id=problem.equation2_id,
        )
        for witness in witnesses:
            coverage.setdefault((witness.name, witness.bits), set()).add(problem.problem_id)

    remaining = {problem.problem_id for problem in false_problems}
    chosen: list[CountermodelCoverEntry] = []
    while remaining:
        best_key = None
        best_cover: set[str] = set()
        for key, covered_ids in coverage.items():
            current_cover = covered_ids & remaining
            if len(current_cover) > len(best_cover):
                best_key = key
                best_cover = current_cover
        if best_key is None or not best_cover:
            break
        remaining -= best_cover
        chosen.append(
            CountermodelCoverEntry(
                name=best_key[0],
                bits=best_key[1],
                covered_problem_ids=tuple(sorted(best_cover)),
            )
        )
        del coverage[best_key]
        if len(chosen) >= 6:
            break
    return chosen


def _three_element_countermodel_search(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
    two_element_covered_ids: set[str],
) -> dict[str, object]:
    uncovered = [
        problem for problem in false_problems if problem.problem_id not in two_element_covered_ids
    ]
    residual_groups = _group_problems_by_pair(uncovered)
    witness_counts: Counter[str] = Counter()
    sample_witnesses: list[dict[str, object]] = []
    covered_problem_ids: list[str] = []
    covered_pair_count = 0
    for pair_group in residual_groups:
        witnesses = find_countermodels(
            catalog=catalog,
            source_law_id=pair_group.equation1_id,
            target_law_id=pair_group.equation2_id,
            size=3,
            limit=1,
        )
        if not witnesses:
            continue
        witness = witnesses[0]
        covered_pair_count += 1
        covered_problem_ids.extend(pair_group.problem_ids)
        witness_counts[witness.bits] += len(pair_group.problem_ids)
        if len(sample_witnesses) < 12:
            sample_witnesses.append(
                {
                    "problem_ids": list(pair_group.problem_ids),
                    "equation1_id": pair_group.equation1_id,
                    "equation2_id": pair_group.equation2_id,
                    "pair_multiplicity": len(pair_group.problem_ids),
                    "witness_bits": witness.bits,
                }
            )

    covered_count = len(covered_problem_ids)
    return {
        "uncovered_after_two_element_count": len(uncovered),
        "residual_unique_pair_count": len(residual_groups),
        "residual_unique_source_count": len({group.equation1_id for group in residual_groups}),
        "covered_count": covered_count,
        "covered_unique_pair_count": covered_pair_count,
        "covered_problem_ids": sorted(covered_problem_ids),
        "remaining_uncovered_count": len(uncovered) - covered_count,
        "top_witness_tables": [
            {"bits": bits, "count": count}
            for bits, count in witness_counts.most_common(10)
        ],
        "sample_witnesses": sample_witnesses,
    }


def _size4_sat_search(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
    two_element_covered_ids: set[str],
    three_element_covered_ids: list[str],
    timeout_ms: int,
) -> dict[str, object]:
    return _sat_residual_search(
        catalog=catalog,
        false_problems=false_problems,
        already_covered_ids=two_element_covered_ids | set(three_element_covered_ids),
        timeout_ms=timeout_ms,
        size=4,
        residual_label="residual_after_three_element_count",
    )


def _size5_sat_search(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
    two_element_covered_ids: set[str],
    three_element_covered_ids: list[str],
    size4_covered_ids: list[str],
    timeout_ms: int,
) -> dict[str, object]:
    return _sat_residual_search(
        catalog=catalog,
        false_problems=false_problems,
        already_covered_ids=(
            two_element_covered_ids | set(three_element_covered_ids) | set(size4_covered_ids)
        ),
        timeout_ms=timeout_ms,
        size=5,
        residual_label="residual_after_size4_count",
    )


def _sat_residual_search(
    catalog: LawCatalog,
    false_problems: list[PublicProblem],
    already_covered_ids: set[str],
    timeout_ms: int,
    size: int,
    residual_label: str,
) -> dict[str, object]:
    if timeout_ms <= 0:
        return {
            "enabled": False,
            "size": size,
            "timeout_ms": timeout_ms,
        }

    residual = [
        problem for problem in false_problems if problem.problem_id not in already_covered_ids
    ]
    residual_groups = _group_problems_by_pair(residual)
    sample_witnesses: list[dict[str, object]] = []
    covered_problem_ids: list[str] = []
    covered_pair_count = 0
    pair_status_counts: Counter[str] = Counter()
    pair_statuses: list[dict[str, object]] = []

    for pair_group in residual_groups:
        source = catalog.law_equation(pair_group.equation1_id)
        target = catalog.law_equation(pair_group.equation2_id)
        search = search_sat_countermodel(
            source=source,
            target=target,
            size=size,
            timeout_ms=timeout_ms,
        )
        pair_status_counts[search.status] += 1
        pair_statuses.append(
            {
                "problem_ids": list(pair_group.problem_ids),
                "equation1_id": pair_group.equation1_id,
                "equation2_id": pair_group.equation2_id,
                "status": search.status,
            }
        )
        witness = search.countermodel
        if witness is None:
            continue
        covered_pair_count += 1
        covered_problem_ids.extend(pair_group.problem_ids)
        if len(sample_witnesses) < 12:
            sample_witnesses.append(
                {
                    "problem_ids": list(pair_group.problem_ids),
                    "equation1_id": pair_group.equation1_id,
                    "equation2_id": pair_group.equation2_id,
                    "pair_multiplicity": len(pair_group.problem_ids),
                    "witness_bits": witness.bits,
                    "witness_assignment": witness.witness_assignment,
                }
            )

    return {
        "enabled": True,
        "size": size,
        "timeout_ms": timeout_ms,
        residual_label: len(residual),
        "residual_unique_pair_count": len(residual_groups),
        "residual_unique_source_count": len({group.equation1_id for group in residual_groups}),
        "covered_count": len(covered_problem_ids),
        "covered_unique_pair_count": covered_pair_count,
        "pair_status_counts": {
            status: pair_status_counts[status]
            for status in sorted(pair_status_counts)
        },
        "pair_statuses": pair_statuses,
        "covered_problem_ids": covered_problem_ids,
        "remaining_uncovered_count": len(residual) - len(covered_problem_ids),
        "sample_witnesses": sample_witnesses,
    }
