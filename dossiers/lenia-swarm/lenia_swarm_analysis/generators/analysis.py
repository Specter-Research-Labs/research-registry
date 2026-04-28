from __future__ import annotations

import argparse
import heapq
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from ripser import ripser

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.topology.analysis import (
    _collect_genotype_groups,
    _pairwise_distance_matrix,
    _resolve_rows_path,
    _upper_triangle,
)
from lenia_swarm_analysis.topology.compare import _representation_matrix


def _default_output_dir(manifest_path: Path) -> Path:
    stem = manifest_path.name.removesuffix(".manifest.json")
    return manifest_path.parent.parent / "topology-generators" / stem


def _edge_key(lhs: int, rhs: int) -> tuple[int, int]:
    return (lhs, rhs) if lhs < rhs else (rhs, lhs)


def _specimen_summary(row: dict[str, Any]) -> dict[str, Any]:
    genotype = row.get("genotype", {})
    terminal = row.get("terminal", {})
    angular = terminal.get("angularSymmetry", {})
    trajectory = row.get("trajectory", {})
    return {
        "specimenId": row.get("specimenId"),
        "runId": row.get("runId"),
        "campaignId": row.get("campaignId"),
        "seed": row.get("seed"),
        "genotypeHash12": genotype.get("hash12"),
        "fingerprintHash12": terminal.get("fingerprintHash12"),
        "dominantOrder": angular.get("dominantOrder"),
        "dominantAmplitude": angular.get("dominantAmplitude"),
        "finalMass": terminal.get("finalMass"),
        "finalOccupancy": terminal.get("finalOccupancy"),
        "finalGyration": terminal.get("finalGyration"),
        "pathTortuosity": trajectory.get("pathTortuosity"),
        "movementEfficiency": trajectory.get("movementEfficiency"),
    }


def _specimen_id(rows: list[dict[str, Any]], index: int) -> str:
    specimen_id = rows[index].get("specimenId")
    if not isinstance(specimen_id, str) or not specimen_id:
        raise SystemExit(f"Row {index} is missing specimenId")
    return specimen_id


def _canonicalize_cycle(vertices: list[int]) -> list[int]:
    if len(vertices) < 2 or vertices[0] != vertices[-1]:
        raise SystemExit("Representative cycles must be closed vertex sequences")
    body = vertices[:-1]
    rotations: list[tuple[int, ...]] = []
    for source in (body, list(reversed(body))):
        for index in range(len(source)):
            rotated = tuple(source[index:] + source[:index])
            rotations.append(rotated)
    best = min(rotations)
    return list(best) + [best[0]]


def _support_coefficients(cocycle: np.ndarray, coeff: int) -> dict[tuple[int, int], int]:
    support: dict[tuple[int, int], int] = {}
    for row in cocycle.tolist():
        if len(row) != 3:
            raise SystemExit("Expected H1 cocycle rows with shape (m, 3)")
        lhs, rhs, value = (int(row[0]), int(row[1]), int(row[2]))
        edge = _edge_key(lhs, rhs)
        support[edge] = int((support.get(edge, 0) + value) % coeff)
    return {edge: value for edge, value in support.items() if value != 0}


def _build_adjacency(distances: np.ndarray, scale: float) -> dict[int, list[tuple[int, float]]]:
    adjacency = {index: [] for index in range(distances.shape[0])}
    for lhs in range(distances.shape[0]):
        for rhs in range(lhs + 1, distances.shape[0]):
            distance = float(distances[lhs, rhs])
            if distance <= scale:
                adjacency[lhs].append((rhs, distance))
                adjacency[rhs].append((lhs, distance))
    return adjacency


