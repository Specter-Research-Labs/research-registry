from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_AGDA_KEYWORDS = {
    "abstract",
    "constructor",
    "data",
    "do",
    "eta",
    "equality",
    "field",
    "forall",
    "hiding",
    "import",
    "in",
    "inductive",
    "infix",
    "infixl",
    "infixr",
    "instance",
    "let",
    "macro",
    "module",
    "mutual",
    "no",
    "open",
    "overlapping",
    "pattern",
    "postulate",
    "primitive",
    "private",
    "public",
    "quote",
    "record",
    "renaming",
    "rewrite",
    "syntax",
    "tactic",
    "unquote",
    "using",
    "variable",
    "where",
    "with",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _require_dict_list(value: Any, *, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{name} must be a JSON array of objects")
    return [row for row in value if isinstance(row, dict)]


def _safe_base(raw: str) -> str:
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", raw.lower()) if part]
    cleaned_parts: list[str] = []
    for part in parts:
        cleaned = f"{part}kw" if part in _AGDA_KEYWORDS else part
        if cleaned and cleaned[0].isdigit():
            cleaned = f"n{cleaned}"
        cleaned_parts.append(cleaned)
    cleaned = "_".join(cleaned_parts).strip("_")
    return cleaned or "value"


def _identifier_map(ids: list[str], prefix: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for raw in ids:
        base = f"{prefix}{_safe_base(raw)}"
        candidate = base
        index = 2
        while candidate in used:
            candidate = f"{base}_{index}"
            index += 1
        mapping[raw] = candidate
        used.add(candidate)
    return mapping


def _id_rows(
    rows: list[dict[str, Any]],
    *,
    prefix: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    id_map = _identifier_map([str(row["id"]) for row in rows], prefix)
    return (
        [
            {"id": str(row["id"]), "ctor": id_map[str(row["id"])]}
            for row in rows
        ],
        id_map,
    )


def build_agda_facing_packet(empirical_packet_path: Path) -> dict[str, Any]:
    packet = _read_json(empirical_packet_path)
    if packet.get("packetKind") != "empirical_fibration_packet_v1":
        raise SystemExit("agda-facing packet expects empirical_fibration_packet_v1")

    generators = _require_dict_list(packet.get("generators"), name="generators")
    cycle_edges = _require_dict_list(packet.get("cycleEdges"), name="cycleEdges")
    open_runs = _require_dict_list(packet.get("openTransportRuns"), name="openTransportRuns")
    transport_groups = _require_dict_list(packet.get("transportGroups"), name="transportGroups")
    repro_transport_groups = _require_dict_list(
        packet.get("reproTransportGroups", []),
        name="reproTransportGroups",
    )
    dense_transport_groups = _require_dict_list(
        packet.get("denseTransportGroups", []),
        name="denseTransportGroups",
    )
    validation_transport_groups = _require_dict_list(
        packet.get("validationTransportGroups", []),
        name="validationTransportGroups",
    )
    attractor_scales = _require_dict_list(packet.get("attractorScales"), name="attractorScales")
    attractor_components = _require_dict_list(
        packet.get("attractorComponents"),
        name="attractorComponents",
    )
    summary = packet.get("summary")
    thresholds = packet.get("thresholds")
    top_witnesses = _require_dict_list(packet.get("topWitnesses"), name="topWitnesses")
    top_hotspots = _require_dict_list(packet.get("topHotspots"), name="topHotspots")
    if not isinstance(summary, dict) or not isinstance(thresholds, dict):
        raise SystemExit("empirical fibration packet is missing summary or thresholds")

    generator_ids, generator_ctor_map = _id_rows(generators, prefix="g_")
    edge_ids, edge_ctor_map = _id_rows(cycle_edges, prefix="e_")
    open_ids, open_ctor_map = _id_rows(open_runs, prefix="ot_")
    group_ids, group_ctor_map = _id_rows(transport_groups, prefix="tg_")
    repro_group_ids, repro_group_ctor_map = _id_rows(
        repro_transport_groups,
        prefix="trg_",
    )
    dense_group_ids, dense_group_ctor_map = _id_rows(
        dense_transport_groups,
        prefix="tdg_",
    )
    validation_group_ids, validation_group_ctor_map = _id_rows(
        validation_transport_groups,
        prefix="tvg_",
    )
    scale_ids, scale_ctor_map = _id_rows(attractor_scales, prefix="as_")
    component_ids, component_ctor_map = _id_rows(attractor_components, prefix="ac_")

    generator_rows = [
        {
            "id": str(row["id"]),
            "ctor": generator_ctor_map[str(row["id"])],
            "persistenceRank": int(row["persistenceRank"]),
            "hasReentryEdge": bool(row["hasReentryEdge"]),
            "hasNonEndpointRepresentativeEdge": bool(
                row["hasNonEndpointRepresentativeEdge"]
            ),
            "hasAnchorInvariantEdge": bool(row["hasAnchorInvariantEdge"]),
            "interestingEdgeIds": [str(value) for value in row["interestingEdgeIds"]],
            "interestingEdgeCtors": [
                edge_ctor_map[str(value)]
                for value in row["interestingEdgeIds"]
                if str(value) in edge_ctor_map
            ],
        }
        for row in generators
    ]
    edge_rows = [
        {
            "id": str(row["id"]),
            "ctor": edge_ctor_map[str(row["id"])],
            "generatorId": str(row["generatorId"]),
            "generatorCtor": generator_ctor_map[str(row["generatorId"])],
            "hasReentry": bool(row["hasReentry"]),
            "visitsNonEndpointRepresentative": bool(
                row["visitsNonEndpointRepresentative"]
            ),
            "anchorInvariant": bool(row["anchorInvariant"]),
            "representativeVisitCount": int(row["representativeVisitCount"]),
            "branchSwitchCount": int(row["branchSwitchCount"]),
        }
        for row in cycle_edges
    ]
    open_rows = [
        {
            "id": str(row["id"]),
            "ctor": open_ctor_map[str(row["id"])],
            "coordinate": (
                str(row["coordinate"])
                if isinstance(row.get("coordinate"), str)
                else None
            ),
            "hiddenStateDominant": bool(row["hiddenStateDominant"]),
            "pointCount": int(row["pointCount"]),
        }
        for row in open_runs
    ]
    group_rows = [
        {
            "id": str(row["id"]),
            "ctor": group_ctor_map[str(row["id"])],
            "bestScaleByState": str(row["bestScaleByState"]),
            "bestScaleByRatio": str(row["bestScaleByRatio"]),
            "scaleCount": int(row["scaleCount"]),
            "loopBeatsControlByState": bool(row["loopBeatsControlByState"]),
            "loopBeatsControlByRatio": bool(row["loopBeatsControlByRatio"]),
        }
        for row in transport_groups
    ]
    repro_group_rows = [
        {
            "id": str(row["id"]),
            "ctor": repro_group_ctor_map[str(row["id"])],
            "kindCount": int(row["kindCount"]),
            "allKindsStable": bool(row["allKindsStable"]),
            "maxStateClosureRange": float(row["maxStateClosureRange"]),
            "maxRatioRange": float(row["maxRatioRange"]),
        }
        for row in repro_transport_groups
    ]
    dense_group_rows = [
        {
            "id": str(row["id"]),
            "ctor": dense_group_ctor_map[str(row["id"])],
            "controlGroup": str(row["controlGroup"]),
            "controlGroupCtor": group_ctor_map.get(str(row["controlGroup"])),
            "densePointCount": int(row["densePointCount"]),
            "denseStateClosure": float(row["denseStateClosure"]),
            "denseRatio": float(row["denseRatio"]),
            "sparseWinnerControlGroup": str(row["sparseWinnerControlGroup"]),
            "sparseWinnerControlGroupCtor": group_ctor_map.get(
                str(row["sparseWinnerControlGroup"])
            ),
        }
        for row in dense_transport_groups
    ]
    validation_group_rows = [
        {
            "id": str(row["id"]),
            "ctor": validation_group_ctor_map[str(row["id"])],
            "canonicalGroup": str(row["canonicalGroup"]),
            "winnerControlGroup": str(row["winnerControlGroup"]),
            "validationBestControlKind": str(row["validationBestControlKind"]),
            "validationDeltaStateClosure": float(row["validationDeltaStateClosure"]),
            "validationDeltaRatio": float(row["validationDeltaRatio"]),
            "survivesValidationByState": bool(row["survivesValidationByState"]),
            "survivesValidationByRatio": bool(row["survivesValidationByRatio"]),
            "survivesValidationStrongly": bool(row["survivesValidationStrongly"]),
        }
        for row in validation_transport_groups
    ]
    scale_rows = [
        {
            "id": str(row["id"]),
            "ctor": scale_ctor_map[str(row["id"])],
            "rank": int(row["rank"]),
            "componentCount": int(row["componentCount"]),
            "topComponentIds": [str(value) for value in row["topComponentIds"]],
            "topComponentCtors": [
                component_ctor_map[str(value)]
                for value in row["topComponentIds"]
                if str(value) in component_ctor_map
            ],
        }
        for row in attractor_scales
    ]
    component_rows = [
        {
            "id": str(row["id"]),
            "ctor": component_ctor_map[str(row["id"])],
            "scaleId": str(row["scaleId"]),
            "scaleCtor": scale_ctor_map[str(row["scaleId"])],
            "specimenCount": int(row["specimenCount"]),
            "representativeSpecimenId": str(row["representativeSpecimenId"]),
        }
        for row in attractor_components
    ]

    return {
        "version": 1,
        "packetKind": "agda_facing_packet_v1",
        "sourceEmpiricalFibrationPacket": str(empirical_packet_path),
        "suggestedModuleName": "Morphospace.Generated.EmpiricalFibration",
        "summary": {
            "topologyRepresentation": str(summary["topologyRepresentation"]),
            "attractorRepresentation": str(summary["attractorRepresentation"]),
            "supportsCycleLinkedReentry": bool(summary["supportsCycleLinkedReentry"]),
            "supportsHiddenStateDominance": bool(summary["supportsHiddenStateDominance"]),
            "supportsPositiveLoopSurplus": bool(summary["supportsPositiveLoopSurplus"]),
            "supportsTransportReproducibility": bool(
                summary.get("supportsTransportReproducibility", False)
            ),
            "supportsDenseWinnerExploration": bool(
                summary.get("supportsDenseWinnerExploration", False)
            ),
            "supportsValidatedLoopSurplus": bool(
                summary.get("supportsValidatedLoopSurplus", False)
            ),
            "generatorCount": len(generator_rows),
            "cycleEdgeCount": len(edge_rows),
            "openTransportCount": len(open_rows),
            "transportGroupCount": len(group_rows),
            "reproTransportGroupCount": len(repro_group_rows),
            "denseTransportGroupCount": len(dense_group_rows),
            "validationTransportGroupCount": len(validation_group_rows),
            "attractorScaleCount": len(scale_rows),
            "attractorComponentCount": len(component_rows),
        },
        "thresholds": {
            "hiddenStateDominanceRatioMin": float(thresholds["hiddenStateDominanceRatioMin"]),
            "positiveLoopSurplusMinStateClosure": float(
                thresholds["positiveLoopSurplusMinStateClosure"]
            ),
            "anchorInvariantMaxPhenotypeDelta": float(
                thresholds["anchorInvariantMaxPhenotypeDelta"]
            ),
        },
        "ids": {
            "generators": generator_ids,
            "cycleEdges": edge_ids,
            "openTransportRuns": open_ids,
            "transportGroups": group_ids,
            "reproTransportGroups": repro_group_ids,
            "denseTransportGroups": dense_group_ids,
            "validationTransportGroups": validation_group_ids,
            "attractorScales": scale_ids,
            "attractorComponents": component_ids,
        },
        "generators": generator_rows,
        "cycleEdges": edge_rows,
        "openTransportRuns": open_rows,
        "transportGroups": group_rows,
        "reproTransportGroups": repro_group_rows,
        "denseTransportGroups": dense_group_rows,
        "validationTransportGroups": validation_group_rows,
        "attractorScales": scale_rows,
        "attractorComponents": component_rows,
        "witnessSets": {
            "generatorHasReentry": [
                row["id"] for row in generator_rows if row["hasReentryEdge"]
            ],
            "generatorHasNonEndpointRepresentative": [
                row["id"] for row in generator_rows if row["hasNonEndpointRepresentativeEdge"]
            ],
            "generatorHasAnchorInvariantEdge": [
                row["id"] for row in generator_rows if row["hasAnchorInvariantEdge"]
            ],
            "edgeHasReentry": [row["id"] for row in edge_rows if row["hasReentry"]],
            "edgeVisitsNonEndpointRepresentative": [
                row["id"] for row in edge_rows if row["visitsNonEndpointRepresentative"]
            ],
            "edgeAnchorInvariant": [
                row["id"] for row in edge_rows if row["anchorInvariant"]
            ],
            "openTransportHiddenStateDominant": [
                row["id"] for row in open_rows if row["hiddenStateDominant"]
            ],
            "transportLoopBeatsControlByState": [
                row["id"] for row in group_rows if row["loopBeatsControlByState"]
            ],
            "transportLoopBeatsControlByRatio": [
                row["id"] for row in group_rows if row["loopBeatsControlByRatio"]
            ],
            "reproTransportAllKindsStable": [
                row["id"] for row in repro_group_rows if row["allKindsStable"]
            ],
            "validationTransportStrong": [
                row["id"] for row in validation_group_rows if row["survivesValidationStrongly"]
            ],
        },
        "topWitnesses": [
            {"kind": str(row["kind"]), "id": str(row["id"])}
            for row in top_witnesses
        ],
        "topHotspots": [
            {"kind": str(row["kind"]), "id": str(row["id"])}
            for row in top_hotspots
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize an empirical fibration packet into an Agda-facing packet."
    )
    parser.add_argument("--packet", required=True, help="Path to empirical fibration packet JSON")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = build_agda_facing_packet(packet_path)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (packet_path.parent / "agda-facing-packet.json").resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Agda-facing packet:"
        f" generators={packet['summary']['generatorCount']}"
        f" edges={packet['summary']['cycleEdgeCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
