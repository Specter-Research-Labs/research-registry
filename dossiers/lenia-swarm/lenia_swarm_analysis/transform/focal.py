from __future__ import annotations

from statistics import mean
from typing import Any

BASELINE_METRIC_KEYS = (
    "score",
    "centerVelocity",
    "displacement",
    "pathLength",
    "finalMass",
    "occupancyMean",
    "varianceMean",
    "gyration",
)

RESPONSE_METRIC_KEYS = (
    "postPerturbationDivergence",
    "returnToBaselineScore",
    "redirectedBehaviorScore",
    "massRetentionRatio",
    "displacementRatio",
    "occupancyDelta",
    "varianceDelta",
    "score",
    "centerVelocity",
)


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    if not values:
        return None
    return float(mean(values))


def _metric_summary(
    rows: list[dict[str, Any]],
    *,
    metric_keys: tuple[str, ...],
) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in metric_keys:
        value = _mean_metric(rows, key)
        if value is not None:
            summary[key] = value
    return summary


def _condition_summary(
    *,
    environment_label: str,
    perturbation_label: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        raise SystemExit(
            f"empty focal condition rows for {environment_label}/{perturbation_label}"
        )
    divergence_values = [
        float(row["postPerturbationDivergence"])
        for row in rows
        if isinstance(row.get("postPerturbationDivergence"), (int, float))
    ]
    return_to_baseline_values = [
        float(row["returnToBaselineScore"])
        for row in rows
        if isinstance(row.get("returnToBaselineScore"), (int, float))
    ]
    if not divergence_values or not return_to_baseline_values:
        raise SystemExit(
            "missing intervention metrics for focal condition "
            f"{environment_label}/{perturbation_label}"
        )
    return {
        "environmentLabel": environment_label,
        "perturbationLabel": perturbation_label,
        "rowCount": len(rows),
        "meanMetrics": _metric_summary(rows, metric_keys=RESPONSE_METRIC_KEYS),
        "meanFragilityScore": float(mean(divergence_values)),
        "maxFragilityScore": float(max(divergence_values)),
        "meanRobustnessScore": float(mean(return_to_baseline_values)),
        "minRobustnessScore": float(min(return_to_baseline_values)),
    }


def _baseline_summary(*, environment_label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise SystemExit(f"missing baseline rows for environment {environment_label}")
    return {
        "environmentLabel": environment_label,
        "rowCount": len(rows),
        "meanMetrics": _metric_summary(rows, metric_keys=BASELINE_METRIC_KEYS),
    }
