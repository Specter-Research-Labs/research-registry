#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.fiber._common import coarse_alpha_grid, write_json
from lenia_swarm_analysis.fiber.packets import load_generator_packet

from .charted_continuation import _generator_pair, run_continuation


def _edge_output_dir(output_root: Path, generator_id: str, edge_index: int) -> Path:
    return output_root / generator_id / f"edge-{edge_index:02d}"


def _generator_row(
    packet: Any,
    generator: Any,
    edge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "packetKind": packet.packet_kind,
        "representation": packet.representation,
        "generatorId": generator.generator_id,
        "persistence": generator.persistence,
        "edgeCount": len(edge_rows),
        "reentryEdgeCount": sum(1 for row in edge_rows if row["hasReentry"]),
        "nonEndpointRepresentativeEdgeCount": sum(
            1 for row in edge_rows if row["visitsNonEndpointRepresentative"]
        ),
        "maxEscapeRatio": max(
            (
                float(row["maxEscapeRatio"])
                for row in edge_rows
                if row["maxEscapeRatio"] is not None
            ),
            default=None,
        ),
        "maxDistanceToCycleSupport": max(
            (
                float(row["maxDistanceToCycleSupport"])
                for row in edge_rows
                if row["maxDistanceToCycleSupport"] is not None
            ),
            default=None,
        ),
        "maxRepresentativeVisitCount": max(
            (
                int(row["representativeVisitCount"])
                for row in edge_rows
                if row["representativeVisitCount"] is not None
            ),
            default=0,
        ),
        "interestingEdges": sorted(
            edge_rows,
            key=lambda row: (
                -int(bool(row["hasReentry"])),
                -int(bool(row["visitsNonEndpointRepresentative"])),
                -(
                    float(row["maxEscapeRatio"])
                    if row["maxEscapeRatio"] is not None
                    else -1.0
                ),
                -int(row["branchSwitchCount"]),
                int(row["edgeIndex"]),
            ),
        )[:5],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run charted continuation over the cycle edges of top persistent generators."
    )
    parser.add_argument(
        "--generator-packet",
        required=True,
        help="Path to topology generator packet JSON",
    )
    parser.add_argument(
        "--replay-root",
        required=True,
        help="Replay root containing source campaigns",
    )
    parser.add_argument("--cli-binary", required=True, help="Path to LeniaCLI binary")
    parser.add_argument("--output", required=True, help="Output directory for report artifacts")
    parser.add_argument(
        "--top-generators",
        type=int,
        default=3,
        help="Number of top generators from the packet to analyze",
    )
    parser.add_argument(
        "--alphas",
        default="0.0,0.25,0.5,0.75,1.0",
        help="Comma-separated continuation alphas including 0 and 1",
    )
    parser.add_argument(
        "--ambiguity-threshold",
        type=float,
        default=0.002,
        help="Phenotype-distance tie threshold for ambiguous control assignment",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet_path = Path(args.generator_packet).expanduser().resolve()
    replay_root = Path(args.replay_root).expanduser().resolve()
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()
    alphas = coarse_alpha_grid(args.alphas)

    packet = load_generator_packet(packet_path)
    generators = list(packet.generators[: args.top_generators])
    edge_rows: list[dict[str, Any]] = []
    generator_rows: list[dict[str, Any]] = []

    for generator in generators:
        generator_edge_rows: list[dict[str, Any]] = []
        edge_count = max(1, len(generator.cycle_edges))
        for edge_index in range(edge_count):
            left, right, source_summary = _generator_pair(
                packet_path=packet_path,
                replay_root=replay_root,
                generator_id=generator.generator_id,
                edge_index=edge_index,
                source_manifest=None,
            )
            source_summary["sourceKind"] = "generator_edge"
            edge_output_dir = _edge_output_dir(output_root, generator.generator_id, edge_index)
            summary = run_continuation(
                cli_binary=cli_binary,
                output_root=edge_output_dir,
                left=left,
                right=right,
                source_specimen=left,
                source_anchor="left",
                alphas=alphas,
                ambiguity_threshold=args.ambiguity_threshold,
                db_path=None,
                source_summary=source_summary,
            )
            edge_row = {
                "generatorId": generator.generator_id,
                "generatorPersistence": generator.persistence,
                "edgeIndex": edge_index,
                "leftSpecimenId": summary["leftSpecimenId"],
                "rightSpecimenId": summary["rightSpecimenId"],
                "outputDir": str(edge_output_dir),
                **summary["continuation"],
            }
            edge_rows.append(edge_row)
            generator_edge_rows.append(edge_row)
        generator_rows.append(_generator_row(packet, generator, generator_edge_rows))

    summary = {
        "packetPath": str(packet_path),
        "representation": packet.representation,
        "packetKind": packet.packet_kind,
        "topGenerators": args.top_generators,
        "generatorCount": len(generator_rows),
        "edgeCount": len(edge_rows),
        "generatorSummaries": generator_rows,
        "topEdges": sorted(
            edge_rows,
            key=lambda row: (
                -int(bool(row["hasReentry"])),
                -int(bool(row["visitsNonEndpointRepresentative"])),
                -(float(row["maxEscapeRatio"]) if row["maxEscapeRatio"] is not None else -1.0),
                -int(row["branchSwitchCount"]),
                str(row["generatorId"]),
                int(row["edgeIndex"]),
            ),
        )[:10],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", summary)
    write_json(output_root / "generator-summaries.json", generator_rows)
    write_json(output_root / "edge-summaries.json", edge_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
