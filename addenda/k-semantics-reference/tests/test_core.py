import math
import random

import pytest

from core import (
    ExecutablePolicy,
    OperatorCostSpec,
    PairedTrial,
    PolicySpec,
    ProblemExecutor,
    ProblemSpace,
    compare_composite_k,
    compare_policies_in_problem_space,
    compose_problem_spaces,
    k_log10_ratio,
    paper_k_from_expectations,
    paper_k_from_paired_trials,
)


def test_k_log10_ratio_invariants():
    assert k_log10_ratio(tau_blind=10.0, tau_agent=10.0) == 0.0
    k1 = k_log10_ratio(tau_blind=100.0, tau_agent=10.0)
    k2 = k_log10_ratio(tau_blind=1000.0, tau_agent=100.0)
    assert k1 == k2
    k_total = k_log10_ratio(tau_blind=100.0 * 1000.0, tau_agent=10.0 * 100.0)
    assert math.isclose(k_total, k1 + k2)


@pytest.mark.parametrize(
    ("tau_blind", "tau_agent"),
    [
        (0.0, 1.0),
        (1.0, 0.0),
    ],
)
def test_k_log10_ratio_rejects_nonpositive_taus(tau_blind: float, tau_agent: float):
    with pytest.raises(ValueError, match="taus must be > 0"):
        k_log10_ratio(tau_blind=tau_blind, tau_agent=tau_agent)


def test_paper_k_all_solved_matches_direct_ratio():
    trials = [
        PairedTrial(agent_cost=10.0, agent_solved=True, blind_cost=100.0, blind_solved=True),
        PairedTrial(agent_cost=20.0, agent_solved=True, blind_cost=200.0, blind_solved=True),
    ]
    out = paper_k_from_paired_trials(
        trials,
        H=1000.0,
        H_unit="op",
        agent_policy="agent",
        blind_policy="blind",
    )
    assert out["solve_rates"]["both_solved"] == 1.0
    assert math.isclose(out["tau"]["agent_restricted_mean"], 15.0)
    assert math.isclose(out["tau"]["blind_restricted_mean"], 150.0)
    assert math.isclose(out["K"]["restricted_mean_at_stop"], 1.0)
    assert math.isclose(out["K"]["conditional_on_both_solved"], 1.0)


def test_paper_k_uses_observed_cost_for_unsolved_trials():
    trials = [
        PairedTrial(
            agent_cost=10.0,
            agent_solved=True,
            blind_cost=0.0,
            blind_solved=False,
            blind_observed_cost=17.0,
        ),
    ]
    out = paper_k_from_paired_trials(
        trials,
        H=1000.0,
        H_unit="attempt",
    )
    assert out["tau"]["agent_restricted_mean"] == 10.0
    assert out["tau"]["blind_restricted_mean"] == 17.0
    assert out["K"]["conditional_on_both_solved"] is None
    assert math.isclose(out["K"]["restricted_mean_at_stop"], math.log10(17.0 / 10.0))


def test_paper_k_bootstrap_uncertainty_reproducible_with_seed():
    trials = [
        PairedTrial(agent_cost=9.0, agent_solved=True, blind_cost=90.0, blind_solved=True),
        PairedTrial(agent_cost=12.0, agent_solved=True, blind_cost=120.0, blind_solved=True),
        PairedTrial(
            agent_cost=0.0,
            agent_solved=False,
            blind_cost=0.0,
            blind_solved=False,
            agent_observed_cost=1000.0,
            blind_observed_cost=1000.0,
        ),
    ]

    out_a = paper_k_from_paired_trials(
        trials,
        H=1000.0,
        H_unit="op",
        bootstrap_samples=400,
        bootstrap_ci_level=0.9,
        bootstrap_seed=123,
    )
    out_b = paper_k_from_paired_trials(
        trials,
        H=1000.0,
        H_unit="op",
        bootstrap_samples=400,
        bootstrap_ci_level=0.9,
        bootstrap_seed=123,
    )

    assert out_a["uncertainty"] == out_b["uncertainty"]
    lower_ci = out_a["uncertainty"]["K_restricted_mean_ci"]
    assert lower_ci is not None
    assert lower_ci[0] <= out_a["K"]["restricted_mean_at_stop"] <= lower_ci[1]


def test_paper_k_bootstrap_rejects_invalid_parameters():
    trials = [
        PairedTrial(agent_cost=1.0, agent_solved=True, blind_cost=2.0, blind_solved=True),
    ]

    with pytest.raises(ValueError, match="bootstrap_samples must be >= 0"):
        paper_k_from_paired_trials(trials, H=100.0, H_unit="op", bootstrap_samples=-1)

    with pytest.raises(ValueError, match=r"bootstrap_ci_level must be in \(0, 1\)"):
        paper_k_from_paired_trials(trials, H=100.0, H_unit="op", bootstrap_ci_level=1.0)


