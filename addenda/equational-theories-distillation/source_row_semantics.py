from __future__ import annotations

from dataclasses import dataclass

from graph import TRUE_STATUSES, ImplicationGraph
from laws import LawCatalog
from small_models import (
    FiniteOperation,
    all_two_element_operations,
    equation_holds_universally,
)

THEORY_NAME_OVERRIDES: dict[tuple[str, ...], str] = {
    ("and", "or"): "and_or",
    ("constant_0", "constant_1"): "constant",
    ("left_and_not_right", "right_implies_left"): "left_and_not_right_right_implies_left",
    ("left_projection",): "left_projection",
    ("nand", "nor"): "nand_nor",
    ("not_left",): "not_left",
    ("left_implies_right", "not_left_and_right"): "not_left_and_right_left_implies_right",
    ("not_right",): "not_right",
    ("right_projection",): "right_projection",
    ("xnor", "xor"): "xor_xnor",
}


@dataclass(frozen=True)
class TwoElementTheory:
    name: str
    operation_names: tuple[str, ...]
    law_ids: frozenset[int]


def build_two_element_theories(catalog: LawCatalog) -> tuple[TwoElementTheory, ...]:
    theory_map: dict[frozenset[int], list[FiniteOperation]] = {}
    for operation in all_two_element_operations():
        law_ids = frozenset(
            law_id
            for law_id in range(1, len(catalog.equations) + 1)
            if equation_holds_universally(catalog.law_equation(law_id), operation)
        )
        theory_map.setdefault(law_ids, []).append(operation)

    theories: list[TwoElementTheory] = []
    for law_ids, operations in theory_map.items():
        operation_names = tuple(sorted(operation.name for operation in operations))
        theories.append(
            TwoElementTheory(
                name=_theory_name(operation_names),
                operation_names=operation_names,
                law_ids=law_ids,
            )
        )
    theories.sort(key=lambda theory: theory.name)
    return tuple(theories)


def fingerprint_for_source_law(
    source_law_id: int,
    theories: tuple[TwoElementTheory, ...],
) -> tuple[str, ...]:
    return tuple(theory.name for theory in theories if source_law_id in theory.law_ids)


def predicted_targets_for_source_law(
    source_law_id: int,
    theories: tuple[TwoElementTheory, ...],
    law_count: int,
) -> frozenset[int]:
    satisfying_law_sets = [theory.law_ids for theory in theories if source_law_id in theory.law_ids]
    if not satisfying_law_sets:
        return frozenset(range(1, law_count + 1))
    predicted = set(satisfying_law_sets[0])
    for law_ids in satisfying_law_sets[1:]:
        predicted &= law_ids
    return frozenset(predicted)


def actual_true_targets_for_source_law(
    source_law_id: int,
    graph: ImplicationGraph,
) -> frozenset[int]:
    row_size = graph.law_count
    start = (source_law_id - 1) * row_size
    row = graph.statuses[start : start + row_size]
    return frozenset(
        target_id
        for target_id, status in enumerate(row, start=1)
        if status in TRUE_STATUSES
    )


def source_row_is_exact_under_two_element_theories(
    source_law_id: int,
    theories: tuple[TwoElementTheory, ...],
    graph: ImplicationGraph,
) -> bool:
    return predicted_targets_for_source_law(
        source_law_id,
        theories,
        graph.law_count,
    ) == actual_true_targets_for_source_law(source_law_id, graph)


def _theory_name(operation_names: tuple[str, ...]) -> str:
    try:
        return THEORY_NAME_OVERRIDES[operation_names]
    except KeyError as error:
        joined = "__".join(operation_names)
        raise KeyError(f"missing theory name for operation class {joined}") from error
