from __future__ import annotations

from collections import deque

from core import (
    ExecutablePolicy,
    PolicySpec,
    ProblemExecutor,
    ProblemSpace,
    compare_policies_in_problem_space,
)
from demos.common import sample_weighted

State = tuple[int, ...]
Operator = tuple[int, int]


def _legal_moves(state: State) -> tuple[Operator, ...]:
    top: dict[int, int] = {}
    for disk, peg in enumerate(state):
        if peg not in top or disk < top[peg]:
            top[peg] = disk

    moves: list[Operator] = []
    for src_peg, disk in top.items():
        for dst_peg in range(3):
            if dst_peg == src_peg:
                continue
            if dst_peg not in top or top[dst_peg] > disk:
                moves.append((disk, dst_peg))
    return tuple(moves)


def _apply_move(state: State, operator: Operator) -> State:
    disk, dst_peg = operator
    updated = list(state)
    updated[disk] = dst_peg
    return tuple(updated)


def _distance_to_target(target: State) -> dict[State, int]:
    queue: deque[State] = deque([target])
    distance = {target: 0}
    while queue:
        state = queue.popleft()
        for operator in _legal_moves(state):
            previous = _apply_move(state, operator)
            if previous in distance:
                continue
            distance[previous] = distance[state] + 1
            queue.append(previous)
    return distance


def run_hanoi_demo(
    *,
    n_disks: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if n_disks < 1:
        raise ValueError("n_disks must be >= 1")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    start = (0,) * n_disks
    target = (2,) * n_disks
    distance_map = _distance_to_target(target)

    def greedy_distribution(state: State) -> dict[Operator, float]:
        best_distance = None
        best_moves: list[Operator] = []
        for operator in _legal_moves(state):
            next_state = _apply_move(state, operator)
            candidate_distance = distance_map[next_state]
            if best_distance is None or candidate_distance < best_distance:
                best_distance = candidate_distance
                best_moves = [operator]
            elif candidate_distance == best_distance:
                best_moves.append(operator)
        probability = 1.0 / len(best_moves)
        return {operator: probability for operator in best_moves}

    def small_disk_bias(state: State) -> dict[Operator, float]:
        return {operator: float(n_disks - operator[0]) for operator in _legal_moves(state)}

    problem_space = ProblemSpace(
        S=f"Tower of Hanoi states with {n_disks} disks",
        operators=("move_top_disk(src,dst)",),
        C=("no larger disk on smaller disk", "move only top disk"),
        E="distance to solved target peg assignment",
        H=float(H),
        H_unit="move",
        S_init=str(list(start)),
        S_goal=str(list(target)),
        executor=ProblemExecutor(
            initial_state_sampler=lambda rng: start,
            initial_state_distribution=lambda: {start: 1.0},
            is_goal=lambda state: state == target,
            applicable_operators=_legal_moves,
            apply_operator=lambda state, operator, rng: _apply_move(state, operator),
            enumerate_states=lambda: tuple(distance_map),
            evaluate=lambda state: -distance_map[state],
            state_serializer=list,
            operator_serializer=lambda operator: f"move_disk_{operator[0]}_to_{operator[1]}",
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="optimal_shortest_path_policy",
            operator_semantics="legal_hanoi_move",
        ),
        choose_operator=lambda problem_space, state, rng: min(
            greedy_distribution(state),
            key=lambda operator: (distance_map[_apply_move(state, operator)], operator),
        ),
        operator_distribution=lambda problem_space, state: greedy_distribution(state),
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_uniform_legal_move",
            operator_semantics="legal_hanoi_move",
        ),
        choose_operator=lambda problem_space, state, rng: rng.choice(_legal_moves(state)),
        operator_distribution=lambda problem_space, state: {
            operator: 1.0 / len(_legal_moves(state)) for operator in _legal_moves(state)
        },
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_small_disk_biased_move",
            operator_semantics="legal_hanoi_move",
            description="Goal-agnostic null that over-samples moves involving smaller disks.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            small_disk_bias(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: small_disk_bias(state),
    )

    result = compare_policies_in_problem_space(
        problem_space,
        agent_policy,
        blind_policy,
        trials=trials,
        seed=seed,
        blind_policy_family={biased_blind.spec.name: biased_blind},
        bootstrap_samples=400,
        exact=n_disks <= 6,
    )
    result["domain"] = {
        "state_space_size": len(distance_map),
        "exact_supported": n_disks <= 6,
    }
    return result
