from __future__ import annotations

import math
from itertools import permutations

from core import (
    ExecutablePolicy,
    PolicySpec,
    ProblemExecutor,
    ProblemSpace,
    compare_policies_in_problem_space,
)
from demos.common import sample_weighted

State = tuple[int, ...]
Operator = int


def _is_sorted(values: State) -> bool:
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def _swap_adjacent(values: State, index: int) -> State:
    updated = list(values)
    updated[index], updated[index + 1] = updated[index + 1], updated[index]
    return tuple(updated)


def run_sorting_demo(
    *,
    n: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if n < 2:
        raise ValueError("n must be >= 2")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    sorted_state = tuple(range(n))
    non_goal_states = tuple(state for state in permutations(range(n)) if state != sorted_state)

    def sample_initial_state(rng) -> State:
        return non_goal_states[rng.randrange(len(non_goal_states))]

    def initial_state_distribution() -> dict[State, float]:
        probability = 1.0 / len(non_goal_states)
        return {state: probability for state in non_goal_states}

    def applicable_operators(state: State) -> tuple[Operator, ...]:
        return tuple(range(n - 1))

    def apply_operator(state: State, operator: Operator, rng) -> State:
        del rng
        return _swap_adjacent(state, operator)

    def greedy_swap_distribution(state: State) -> dict[Operator, float]:
        for index in range(n - 1):
            if state[index] > state[index + 1]:
                return {index: 1.0}
        return {}

    def parity_biased_distribution(state: State) -> dict[Operator, float]:
        return {index: (2.0 if index % 2 == 0 else 1.0) for index in range(n - 1)}

    problem_space = ProblemSpace(
        S=f"all permutations of {n} items",
        operators=("adjacent_swap(i,i+1)",),
        C=("index bounds: 0 <= i < n-1",),
        E="distance to sorted order (ascending)",
        H=float(H),
        H_unit="swap",
        S_init="uniform random permutation",
        S_goal="sorted permutation",
        executor=ProblemExecutor(
            initial_state_sampler=sample_initial_state,
            initial_state_distribution=initial_state_distribution,
            is_goal=_is_sorted,
            applicable_operators=applicable_operators,
            apply_operator=apply_operator,
            enumerate_states=lambda: tuple(non_goal_states) + (sorted_state,),
            evaluate=lambda state: -sum(int(state[index] > state[index + 1]) for index in range(n - 1)),
            state_serializer=list,
            operator_serializer=lambda operator: f"adjacent_swap({operator},{operator + 1})",
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="leftmost_inversion_swap",
            operator_semantics="adjacent_swap",
            description="Deterministic adjacent-swap sorter with inversion-count cost.",
        ),
        choose_operator=lambda problem_space, state, rng: next(
            index for index in range(n - 1) if state[index] > state[index + 1]
        ),
        operator_distribution=lambda problem_space, state: greedy_swap_distribution(state),
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_uniform_adjacent_swaps",
            operator_semantics="adjacent_swap",
        ),
        choose_operator=lambda problem_space, state, rng: rng.randrange(n - 1),
        operator_distribution=lambda problem_space, state: {
            index: 1.0 / (n - 1) for index in range(n - 1)
        },
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_parity_biased_adjacent_swaps",
            operator_semantics="adjacent_swap",
            description="Goal-agnostic null that over-samples even-index swaps.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            parity_biased_distribution(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: parity_biased_distribution(state),
    )

    exact_supported = n <= 6 and H <= 400
    result = compare_policies_in_problem_space(
        problem_space,
        agent_policy,
        blind_policy,
        trials=trials,
        seed=seed,
        blind_policy_family={biased_blind.spec.name: biased_blind},
        bootstrap_samples=400,
        exact=exact_supported,
    )
    result["domain"] = {
        "state_space_size": math.factorial(n),
        "exact_supported": exact_supported,
    }
    if not exact_supported:
        result["exact"] = {
            "unsupported": "sorting exact finite-horizon enumeration is only enabled for n <= 6 and H <= 400",
        }
    return result
