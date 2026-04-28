from __future__ import annotations

import random
from typing import Iterable

from core import (
    ExecutablePolicy,
    PolicySpec,
    ProblemExecutor,
    ProblemSpace,
    compare_policies_in_problem_space,
)
from demos.common import sample_weighted

Token = int | str
State = tuple[frozenset[int], tuple[tuple[int, int], ...]]
Operator = int


def _eval_rpn(tokens: tuple[Token, ...], *, x: int) -> int:
    stack: list[int] = []
    for token in tokens:
        if token == "x":
            stack.append(x)
            continue
        if isinstance(token, int):
            stack.append(token)
            continue
        if token in {"+", "*"}:
            if len(stack) < 2:
                raise ValueError("invalid rpn program (stack underflow)")
            b = stack.pop()
            a = stack.pop()
            stack.append(a + b if token == "+" else a * b)
            continue
        raise ValueError(f"invalid token: {token!r}")

    if len(stack) != 1:
        raise ValueError("invalid rpn program (final stack size != 1)")
    return stack[0]


def _matches_examples(tokens: tuple[Token, ...], *, examples: Iterable[tuple[int, int]]) -> bool:
    for x, y in examples:
        if _eval_rpn(tokens, x=x) != y:
            return False
    return True


def _generate_programs(
    *,
    max_len: int,
    operands: list[Token],
    ops: list[str],
) -> list[tuple[Token, ...]]:
    if max_len < 1:
        raise ValueError("max_len must be >= 1")
    if max_len > 7:
        raise ValueError("max_len must be <= 7 for this demo (keeps the space small)")
    if not operands or not ops:
        raise ValueError("operands and ops must be non-empty")

    out: list[tuple[Token, ...]] = []
    prefix: list[Token] = []

    def rec(depth: int) -> None:
        if 1 <= len(prefix) <= max_len and depth == 1:
            out.append(tuple(prefix))
        if len(prefix) == max_len:
            return

        for tok in operands:
            prefix.append(tok)
            rec(depth + 1)
            prefix.pop()

        if depth >= 2:
            for op in ops:
                prefix.append(op)
                rec(depth - 1)
                prefix.pop()

    rec(0)
    return out


def _canonical_linear_program(*, a: int, b: int) -> tuple[Token, ...]:
    if a == 0:
        return (b,)

    out: list[Token] = ["x"]
    if a != 1:
        out.extend([a, "*"])
    if b != 0:
        out.extend([b, "+"])
    return tuple(out)


def _target_examples(*, a: int, b: int) -> tuple[tuple[int, int], ...]:
    xs = (-2, -1, 0, 1, 2)
    return tuple((x, a * x + b) for x in xs)


def run_synthesis_demo(
    *,
    max_len: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if max_len < 5:
        raise ValueError("max_len must be >= 5 (so all a*x+b targets are representable)")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    coef_max = 2
    operands: list[Token] = ["x", -2, -1, 0, 1, 2]
    ops = ["+", "*"]
    programs = _generate_programs(max_len=max_len, operands=operands, ops=ops)
    program_lengths = {index: len(program) for index, program in enumerate(programs)}

    linear_programs: list[tuple[Token, ...]] = []
    for a in range(-coef_max, coef_max + 1):
        for b in range(-coef_max, coef_max + 1):
            linear_programs.append(_canonical_linear_program(a=a, b=b))
    linear_programs.sort(key=lambda program: (len(program), tuple(str(token) for token in program)))

    linear_first_order: list[int] = []
    seen: set[int] = set()
    for program in linear_programs:
        try:
            index = programs.index(program)
        except ValueError:
            continue
        if index not in seen:
            seen.add(index)
            linear_first_order.append(index)
    linear_first_order.extend(index for index in range(len(programs)) if index not in seen)

    def sample_initial_state(rng: random.Random) -> State:
        a = rng.randint(-coef_max, coef_max)
        b = rng.randint(-coef_max, coef_max)
        if a == 0 and b == 0:
            a = 1
        return (frozenset(), _target_examples(a=a, b=b))

    def applicable_operators(state: State) -> tuple[Operator, ...]:
        tried, _examples = state
        return tuple(index for index in range(len(programs)) if index not in tried)

    def apply_operator(state: State, operator: Operator, rng: random.Random) -> State:
        del rng
        tried, examples = state
        return (frozenset(set(tried) | {operator}), examples)

    def is_goal(state: State) -> bool:
        tried, examples = state
        return any(_matches_examples(programs[index], examples=examples) for index in tried)

    def uniform_remaining_distribution(state: State) -> dict[Operator, float]:
        remaining = applicable_operators(state)
        return {index: 1.0 / len(remaining) for index in remaining}

    def length_biased_distribution(state: State) -> dict[Operator, float]:
        return {
            index: 1.0 / float(program_lengths[index])
            for index in applicable_operators(state)
        }

    problem_space = ProblemSpace(
        S="syntactically valid bounded-length RPN programs with target I/O examples",
        operators=("evaluate_next_program_candidate",),
        C=("stack must not underflow", f"program length <= {max_len}"),
        E="program matches all I/O examples",
        H=float(H),
        H_unit="program_eval",
        S_init="empty search history with sampled linear target examples",
        S_goal="a tried program consistent with all examples",
        executor=ProblemExecutor(
            initial_state_sampler=sample_initial_state,
            is_goal=is_goal,
            applicable_operators=applicable_operators,
            apply_operator=apply_operator,
            evaluate=lambda state: -len(state[0]),
            state_serializer=lambda state: {
                "n_tried": len(state[0]),
                "examples": [list(example) for example in state[1]],
            },
            operator_serializer=lambda index: f"program_index({index})",
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="linear_first_then_enumerate_rpn",
            operator_semantics="bounded-rpn-enumeration",
        ),
        choose_operator=lambda problem_space, state, rng: next(
            index for index in linear_first_order if index not in state[0]
        ),
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_uniform_program_sampling",
            operator_semantics="bounded-rpn-enumeration",
        ),
        choose_operator=lambda problem_space, state, rng: rng.choice(applicable_operators(state)),
        operator_distribution=lambda problem_space, state: uniform_remaining_distribution(state),
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_length_biased_program_sampling",
            operator_semantics="bounded-rpn-enumeration",
            description="Goal-agnostic null that over-samples shorter candidate programs.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            length_biased_distribution(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: length_biased_distribution(state),
    )

    result = compare_policies_in_problem_space(
        problem_space,
        agent_policy,
        blind_policy,
        trials=trials,
        seed=seed,
        blind_policy_family={biased_blind.spec.name: biased_blind},
        bootstrap_samples=400,
        exact=False,
    )
    result["domain"] = {
        "candidate_program_count": len(programs),
        "exact_supported": False,
    }
    result["exact"] = {
        "unsupported": "program synthesis search state space is not enumerated in the executable model",
    }
    return result
