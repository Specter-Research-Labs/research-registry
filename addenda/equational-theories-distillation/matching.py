from __future__ import annotations

from dataclasses import dataclass

from syntax import Binary, Equation, Term, Variable


@dataclass(frozen=True)
class SubstitutionMatch:
    swaps_equation_sides: bool
    assignments: dict[str, str]


def find_substitution_instance(source: Equation, target: Equation) -> SubstitutionMatch | None:
    direct = _match_equation(source.left, target.left, source.right, target.right)
    if direct is not None:
        return SubstitutionMatch(
            swaps_equation_sides=False,
            assignments={name: _render_term(term) for name, term in sorted(direct.items())},
        )

    swapped = _match_equation(source.left, target.right, source.right, target.left)
    if swapped is not None:
        return SubstitutionMatch(
            swaps_equation_sides=True,
            assignments={name: _render_term(term) for name, term in sorted(swapped.items())},
        )
    return None


def is_substitution_instance(source: Equation, target: Equation) -> bool:
    return find_substitution_instance(source, target) is not None


def find_contextual_instance(source: Equation, target: Equation) -> SubstitutionMatch | None:
    hole_pair = _extract_hole_pair(target.left, target.right)
    if hole_pair is None:
        return None
    direct = _match_equation(source.left, hole_pair[0], source.right, hole_pair[1])
    if direct is not None:
        return SubstitutionMatch(
            swaps_equation_sides=False,
            assignments={name: _render_term(term) for name, term in sorted(direct.items())},
        )

    swapped = _match_equation(source.left, hole_pair[1], source.right, hole_pair[0])
    if swapped is not None:
        return SubstitutionMatch(
            swaps_equation_sides=True,
            assignments={name: _render_term(term) for name, term in sorted(swapped.items())},
        )
    return None


def _match_equation(
    source_left: Term,
    target_left: Term,
    source_right: Term,
    target_right: Term,
) -> dict[str, Term] | None:
    assignments: dict[str, Term] = {}
    if not _match_term(source_left, target_left, assignments):
        return None
    if not _match_term(source_right, target_right, assignments):
        return None
    return assignments


def _match_term(source: Term, target: Term, assignments: dict[str, Term]) -> bool:
    if isinstance(source, Variable):
        existing = assignments.get(source.name)
        if existing is None:
            assignments[source.name] = target
            return True
        return existing == target
    if not isinstance(target, Binary):
        return False
    return _match_term(source.left, target.left, assignments) and _match_term(
        source.right,
        target.right,
        assignments,
    )


def _extract_hole_pair(left: Term, right: Term) -> tuple[Term, Term] | None:
    if left == right:
        return None
    if isinstance(left, Binary) and isinstance(right, Binary):
        if left.left == right.left:
            nested = _extract_hole_pair(left.right, right.right)
            return nested or (left.right, right.right)
        if left.right == right.right:
            nested = _extract_hole_pair(left.left, right.left)
            return nested or (left.left, right.left)
    return (left, right)


def _render_term(term: Term) -> str:
    if isinstance(term, Variable):
        return term.name
    return f"({_render_term(term.left)} ◇ {_render_term(term.right)})"
