from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import _resolve_rows_path


def _default_output_dir(targets_dir: Path) -> Path:
    return targets_dir.parent.parent / "topology-generator-pilot-analysis" / targets_dir.name


def _load_targets(targets_path: Path) -> dict[str, Any]:
    packet = read_json(targets_path)
    if not isinstance(packet, dict):
        raise SystemExit(f"{targets_path}: expected a JSON object")
    generators = packet.get("generators")
    if not isinstance(generators, list):
        raise SystemExit(f"{targets_path}: missing generators[]")
    return packet


def _load_source_rows(source_manifest: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(source_manifest)
    rows_path = _resolve_rows_path(source_manifest, manifest)
    rows = read_jsonl(rows_path)
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        specimen_id = row.get("specimenId")
        if isinstance(specimen_id, str) and specimen_id:
            mapping[specimen_id] = row
    return mapping


def _result_feature_value(result: dict[str, Any], feature: str) -> float:
    bundle = result.get("descriptor_bundle", {})
    terminal = bundle.get("terminal", {}) if isinstance(bundle, dict) else {}
    trajectory = bundle.get("trajectory", {}) if isinstance(bundle, dict) else {}
    angular = terminal.get("angularSymmetry", {}) if isinstance(terminal, dict) else {}
    mapping: dict[str, Any] = {
        "terminal_final_mass": terminal.get("finalMass"),
        "terminal_final_gyration": terminal.get("finalGyration"),
        "terminal_final_occupancy": terminal.get("finalOccupancy"),
        "symmetry_dominant_amplitude": angular.get("dominantAmplitude"),
        "symmetry_entropy": angular.get("normalizedEntropy"),
        "trajectory_path_tortuosity": trajectory.get("pathTortuosity"),
        "trajectory_movement_efficiency": trajectory.get("movementEfficiency"),
        "trajectory_heading_circular_variance": trajectory.get("headingCircularVariance"),
        "trajectory_accumulated_turn_abs": trajectory.get("accumulatedTurnAbs"),
    }
    value = mapping.get(feature)
    if not isinstance(value, (int, float)):
        raise SystemExit(f"Missing feature '{feature}' in pilot result row")
    return float(value)


def _result_goal_vector(result: dict[str, Any], features: list[str]) -> dict[str, float]:
    return {feature: _result_feature_value(result, feature) for feature in features}


def _normalized_goal_distance(
    value: dict[str, float],
    goal: dict[str, float],
    bounds: dict[str, list[float]],
) -> float:
    accum = 0.0
    count = 0
    for feature, observed in value.items():
        lower, upper = bounds[feature]
        span = max(float(upper) - float(lower), 1e-6)
        accum += ((observed - float(goal[feature])) / span) ** 2
        count += 1
    return math.sqrt(accum / max(count, 1))


def _in_bounds(value: dict[str, float], bounds: dict[str, list[float]]) -> bool:
    return all(
        float(bounds[key][0]) <= observed <= float(bounds[key][1])
        for key, observed in value.items()
    )


def _extract_fingerprint(payload: dict[str, Any]) -> np.ndarray:
    terminal = payload.get("terminal")
    if not isinstance(terminal, dict):
        raise SystemExit("Missing terminal payload in source topology row")
    resolution = terminal.get("fingerprintResolution")
    fingerprint = terminal.get("fingerprintU8")
    if not isinstance(resolution, int) or not isinstance(fingerprint, list):
        raise SystemExit("Missing fingerprint payload in source topology row")
    return np.asarray(fingerprint, dtype=np.float64) / 255.0


def _extract_result_fingerprint(payload: dict[str, Any]) -> np.ndarray:
    bundle = payload.get("descriptor_bundle", {})
    terminal = bundle.get("terminal", {}) if isinstance(bundle, dict) else {}
    resolution = terminal.get("fingerprintResolution")
    fingerprint = terminal.get("fingerprintU8")
    if not isinstance(resolution, int):
        raise SystemExit("Missing fingerprint payload in pilot result row")
    if isinstance(fingerprint, list):
        return np.asarray(fingerprint, dtype=np.float64) / 255.0
    if isinstance(fingerprint, str):
        raw = base64.b64decode(fingerprint)
        return np.frombuffer(raw, dtype=np.uint8).astype(np.float64) / 255.0
    raise SystemExit("Missing fingerprint payload in pilot result row")


def _representative_fingerprints(
    generator: dict[str, Any],
    source_rows: dict[str, dict[str, Any]],
) -> tuple[list[str], np.ndarray]:
    specimen_ids = generator.get("representativeSpecimenIds")
    if not isinstance(specimen_ids, list) or not specimen_ids:
        raise SystemExit("Generator packet missing representativeSpecimenIds")
    vectors: list[np.ndarray] = []
    ordered_ids: list[str] = []
    for specimen_id in specimen_ids:
        if not isinstance(specimen_id, str):
            continue
        row = source_rows.get(specimen_id)
        if row is None:
            continue
        ordered_ids.append(specimen_id)
        vectors.append(_extract_fingerprint(row))
    if not vectors:
        raise SystemExit("No representative fingerprints available for generator")
    return ordered_ids, np.stack(vectors, axis=0)


def _nearest_representative(
    fingerprint: np.ndarray,
    representative_ids: list[str],
    representative_vectors: np.ndarray,
) -> tuple[str, float]:
    distances = np.linalg.norm(representative_vectors - fingerprint[None, :], axis=1)
    index = int(np.argmin(distances))
    return representative_ids[index], float(distances[index])


def analyze_generator_runs(
    targets_path: Path,
    run_dirs: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    packet = _load_targets(targets_path)
    source_generator_packet = packet.get("sourceGeneratorPacket")
    if not isinstance(source_generator_packet, str) or not source_generator_packet:
        raise SystemExit(f"{targets_path}: missing sourceGeneratorPacket")
    source_packet = read_json(Path(source_generator_packet))
    source_manifest = source_packet.get("sourceManifest")
    if not isinstance(source_manifest, str) or not source_manifest:
        raise SystemExit(f"{source_generator_packet}: missing sourceManifest")
    source_rows = _load_source_rows(Path(source_manifest))
    generators = packet["generators"]
    generator_by_id = {
        generator["generatorId"]: generator
        for generator in generators
        if isinstance(generator, dict) and isinstance(generator.get("generatorId"), str)
    }
    features = packet.get("features")
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise SystemExit(f"{targets_path}: missing features[]")

    summaries: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for run_dir in run_dirs:
        generator_id = run_dir.name
        generator = generator_by_id.get(generator_id)
        if generator is None:
            raise SystemExit(f"{run_dir}: no matching generatorId in {targets_path}")
        results_path = run_dir / "results.jsonl"
        summary_path = run_dir / "summary.json"
        if not results_path.is_file() or not summary_path.is_file():
            raise SystemExit(f"{run_dir}: missing results.jsonl or summary.json")
        results = read_jsonl(results_path)
        run_summary = read_json(summary_path)
        representative_ids, representative_vectors = _representative_fingerprints(
            generator,
            source_rows,
        )
        bounds = generator["bounds"]
        goals = [
            *(generator.get("specimenGoals", [])),
            *(generator.get("edgeGoals", [])),
        ]

        goal_kind_counts = {"specimen": 0, "edge": 0}
        unique_goal_ids: set[str] = set()
        unique_edge_goal_ids: set[str] = set()
        representative_distance_values: list[float] = []
        normalized_goal_distances: list[float] = []
        in_bounds_count = 0
        kept_results = 0
        closest_examples: list[dict[str, Any]] = []

        for result in results:
            if not bool(result.get("filters_passed")):
                continue
            kept_results += 1
            goal_vector = _result_goal_vector(result, features)
            if _in_bounds(goal_vector, bounds):
                in_bounds_count += 1
            nearest_goal = None
            nearest_distance = float("inf")
            for goal in goals:
                if not isinstance(goal, dict):
                    continue
                goal_id = goal.get("goalId")
                target = goal.get("goal")
                if not isinstance(goal_id, str) or not isinstance(target, dict):
                    continue
                distance = _normalized_goal_distance(goal_vector, target, bounds)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_goal = goal
            if nearest_goal is None:
                continue
            normalized_goal_distances.append(nearest_distance)
            goal_kind = str(nearest_goal.get("kind"))
            if goal_kind in goal_kind_counts:
                goal_kind_counts[goal_kind] += 1
            goal_id = str(nearest_goal.get("goalId"))
            unique_goal_ids.add(goal_id)
            if goal_kind == "edge":
                unique_edge_goal_ids.add(goal_id)
            representative_id, representative_distance = _nearest_representative(
                _extract_result_fingerprint(result),
                representative_ids,
                representative_vectors,
            )
            representative_distance_values.append(representative_distance)
            closest_examples.append(
                {
                    "seed": result.get("seed"),
                    "score": result.get("score"),
                    "nearestGoalId": goal_id,
                    "nearestGoalKind": goal_kind,
                    "normalizedGoalDistance": nearest_distance,
                    "nearestRepresentativeSpecimenId": representative_id,
                    "nearestRepresentativePhenotypeDistance": representative_distance,
                }
            )

        closest_examples.sort(
            key=lambda item: (
                float(item["normalizedGoalDistance"]),
                float(item["nearestRepresentativePhenotypeDistance"]),
            )
        )
        run_report = {
            "generatorId": generator_id,
            "resultCount": len(results),
            "keptResultCount": kept_results,
            "historyCount": int(run_summary.get("history_count", 0)),
            "topCount": int(run_summary.get("top_count", 0)),
            "durationSeconds": float(run_summary.get("duration_seconds", 0.0)),
            "boundsHitRate": (in_bounds_count / kept_results) if kept_results else 0.0,
            "nearestGoalKindCounts": goal_kind_counts,
            "uniqueNearestGoalCount": len(unique_goal_ids),
            "uniqueNearestEdgeGoalCount": len(unique_edge_goal_ids),
            "edgePreferredRate": (
                goal_kind_counts["edge"] / kept_results if kept_results else 0.0
            ),
            "normalizedGoalDistance": {
                "min": min(normalized_goal_distances) if normalized_goal_distances else None,
                "mean": (
                    sum(normalized_goal_distances) / len(normalized_goal_distances)
                    if normalized_goal_distances
                    else None
                ),
                "median": (
                    float(np.median(np.asarray(normalized_goal_distances, dtype=np.float64)))
                    if normalized_goal_distances
                    else None
                ),
            },
            "representativePhenotypeDistance": {
                "min": (
                    min(representative_distance_values)
                    if representative_distance_values
                    else None
                ),
                "mean": (
                    sum(representative_distance_values) / len(representative_distance_values)
                    if representative_distance_values
                    else None
                ),
                "median": (
                    float(np.median(np.asarray(representative_distance_values, dtype=np.float64)))
                    if representative_distance_values
                    else None
                ),
            },
            "bestExamples": closest_examples[:12],
        }
        summaries.append(run_report)
        (output_dir / f"{generator_id}.json").write_text(
            json.dumps(run_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    aggregate = {
        "version": 1,
        "packetKind": "topology_generator_pilot_analysis_v1",
        "targetsPath": str(targets_path),
        "sourceGeneratorPacket": source_generator_packet,
        "generatorCount": len(summaries),
        "runs": summaries,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return aggregate


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze cycle-informed IMGEP pilot runs against generator targets."
    )
    parser.add_argument("--targets", required=True, help="Path to topology-generator targets.json")
    parser.add_argument(
        "--run-dir",
        action="append",
        required=True,
        help="Run directory produced by the supported discovery/orchestration flow; pass multiple times",
    )
    parser.add_argument("--output", help="Output directory for pilot analysis artifacts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    targets_path = Path(args.targets).expanduser().resolve()
    if not targets_path.is_file():
        raise SystemExit(f"Missing targets.json: {targets_path}")
    run_dirs = [Path(item).expanduser().resolve() for item in args.run_dir]
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            raise SystemExit(f"Missing run dir: {run_dir}")
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(targets_path.parent).resolve()
    )
    analyze_generator_runs(targets_path, run_dirs, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
