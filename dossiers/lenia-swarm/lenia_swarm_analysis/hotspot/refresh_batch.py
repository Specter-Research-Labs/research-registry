from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROFILE_OFFSETS = {
    "small": {
        "m.0": [-0.001, -0.0005, 0.0, 0.0005, 0.001],
        "h.0": [-0.01, -0.005, 0.0, 0.005, 0.01],
    },
    "medium": {
        "m.0": [-0.002, -0.001, 0.0, 0.001, 0.002],
        "h.0": [-0.02, -0.01, 0.0, 0.01, 0.02],
    },
}

COORDINATE_MAP = {
    "m": "m.0",
    "h": "h.0",
    "r": "R",
    "s": "s.0",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _group_coordinate_paths(control_group: str) -> list[str]:
    parts = control_group.split("-", 1)
    if len(parts) != 2 or not parts[1]:
        raise SystemExit(f"{control_group}: cannot infer coordinate token")
    token = parts[1].lower()
    coordinates: list[str] = []
    for char in token:
        path = COORDINATE_MAP.get(char)
        if path is None:
            raise SystemExit(f"{control_group}: unsupported coordinate token {char!r}")
        coordinates.append(path)
    return coordinates


def build_hotspot_transport_refresh_spec(
    *,
    neighborhood_packet_path: Path,
    cli_binary: Path,
    output_root: Path,
    per_group_limit: int,
    profiles: list[str],
) -> dict[str, Any]:
    if per_group_limit <= 0:
        raise SystemExit("--per-group-limit must be > 0")
    if not profiles:
        raise SystemExit("at least one profile is required")
    packet = _read_json(neighborhood_packet_path)
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("neighborhood packet is missing groups[]")

    for profile in profiles:
        if profile not in PROFILE_OFFSETS:
            raise SystemExit(f"unsupported profile {profile!r}")

    run_rows: list[dict[str, Any]] = []
    for group in groups:
        control_group = str(group["controlGroup"])
        specimen = str(group["specimen"])
        coordinates = _group_coordinate_paths(control_group)
        candidates = group.get("selectedCandidates")
        if not isinstance(candidates, list) or any(not isinstance(row, dict) for row in candidates):
            raise SystemExit(f"{control_group}: selectedCandidates[] is required")
        for candidate in candidates[:per_group_limit]:
            bundle = candidate.get("exportDir")
            candidate_id = str(candidate["candidateId"])
            if not isinstance(bundle, str):
                raise SystemExit(f"{candidate_id}: exportDir is required")
            for profile in profiles:
                offsets_by_coord = PROFILE_OFFSETS[profile]
                for coordinate in coordinates:
                    if coordinate not in offsets_by_coord:
                        raise SystemExit(
                            f"profile {profile!r} does not define offsets for {coordinate}"
                        )
                    coord_slug = coordinate.replace(".", "").replace("/", "-")
                    run_rows.append(
                        {
                            "name": f"{candidate_id}-{coord_slug}-{profile}-open",
                            "bundle": str(Path(bundle).expanduser().resolve()),
                            "coordinate": coordinate,
                            "offsets": list(offsets_by_coord[coordinate]),
                            "tags": {
                                "specimen": specimen,
                                "controlGroup": control_group,
                                "candidateId": candidate_id,
                                "profile": profile,
                                "coordinate": coordinate,
                                "role": "transport-refresh",
                                "kind": "open-path",
                            },
                        }
                    )

    return {
        "version": 1,
        "packetKind": "hotspot_transport_refresh_batch_spec_v1",
        "sourceNeighborhoodPacket": str(neighborhood_packet_path),
        "cliBinary": str(cli_binary),
        "outputRoot": str(output_root),
        "perGroupLimit": per_group_limit,
        "profiles": list(profiles),
        "runCount": len(run_rows),
        "runs": run_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a stateful continuation refresh batch from hotspot neighborhoods."
    )
    parser.add_argument(
        "--neighborhood-packet",
        required=True,
        help="Path to hotspot_neighborhood_packet_v1 JSON",
    )
    parser.add_argument("--cli-binary", required=True, help="Path to LeniaCLI release binary")
    parser.add_argument("--output-root", required=True, help="Root directory for run outputs")
    parser.add_argument(
        "--per-group-limit",
        type=int,
        default=2,
        help="How many selected candidates per control group to include",
    )
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Refresh profile to include; supported: small, medium",
    )
    parser.add_argument("--output", help="Output path for batch spec JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    profiles = [str(value) for value in args.profile] if args.profile else ["small", "medium"]
    spec = build_hotspot_transport_refresh_spec(
        neighborhood_packet_path=Path(args.neighborhood_packet).expanduser().resolve(),
        cli_binary=Path(args.cli_binary).expanduser().resolve(),
        output_root=Path(args.output_root).expanduser().resolve(),
        per_group_limit=int(args.per_group_limit),
        profiles=profiles,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(args.output_root).expanduser().resolve() / "batch-spec.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Hotspot transport refresh batch:"
        f" runs={spec['runCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
