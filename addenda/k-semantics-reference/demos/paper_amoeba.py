from __future__ import annotations

import math

from core import PolicySpec, ProblemSpace, paper_k_from_expectations


def _mfpt_seconds(
    *,
    distance_um: float,
    motility_um2_per_min: float,
    prefactor: float,
) -> float:
    if distance_um <= 0:
        raise ValueError("distance_um must be > 0")
    if motility_um2_per_min <= 0:
        raise ValueError("motility_um2_per_min must be > 0")
    if prefactor <= 0:
        raise ValueError("prefactor must be > 0")
    motility_um2_per_s = motility_um2_per_min / 60.0
    return (distance_um * distance_um) / (prefactor * motility_um2_per_s)


def run_paper_amoeba_demo(
    *,
    distance_um: float = 100.0,
    dcell_min_um2_per_min: float = 30.0,
    dcell_max_um2_per_min: float = 40.0,
    tau_agent_s: float = 100.0,
    mfpt_prefactor: float = 1.0,
) -> dict:
    if dcell_min_um2_per_min <= 0 or dcell_max_um2_per_min <= 0:
        raise ValueError("motility coefficients must be > 0")
    if dcell_min_um2_per_min > dcell_max_um2_per_min:
        raise ValueError("dcell_min_um2_per_min must be <= dcell_max_um2_per_min")
    if tau_agent_s <= 0:
        raise ValueError("tau_agent_s must be > 0")

    problem_space = ProblemSpace(
        S="~500 cortical patches representing membrane occupancy states",
        operators=("actin-driven pseudopod extension/retraction step",),
        C=("cortical tension and membrane integrity constraints",),
        E="thermodynamic motility expenditure toward nutrient patch",
        H=1.0,
        H_unit="predictive_step",
        w=1.0,
        w_unit="second",
        S_init="cell start location before gradient traversal",
        S_goal="nutrient patch location (~10 cell lengths)",
    )
    agent_spec = PolicySpec(
        name="amoeboid_chemotaxis_policy",
        operator_semantics="motility_step_same_P",
    )
    blind_spec = PolicySpec(
        name="maxent_random_walk_policy",
        operator_semantics="motility_step_same_P",
    )

    tau_blind_low = _mfpt_seconds(
        distance_um=distance_um,
        motility_um2_per_min=dcell_max_um2_per_min,
        prefactor=mfpt_prefactor,
    )
    tau_blind_high = _mfpt_seconds(
        distance_um=distance_um,
        motility_um2_per_min=dcell_min_um2_per_min,
        prefactor=mfpt_prefactor,
    )

    low_result = paper_k_from_expectations(
        tau_agent=tau_agent_s,
        tau_blind=tau_blind_low,
        problem_space=problem_space,
        agent_policy_spec=agent_spec,
        blind_policy_spec=blind_spec,
    )
    high_result = paper_k_from_expectations(
        tau_agent=tau_agent_s,
        tau_blind=tau_blind_high,
        problem_space=problem_space,
        agent_policy_spec=agent_spec,
        blind_policy_spec=blind_spec,
    )

    k_low = low_result["K"]["lower_bound_censored_at_H"]
    k_high = high_result["K"]["lower_bound_censored_at_H"]
    if k_low > k_high:
        k_low, k_high = k_high, k_low

    return {
        "schema_version": 2,
        "paper_reference": {
            "paper_id": "009-2025-cognition-all-the-way-down-2-0",
            "section": "5.2",
            "reported_K_range": [2.18, 2.30],
        },
        "inputs": {
            "distance_um": distance_um,
            "dcell_min_um2_per_min": dcell_min_um2_per_min,
            "dcell_max_um2_per_min": dcell_max_um2_per_min,
            "tau_agent_s": tau_agent_s,
            "mfpt_prefactor": mfpt_prefactor,
            "mfpt_model": "tau_blind = L^2 / (prefactor * Dcell)",
        },
        "assumption_ledger": [
            {
                "id": "same_problem_space",
                "assumption": (
                    "Agent and blind policies are compared in one shared motility problem space "
                    "with the same effective traversal operator semantics."
                ),
                "impact": "If false, the reported K is not semantically comparable.",
            },
            {
                "id": "mfpt_model_choice",
                "assumption": (
                    "The blind baseline is modeled with an MFPT diffusion estimate rather than a "
                    "full boundary-conditioned stochastic simulation."
                ),
                "impact": "Changes in the MFPT form shift tau_blind and therefore K directly.",
            },
            {
                "id": "motility_range",
                "assumption": (
                    "The random motility coefficient is well-approximated by the supplied "
                    "[dcell_min, dcell_max] interval."
                ),
                "impact": "The K interval width is driven mainly by this range.",
            },
            {
                "id": "observed_agent_time",
                "assumption": (
                    "tau_agent_s is treated as an external observed traversal time rather than "
                    "something re-derived from the same MFPT model."
                ),
                "impact": "The result is a calibration against the paper's observed agent time.",
            },
        ],
        "derived": {
            "tau_blind_range_s": [tau_blind_low, tau_blind_high],
            "K_range": [k_low, k_high],
            "fold_efficiency_range": [10.0**k_low, 10.0**k_high],
            "path_information_bits_range": [
                k_low * math.log2(10.0),
                k_high * math.log2(10.0),
            ],
        },
        "scenarios": {
            "Dcell_max_fast_walk": low_result,
            "Dcell_min_slow_walk": high_result,
        },
    }
