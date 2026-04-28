from __future__ import annotations

import random
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
Inputs = tuple[tuple[int, int], ...]


def _make_and_network(n: int, rng) -> Inputs:
    inputs: list[tuple[int, int]] = []
    for i in range(n):
        candidates = [j for j in range(n) if j != i]
        j1, j2 = rng.sample(candidates, 2)
        inputs.append((j1, j2))
    return tuple(inputs)


def _bn_update(state: State, gene: int, inputs: Inputs) -> int:
    j1, j2 = inputs[gene]
    return state[j1] & state[j2]


def _apply_operator(state: State, gene: int, inputs: Inputs) -> State:
    updated = list(state)
    updated[gene] = _bn_update(state, gene, inputs)
    return tuple(updated)


def _hamming_to_target(state: State, target: State) -> int:
    return sum(int(a != b) for a, b in zip(state, target, strict=True))


def run_grn_demo(
    *,
    n_genes: int,
    trials: int,
    H: int,
    seed: int,
) -> dict:
    if n_genes < 3:
        raise ValueError("n_genes must be >= 3")
    if trials < 1:
        raise ValueError("trials must be >= 1")
    if H < 1:
        raise ValueError("H must be >= 1")

    rng = random.Random(seed)
    target = (0,) * n_genes
    inputs = _make_and_network(n_genes, rng)
    non_target_states = tuple(
        state for state in product((0, 1), repeat=n_genes) if state != target
    )

    def sample_initial_state(rng) -> State:
        return non_target_states[rng.randrange(len(non_target_states))]

    def initial_state_distribution() -> dict[State, float]:
        probability = 1.0 / len(non_target_states)
        return {state: probability for state in non_target_states}

    def agent_distribution(state: State) -> dict[Operator, float]:
        best_distance = None
        best_genes: list[Operator] = []
        for gene in range(n_genes):
            next_state = _apply_operator(state, gene, inputs)
            distance = _hamming_to_target(next_state, target)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_genes = [gene]
            elif distance == best_distance:
                best_genes.append(gene)
        probability = 1.0 / len(best_genes)
        return {gene: probability for gene in best_genes}

    def low_index_bias(state: State) -> dict[Operator, float]:
        return {gene: float(n_genes - gene) for gene in range(n_genes)}

    problem_space = ProblemSpace(
        S=f"Boolean vectors in {{0,1}}^{n_genes}",
        operators=("apply_async_gene_rule(gene)",),
        C=("gene index bounds",),
        E="Hamming distance to all-zeros attractor",
        H=float(H),
        H_unit="gene_update",
        S_init="uniform random non-target state",
        S_goal="all-zeros state",
        executor=ProblemExecutor(
            initial_state_sampler=sample_initial_state,
            initial_state_distribution=initial_state_distribution,
            is_goal=lambda state: state == target,
            applicable_operators=lambda state: tuple(range(n_genes)),
            apply_operator=lambda state, gene, rng: _apply_operator(state, gene, inputs),
            enumerate_states=lambda: tuple(non_target_states) + (target,),
            evaluate=lambda state: -_hamming_to_target(state, target),
            state_serializer=list,
            operator_serializer=lambda gene: f"apply_gene_rule({gene})",
        ),
    )
    agent_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="greedy_async_boolean_network_update",
            operator_semantics="async_boolean_network_rule_update",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            agent_distribution(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: agent_distribution(state),
    )
    blind_policy = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_random_async_boolean_network_update",
            operator_semantics="async_boolean_network_rule_update",
        ),
        choose_operator=lambda problem_space, state, rng: rng.randrange(n_genes),
        operator_distribution=lambda problem_space, state: {
            gene: 1.0 / n_genes for gene in range(n_genes)
        },
    )
    biased_blind = ExecutablePolicy(
        spec=PolicySpec(
            name="blind_low_index_biased_async_update",
            operator_semantics="async_boolean_network_rule_update",
            description="Goal-agnostic null that over-samples low-index genes.",
        ),
        choose_operator=lambda problem_space, state, rng: sample_weighted(
            low_index_bias(state),
            rng,
        ),
        operator_distribution=lambda problem_space, state: low_index_bias(state),
    )

    exact_supported = n_genes <= 8
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
        "state_space_size": 2**n_genes,
        "exact_supported": exact_supported,
    }
    if not exact_supported:
        result["exact"] = {
            "unsupported": "grn exact finite-horizon enumeration is only enabled for n_genes <= 8",
        }
    return result
