from matching import (
    find_contextual_instance,
    find_substitution_instance,
)
from syntax import parse_equation


def test_find_substitution_instance_matches_direct_orientation() -> None:
    source = parse_equation("x * y = y * x")
    target = parse_equation("(z * z) * w = w * (z * z)")

    match = find_substitution_instance(source, target)

    assert match is not None
    assert not match.swaps_equation_sides
    assert match.assignments == {"x": "(z ◇ z)", "y": "w"}


def test_find_substitution_instance_matches_swapped_equation_sides() -> None:
    source = parse_equation("x = y * z")
    target = parse_equation("(x * x) * y = z")

    match = find_substitution_instance(source, target)

    assert match is not None
    assert match.swaps_equation_sides
    assert match.assignments == {"x": "z", "y": "(x ◇ x)", "z": "y"}


def test_find_substitution_instance_rejects_inconsistent_assignments() -> None:
    source = parse_equation("x = x * y")
    target = parse_equation("z = x * y")

    assert find_substitution_instance(source, target) is None


def test_find_contextual_instance_matches_one_hole_rewrite() -> None:
    source = parse_equation("x * y = y * x")
    target = parse_equation("z * (x * y) = z * (y * x)")

    match = find_contextual_instance(source, target)

    assert match is not None
    assert not match.swaps_equation_sides
    assert match.assignments == {"x": "x", "y": "y"}


def test_find_contextual_instance_rejects_multiple_differences() -> None:
    source = parse_equation("x * y = y * x")
    target = parse_equation("(z * (x * y)) * w = (u * (y * x)) * v")

    assert find_contextual_instance(source, target) is None
