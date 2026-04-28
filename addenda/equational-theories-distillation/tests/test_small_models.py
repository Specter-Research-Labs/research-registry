from small_models import (
    all_two_element_operations,
    equation_holds_universally,
    iter_operations,
)
from syntax import parse_equation


def _operation(name: str):
    for operation in all_two_element_operations():
        if operation.name == name:
            return operation
    raise AssertionError(f"unknown operation {name}")


def test_left_projection_satisfies_x_equals_x_times_y() -> None:
    equation = parse_equation("x = x * y")
    assert equation_holds_universally(equation, _operation("left_projection"))


def test_xor_refutes_x_equals_x_times_x() -> None:
    equation = parse_equation("x = x * x")
    assert not equation_holds_universally(equation, _operation("xor"))


def test_iter_operations_counts_three_element_tables() -> None:
    assert sum(1 for _ in iter_operations(3)) == 19683
