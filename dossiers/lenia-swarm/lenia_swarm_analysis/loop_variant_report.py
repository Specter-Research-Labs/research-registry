from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, write_json

KNOWN_SCALE_SUFFIXES = ("small", "medium", "large")
KNOWN_VARIANT_TOKENS = ("mh", "hbias", "mbias")


def _parse_labeled_packet(value: str) -> tuple[str, Path]:
    if "=" in value:
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label:
            raise SystemExit("--packet label must be non-empty")
        return label, Path(raw_path).expanduser().resolve()
    path = Path(value).expanduser().resolve()
    return path.stem, path


def _canonicalize_control_group(control_group: str) -> tuple[str, str, str]:
    tokens = [token for token in control_group.split("-") if token]
    if not tokens:
        raise SystemExit("controlGroup must be non-empty")
    scale = "default"
    if tokens[-1] in KNOWN_SCALE_SUFFIXES:
        scale = tokens[-1]
        tokens = tokens[:-1]
    variant = "default"
    if tokens and tokens[-1] in KNOWN_VARIANT_TOKENS:
        variant = tokens[-1]
        tokens = tokens[:-1]
    if not tokens:
        raise SystemExit(f"{control_group}: could not infer canonical group")
    return "-".join(tokens), scale, variant


def _variant_summary(packet_label: str, row: dict[str, Any]) -> dict[str, Any]:
    control_group = row.get("controlGroup")
    if not isinstance(control_group, str) or not control_group:
        raise SystemExit("loop transport row is missing controlGroup")
    canonical_group, scale, variant = _canonicalize_control_group(control_group)
    top_loop = row.get("topLoop")
    best_control = row.get("bestControl")
    if not isinstance(top_loop, dict):
        raise SystemExit(f"{control_group}: topLoop must be an object")
    if best_control is not None and not isinstance(best_control, dict):
        raise SystemExit(f"{control_group}: bestControl must be an object or null")
    return {
        "packetLabel": packet_label,
        "controlGroup": control_group,
        "canonicalGroup": canonical_group,
        "scale": scale,
        "variant": variant,
        "topLoop": top_loop,
        "bestControl": best_control,
        "deltaStateClosure": row.get("loopMinusBestControlStateClosure"),
        "deltaPhenotypeClosure": row.get("loopMinusBestControlPhenotypeClosure"),
        "deltaRatio": row.get("loopMinusBestControlRatio"),
    }


def build_loop_variant_report(labeled_packets: list[tuple[str, Path]]) -> dict[str, Any]:
    if not labeled_packets:
        raise SystemExit("at least one --packet LABEL=PATH entry is required")

    groups_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    source_packets: list[dict[str, str]] = []
    for packet_label, path in labeled_packets:
        packet = read_json(path)
        groups = packet.get("groups")
        if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
            raise SystemExit(f"{path}: packet is missing groups[]")
        source_packets.append({"label": packet_label, "path": str(path)})
        for row in groups:
            summary = _variant_summary(packet_label, row)
            groups_by_key.setdefault(
                (summary["canonicalGroup"], summary["scale"]),
                [],
            ).append(summary)

    group_rows: list[dict[str, Any]] = []
    for canonical_group, scale in sorted(groups_by_key):
        variants = sorted(
            groups_by_key[(canonical_group, scale)],
            key=lambda row: (str(row["variant"]), str(row["packetLabel"])),
        )
        best_state = max(
            variants,
            key=lambda row: float(
                row["deltaStateClosure"] if row["deltaStateClosure"] is not None else 0.0
            ),
        )
        best_ratio = max(
            variants,
            key=lambda row: float(row["deltaRatio"] if row["deltaRatio"] is not None else 0.0),
        )
        group_rows.append(
            {
                "canonicalGroup": canonical_group,
                "scale": scale,
                "variantCount": len(variants),
                "variants": variants,
                "bestVariantByStateClosure": {
                    "variant": best_state["variant"],
                    "packetLabel": best_state["packetLabel"],
                    "deltaStateClosure": best_state["deltaStateClosure"],
                    "deltaRatio": best_state["deltaRatio"],
                },
                "bestVariantByRatio": {
                    "variant": best_ratio["variant"],
                    "packetLabel": best_ratio["packetLabel"],
                    "deltaStateClosure": best_ratio["deltaStateClosure"],
                    "deltaRatio": best_ratio["deltaRatio"],
                },
            }
        )

    top_groups = sorted(
        group_rows,
        key=lambda row: (
            -float(row["bestVariantByStateClosure"]["deltaStateClosure"] or 0.0),
            -float(row["bestVariantByRatio"]["deltaRatio"] or 0.0),
            str(row["canonicalGroup"]),
            str(row["scale"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "loop_variant_report_v1",
        "sourcePackets": source_packets,
        "groupCount": len(group_rows),
        "topGroups": [
            f"{row['canonicalGroup']}-{row['scale']}" for row in top_groups[:8]
        ],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare loop-transport packets across variant families."
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
    report = build_loop_variant_report(labeled_packets)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else labeled_packets[0][1].parent / "loop-variant-report.json"
    )
    write_json(output_path, report)
    print(
        "Loop variant report:"
        f" groups={report['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
