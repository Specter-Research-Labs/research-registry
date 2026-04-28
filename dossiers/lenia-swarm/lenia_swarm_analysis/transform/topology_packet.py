from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from ripser import ripser

from lenia_swarm_analysis._io import read_json
from lenia_swarm_analysis.topology.analysis import _diagram_summary, _pairwise_distance_matrix
from lenia_swarm_analysis.transformation_metrics import (
    TERMINAL_AXIS_IDS,
    TRANSFORMATION_SIGNATURE_AXIS_IDS,
)


def _specimen_matrix(
    specimens: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    rows: list[list[float]] = []
    kept: list[dict[str, Any]] = []
    for specimen in specimens:
        raw_axes = specimen.get("rawAxes")
        if not isinstance(raw_axes, dict):
            raise SystemExit("packet specimen is missing rawAxes")
        try:
            vector = [float(raw_axes[axis_id]) for axis_id in axis_ids]
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(
                f"packet specimen is missing numeric axis values for {axis_ids}"
            ) from exc
        rows.append(vector)
        kept.append(specimen)
    return np.asarray(rows, dtype=np.float64), kept


def _supports_axes(specimen: dict[str, Any], *, axis_ids: tuple[str, ...]) -> bool:
    raw_axes = specimen.get("rawAxes")
    if not isinstance(raw_axes, dict):
        return False
    try:
        for axis_id in axis_ids:
            float(raw_axes[axis_id])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _space_topology(
    *,
    specimens: list[dict[str, Any]],
    axis_ids: tuple[str, ...],
    max_homology_dim: int,
    min_group_size: int,
) -> dict[str, Any]:
    matrix, kept = _specimen_matrix(specimens, axis_ids=axis_ids)
    distances = _pairwise_distance_matrix(matrix)
    diagrams = ripser(distances, distance_matrix=True, maxdim=max_homology_dim)["dgms"]
    pairwise_max = float(np.max(distances)) if distances.size else 0.0
    groups: dict[str, list[dict[str, Any]]] = {}
    for group_key in ("familyKind", "regimeFamily", "geometryFamily", "canonicalFamily"):
        entries = []
        values = sorted(
            {specimen.get(group_key) for specimen in kept if specimen.get(group_key) is not None}
        )
        for value in values:
            group_specimens = [specimen for specimen in kept if specimen.get(group_key) == value]
            if len(group_specimens) < min_group_size:
                continue
            group_matrix, _ = _specimen_matrix(group_specimens, axis_ids=axis_ids)
            group_distances = _pairwise_distance_matrix(group_matrix)
            group_diagrams = ripser(
                group_distances,
                distance_matrix=True,
                maxdim=max_homology_dim,
            )["dgms"]
            group_pairwise_max = float(np.max(group_distances)) if group_distances.size else 0.0
            entries.append(
                {
                    group_key: str(value),
                    "pointCount": len(group_specimens),
                    "topology": _diagram_summary(group_diagrams, group_pairwise_max),
                }
            )
        groups[group_key] = entries
    return {
        "pointCount": len(kept),
        "axisIds": list(axis_ids),
        "global": _diagram_summary(diagrams, pairwise_max),
        "groups": groups,
    }


def _response_axis_id(condition: dict[str, Any]) -> str:
    environment_label = condition.get("environmentLabel")
    perturbation_label = condition.get("perturbationLabel")
    if not isinstance(environment_label, str) or not environment_label:
        raise SystemExit("focal response condition is missing environmentLabel")
    if not isinstance(perturbation_label, str) or not perturbation_label:
        raise SystemExit("focal response condition is missing perturbationLabel")
    return f"{environment_label}__{perturbation_label}"


def _focal_response_space_topology(
    *,
    specimens: list[dict[str, Any]],
    max_homology_dim: int,
    min_group_size: int,
) -> dict[str, Any]:
    axis_ids = sorted(
        {
            _response_axis_id(condition)
            for specimen in specimens
            for condition in specimen.get("responseByCondition", [])
            if isinstance(condition, dict)
        }
    )
    if not axis_ids:
        raise SystemExit("focal packet has no responseByCondition rows for response topology")
    derived_specimens: list[dict[str, Any]] = []
    for specimen in specimens:
        conditions = specimen.get("responseByCondition")
        if not isinstance(conditions, list):
            raise SystemExit("focal specimen is missing responseByCondition")
        response_axes: dict[str, float] = {}
        for condition in conditions:
            if not isinstance(condition, dict):
                raise SystemExit("focal response condition must be an object")
            axis_id = _response_axis_id(condition)
            value = condition.get("meanFragilityScore")
            if not isinstance(value, (int, float)):
                raise SystemExit(
                    f"{specimen.get('specimenId', 'unknown')}: response condition {axis_id} "
                    "is missing meanFragilityScore"
                )
            response_axes[axis_id] = float(value)
        missing_axes = [axis_id for axis_id in axis_ids if axis_id not in response_axes]
        if missing_axes:
            continue
        derived_specimens.append({**specimen, "rawAxes": response_axes})
    if not derived_specimens:
        raise SystemExit("focal packet has no complete response specimens for response topology")
    return _space_topology(
        specimens=derived_specimens,
        axis_ids=tuple(axis_ids),
        max_homology_dim=max_homology_dim,
        min_group_size=min_group_size,
    )


def build_transformation_topology_packet(
    *,
    atlas_packet_path: Path,
    min_group_size: int,
    max_homology_dim: int,
) -> dict[str, Any]:
    atlas = read_json(atlas_packet_path)
    packet_kind = atlas.get("packetKind")
    if packet_kind not in {
        "developmental_transformation_atlas_v2",
        "transformation_focal_packet_v1",
    }:
        raise SystemExit(
            "transformation topology expects developmental_transformation_atlas_v2 "
            "or transformation_focal_packet_v1"
        )
    specimens = atlas.get("specimens")
    if not isinstance(specimens, list) or not specimens:
        raise SystemExit(f"{atlas_packet_path}: atlas packet has no specimens")
    terminal_specimens = [
        specimen for specimen in specimens if _supports_axes(specimen, axis_ids=TERMINAL_AXIS_IDS)
    ]
    if not terminal_specimens:
        raise SystemExit(
            f"{atlas_packet_path}: packet has no specimens with complete terminal descriptor axes"
        )
    terminal_space = _space_topology(
        specimens=terminal_specimens,
        axis_ids=TERMINAL_AXIS_IDS,
        max_homology_dim=max_homology_dim,
        min_group_size=min_group_size,
    )
    spaces: dict[str, Any] = {
        "terminal_descriptor_space": terminal_space,
    }
    signature_specimens = [
        specimen
        for specimen in specimens
        if _supports_axes(specimen, axis_ids=TRANSFORMATION_SIGNATURE_AXIS_IDS)
    ]
    if signature_specimens:
        spaces["transformation_signature_space"] = _space_topology(
            specimens=signature_specimens,
            axis_ids=TRANSFORMATION_SIGNATURE_AXIS_IDS,
            max_homology_dim=max_homology_dim,
            min_group_size=min_group_size,
        )
    if packet_kind == "transformation_focal_packet_v1":
        has_response_rows = any(
            isinstance(specimen.get("responseByCondition"), list) and specimen.get("responseByCondition")
            for specimen in specimens
        )
        if has_response_rows:
            spaces["focal_response_space"] = _focal_response_space_topology(
                specimens=specimens,
                max_homology_dim=max_homology_dim,
                min_group_size=min_group_size,
            )
    space_names = list(spaces)
    limitations = [
        (
            "Topology is currently computed in descriptor space over atlas raw axes, "
            "not over the full terminal fingerprint field."
        ),
        (
            "Grouped topology omits strata with fewer than minGroupSize specimens, "
            "so sparse canonical families are reported by absence rather than "
            "by noisy diagrams."
        ),
    ]
    if len(terminal_specimens) != len(specimens):
        limitations.append(
            (
                "Topology spaces may exclude warehouse specimens that lack the required axis "
                "families; compendium summary or export rows stay in the warehouse but are "
                "not treated as topology-ready specimens."
            )
        )
    if not signature_specimens:
        limitations.append(
            (
                "Transformation signature topology is omitted when specimens lack the full "
                "developmental axis set, which is expected for compendium ingests without "
                "replay traces."
            )
        )
    if packet_kind == "transformation_focal_packet_v1":
        if "focal_response_space" in spaces:
            limitations.append(
                (
                    "Focal response topology uses per-condition mean fragility scores, "
                    "so it summarizes perturbation-response geometry rather than the "
                    "full replay-time perturbed developmental traces."
                )
            )
        else:
            limitations.append(
                (
                    "Focal response topology is omitted when the packet has no stored "
                    "response-condition summaries."
                )
            )
    return {
        "version": 1,
        "packetKind": "transformation_topology_packet_v1",
        "sourceArtifact": str(atlas_packet_path),
        "summary": {
            "specimenCount": len(specimens),
            "sourcePacketKind": packet_kind,
            "minGroupSize": min_group_size,
            "maxHomologyDim": max_homology_dim,
            "spaces": space_names,
        },
        "limitations": limitations,
        "spaces": spaces,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute topology on terminal and developmental transformation atlas spaces."
        )
    )
    parser.add_argument(
        "--atlas-packet",
        required=True,
        help="Path to transformation atlas v2 JSON or transformation focal packet JSON",
    )
    parser.add_argument("--min-group-size", type=int, default=8, help="Minimum specimens per group")
    parser.add_argument(
        "--max-homology-dim",
        type=int,
        default=1,
        help="Maximum homology dimension",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    atlas_packet_path = Path(args.atlas_packet).expanduser().resolve()
    packet = build_transformation_topology_packet(
        atlas_packet_path=atlas_packet_path,
        min_group_size=args.min_group_size,
        max_homology_dim=args.max_homology_dim,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else atlas_packet_path.parent / "transformation-topology-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transformation topology:"
        f" specimens={packet['summary']['specimenCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
