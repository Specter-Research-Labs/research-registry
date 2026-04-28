from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

KNOWN_SCALE_SUFFIXES = ("small", "medium", "large")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _parse_labeled_packet(value: str) -> tuple[str, Path]:
    if "=" in value:
        scale, raw_path = value.split("=", 1)
        scale = scale.strip()
        if not scale:
            raise SystemExit("--packet scale label must be non-empty")
        path = Path(raw_path).expanduser().resolve()
        return scale, path
    return "", Path(value).expanduser().resolve()


def _canonical_group_and_scale(control_group: str, packet_scale: str) -> tuple[str, str]:
    if packet_scale:
        suffix = f"-{packet_scale}"
        if control_group.endswith(suffix):
            return control_group[: -len(suffix)], packet_scale
        return control_group, packet_scale
    for scale in KNOWN_SCALE_SUFFIXES:
        suffix = f"-{scale}"
        if control_group.endswith(suffix):
            return control_group[: -len(suffix)], scale
    return control_group, "default"


def _group_summary(scale: str, row: dict[str, Any]) -> dict[str, Any]:
    top_loop = row.get("topLoop")
    best_control = row.get("bestControl")
    if not isinstance(top_loop, dict):
        raise SystemExit("loop transport row is missing topLoop")
    if best_control is not None and not isinstance(best_control, dict):
        raise SystemExit("loop transport row bestControl must be an object or null")
    return {
        "scale": scale,
        "topLoop": top_loop,
        "bestControl": best_control,
        "deltaStateClosure": row.get("loopMinusBestControlStateClosure"),
        "deltaPhenotypeClosure": row.get("loopMinusBestControlPhenotypeClosure"),
        "deltaRatio": row.get("loopMinusBestControlRatio"),
    }


def build_transport_scale_report(labeled_packets: list[tuple[str, Path]]) -> dict[str, Any]:
    if not labeled_packets:
        raise SystemExit("at least one --packet SCALE=PATH entry is required")

    groups_by_name: dict[str, list[dict[str, Any]]] = {}
    source_packets: list[dict[str, str]] = []
    for scale, path in labeled_packets:
        packet = _read_json(path)
        groups = packet.get("groups")
        if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
            raise SystemExit(f"{path}: packet is missing groups[]")
        source_packets.append({"scale": scale, "path": str(path)})
        for row in groups:
            control_group = row.get("controlGroup")
            if not isinstance(control_group, str) or not control_group:
                raise SystemExit(f"{path}: controlGroup must be a non-empty string")
            canonical_group, inferred_scale = _canonical_group_and_scale(control_group, scale)
            groups_by_name.setdefault(canonical_group, []).append(
                _group_summary(inferred_scale, row)
            )

    group_rows: list[dict[str, Any]] = []
    for control_group in sorted(groups_by_name):
        scale_rows = sorted(groups_by_name[control_group], key=lambda row: str(row["scale"]))
        best_state = max(
            scale_rows,
            key=lambda row: float(
                row["deltaStateClosure"] if row["deltaStateClosure"] is not None else 0.0
            ),
        )
        best_ratio = max(
            scale_rows,
            key=lambda row: float(row["deltaRatio"] if row["deltaRatio"] is not None else 0.0),
        )
        group_rows.append(
            {
                "controlGroup": control_group,
                "scaleCount": len(scale_rows),
                "scales": scale_rows,
                "bestScaleByStateClosure": {
                    "scale": best_state["scale"],
                    "deltaStateClosure": best_state["deltaStateClosure"],
                    "deltaRatio": best_state["deltaRatio"],
                },
                "bestScaleByRatio": {
                    "scale": best_ratio["scale"],
                    "deltaStateClosure": best_ratio["deltaStateClosure"],
                    "deltaRatio": best_ratio["deltaRatio"],
                },
            }
        )

    top_groups = sorted(
        group_rows,
        key=lambda row: (
            -float(row["bestScaleByStateClosure"]["deltaStateClosure"] or 0.0),
            -float(row["bestScaleByRatio"]["deltaRatio"] or 0.0),
            str(row["controlGroup"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "transport_scale_report_v1",
        "sourcePackets": source_packets,
        "scaleCount": len(labeled_packets),
        "groupCount": len(group_rows),
        "topGroups": [row["controlGroup"] for row in top_groups[:8]],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare loop-transport packets across multiple scale labels."
    )
    parser.add_argument(
        "--packet",
        action="append",
        default=[],
        help="Packet input as /absolute/path.json or SCALE=/absolute/path.json",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    labeled_packets = [_parse_labeled_packet(value) for value in args.packet]
    report = build_transport_scale_report(labeled_packets)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else labeled_packets[0][1].parent / "transport-scale-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport scale report:"
        f" groups={report['groupCount']}"
        f" scales={report['scaleCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
