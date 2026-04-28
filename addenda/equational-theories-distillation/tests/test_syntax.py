from syntax import (
    count_variable_occurrences,
    extract_features,
    leftmost_variable_name,
    parse_equation,
)


def test_parse_equation_handles_parenthesized_and_flat_terms() -> None:
    equation = parse_equation("x * y = (z * x) * y")
    features = extract_features(equation)

    assert features.canonical == "(v0 ◇ v1) = ((v2 ◇ v0) ◇ v1)"
    assert features.shape == "(v ◇ v) = ((v ◇ v) ◇ v)"
    assert features.operation_count == 3
    assert features.distinct_variables == 3
    assert features.leaf_pattern == (0, 1, 2, 0, 1)


def test_parse_equation_rejects_trailing_tokens() -> None:
    try:
        parse_equation("x = y )")
    except ValueError as error:
        assert "unexpected trailing token" in str(error)
        return
    raise AssertionError("expected ValueError")


def test_leftmost_variable_and_occurrence_count() -> None:
    equation = parse_equation("x = (y * x) * z")

    assert leftmost_variable_name(equation.right) == "y"
    assert count_variable_occurrences(equation.right, "x") == 1
