from source_patterns import (
    has_internal_singleton_self_reference,
    has_mixed_self_reference_with_singleton,
    is_collapse_source_law,
    occurrence_paths,
    variable_counts,
)
from syntax import parse_equation


def test_is_collapse_source_law_matches_lhs_variable_absence() -> None:
    assert is_collapse_source_law(parse_equation("x = y * z"))
    assert not is_collapse_source_law(parse_equation("x = y * (x * z)"))


def test_has_internal_singleton_self_reference_matches_mixed_path_with_singleton_other() -> None:
    equation = parse_equation("x = (y * x) * z")

    assert has_internal_singleton_self_reference(equation)


def test_has_internal_singleton_self_reference_rejects_spine_occurrence() -> None:
    assert not has_internal_singleton_self_reference(parse_equation("x = x * y"))
    assert not has_internal_singleton_self_reference(parse_equation("x = y * (z * x)"))


def test_has_internal_singleton_self_reference_rejects_no_singleton_other() -> None:
    assert not has_internal_singleton_self_reference(parse_equation("x = (y * x) * y"))


def test_has_mixed_self_reference_with_singleton_accepts_broader_family() -> None:
    equation = parse_equation("x = y * (x * (x * z))")

    assert has_mixed_self_reference_with_singleton(equation)
    assert not has_internal_singleton_self_reference(equation)


def test_has_mixed_self_reference_with_singleton_rejects_lr_rl_cross_pattern() -> None:
    equation = parse_equation("x = (y * x) * (x * z)")

    assert not has_mixed_self_reference_with_singleton(equation)


def test_occurrence_paths_and_variable_counts_are_stable() -> None:
    equation = parse_equation("x = y * ((x * z) * y)")

    assert occurrence_paths(equation.right, "x") == ("RLL",)
    assert variable_counts(equation.right) == {"x": 1, "y": 2, "z": 1}
