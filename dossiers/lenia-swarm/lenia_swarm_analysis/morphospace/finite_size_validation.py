from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MOTION_DISPLACEMENT_MIN = 5.0
MOTION_EFFICIENCY_MIN = 0.25
COMPACT_COMPONENT_COUNT_MAX = 4.0
COMPACT_LARGEST_COMPONENT_MIN = 0.95


def result_jsonl_path(path: Path) -> Path:
    if path.is_dir():
        return path / "results.jsonl"
    return path


def read_result_jsonl_by_seed(path: Path) -> dict[int, dict[str, Any]]:
    results_path = result_jsonl_path(path)
    rows: dict[int, dict[str, Any]] = {}
    with results_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{results_path}:{line_number}: expected a JSON object")
            seed = row.get("seed")
            if not isinstance(seed, int):
                raise ValueError(f"{results_path}:{line_number}: missing integer seed")
            rows[seed] = row
    return rows


def classify_result(row: dict[str, Any]) -> dict[str, bool]:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("result row missing metrics object")
    displacement = _number(metrics.get("displacement"))
    efficiency = _movement_efficiency(metrics)
    component_count = _number(metrics.get("component_count"))
    largest_component_fraction = _number(metrics.get("largest_component_fraction"))
    moving = (
        displacement is not None
        and displacement >= MOTION_DISPLACEMENT_MIN
        and efficiency is not None
        and efficiency >= MOTION_EFFICIENCY_MIN
    )
    compact_connected = (
        component_count is not None
        and component_count <= COMPACT_COMPONENT_COUNT_MAX
        and largest_component_fraction is not None
        and largest_component_fraction >= COMPACT_LARGEST_COMPONENT_MIN
    )
    return {
        "moving": moving,
        "compactConnected": compact_connected,
        "compactMoving": moving and compact_connected,
    }


