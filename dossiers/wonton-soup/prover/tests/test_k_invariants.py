import pytest

from prover.k import k_log10_ratio


def test_k_log10_ratio_invariants():
    assert abs(k_log10_ratio(tau_blind=123.0, tau_agent=123.0)) < 1e-12
    assert abs(k_log10_ratio(tau_blind=10.0, tau_agent=1.0) - 1.0) < 1e-12

    scaled = k_log10_ratio(tau_blind=100.0, tau_agent=4.0)
    assert abs(scaled - k_log10_ratio(tau_blind=1000.0, tau_agent=40.0)) < 1e-12

    k1 = k_log10_ratio(tau_blind=100.0, tau_agent=10.0)
    k2 = k_log10_ratio(tau_blind=1000.0, tau_agent=1.0)
    kt = k_log10_ratio(tau_blind=100.0 * 1000.0, tau_agent=10.0 * 1.0)
    assert abs((k1 + k2) - kt) < 1e-12


@pytest.mark.parametrize(
    ("tau_blind", "tau_agent"),
    [
        (0.0, 1.0),
        (1.0, 0.0),
    ],
)
def test_k_rejects_nonpositive_tau(tau_blind: float, tau_agent: float):
    with pytest.raises(ValueError, match="must be positive"):
        k_log10_ratio(tau_blind=tau_blind, tau_agent=tau_agent)
