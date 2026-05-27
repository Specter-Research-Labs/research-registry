from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "median": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "min": _finite_or_none(float(np.min(array))),
        "mean": _finite_or_none(float(np.mean(array))),
        "median": _finite_or_none(float(np.median(array))),
        "p95": _finite_or_none(float(np.quantile(array, 0.95))),
        "p99": _finite_or_none(float(np.quantile(array, 0.99))),
        "max": _finite_or_none(float(np.max(array))),
    }


def _source_class(bundle: str) -> str:
    if "/flow-map-elites/" in bundle:
        return "flow-map-elites"
    if "/no-food-256x2c-" in bundle:
        return "no-food-256x2c"
    if "/paper-no-food-256x2c-" in bundle:
        return "paper-no-food-256x2c"
    return "other"


def _scale_value(scale: dict[str, Any], key: str) -> float:
    value = scale.get(key)
    if value is None:
        return 0.0
    return float(value)


def _control_state_closure(scale: dict[str, Any]) -> float | None:
    if "controlState" in scale:
        return float(scale["controlState"])
    best_control = scale.get("bestControl")
    if isinstance(best_control, dict):
        return float(best_control["endpointTransportedStateDistance"])
    return None


def _row_scales(row: dict[str, Any]) -> list[dict[str, Any]]:
    scales = row.get("scales")
    if not isinstance(scales, list) or any(not isinstance(scale, dict) for scale in scales):
        raise SystemExit("transport scale report group is missing scales[]")
    return scales


def _group_summary(row: dict[str, Any]) -> dict[str, Any]:
    scales = _row_scales(row)
    state_deltas = [_scale_value(scale, "deltaStateClosure") for scale in scales]
    ratio_deltas = [_scale_value(scale, "deltaRatio") for scale in scales]
    relative_state_surpluses = [
        delta / max(control_state, 1e-12)
        if (control_state := _control_state_closure(scale)) is not None
        else 0.0
        for delta, scale in zip(state_deltas, scales, strict=True)
    ]
    positive_state = [value for value in state_deltas if value > 0.0]
    positive_ratio = [value for value in ratio_deltas if value > 0.0]
    first_loop = scales[0].get("topLoop")
    bundle = str(first_loop.get("bundle")) if isinstance(first_loop, dict) else ""
    return {
        "controlGroup": str(row["controlGroup"]),
        "bundle": bundle,
        "sourceClass": _source_class(bundle),
        "scaleCount": len(scales),
        "positiveStateScales": int(sum(value > 0.0 for value in state_deltas)),
        "positiveRatioScales": int(sum(value > 0.0 for value in ratio_deltas)),
        "positiveBothScales": int(
            sum(
                state > 0.0 and ratio > 0.0
                for state, ratio in zip(state_deltas, ratio_deltas, strict=True)
            )
        ),
        "minStateDelta": min(state_deltas) if state_deltas else None,
        "maxStateDelta": max(state_deltas) if state_deltas else None,
        "meanStateDelta": float(np.mean(state_deltas)) if state_deltas else None,
        "meanPositiveStateDelta": float(np.mean(positive_state)) if positive_state else 0.0,
        "minRatioDelta": min(ratio_deltas) if ratio_deltas else None,
        "maxRatioDelta": max(ratio_deltas) if ratio_deltas else None,
        "meanRatioDelta": float(np.mean(ratio_deltas)) if ratio_deltas else None,
        "meanPositiveRatioDelta": float(np.mean(positive_ratio)) if positive_ratio else 0.0,
        "meanRelativeStateSurplus": float(np.mean(relative_state_surpluses))
        if relative_state_surpluses
        else None,
        "scales": [
            {
                "scale": str(scale.get("scale")),
                "deltaStateClosure": _scale_value(scale, "deltaStateClosure"),
                "deltaPhenotypeClosure": _scale_value(scale, "deltaPhenotypeClosure"),
                "deltaRatio": _scale_value(scale, "deltaRatio"),
                "loopStateClosure": float(scale["topLoop"]["endpointTransportedStateDistance"])
                if isinstance(scale.get("topLoop"), dict)
                else None,
                "controlStateClosure": _control_state_closure(scale),
                "loopRatio": float(scale["topLoop"]["transportToPhenotypeRatio"])
                if isinstance(scale.get("topLoop"), dict)
                else None,
                "controlRatio": float(scale["bestControl"]["transportToPhenotypeRatio"])
                if isinstance(scale.get("bestControl"), dict)
                else None,
            }
            for scale in scales
        ],
    }