def _shortest_path(
    adjacency: dict[int, list[tuple[int, float]]],
    start: int,
    goal: int,
    *,
    forbidden_edge: tuple[int, int],
    support_edges: set[tuple[int, int]],
    support_penalty: float,
) -> list[int] | None:
    frontier: list[tuple[float, int, list[int]]] = [(0.0, start, [start])]
    best: dict[int, float] = {start: 0.0}
    while frontier:
        cost, node, path = heapq.heappop(frontier)
        if node == goal:
            return path
        if cost > best.get(node, math.inf) + 1e-12:
            continue
        for nxt, distance in adjacency.get(node, []):
            edge = _edge_key(node, nxt)
            if edge == forbidden_edge:
                continue
            penalty = support_penalty if edge in support_edges else 0.0
            next_cost = cost + distance + penalty
            if next_cost + 1e-12 < best.get(nxt, math.inf):
                best[nxt] = next_cost
                heapq.heappush(frontier, (next_cost, nxt, path + [nxt]))
    return None


def _cycle_edges(vertices: list[int]) -> list[tuple[int, int]]:
    return [
        _edge_key(lhs, rhs)
        for lhs, rhs in zip(vertices, vertices[1:], strict=False)
    ]


def _pairing_mod(
    edges: list[tuple[int, int]],
    support_coefficients: dict[tuple[int, int], int],
    coeff: int,
) -> int:
    return int(sum(support_coefficients.get(edge, 0) for edge in edges) % coeff)


def _distance_percentiles(distances: np.ndarray, values: list[float]) -> list[float]:
    upper = np.sort(_upper_triangle(distances))
    if upper.size == 0:
        return [0.0 for _ in values]
    return [float(np.searchsorted(upper, value, side="right") / upper.size) for value in values]


def _neighbor_rank_matrix(distances: np.ndarray) -> np.ndarray:
    point_count = distances.shape[0]
    ranks = np.zeros((point_count, point_count), dtype=np.int64)
    for index in range(point_count):
        row = distances[index].copy()
        row[index] = np.inf
        ordered = np.argsort(row, kind="stable")
        for rank, neighbor in enumerate(ordered, start=1):
            ranks[index, int(neighbor)] = rank
    return ranks


def _cycle_control_lift(
    rows: list[dict[str, Any]],
    cycle_vertices: list[int],
    genotype_groups: list[dict[str, Any]],
    phenotype_distances: np.ndarray,
) -> dict[str, Any]:
    open_vertices = cycle_vertices[:-1]
    run_ids = sorted({str(rows[index].get("runId")) for index in open_vertices})
    campaign_ids = sorted({str(rows[index].get("campaignId")) for index in open_vertices})
    step_pairs = list(zip(cycle_vertices, cycle_vertices[1:], strict=False))
    step_phenotype_distances = [float(phenotype_distances[lhs, rhs]) for lhs, rhs in step_pairs]
    phenotype_percentiles = _distance_percentiles(
        phenotype_distances,
        step_phenotype_distances,
    )

    if len(genotype_groups) != 1:
        canonicalizers = [
            str(rows[index]["genotype"].get("canonicalizer", "unknown"))
            for index in open_vertices
        ]
        return {
            "status": "heterogeneous",
            "distinctRunCount": len(run_ids),
            "distinctCampaignCount": len(campaign_ids),
            "canonicalizersAlongCycle": canonicalizers,
            "stepPhenotypeDistances": step_phenotype_distances,
            "stepPhenotypeDistancePercentiles": phenotype_percentiles,
        }

    group = genotype_groups[0]
    genotype_distances = _pairwise_distance_matrix(group["matrix"])
    rank_matrix = _neighbor_rank_matrix(genotype_distances)
    genotype_percentiles = _distance_percentiles(
        genotype_distances,
        [float(genotype_distances[lhs, rhs]) for lhs, rhs in step_pairs],
    )
    step_genotype_distances = [float(genotype_distances[lhs, rhs]) for lhs, rhs in step_pairs]
    directed_neighbor_ranks = [int(rank_matrix[lhs, rhs]) for lhs, rhs in step_pairs]
    reverse_neighbor_ranks = [int(rank_matrix[rhs, lhs]) for lhs, rhs in step_pairs]
    symmetric_neighbor_ranks = [
        max(lhs_rank, rhs_rank)
        for lhs_rank, rhs_rank in zip(
            directed_neighbor_ranks,
            reverse_neighbor_ranks,
            strict=False,
        )
    ]
    return {
        "status": "homogeneous",
        "canonicalizer": group["canonicalizer"],
        "dimension": int(group["matrix"].shape[1]),
        "distinctRunCount": len(run_ids),
        "distinctCampaignCount": len(campaign_ids),
        "stepGenotypeDistances": step_genotype_distances,
        "stepGenotypeDistancePercentiles": genotype_percentiles,
        "stepPhenotypeDistances": step_phenotype_distances,
        "stepPhenotypeDistancePercentiles": phenotype_percentiles,
        "stepGenotypeNeighborRanks": symmetric_neighbor_ranks,
        "meanStepGenotypeDistancePercentile": float(np.mean(genotype_percentiles)),
        "maxStepGenotypeDistancePercentile": float(np.max(genotype_percentiles)),
        "meanStepGenotypeNeighborRank": float(np.mean(symmetric_neighbor_ranks)),
        "maxStepGenotypeNeighborRank": int(np.max(symmetric_neighbor_ranks)),
        "genotypeJumpStepCount95": int(sum(value >= 0.95 for value in genotype_percentiles)),
        "genotypeJumpStepCount90": int(sum(value >= 0.90 for value in genotype_percentiles)),
        "genotypeNeighborRankAbove32Count": int(
            sum(rank > 32 for rank in symmetric_neighbor_ranks)
        ),
    }


