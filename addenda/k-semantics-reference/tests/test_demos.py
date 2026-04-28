import math
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demos.bitstring import run_bitstring_demo
from demos.chemotaxis import run_chemotaxis_demo
from demos.compositional import run_compositional_demo
from demos.grid import run_grid_demo
from demos.grn import run_grn_demo
from demos.hanoi import run_hanoi_demo
from demos.paper_amoeba import run_paper_amoeba_demo
from demos.paper_planarian import run_paper_planarian_demo
from demos.sorting import run_sorting_demo
from demos.synthesis import run_synthesis_demo


def _assert_common_demo_metrics(out, *, exact_supported: bool) -> None:
    assert out["domain"]["exact_supported"] is exact_supported
    assert out["tau"]["agent_mean_censored"] > 0.0
    assert out["tau"]["blind_mean_censored"] > 0.0
    assert math.isfinite(out["K"]["restricted_mean_at_stop"])
    if exact_supported:
        assert math.isfinite(out["exact"]["K"]["restricted_mean_at_H_exact"])
    else:
        assert out["exact"]["unsupported"]


def _assert_expected_semantics(out, expected: dict) -> None:
    assert out["problem_space"]["H_unit"] == expected["h_unit"]
    if "operators" in expected:
        assert out["problem_space"]["P"]["O"] == expected["operators"]
    if "state_prefix" in expected:
        assert out["problem_space"]["P"]["S"].startswith(expected["state_prefix"])
    if "default_cost" in expected:
        assert out["problem_space"]["w"]["default"] == expected["default_cost"]
    if "shared_operator_semantics" in expected:
        assert out["policies"]["shared_operator_semantics"] == expected["shared_operator_semantics"]
    if "agent_mean_censored" in expected:
        assert out["tau"]["agent_mean_censored"] == expected["agent_mean_censored"]


def test_exact_supported_demos_report_problem_semantics():
    cases = [
        (
            partial(run_sorting_demo, n=5, trials=25, H=50, seed=0),
            {"h_unit": "swap", "operators": ["adjacent_swap(i,i+1)"]},
        ),
        (
            partial(run_bitstring_demo, n_bits=8, trials=25, H=50, seed=0),
            {"h_unit": "bit_flip", "operators": ["flip_bit(i)"], "default_cost": 1.0},
        ),
        (partial(run_grid_demo, size=5, trials=10, H=200, seed=42), {"h_unit": "step"}),
        (
            partial(run_hanoi_demo, n_disks=3, trials=10, H=5000, seed=42),
            {
                "h_unit": "move",
                "shared_operator_semantics": "legal_hanoi_move",
                "agent_mean_censored": 7.0,
            },
        ),
        (
            partial(run_grn_demo, n_genes=8, trials=20, H=500, seed=42),
            {
                "h_unit": "gene_update",
                "shared_operator_semantics": "async_boolean_network_rule_update",
            },
        ),
    ]

    for run_demo, expected in cases:
        out = run_demo()
        _assert_expected_semantics(out, expected)
        _assert_common_demo_metrics(out, exact_supported=True)


def test_sampling_only_demos_report_problem_semantics():
    cases = [
        (
            partial(run_synthesis_demo, max_len=5, trials=25, H=200, seed=0),
            {
                "h_unit": "program_eval",
                "state_prefix": "syntactically valid bounded-length RPN programs",
            },
        ),
        (
            partial(run_chemotaxis_demo, size=5, noise_sigma=0.1, trials=10, H=200, seed=42),
            {"h_unit": "step", "shared_operator_semantics": "4-neighbor-step"},
        ),
    ]

    for run_demo, expected in cases:
        out = run_demo()
        _assert_expected_semantics(out, expected)
        _assert_common_demo_metrics(out, exact_supported=False)


def test_demo_chemotaxis_no_noise():
    out = run_chemotaxis_demo(size=5, noise_sigma=0.0, trials=10, H=200, seed=42)
    assert out["domain"]["exact_supported"] is True
    assert out["solve_rates"]["agent"] == 1.0
    assert math.isfinite(out["exact"]["K"]["restricted_mean_at_H_exact"])


def test_demo_compositional_additivity():
    out = run_compositional_demo(
        n_sort=5,
        n_bits=6,
        trials=200,
        H_sort=200,
        H_bits=100,
        seed=42,
    )
    assert "stages" in out
    assert "composite" in out
    assert "additivity" in out
    assert out["stages"]["sorting"]["domain"]["exact_supported"] is True
    assert out["stages"]["bitstring"]["domain"]["exact_supported"] is True
    assert out["additivity"]["delta"] < 0.3


def test_paper_demos_reproduce_reported_values():
    amoeba = run_paper_amoeba_demo()
    k_low, k_high = amoeba["derived"]["K_range"]
    assert 2.17 <= k_low <= 2.20
    assert 2.29 <= k_high <= 2.31

    planarian = run_paper_planarian_demo()
    k_val = planarian["derived"]["K"]
    assert 20.9 <= k_val <= 21.4
