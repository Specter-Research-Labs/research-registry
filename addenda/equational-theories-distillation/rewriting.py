from __future__ import annotations

from collections import deque

from syntax import Binary, Equation, Term, Variable


def find_equation_rewrite_path(
    start: Equation,
    target: Equation,
    helper: Equation,
    max_steps: int,
) -> tuple[Equation, ...] | None:
    if start == target or _equations_equal_up_to_swap(start, target):
        return (start,)

    queue = deque([(start, 0)])
    parents: dict[Equation, Equation | None] = {start: None}

    while queue:
        equation, steps = queue.popleft()
        if steps >= max_steps:
            continue
        for rewritten in iter_equation_rewrites(equation, helper):
            if rewritten in parents:
                continue
            parents[rewritten] = equation
            if _equations_equal_up_to_swap(rewritten, target):
                return _reconstruct_path(rewritten, parents)
            queue.append((rewritten, steps + 1))
    return None


def iter_equation_rewrites(equation: Equation, helper: Equation) -> tuple[Equation, ...]:
    rewrites: set[Equation] = set()
    orientations = (
        (helper.left, helper.right),
        (helper.right, helper.left),
    )
    for pattern, replacement in orientations:
        for term in _iter_term_rewrites(equation.left, pattern, replacement):
            rewrites.add(Equation(left=term, right=equation.right))
        for term in _iter_term_rewrites(equation.right, pattern, replacement):
            rewrites.add(Equation(left=equation.left, right=term))
    rewrites.discard(equation)
    return tuple(sorted(rewrites, key=_equation_sort_key))


def _iter_term_rewrites(term: Term, pattern: Term, replacement: Term) -> tuple[Term, ...]:
    rewrites: list[Term] = []
    for path, subterm in _iter_term_positions(term):
        assignments: dict[str, Term] = {}
        if not _match_term(pattern, subterm, assignments):
            continue
        rewritten_subterm = _substitute_term(replacement, assignments)
        rewrites.append(_replace_subterm(term, path, rewritten_subterm))
    return tuple(rewrites)


def _iter_term_positions(term: Term) -> tuple[tuple[tuple[str, ...], Term], ...]:
    positions: list[tuple[tuple[str, ...], Term]] = []

    def visit(cursor: Term, path: tuple[str, ...]) -> None:
        positions.append((path, cursor))
        if isinstance(cursor, Binary):
            visit(cursor.left, path + ("L",))
            visit(cursor.right, path + ("R",))

    visit(term, ())
    return tuple(positions)


def _replace_subterm(term: Term, path: tuple[str, ...], replacement: Term) -> Term:
    if not path:
        return replacement
    if not isinstance(term, Binary):
        raise ValueError("rewrite path descends through a variable")
    head, *tail = path
    if head == "L":
        return Binary(
            left=_replace_subterm(term.left, tuple(tail), replacement),
            right=term.right,
        )
    if head == "R":
        return Binary(
            left=term.left,
            right=_replace_subterm(term.right, tuple(tail), replacement),
        )
    raise ValueError(f"invalid rewrite path segment: {head}")


def _match_term(pattern: Term, target: Term, assignments: dict[str, Term]) -> bool:
    if isinstance(pattern, Variable):
        existing = assignments.get(pattern.name)
        if existing is None:
            assignments[pattern.name] = target
            return True
        return existing == target
    if not isinstance(target, Binary):
        return False
    return _match_term(pattern.left, target.left, assignments) and _match_term(
        pattern.right,
        target.right,
        assignments,
    )


def _substitute_term(term: Term, assignments: dict[str, Term]) -> Term:
    if isinstance(term, Variable):
        return assignments.get(term.name, term)
    return Binary(
        left=_substitute_term(term.left, assignments),
        right=_substitute_term(term.right, assignments),
    )


def _reconstruct_path(
    end: Equation,
    parents: dict[Equation, Equation | None],
) -> tuple[Equation, ...]:
    path = [end]
    cursor = end
    while True:
        parent = parents[cursor]
        if parent is None:
            break
        path.append(parent)
        cursor = parent
    path.reverse()
    return tuple(path)


def _equations_equal_up_to_swap(left: Equation, right: Equation) -> bool:
    return (left.left, left.right) == (right.left, right.right) or (
        left.left,
        left.right,
    ) == (right.right, right.left)


def _equation_sort_key(equation: Equation) -> tuple[str, str]:
    return (_render_term(equation.left), _render_term(equation.right))


def _render_term(term: Term) -> str:
    if isinstance(term, Variable):
        return term.name
    return f"({_render_term(term.left)} ◇ {_render_term(term.right)})"
