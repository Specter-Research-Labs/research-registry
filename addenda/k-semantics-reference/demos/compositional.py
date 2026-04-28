from __future__ import annotations

import random
from itertools import permutations, product
from typing import Any

from core import (
    PairedTrial,
    PolicySpec,
    ProblemSpace,
    compare_composite_k,
    compose_problem_spaces,
    paper_k_from_paired_trials,
)


def _sorting_agent_cost(values: tuple[int, ...]) -> int:
    updated = list(values)
    swaps = 0
    while True:
        moved = False
        for index in range(len(updated) - 1):
            if updated[index] > updated[index + 1]:
                updated[index], updated[index + 1] = updated[index + 1], updated[index]
                swaps += 1
                moved = True
                break
        if not moved:
            return swaps


def _sorting_blind_cost(values: tuple[int, ...], *, rng: random.Random, H: int) -> tuple[bool, int]:
    updated = list(values)
    for step in range(1, H + 1):
        if all(updated[index] <= updated[index + 1] for index in range(len(updated) - 1)):
            return True, step - 1
        swap_index = rng.randrange(len(updated) - 1)
        updated[swap_index], updated[swap_index + 1] = updated[swap_index + 1], updated[swap_index]
    solved = all(updated[index] <= updated[index + 1] for index in range(len(updated) - 1))
    return solved, H


def _bitstring_agent_cost(values: tuple[int, ...]) -> int:
    return sum(values)


def _bitstring_blind_cost(values: tuple[int, ...], *, rng: random.Random, H: int) -> tuple[bool, int]:
    updated = list(values)
    for step in range(1, H + 1):
        if all(bit == 0 for bit in updated):
            return True, step - 1
        index = rng.randrange(len(updated))
        updated[index] = 1 - updated[index]
    solved = all(bit == 0 for bit in updated)
    return solved, H


def run_compositional_demo(
    *,
    n_sort: int = 6,
    n_bits: int = 8,
    trials: int,
    H_sort: int = 200,
    H_bits: int = 100,
    seed: int,
) -> dict[str, Any]:
    if n_sort < 2:
        raise ValueError("n_sort must be >= 2")
    if n_bits < 1:
        raise ValueError("n_bits must be >= 1")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H_sort < 1 or H_bits < 1:
        raise ValueError("H_sort and H_bits must be >= 1")

    rng = random.Random(seed)
    sorted_state = tuple(range(n_sort))
    sort_initial_states = tuple(state for state in permutations(range(n_sort)) if state != sorted_state)
    zero_bits = (0,) * n_bits
    bit_initial_states = tuple(state for state in product((0, 1), repeat=n_bits) if state != zero_bits)

    sort_pairs: list[PairedTrial] = []
    bits_pairs: list[PairedTrial] = []
    composite_pairs: list[PairedTrial] = []

    for _ in range(trials):
        sort_state = sort_initial_states[rng.randrange(len(sort_initial_states))]
        bit_state = bit_initial_states[rng.randrange(len(bit_initial_states))]

        sort_agent_cost = _sorting_agent_cost(sort_state)
        sort_blind_solved, sort_blind_cost = _sorting_blind_cost(sort_state, rng=rng, H=H_sort)
        sort_pairs.append(
            PairedTrial(
                agent_cost=float(sort_agent_cost),
                agent_solved=True,
                blind_cost=float(sort_blind_cost),
                blind_solved=sort_blind_solved,
                blind_observed_cost=float(sort_blind_cost),
            )
        )

        bit_agent_cost = _bitstring_agent_cost(bit_state)
        bit_blind_solved, bit_blind_cost = _bitstring_blind_cost(bit_state, rng=rng, H=H_bits)
        bits_pairs.append(
            PairedTrial(
                agent_cost=float(bit_agent_cost),
                agent_solved=True,
                blind_cost=float(bit_blind_cost),
                blind_solved=bit_blind_solved,
                blind_observed_cost=float(bit_blind_cost),
            )
        )

        composite_pairs.append(
            PairedTrial(
                agent_cost=float(sort_agent_cost) * float(bit_agent_cost),
                agent_solved=True,
                blind_cost=float(sort_blind_cost) * float(bit_blind_cost),
                blind_solved=True,
                blind_observed_cost=float(sort_blind_cost) * float(bit_blind_cost),
            )
        )

    sort_problem_space = ProblemSpace(
        S=f"all permutations of {n_sort} items",
        operators=("adjacent_swap(i,i+1)",),
        C=("index bounds: 0 <= i < n-1",),
        E="distance to sorted order (ascending)",
        H=float(H_sort),
        H_unit="swap",
        S_init="uniform random non-goal permutation",
        S_goal="sorted permutation",
    )
    bits_problem_space = ProblemSpace(
        S=f"binary strings of length {n_bits}",
        operators=("flip_bit(i)",),
        C=(f"index bounds: 0 <= i < {n_bits}",),
        E="Hamming distance to all-zero target",
        H=float(H_bits),
        H_unit="bit_flip",
        S_init="uniform random non-goal bitstring",
        S_goal="all-zero bitstring",
    )
    composite_problem_space = compose_problem_spaces(
        sort_problem_space,
        bits_problem_space,
        name="Cartesian product: sorting_state x bitstring_state",
    )

    sort_result = paper_k_from_paired_trials(
        sort_pairs,
        problem_space=sort_problem_space,
        agent_policy_spec=PolicySpec(name="leftmost_inversion_swap", operator_semantics="adjacent_swap"),
        blind_policy_spec=PolicySpec(name="blind_uniform_adjacent_swaps", operator_semantics="adjacent_swap"),
    )
    sort_result["domain"] = {
        "state_space_size": len(sort_initial_states) + 1,
        "exact_supported": n_sort <= 6 and H_sort <= 400,
    }
    bits_result = paper_k_from_paired_trials(
        bits_pairs,
        problem_space=bits_problem_space,
        agent_policy_spec=PolicySpec(name="greedy_hamming_repair", operator_semantics="single-bit-flip"),
        blind_policy_spec=PolicySpec(name="blind_uniform_bit_flip", operator_semantics="single-bit-flip"),
    )
    bits_result["domain"] = {
        "state_space_size": len(bit_initial_states) + 1,
        "exact_supported": n_bits <= 8 and H_bits <= 400,
    }
    composite_result = paper_k_from_paired_trials(
        composite_pairs,
        problem_space=composite_problem_space,
        agent_policy_spec=PolicySpec(name="sorting_stage * bitstring_stage", operator_semantics="product_of_stage_operators"),
        blind_policy_spec=PolicySpec(name="blind_swaps * blind_flips", operator_semantics="product_of_stage_operators"),
    )

    return {
        "schema_version": 2,
        "stages": {"sorting": sort_result, "bitstring": bits_result},
        "composite": composite_result,
        "additivity": compare_composite_k(
            sort_result,
            bits_result,
            composite_result=composite_result,
        ),
        "notes": [
            "Composite costs are multiplicative so that log-ratio K composes additively.",
            "compose_problem_spaces() and compare_composite_k() are the reusable core surfaces.",
        ],
    }
