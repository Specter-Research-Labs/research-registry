from __future__ import annotations

import math


def k_log10_ratio(*, tau_blind: float, tau_agent: float) -> float:
    """Compute paper K = log10(tau_blind / tau_agent).

    Both taus must be positive costs expressed in the same units.
    """

    tb = float(tau_blind)
    ta = float(tau_agent)
    if not (tb > 0.0) or not (ta > 0.0):
        raise ValueError(
            "tau_blind and tau_agent must be positive; "
            f"got tau_blind={tau_blind!r} tau_agent={tau_agent!r}"
        )
    return math.log10(tb / ta)

