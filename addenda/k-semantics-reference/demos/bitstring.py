from __future__ import annotations

from itertools import product

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


def _is_target(state: State) -> bool:
    return all(bit == 0 for bit in state)


def _flip_bit(state: State, index: int) -> State:
    values = list(state)
    values[index] = 1 - values[index]
    return tuple(values)


def run_bitstring_demo(
    *,
    n_bits: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if n_bits < 1:
        raise ValueError("n_bits must be >= 1")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    target = (0,) * n_bits
    non_target_states = tuple(
        state for state in product((0, 1), repeat=n_bits) if state != target
    )

    def sample_initial_state(rng) -> State:
        return non_target_states[rng.randrange(len(non_target_states))]

    def initial_state_distribution() -> dict[State, float]:
        probability = 1.0 / len(non_target_states)
        return {state: probability for state in non_target_states}

    def applicable_operators(state: State) -> tuple[Operator, ...]:
        return tuple(range(n_bits))

    def apply_operator(state: State, operator: Operator, rng) -> State:
        del rng
        return _flip_bit(state, operator)

    problem_space = ProblemSpace(
        S=f"binary strings of length {n_bits}",
        operators=("flip_bit(i)",),
        C=(f"index bounds: 0 <= i < {n_bits}",),
        E="Hamming distance to all-zero target",
        H=float(H),
        H_unit="bit_flip",
        S_init="uniform random bitstring (non-target enforced)",
        S_goal="all-zero bitstring",
        executor=ProblemExecutor(
            initial_state_sampler=sample_initial_state,
            initial_state_distribution=initial_state_distribution,
            is_goal=_is_target,
            applicable_operators=applicable_operators,
            apply_operator=apply_operator,
            enumerate_states=lambda: tuple(non_target_states) + (target,),
            evaluate=lambda state: -sum(state),
            state_serializer=list,
            operator_serializer=lambda operator: f"flip_bit({operator})",
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="greedy_hamming_repair",
            operator_semantics="single-bit-flip",
        ),
        choose_operator=lambda problem_space, state, rng: next(
            index for index, bit in enumerate(state) if bit != 0
        ),
        operator_distribution=lambda problem_space, state: {
            next(index for index, bit in enumerate(state) if bit != 0): 1.0,
        },
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_uniform_bit_flip",
            operator_semantics="single-bit-flip",
        ),
        choose_operator=lambda problem_space, state, rng: rng.randrange(n_bits),
        operator_distribution=lambda problem_space, state: {
            index: 1.0 / n_bits for index in range(n_bits)
        },
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_low_index_biased_bit_flip",
            operator_semantics="single-bit-flip",
            description="Goal-agnostic null that over-samples low-index operators.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            {index: float(n_bits - index) for index in range(n_bits)},
            rng,
        ),
        operator_distribution=lambda problem_space, state: {
            index: float(n_bits - index) for index in range(n_bits)
        },
    )

    exact_supported = n_bits <= 8 and H <= 400
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
        "state_space_size": 2**n_bits,
        "exact_supported": exact_supported,
    }
    if not exact_supported:
        result["exact"] = {
            "unsupported": "bitstring exact finite-horizon enumeration is only enabled for n_bits <= 8 and H <= 400",
        }
    return result
