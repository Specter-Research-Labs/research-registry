#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.fiber._common import coarse_alpha_grid, write_json

from .charted_continuation import _candidate_pair, run_continuation


def _pair_output_dir(output_root: Path, pair_rank: int) -> Path:
    return output_root / f"pair-{pair_rank:04d}"


def _summary_row(pair_rank: int, summary: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    continuation = summary["continuation"]
    return {
        "pairRank": pair_rank,
        "leftSpecimenId": summary["leftSpecimenId"],
        "rightSpecimenId": summary["rightSpecimenId"],
        "sourceAnchor": summary["sourceAnchor"],
        "outputDir": str(output_dir),
        "successCount": continuation["successCount"],
        "failureCount": continuation["failureCount"],
        "ambiguousCount": continuation["ambiguousCount"],
        "branchSwitchCount": continuation["branchSwitchCount"],
        "collapsedControlPath": continuation["collapsedControlPath"],
        "hasReentry": continuation["hasReentry"],
        "endpointPhenotypeDistance": continuation["endpointPhenotypeDistance"],
        "maxNearestAnchorDistance": continuation["maxNearestAnchorDistance"],
        "maxEscapeRatio": continuation["maxEscapeRatio"],
        "maxStepPhenotypeDelta": continuation["maxStepPhenotypeDelta"],
        "maxPhenotypeDistanceToA": continuation["maxPhenotypeDistanceToA"],
        "maxPhenotypeDistanceToB": continuation["maxPhenotypeDistanceToB"],
    }


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pairCount": len(rows),
        "pairsWithFailures": sum(1 for row in rows if row["failureCount"] > 0),
        "pairsWithAmbiguity": sum(1 for row in rows if row["ambiguousCount"] > 0),
        "pairsWithBranchSwitch": sum(1 for row in rows if row["branchSwitchCount"] > 0),
        "pairsWithReentry": sum(1 for row in rows if row["hasReentry"]),
        "maxBranchSwitchCount": max((int(row["branchSwitchCount"]) for row in rows), default=0),
        "maxEscapeRatio": max(
            (
                float(row["maxEscapeRatio"])
                for row in rows
                if row["maxEscapeRatio"] is not None
            ),
            default=None,
        ),
        "maxStepPhenotypeDelta": max(
            (
                float(row["maxStepPhenotypeDelta"])
                for row in rows
                if row["maxStepPhenotypeDelta"] is not None
            ),
            default=None,
        ),
        "topSwitchPairs": sorted(
            rows,
            key=lambda row: (
                -int(bool(row["hasReentry"])),
                -int(row["branchSwitchCount"]),
                -(
                    float(row["maxEscapeRatio"])
                    if row["maxEscapeRatio"] is not None
                    else -1.0
                ),
                -(
                    float(row["maxStepPhenotypeDelta"])
                    if row["maxStepPhenotypeDelta"] is not None
                    else -1.0
                ),
                int(row["pairRank"]),
            ),
        )[:10],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run chart-aware continuation over a batch of ranked candidate pairs."
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help="Path to ranked fiber candidates JSON",
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
        help="Output directory for batch continuation artifacts",
    )
    parser.add_argument(
        "--top-pairs",
        type=int,
        default=20,
        help="Number of top-ranked pairs to continue",
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
    parser.add_argument("--db", help="Optional compendium database to index replay runs")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    candidates_path = Path(args.candidates).expanduser().resolve()
    replay_root = Path(args.replay_root).expanduser().resolve()
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else None
    alphas = coarse_alpha_grid(args.alphas)

    rows: list[dict[str, Any]] = []
    output_root.mkdir(parents=True, exist_ok=True)
    for pair_rank in range(1, args.top_pairs + 1):
        pair = _candidate_pair(
            candidates_path=candidates_path,
            replay_root=replay_root,
            pair_rank=pair_rank,
        )
        summary = run_continuation(
            cli_binary=cli_binary,
            output_root=_pair_output_dir(output_root, pair_rank),
            left=pair.specimen_a,
            right=pair.specimen_b,
            source_specimen=pair.specimen_a,
            source_anchor="left",
            alphas=alphas,
            ambiguity_threshold=args.ambiguity_threshold,
            db_path=db_path,
            source_summary={
                "sourceKind": "candidate_pair",
                "pairRank": pair.rank,
                "candidateRow": pair.row,
            },
        )
        rows.append(_summary_row(pair_rank, summary, _pair_output_dir(output_root, pair_rank)))

    write_json(output_root / "pair-summaries.json", rows)
    write_json(
        output_root / "study-summary.json",
        {
            "topPairs": args.top_pairs,
            "alphas": alphas,
            "aggregate": _aggregate(rows),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
