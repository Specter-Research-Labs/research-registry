#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.fiber._common import (
    coarse_alpha_grid,
    extract_result_metrics,
    find_single_results_path,
    l2_distance,
    read_jsonl,
    write_json,
)

from .charted_continuation import (
    _candidate_pair,
    _generator_pair,
    run_continuation,
)


def _row_fingerprint(row: dict[str, Any]):
    rows = read_jsonl(find_single_results_path(Path(row["runDir"])))
    if len(rows) != 1:
        raise SystemExit("expected exactly one replay result row")
    return extract_result_metrics(rows[0])[0]


def _compare_runs(
    *,
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    endpoint_distance: float,
) -> dict[str, Any]:
    if len(left_rows) != len(right_rows):
        raise SystemExit("bidirectional rows length mismatch")
    comparisons: list[dict[str, Any]] = []
    for left_row, right_row in zip(left_rows, right_rows, strict=False):
        if float(left_row["alpha"]) != float(right_row["alpha"]):
            raise SystemExit("bidirectional rows alpha mismatch")
        entry: dict[str, Any] = {
            "alpha": left_row["alpha"],
            "leftLabel": left_row["controlLabel"],
            "rightLabel": right_row["controlLabel"],
            "leftReturncode": left_row["returncode"],
            "rightReturncode": right_row["returncode"],
        }
        if left_row["returncode"] == 0 and right_row["returncode"] == 0:
            left_fingerprint = _row_fingerprint(left_row)
            right_fingerprint = _row_fingerprint(right_row)
            divergence = l2_distance(left_fingerprint, right_fingerprint)
            entry["anchorPhenotypeDelta"] = divergence
            entry["anchorDivergenceRatio"] = (
                None if endpoint_distance == 0.0 else divergence / endpoint_distance
            )
            entry["labelDisagreement"] = left_row["controlLabel"] != right_row["controlLabel"]
        else:
            entry["anchorPhenotypeDelta"] = None
            entry["anchorDivergenceRatio"] = None
            entry["labelDisagreement"] = None
        comparisons.append(entry)

    comparable = [row for row in comparisons if row["anchorPhenotypeDelta"] is not None]
    return {
        "comparisons": comparisons,
        "aggregate": {
            "comparableCount": len(comparable),
            "labelDisagreementCount": sum(1 for row in comparable if row["labelDisagreement"]),
            "maxAnchorPhenotypeDelta": max(
                (float(row["anchorPhenotypeDelta"]) for row in comparable),
                default=None,
            ),
            "maxAnchorDivergenceRatio": max(
                (
                    float(row["anchorDivergenceRatio"])
                    for row in comparable
                    if row["anchorDivergenceRatio"] is not None
                ),
                default=None,
            ),
            "meanAnchorPhenotypeDelta": (
                None
                if not comparable
                else sum(float(row["anchorPhenotypeDelta"]) for row in comparable) / len(comparable)
            ),
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare left-anchored and right-anchored chart-aware continuation."
    )
    parser.add_argument(
        "--replay-root",
        required=True,
        help="Replay root containing source campaigns",
    )
    parser.add_argument("--cli-binary", required=True, help="Path to LeniaCLI binary")
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for bidirectional artifacts",
    )
    parser.add_argument(
        "--alphas",
        default="0.0,0.0625,0.125,0.1875,0.25,0.3125,0.375,0.4375,0.5,0.5625,0.625,0.6875,0.75,0.8125,0.875,0.9375,1.0",
        help="Comma-separated continuation alphas including 0 and 1",
    )
    parser.add_argument(
        "--ambiguity-threshold",
        type=float,
        default=0.002,
        help="Phenotype-distance tie threshold for ambiguous control assignment",
    )
    parser.add_argument("--db", help="Optional compendium database to index replay runs")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--candidates", help="Path to ranked fiber candidates JSON")
    source.add_argument("--generator-packet", help="Path to topology generator packet JSON")
    parser.add_argument(
        "--pair-rank",
        type=int,
        default=1,
        help="Candidate pair rank to continue",
    )
    parser.add_argument("--generator-id", help="Generator ID within the packet")
    parser.add_argument(
        "--edge-index",
        type=int,
        default=0,
        help="Cycle edge index within the generator",
    )
    parser.add_argument(
        "--source-manifest",
        help="Optional topology export manifest if the generator packet omits it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    replay_root = Path(args.replay_root).expanduser().resolve()
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else None
    alphas = coarse_alpha_grid(args.alphas)

    if args.candidates:
        pair = _candidate_pair(
            candidates_path=Path(args.candidates).expanduser().resolve(),
            replay_root=replay_root,
            pair_rank=args.pair_rank,
        )
        left = pair.specimen_a
        right = pair.specimen_b
        source_summary = {
            "sourceKind": "candidate_pair",
            "pairRank": pair.rank,
            "candidateRow": pair.row,
        }
    else:
        if not args.generator_id:
            raise SystemExit("--generator-id is required with --generator-packet")
        left, right, source_summary = _generator_pair(
            packet_path=Path(args.generator_packet).expanduser().resolve(),
            replay_root=replay_root,
            generator_id=args.generator_id,
            edge_index=args.edge_index,
            source_manifest=(
                Path(args.source_manifest).expanduser().resolve() if args.source_manifest else None
            ),
        )
        source_summary["sourceKind"] = "generator_edge"

    left_summary = run_continuation(
        cli_binary=cli_binary,
        output_root=output_root / "left-anchor",
        left=left,
        right=right,
        source_specimen=left,
        source_anchor="left",
        alphas=alphas,
        ambiguity_threshold=args.ambiguity_threshold,
        db_path=db_path,
        source_summary=source_summary,
    )
    right_summary = run_continuation(
        cli_binary=cli_binary,
        output_root=output_root / "right-anchor",
        left=left,
        right=right,
        source_specimen=right,
        source_anchor="right",
        alphas=alphas,
        ambiguity_threshold=args.ambiguity_threshold,
        db_path=db_path,
        source_summary=source_summary,
    )

    import json

    left_rows = json.loads(
        (output_root / "left-anchor" / "rows.json").read_text(encoding="utf-8")
    )
    right_rows = json.loads(
        (output_root / "right-anchor" / "rows.json").read_text(encoding="utf-8")
    )
    comparison = _compare_runs(
        left_rows=left_rows,
        right_rows=right_rows,
        endpoint_distance=float(left_summary["continuation"]["endpointPhenotypeDistance"]),
    )
    summary = {
        "source": source_summary,
        "leftSpecimenId": left.specimen_id,
        "rightSpecimenId": right.specimen_id,
        "alphaCount": len(alphas),
        "leftContinuation": left_summary["continuation"],
        "rightContinuation": right_summary["continuation"],
        "bidirectional": comparison["aggregate"],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", summary)
    write_json(output_root / "comparison-rows.json", comparison["comparisons"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
