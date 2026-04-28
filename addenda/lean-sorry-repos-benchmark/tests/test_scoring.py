from __future__ import annotations

import pytest

from lean_sorry_repos_benchmark.scoring import (
    aggregate_verification_pass_at_k,
    aggregate_verification_pass_at_k_confidence_intervals,
    bootstrap_rate_confidence_interval,
    bounded_pass_at_k_values,
)


def test_bounded_pass_at_k_values_clamps_and_sorts() -> None:
    values = bounded_pass_at_k_values(configured_values=[10, 1, 5, 5], samples_per_item=3)
    assert values == [1, 3]


def test_aggregate_verification_pass_at_k_uses_item_level_any_success() -> None:
    metrics = aggregate_verification_pass_at_k(
        verification_success_by_item=[
            [False, False, True],
            [True, False, False],
            [False, False, False],
        ],
        ks=[1, 2, 3],
    )
    assert metrics[1]["success_count"] == 1
    assert metrics[2]["success_count"] == 1
    assert metrics[3]["success_count"] == 2
    assert metrics[1]["success_rate"] == pytest.approx(1 / 3)
    assert metrics[2]["success_rate"] == pytest.approx(1 / 3)
    assert metrics[3]["success_rate"] == pytest.approx(2 / 3)


def test_bootstrap_rate_confidence_interval_is_deterministic() -> None:
    outcomes = [True, False, True, True, False, False, True, False]
    ci_a = bootstrap_rate_confidence_interval(
        outcomes=outcomes,
        seed=17,
        iters=200,
        confidence_level=0.95,
    )
    ci_b = bootstrap_rate_confidence_interval(
        outcomes=outcomes,
        seed=17,
        iters=200,
        confidence_level=0.95,
    )
    assert ci_a == ci_b
    assert ci_a is not None
    assert 0.0 <= ci_a["low"] <= ci_a["high"] <= 1.0


def test_pass_at_k_confidence_intervals_support_zero_iters() -> None:
    ci = aggregate_verification_pass_at_k_confidence_intervals(
        verification_success_by_item=[
            [False, False, True],
            [True, False, False],
            [False, False, False],
        ],
        ks=[1, 3],
        seed=11,
        iters=0,
        confidence_level=0.95,
    )
    assert ci[1] is not None
    assert ci[3] is not None
    assert ci[1]["low"] == pytest.approx(1 / 3)
    assert ci[1]["high"] == pytest.approx(1 / 3)
    assert ci[3]["low"] == pytest.approx(2 / 3)
    assert ci[3]["high"] == pytest.approx(2 / 3)
