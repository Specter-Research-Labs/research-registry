from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean


def tactic_nonempty(tactic: str) -> bool:
    return bool(tactic.strip())


def tactic_contains_sorry(tactic: str) -> bool:
    lower = tactic.lower()
    return "sorry" in lower or "admit" in lower


def tactic_valid(tactic: str, *, max_chars: int) -> bool:
    value = tactic.strip()
    if not value:
        return False
    if len(value) > max_chars:
        return False
    if tactic_contains_sorry(value):
        return False
    if value.startswith("```"):
        return False
    return True


@dataclass(frozen=True)
class AggregateMetrics:
    attempts_total: int
    generation_error_count: int
    nonempty_count: int
    valid_count: int
    contains_sorry_count: int
    latency_ms_mean: float
    latency_ms_p50: int
    latency_ms_p95: int

    def as_dict(self) -> dict[str, float | int]:
        total = max(self.attempts_total, 1)
        return {
            "attempts_total": self.attempts_total,
            "generation_error_count": self.generation_error_count,
            "generation_error_rate": self.generation_error_count / total,
            "nonempty_count": self.nonempty_count,
            "nonempty_rate": self.nonempty_count / total,
            "valid_count": self.valid_count,
            "valid_rate": self.valid_count / total,
            "contains_sorry_count": self.contains_sorry_count,
            "contains_sorry_rate": self.contains_sorry_count / total,
            "latency_ms_mean": self.latency_ms_mean,
            "latency_ms_p50": self.latency_ms_p50,
            "latency_ms_p95": self.latency_ms_p95,
        }


def _percentile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    idx = int(round((len(sorted_values) - 1) * q))
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def aggregate(
    *,
    generation_error_count: int,
    nonempty_count: int,
    valid_count: int,
    contains_sorry_count: int,
    latencies_ms: list[int],
) -> AggregateMetrics:
    sorted_latencies = sorted(latencies_ms)
    return AggregateMetrics(
        attempts_total=len(latencies_ms),
        generation_error_count=generation_error_count,
        nonempty_count=nonempty_count,
        valid_count=valid_count,
        contains_sorry_count=contains_sorry_count,
        latency_ms_mean=mean(latencies_ms) if latencies_ms else 0.0,
        latency_ms_p50=_percentile(sorted_latencies, 0.5),
        latency_ms_p95=_percentile(sorted_latencies, 0.95),
    )


def bounded_pass_at_k_values(*, configured_values: list[int], samples_per_item: int) -> list[int]:
    if samples_per_item <= 0:
        raise ValueError("samples_per_item must be > 0")
    if not configured_values:
        raise ValueError("configured_values must not be empty")
    bounded: set[int] = set()
    for value in configured_values:
        if value <= 0:
            raise ValueError("pass@k values must be > 0")
        bounded.add(min(value, samples_per_item))
    return sorted(bounded)


def aggregate_verification_pass_at_k(
    *,
    verification_success_by_item: list[list[bool]],
    ks: list[int],
) -> dict[int, dict[str, int | float]]:
    if not ks:
        raise ValueError("ks must not be empty")
    item_count = len(verification_success_by_item)
    denominator = max(item_count, 1)
    metrics: dict[int, dict[str, int | float]] = {}
    for k in ks:
        if k <= 0:
            raise ValueError("k must be > 0")
        pass_count = sum(1 for per_item in verification_success_by_item if any(per_item[:k]))
        metrics[k] = {
            "success_count": pass_count,
            "success_rate": pass_count / denominator,
        }
    return metrics


def _validate_bootstrap_params(*, iters: int, confidence_level: float) -> None:
    if iters < 0:
        raise ValueError("iters must be >= 0")
    if confidence_level <= 0.0 or confidence_level >= 1.0:
        raise ValueError("confidence_level must be in (0,1)")


def _percentile_float(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]
    idx = q * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def bootstrap_rate_confidence_interval(
    *,
    outcomes: list[bool],
    seed: int,
    iters: int,
    confidence_level: float,
) -> dict[str, float] | None:
    if not outcomes:
        return None
    _validate_bootstrap_params(iters=iters, confidence_level=confidence_level)
    sample_size = len(outcomes)
    point_rate = sum(1 for value in outcomes if value) / sample_size
    if iters == 0:
        return {"low": point_rate, "high": point_rate}

    values = [1 if value else 0 for value in outcomes]
    rnd = random.Random(seed)
    rates: list[float] = []
    for _ in range(iters):
        success_count = 0
        for _ in range(sample_size):
            success_count += values[rnd.randrange(sample_size)]
        rates.append(success_count / sample_size)
    rates.sort()
    alpha = 1.0 - confidence_level
    return {
        "low": _percentile_float(rates, alpha / 2.0),
        "high": _percentile_float(rates, 1.0 - alpha / 2.0),
    }


def aggregate_verification_pass_at_k_confidence_intervals(
    *,
    verification_success_by_item: list[list[bool]],
    ks: list[int],
    seed: int,
    iters: int,
    confidence_level: float,
) -> dict[int, dict[str, float] | None]:
    if not ks:
        raise ValueError("ks must not be empty")
    metrics: dict[int, dict[str, float] | None] = {}
    for k in ks:
        if k <= 0:
            raise ValueError("k must be > 0")
        outcomes = [any(per_item[:k]) for per_item in verification_success_by_item]
        metrics[k] = bootstrap_rate_confidence_interval(
            outcomes=outcomes,
            seed=seed + k * 1_000_003,
            iters=iters,
            confidence_level=confidence_level,
        )
    return metrics
