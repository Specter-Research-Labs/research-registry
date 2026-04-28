from __future__ import annotations

import math

from core import (
    ExecutablePolicy,
    PolicySpec,
    ProblemExecutor,
    ProblemSpace,
    compare_policies_in_problem_space,
)
from demos.common import sample_weighted

State = tuple[int, int]
Operator = str


def _apply_move(state: State, operator: Operator) -> State:
    x, y = state
    if operator == "move_right":
        return (x + 1, y)
    if operator == "move_left":
        return (x - 1, y)
    if operator == "move_down":
        return (x, y + 1)
    if operator == "move_up":
        return (x, y - 1)
    raise ValueError(f"unknown operator: {operator}")


def _concentration(pos: State, goal: State) -> float:
    dx = pos[0] - goal[0]
    dy = pos[1] - goal[1]
    return 1.0 / (1.0 + math.hypot(dx, dy))


def run_chemotaxis_demo(
    *,
    size: int,
    noise_sigma: float = 0.0,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if size < 2:
        raise ValueError("size must be >= 2")
    if noise_sigma < 0:
        raise ValueError("noise_sigma must be >= 0")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    start = (0, 0)
    goal = (size - 1, size - 1)

    def applicable_operators(state: State) -> tuple[Operator, ...]:
        x, y = state
        operators: list[Operator] = []
        if x + 1 < size:
            operators.append("move_right")
        if y + 1 < size:
            operators.append("move_down")
        if x > 0:
            operators.append("move_left")
        if y > 0:
            operators.append("move_up")
        return tuple(operators)

    def greedy_distribution(state: State) -> dict[Operator, float]:
        best_operator = max(
            applicable_operators(state),
            key=lambda operator: _concentration(_apply_move(state, operator), goal),
        )
        return {best_operator: 1.0}

    def axis_biased_distribution(state: State) -> dict[Operator, float]:
        weights: dict[Operator, float] = {}
        for operator in applicable_operators(state):
            weights[operator] = 2.0 if operator in {"move_left", "move_right"} else 1.0
        return weights

    problem_space = ProblemSpace(
        S=f"cell positions on {size}x{size} lattice",
        operators=("move_to_neighbor_patch",),
        C=("lattice boundaries", "one move per step"),
        E="negative distance to chemoattractant maximum",
        H=float(H),
        H_unit="step",
        S_init="(0,0)",
        S_goal=f"{goal}",
        executor=ProblemExecutor(
            initial_state_sampler=lambda rng: start,
            initial_state_distribution=lambda: {start: 1.0},
            is_goal=lambda state: state == goal,
            applicable_operators=applicable_operators,
            apply_operator=lambda state, operator, rng: _apply_move(state, operator),
            enumerate_states=lambda: tuple((x, y) for x in range(size) for y in range(size)),
            evaluate=lambda state: _concentration(state, goal),
            state_serializer=list,
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name=f"gradient_follower(noise_sigma={noise_sigma})",
            operator_semantics="4-neighbor-step",
        ),
        choose_operator=lambda problem_space, state, rng: max(
            applicable_operators(state),
            key=lambda operator: _concentration(_apply_move(state, operator), goal)
            + rng.gauss(0, noise_sigma),
        ),
        operator_distribution=((lambda problem_space, state: greedy_distribution(state)) if noise_sigma == 0.0 else None),
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_uniform_random_walk",
            operator_semantics="4-neighbor-step",
        ),
        choose_operator=lambda problem_space, state, rng: rng.choice(applicable_operators(state)),
        operator_distribution=lambda problem_space, state: {
            operator: 1.0 / len(applicable_operators(state))
            for operator in applicable_operators(state)
        },
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_axis_biased_random_walk",
            operator_semantics="4-neighbor-step",
            description="Goal-agnostic null that prefers horizontal moves when available.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            axis_biased_distribution(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: axis_biased_distribution(state),
    )

    exact_supported = noise_sigma == 0.0
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
        "state_space_size": size * size,
        "exact_supported": exact_supported,
    }
    if not exact_supported:
        result["exact"] = {
            "unsupported": "chemotaxis exact finite-horizon enumeration is only enabled when noise_sigma == 0",
        }
    return result
