from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, write_json


def _require_dict_list(value: Any, *, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{name} must be a JSON array of objects")
    return [row for row in value if isinstance(row, dict)]


def _edge_id(generator_id: str, edge_index: int) -> str:
    return f"{generator_id}:edge{edge_index:02d}"


def _anchor_invariant(row: dict[str, Any]) -> bool:
    payload = row.get("anchorInvariance")
    if not isinstance(payload, dict):
        return False
    return (
        int(payload["labelDisagreementCount"]) == 0
        and float(payload["maxAnchorPhenotypeDelta"]) == 0.0
    )


def _generator_rows(
    cycle_packet: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    generators = _require_dict_list(
        cycle_packet.get("generators"),
        name="cycle-lift packet generators",
    )

    ranked = sorted(
        generators,
        key=lambda row: (-float(row["persistence"]), str(row["generatorId"])),
    )
    rank_by_id = {
        str(row["generatorId"]): index for index, row in enumerate(ranked, start=1)
    }

    generator_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    for row in ranked:
        generator_id = str(row["generatorId"])
        edges = _require_dict_list(
            row.get("edges"),
            name=f"cycle-lift generator {generator_id} edges",
        )
        interesting = {int(index) for index in row.get("interestingEdges", [])}
        generator_rows.append(
            {
                "id": generator_id,
                "persistenceRank": rank_by_id[generator_id],
                "edgeCount": int(row["edgeCount"]),
                "reentryEdgeCount": int(row["reentryEdgeCount"]),
                "nonEndpointRepresentativeEdgeCount": int(
                    row["nonEndpointRepresentativeEdgeCount"]
                ),
                "anchorInvariantEdgeCount": int(row["anchorInvariantEdgeCount"]),
                "maxRepresentativeVisitCount": int(row["maxRepresentativeVisitCount"]),
                "hasReentryEdge": int(row["reentryEdgeCount"]) > 0,
                "hasNonEndpointRepresentativeEdge": int(
                    row["nonEndpointRepresentativeEdgeCount"]
                )
                > 0,
                "hasAnchorInvariantEdge": int(row["anchorInvariantEdgeCount"]) > 0,
                "interestingEdgeIds": [
                    _edge_id(generator_id, int(edge["edgeIndex"]))
                    for edge in edges
                    if int(edge["edgeIndex"]) in interesting
                ],
            }
        )
        for edge in sorted(edges, key=lambda edge: int(edge["edgeIndex"])):
            edge_rows.append(
                {
                    "id": _edge_id(generator_id, int(edge["edgeIndex"])),
                    "generatorId": generator_id,
                    "edgeIndex": int(edge["edgeIndex"]),
                    "fromSpecimenId": str(edge["fromSpecimenId"]),
                    "toSpecimenId": str(edge["toSpecimenId"]),
                    "branchSwitchCount": int(edge["branchSwitchCount"]),
                    "ambiguousCount": int(edge["ambiguousCount"]),
                    "representativeVisitCount": int(edge["representativeVisitCount"]),
                    "hasReentry": bool(edge["hasReentry"]),
                    "visitsNonEndpointRepresentative": bool(
                        edge["visitsNonEndpointRepresentative"]
                    ),
                    "anchorInvariant": _anchor_invariant(edge),
                }
            )
    return generator_rows, edge_rows


def _open_transport_rows(arrangement_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _require_dict_list(
        arrangement_packet.get("openTransportWitnesses"),
        name="arrangement packet openTransportWitnesses",
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": str(row["id"]),
                "bundle": str(row["bundle"]),
                "coordinate": (
                    str(row["coordinate"])
                    if isinstance(row.get("coordinate"), str)
                    else None
                ),
                "pointCount": int(row["pointCount"]),
                "hiddenStateDominant": float(row["transportToPhenotypeRatio"]) > 1.0,
            }
        )
    return result


def _transport_group_rows(arrangement_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _require_dict_list(
        arrangement_packet.get("loopTransportWitnesses"),
        name="arrangement packet loopTransportWitnesses",
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        best_state = row.get("bestScaleByStateClosure")
        best_ratio = row.get("bestScaleByRatio")
        if not isinstance(best_state, dict) or not isinstance(best_ratio, dict):
            raise SystemExit("arrangement packet loop transport witness is missing best scales")
        delta_state = best_state.get("deltaStateClosure")
        delta_ratio = best_ratio.get("deltaRatio")
        result.append(
            {
                "id": str(row["id"]),
                "bestScaleByState": str(best_state["scale"]),
                "bestScaleByRatio": str(best_ratio["scale"]),
                "scaleCount": int(row["scaleCount"]),
                "loopBeatsControlByState": float(delta_state or 0.0) > 0.0,
                "loopBeatsControlByRatio": float(delta_ratio or 0.0) > 0.0,
            }
        )
    return result


def _repro_transport_rows(arrangement_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _require_dict_list(
        arrangement_packet.get("reproTransportWitnesses"),
        name="arrangement packet reproTransportWitnesses",
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": str(row["id"]),
                "kindCount": int(row["kindCount"]),
                "allKindsStable": bool(row["allKindsStable"]),
                "maxStateClosureRange": float(row["maxStateClosureRange"]),
                "maxRatioRange": float(row["maxRatioRange"]),
            }
        )
    return result


def _dense_transport_rows(arrangement_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _require_dict_list(
        arrangement_packet.get("denseTransportWitnesses"),
        name="arrangement packet denseTransportWitnesses",
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": str(row["id"]),
                "controlGroup": str(row["controlGroup"]),
                "densePointCount": int(row["densePointCount"]),
                "denseStateClosure": float(row["denseStateClosure"]),
                "denseRatio": float(row["denseRatio"]),
                "sparseWinnerControlGroup": str(row["sparseWinnerControlGroup"]),
            }
        )
    return result


def _validation_transport_rows(arrangement_packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = arrangement_packet.get("validationTransportWitnesses")
    if rows is None:
        return []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit("arrangement packet validationTransportWitnesses must be an array")
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": str(row["id"]),
                "canonicalGroup": str(row["canonicalGroup"]),
                "winnerControlGroup": str(row["winnerControlGroup"]),
                "validationBestControlKind": str(row["validationBestControlKind"]),
                "validationDeltaStateClosure": float(row["validationDeltaStateClosure"]),
                "validationDeltaRatio": float(row["validationDeltaRatio"]),
                "survivesValidationByState": bool(row["survivesValidationByState"]),
                "survivesValidationByRatio": bool(row["survivesValidationByRatio"]),
                "survivesValidationStrongly": bool(row["survivesValidationStrongly"]),
            }
        )
    return result


def _attractor_rows(
    attractor_packet: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scales = _require_dict_list(
        attractor_packet.get("scales"),
        name="attractor packet scales",
    )
    scale_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    for scale in scales:
        rank = int(scale["rank"])
        scale_id = f"h0_scale_rank_{rank:02d}"
        components = _require_dict_list(
            scale.get("components"),
            name=f"attractor scale {rank} components",
        )
        component_ids: list[str] = []
        for index, component in enumerate(components, start=1):
            component_id = f"{scale_id}_component_{index:02d}"
            component_ids.append(component_id)
            representative = component.get("representative")
            if not isinstance(representative, dict):
                raise SystemExit(f"attractor component {component_id} is missing representative")
            component_rows.append(
                {
                    "id": component_id,
                    "scaleId": scale_id,
                    "specimenCount": int(component["specimenCount"]),
                    "runCount": int(component["runCount"]),
                    "campaignCount": int(component["campaignCount"]),
                    "representativeSpecimenId": str(representative["specimenId"]),
                    "representativeDominantOrder": int(representative["dominantOrder"]),
                    "membershipHash12": str(component["membershipHash12"]),
                }
            )
        scale_rows.append(
            {
                "id": scale_id,
                "rank": rank,
                "componentCount": int(scale["componentCount"]),
                "topComponentIds": component_ids,
            }
        )
    return scale_rows, component_rows


def build_empirical_fibration_packet(
    *,
    arrangement_packet_path: Path,
    cycle_lift_packet_path: Path,
    attractor_packet_path: Path,
) -> dict[str, Any]:
    arrangement_packet = read_json(arrangement_packet_path)
    cycle_packet = read_json(cycle_lift_packet_path)
    attractor_packet = read_json(attractor_packet_path)

    generator_rows, edge_rows = _generator_rows(cycle_packet)
    open_transport_rows = _open_transport_rows(arrangement_packet)
    transport_group_rows = _transport_group_rows(arrangement_packet)
    repro_transport_rows = _repro_transport_rows(arrangement_packet)
    dense_transport_rows = _dense_transport_rows(arrangement_packet)
    validation_transport_rows = _validation_transport_rows(arrangement_packet)
    attractor_scales, attractor_components = _attractor_rows(attractor_packet)

    top_witnesses = arrangement_packet.get("topWitnesses")
    if not isinstance(top_witnesses, list):
        raise SystemExit("arrangement packet is missing topWitnesses[]")
    top_hotspots = arrangement_packet.get("topHotspots")
    if not isinstance(top_hotspots, list):
        raise SystemExit("arrangement packet is missing topHotspots[]")

    return {
        "version": 1,
        "packetKind": "empirical_fibration_packet_v1",
        "sourceArtifacts": {
            "arrangementPacket": str(arrangement_packet_path),
            "cycleLiftPacket": str(cycle_lift_packet_path),
            "attractorPacket": str(attractor_packet_path),
        },
        "thresholds": {
            "hiddenStateDominanceRatioMin": 1.0,
            "positiveLoopSurplusMinStateClosure": 0.0,
            "anchorInvariantMaxPhenotypeDelta": 0.0,
        },
        "summary": {
            "topologyRepresentation": str(cycle_packet["representation"]),
            "attractorRepresentation": str(attractor_packet["representation"]),
            "supportsCycleLinkedReentry": bool(
                arrangement_packet["supportsCycleLinkedReentry"]
            ),
            "supportsHiddenStateDominance": bool(
                arrangement_packet["supportsHiddenStateDominance"]
            ),
            "supportsPositiveLoopSurplus": bool(
                arrangement_packet["supportsPositiveLoopSurplus"]
            ),
            "supportsTransportReproducibility": bool(
                arrangement_packet["supportsTransportReproducibility"]
            ),
            "supportsDenseWinnerExploration": bool(
                arrangement_packet["supportsDenseWinnerExploration"]
            ),
            "supportsValidatedLoopSurplus": bool(
                arrangement_packet.get("supportsValidatedLoopSurplus", False)
            ),
            "generatorCount": len(generator_rows),
            "cycleEdgeCount": len(edge_rows),
            "openTransportCount": len(open_transport_rows),
            "transportGroupCount": len(transport_group_rows),
            "reproTransportGroupCount": len(repro_transport_rows),
            "denseTransportGroupCount": len(dense_transport_rows),
            "validationTransportGroupCount": len(validation_transport_rows),
            "attractorScaleCount": len(attractor_scales),
            "attractorComponentCount": len(attractor_components),
        },
        "topWitnesses": [
            {"kind": str(row["kind"]), "id": str(row["id"])}
            for row in top_witnesses
            if isinstance(row, dict)
            and isinstance(row.get("kind"), str)
            and isinstance(row.get("id"), str)
        ],
        "topHotspots": [
            {"kind": str(row["kind"]), "id": str(row["id"])}
            for row in top_hotspots
            if isinstance(row, dict)
            and isinstance(row.get("kind"), str)
            and isinstance(row.get("id"), str)
        ],
        "generators": generator_rows,
        "cycleEdges": edge_rows,
        "openTransportRuns": open_transport_rows,
        "transportGroups": transport_group_rows,
        "reproTransportGroups": repro_transport_rows,
        "denseTransportGroups": dense_transport_rows,
        "validationTransportGroups": validation_transport_rows,
        "attractorScales": attractor_scales,
        "attractorComponents": attractor_components,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a finite Agda-facing empirical fibration packet."
    )
    parser.add_argument("--arrangement-packet", required=True, help="Path to arrangement packet")
    parser.add_argument("--cycle-lift-packet", required=True, help="Path to cycle-lift packet")
    parser.add_argument("--attractor-packet", required=True, help="Path to attractor packet")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    arrangement_packet_path = Path(args.arrangement_packet).expanduser().resolve()
    cycle_lift_packet_path = Path(args.cycle_lift_packet).expanduser().resolve()
    attractor_packet_path = Path(args.attractor_packet).expanduser().resolve()
    packet = build_empirical_fibration_packet(
        arrangement_packet_path=arrangement_packet_path,
        cycle_lift_packet_path=cycle_lift_packet_path,
        attractor_packet_path=attractor_packet_path,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (arrangement_packet_path.parent / "empirical-fibration-packet.json").resolve()
    )
    write_json(output_path, packet)
    print(
        "Empirical fibration packet:"
        f" generators={packet['summary']['generatorCount']}"
        f" edges={packet['summary']['cycleEdgeCount']}"
        f" transportGroups={packet['summary']['transportGroupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
