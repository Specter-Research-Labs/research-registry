from dataclasses import dataclass
from itertools import product
from typing import Iterator

from laws import LawCatalog
from syntax import Binary, Equation, Term, Variable

BOOLEAN_OPERATION_NAMES = {
    "0000": "constant_0",
    "0001": "and",
    "0010": "left_and_not_right",
    "0011": "left_projection",
    "0100": "not_left_and_right",
    "0101": "right_projection",
    "0110": "xor",
    "0111": "or",
    "1000": "nor",
    "1001": "xnor",
    "1010": "not_right",
    "1011": "right_implies_left",
    "1100": "not_left",
    "1101": "left_implies_right",
    "1110": "nand",
    "1111": "constant_1",
}


@dataclass(frozen=True)
class FiniteOperation:
    size: int
    table: tuple[int, ...]
    name: str
    bits: str

    def apply(self, left: int, right: int) -> int:
        return self.table[left * self.size + right]


def all_two_element_operations() -> tuple[FiniteOperation, ...]:
    operations = []
    for mask in range(16):
        bits = f"{mask:04b}"
        table = tuple(int(bit) for bit in bits)
        operations.append(
            FiniteOperation(
                size=2,
                table=table,
                name=BOOLEAN_OPERATION_NAMES[bits],
                bits=bits,
            )
        )
    return tuple(operations)


def iter_operations(size: int) -> Iterator[FiniteOperation]:
    if size < 2:
        raise ValueError(f"operation size must be at least 2, got {size}")
    if size == 2:
        yield from all_two_element_operations()
        return
    for digits in product(range(size), repeat=size * size):
        bits = "".join(str(digit) for digit in digits)
        yield FiniteOperation(
            size=size,
            table=digits,
            name=f"size_{size}_{bits}",
            bits=bits,
        )


def equation_holds_universally(equation: Equation, operation: FiniteOperation) -> bool:
    variable_names = tuple(sorted(_variable_names(equation)))
    assignments = [{}]
    for name in variable_names:
        next_assignments = []
        for assignment in assignments:
            for value in range(operation.size):
                next_assignments.append({**assignment, name: value})
        assignments = next_assignments
    for assignment in assignments:
        if _evaluate(equation.left, assignment, operation) != _evaluate(
            equation.right,
            assignment,
            operation,
        ):
            return False
    return True


def find_two_element_countermodels(
    catalog: LawCatalog,
    source_law_id: int,
    target_law_id: int,
) -> list[FiniteOperation]:
    return find_countermodels(
        catalog=catalog,
        source_law_id=source_law_id,
        target_law_id=target_law_id,
        size=2,
    )


def find_countermodels(
    catalog: LawCatalog,
    source_law_id: int,
    target_law_id: int,
    size: int,
    limit: int | None = None,
) -> list[FiniteOperation]:
    source = catalog.law_equation(source_law_id)
    target = catalog.law_equation(target_law_id)
    witnesses: list[FiniteOperation] = []
    for operation in iter_operations(size):
        if equation_holds_universally(source, operation) and not equation_holds_universally(
            target,
            operation,
        ):
            witnesses.append(operation)
            if limit is not None and len(witnesses) >= limit:
                break
    return witnesses


def _evaluate(term: Term, assignment: dict[str, int], operation: FiniteOperation) -> int:
    if isinstance(term, Variable):
        return assignment[term.name]
    if isinstance(term, Binary):
        return operation.apply(
            _evaluate(term.left, assignment, operation),
            _evaluate(term.right, assignment, operation),
        )
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
