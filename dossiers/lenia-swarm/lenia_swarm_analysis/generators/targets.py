from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import _resolve_rows_path

DEFAULT_FEATURES = (
    "terminal_final_mass",
    "terminal_final_gyration",
    "terminal_final_occupancy",
    "symmetry_dominant_amplitude",
    "symmetry_entropy",
    "trajectory_path_tortuosity",
)


def _default_output_dir(analysis_dir: Path) -> Path:
    return analysis_dir.parent.parent / "topology-generator-targets" / analysis_dir.name


def _load_generator_artifacts(
    analysis_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest = read_json(analysis_dir / "analysis-manifest.json")
    generators = json.loads((analysis_dir / "generators.json").read_text(encoding="utf-8"))
    packet = read_json(analysis_dir / "generator-packet.json")
    if not isinstance(generators, list):
        raise SystemExit(f"{analysis_dir}/generators.json: expected a JSON array")
    return manifest, generators, packet


def _rows_by_specimen_id(source_manifest: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(source_manifest)
    rows_path = _resolve_rows_path(source_manifest, manifest)
    rows = read_jsonl(rows_path)
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        specimen_id = row.get("specimenId")
        if isinstance(specimen_id, str) and specimen_id:
            mapping[specimen_id] = row
    return mapping


def _feature_value(row: dict[str, Any], feature: str) -> float:
    terminal = row.get("terminal", {})
    trajectory = row.get("trajectory", {})
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
        raise SystemExit(f"Missing feature '{feature}' in topology export row")
    return float(value)


def _goal_vector(row: dict[str, Any], features: tuple[str, ...]) -> dict[str, float]:
    return {feature: _feature_value(row, feature) for feature in features}


def _interpolate_goal(
    lhs: dict[str, float],
    rhs: dict[str, float],
    alpha: float,
) -> dict[str, float]:
    return {
        key: (1.0 - alpha) * lhs[key] + alpha * rhs[key]
        for key in lhs
    }


def _goal_bounds(goals: list[dict[str, float]], margin: float) -> dict[str, list[float]]:
    bounds: dict[str, list[float]] = {}
    keys = goals[0].keys()
    for key in keys:
        values = [goal[key] for goal in goals]
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        padding = max(span * margin, 1e-6)
        bounds[key] = [minimum - padding, maximum + padding]
    return bounds


def _base_imgep_config(path: Path) -> dict[str, Any]:
    config = read_json(path)
    if not isinstance(config, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return config


def build_generator_targets(
    analysis_dir: Path,
    output_dir: Path,
    *,
    features: tuple[str, ...],
    edge_alphas: tuple[float, ...],
    bounds_margin: float,
    base_imgep_config_path: Path,
) -> dict[str, Any]:
    _, generators, packet = _load_generator_artifacts(analysis_dir)
    source_manifest = packet.get("sourceManifest")
    if not isinstance(source_manifest, str) or not source_manifest:
        raise SystemExit(f"{analysis_dir}: generator packet missing sourceManifest")
    rows_by_id = _rows_by_specimen_id(Path(source_manifest))
    base_config = _base_imgep_config(base_imgep_config_path)

    generator_packets: list[dict[str, Any]] = []
    configs_dir = output_dir / "imgep-configs"
    output_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    for generator, detailed in zip(packet.get("generators", []), generators, strict=False):
        if not isinstance(generator, dict) or not isinstance(detailed, dict):
            continue
        generator_id = generator.get("generatorId")
        specimen_ids = generator.get("representativeSpecimenIds")
        if (
            not isinstance(generator_id, str)
            or not isinstance(specimen_ids, list)
            or not specimen_ids
        ):
            continue
        rows = [
            rows_by_id[specimen_id]
            for specimen_id in specimen_ids
            if specimen_id in rows_by_id
        ]
        if len(rows) < 2:
            continue
        specimen_goals = []
        all_goals: list[dict[str, float]] = []
        for row in rows:
            specimen_id = str(row["specimenId"])
            goal = _goal_vector(row, features)
            all_goals.append(goal)
            specimen_goals.append(
                {
                    "goalId": f"{generator_id}-specimen-{specimen_id.split('|')[-1]}",
                    "kind": "specimen",
                    "specimenId": specimen_id,
                    "goal": goal,
                }
            )
        edge_goals = []
        for left, right in zip(rows, rows[1:] + rows[:1], strict=False):
            left_goal = _goal_vector(left, features)
            right_goal = _goal_vector(right, features)
            for alpha in edge_alphas:
                goal = _interpolate_goal(left_goal, right_goal, alpha)
                all_goals.append(goal)
                edge_goals.append(
                    {
                        "goalId": (
                            f"{generator_id}-edge-{left['specimenId'].split('|')[-1]}-"
                            f"{right['specimenId'].split('|')[-1]}-a{int(round(alpha * 100)):02d}"
                        ),
                        "kind": "edge",
                        "fromSpecimenId": left["specimenId"],
                        "toSpecimenId": right["specimenId"],
                        "alpha": alpha,
                        "goal": goal,
                    }
                )
        bounds = _goal_bounds(all_goals, bounds_margin)
        imgep_config = json.loads(json.dumps(base_config))
        imgep_config["goal"] = {
            "features": list(features),
            "boundsMode": "fixed",
            "bounds": bounds,
        }
        config_name = f"{generator_id}.imgep.json"
        (configs_dir / config_name).write_text(
            json.dumps(imgep_config, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        generator_packets.append(
            {
                "generatorId": generator_id,
                "persistence": generator.get("persistence"),
                "representativeSpecimenIds": specimen_ids,
                "cycleEdges": generator.get("cycleEdges", []),
                "specimenGoals": specimen_goals,
                "edgeGoals": edge_goals,
                "bounds": bounds,
                "imgepConfigPath": f"imgep-configs/{config_name}",
                "representativeOrders": [
                    row.get("terminal", {}).get("angularSymmetry", {}).get("dominantOrder")
                    for row in rows
                ],
            }
        )

    packet_out = {
        "version": 1,
        "packetKind": "topology_generator_target_packet_v1",
        "sourceGeneratorPacket": str((analysis_dir / "generator-packet.json").resolve()),
        "features": list(features),
        "edgeAlphas": list(edge_alphas),
        "boundsMargin": bounds_margin,
        "generators": generator_packets,
    }
    (output_dir / "targets.json").write_text(
        json.dumps(packet_out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "version": 1,
                "packetKind": "topology_generator_target_summary_v1",
                "generatorCount": len(generator_packets),
                "features": list(features),
                "sourceGeneratorPacket": packet_out["sourceGeneratorPacket"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return packet_out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build cycle-informed IMGEP targeting packets from topology generators."
    )
    parser.add_argument("--analysis-dir", required=True, help="Generator analysis output directory")
    parser.add_argument("--output", help="Output directory for targeting artifacts")
    parser.add_argument(
        "--features",
        default=",".join(DEFAULT_FEATURES),
        help="Comma-separated IMGEP feature names to target",
    )
    parser.add_argument(
        "--edge-alphas",
        default="0.25,0.5,0.75",
        help="Comma-separated interpolation fractions for edge goals",
    )
    parser.add_argument(
        "--bounds-margin",
        type=float,
        default=0.1,
        help="Relative padding around goal bounds",
    )
    parser.add_argument(
        "--base-imgep-config",
        required=True,
        help="Path to an existing IMGEP config to clone for per-generator targeting configs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    analysis_dir = Path(args.analysis_dir).expanduser().resolve()
    if not analysis_dir.is_dir():
        raise SystemExit(f"Missing analysis dir: {analysis_dir}")
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(analysis_dir).resolve()
    )
    features = tuple(item.strip() for item in args.features.split(",") if item.strip())
    edge_alphas = tuple(float(item.strip()) for item in args.edge_alphas.split(",") if item.strip())
    packet = build_generator_targets(
        analysis_dir,
        output_dir,
        features=features,
        edge_alphas=edge_alphas,
        bounds_margin=args.bounds_margin,
        base_imgep_config_path=Path(args.base_imgep_config).expanduser().resolve(),
    )
    print(
        "Topology generator targets:"
        f" generators={len(packet['generators'])}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
