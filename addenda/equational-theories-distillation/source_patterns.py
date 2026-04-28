from __future__ import annotations

from syntax import (
    Equation,
    Term,
    Variable,
    count_variable_occurrences,
)


def is_collapse_source_law(equation: Equation) -> bool:
    if not isinstance(equation.left, Variable):
        return False
    return count_variable_occurrences(equation.right, equation.left.name) == 0


def has_internal_singleton_self_reference(equation: Equation) -> bool:
    if not isinstance(equation.left, Variable):
        return False
    if not has_mixed_self_reference_with_singleton(equation):
        return False
    lhs_name = equation.left.name
    return count_variable_occurrences(equation.right, lhs_name) == 1


def has_mixed_self_reference_with_singleton(equation: Equation) -> bool:
    if not isinstance(equation.left, Variable):
        return False
    lhs_name = equation.left.name
    paths = occurrence_paths(equation.right, lhs_name)
    if not paths:
        return False
    if any(not _is_mixed_path(path) for path in paths):
        return False
    if "LR" in paths and "RL" in paths:
        return False
    counts = variable_counts(equation.right)
    return any(count == 1 for name, count in counts.items() if name != lhs_name)


def occurrence_paths(term: Term, name: str, prefix: str = "") -> tuple[str, ...]:
    if isinstance(term, Variable):
        return (prefix,) if term.name == name else ()
    return occurrence_paths(term.left, name, prefix + "L") + occurrence_paths(
        term.right,
        name,
        prefix + "R",
    )


def variable_counts(term: Term) -> dict[str, int]:
    counts: dict[str, int] = {}
    _accumulate_variable_counts(term, counts)
    return counts


def _is_mixed_path(path: str) -> bool:
    return "L" in path and "R" in path


def _accumulate_variable_counts(term: Term, counts: dict[str, int]) -> None:
    if isinstance(term, Variable):
        counts[term.name] = counts.get(term.name, 0) + 1
        return
    _accumulate_variable_counts(term.left, counts)
    _accumulate_variable_counts(term.right, counts)
