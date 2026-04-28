from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from lenia_swarm_analysis._io import read_json
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    TRANSFORMATION_SIGNATURE_AXIS_IDS,
)


def _require_packet_kind(packet: dict[str, Any], *, expected: str, path: Path) -> None:
    if packet.get("packetKind") != expected:
        raise SystemExit(f"{path}: expected {expected}")


def _canonical_family_specimens(
    packet: dict[str, Any],
    *,
    family: str,
) -> list[dict[str, Any]]:
    specimens = packet.get("specimens")
    if not isinstance(specimens, list):
        raise SystemExit("packet is missing specimens")
    return [
        specimen
        for specimen in specimens
        if isinstance(specimen, dict) and specimen.get("canonicalFamily") == family
    ]


def _family_axis_medians(
    specimens: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
) -> dict[str, float]:
    medians: dict[str, float] = {}
    for axis_id in axis_ids:
        values = [
            float(specimen["rawAxes"][axis_id])
            for specimen in specimens
            if isinstance(specimen.get("rawAxes"), dict) and axis_id in specimen["rawAxes"]
        ]
        if values:
            medians[axis_id] = float(median(values))
    return medians


def _family_dominant_programs(specimens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        str(specimen["dominantProgram"])
        for specimen in specimens
        if isinstance(specimen.get("dominantProgram"), str)
    )
    total = sum(counts.values())
    if total == 0:
        return []
    return [
        {"axisId": axis_id, "count": count, "fraction": count / total}
        for axis_id, count in counts.most_common()
    ]


def _canonical_family_topology_entry(
    topology_packet: dict[str, Any] | None,
    *,
    space_name: str,
    family: str,
) -> dict[str, Any] | None:
    if topology_packet is None:
        return None
    spaces = topology_packet.get("spaces")
    if not isinstance(spaces, dict):
        raise SystemExit("topology packet is missing spaces")
    space = spaces.get(space_name)
    if not isinstance(space, dict):
        return None
    groups = space.get("groups")
    if not isinstance(groups, dict):
        raise SystemExit("topology space is missing groups")
    entries = groups.get("canonicalFamily")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("canonicalFamily") != family:
            continue
        topology = entry.get("topology")
        if not isinstance(topology, dict):
            raise SystemExit(f"{space_name}: canonical topology entry is missing topology")
        summaries = topology.get("summaries")
        if not isinstance(summaries, list):
            raise SystemExit(f"{space_name}: canonical topology entry is missing summaries")
        by_dimension = {
            int(summary["dimension"]): summary
            for summary in summaries
            if isinstance(summary, dict) and "dimension" in summary
        }
        h1 = by_dimension.get(1, {"featureCount": 0, "topPersistence": []})
        return {
            "pointCount": int(entry.get("pointCount", 0)),
            "h1FeatureCount": int(h1.get("featureCount", 0)),
            "h1TopPersistence": [float(value) for value in h1.get("topPersistence", [])],
        }
    return None


