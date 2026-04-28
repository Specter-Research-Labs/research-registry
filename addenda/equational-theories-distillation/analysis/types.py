from __future__ import annotations

from dataclasses import dataclass

THEORY_REPRESENTATIVE_OPERATIONS = {
    "and_or": "and",
    "constant": "constant_0",
    "left_and_not_right_right_implies_left": "left_and_not_right",
    "left_projection": "left_projection",
    "nand_nor": "nor",
    "not_left": "not_left",
    "not_left_and_right_left_implies_right": "not_left_and_right",
    "not_right": "not_right",
    "right_projection": "right_projection",
    "xor_xnor": "xor",
}


@dataclass(frozen=True)
class CountermodelCoverEntry:
    name: str
    bits: str
    covered_problem_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProblemPairGroup:
    equation1_id: int
    equation2_id: int
    problem_ids: tuple[str, ...]
