from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import (
    _extract_phenotype_matrix,
    _pairwise_distance_matrix,
)


def _resolve_path(base: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _membership_hash(specimen_ids: list[str]) -> str:
    digest = hashlib.sha256("\n".join(specimen_ids).encode("utf-8")).hexdigest()
    return digest[:12]


def _finite_h0_deaths(diagrams_path: Path) -> list[float]:
    payload = read_json(diagrams_path)
    phenotype = payload.get("phenotype")
    if not isinstance(phenotype, list) or not phenotype or not isinstance(phenotype[0], list):
        raise SystemExit(f"{diagrams_path}: expected phenotype H0 diagram array")
    finite = sorted(
        {
            float(entry["death"])
            for entry in phenotype[0]
            if isinstance(entry, dict) and entry.get("death") is not None
        },
        reverse=True,
    )
    if not finite:
        raise SystemExit(f"{diagrams_path}: no finite H0 deaths found")
    return finite


def _connected_components(distances: np.ndarray, threshold: float) -> list[list[int]]:
    adjacency = distances <= threshold
    np.fill_diagonal(adjacency, True)
    remaining = np.ones(distances.shape[0], dtype=bool)
    components: list[list[int]] = []
    while bool(np.any(remaining)):
        start = int(np.flatnonzero(remaining)[0])
        frontier = np.asarray([start], dtype=np.int64)
        remaining[start] = False
        component: list[int] = []
        while frontier.size:
            component.extend(frontier.tolist())
            neighbor_mask = adjacency[frontier].any(axis=0) & remaining
            frontier = np.flatnonzero(neighbor_mask)
            remaining[frontier] = False
        components.append(sorted(component))
    return components


def _representative_index(component: list[int], distances: np.ndarray) -> int:
    if len(component) == 1:
        return component[0]
    submatrix = distances[np.ix_(component, component)]
    medoid_local = int(np.argmin(np.sum(submatrix, axis=1)))
    return component[medoid_local]


def _component_summary(
    component: list[int],
    rows: list[dict[str, Any]],
    distances: np.ndarray,
) -> dict[str, Any]:
    representative_index = _representative_index(component, distances)
    representative_row = rows[representative_index]
    representative_terminal = representative_row["terminal"]
    submatrix = distances[np.ix_(component, component)]
    representative_distances = distances[representative_index, component]
    masses = [float(rows[index]["terminal"]["finalMass"]) for index in component]
    occupancies = [float(rows[index]["terminal"]["finalOccupancy"]) for index in component]
    gyrations = [float(rows[index]["terminal"]["finalGyration"]) for index in component]
    dominant_orders = [
        int(rows[index]["terminal"]["angularSymmetry"]["dominantOrder"]) for index in component
    ]
    specimen_ids = [str(rows[index]["specimenId"]) for index in component]
    return {
        "membershipHash12": _membership_hash(specimen_ids),
        "specimenCount": len(component),
        "memberSpecimenIds": specimen_ids,
        "runCount": len({str(rows[index]["runId"]) for index in component}),
        "campaignCount": len({str(rows[index]["campaignId"]) for index in component}),
        "representative": {
            "index": representative_index,
            "specimenId": str(representative_row["specimenId"]),
            "runId": str(representative_row["runId"]),
            "campaignId": str(representative_row["campaignId"]),
            "fingerprintHash12": str(representative_terminal["fingerprintHash12"]),
            "finalMass": float(representative_terminal["finalMass"]),
            "finalOccupancy": float(representative_terminal["finalOccupancy"]),
            "finalGyration": float(representative_terminal["finalGyration"]),
            "dominantOrder": int(
                representative_terminal["angularSymmetry"]["dominantOrder"]
            ),
        },
        "meanDistanceToRepresentative": float(np.mean(representative_distances)),
        "maxDistanceToRepresentative": float(np.max(representative_distances)),
        "meanPairwiseDistance": float(np.mean(submatrix)),
        "meanFinalMass": float(np.mean(masses)),
        "meanFinalOccupancy": float(np.mean(occupancies)),
        "meanFinalGyration": float(np.mean(gyrations)),
        "meanDominantOrder": float(np.mean(dominant_orders)),
    }


def build_attractor_packet(
    *,
    analysis_manifest_path: Path,
    top_scales: int,
    top_components_per_scale: int,
) -> dict[str, Any]:
    analysis_manifest = read_json(analysis_manifest_path)
    rows_path = _resolve_path(analysis_manifest_path.parent, str(analysis_manifest["rowsPath"]))
    diagrams_path = _resolve_path(
        analysis_manifest_path.parent,
        str(analysis_manifest["diagramsPath"]),
    )
    summary_path = _resolve_path(
        analysis_manifest_path.parent,
        str(analysis_manifest["summaryPath"]),
    )
    topology_summary = read_json(summary_path)
    rows = read_jsonl(rows_path)
    phenotype = _extract_phenotype_matrix(rows)
    distances = _pairwise_distance_matrix(phenotype)
    finite_deaths = _finite_h0_deaths(diagrams_path)
    selected_deaths = finite_deaths[:top_scales]

    scales: list[dict[str, Any]] = []
    for rank, death in enumerate(selected_deaths, start=1):
        threshold = float(np.nextafter(death, -np.inf))
        components = _connected_components(distances, threshold)
        component_rows = [
            _component_summary(component, rows, distances) for component in components
        ]
        component_rows.sort(
            key=lambda row: (
                -int(row["specimenCount"]),
                float(row["meanDistanceToRepresentative"]),
                str(row["representative"]["specimenId"]),
            )
        )
        scales.append(
            {
                "rank": rank,
                "mergeScale": death,
                "thresholdBelowMerge": threshold,
                "componentCount": len(components),
                "components": component_rows[:top_components_per_scale],
            }
        )

    phenotype_space = topology_summary["spaces"]["phenotype"]
    h0_summary = phenotype_space["ripser"][0]
    return {
        "version": 1,
        "packetKind": "attractor_packet_v1",
        "representation": "fingerprint_only",
        "sourceAnalysisManifest": str(analysis_manifest_path),
        "sourceRowsPath": str(rows_path),
        "specimenCount": len(rows),
        "phenotypeDimension": int(phenotype.shape[1]),
        "h0": {
            "featureCount": int(h0_summary["featureCount"]),
            "essentialCount": int(h0_summary["essentialCount"]),
            "topPersistence": [float(value) for value in h0_summary["topPersistence"]],
            "selectedMergeScales": selected_deaths,
        },
        "scales": scales,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an attractor-candidate packet from a frozen topology analysis."
    )
    parser.add_argument(
        "--analysis-manifest",
        required=True,
        help="Path to topology-analysis analysis-manifest.json",
    )
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument(
        "--top-scales",
        type=int,
        default=6,
        help="How many of the largest finite H0 merge scales to lift into component slices",
    )
    parser.add_argument(
        "--top-components-per-scale",
        type=int,
        default=8,
        help="How many of the largest components to keep per selected scale",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    analysis_manifest_path = Path(args.analysis_manifest).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (analysis_manifest_path.parent / "attractor-packet.json").resolve()
    )
    packet = build_attractor_packet(
        analysis_manifest_path=analysis_manifest_path,
        top_scales=args.top_scales,
        top_components_per_scale=args.top_components_per_scale,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Attractor packet:"
        f" specimens={packet['specimenCount']}"
        f" scales={len(packet['scales'])}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
