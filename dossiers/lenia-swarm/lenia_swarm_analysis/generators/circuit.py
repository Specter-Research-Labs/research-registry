from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json

from .cycle_transport import (
    _edge_summary_path,
    _load_generator_packet,
    _specimen_suffix,
)


def _default_output_dir(sweep_root: Path) -> Path:
    return sweep_root.parent.parent / "topology-generator-circuit" / sweep_root.name


def _load_representative_path(
    sweep_root: Path,
    generator_id: str,
    edge_index: int,
    anchor: str,
) -> list[str]:
    summary_path = _edge_summary_path(sweep_root, generator_id, edge_index, anchor)
    summary = read_json(summary_path)
    continuation = summary.get("continuation")
    if not isinstance(continuation, dict):
        raise SystemExit(f"{summary_path}: missing continuation object")
    representative_path = continuation.get("collapsedRepresentativePath")
    if not isinstance(representative_path, list) or not all(
        isinstance(item, str) for item in representative_path
    ):
        raise SystemExit(f"{summary_path}: missing collapsedRepresentativePath")
    return representative_path


def _edge_lookup(generator: dict[str, Any]) -> dict[frozenset[str], tuple[int, str, str]]:
    cycle_edges = generator.get("cycleEdges")
    if not isinstance(cycle_edges, list):
        raise SystemExit("Generator packet is missing cycleEdges")
    lookup: dict[frozenset[str], tuple[int, str, str]] = {}
    for edge_index, edge in enumerate(cycle_edges):
        if not isinstance(edge, dict):
            raise SystemExit("cycleEdges rows must be objects")
        typed_edge: dict[str, Any] = {str(key): value for key, value in edge.items()}
        from_id = typed_edge.get("fromSpecimenId")
        to_id = typed_edge.get("toSpecimenId")
        if not isinstance(from_id, str) or not isinstance(to_id, str):
            raise SystemExit("cycle edge is missing fromSpecimenId/toSpecimenId")
        lookup[frozenset({from_id, to_id})] = (edge_index, from_id, to_id)
    return lookup


def _collapse_concatenation(paths: list[list[str]]) -> list[str]:
    collapsed: list[str] = []
    for path in paths:
        if not path:
            continue
        if not collapsed:
            collapsed.extend(path)
            continue
        if collapsed[-1] == path[0]:
            collapsed.extend(path[1:])
        else:
            collapsed.extend(path)
    return collapsed


def _cycle_only_path(path: list[str], cycle_vertices: set[str]) -> list[str]:
    filtered: list[str] = []
    for specimen_id in path:
        if specimen_id not in cycle_vertices:
            continue
        if not filtered or filtered[-1] != specimen_id:
            filtered.append(specimen_id)
    return filtered


def _distinct_neighbors(path: list[str], vertex: str) -> tuple[str | None, str | None]:
    first_next: str | None = None
    last_prev: str | None = None
    for idx, specimen_id in enumerate(path):
        if specimen_id != vertex:
            continue
        for next_idx in range(idx + 1, len(path)):
            if path[next_idx] != vertex:
                first_next = path[next_idx]
                break
        break
    for idx in range(len(path) - 1, -1, -1):
        if path[idx] != vertex:
            continue
        for prev_idx in range(idx - 1, -1, -1):
            if path[prev_idx] != vertex:
                last_prev = path[prev_idx]
                break
        break
    return first_next, last_prev


def _rotated_cycle(cycle_vertices: list[str], start_index: int) -> list[str]:
    return cycle_vertices[start_index:] + cycle_vertices[:start_index]


