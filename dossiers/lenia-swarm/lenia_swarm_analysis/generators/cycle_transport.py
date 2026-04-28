from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return payload


def _default_output_dir(sweep_root: Path) -> Path:
    return sweep_root.parent.parent / "topology-generator-cycle-transport" / sweep_root.name


def _row_map(rows: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
    mapping: dict[float, dict[str, Any]] = {}
    for row in rows:
        global_alpha = row.get("globalAlpha")
        if isinstance(global_alpha, (int, float)):
            mapping[round(float(global_alpha), 6)] = row
    return mapping


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise SystemExit(f"{path}: expected a JSON array of objects")
    return rows


def _anchor_equivalent(
    left_summary: dict[str, Any] | None,
    right_summary: dict[str, Any] | None,
) -> bool | None:
    if left_summary is None or right_summary is None:
        return None
    left_rows_path = left_summary.get("rowsPath")
    right_rows_path = right_summary.get("rowsPath")
    if not isinstance(left_rows_path, str) or not isinstance(right_rows_path, str):
        return None
    left_map = _row_map(_load_rows(Path(left_rows_path)))
    right_map = _row_map(_load_rows(Path(right_rows_path)))
    comparable = sorted(set(left_map) & set(right_map))
    if not comparable:
        return None
    for alpha in comparable:
        left = left_map[alpha]
        right = right_map[alpha]
        if left.get("controlLabel") != right.get("controlLabel"):
            return False
        if (
            left.get("nearestRepresentativeSpecimenId")
            != right.get("nearestRepresentativeSpecimenId")
        ):
            return False
        if not math.isclose(float(left.get("distToA", 0.0)), float(right.get("distToA", 0.0))):
            return False
        if not math.isclose(float(left.get("distToB", 0.0)), float(right.get("distToB", 0.0))):
            return False
        if not math.isclose(
            float(left.get("distToCycleSupport", 0.0)),
            float(right.get("distToCycleSupport", 0.0)),
        ):
            return False
    return True


def _specimen_suffix(specimen_id: str) -> str:
    return specimen_id.split("|")[-1] if "|" in specimen_id else specimen_id


def _load_generator_packet(packet_path: Path) -> dict[str, Any]:
    packet = _read_json(packet_path)
    generators = packet.get("generators")
    if not isinstance(generators, list):
        raise SystemExit(f"{packet_path}: missing generators[]")
    return packet


def _edge_summary_path(sweep_root: Path, generator_id: str, edge_index: int, anchor: str) -> Path:
    return sweep_root / generator_id / f"edge{edge_index:02d}" / f"{anchor}-anchor" / "summary.json"


def _filtered_path(
    representative_path: list[str],
    *,
    allowed: set[str],
    excluded: set[str],
) -> list[str]:
    filtered: list[str] = []
    for specimen_id in representative_path:
        if specimen_id not in allowed or specimen_id in excluded:
            continue
        if not filtered or filtered[-1] != specimen_id:
            filtered.append(specimen_id)
    return filtered


def _edge_record(
    *,
    generator: dict[str, Any],
    edge_index: int,
    edge: dict[str, Any],
    left_summary: dict[str, Any] | None,
    right_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    if left_summary is None and right_summary is None:
        raise SystemExit("Missing both anchor summaries for edge")
    canonical = left_summary or right_summary
    assert canonical is not None
    continuation = canonical.get("continuation", {})
    if not isinstance(continuation, dict):
        raise SystemExit("Malformed continuation payload")
    representative_path = continuation.get("collapsedRepresentativePath", [])
    if not isinstance(representative_path, list) or not all(
        isinstance(item, str) for item in representative_path
    ):
        raise SystemExit("Continuation summary is missing collapsedRepresentativePath")
    from_id = edge.get("fromSpecimenId")
    to_id = edge.get("toSpecimenId")
    if not isinstance(from_id, str) or not isinstance(to_id, str):
        raise SystemExit("Generator edge is missing fromSpecimenId/toSpecimenId")
    cycle_vertices = generator.get("representativeSpecimenIds", [])
    if not isinstance(cycle_vertices, list) or not all(
        isinstance(item, str) for item in cycle_vertices
    ):
        raise SystemExit("Generator packet is missing representativeSpecimenIds")
    cycle_vertex_set = {item for item in cycle_vertices if isinstance(item, str)}
    cycle_vertex_path = _filtered_path(
        representative_path,
        allowed=cycle_vertex_set,
        excluded=set(),
    )
    interior_cycle_vertices = _filtered_path(
        representative_path,
        allowed=cycle_vertex_set,
        excluded={from_id, to_id},
    )
    return {
        "edgeIndex": edge_index,
        "fromSpecimenId": from_id,
        "toSpecimenId": to_id,
        "fromSpecimenLabel": _specimen_suffix(from_id),
        "toSpecimenLabel": _specimen_suffix(to_id),
        "hasLeftAnchor": left_summary is not None,
        "hasRightAnchor": right_summary is not None,
        "anchorEquivalent": _anchor_equivalent(left_summary, right_summary),
        "hasReentry": bool(continuation.get("hasReentry", False)),
        "ambiguousCount": int(continuation.get("ambiguousCount", 0)),
        "representativeVisitCount": int(continuation.get("representativeVisitCount", 0)),
        "representativePath": representative_path,
        "cycleVertexPath": cycle_vertex_path,
        "interiorCycleVertexPath": interior_cycle_vertices,
        "visitsInteriorCycleVertex": bool(interior_cycle_vertices),
    }


def analyze_cycle_transport(
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
        cycle_edges = generator.get("cycleEdges", [])
        if not isinstance(cycle_edges, list):
            raise SystemExit(f"{generator_id}: cycleEdges must be a list")
        typed_cycle_edges: list[dict[str, Any]] = []
        for edge in cycle_edges:
            if not isinstance(edge, dict):
                raise SystemExit(f"{generator_id}: cycleEdges rows must be objects")
            typed_cycle_edges.append(edge)
        edge_reports: list[dict[str, Any]] = []
        vertex_visit_counts: dict[str, int] = {}
        full_coverage = True
        for edge_index, edge in enumerate(typed_cycle_edges):
            left_path = _edge_summary_path(sweep_root, generator_id, edge_index, "left")
            right_path = _edge_summary_path(sweep_root, generator_id, edge_index, "right")
            left_summary = _read_json(left_path) if left_path.is_file() else None
            right_summary = _read_json(right_path) if right_path.is_file() else None
            if left_summary is None and right_summary is None:
                full_coverage = False
                continue
            edge_report = _edge_record(
                generator=generator,
                edge_index=edge_index,
                edge=edge,
                left_summary=left_summary,
                right_summary=right_summary,
            )
            for specimen_id in edge_report["cycleVertexPath"]:
                vertex_visit_counts[specimen_id] = vertex_visit_counts.get(specimen_id, 0) + 1
            edge_reports.append(edge_report)

        cycle_vertices = generator.get("representativeSpecimenIds", [])
        assert isinstance(cycle_vertices, list)
        repeated_vertices = {
            specimen_id: count
            for specimen_id, count in vertex_visit_counts.items()
            if count > 1
        }
        report = {
            "generatorId": generator_id,
            "representation": packet.get("representation"),
            "persistence": generator.get("persistence"),
            "cycleVertexIds": cycle_vertices,
            "cycleVertexLabels": [_specimen_suffix(specimen_id) for specimen_id in cycle_vertices],
            "edgeCount": len(typed_cycle_edges),
            "coveredEdgeCount": len(edge_reports),
            "fullCoverage": full_coverage and len(edge_reports) == len(typed_cycle_edges),
            "reentryEdgeCount": sum(bool(edge["hasReentry"]) for edge in edge_reports),
            "ambiguousEdgeCount": sum(edge["ambiguousCount"] > 0 for edge in edge_reports),
            "anchorEquivalentEdgeCount": sum(
                edge["anchorEquivalent"] is True for edge in edge_reports
            ),
            "interiorCycleVertexEdgeCount": sum(
                bool(edge["visitsInteriorCycleVertex"]) for edge in edge_reports
            ),
            "interiorCycleVerticesVisited": sorted(
                {
                    specimen_id
                    for edge in edge_reports
                    for specimen_id in edge["interiorCycleVertexPath"]
                }
            ),
            "interiorCycleVertexLabels": sorted(
                {
                    _specimen_suffix(specimen_id)
                    for edge in edge_reports
                    for specimen_id in edge["interiorCycleVertexPath"]
                }
            ),
            "repeatedCycleVertexVisits": {
                _specimen_suffix(specimen_id): count
                for specimen_id, count in sorted(repeated_vertices.items())
            },
            "edgeReports": edge_reports,
        }
        reports.append(report)
        (output_dir / f"{generator_id}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    aggregate = {
        "version": 1,
        "packetKind": "topology_generator_cycle_transport_v1",
        "generatorCount": len(reports),
        "generators": reports,
        "aggregate": {
            "generatorCount": len(reports),
            "fullCoverageCount": sum(bool(item["fullCoverage"]) for item in reports),
            "interiorCycleVertexGeneratorCount": sum(
                bool(item["interiorCycleVertexEdgeCount"]) for item in reports
            ),
            "fullyAnchorEquivalentCount": sum(
                item["edgeCount"] == item["anchorEquivalentEdgeCount"] for item in reports
            ),
            "topGenerators": sorted(
                reports,
                key=lambda item: (
                    -int(item["interiorCycleVertexEdgeCount"]),
                    -int(item["reentryEdgeCount"]),
                    int(item["ambiguousEdgeCount"]),
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
        description="Analyze full-cycle continuation transport from generator-edge sweeps."
    )
    parser.add_argument("--generator-packet", required=True)
    parser.add_argument("--sweep-root", required=True)
    parser.add_argument("--output", help="Output directory for cycle transport packet")
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
    analyze_cycle_transport(packet_path, sweep_root, output_dir, generator_ids=generator_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