def test_problem_space_serialized_with_structured_operator_costs():
    trials = [
        PairedTrial(agent_cost=1.0, agent_solved=True, blind_cost=10.0, blind_solved=True),
    ]
    ps = ProblemSpace(
        S="test states",
        operators=("op_a", "op_b"),
        C=("forbid_x",),
        E="maximize score",
        H=50.0,
        H_unit="op",
        w=OperatorCostSpec(
            default_cost=2.0,
            per_operator=(("op_b", 3.0),),
            description="toy operator costs",
        ),
        w_unit="joule",
        S_init="initial",
        S_goal="goal",
    )
    out = paper_k_from_paired_trials(trials, problem_space=ps)
    assert out["problem_space"]["P"]["S"] == "test states"
    assert out["problem_space"]["P"]["O"] == ["op_a", "op_b"]
    assert out["problem_space"]["P"]["C"] == ["forbid_x"]
    assert out["problem_space"]["P"]["E"] == "maximize score"
    assert out["problem_space"]["P"]["H"] == 50.0
    assert out["problem_space"]["w"]["default"] == 2.0
    assert out["problem_space"]["w"]["by_operator"] == {"op_b": 3.0}
    assert out["problem_space"]["w"]["unit"] == "joule"
    assert out["problem_space"]["S_init"] == "initial"
    assert out["problem_space"]["S_goal"] == "goal"


def test_reject_mismatched_operator_semantics():
    trials = [
        PairedTrial(agent_cost=1.0, agent_solved=True, blind_cost=2.0, blind_solved=True),
    ]
    with pytest.raises(ValueError, match="must share operator semantics"):
        paper_k_from_paired_trials(
            trials,
            H=10.0,
            H_unit="op",
            agent_policy_spec=PolicySpec(name="agent", operator_semantics="sem_a"),
            blind_policy_spec=PolicySpec(name="blind", operator_semantics="sem_b"),
        )


def test_paper_k_from_expectations_matches_ratio():
    out = paper_k_from_expectations(
        tau_agent=100.0,
        tau_blind=10_000.0,
        H=1.0,
        H_unit="step",
    )
    assert math.isclose(out["K"]["restricted_mean_at_stop"], 2.0)
    assert math.isclose(out["K"]["conditional_on_both_solved"], 2.0)
    assert out["counts"]["trials"] == 1


def test_compare_policies_in_problem_space_reports_exact_metrics():
    def sample_initial_state(rng: random.Random) -> tuple[int]:
        del rng
        return (1,)

    def applicable_operators(state: tuple[int]) -> tuple[str, ...]:
        return ("flip",) if state == (1,) else ()

    def apply_operator(state: tuple[int], operator: str, rng: random.Random) -> tuple[int]:
        del rng
        assert operator == "flip"
        return (0,)

    executor = ProblemExecutor(
        initial_state_sampler=sample_initial_state,
        initial_state_distribution=lambda: {(1,): 1.0},
        is_goal=lambda state: state == (0,),
        applicable_operators=applicable_operators,
        apply_operator=apply_operator,
        enumerate_states=lambda: ((0,), (1,)),
        state_serializer=list,
    )
    problem_space = ProblemSpace(
        S="single bit",
        operators=("flip",),
        C=("must be 0 or 1",),
        E="reach zero",
        H=1.0,
        H_unit="flip",
        executor=executor,
    )
    policy = ExecutablePolicy(
        spec=PolicySpec(name="flip_once", operator_semantics="single_flip"),
        choose_operator=lambda problem_space, state, rng: "flip",
        operator_distribution=lambda problem_space, state: {"flip": 1.0},
    )
    result = compare_policies_in_problem_space(
        problem_space,
        policy,
        policy,
        trials=5,
        seed=7,
        exact=True,
        provenance_limit=2,
    )

    assert result["execution"]["paired_initial_states"] is True
    assert len(result["execution"]["provenance_head"]) == 2
    assert result["exact"]["solve_rates"]["agent_exact"] == 1.0
    assert result["exact"]["solve_rates"]["blind_exact"] == 1.0
    assert result["exact"]["K"]["restricted_mean_at_H_exact"] == 0.0


def test_compose_problem_spaces_and_compare_composite_k():
    stage_a = ProblemSpace(
        S="a",
        operators=("move_a",),
        C=(),
        E="goal_a",
        H=2.0,
        H_unit="step",
        w=3.0,
    )
    stage_b = ProblemSpace(
        S="b",
        operators=("move_b",),
        C=(),
        E="goal_b",
        H=5.0,
        H_unit="step",
        w=7.0,
    )
    composite = compose_problem_spaces(stage_a, stage_b)
    assert composite.H == 10.0
    assert composite.cost_spec.default_cost == 21.0

    additivity = compare_composite_k(
        {"K": {"restricted_mean_at_stop": 1.25}},
        {"K": {"restricted_mean_at_stop": 0.75}},
        composite_result={"K": {"restricted_mean_at_stop": 2.0}},
    )
    assert additivity["K_sum_stages"] == 2.0
    assert additivity["delta"] == 0.0
