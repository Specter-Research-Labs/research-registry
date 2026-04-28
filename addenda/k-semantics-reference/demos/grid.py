from __future__ import annotations

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


def shortest_path_open_grid_cost(*, size: int) -> int:
    if size < 2:
        raise ValueError("size must be >= 2")
    return 2 * (size - 1)


def run_grid_demo(
    *,
    size: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if size < 2:
        raise ValueError("size must be >= 2")
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

    def primary_agent_distribution(state: State) -> dict[Operator, float]:
        x, y = state
        if x < goal[0]:
            return {"move_right": 1.0}
        if y < goal[1]:
            return {"move_down": 1.0}
        return {}

    def axis_biased_distribution(state: State) -> dict[Operator, float]:
        weights: dict[Operator, float] = {}
        for operator in applicable_operators(state):
            weights[operator] = 2.0 if operator in {"move_left", "move_right"} else 1.0
        return weights

    problem_space = ProblemSpace(
        S=f"lattice positions on {size}x{size} grid",
        operators=("move_up", "move_down", "move_left", "move_right"),
        C=("moves outside grid are forbidden",),
        E="negative Manhattan distance to goal",
        H=float(H),
        H_unit="step",
        S_init="(0,0)",
        S_goal=f"({size - 1},{size - 1})",
        executor=ProblemExecutor(
            initial_state_sampler=lambda rng: start,
            initial_state_distribution=lambda: {start: 1.0},
            is_goal=lambda state: state == goal,
            applicable_operators=applicable_operators,
            apply_operator=lambda state, operator, rng: _apply_move(state, operator),
            enumerate_states=lambda: tuple((x, y) for x in range(size) for y in range(size)),
            evaluate=lambda state: -(abs(goal[0] - state[0]) + abs(goal[1] - state[1])),
            state_serializer=list,
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="shortest_path_open_grid",
            operator_semantics="4-neighbor-step",
        ),
        choose_operator=lambda problem_space, state, rng: next(iter(primary_agent_distribution(state))),
        operator_distribution=lambda problem_space, state: primary_agent_distribution(state),
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

    result = compare_policies_in_problem_space(
        problem_space,
        agent_policy,
        blind_policy,
        trials=trials,
        seed=seed,
        blind_policy_family={biased_blind.spec.name: biased_blind},
        bootstrap_samples=400,
        exact=True,
    )
    result["domain"] = {
        "state_space_size": size * size,
        "exact_supported": True,
    }
    return result
