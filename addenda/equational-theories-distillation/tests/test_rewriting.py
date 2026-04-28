from rewriting import find_equation_rewrite_path
from syntax import parse_equation


def test_find_equation_rewrite_path_handles_one_commutativity_step() -> None:
    helper = parse_equation("x * y = y * x")
    start = parse_equation("x * y = y * ((x * z) * z)")
    target = parse_equation("x * y = y * ((z * x) * z)")

    path = find_equation_rewrite_path(start=start, target=target, helper=helper, max_steps=1)

    assert path == (start, target)


def test_find_equation_rewrite_path_handles_two_commutativity_steps() -> None:
    helper = parse_equation("x * y = y * x")
    start = parse_equation("x * (y * x) = (y * z) * z")
    target = parse_equation("(x * y) * x = (y * z) * z")

    path = find_equation_rewrite_path(start=start, target=target, helper=helper, max_steps=2)

    assert path == (
        start,
        parse_equation("(y * x) * x = (y * z) * z"),
        target,
    )


def test_find_equation_rewrite_path_allows_unbound_variables_in_replacement() -> None:
    helper = parse_equation("x = y")
    start = parse_equation("x = x")
    target = parse_equation("x = y")

    path = find_equation_rewrite_path(start=start, target=target, helper=helper, max_steps=1)

    assert path == (start, target)
