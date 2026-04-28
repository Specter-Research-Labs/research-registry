from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, write_json


def _cycle_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
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
                "witnessKind": "cycle_generator",
                "id": str(row["generatorId"]),
                "representation": representation,
                "score": score,
                "persistence": float(row["persistence"]),
                "edgeCount": int(row["edgeCount"]),
                "reentryEdgeCount": int(row["reentryEdgeCount"]),
                "nonEndpointRepresentativeEdgeCount": int(
                    row["nonEndpointRepresentativeEdgeCount"]
                ),
                "anchorInvariantEdgeCount": int(row["anchorInvariantEdgeCount"]),
                "maxEscapeRatio": float(row["maxEscapeRatio"]),
                "maxDistanceToCycleSupport": float(row["maxDistanceToCycleSupport"]),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), str(row["id"])))


def _open_transport_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
    runs = packet.get("runs")
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
        raise SystemExit("stateful continuation batch packet is missing runs[]")
    rows: list[dict[str, Any]] = []
    for row in runs:
        ratio = float(row["transportToPhenotypeRatio"])
        transported = float(row["endpointTransportedStateDistance"])
        rows.append(
            {
                "witnessKind": "open_transport",
                "id": str(row["name"]),
                "score": ratio,
                "bundle": str(row["bundle"]),
                "coordinate": str(row["coordinate"]) if row["coordinate"] is not None else None,
                "pointCount": int(row["pointCount"]),
                "endpointPhenotypeDistance": float(row["endpointPhenotypeDistance"]),
                "endpointTransportedStateDistance": transported,
                "transportToPhenotypeRatio": ratio,
                "maxTransportedStateDistanceFromStart": float(
                    row["maxTransportedStateDistanceFromStart"]
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-float(row["score"]), -float(row["endpointTransportedStateDistance"])),
    )


def _loop_transport_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport scale report is missing groups[]")
    rows: list[dict[str, Any]] = []
    for row in groups:
        best_state = row.get("bestScaleByStateClosure")
        best_ratio = row.get("bestScaleByRatio")
        if not isinstance(best_state, dict) or not isinstance(best_ratio, dict):
            raise SystemExit("transport scale report group is missing best-scale summaries")
        delta_state = float(best_state["deltaStateClosure"] or 0.0)
        delta_ratio = float(best_ratio["deltaRatio"] or 0.0)
        score = (10000.0 * delta_state) + (2.0 * delta_ratio)
        rows.append(
            {
                "witnessKind": "loop_transport_group",
                "id": str(row["controlGroup"]),
                "score": score,
                "bestScaleByStateClosure": best_state,
                "bestScaleByRatio": best_ratio,
                "scaleCount": int(row["scaleCount"]),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), str(row["id"])))


def _transport_repro_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport repro report is missing groups[]")
    rows: list[dict[str, Any]] = []
    for row in groups:
        stable = bool(row["allKindsStable"])
        max_state_range = float(row["maxStateClosureRange"])
        max_ratio_range = float(row["maxRatioRange"])
        score = (1000.0 if stable else 0.0) - (100000.0 * max_state_range) - max_ratio_range
        rows.append(
            {
                "witnessKind": "transport_repro_group",
                "id": str(row["controlGroup"]),
                "score": score,
                "allKindsStable": stable,
                "maxStateClosureRange": max_state_range,
                "maxRatioRange": max_ratio_range,
                "kindCount": int(row["kindCount"]),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), str(row["id"])))


def _transport_dense_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport dense report is missing groups[]")
    rows: list[dict[str, Any]] = []
    for row in groups:
        dense_state = float(row["denseStateClosure"])
        dense_ratio = float(row["denseRatio"])
        score = (10000.0 * dense_state) + dense_ratio
        rows.append(
            {
                "witnessKind": "transport_dense_group",
                "id": str(row["canonicalGroup"]),
                "score": score,
                "controlGroup": str(row["controlGroup"]),
                "densePointCount": int(row["densePointCount"]),
                "denseStateClosure": dense_state,
                "denseRatio": dense_ratio,
                "sparseWinnerControlGroup": str(row["sparseWinnerControlGroup"]),
                "sparseWinnerStateSurplus": float(row["sparseWinnerStateSurplus"]),
                "sparseWinnerRatioSurplus": float(row["sparseWinnerRatioSurplus"]),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), str(row["id"])))


