from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

KNOWN_VARIANTS = {"mh", "hbias", "mbias"}
KNOWN_SCALES = {"small", "medium", "large", "wide"}
KNOWN_PROFILES = {"tight", "wide"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _parse_labeled_packet(value: str) -> tuple[str, Path]:
    if "=" in value:
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label:
            raise SystemExit("--packet label must be non-empty")
        return label, Path(raw_path).expanduser().resolve()
    path = Path(value).expanduser().resolve()
    return path.stem, path


def _parse_control_group(control_group: str) -> tuple[str, str, str]:
    tokens = [token for token in control_group.split("-") if token]
    if not tokens:
        raise SystemExit("controlGroup must be non-empty")
    if len(tokens) >= 2 and tokens[-1] in KNOWN_PROFILES and tokens[-2] in KNOWN_SCALES:
        return "-".join(tokens[:-2]), f"{tokens[-2]}-{tokens[-1]}", "mh"
    if len(tokens) >= 2 and tokens[-1] in KNOWN_SCALES and tokens[-2] in KNOWN_VARIANTS:
        return "-".join(tokens[:-2]), tokens[-1], tokens[-2]
    if tokens[-1] in KNOWN_SCALES:
        return "-".join(tokens[:-1]), tokens[-1], "default"
    raise SystemExit(f"{control_group}: could not infer canonical transport group")


def _candidate_row(packet_label: str, row: dict[str, Any]) -> dict[str, Any]:
    control_group = row.get("controlGroup")
    if not isinstance(control_group, str) or not control_group:
        raise SystemExit("loop transport row is missing controlGroup")
    canonical_group, profile_label, variant = _parse_control_group(control_group)
    delta_state = float(row.get("loopMinusBestControlStateClosure") or 0.0)
    delta_ratio = float(row.get("loopMinusBestControlRatio") or 0.0)
    return {
        "packetLabel": packet_label,
        "controlGroup": control_group,
        "canonicalGroup": canonical_group,
        "profileLabel": profile_label,
        "variant": variant,
        "deltaStateClosure": delta_state,
        "deltaRatio": delta_ratio,
        "compositeScore": (10000.0 * delta_state) + (2.0 * delta_ratio),
        "topLoop": row.get("topLoop"),
        "bestControl": row.get("bestControl"),
    }


def build_transport_winner_packet(labeled_packets: list[tuple[str, Path]]) -> dict[str, Any]:
    if not labeled_packets:
        raise SystemExit("at least one --packet LABEL=PATH entry is required")

    source_packets: list[dict[str, str]] = []
    groups_by_name: dict[str, list[dict[str, Any]]] = {}
    for packet_label, path in labeled_packets:
        packet = _read_json(path)
        groups = packet.get("groups")
        if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
            raise SystemExit(f"{path}: packet is missing groups[]")
        source_packets.append({"label": packet_label, "path": str(path)})
        for row in groups:
            candidate = _candidate_row(packet_label, row)
            groups_by_name.setdefault(candidate["canonicalGroup"], []).append(candidate)

    group_rows: list[dict[str, Any]] = []
    for canonical_group in sorted(groups_by_name):
        candidates = sorted(
            groups_by_name[canonical_group],
            key=lambda row: (
                -float(row["compositeScore"]),
                -float(row["deltaRatio"]),
                -float(row["deltaStateClosure"]),
                str(row["controlGroup"]),
            ),
        )
        best_by_state = max(candidates, key=lambda row: float(row["deltaStateClosure"]))
        best_by_ratio = max(candidates, key=lambda row: float(row["deltaRatio"]))
        winner = candidates[0]
        group_rows.append(
            {
                "controlGroup": canonical_group,
                "candidateCount": len(candidates),
                "scaleCount": len(candidates),
                "winnerByCompositeScore": {
                    "scale": winner["profileLabel"],
                    "variant": winner["variant"],
                    "packetLabel": winner["packetLabel"],
                    "controlGroup": winner["controlGroup"],
                    "deltaStateClosure": winner["deltaStateClosure"],
                    "deltaRatio": winner["deltaRatio"],
                    "compositeScore": winner["compositeScore"],
                },
                "bestScaleByStateClosure": {
                    "scale": best_by_state["profileLabel"],
                    "variant": best_by_state["variant"],
                    "packetLabel": best_by_state["packetLabel"],
                    "controlGroup": best_by_state["controlGroup"],
                    "deltaStateClosure": best_by_state["deltaStateClosure"],
                    "deltaRatio": best_by_state["deltaRatio"],
                },
                "bestScaleByRatio": {
                    "scale": best_by_ratio["profileLabel"],
                    "variant": best_by_ratio["variant"],
                    "packetLabel": best_by_ratio["packetLabel"],
                    "controlGroup": best_by_ratio["controlGroup"],
                    "deltaStateClosure": best_by_ratio["deltaStateClosure"],
                    "deltaRatio": best_by_ratio["deltaRatio"],
                },
                "candidates": candidates,
            }
        )

    top_groups = sorted(
        group_rows,
        key=lambda row: (
            -float(row["winnerByCompositeScore"]["compositeScore"]),
            str(row["controlGroup"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "transport_winner_packet_v1",
        "sourcePackets": source_packets,
        "groupCount": len(group_rows),
        "topGroups": [row["controlGroup"] for row in top_groups],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select final transport winners from multiple loop-transport packets."
    )
    parser.add_argument(
        "--packet",
        action="append",
        default=[],
        help="Packet input as LABEL=/absolute/path.json",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    labeled_packets = [_parse_labeled_packet(value) for value in args.packet]
    packet = build_transport_winner_packet(labeled_packets)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else labeled_packets[0][1].parent / "transport-winner-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport winner packet:"
        f" groups={packet['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
