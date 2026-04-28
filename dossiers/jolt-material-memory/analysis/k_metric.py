from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BootstrapCI:
    median: float
    low: float
    high: float


def k_score(tau_blind: float, tau_agent: float) -> float:
    if tau_blind <= 0 or tau_agent <= 0:
        raise ValueError("tau values must be positive")
    return math.log10(tau_blind / tau_agent)


def bootstrap_ci(values: np.ndarray, *, trials: int = 2000, alpha: float = 0.05) -> BootstrapCI:
    if values.size == 0:
        raise ValueError("cannot bootstrap an empty array")
    rng = np.random.default_rng(1337)
    samples = np.empty(trials, dtype=float)
    n = values.size
    for i in range(trials):
        draws = rng.choice(values, size=n, replace=True)
        samples[i] = float(np.median(draws))
    low = float(np.quantile(samples, alpha / 2.0))
    high = float(np.quantile(samples, 1.0 - alpha / 2.0))
    return BootstrapCI(median=float(np.median(values)), low=low, high=high)
