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


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SystemExit(f"{path}: expected a JSON array of objects")
    return value


def _edge_key(generator_id: str, edge_index: int) -> tuple[str, int]:
    return generator_id, edge_index


def _override_map(paths: list[Path]) -> dict[tuple[str, int], dict[str, Any]]:
    overrides: dict[tuple[str, int], dict[str, Any]] = {}
    for path in paths:
        payload = _read_json(path)
        source = payload.get("source")
        if not isinstance(source, dict):
            raise SystemExit(f"{path}: missing source block")
        generator_id = source.get("generatorId")
        edge_index = source.get("edgeIndex")
        if not isinstance(generator_id, str) or not isinstance(edge_index, int):
            raise SystemExit(f"{path}: missing source.generatorId or source.edgeIndex")
        overrides[_edge_key(generator_id, edge_index)] = payload
    return overrides


def _anchor_invariance(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    summary = payload.get("bidirectional")
    if not isinstance(summary, dict):
        raise SystemExit("bidirectional summary is missing bidirectional block")
    return {
        "checked": True,
        "comparableCount": int(summary["comparableCount"]),
        "labelDisagreementCount": int(summary["labelDisagreementCount"]),
        "maxAnchorPhenotypeDelta": float(summary["maxAnchorPhenotypeDelta"]),
        "maxAnchorDivergenceRatio": float(summary["maxAnchorDivergenceRatio"]),
        "meanAnchorPhenotypeDelta": float(summary["meanAnchorPhenotypeDelta"]),
    }


def _edge_packet(
    coarse_row: dict[str, Any],
    *,
    dense_override: dict[str, Any] | None,
    bidirectional_override: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dense_override if dense_override is not None else {"continuation": coarse_row}
    continuation = payload.get("continuation")
    if not isinstance(continuation, dict):
        raise SystemExit("continuation payload is missing continuation block")
    source = payload.get("source")
    source_artifact = payload.get("outputDir")
    if isinstance(source, dict):
        source_artifact = payload.get("outputDir") or coarse_row.get("outputDir")
    alpha_count = payload.get("alphaCount")
    edge = {
        "edgeIndex": int(coarse_row["edgeIndex"]),
        "fromSpecimenId": str(coarse_row["leftSpecimenId"]),
        "toSpecimenId": str(coarse_row["rightSpecimenId"]),
        "sourceArtifact": str(source_artifact) if source_artifact is not None else None,
        "alphaCount": (
            alpha_count
            if isinstance(alpha_count, int)
            else int(continuation["successCount"]) + int(continuation["failureCount"])
        ),
        "successCount": int(continuation["successCount"]),
        "failureCount": int(continuation["failureCount"]),
        "ambiguousCount": int(continuation["ambiguousCount"]),
        "branchSwitchCount": int(continuation["branchSwitchCount"]),
        "collapsedControlPath": list(continuation["collapsedControlPath"]),
        "hasReentry": bool(continuation["hasReentry"]),
        "collapsedRepresentativePath": list(continuation["collapsedRepresentativePath"]),
        "representativeVisitCount": int(continuation["representativeVisitCount"]),
        "visitsNonEndpointRepresentative": bool(
            continuation["visitsNonEndpointRepresentative"]
        ),
        "endpointPhenotypeDistance": float(continuation["endpointPhenotypeDistance"]),
        "maxEscapeRatio": float(continuation["maxEscapeRatio"]),
        "maxDistanceToCycleSupport": float(continuation["maxDistanceToCycleSupport"]),
        "maxNearestAnchorDistance": float(continuation["maxNearestAnchorDistance"]),
        "maxStepPhenotypeDelta": float(continuation["maxStepPhenotypeDelta"]),
        "maxPhenotypeDistanceToA": float(continuation["maxPhenotypeDistanceToA"]),
        "maxPhenotypeDistanceToB": float(continuation["maxPhenotypeDistanceToB"]),
        "anchorInvariance": _anchor_invariance(bidirectional_override),
    }
    return edge


def _generator_packet(
    generator_summary: dict[str, Any],
    edge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    interesting = sorted(
        edge_rows,
        key=lambda row: (
            -int(row["hasReentry"]),
            -int(row["visitsNonEndpointRepresentative"]),
            -float(row["maxEscapeRatio"]),
            -int(row["branchSwitchCount"]),
            int(row["edgeIndex"]),
        ),
    )[:5]
    return {
        "generatorId": str(generator_summary["generatorId"]),
        "persistence": float(generator_summary["persistence"]),
        "edgeCount": len(edge_rows),
        "reentryEdgeCount": sum(1 for row in edge_rows if row["hasReentry"]),
        "nonEndpointRepresentativeEdgeCount": sum(
            1 for row in edge_rows if row["visitsNonEndpointRepresentative"]
        ),
        "anchorInvariantEdgeCount": sum(
            1
            for row in edge_rows
            if row["anchorInvariance"] is not None
            and row["anchorInvariance"]["labelDisagreementCount"] == 0
            and row["anchorInvariance"]["maxAnchorPhenotypeDelta"] == 0.0
        ),
        "maxEscapeRatio": max(row["maxEscapeRatio"] for row in edge_rows),
        "maxDistanceToCycleSupport": max(
            row["maxDistanceToCycleSupport"] for row in edge_rows
        ),
        "maxRepresentativeVisitCount": max(row["representativeVisitCount"] for row in edge_rows),
        "interestingEdges": [row["edgeIndex"] for row in interesting],
        "edges": edge_rows,
    }


def build_cycle_lift_packet(
    *,
    report_root: Path,
    dense_summaries: list[Path],
    bidirectional_summaries: list[Path],
) -> dict[str, Any]:
    summary = _read_json(report_root / "summary.json")
    generator_summaries = _read_json_array(report_root / "generator-summaries.json")
    edge_summaries = _read_json_array(report_root / "edge-summaries.json")
    dense_map = _override_map(dense_summaries)
    bidirectional_map = _override_map(bidirectional_summaries)

    generator_rows: list[dict[str, Any]] = []
    for generator_summary in generator_summaries:
        generator_id = generator_summary["generatorId"]
        relevant_edges = [
            row for row in edge_summaries if row["generatorId"] == generator_id
        ]
        edge_rows = [
            _edge_packet(
                row,
                dense_override=dense_map.get(_edge_key(generator_id, int(row["edgeIndex"]))),
                bidirectional_override=bidirectional_map.get(
                    _edge_key(generator_id, int(row["edgeIndex"]))
                ),
            )
            for row in relevant_edges
        ]
        generator_rows.append(_generator_packet(generator_summary, edge_rows))

    top_generators = sorted(
        generator_rows,
        key=lambda row: (
            -int(row["reentryEdgeCount"]),
            -int(row["nonEndpointRepresentativeEdgeCount"]),
            -float(row["maxEscapeRatio"]),
            -float(row["persistence"]),
            str(row["generatorId"]),
        ),
    )[:5]
    top_edges = sorted(
        [edge for generator in generator_rows for edge in generator["edges"]],
        key=lambda row: (
            -int(row["hasReentry"]),
            -int(row["visitsNonEndpointRepresentative"]),
            -float(row["maxEscapeRatio"]),
            -int(row["branchSwitchCount"]),
            int(row["edgeIndex"]),
        ),
    )[:10]
    return {
        "version": 1,
        "packetKind": "cycle_lift_packet_v1",
        "representation": summary["representation"],
        "sourceGeneratorPacket": summary["packetPath"],
        "sourceContinuationReport": str(report_root / "summary.json"),
        "generatorCount": len(generator_rows),
        "edgeCount": sum(generator["edgeCount"] for generator in generator_rows),
        "generators": generator_rows,
        "topGenerators": [row["generatorId"] for row in top_generators],
        "topEdges": top_edges,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package generator-level continuation evidence into a cycle-lift packet."
    )
    parser.add_argument("--report-root", required=True, help="Generator continuation report root")
    parser.add_argument("--output", help="Output path for cycle-lift packet JSON")
    parser.add_argument(
        "--dense-summary",
        action="append",
        default=[],
        help="Dense continuation summary JSON that overrides a coarse generator-edge row",
    )
    parser.add_argument(
        "--bidirectional-summary",
        action="append",
        default=[],
        help="Bidirectional continuation summary JSON keyed by generatorId/edgeIndex",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report_root = Path(args.report_root).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (report_root / "cycle-lift-packet.json").resolve()
    )
    packet = build_cycle_lift_packet(
        report_root=report_root,
        dense_summaries=[Path(item).expanduser().resolve() for item in args.dense_summary],
        bidirectional_summaries=[
            Path(item).expanduser().resolve() for item in args.bidirectional_summary
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Cycle-lift packet:"
        f" generators={packet['generatorCount']}"
        f" edges={packet['edgeCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