def _scale_stats(groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows_by_scale: dict[str, dict[str, list[float]]] = {}
    for group in groups:
        for scale in group["scales"]:
            scale_name = str(scale["scale"])
            rows_by_scale.setdefault(
                scale_name,
                {
                    "deltaStateClosure": [],
                    "deltaPhenotypeClosure": [],
                    "deltaRatio": [],
                    "loopStateClosure": [],
                    "controlStateClosure": [],
                    "loopRatio": [],
                    "controlRatio": [],
                },
            )
            for key in rows_by_scale[scale_name]:
                value = scale.get(key)
                if value is not None:
                    rows_by_scale[scale_name][key].append(float(value))
    stats: dict[str, Any] = {}
    for scale_name, values_by_key in sorted(rows_by_scale.items()):
        positive_state = [
            value > 0.0 for value in values_by_key.get("deltaStateClosure", [])
        ]
        positive_ratio = [value > 0.0 for value in values_by_key.get("deltaRatio", [])]
        stats[scale_name] = {
            key: _distribution(values)
            for key, values in sorted(values_by_key.items())
        }
        stats[scale_name]["positiveDeltaState"] = int(sum(positive_state))
        stats[scale_name]["positiveDeltaRatio"] = int(sum(positive_ratio))
        stats[scale_name]["positiveBoth"] = int(
            sum(
                state and ratio
                for state, ratio in zip(positive_state, positive_ratio, strict=True)
            )
        )
        stats[scale_name]["count"] = len(positive_state)
    return stats


def _normal_survival(observed: int, *, count: int, probability: float) -> float | None:
    if probability <= 0.0:
        return 0.0 if observed > 0 else 1.0
    if probability >= 1.0:
        return 1.0 if observed <= count else 0.0
    mean = count * probability
    variance = count * probability * (1.0 - probability)
    if variance <= 0.0:
        return None
    z = (observed - 0.5 - mean) / math.sqrt(variance)
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _all_scale_null(
    *,
    groups: list[dict[str, Any]],
    scale_stats: dict[str, Any],
    field: str,
    observed: int,
) -> dict[str, Any]:
    probabilities = [
        float(row[field]) / max(float(row["count"]), 1.0)
        for _, row in sorted(scale_stats.items())
    ]
    probability = float(np.prod(probabilities)) if probabilities else 0.0
    count = len(groups)
    return {
        "observed": observed,
        "expectedIndependentScaleMarginals": count * probability,
        "scaleMarginalProbabilities": probabilities,
        "normalApproxSurvivalP": _normal_survival(
            observed,
            count=count,
            probability=probability,
        ),
    }


def _permutation_alignment_null(
    *,
    groups: list[dict[str, Any]],
    metric: str,
    permutations: int,
    seed: int,
) -> dict[str, Any]:
    if not groups:
        return {"permutations": permutations, "observed": 0, "mean": None, "pGeObserved": None}
    scale_names = sorted({str(scale["scale"]) for group in groups for scale in group["scales"]})
    observed_flags: dict[str, np.ndarray] = {}
    for scale_name in scale_names:
        flags = []
        for group in groups:
            scale = next(
                (row for row in group["scales"] if str(row["scale"]) == scale_name),
                None,
            )
            if scale is None:
                flags.append(False)
                continue
            if metric == "state":
                flags.append(float(scale["deltaStateClosure"]) > 0.0)
            elif metric == "ratio":
                flags.append(float(scale["deltaRatio"]) > 0.0)
            elif metric == "both":
                flags.append(
                    float(scale["deltaStateClosure"]) > 0.0
                    and float(scale["deltaRatio"]) > 0.0
                )
            else:
                raise ValueError(f"unknown metric: {metric}")
        observed_flags[scale_name] = np.asarray(flags, dtype=bool)
    observed = int(
        np.count_nonzero(np.logical_and.reduce(list(observed_flags.values())))
    )
    rng = np.random.default_rng(seed)
    draws = np.zeros(permutations, dtype=np.int64)
    arrays = list(observed_flags.values())
    for index in range(permutations):
        shuffled = [rng.permutation(array) for array in arrays]
        draws[index] = int(np.count_nonzero(np.logical_and.reduce(shuffled)))
    return {
        "metric": metric,
        "permutations": permutations,
        "observed": observed,
        "mean": float(np.mean(draws)),
        "p95": float(np.quantile(draws, 0.95)),
        "p99": float(np.quantile(draws, 0.99)),
        "max": int(np.max(draws)),
        "pGeObserved": float((np.count_nonzero(draws >= observed) + 1) / (permutations + 1)),
    }


def build_transport_confidence_report(
    scale_report_path: Path,
    *,
    permutations: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    report = _read_json(scale_report_path)
    raw_groups = report.get("groups")
    if not isinstance(raw_groups, list) or any(not isinstance(row, dict) for row in raw_groups):
        raise SystemExit(f"{scale_report_path}: report is missing groups[]")
    groups = [_group_summary(row) for row in raw_groups]
    scale_stats = _scale_stats(groups)
    source_class_counts = Counter(group["sourceClass"] for group in groups)

    strict = [
        group
        for group in groups
        if group["positiveStateScales"] == group["scaleCount"]
        and group["positiveRatioScales"] == group["scaleCount"]
    ]
    top_strict = sorted(
        strict,
        key=lambda row: (
            -float(row["meanRelativeStateSurplus"] or 0.0),
            -float(row["meanPositiveStateDelta"]),
            -float(row["meanPositiveRatioDelta"]),
            row["controlGroup"],
        ),
    )
    top_state = sorted(
        groups,
        key=lambda row: (
            -int(row["positiveStateScales"]),
            -float(row["meanPositiveStateDelta"]),
            row["controlGroup"],
        ),
    )
    top_ratio = sorted(
        groups,
        key=lambda row: (
            -int(row["positiveRatioScales"]),
            -float(row["meanPositiveRatioDelta"]),
            row["controlGroup"],
        ),
    )

    state_all = int(sum(group["positiveStateScales"] == group["scaleCount"] for group in groups))
    ratio_all = int(sum(group["positiveRatioScales"] == group["scaleCount"] for group in groups))
    both_all = len(strict)
    null_checks = {
        "independentScaleMarginals": {
            "stateAllScales": _all_scale_null(
                groups=groups,
                scale_stats=scale_stats,
                field="positiveDeltaState",
                observed=state_all,
            ),
            "ratioAllScales": _all_scale_null(
                groups=groups,
                scale_stats=scale_stats,
                field="positiveDeltaRatio",
                observed=ratio_all,
            ),
            "bothAllScales": _all_scale_null(
                groups=groups,
                scale_stats=scale_stats,
                field="positiveBoth",
                observed=both_all,
            ),
        },
        "permutedScaleAlignment": {
            "stateAllScales": _permutation_alignment_null(
                groups=groups,
                metric="state",
                permutations=permutations,
                seed=seed,
            ),
            "ratioAllScales": _permutation_alignment_null(
                groups=groups,
                metric="ratio",
                permutations=permutations,
                seed=seed + 1,
            ),
            "bothAllScales": _permutation_alignment_null(
                groups=groups,
                metric="both",
                permutations=permutations,
                seed=seed + 2,
            ),
        },
    }

    return {
        "packetKind": "transport_confidence_report_v1",
        "sourceReport": str(scale_report_path),
        "groupCount": len(groups),
        "scaleCount": int(report.get("scaleCount") or len(scale_stats)),
        "strictDefinition": (
            "positive deltaStateClosure and positive deltaRatio at every scale"
        ),
        "strictCount": both_all,
        "sourceClassCounts": dict(sorted(source_class_counts.items())),
        "strictSourceClassCounts": dict(
            sorted(Counter(group["sourceClass"] for group in strict).items())
        ),
        "scaleStats": scale_stats,
        "nullChecks": null_checks,
        "topStrictBoth": top_strict[:32],
        "topRobustState": top_state[:32],
        "topRobustRatio": top_ratio[:32],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build holonomy/transport confidence checks from a transport scale report."
    )
    parser.add_argument("--scale-report", required=True, help="Path to transport-scale-report.json")
    parser.add_argument("--output", help="Output path")
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    scale_report_path = Path(args.scale_report).expanduser().resolve()
    packet = build_transport_confidence_report(
        scale_report_path,
        permutations=int(args.permutations),
        seed=int(args.seed),
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else scale_report_path.parent / "transport-confidence-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport confidence report:"
        f" groups={packet['groupCount']}"
        f" strict={packet['strictCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
