from sat_countermodels import (
    SAT_STATUS_SAT,
    SAT_STATUS_UNSAT,
    find_sat_countermodel,
    search_sat_countermodel,
)
from syntax import parse_equation


def test_find_sat_countermodel_finds_two_element_witness() -> None:
    source = parse_equation("x = x * y")
    target = parse_equation("x = y")

    witness = find_sat_countermodel(source, target, size=2, timeout_ms=1_000)

    assert witness is not None
    assert witness.size == 2
    assert len(witness.table) == 4


def test_search_sat_countermodel_reports_sat_status() -> None:
    source = parse_equation("x = x * y")
    target = parse_equation("x = y")

    result = search_sat_countermodel(source, target, size=2, timeout_ms=1_000)

    assert result.status == SAT_STATUS_SAT
    assert result.countermodel is not None


def test_find_sat_countermodel_returns_none_for_true_implication() -> None:
    source = parse_equation("x = y * z")
    target = parse_equation("x = w")

    witness = find_sat_countermodel(source, target, size=2, timeout_ms=1_000)

    assert witness is None


def test_search_sat_countermodel_reports_unsat_status() -> None:
    source = parse_equation("x = y * z")
    target = parse_equation("x = w")

    result = search_sat_countermodel(source, target, size=2, timeout_ms=1_000)

    assert result.status == SAT_STATUS_UNSAT
    assert result.countermodel is None
