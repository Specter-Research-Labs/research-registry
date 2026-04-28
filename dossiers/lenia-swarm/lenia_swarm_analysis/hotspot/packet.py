from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _cycle_hotspots(packet: dict[str, Any]) -> list[dict[str, Any]]:
    generators = packet.get("generators")
    if not isinstance(generators, list) or any(not isinstance(row, dict) for row in generators):
        raise SystemExit("cycle-lift packet is missing generators[]")
    rows: list[dict[str, Any]] = []
    representation = packet.get("representation")
    for row in generators:
        score = (
            10.0 * float(row["reentryEdgeCount"])
            + 2.0 * float(row["nonEndpointRepresentativeEdgeCount"])
            + float(row["maxEscapeRatio"])
        )
        rows.append(
            {
                "kind": "cycle_generator",
                "id": str(row["generatorId"]),
                "representation": representation,
                "score": score,
                "reentryEdgeCount": int(row["reentryEdgeCount"]),
                "nonEndpointRepresentativeEdgeCount": int(
                    row["nonEndpointRepresentativeEdgeCount"]
                ),
                "maxEscapeRatio": float(row["maxEscapeRatio"]),
                "persistence": float(row["persistence"]),
            }
        )
    return rows


def _transport_hotspots(packet: dict[str, Any]) -> list[dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport scale report is missing groups[]")
    rows: list[dict[str, Any]] = []
    for row in groups:
        best_state = row.get("bestScaleByStateClosure")
        best_ratio = row.get("bestScaleByRatio")
        if not isinstance(best_state, dict) or not isinstance(best_ratio, dict):
            raise SystemExit("transport scale group is missing best scale summaries")
        score = (
            10000.0 * float(best_state["deltaStateClosure"] or 0.0)
            + 2.0 * float(best_ratio["deltaRatio"] or 0.0)
        )
        rows.append(
            {
                "kind": "transport_group",
                "id": str(row["controlGroup"]),
                "score": score,
                "bestScaleByStateClosure": best_state,
                "bestScaleByRatio": best_ratio,
            }
        )
    return rows


def build_hotspot_packet(
    *,
    cycle_lift_packet: Path | None,
    transport_scale_report: Path | None,
) -> dict[str, Any]:
    hotspot_rows: list[dict[str, Any]] = []
    source: dict[str, str] = {}
    if cycle_lift_packet is not None:
        source["cycleLiftPacket"] = str(cycle_lift_packet)
        hotspot_rows.extend(_cycle_hotspots(_read_json(cycle_lift_packet)))
    if transport_scale_report is not None:
        source["transportScaleReport"] = str(transport_scale_report)
        hotspot_rows.extend(_transport_hotspots(_read_json(transport_scale_report)))
    ranked = sorted(
        hotspot_rows,
        key=lambda row: (-float(row["score"]), str(row["kind"]), str(row["id"])),
    )
    return {
        "version": 1,
        "packetKind": "morphospace_hotspot_packet_v1",
        "sourceArtifacts": source,
        "hotspotCount": len(ranked),
        "topHotspots": [{"kind": row["kind"], "id": row["id"]} for row in ranked[:12]],
        "hotspots": ranked,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine cycle-lift and transport-scale evidence into one hotspot packet."
    )
    parser.add_argument("--cycle-lift-packet", help="Path to cycle-lift packet JSON")
    parser.add_argument("--transport-scale-report", help="Path to transport-scale report JSON")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.cycle_lift_packet and not args.transport_scale_report:
        raise SystemExit(
            "at least one of --cycle-lift-packet or --transport-scale-report is required"
        )
    packet = build_hotspot_packet(
        cycle_lift_packet=(
            Path(args.cycle_lift_packet).expanduser().resolve()
            if args.cycle_lift_packet
            else None
        ),
        transport_scale_report=(
            Path(args.transport_scale_report).expanduser().resolve()
            if args.transport_scale_report
            else None
        ),
    )
    default_root = (
        Path(args.transport_scale_report).expanduser().resolve().parent
        if args.transport_scale_report
        else Path(args.cycle_lift_packet).expanduser().resolve().parent
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (default_root / "hotspot-packet.json").resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Hotspot packet:"
        f" hotspots={packet['hotspotCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