def _family_condition_fragility(specimens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for specimen in specimens:
        conditions = specimen.get("responseByCondition")
        if not isinstance(conditions, list):
            continue
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            environment_label = condition.get("environmentLabel")
            perturbation_label = condition.get("perturbationLabel")
            fragility = condition.get("meanFragilityScore")
            if (
                isinstance(environment_label, str)
                and environment_label
                and isinstance(perturbation_label, str)
                and perturbation_label
                and isinstance(fragility, (int, float))
            ):
                grouped[(environment_label, perturbation_label)].append(float(fragility))
    rows = [
        {
            "environmentLabel": environment_label,
            "perturbationLabel": perturbation_label,
            "meanFragilityScore": float(mean(values)),
        }
        for (environment_label, perturbation_label), values in grouped.items()
    ]
    return sorted(
        rows,
        key=lambda row: (
            -row["meanFragilityScore"],
            row["environmentLabel"],
            row["perturbationLabel"],
        ),
    )


def _group_family_condition_fragility(
    conditions: list[dict[str, Any]],
    *,
    group_key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for condition in conditions:
        group_value = condition.get(group_key)
        fragility = condition.get("meanFragilityScore")
        if isinstance(group_value, str) and group_value and isinstance(fragility, (int, float)):
            grouped[group_value].append(float(fragility))
    rows = [
        {
            group_key: group_value,
            "meanFragilityScore": float(mean(values)),
        }
        for group_value, values in grouped.items()
    ]
    return sorted(
        rows,
        key=lambda row: (-row["meanFragilityScore"], str(row[group_key])),
    )


def _condition_signature(condition: dict[str, Any]) -> tuple[str, str]:
    return (str(condition["environmentLabel"]), str(condition["perturbationLabel"]))


def _pairwise_condition_deltas(
    left_conditions: list[dict[str, Any]],
    right_conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    left_by_signature = {
        _condition_signature(condition): float(condition["meanFragilityScore"])
        for condition in left_conditions
    }
    right_by_signature = {
        _condition_signature(condition): float(condition["meanFragilityScore"])
        for condition in right_conditions
    }
    shared_signatures = sorted(set(left_by_signature) & set(right_by_signature))
    rows = [
        {
            "environmentLabel": environment_label,
            "perturbationLabel": perturbation_label,
            "familyAMeanFragilityScore": left_by_signature[(environment_label, perturbation_label)],
            "familyBMeanFragilityScore": right_by_signature[
                (environment_label, perturbation_label)
            ],
            "delta": (
                right_by_signature[(environment_label, perturbation_label)]
                - left_by_signature[(environment_label, perturbation_label)]
            ),
            "absDelta": abs(
                right_by_signature[(environment_label, perturbation_label)]
                - left_by_signature[(environment_label, perturbation_label)]
            ),
        }
        for environment_label, perturbation_label in shared_signatures
    ]
    return sorted(
        rows,
        key=lambda row: (
            -float(row["absDelta"]),
            row["environmentLabel"],
            row["perturbationLabel"],
        ),
    )


def _h1_feature_count(summary: dict[str, Any] | None) -> int:
    if not isinstance(summary, dict):
        return 0
    return int(summary.get("h1FeatureCount", 0))


def _h1_top_persistence(summary: dict[str, Any] | None) -> float:
    if not isinstance(summary, dict):
        return 0.0
    top = summary.get("h1TopPersistence")
    if not isinstance(top, list) or not top:
        return 0.0
    return float(top[0])


def build_transformation_family_comparison_packet(
    *,
    atlas_packet_path: Path,
    focal_packet_path: Path | None,
    atlas_topology_packet_path: Path | None,
    focal_topology_packet_path: Path | None,
    canonical_families: list[str] | None,
) -> dict[str, Any]:
    atlas_packet = read_json(atlas_packet_path)
    _require_packet_kind(
        atlas_packet,
        expected="developmental_transformation_atlas_v2",
        path=atlas_packet_path,
    )
    focal_packet = read_json(focal_packet_path) if focal_packet_path else None
    if focal_packet is not None:
        resolved_focal_packet_path = focal_packet_path
        if resolved_focal_packet_path is None:
            raise AssertionError("unreachable")
        _require_packet_kind(
            focal_packet,
            expected="transformation_focal_packet_v1",
            path=resolved_focal_packet_path,
        )
    atlas_topology_packet = (
        read_json(atlas_topology_packet_path) if atlas_topology_packet_path else None
    )
    if atlas_topology_packet is not None:
        resolved_atlas_topology_packet_path = atlas_topology_packet_path
        if resolved_atlas_topology_packet_path is None:
            raise AssertionError("unreachable")
        _require_packet_kind(
            atlas_topology_packet,
            expected="transformation_topology_packet_v1",
            path=resolved_atlas_topology_packet_path,
        )
    focal_topology_packet = (
        read_json(focal_topology_packet_path) if focal_topology_packet_path else None
    )
    if focal_topology_packet is not None:
        resolved_focal_topology_packet_path = focal_topology_packet_path
        if resolved_focal_topology_packet_path is None:
            raise AssertionError("unreachable")
        _require_packet_kind(
            focal_topology_packet,
            expected="transformation_topology_packet_v1",
            path=resolved_focal_topology_packet_path,
        )

    atlas_specimens = atlas_packet.get("specimens")
    if not isinstance(atlas_specimens, list) or not atlas_specimens:
        raise SystemExit(f"{atlas_packet_path}: atlas packet has no specimens")

    selected_families = canonical_families or sorted(
        {
            str(specimen["canonicalFamily"])
            for specimen in atlas_specimens
            if isinstance(specimen, dict) and isinstance(specimen.get("canonicalFamily"), str)
        }
    )
    families: list[dict[str, Any]] = []
    for family in selected_families:
        atlas_family_specimens = _canonical_family_specimens(atlas_packet, family=family)
        if not atlas_family_specimens:
            raise SystemExit(f"{family}: missing from atlas packet")
        focal_family_specimens = (
            _canonical_family_specimens(focal_packet, family=family) if focal_packet else []
        )
        regime_family = atlas_family_specimens[0].get("regimeFamily")
        geometry_family = atlas_family_specimens[0].get("geometryFamily")
        atlas_entry: dict[str, Any] = {
            "specimenCount": len(atlas_family_specimens),
            "terminalAxisMedians": _family_axis_medians(
                atlas_family_specimens,
                axis_ids=TERMINAL_AXIS_IDS,
            ),
            "developmentalAxisMedians": _family_axis_medians(
                atlas_family_specimens,
                axis_ids=DEVELOPMENTAL_AXIS_IDS,
            ),
            "signatureAxisMedians": _family_axis_medians(
                atlas_family_specimens,
                axis_ids=TRANSFORMATION_SIGNATURE_AXIS_IDS,
            ),
            "dominantPrograms": _family_dominant_programs(atlas_family_specimens),
            "signatureTopology": _canonical_family_topology_entry(
                atlas_topology_packet,
                space_name="transformation_signature_space",
                family=family,
            ),
        }
        focal_entry: dict[str, Any] | None = None
        if focal_packet is not None:
            condition_profile = _family_condition_fragility(focal_family_specimens)
            mean_fragility = mean(
                float(specimen["fragilitySummary"]["meanFragilityScore"])
                for specimen in focal_family_specimens
            )
            mean_robustness = mean(
                float(specimen["fragilitySummary"]["meanRobustnessScore"])
                for specimen in focal_family_specimens
            )
            max_fragility = max(
                float(specimen["fragilitySummary"]["maxFragilityScore"])
                for specimen in focal_family_specimens
            )
            focal_entry = {
                "specimenCount": len(focal_family_specimens),
                "meanFragilityScore": float(mean_fragility),
                "meanRobustnessScore": float(mean_robustness),
                "maxFragilityScore": float(max_fragility),
                "conditionProfile": condition_profile,
                "topConditions": condition_profile[:5],
                "environmentProfile": _group_family_condition_fragility(
                    condition_profile,
                    group_key="environmentLabel",
                ),
                "perturbationProfile": _group_family_condition_fragility(
                    condition_profile,
                    group_key="perturbationLabel",
                ),
                "responseTopology": _canonical_family_topology_entry(
                    focal_topology_packet,
                    space_name="focal_response_space",
                    family=family,
                ),
            }
        families.append(
            {
                "canonicalFamily": family,
                "regimeFamily": regime_family,
                "geometryFamily": geometry_family,
                "atlas": atlas_entry,
                "focal": focal_entry,
            }
        )

    pairwise: list[dict[str, Any]] = []
    for index, left in enumerate(families):
        for right in families[index + 1 :]:
            left_focal = left.get("focal")
            right_focal = right.get("focal")
            pairwise.append(
                {
                    "familyA": left["canonicalFamily"],
                    "familyB": right["canonicalFamily"],
                    "atlasSpecimenDelta": (
                        int(right["atlas"]["specimenCount"])
                        - int(left["atlas"]["specimenCount"])
                    ),
                    "meanFragilityDelta": (
                        float(right_focal["meanFragilityScore"])
                        - float(left_focal["meanFragilityScore"])
                        if isinstance(left_focal, dict) and isinstance(right_focal, dict)
                        else None
                    ),
                    "signatureH1Delta": (
                        _h1_feature_count(right["atlas"]["signatureTopology"])
                        - _h1_feature_count(left["atlas"]["signatureTopology"])
                    ),
                    "responseH1Delta": (
                        _h1_feature_count((right_focal or {}).get("responseTopology"))
                        - _h1_feature_count((left_focal or {}).get("responseTopology"))
                        if isinstance(left_focal, dict) and isinstance(right_focal, dict)
                        else None
                    ),
                    "topConditionDeltas": (
                        _pairwise_condition_deltas(
                            list(left_focal.get("conditionProfile", [])),
                            list(right_focal.get("conditionProfile", [])),
                        )[:5]
                        if isinstance(left_focal, dict) and isinstance(right_focal, dict)
                        else []
                    ),
                }
            )

    most_fragile_family = None
    if all(isinstance(family.get("focal"), dict) for family in families):
        most_fragile = max(
            families,
            key=lambda family: float(family["focal"]["meanFragilityScore"]),
        )
        most_fragile_family = {
            "canonicalFamily": most_fragile["canonicalFamily"],
            "meanFragilityScore": float(most_fragile["focal"]["meanFragilityScore"]),
        }
    most_signature_topology_family = max(
        families,
        key=lambda family: (
            _h1_feature_count(family["atlas"]["signatureTopology"]),
            _h1_top_persistence(family["atlas"]["signatureTopology"]),
        ),
    )
    most_response_topology_family = None
    if all(isinstance(family.get("focal"), dict) for family in families):
        most_response = max(
            families,
            key=lambda family: (
                _h1_feature_count((family["focal"] or {}).get("responseTopology")),
                _h1_top_persistence((family["focal"] or {}).get("responseTopology")),
            ),
        )
        response_topology = (most_response["focal"] or {}).get("responseTopology")
        most_response_topology_family = {
            "canonicalFamily": most_response["canonicalFamily"],
            "h1FeatureCount": _h1_feature_count(response_topology),
            "h1TopPersistence": _h1_top_persistence(response_topology),
        }
    signature_topology = most_signature_topology_family["atlas"]["signatureTopology"]

    return {
        "version": 1,
        "packetKind": "transformation_family_comparison_packet_v1",
        "sourceArtifacts": {
            "atlasPacket": str(atlas_packet_path),
            "focalPacket": str(focal_packet_path) if focal_packet_path else None,
            "atlasTopologyPacket": (
                str(atlas_topology_packet_path) if atlas_topology_packet_path else None
            ),
            "focalTopologyPacket": (
                str(focal_topology_packet_path) if focal_topology_packet_path else None
            ),
        },
        "summary": {
            "familyCount": len(families),
            "canonicalFamilies": [family["canonicalFamily"] for family in families],
            "mostFragileFamily": most_fragile_family,
            "mostSignatureTopologyFamily": {
                "canonicalFamily": most_signature_topology_family["canonicalFamily"],
                "h1FeatureCount": _h1_feature_count(signature_topology),
                "h1TopPersistence": _h1_top_persistence(signature_topology),
            },
            "mostResponseTopologyFamily": most_response_topology_family,
        },
        "families": families,
        "pairwise": pairwise,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare canonical developmental families across atlas, focal, "
            "and topology packets."
        )
    )
    parser.add_argument(
        "--atlas-packet",
        required=True,
        help="Path to transformation atlas v2 JSON",
    )
    parser.add_argument("--focal-packet", help="Optional path to transformation focal packet JSON")
    parser.add_argument(
        "--atlas-topology-packet",
        help="Optional path to transformation topology packet for the atlas cohort",
    )
    parser.add_argument(
        "--focal-topology-packet",
        help="Optional path to transformation topology packet for the focal cohort",
    )
    parser.add_argument(
        "--family",
        action="append",
        dest="families",
        help="Restrict comparison to these canonical families",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    atlas_packet_path = Path(args.atlas_packet).expanduser().resolve()
    focal_packet_path = (
        Path(args.focal_packet).expanduser().resolve() if args.focal_packet else None
    )
    atlas_topology_packet_path = (
        Path(args.atlas_topology_packet).expanduser().resolve()
        if args.atlas_topology_packet
        else None
    )
    focal_topology_packet_path = (
        Path(args.focal_topology_packet).expanduser().resolve()
        if args.focal_topology_packet
        else None
    )
    packet = build_transformation_family_comparison_packet(
        atlas_packet_path=atlas_packet_path,
        focal_packet_path=focal_packet_path,
        atlas_topology_packet_path=atlas_topology_packet_path,
        focal_topology_packet_path=focal_topology_packet_path,
        canonical_families=[str(family) for family in args.families] if args.families else None,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else atlas_packet_path.parent / "transformation-family-comparison-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transformation family comparison:"
        f" families={packet['summary']['familyCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