def _candidate_scale(
    birth: float,
    death: float | None,
    support_coefficients: dict[tuple[int, int], int],
    phenotype_distances: np.ndarray,
) -> tuple[dict[str, float | None], float]:
    support_distances = [
        float(phenotype_distances[lhs, rhs])
        for lhs, rhs in support_coefficients
    ]
    support_min = min(support_distances, default=birth)
    support_max = max(support_distances, default=birth)
    midpoint = birth + 0.5 * ((death - birth) if death is not None else max(birth, support_max))
    epsilon = max(1e-9, 1e-6 * max(1.0, support_max, death or birth))
    if death is None:
        scale = max(midpoint, support_max + epsilon)
    else:
        upper = max(birth + epsilon, death - epsilon)
        scale = min(max(midpoint, support_max + epsilon), upper)
        if scale <= birth:
            scale = upper
    summary = {
        "birth": birth,
        "death": death,
        "midpoint": midpoint,
        "supportMin": support_min,
        "supportMax": support_max,
        "selected": scale,
    }
    return summary, scale


def _candidate_cycles(
    support_coefficients: dict[tuple[int, int], int],
    phenotype_distances: np.ndarray,
    representative_scale: float,
    coeff: int,
) -> list[dict[str, Any]]:
    adjacency = _build_adjacency(phenotype_distances, representative_scale)
    support_edges = set(support_coefficients)
    support_penalty = max(1.0, representative_scale * phenotype_distances.shape[0])
    candidates: list[dict[str, Any]] = []
    for closing_edge in sorted(support_edges):
        path = _shortest_path(
            adjacency,
            closing_edge[0],
            closing_edge[1],
            forbidden_edge=closing_edge,
            support_edges=support_edges,
            support_penalty=support_penalty,
        )
        if path is None or len(path) < 2:
            continue
        cycle_vertices = _canonicalize_cycle(path + [path[0]])
        cycle_edges = _cycle_edges(cycle_vertices)
        pairing = _pairing_mod(cycle_edges, support_coefficients, coeff)
        if pairing == 0:
            continue
        total_length = float(
            sum(
                phenotype_distances[lhs, rhs]
                for lhs, rhs in zip(cycle_vertices, cycle_vertices[1:], strict=False)
            )
        )
        support_edge_count = int(sum(edge in support_edges for edge in cycle_edges))
        candidates.append(
            {
                "closingEdge": list(closing_edge),
                "closingEdgeDistance": float(phenotype_distances[closing_edge[0], closing_edge[1]]),
                "vertexCount": len(cycle_vertices) - 1,
                "cycleVertices": cycle_vertices,
                "cycleEdges": [list(edge) for edge in cycle_edges],
                "totalPhenotypeLength": total_length,
                "supportEdgeCount": support_edge_count,
                "pairingModCoeff": pairing,
            }
        )
    candidates.sort(
        key=lambda candidate: (
            -int(candidate["vertexCount"]),
            -float(candidate["totalPhenotypeLength"]),
            int(candidate["supportEdgeCount"]),
            float(candidate["closingEdgeDistance"]),
        )
    )
    return candidates