def _circuit_record(
    *,
    generator: dict[str, Any],
    sweep_root: Path,
    start_index: int,
) -> dict[str, Any]:
    generator_id = generator.get("generatorId")
    if not isinstance(generator_id, str):
        raise SystemExit("Generator packet is missing generatorId")
    cycle_vertices = generator.get("representativeSpecimenIds")
    if not isinstance(cycle_vertices, list) or not all(
        isinstance(item, str) for item in cycle_vertices
    ):
        raise SystemExit("Generator packet is missing representativeSpecimenIds")
    rotated = _rotated_cycle(cycle_vertices, start_index)
    oriented_cycle = rotated + [rotated[0]]
    edge_lookup = _edge_lookup(generator)
    edge_records: list[dict[str, Any]] = []
    edge_paths: list[list[str]] = []
    for from_id, to_id in zip(oriented_cycle, oriented_cycle[1:], strict=False):
        key = frozenset({from_id, to_id})
        if key not in edge_lookup:
            raise SystemExit(f"{generator_id}: missing cycle edge for {from_id} -> {to_id}")
        edge_index, stored_from, stored_to = edge_lookup[key]
        anchor = "left" if (stored_from, stored_to) == (from_id, to_id) else "right"
        representative_path = _load_representative_path(
            sweep_root,
            generator_id,
            edge_index,
            anchor,
        )
        edge_paths.append(representative_path)
        edge_records.append(
            {
                "edgeIndex": edge_index,
                "anchor": anchor,
                "fromSpecimenId": from_id,
                "toSpecimenId": to_id,
                "fromSpecimenLabel": _specimen_suffix(from_id),
                "toSpecimenLabel": _specimen_suffix(to_id),
                "representativePath": representative_path,
            }
        )

    concatenated = _collapse_concatenation(edge_paths)
    cycle_vertex_set = {item for item in cycle_vertices if isinstance(item, str)}
    cycle_path = _cycle_only_path(concatenated, cycle_vertex_set)
    start_vertex = rotated[0]
    end_vertex = cycle_path[-1] if cycle_path else None
    start_next, end_prev = _distinct_neighbors(cycle_path, start_vertex)
    expected_successor = rotated[1]
    expected_predecessor = rotated[-1]
    return_offset = None
    if isinstance(end_vertex, str) and end_vertex in cycle_vertices:
        start_position = cycle_vertices.index(start_vertex)
        end_position = cycle_vertices.index(end_vertex)
        return_offset = (end_position - start_position) % len(cycle_vertices)
    return {
        "startIndex": start_index,
        "startSpecimenId": start_vertex,
        "startSpecimenLabel": _specimen_suffix(start_vertex),
        "expectedSuccessorId": expected_successor,
        "expectedSuccessorLabel": _specimen_suffix(expected_successor),
        "expectedPredecessorId": expected_predecessor,
        "expectedPredecessorLabel": _specimen_suffix(expected_predecessor),
        "edgeTraversals": edge_records,
        "concatenatedRepresentativePath": concatenated,
        "concatenatedCycleVertexPath": cycle_path,
        "visitedAllCycleVertices": set(cycle_path) == cycle_vertex_set,
        "cycleVertexVisitCounts": {
            _specimen_suffix(vertex): cycle_path.count(vertex) for vertex in cycle_vertices
        },
        "endSpecimenId": end_vertex,
        "endSpecimenLabel": _specimen_suffix(end_vertex) if isinstance(end_vertex, str) else None,
        "returnsToStart": end_vertex == start_vertex,
        "returnOffset": return_offset,
        "startDepartureId": start_next,
        "startDepartureLabel": (
            _specimen_suffix(start_next) if isinstance(start_next, str) else None
        ),
        "finalArrivalId": end_prev,
        "finalArrivalLabel": _specimen_suffix(end_prev) if isinstance(end_prev, str) else None,
        "orientationConsistent": (
            start_next == expected_successor and end_prev == expected_predecessor
        ),
    }


def analyze_generator_circuits(
    packet_path: Path,
    sweep_root: Path,
    output_dir: Path,
    *,
    generator_ids: set[str] | None = None,
) -> dict[str, Any]:
    packet = _load_generator_packet(packet_path)
    generators = packet["generators"]
    reports: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for generator in generators:
        if not isinstance(generator, dict):
            raise SystemExit("Generator rows must be objects")
        generator_id = generator.get("generatorId")
        if not isinstance(generator_id, str):
            raise SystemExit("Generator packet is missing generatorId")
        if generator_ids is not None and generator_id not in generator_ids:
            continue
        cycle_vertices = generator.get("representativeSpecimenIds")
        if not isinstance(cycle_vertices, list) or not all(
            isinstance(item, str) for item in cycle_vertices
        ):
            raise SystemExit("Generator packet is missing representativeSpecimenIds")
        circuits = [
            _circuit_record(generator=generator, sweep_root=sweep_root, start_index=start_index)
            for start_index in range(len(cycle_vertices))
        ]
        report = {
            "generatorId": generator_id,
            "representation": packet.get("representation"),
            "persistence": generator.get("persistence"),
            "cycleVertexIds": cycle_vertices,
            "cycleVertexLabels": [_specimen_suffix(specimen_id) for specimen_id in cycle_vertices],
            "circuitCount": len(circuits),
            "exactVertexReturnCount": sum(bool(item["returnsToStart"]) for item in circuits),
            "orientationConsistentCount": sum(
                bool(item["orientationConsistent"]) for item in circuits
            ),
            "visitedAllCycleVerticesCount": sum(
                bool(item["visitedAllCycleVertices"]) for item in circuits
            ),
            "circuits": circuits,
        }
        reports.append(report)
        (output_dir / f"{generator_id}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    aggregate = {
        "version": 1,
        "packetKind": "topology_generator_circuit_analysis_v1",
        "generatorCount": len(reports),
        "generators": reports,
        "aggregate": {
            "generatorCount": len(reports),
            "exactVertexReturnGeneratorCount": sum(
                item["circuitCount"] == item["exactVertexReturnCount"] for item in reports
            ),
            "orientationConsistentGeneratorCount": sum(
                item["circuitCount"] == item["orientationConsistentCount"] for item in reports
            ),
            "fullCycleCoverageGeneratorCount": sum(
                item["circuitCount"] == item["visitedAllCycleVerticesCount"] for item in reports
            ),
            "topGenerators": sorted(
                reports,
                key=lambda item: (
                    -int(item["visitedAllCycleVerticesCount"]),
                    -int(item["exactVertexReturnCount"]),
                    -float(item.get("persistence") or 0.0),
                ),
            )[:8],
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return aggregate


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compose full ordered generator circuits from symmetry continuation sweeps."
    )
    parser.add_argument("--generator-packet", required=True)
    parser.add_argument("--sweep-root", required=True)
    parser.add_argument("--output", help="Output directory for circuit analysis packet")
    parser.add_argument(
        "--generator-id",
        action="append",
        help="Restrict to a specific generatorId; pass multiple times",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet_path = Path(args.generator_packet).expanduser().resolve()
    sweep_root = Path(args.sweep_root).expanduser().resolve()
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(sweep_root).resolve()
    )
    generator_ids = set(args.generator_id) if args.generator_id else None
    analyze_generator_circuits(packet_path, sweep_root, output_dir, generator_ids=generator_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
