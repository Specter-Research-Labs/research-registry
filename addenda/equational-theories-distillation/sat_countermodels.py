from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import z3

from syntax import Binary, Equation, Term, Variable

SAT_STATUS_SAT = "sat"
SAT_STATUS_UNSAT = "unsat"
SAT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class SatCountermodel:
    size: int
    table: tuple[int, ...]
    witness_assignment: dict[str, int]

    @property
    def bits(self) -> str:
        return "".join(str(value) for value in self.table)


@dataclass(frozen=True)
class SatCountermodelSearch:
    status: str
    countermodel: SatCountermodel | None


def find_sat_countermodel(
    source: Equation,
    target: Equation,
    size: int,
    timeout_ms: int,
) -> SatCountermodel | None:
    return search_sat_countermodel(
        source=source,
        target=target,
        size=size,
        timeout_ms=timeout_ms,
    ).countermodel


def search_sat_countermodel(
    source: Equation,
    target: Equation,
    size: int,
    timeout_ms: int,
) -> SatCountermodelSearch:
    if size < 2:
        raise ValueError(f"countermodel size must be at least 2, got {size}")
    if timeout_ms <= 0:
        raise ValueError(f"timeout_ms must be positive, got {timeout_ms}")

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    table = [z3.Int(f"op_{index}") for index in range(size * size)]
    for cell in table:
        solver.add(cell >= 0, cell < size)

    source_assignments = _all_assignments(source, size)
    for assignment in source_assignments:
        left = _evaluate_term(source.left, assignment, table, size)
        right = _evaluate_term(source.right, assignment, table, size)
        solver.add(left == right)

    target_assignments = _all_assignments(target, size)
    target_failures = []
    for assignment in target_assignments:
        left = _evaluate_term(target.left, assignment, table, size)
        right = _evaluate_term(target.right, assignment, table, size)
        target_failures.append(left != right)
    solver.add(z3.Or(target_failures))

    result = solver.check()
    if result == z3.unsat:
        return SatCountermodelSearch(status=SAT_STATUS_UNSAT, countermodel=None)
    if result == z3.unknown:
        return SatCountermodelSearch(status=SAT_STATUS_UNKNOWN, countermodel=None)

    model = solver.model()
    concrete_table = tuple(model.evaluate(cell).as_long() for cell in table)
    witness_assignment = _find_target_witness_assignment(target, concrete_table, size)
    return SatCountermodelSearch(
        status=SAT_STATUS_SAT,
        countermodel=SatCountermodel(
            size=size,
            table=concrete_table,
            witness_assignment=witness_assignment,
        ),
    )


def _evaluate_term(
    term: Term,
    assignment: dict[str, z3.IntNumRef],
    table: list[z3.ArithRef],
    size: int,
) -> z3.ArithRef:
    if isinstance(term, Variable):
        return assignment[term.name]
    if isinstance(term, Binary):
        left = _evaluate_term(term.left, assignment, table, size)
        right = _evaluate_term(term.right, assignment, table, size)
        return _apply_operation(left, right, table, size)
    raise TypeError(f"unsupported term: {term!r}")


def _apply_operation(
    left: z3.ArithRef,
    right: z3.ArithRef,
    table: list[z3.ArithRef],
    size: int,
) -> z3.ArithRef:
    result = table[-1]
    for left_value in range(size - 1, -1, -1):
        for right_value in range(size - 1, -1, -1):
            cell = table[left_value * size + right_value]
            result = z3.If(
                z3.And(left == left_value, right == right_value),
                cell,
                result,
            )
    return result


def _all_assignments(equation: Equation, size: int) -> list[dict[str, z3.IntNumRef]]:
    names = tuple(sorted(_variable_names(equation)))
    assignments = []
    for values in product(range(size), repeat=len(names)):
        assignments.append(
            {name: z3.IntVal(value) for name, value in zip(names, values, strict=True)}
        )
    return assignments


def _find_target_witness_assignment(
    target: Equation,
    table: tuple[int, ...],
    size: int,
) -> dict[str, int]:
    names = tuple(sorted(_variable_names(target)))
    for values in product(range(size), repeat=len(names)):
        assignment = {name: value for name, value in zip(names, values, strict=True)}
        left = _evaluate_concrete(target.left, assignment, table, size)
        right = _evaluate_concrete(target.right, assignment, table, size)
        if left != right:
            return assignment
    raise AssertionError("satisfying model should witness target failure")


def _evaluate_concrete(
    term: Term,
    assignment: dict[str, int],
    table: tuple[int, ...],
    size: int,
) -> int:
    if isinstance(term, Variable):
        return assignment[term.name]
    if isinstance(term, Binary):
        left = _evaluate_concrete(term.left, assignment, table, size)
        right = _evaluate_concrete(term.right, assignment, table, size)
        return table[left * size + right]
    raise TypeError(f"unsupported term: {term!r}")


def _variable_names(equation: Equation) -> set[str]:
    names: set[str] = set()
    _collect_names(equation.left, names)
    _collect_names(equation.right, names)
    return names


def _collect_names(term: Term, names: set[str]) -> None:
    if isinstance(term, Variable):
        names.add(term.name)
        return
    if isinstance(term, Binary):
        _collect_names(term.left, names)
        _collect_names(term.right, names)
        return
    raise TypeError(f"unsupported term: {term!r}")
