from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.morphospace.track1_spec import (
    TRACK1_FAMILIES,
    track1_family_metadata,
)

METRIC_KEYS = (
    "displacement",
    "path_length",
    "center_velocity",
    "speed_mean",
    "largest_component_fraction",
    "component_count",
    "gyration",
    "occupancy_mean",
    "moment_density",
    "moment_anisotropy",
    "mass_mean",
)


def build_track1_raw_summary_packet(
    *,
    run_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    buckets = {family["familyKey"]: _empty_bucket() for family in TRACK1_FAMILIES.values()}
    overall = _empty_bucket()
    anomalies: list[dict[str, Any]] = []
    complete_run_count = 0

    for run_id, run_dir, summary in _completed_summary_rows(run_root):
        complete_run_count += 1
        expected_count = int(summary["resultsCount"])
        actual_count = _count_lines(run_dir / "results.jsonl")
        if actual_count != expected_count:
            anomalies.append(
                {
                    "runId": run_id,
                    "summaryResultsCount": expected_count,
                    "actualResultLines": actual_count,
                    "usedResultLines": expected_count,
                }
            )
        family = _family_metadata(run_id)
        targets = [overall, buckets[family["familyKey"]]]
        for bucket in targets:
            bucket["runs"].append(
                {
                    "runId": run_id,
                    "durationSeconds": summary.get("durationSeconds"),
                    "seedStart": summary.get("seedStart"),
                    "actualResultLines": actual_count,
                }
            )
        with (run_dir / "results.jsonl").open(encoding="utf-8") as handle:
            for line in islice(handle, expected_count):
                if line.strip():
                    _record_result_row(
                        json.loads(line),
                        run_id=run_id,
                        family_key=family["familyKey"],
                        buckets=targets,
                    )

    running_runs = []
    for run_dir in sorted(run_root.glob("track1b-*-8192-s*")):
        if not run_dir.is_dir() or (run_dir / "summary.json").exists():
            continue
        result_path = run_dir / "results.jsonl"
        running_runs.append(
            {
                "runId": run_dir.name,
                "currentResultLines": _count_lines(result_path) if result_path.exists() else 0,
            }
        )

    return {
        "packetKind": "track1_partial_raw_harvest_summary_v1",
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "completedRunCount": complete_run_count,
        "completedResultCount": int(overall["resultCount"]),
        "runningRuns": running_runs,
        "lineCountAnomalies": anomalies,
        "families": {key: _finish_bucket(bucket) for key, bucket in buckets.items()},
        "overall": _finish_bucket(overall),
        "thresholds": {
            "moving": {"displacementMin": 5.0, "movementEfficiencyMin": 0.25},
            "coherentMover": {
                "displacementMin": 10.0,
                "movementEfficiencyMin": 0.25,
                "pathLengthMin": 10.0,
            },
            "compactConnected": {
                "componentCountMax": 4,
                "largestComponentFractionMin": 0.95,
            },
            "compactMoving": "moving and compactConnected",
        },
        "sourceAlgorithms": {
            family["familyKey"]: family["sourceAlgorithm"]
            for family in TRACK1_FAMILIES.values()
        },
        "notes": [
            (
                "Computed directly from completed raw Track1b results.jsonl chunks; "
                "running chunks are excluded."
            ),
            (
                "When a complete run has extra appended rows, this packet uses the "
                "summary resultsCount as the authoritative row limit and records the anomaly."
            ),
            "Biological distance and TDA require warehouse/common-morphology feature rows.",
        ],
    }


def write_track1_raw_summary_packet(
    *,
    run_root: Path,
    output_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    packet = build_track1_raw_summary_packet(
        run_root=run_root,
        generated_at=generated_at,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def build_track1_candidate_manifest(
    *,
    summary_packet: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    overall = summary_packet["overall"]
    selection_sets = {
        "overallTopDisplacement": overall["candidates"]["topDisplacement"][:12],
        "overallTopCompactMoving": overall["candidates"]["topCompactMoving"][:12],
        "overallTopCoherent": overall["candidates"]["topCoherent"][:12],
    }
    family_balanced: list[dict[str, Any]] = []
    for family_packet in summary_packet["families"].values():
        for key in ("topDisplacement", "topCompactMoving", "topCoherent"):
            family_balanced.extend(family_packet["candidates"][key][:4])
    selection_sets["familyBalancedMotionAndCompactness"] = _dedupe_candidates(family_balanced)
    candidates = _dedupe_candidates(
        row for rows in selection_sets.values() for row in rows
    )
    return {
        "packetKind": "track1_partial_candidate_manifest_v1",
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "sourceSummary": summary_packet.get("sourceSummary"),
        "completedRunCount": summary_packet["completedRunCount"],
        "completedResultCount": summary_packet["completedResultCount"],
        "selectionSets": selection_sets,
        "candidateCount": len(candidates),
        "candidates": candidates,
        "nextUse": [
            "Render family-balanced candidates after the active Metal harvest finishes.",
            "Measure temporal individuality at 192/256 before treating compact movers as coherent individuals.",
            (
                "Use top-displacement candidates as transport controls; many are not "
                "compact-connected."
            ),
        ],
    }


def write_track1_candidate_manifest(
    *,
    summary_path: Path,
    output_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    summary_packet = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_packet["sourceSummary"] = str(summary_path)
    packet = build_track1_candidate_manifest(
        summary_packet=summary_packet,
        generated_at=generated_at,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def _completed_summary_rows(run_root: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    rows = []
    for summary_path in sorted(run_root.glob("track1b-*-8192-s*/summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(summary.get("count") or 0) != 8192:
            continue
        if int(summary.get("resultsCount") or 0) != 8192:
            continue
        rows.append((summary_path.parent.name, summary_path.parent, summary))
    return rows


def _family_metadata(run_id: str) -> dict[str, str]:
    return track1_family_metadata(run_id)


def _empty_bucket() -> dict[str, Any]:
    return {
        "runs": [],
        "resultCount": 0,
        "counts": defaultdict(int),
        "metrics": defaultdict(list),
        "topDisplacement": [],
        "topCompactMoving": [],
        "topCoherent": [],
        "topScore": [],
    }


def _record_result_row(
    row: dict[str, Any],
    *,
    run_id: str,
    family_key: str,
    buckets: list[dict[str, Any]],
) -> None:
    candidate = _candidate(row, run_id=run_id, family_key=family_key)
    classes = {
        "filtersPassed": row.get("filters_passed") is True,
        "isStable": (row.get("metrics") or {}).get("is_stable") is True,
        "displacementGe5": _ge(candidate["displacement"], 5.0),
        "displacementGe10": _ge(candidate["displacement"], 10.0),
        "displacementGe20": _ge(candidate["displacement"], 20.0),
        "movementEfficiencyGe025": _ge(candidate["movementEfficiency"], 0.25),
        "compactConnected": _compact_connected(row),
        "moving": _moving(row),
        "coherentMover": _coherent_mover(row),
    }
    classes["compactMoving"] = classes["compactConnected"] and classes["moving"]
    for bucket in buckets:
        bucket["resultCount"] += 1
        for key, ok in classes.items():
            if ok:
                bucket["counts"][key] += 1
        for key in (*METRIC_KEYS, "movement_efficiency"):
            value = _metric(row, key)
            if isinstance(value, int | float) and math.isfinite(float(value)):
                bucket["metrics"][key].append(float(value))
        _push_top(bucket["topDisplacement"], "displacement", candidate)
        _push_top(bucket["topScore"], "score", candidate)
        if classes["compactMoving"]:
            _push_top(bucket["topCompactMoving"], "displacement", candidate)
        if classes["coherentMover"]:
            _push_top(bucket["topCoherent"], "displacement", candidate)


def _finish_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    count = int(bucket["resultCount"])
    counts = dict(bucket["counts"])
    return {
        "runCount": len(bucket["runs"]),
        "resultCount": count,
        "runs": bucket["runs"],
        "counts": counts,
        "fractions": {
            key: (value / count if count else None) for key, value in counts.items()
        },
        "metrics": {
            key: _distribution(values)
            for key, values in sorted(bucket["metrics"].items())
        },
        "candidates": {
            "topDisplacement": bucket["topDisplacement"][:12],
            "topCompactMoving": bucket["topCompactMoving"][:12],
            "topCoherent": bucket["topCoherent"][:12],
            "topScore": bucket["topScore"][:12],
        },
    }


def _candidate(row: dict[str, Any], *, run_id: str, family_key: str) -> dict[str, Any]:
    descriptor = row.get("descriptor_bundle") or {}
    terminal = descriptor.get("terminal") or {}
    genotype = descriptor.get("genotype") or {}
    metrics = row.get("metrics") or {}
    return {
        "runId": run_id,
        "family": family_key,
        "seed": row.get("seed"),
        "initSeed": row.get("init_seed"),
        "genotypeHash12": genotype.get("hash12"),
        "fingerprintHash12": terminal.get("fingerprintHash12"),
        "score": row.get("score"),
        "displacement": _metric(row, "displacement"),
        "pathLength": _metric(row, "path_length"),
        "movementEfficiency": _metric(row, "movement_efficiency"),
        "centerVelocity": _metric(row, "center_velocity"),
        "componentCount": _metric(row, "component_count"),
        "largestComponentFraction": _metric(row, "largest_component_fraction"),
        "occupancyMean": _metric(row, "occupancy_mean"),
        "gyration": _metric(row, "gyration"),
        "isStable": metrics.get("is_stable"),
        "filtersPassed": row.get("filters_passed"),
    }


def _metric(row: dict[str, Any], key: str) -> float | int | None:
    metrics = row.get("metrics") or {}
    if key != "movement_efficiency":
        value = metrics.get(key)
        return value if isinstance(value, int | float) else None
    trajectory = (row.get("descriptor_bundle") or {}).get("trajectory") or {}
    value = trajectory.get("movementEfficiency")
    if isinstance(value, int | float):
        return value
    displacement = metrics.get("displacement")
    path_length = metrics.get("path_length")
    if isinstance(displacement, int | float) and isinstance(path_length, int | float):
        if path_length:
            return float(displacement) / float(path_length)
    return None


def _compact_connected(row: dict[str, Any]) -> bool:
    component_count = _metric(row, "component_count")
    largest = _metric(row, "largest_component_fraction")
    return _le(component_count, 4) and _ge(largest, 0.95)


def _moving(row: dict[str, Any]) -> bool:
    return _ge(_metric(row, "displacement"), 5.0) and _ge(_metric(row, "movement_efficiency"), 0.25)


def _coherent_mover(row: dict[str, Any]) -> bool:
    return (
        _ge(_metric(row, "displacement"), 10.0)
        and _ge(_metric(row, "movement_efficiency"), 0.25)
        and _ge(_metric(row, "path_length"), 10.0)
    )


def _ge(value: object, threshold: float) -> bool:
    return (
        isinstance(value, int | float)
        and math.isfinite(float(value))
        and float(value) >= threshold
    )


def _le(value: object, threshold: float) -> bool:
    return (
        isinstance(value, int | float)
        and math.isfinite(float(value))
        and float(value) <= threshold
    )


def _push_top(rows: list[dict[str, Any]], key: str, candidate: dict[str, Any]) -> None:
    value = candidate.get(key)
    if not isinstance(value, int | float) or not math.isfinite(float(value)):
        return
    rows.append(candidate)
    rows.sort(
        key=lambda row: (
            float(row[key]) if isinstance(row.get(key), int | float) else -math.inf
        ),
        reverse=True,
    )
    del rows[24:]


def _dedupe_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[object, object]] = set()
    result = []
    for row in rows:
        key = (row.get("runId"), row.get("seed"))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _distribution(values: list[float]) -> dict[str, Any] | None:
    cleaned = sorted(value for value in values if math.isfinite(value))
    if not cleaned:
        return None

    def percentile(p: float) -> float:
        if len(cleaned) == 1:
            return cleaned[0]
        index = (len(cleaned) - 1) * p
        low = math.floor(index)
        high = math.ceil(index)
        if low == high:
            return cleaned[low]
        fraction = index - low
        return cleaned[low] * (1.0 - fraction) + cleaned[high] * fraction

    return {
        "count": len(cleaned),
        "min": cleaned[0],
        "mean": sum(cleaned) / len(cleaned),
        "median": percentile(0.5),
        "p90": percentile(0.9),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": cleaned[-1],
    }


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)
