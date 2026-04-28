from __future__ import annotations

from laws import LawCatalog
from matching import (
    find_contextual_instance,
    find_substitution_instance,
)
from public_benchmark import PublicProblem
from source_patterns import (
    has_mixed_self_reference_with_singleton,
    is_collapse_source_law,
)


def _theorem_backed_true_rules(
    catalog: LawCatalog,
    problems: list[PublicProblem],
) -> dict[str, object]:
    true_problem_ids = {problem.problem_id for problem in problems if problem.answer}
    collapse_true_ids: set[str] = set()
    collapse_false_ids: set[str] = set()
    mixed_self_reference_true_ids: set[str] = set()
    mixed_self_reference_false_ids: set[str] = set()
    substitution_true_ids: set[str] = set()
    substitution_false_ids: set[str] = set()
    substitution_examples: list[dict[str, object]] = []
    contextual_true_ids: set[str] = set()
    contextual_false_ids: set[str] = set()
    contextual_examples: list[dict[str, object]] = []

    for problem in problems:
        source = catalog.law_equation(problem.equation1_id)
        target = catalog.law_equation(problem.equation2_id)
        if is_collapse_source_law(source):
            if problem.answer:
                collapse_true_ids.add(problem.problem_id)
            else:
                collapse_false_ids.add(problem.problem_id)

        if has_mixed_self_reference_with_singleton(source):
            if problem.answer:
                mixed_self_reference_true_ids.add(problem.problem_id)
            else:
                mixed_self_reference_false_ids.add(problem.problem_id)

        match = find_substitution_instance(source, target)
        if match is not None:
            if problem.answer:
                substitution_true_ids.add(problem.problem_id)
                if len(substitution_examples) < 6:
                    substitution_examples.append(
                        {
                            "problem_id": problem.problem_id,
                            "equation1_id": problem.equation1_id,
                            "equation2_id": problem.equation2_id,
                            "swaps_equation_sides": match.swaps_equation_sides,
                            "assignments": match.assignments,
                        }
                    )
            else:
                substitution_false_ids.add(problem.problem_id)

        contextual_match = find_contextual_instance(source, target)
        if contextual_match is not None:
            if problem.answer:
                contextual_true_ids.add(problem.problem_id)
                if len(contextual_examples) < 6:
                    contextual_examples.append(
                        {
                            "problem_id": problem.problem_id,
                            "equation1_id": problem.equation1_id,
                            "equation2_id": problem.equation2_id,
                            "swaps_equation_sides": contextual_match.swaps_equation_sides,
                            "assignments": contextual_match.assignments,
                        }
                    )
            else:
                contextual_false_ids.add(problem.problem_id)

    combined_true_ids = (
        collapse_true_ids | mixed_self_reference_true_ids | contextual_true_ids
    )
    remaining_true_ids = true_problem_ids - combined_true_ids
    return {
        "public_true_problem_count": len(true_problem_ids),
        "collapse_source_rule": {
            "public_true_count": len(collapse_true_ids),
            "public_false_count": len(collapse_false_ids),
            "public_true_rate": round(len(collapse_true_ids) / len(true_problem_ids), 4),
        },
        "mixed_self_reference_singleton_rule": {
            "public_true_count": len(mixed_self_reference_true_ids),
            "public_false_count": len(mixed_self_reference_false_ids),
            "public_true_rate": round(
                len(mixed_self_reference_true_ids) / len(true_problem_ids),
                4,
            ),
        },
        "substitution_instance_rule": {
            "public_true_count": len(substitution_true_ids),
            "public_false_count": len(substitution_false_ids),
            "public_true_rate": round(len(substitution_true_ids) / len(true_problem_ids), 4),
            "examples": substitution_examples,
        },
        "one_hole_context_rule": {
            "public_true_count": len(contextual_true_ids),
            "public_false_count": len(contextual_false_ids),
            "public_true_rate": round(len(contextual_true_ids) / len(true_problem_ids), 4),
            "examples": contextual_examples,
        },
        "combined_true_rule_cover": {
            "public_true_count": len(combined_true_ids),
            "public_true_rate": round(len(combined_true_ids) / len(true_problem_ids), 4),
            "remaining_true_problem_count": len(remaining_true_ids),
        },
        "combined_true_problem_ids": sorted(combined_true_ids),
        "remaining_true_problem_ids": sorted(remaining_true_ids),
    }