def build_finite_size_validation_packet(
    runs: dict[str, Path],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if len(runs) < 2:
        raise ValueError("finite-size validation requires at least two runs")

    result_sets = {
        label: read_result_jsonl_by_seed(path)
        for label, path in runs.items()
    }
    labels = list(result_sets)
    all_seeds = sorted({seed for rows in result_sets.values() for seed in rows})
    common_seeds = [
        seed
        for seed in all_seeds
        if all(seed in rows for rows in result_sets.values())
    ]

    rows = [
        _seed_packet(seed, labels, result_sets)
        for seed in common_seeds
    ]
    per_run = {
        label: _run_summary(rows, label)
        for label in labels
    }
    pairwise = {
        f"{left}->{right}": _pairwise_summary(rows, left, right)
        for left, right in zip(labels, labels[1:], strict=False)
    }
    stable_mover_seeds = [
        row["seed"]
        for row in rows
        if all(row["classes"][label]["moving"] for label in labels)
    ]
    stable_compact_mover_seeds = [
        row["seed"]
        for row in rows
        if all(row["classes"][label]["compactMoving"] for label in labels)
    ]
    genotype_hash_mismatches = [
        row["seed"]
        for row in rows
        if len(set(row["genotypeHash12"].values())) > 1
    ]

    return {
        "packetKind": "fl2c20_motion_finite_size_validation_v1",
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "runLabels": labels,
        "seedCount": len(common_seeds),
        "missingSeedCount": len(all_seeds) - len(common_seeds),
        "classificationThresholds": {
            "moving": {
                "displacementMin": MOTION_DISPLACEMENT_MIN,
                "movementEfficiencyMin": MOTION_EFFICIENCY_MIN,
            },
            "compactConnected": {
                "componentCountMax": COMPACT_COMPONENT_COUNT_MAX,
                "largestComponentFractionMin": COMPACT_LARGEST_COMPONENT_MIN,
            },
        },
        "summary": {
            "perRun": per_run,
            "pairwise": pairwise,
            "stableMoverSeeds": stable_mover_seeds,
            "stableMoverCount": len(stable_mover_seeds),
            "stableCompactMoverSeeds": stable_compact_mover_seeds,
            "stableCompactMoverCount": len(stable_compact_mover_seeds),
            "genotypeHashMismatchSeeds": genotype_hash_mismatches,
            "genotypeHashMismatchCount": len(genotype_hash_mismatches),
        },
        "rows": rows,
    }


def _seed_packet(
    seed: int,
    labels: list[str],
    result_sets: dict[str, dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "seed": seed,
        "classes": {
            label: classify_result(result_sets[label][seed])
            for label in labels
        },
        "metrics": {
            label: _metric_subset(result_sets[label][seed])
            for label in labels
        },
        "genotypeHash12": {
            label: _genotype_hash12(result_sets[label][seed])
            for label in labels
        },
    }


def _run_summary(rows: list[dict[str, Any]], label: str) -> dict[str, int]:
    return {
        "moving": sum(1 for row in rows if row["classes"][label]["moving"]),
        "compactConnected": sum(
            1 for row in rows if row["classes"][label]["compactConnected"]
        ),
        "compactMoving": sum(
            1 for row in rows if row["classes"][label]["compactMoving"]
        ),
    }


def _pairwise_summary(rows: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    left_moving = sum(1 for row in rows if row["classes"][left]["moving"])
    left_compact_moving = sum(
        1 for row in rows if row["classes"][left]["compactMoving"]
    )
    moving_survived = [
        row["seed"]
        for row in rows
        if row["classes"][left]["moving"] and row["classes"][right]["moving"]
    ]
    compact_moving_survived = [
        row["seed"]
        for row in rows
        if row["classes"][left]["compactMoving"]
        and row["classes"][right]["compactMoving"]
    ]
    return {
        "movingSurvivalCount": len(moving_survived),
        "movingSurvivalFraction": _ratio(len(moving_survived), left_moving),
        "movingSurvivedSeeds": moving_survived,
        "compactMovingSurvivalCount": len(compact_moving_survived),
        "compactMovingSurvivalFraction": _ratio(
            len(compact_moving_survived),
            left_compact_moving,
        ),
        "compactMovingSurvivedSeeds": compact_moving_survived,
        "metricRatios": _pairwise_metric_ratios(rows, left, right),
    }


def _pairwise_metric_ratios(
    rows: list[dict[str, Any]],
    left: str,
    right: str,
) -> dict[str, dict[str, float]]:
    ratios: dict[str, list[float]] = {
        "displacement": [],
        "pathLength": [],
        "gyration": [],
        "occupancyMean": [],
    }
    for row in rows:
        left_metrics = row["metrics"][left]
        right_metrics = row["metrics"][right]
        for key, values in ratios.items():
            value = _ratio(right_metrics.get(key), left_metrics.get(key))
            if value is not None:
                values.append(value)
    return {
        key: _number_summary(values)
        for key, values in ratios.items()
        if values
    }


def _metric_subset(row: dict[str, Any]) -> dict[str, float | int | None]:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    return {
        "score": _number(row.get("score")),
        "displacement": _number(metrics.get("displacement")),
        "pathLength": _number(metrics.get("path_length")),
        "movementEfficiency": _movement_efficiency(metrics),
        "componentCount": _number(metrics.get("component_count")),
        "largestComponentFraction": _number(metrics.get("largest_component_fraction")),
        "gyration": _number(metrics.get("gyration")),
        "momentAnisotropy": _number(metrics.get("moment_anisotropy")),
        "occupancyMean": _number(metrics.get("occupancy_mean")),
    }


def _genotype_hash12(row: dict[str, Any]) -> str | None:
    bundle = row.get("descriptor_bundle")
    if not isinstance(bundle, dict):
        return None
    genotype = bundle.get("genotype")
    if not isinstance(genotype, dict):
        return None
    value = genotype.get("hash12")
    return value if isinstance(value, str) else None


def _movement_efficiency(metrics: dict[str, Any]) -> float | int | None:
    stored = _number(metrics.get("movement_efficiency"))
    if stored is not None:
        return stored
    return _ratio(metrics.get("displacement"), metrics.get("path_length"))


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


def _ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _number(numerator)
    denominator_value = _number(denominator)
    if numerator_value is None or denominator_value in (None, 0):
        return None
    return float(numerator_value) / float(denominator_value)


def _number_summary(values: list[float]) -> dict[str, float]:
    sorted_values = sorted(values)
    count = len(sorted_values)
    return {
        "count": count,
        "min": sorted_values[0],
        "mean": sum(sorted_values) / count,
        "median": sorted_values[count // 2],
        "max": sorted_values[-1],
    }