def _transport_validation_witnesses(packet: dict[str, Any]) -> list[dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport validation report is missing groups[]")
    rows: list[dict[str, Any]] = []
    for row in groups:
        validation_delta_state = float(row["validationDeltaStateClosure"])
        validation_delta_ratio = float(row["validationDeltaRatio"])
        score = max(0.0, (10000.0 * validation_delta_state) + (2.0 * validation_delta_ratio))
        rows.append(
            {
                "witnessKind": "transport_validation_group",
                "id": str(row["validationControlGroup"]),
                "score": score,
                "canonicalGroup": str(row["canonicalGroup"]),
                "winnerControlGroup": str(row["winnerControlGroup"]),
                "validationBestControlKind": str(row["validationBestControlKind"]),
                "validationDeltaStateClosure": validation_delta_state,
                "validationDeltaRatio": validation_delta_ratio,
                "survivesValidationByState": bool(row["survivesValidationByState"]),
                "survivesValidationByRatio": bool(row["survivesValidationByRatio"]),
                "survivesValidationStrongly": bool(row["survivesValidationStrongly"]),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), str(row["id"])))


def build_arrangement_witness_packet(
    *,
    cycle_lift_packet: Path | None,
    atlas_batch_packet: Path | None,
    transport_scale_report: Path | None,
    transport_repro_report: Path | None,
    transport_dense_report: Path | None,
    transport_validation_report: Path | None,
    hotspot_packet: Path | None,
) -> dict[str, Any]:
    source: dict[str, str] = {}
    cycle_rows: list[dict[str, Any]] = []
    open_transport_rows: list[dict[str, Any]] = []
    loop_transport_rows: list[dict[str, Any]] = []
    repro_transport_rows: list[dict[str, Any]] = []
    dense_transport_rows: list[dict[str, Any]] = []
    validation_transport_rows: list[dict[str, Any]] = []
    hotspot_refs: list[dict[str, str]] = []

    if cycle_lift_packet is not None:
        source["cycleLiftPacket"] = str(cycle_lift_packet)
        cycle_rows = _cycle_witnesses(read_json(cycle_lift_packet))
    if atlas_batch_packet is not None:
        source["atlasBatchPacket"] = str(atlas_batch_packet)
        open_transport_rows = _open_transport_witnesses(read_json(atlas_batch_packet))
    if transport_scale_report is not None:
        source["transportScaleReport"] = str(transport_scale_report)
        loop_transport_rows = _loop_transport_witnesses(read_json(transport_scale_report))
    if transport_repro_report is not None:
        source["transportReproReport"] = str(transport_repro_report)
        repro_transport_rows = _transport_repro_witnesses(read_json(transport_repro_report))
    if transport_dense_report is not None:
        source["transportDenseReport"] = str(transport_dense_report)
        dense_transport_rows = _transport_dense_witnesses(read_json(transport_dense_report))
    if transport_validation_report is not None:
        source["transportValidationReport"] = str(transport_validation_report)
        validation_transport_rows = _transport_validation_witnesses(
            read_json(transport_validation_report)
        )
    if hotspot_packet is not None:
        source["hotspotPacket"] = str(hotspot_packet)
        raw_hotspots = read_json(hotspot_packet).get("topHotspots")
        if isinstance(raw_hotspots, list):
            hotspot_refs = [
                {"kind": str(row["kind"]), "id": str(row["id"])}
                for row in raw_hotspots
                if isinstance(row, dict)
                and isinstance(row.get("kind"), str)
                and isinstance(row.get("id"), str)
            ]

    all_rows = sorted(
        cycle_rows
        + open_transport_rows
        + loop_transport_rows
        + repro_transport_rows
        + dense_transport_rows,
        key=lambda row: (-float(row["score"]), str(row["witnessKind"]), str(row["id"])),
    )
    all_rows = sorted(
        all_rows + validation_transport_rows,
        key=lambda row: (-float(row["score"]), str(row["witnessKind"]), str(row["id"])),
    )
    return {
        "version": 1,
        "packetKind": "arrangement_witness_packet_v1",
        "sourceArtifacts": source,
        "arrangementProxy": {
            "kind": "transported_terminal_state_patch",
            "note": (
                "Current arrangement evidence is a transport/state proxy plus cycle-support "
                "visitation; it is not yet a substructure/interface decomposition."
            ),
        },
        "supportsCycleLinkedReentry": any(
            int(row["reentryEdgeCount"]) > 0 for row in cycle_rows
        ),
        "supportsHiddenStateDominance": any(
            float(row["transportToPhenotypeRatio"]) > 1.0 for row in open_transport_rows
        ),
        "supportsPositiveLoopSurplus": any(
            float(row["bestScaleByStateClosure"]["deltaStateClosure"] or 0.0) > 0.0
            for row in loop_transport_rows
        ),
        "supportsTransportReproducibility": any(
            bool(row["allKindsStable"]) for row in repro_transport_rows
        ),
        "supportsDenseWinnerExploration": any(
            int(row["densePointCount"]) > 5 for row in dense_transport_rows
        ),
        "supportsValidatedLoopSurplus": any(
            bool(row["survivesValidationStrongly"]) for row in validation_transport_rows
        ),
        "cycleWitnessCount": len(cycle_rows),
        "openTransportWitnessCount": len(open_transport_rows),
        "loopTransportWitnessCount": len(loop_transport_rows),
        "reproTransportWitnessCount": len(repro_transport_rows),
        "denseTransportWitnessCount": len(dense_transport_rows),
        "validationTransportWitnessCount": len(validation_transport_rows),
        "topWitnesses": [
            {"kind": str(row["witnessKind"]), "id": str(row["id"])} for row in all_rows[:12]
        ],
        "topHotspots": hotspot_refs,
        "cycleWitnesses": cycle_rows,
        "openTransportWitnesses": open_transport_rows,
        "loopTransportWitnesses": loop_transport_rows,
        "reproTransportWitnesses": repro_transport_rows,
        "denseTransportWitnesses": dense_transport_rows,
        "validationTransportWitnesses": validation_transport_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package current cycle/transport evidence into an arrangement witness packet."
    )
    parser.add_argument("--cycle-lift-packet", help="Path to cycle-lift packet JSON")
    parser.add_argument(
        "--atlas-batch-packet",
        help="Path to open-path stateful atlas batch packet",
    )
    parser.add_argument("--transport-scale-report", help="Path to transport scale report JSON")
    parser.add_argument("--transport-repro-report", help="Path to transport repro report JSON")
    parser.add_argument("--transport-dense-report", help="Path to transport dense report JSON")
    parser.add_argument(
        "--transport-validation-report",
        help="Path to transport validation report JSON",
    )
    parser.add_argument("--hotspot-packet", help="Path to hotspot packet JSON")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not any(
        [
            args.cycle_lift_packet,
            args.atlas_batch_packet,
            args.transport_scale_report,
            args.transport_repro_report,
            args.transport_dense_report,
            args.transport_validation_report,
            args.hotspot_packet,
        ]
    ):
        raise SystemExit("at least one packet path is required")
    packet = build_arrangement_witness_packet(
        cycle_lift_packet=(
            Path(args.cycle_lift_packet).expanduser().resolve()
            if args.cycle_lift_packet
            else None
        ),
        atlas_batch_packet=(
            Path(args.atlas_batch_packet).expanduser().resolve()
            if args.atlas_batch_packet
            else None
        ),
        transport_scale_report=(
            Path(args.transport_scale_report).expanduser().resolve()
            if args.transport_scale_report
            else None
        ),
        transport_repro_report=(
            Path(args.transport_repro_report).expanduser().resolve()
            if args.transport_repro_report
            else None
        ),
        transport_dense_report=(
            Path(args.transport_dense_report).expanduser().resolve()
            if args.transport_dense_report
            else None
        ),
        transport_validation_report=(
            Path(args.transport_validation_report).expanduser().resolve()
            if args.transport_validation_report
            else None
        ),
        hotspot_packet=(
            Path(args.hotspot_packet).expanduser().resolve() if args.hotspot_packet else None
        ),
    )
    base_path = next(iter(packet["sourceArtifacts"].values()))
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (Path(base_path).expanduser().resolve().parent / "arrangement-witness-packet.json")
    )
    write_json(output_path, packet)
    print(
        "Arrangement witness packet:"
        f" cycle={packet['cycleWitnessCount']}"
        f" open={packet['openTransportWitnessCount']}"
        f" loop={packet['loopTransportWitnessCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
