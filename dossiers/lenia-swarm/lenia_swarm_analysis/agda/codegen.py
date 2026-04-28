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


def _require_dict_list(value: Any, *, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{name} must be a JSON array of objects")
    return [row for row in value if isinstance(row, dict)]


def _escape_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
    return f"\"{escaped}\""


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _list(items: list[str]) -> str:
    if not items:
        return "[]"
    return " ∷ ".join(items) + " ∷ []"


def _maybe_string(value: str | None) -> str:
    if value is None:
        return "nothing"
    return f"just {_escape_string(value)}"


def _scale_ctor(raw: str) -> str:
    return {
        "small": "small",
        "medium": "medium",
        "large": "large",
    }.get(raw, "other")


def _emit_data_type(lines: list[str], type_name: str, ctors: list[str]) -> None:
    lines.append(f"data {type_name} : Set where")
    if not ctors:
        lines.append("")
        return
    for ctor in ctors:
        lines.append(f"  {ctor} : {type_name}")
    lines.append("")


def _emit_lookup(
    lines: list[str],
    name: str,
    domain: str,
    codomain: str,
    entries: list[tuple[str, str]],
) -> None:
    lines.append(f"{name} : {domain} → {codomain}")
    for ctor, value in entries:
        lines.append(f"{name} {ctor} = {value}")
    lines.append("")


def _module_prelude(
    module_name: str,
    *,
    include_maybe: bool = True,
    options: list[str] | None = None,
) -> list[str]:
    lines: list[str] = []
    if options:
        lines.append("{-# OPTIONS " + " ".join(options) + " #-}")
        lines.append("")
    lines.extend(
        [
            f"module {module_name} where",
            "",
            "open import Agda.Builtin.Bool using (Bool; true; false)",
            "open import Agda.Builtin.List using (List; []; _∷_)",
            "open import Agda.Builtin.Nat using (Nat)",
            "open import Agda.Builtin.String using (String)",
        ]
    )
    if include_maybe:
        lines.append("open import Agda.Builtin.Maybe using (Maybe; just; nothing)")
    lines.append("")
    return lines


def _packet_sections(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("packetKind") != "agda_facing_packet_v1":
        raise SystemExit("agda codegen expects agda_facing_packet_v1")

    summary = packet.get("summary")
    if not isinstance(summary, dict):
        raise SystemExit("agda-facing packet is missing summary")

    return {
        "summary": summary,
        "generators": _require_dict_list(packet.get("generators"), name="generators"),
        "cycle_edges": _require_dict_list(packet.get("cycleEdges"), name="cycleEdges"),
        "open_runs": _require_dict_list(
            packet.get("openTransportRuns"),
            name="openTransportRuns",
        ),
        "transport_groups": _require_dict_list(
            packet.get("transportGroups"),
            name="transportGroups",
        ),
        "attractor_scales": _require_dict_list(
            packet.get("attractorScales"),
            name="attractorScales",
        ),
        "attractor_components": _require_dict_list(
            packet.get("attractorComponents"),
            name="attractorComponents",
        ),
        "top_witnesses": _require_dict_list(
            packet.get("topWitnesses"),
            name="topWitnesses",
        ),
        "top_hotspots": _require_dict_list(
            packet.get("topHotspots"),
            name="topHotspots",
        ),
    }


def _render_ids_module(packet: dict[str, Any], *, module_name: str) -> str:
    sections = _packet_sections(packet)
    generators = sections["generators"]
    cycle_edges = sections["cycle_edges"]
    open_runs = sections["open_runs"]
    transport_groups = sections["transport_groups"]
    attractor_scales = sections["attractor_scales"]
    attractor_components = sections["attractor_components"]

    lines = _module_prelude(
        module_name,
        include_maybe=False,
        options=["--cubical-compatible"],
    )
    lines.extend(
        [
            "data Scale : Set where",
            "  small : Scale",
            "  medium : Scale",
            "  large : Scale",
            "  other : Scale",
            "",
        ]
    )
    _emit_data_type(lines, "GeneratorId", [str(row["ctor"]) for row in generators])
    _emit_data_type(lines, "EdgeId", [str(row["ctor"]) for row in cycle_edges])
    _emit_data_type(lines, "OpenTransportId", [str(row["ctor"]) for row in open_runs])
    _emit_data_type(
        lines,
        "TransportGroupId",
        [str(row["ctor"]) for row in transport_groups],
    )
    _emit_data_type(
        lines,
        "AttractorScaleId",
        [str(row["ctor"]) for row in attractor_scales],
    )
    _emit_data_type(
        lines,
        "AttractorComponentId",
        [str(row["ctor"]) for row in attractor_components],
    )
    lines.extend(
        [
            "allGenerators : List GeneratorId",
            _render_all("allGenerators", [str(row["ctor"]) for row in generators]),
            "",
            "allCycleEdges : List EdgeId",
            _render_all("allCycleEdges", [str(row["ctor"]) for row in cycle_edges]),
            "",
            "allOpenTransportRuns : List OpenTransportId",
            _render_all("allOpenTransportRuns", [str(row["ctor"]) for row in open_runs]),
            "",
            "allTransportGroups : List TransportGroupId",
            _render_all(
                "allTransportGroups",
                [str(row["ctor"]) for row in transport_groups],
            ),
            "",
            "allAttractorScales : List AttractorScaleId",
            _render_all(
                "allAttractorScales",
                [str(row["ctor"]) for row in attractor_scales],
            ),
            "",
            "allAttractorComponents : List AttractorComponentId",
            _render_all(
                "allAttractorComponents",
                [str(row["ctor"]) for row in attractor_components],
            ),
            "",
        ]
    )
    _emit_lookup(
        lines,
        "generatorSourceId",
        "GeneratorId",
        "String",
        [(str(row["ctor"]), _escape_string(str(row["id"]))) for row in generators],
    )
    _emit_lookup(
        lines,
        "edgeSourceId",
        "EdgeId",
        "String",
        [(str(row["ctor"]), _escape_string(str(row["id"]))) for row in cycle_edges],
    )
    _emit_lookup(
        lines,
        "openTransportSourceId",
        "OpenTransportId",
        "String",
        [(str(row["ctor"]), _escape_string(str(row["id"]))) for row in open_runs],
    )
    _emit_lookup(
        lines,
        "transportGroupSourceId",
        "TransportGroupId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "attractorScaleSourceId",
        "AttractorScaleId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in attractor_scales
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentSourceId",
        "AttractorComponentId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in attractor_components
        ],
    )
    return "\n".join(lines) + "\n"


def _render_witnesses_module(
    packet: dict[str, Any],
    *,
    module_name: str,
    ids_module_name: str,
) -> str:
    sections = _packet_sections(packet)
    generators = sections["generators"]
    cycle_edges = sections["cycle_edges"]
    open_runs = sections["open_runs"]
    transport_groups = sections["transport_groups"]
    summary = sections["summary"]
    top_witnesses = sections["top_witnesses"]
    top_hotspots = sections["top_hotspots"]

    lines = _module_prelude(module_name, options=["--cubical-compatible"])
    lines.append(f"open import {ids_module_name}")
    lines.append("")
    _emit_lookup(
        lines,
        "generatorPersistenceRank",
        "GeneratorId",
        "Nat",
        [(str(row["ctor"]), str(int(row["persistenceRank"]))) for row in generators],
    )
    _emit_lookup(
        lines,
        "generatorHasReentry",
        "GeneratorId",
        "Bool",
        [(str(row["ctor"]), _bool(bool(row["hasReentryEdge"]))) for row in generators],
    )
    _emit_lookup(
        lines,
        "generatorHasNonEndpointRepresentative",
        "GeneratorId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["hasNonEndpointRepresentativeEdge"])),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "generatorHasAnchorInvariantEdge",
        "GeneratorId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["hasAnchorInvariantEdge"])))
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "interestingEdgesOfGenerator",
        "GeneratorId",
        "List EdgeId",
        [
            (
                str(row["ctor"]),
                _list([str(value) for value in row["interestingEdgeCtors"]]),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "edgeGenerator",
        "EdgeId",
        "GeneratorId",
        [(str(row["ctor"]), str(row["generatorCtor"])) for row in cycle_edges],
    )
    _emit_lookup(
        lines,
        "edgeHasReentry",
        "EdgeId",
        "Bool",
        [(str(row["ctor"]), _bool(bool(row["hasReentry"]))) for row in cycle_edges],
    )
    _emit_lookup(
        lines,
        "edgeVisitsNonEndpointRepresentative",
        "EdgeId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["visitsNonEndpointRepresentative"])),
            )
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeAnchorInvariant",
        "EdgeId",
        "Bool",
        [(str(row["ctor"]), _bool(bool(row["anchorInvariant"]))) for row in cycle_edges],
    )
    _emit_lookup(
        lines,
        "edgeRepresentativeVisitCount",
        "EdgeId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["representativeVisitCount"])))
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeBranchSwitchCount",
        "EdgeId",
        "Nat",
        [(str(row["ctor"]), str(int(row["branchSwitchCount"]))) for row in cycle_edges],
    )
    _emit_lookup(
        lines,
        "openTransportCoordinate",
        "OpenTransportId",
        "Maybe String",
        [
            (
                str(row["ctor"]),
                _maybe_string(
                    str(row["coordinate"]) if row.get("coordinate") is not None else None
                ),
            )
            for row in open_runs
        ],
    )
    _emit_lookup(
        lines,
        "openTransportHiddenStateDominant",
        "OpenTransportId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["hiddenStateDominant"])))
            for row in open_runs
        ],
    )
    _emit_lookup(
        lines,
        "transportBestScaleByState",
        "TransportGroupId",
        "Scale",
        [
            (str(row["ctor"]), _scale_ctor(str(row["bestScaleByState"])))
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportBestScaleByRatio",
        "TransportGroupId",
        "Scale",
        [
            (str(row["ctor"]), _scale_ctor(str(row["bestScaleByRatio"])))
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportLoopBeatsControlByState",
        "TransportGroupId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["loopBeatsControlByState"])))
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportLoopBeatsControlByRatio",
        "TransportGroupId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["loopBeatsControlByRatio"])))
            for row in transport_groups
        ],
    )

    top_witness_kinds = [_escape_string(str(row["kind"])) for row in top_witnesses]
    top_witness_ids = [_escape_string(str(row["id"])) for row in top_witnesses]
    top_hotspot_kinds = [_escape_string(str(row["kind"])) for row in top_hotspots]
    top_hotspot_ids = [_escape_string(str(row["id"])) for row in top_hotspots]

    lines.extend(
        [
            "supportsCycleLinkedReentry : Bool",
            f"supportsCycleLinkedReentry = {_bool(bool(summary['supportsCycleLinkedReentry']))}",
            "",
            "supportsHiddenStateDominance : Bool",
            "supportsHiddenStateDominance = "
            f"{_bool(bool(summary['supportsHiddenStateDominance']))}",
            "",
            "supportsPositiveLoopSurplus : Bool",
            f"supportsPositiveLoopSurplus = {_bool(bool(summary['supportsPositiveLoopSurplus']))}",
            "",
            "topologyRepresentation : String",
            f"topologyRepresentation = {_escape_string(str(summary['topologyRepresentation']))}",
            "",
            "attractorRepresentation : String",
            f"attractorRepresentation = {_escape_string(str(summary['attractorRepresentation']))}",
            "",
            "topWitnessKinds : List String",
            f"topWitnessKinds = {_list(top_witness_kinds)}",
            "",
            "topWitnessIds : List String",
            f"topWitnessIds = {_list(top_witness_ids)}",
            "",
            "topHotspotKinds : List String",
            f"topHotspotKinds = {_list(top_hotspot_kinds)}",
            "",
            "topHotspotIds : List String",
            f"topHotspotIds = {_list(top_hotspot_ids)}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_attractors_module(
    packet: dict[str, Any],
    *,
    module_name: str,
    ids_module_name: str,
) -> str:
    sections = _packet_sections(packet)
    attractor_scales = sections["attractor_scales"]
    attractor_components = sections["attractor_components"]

    lines = _module_prelude(
        module_name,
        include_maybe=False,
        options=["--cubical-compatible"],
    )
    lines.append(f"open import {ids_module_name}")
    lines.append("")
    _emit_lookup(
        lines,
        "attractorScaleRank",
        "AttractorScaleId",
        "Nat",
        [(str(row["ctor"]), str(int(row["rank"]))) for row in attractor_scales],
    )
    _emit_lookup(
        lines,
        "attractorScaleComponentCount",
        "AttractorScaleId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["componentCount"])))
            for row in attractor_scales
        ],
    )
    _emit_lookup(
        lines,
        "attractorScaleTopComponents",
        "AttractorScaleId",
        "List AttractorComponentId",
        [
            (
                str(row["ctor"]),
                _list([str(value) for value in row["topComponentCtors"]]),
            )
            for row in attractor_scales
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentScale",
        "AttractorComponentId",
        "AttractorScaleId",
        [(str(row["ctor"]), str(row["scaleCtor"])) for row in attractor_components],
    )
    _emit_lookup(
        lines,
        "attractorComponentSpecimenCount",
        "AttractorComponentId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["specimenCount"])))
            for row in attractor_components
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentRepresentativeSpecimenId",
        "AttractorComponentId",
        "String",
        [
            (
                str(row["ctor"]),
                _escape_string(str(row["representativeSpecimenId"])),
            )
            for row in attractor_components
        ],
    )
    return "\n".join(lines) + "\n"


def render_agda_package(
    packet: dict[str, Any],
    *,
    root_module: str,
) -> dict[str, str]:
    generated_prefix = f"{root_module}.Generated"
    ids_module = f"{generated_prefix}.Ids"
    witnesses_module = f"{generated_prefix}.Witnesses"
    attractors_module = f"{generated_prefix}.Attractors"
    return {
        "Generated/Ids.agda": _render_ids_module(packet, module_name=ids_module),
        "Generated/Witnesses.agda": _render_witnesses_module(
            packet,
            module_name=witnesses_module,
            ids_module_name=ids_module,
        ),
        "Generated/Attractors.agda": _render_attractors_module(
            packet,
            module_name=attractors_module,
            ids_module_name=ids_module,
        ),
    }


def render_agda_module(packet: dict[str, Any], *, module_name: str) -> str:
    if packet.get("packetKind") != "agda_facing_packet_v1":
        raise SystemExit("agda codegen expects agda_facing_packet_v1")

    generators = _require_dict_list(packet.get("generators"), name="generators")
    cycle_edges = _require_dict_list(packet.get("cycleEdges"), name="cycleEdges")
    open_runs = _require_dict_list(packet.get("openTransportRuns"), name="openTransportRuns")
    transport_groups = _require_dict_list(packet.get("transportGroups"), name="transportGroups")
    attractor_scales = _require_dict_list(packet.get("attractorScales"), name="attractorScales")
    attractor_components = _require_dict_list(
        packet.get("attractorComponents"),
        name="attractorComponents",
    )
    top_witnesses = _require_dict_list(packet.get("topWitnesses"), name="topWitnesses")
    top_hotspots = _require_dict_list(packet.get("topHotspots"), name="topHotspots")
    summary = packet.get("summary")
    if not isinstance(summary, dict):
        raise SystemExit("agda-facing packet is missing summary")

    lines = [
        f"module {module_name} where",
        "",
        "open import Agda.Builtin.Bool using (Bool; true; false)",
        "open import Agda.Builtin.List using (List; []; _∷_)",
        "open import Agda.Builtin.Maybe using (Maybe; just; nothing)",
        "open import Agda.Builtin.Nat using (Nat)",
        "open import Agda.Builtin.String using (String)",
        "",
        "data Scale : Set where",
        "  small : Scale",
        "  medium : Scale",
        "  large : Scale",
        "  other : Scale",
        "",
    ]

    _emit_data_type(lines, "GeneratorId", [str(row["ctor"]) for row in generators])
    _emit_data_type(lines, "EdgeId", [str(row["ctor"]) for row in cycle_edges])
    _emit_data_type(lines, "OpenTransportId", [str(row["ctor"]) for row in open_runs])
    _emit_data_type(lines, "TransportGroupId", [str(row["ctor"]) for row in transport_groups])
    _emit_data_type(lines, "AttractorScaleId", [str(row["ctor"]) for row in attractor_scales])
    _emit_data_type(
        lines,
        "AttractorComponentId",
        [str(row["ctor"]) for row in attractor_components],
    )

    lines.extend(
        [
            "allGenerators : List GeneratorId",
            _render_all("allGenerators", [str(row["ctor"]) for row in generators]),
            "",
            "allCycleEdges : List EdgeId",
            _render_all("allCycleEdges", [str(row["ctor"]) for row in cycle_edges]),
            "",
            "allOpenTransportRuns : List OpenTransportId",
            _render_all("allOpenTransportRuns", [str(row["ctor"]) for row in open_runs]),
            "",
            "allTransportGroups : List TransportGroupId",
            _render_all("allTransportGroups", [str(row["ctor"]) for row in transport_groups]),
            "",
            "allAttractorScales : List AttractorScaleId",
            _render_all("allAttractorScales", [str(row["ctor"]) for row in attractor_scales]),
            "",
            "allAttractorComponents : List AttractorComponentId",
            _render_all(
                "allAttractorComponents",
                [str(row["ctor"]) for row in attractor_components],
            ),
            "",
        ]
    )

    _emit_lookup(
        lines,
        "generatorSourceId",
        "GeneratorId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "edgeSourceId",
        "EdgeId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "transportGroupSourceId",
        "TransportGroupId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentSourceId",
        "AttractorComponentId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in attractor_components
        ],
    )

    _emit_lookup(
        lines,
        "generatorPersistenceRank",
        "GeneratorId",
        "Nat",
        [
            (
                str(row["ctor"]),
                str(int(row["persistenceRank"])),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "generatorHasReentry",
        "GeneratorId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["hasReentryEdge"])),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "generatorHasNonEndpointRepresentative",
        "GeneratorId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["hasNonEndpointRepresentativeEdge"])),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "generatorHasAnchorInvariantEdge",
        "GeneratorId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["hasAnchorInvariantEdge"])),
            )
            for row in generators
        ],
    )
    _emit_lookup(
        lines,
        "interestingEdgesOfGenerator",
        "GeneratorId",
        "List EdgeId",
        [
            (
                str(row["ctor"]),
                _list([str(value) for value in row["interestingEdgeCtors"]]),
            )
            for row in generators
        ],
    )

    _emit_lookup(
        lines,
        "edgeGenerator",
        "EdgeId",
        "GeneratorId",
        [
            (
                str(row["ctor"]),
                str(row["generatorCtor"]),
            )
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeHasReentry",
        "EdgeId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["hasReentry"])))
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeVisitsNonEndpointRepresentative",
        "EdgeId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["visitsNonEndpointRepresentative"])),
            )
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeAnchorInvariant",
        "EdgeId",
        "Bool",
        [
            (str(row["ctor"]), _bool(bool(row["anchorInvariant"])))
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeRepresentativeVisitCount",
        "EdgeId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["representativeVisitCount"])))
            for row in cycle_edges
        ],
    )
    _emit_lookup(
        lines,
        "edgeBranchSwitchCount",
        "EdgeId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["branchSwitchCount"])))
            for row in cycle_edges
        ],
    )

    _emit_lookup(
        lines,
        "openTransportSourceId",
        "OpenTransportId",
        "String",
        [
            (str(row["ctor"]), _escape_string(str(row["id"])))
            for row in open_runs
        ],
    )
    _emit_lookup(
        lines,
        "openTransportCoordinate",
        "OpenTransportId",
        "Maybe String",
        [
            (
                str(row["ctor"]),
                _maybe_string(
                    str(row["coordinate"]) if row.get("coordinate") is not None else None
                ),
            )
            for row in open_runs
        ],
    )
    _emit_lookup(
        lines,
        "openTransportHiddenStateDominant",
        "OpenTransportId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["hiddenStateDominant"])),
            )
            for row in open_runs
        ],
    )

    _emit_lookup(
        lines,
        "transportBestScaleByState",
        "TransportGroupId",
        "Scale",
        [
            (
                str(row["ctor"]),
                _scale_ctor(str(row["bestScaleByState"])),
            )
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportBestScaleByRatio",
        "TransportGroupId",
        "Scale",
        [
            (
                str(row["ctor"]),
                _scale_ctor(str(row["bestScaleByRatio"])),
            )
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportLoopBeatsControlByState",
        "TransportGroupId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["loopBeatsControlByState"])),
            )
            for row in transport_groups
        ],
    )
    _emit_lookup(
        lines,
        "transportLoopBeatsControlByRatio",
        "TransportGroupId",
        "Bool",
        [
            (
                str(row["ctor"]),
                _bool(bool(row["loopBeatsControlByRatio"])),
            )
            for row in transport_groups
        ],
    )

    _emit_lookup(
        lines,
        "attractorScaleRank",
        "AttractorScaleId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["rank"])))
            for row in attractor_scales
        ],
    )
    _emit_lookup(
        lines,
        "attractorScaleComponentCount",
        "AttractorScaleId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["componentCount"])))
            for row in attractor_scales
        ],
    )
    _emit_lookup(
        lines,
        "attractorScaleTopComponents",
        "AttractorScaleId",
        "List AttractorComponentId",
        [
            (
                str(row["ctor"]),
                _list([str(value) for value in row["topComponentCtors"]]),
            )
            for row in attractor_scales
        ],
    )

    _emit_lookup(
        lines,
        "attractorComponentScale",
        "AttractorComponentId",
        "AttractorScaleId",
        [
            (
                str(row["ctor"]),
                str(row["scaleCtor"]),
            )
            for row in attractor_components
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentSpecimenCount",
        "AttractorComponentId",
        "Nat",
        [
            (str(row["ctor"]), str(int(row["specimenCount"])))
            for row in attractor_components
        ],
    )
    _emit_lookup(
        lines,
        "attractorComponentRepresentativeSpecimenId",
        "AttractorComponentId",
        "String",
        [
            (
                str(row["ctor"]),
                _escape_string(str(row["representativeSpecimenId"])),
            )
            for row in attractor_components
        ],
    )

    top_witness_kinds = [_escape_string(str(row["kind"])) for row in top_witnesses]
    top_witness_ids = [_escape_string(str(row["id"])) for row in top_witnesses]
    top_hotspot_kinds = [_escape_string(str(row["kind"])) for row in top_hotspots]
    top_hotspot_ids = [_escape_string(str(row["id"])) for row in top_hotspots]
    supports_cycle = _bool(bool(summary["supportsCycleLinkedReentry"]))
    supports_hidden = _bool(bool(summary["supportsHiddenStateDominance"]))
    supports_loop = _bool(bool(summary["supportsPositiveLoopSurplus"]))
    topology_representation = _escape_string(str(summary["topologyRepresentation"]))
    attractor_representation = _escape_string(str(summary["attractorRepresentation"]))

    lines.extend(
        [
            "supportsCycleLinkedReentry : Bool",
            f"supportsCycleLinkedReentry = {supports_cycle}",
            "",
            "supportsHiddenStateDominance : Bool",
            f"supportsHiddenStateDominance = {supports_hidden}",
            "",
            "supportsPositiveLoopSurplus : Bool",
            f"supportsPositiveLoopSurplus = {supports_loop}",
            "",
            "topologyRepresentation : String",
            f"topologyRepresentation = {topology_representation}",
            "",
            "attractorRepresentation : String",
            f"attractorRepresentation = {attractor_representation}",
            "",
            "topWitnessKinds : List String",
            f"topWitnessKinds = {_list(top_witness_kinds)}",
            "",
            "topWitnessIds : List String",
            f"topWitnessIds = {_list(top_witness_ids)}",
            "",
            "topHotspotKinds : List String",
            f"topHotspotKinds = {_list(top_hotspot_kinds)}",
            "",
            "topHotspotIds : List String",
            f"topHotspotIds = {_list(top_hotspot_ids)}",
            "",
        ]
    )

    return "\n".join(lines) + "\n"


def _render_all(name: str, ctors: list[str]) -> str:
    return f"{name} = {_list(ctors)}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a Cubical-Agda-facing module from an empirical fibration packet."
    )
    parser.add_argument("--packet", required=True, help="Path to empirical fibration packet JSON")
    parser.add_argument(
        "--module-name",
        default="Morphospace.Generated.EmpiricalFibration",
        help="Agda module name to emit",
    )
    parser.add_argument("--output", help="Output .agda path")
    parser.add_argument(
        "--package-root-module",
        help="Root module name for split package output, e.g. Morphospace",
    )
    parser.add_argument(
        "--package-output-root",
        help="Output directory for split package emission",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet_path = Path(args.packet).expanduser().resolve()
    packet = _read_json(packet_path)
    if bool(args.package_root_module) != bool(args.package_output_root):
        raise SystemExit(
            "--package-root-module and --package-output-root must be passed together"
        )
    if args.package_root_module and args.package_output_root:
        output_root = Path(args.package_output_root).expanduser().resolve()
        package = render_agda_package(packet, root_module=str(args.package_root_module))
        for relative_path, source in package.items():
            out_path = (output_root / relative_path).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(source, encoding="utf-8")
        print(
            "Agda package:"
            f" root_module={args.package_root_module}"
            f" output_root={output_root}"
            f" file_count={len(package)}"
        )
        return 0
    source = render_agda_module(packet, module_name=str(args.module_name))
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (packet_path.parent / "EmpiricalFibration.agda").resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(source, encoding="utf-8")
    print(
        "Agda module:"
        f" module={args.module_name}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