def _generator_packet(
    *,
    feature_index: int,
    birth: float,
    death: float | None,
    persistence: float | None,
    cocycle: np.ndarray,
    rows: list[dict[str, Any]],
    genotype_groups: list[dict[str, Any]],
    phenotype_distances: np.ndarray,
    coeff: int,
) -> dict[str, Any]:
    support_coefficients = _support_coefficients(cocycle, coeff)
    scale_summary, selected_scale = _candidate_scale(
        birth,
        death,
        support_coefficients,
        phenotype_distances,
    )
    candidates = _candidate_cycles(
        support_coefficients,
        phenotype_distances,
        representative_scale=selected_scale,
        coeff=coeff,
    )
    representative_cycle = candidates[0] if candidates else None
    cycle_specimens: list[dict[str, Any]] = []
    control_lift: dict[str, Any] | None = None
    if representative_cycle is not None:
        vertices = [int(value) for value in representative_cycle["cycleVertices"]]
        cycle_specimens = [_specimen_summary(rows[index]) for index in vertices[:-1]]
        control_lift = _cycle_control_lift(rows, vertices, genotype_groups, phenotype_distances)
    return {
        "featureIndex": feature_index,
        "birth": birth,
        "death": death,
        "persistence": persistence,
        "supportEdgeCount": len(support_coefficients),
        "supportEdges": [
            {"edge": list(edge), "coefficient": int(value)}
            for edge, value in sorted(support_coefficients.items())
        ],
        "scale": scale_summary,
        "candidateCycleCount": len(candidates),
        "candidateCycles": candidates[:8],
        "representativeCycle": representative_cycle,
        "cycleSpecimens": cycle_specimens,
        "controlLift": control_lift,
    }


def _generator_id(rank: int, feature_index: int) -> str:
    return f"h1-rank{rank:02d}-feature{feature_index:04d}"


def _generator_packet_contract(
    packets: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    source_manifest: Path,
    representation: str,
) -> dict[str, Any]:
    generators: list[dict[str, Any]] = []
    for packet in packets:
        representative = packet.get("representativeCycle")
        cycle_vertices = (
            representative.get("cycleVertices")
            if isinstance(representative, dict)
            else None
        )
        representative_ids = (
            [_specimen_id(rows, int(index)) for index in cycle_vertices[:-1]]
            if isinstance(cycle_vertices, list) and len(cycle_vertices) >= 2
            else []
        )
        member_indices = sorted(
            {
                int(index)
                for entry in packet.get("supportEdges", [])
                if isinstance(entry, dict)
                for index in entry.get("edge", [])
            }
        )
        member_ids = [_specimen_id(rows, index) for index in member_indices]
        cycle_edges = []
        if isinstance(representative, dict):
            for edge in representative.get("cycleEdges", []):
                if not isinstance(edge, list) or len(edge) != 2:
                    continue
                lhs = int(edge[0])
                rhs = int(edge[1])
                cycle_edges.append(
                    {
                        "fromSpecimenId": _specimen_id(rows, lhs),
                        "toSpecimenId": _specimen_id(rows, rhs),
                    }
                )
        generators.append(
            {
                "generatorId": _generator_id(int(packet["rank"]), int(packet["featureIndex"])),
                "persistence": packet.get("persistence"),
                "representativeSpecimenIds": representative_ids,
                "memberSpecimenIds": member_ids,
                "cycleEdges": cycle_edges,
            }
        )
    return {
        "version": 1,
        "packetKind": "topology_generator_packet_v1",
        "sourceManifest": str(source_manifest),
        "representation": representation,
        "generators": generators,
    }


