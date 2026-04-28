from graph import ImplicationGraph
from source_row_semantics import (
    TwoElementTheory,
    fingerprint_for_source_law,
    predicted_targets_for_source_law,
    source_row_is_exact_under_two_element_theories,
)


def test_source_row_semantics_helpers_track_exact_rows() -> None:
    theories = (
        TwoElementTheory(
            name="left_projection",
            operation_names=("left_projection",),
            law_ids=frozenset({1, 2}),
        ),
        TwoElementTheory(
            name="right_projection",
            operation_names=("right_projection",),
            law_ids=frozenset({1, 3}),
        ),
    )
    graph = ImplicationGraph(
        law_count=3,
        statuses=bytes(
            [
                3, 2, 2,
                3, 2, 2,
                2, 2, 3,
            ]
        ),
        equivalence_classes=(),
    )

    assert fingerprint_for_source_law(1, theories) == (
        "left_projection",
        "right_projection",
    )
    assert predicted_targets_for_source_law(1, theories, graph.law_count) == frozenset({1})
    assert source_row_is_exact_under_two_element_theories(1, theories, graph)
    assert not source_row_is_exact_under_two_element_theories(2, theories, graph)
