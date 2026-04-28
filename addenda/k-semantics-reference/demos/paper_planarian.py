from __future__ import annotations

import math

from core import PolicySpec, ProblemSpace, paper_k_from_expectations


def run_paper_planarian_demo(
    *,
    n_responsive_genes: int = 2700,
    n_required_genes: int = 10,
    neoblast_count: int = 100_000,
    neoblast_cycle_hours: float = 30.0,
    tau_agent_days: float = 37.0,
) -> dict:
    if n_responsive_genes < 1:
        raise ValueError("n_responsive_genes must be >= 1")
    if n_required_genes < 1:
        raise ValueError("n_required_genes must be >= 1")
    if n_required_genes > n_responsive_genes:
        raise ValueError("n_required_genes must be <= n_responsive_genes")
    if neoblast_count < 1:
        raise ValueError("neoblast_count must be >= 1")
    if neoblast_cycle_hours <= 0:
        raise ValueError("neoblast_cycle_hours must be > 0")
    if tau_agent_days <= 0:
        raise ValueError("tau_agent_days must be > 0")

    problem_space = ProblemSpace(
        S="combinatorial gene-expression configurations in BaCl2 adaptation",
        operators=("edit_expression_of_gene_subset",),
        C=("viability and developmental polarity constraints",),
        E="restore viable head regeneration under BaCl2 perturbation",
        H=22_000.0,
        H_unit="operator_cycle",
        w=1.0,
        w_unit="second",
        S_init="post-degeneration transcriptional state",
        S_goal="BaCl2-tolerant regenerated head state",
    )
    agent_spec = PolicySpec(
        name="targeted_transcriptional_adaptation",
        operator_semantics="gene_subset_edit_same_P",
    )
    blind_spec = PolicySpec(
        name="uniform_random_gene_subset_search",
        operator_semantics="gene_subset_edit_same_P",
    )

    search_space_size = math.comb(n_responsive_genes, n_required_genes)
    rounds_to_cover_space = search_space_size / float(neoblast_count)
    tau_blind_s = rounds_to_cover_space * neoblast_cycle_hours * 3600.0
    tau_agent_s = tau_agent_days * 24.0 * 3600.0

    result = paper_k_from_expectations(
        tau_agent=tau_agent_s,
        tau_blind=tau_blind_s,
        problem_space=problem_space,
        agent_policy_spec=agent_spec,
        blind_policy_spec=blind_spec,
    )
    k_value = result["K"]["lower_bound_censored_at_H"]

    return {
        "schema_version": 2,
        "paper_reference": {
            "paper_id": "009-2025-cognition-all-the-way-down-2-0",
            "section": "6.2",
            "reported_K": 21.0,
        },
        "inputs": {
            "n_responsive_genes": n_responsive_genes,
            "n_required_genes": n_required_genes,
            "neoblast_count": neoblast_count,
            "neoblast_cycle_hours": neoblast_cycle_hours,
            "tau_agent_days": tau_agent_days,
        },
        "assumption_ledger": [
            {
                "id": "search_space_proxy",
                "assumption": (
                    "The blind search space is approximated as choosing n_required_genes from the "
                    "responsive-gene set, with search-space size comb(n_responsive, n_required)."
                ),
                "impact": "Any change to the combinatoric abstraction changes tau_blind by orders of magnitude.",
            },
            {
                "id": "parallel_neoblast_search",
                "assumption": (
                    "neoblast_count acts like a pool of parallel blind explorers that partition the "
                    "search burden evenly across rounds."
                ),
                "impact": "This is the dominant control on the blind coverage rate.",
            },
            {
                "id": "cycle_time_proxy",
                "assumption": (
                    "neoblast_cycle_hours is the relevant operator-cycle duration for the blind baseline."
                ),
                "impact": "Longer cycle times linearly inflate tau_blind.",
            },
            {
                "id": "observed_agent_duration",
                "assumption": (
                    "tau_agent_days is treated as the observed adaptive timescale of the biological system."
                ),
                "impact": "The final K is calibrated against this reported organism-scale duration.",
            },
        ],
        "derived": {
            "search_space_size_comb": str(search_space_size),
            "search_space_size_comb_scientific": float(search_space_size),
            "rounds_to_cover_space": rounds_to_cover_space,
            "tau_blind_s": tau_blind_s,
            "tau_agent_s": tau_agent_s,
            "K": k_value,
            "fold_efficiency": 10.0**k_value,
            "path_information_bits": k_value * math.log2(10.0),
        },
        "result": result,
    }