def run_generator_analysis(
    manifest_path: Path,
    output_dir: Path,
    *,
    representation: str,
    maxdim: int,
    top_h1: int,
    coeff: int,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    rows_path = _resolve_rows_path(manifest_path, manifest)
    rows = read_jsonl(rows_path)
    if len(rows) < 3:
        raise SystemExit("Generator analysis requires at least 3 specimens.")

    phenotype = _representation_matrix(rows, representation)
    phenotype_distances = _pairwise_distance_matrix(phenotype)
    genotype_groups = _collect_genotype_groups(rows)
    result = ripser(
        phenotype,
        maxdim=maxdim,
        metric="euclidean",
        do_cocycles=True,
        coeff=coeff,
    )
    diagrams = result["dgms"]
    cocycles = result["cocycles"]
    if len(diagrams) <= 1:
        raise SystemExit("Generator analysis requires H1 output; pass maxdim >= 1")

    packets: list[dict[str, Any]] = []
    ranked = []
    for index, feature in enumerate(diagrams[1].tolist()):
        birth = float(feature[0])
        death = None if math.isinf(float(feature[1])) else float(feature[1])
        persistence = None if death is None else death - birth
        ranked.append((index, birth, death, persistence))
    ranked.sort(
        key=lambda entry: (
            -(entry[3] if entry[3] is not None else math.inf),
            entry[1],
            entry[0],
        )
    )
    for rank, (feature_index, birth, death, persistence) in enumerate(ranked[:top_h1], start=1):
        packet = _generator_packet(
            feature_index=feature_index,
            birth=birth,
            death=death,
            persistence=persistence,
            cocycle=np.asarray(cocycles[1][feature_index], dtype=np.int64),
            rows=rows,
            genotype_groups=genotype_groups,
            phenotype_distances=phenotype_distances,
            coeff=coeff,
        )
        packet["rank"] = rank
        packets.append(packet)

    summary = {
        "sourceManifest": str(manifest_path),
        "rowsPath": str(rows_path),
        "specimenCount": len(rows),
        "representation": representation,
        "analysisBackend": "ripser-cocycle-heuristic-cycle-v1",
        "topH1Requested": top_h1,
        "generatorCount": len(diagrams[1]),
        "selectedGeneratorCount": len(packets),
        "coeff": coeff,
        "notes": (
            "Representative cycles are reconstructed heuristically from H1 cocycle support "
            "by finding a nontrivially paired shortest closure in the Rips graph at a scale "
            "between birth and death. They are concrete specimen loops, not canonical cycle "
            "bases."
        ),
        "topH1Persistence": [
            packet.get("persistence")
            for packet in packets
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "generators.json").write_text(
        json.dumps(packets, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "generator-packet.json").write_text(
        json.dumps(
            _generator_packet_contract(
                packets,
                rows,
                source_manifest=manifest_path,
                representation=representation,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output_dir / "analysis-manifest.json").write_text(
        json.dumps(
            {
                "sourceManifest": str(manifest_path),
                "rowsPath": str(rows_path),
                "summaryPath": "summary.json",
                "generatorsPath": "generators.json",
                "generatorPacketPath": "generator-packet.json",
                "representation": representation,
                "topH1Requested": top_h1,
                "coeff": coeff,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract concrete H1 generator packets from lenia-swarm topology exports."
        )
    )
    parser.add_argument("--manifest", required=True, help="Path to topology manifest JSON")
    parser.add_argument(
        "--output",
        help=(
            "Output directory for topology-generator artifacts. Defaults to "
            "outputs/topology-generators/<stem>"
        ),
    )
    parser.add_argument(
        "--representation",
        default="fingerprint_only",
        help="Phenotype representation to analyze",
    )
    parser.add_argument(
        "--maxdim",
        type=int,
        default=1,
        help="Maximum homology dimension for ripser",
    )
    parser.add_argument(
        "--top-h1",
        type=int,
        default=5,
        help="Number of top H1 generators to extract",
    )
    parser.add_argument(
        "--coeff",
        type=int,
        default=2,
        help="Prime coefficient field for ripser cocycles",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(manifest_path).resolve()
    )
    summary = run_generator_analysis(
        manifest_path,
        output_dir,
        representation=args.representation,
        maxdim=args.maxdim,
        top_h1=args.top_h1,
        coeff=args.coeff,
    )
    print(
        "Topology generators:"
        f" specimens={summary['specimenCount']}"
        f" generators={summary['selectedGeneratorCount']}"
        f" output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
