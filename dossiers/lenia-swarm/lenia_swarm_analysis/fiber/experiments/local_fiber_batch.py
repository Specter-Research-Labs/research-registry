#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.fiber._common import (
    CandidatePair,
    ReplayOutcome,
    adjacent_status_brackets,
    coarse_alpha_grid,
    extract_result_metrics,
    has_interior_failure_band,
    interpolate_payload,
    l2_distance,
    load_candidate_pairs,
    max_contiguous_success_from_a,
    pair_slug,
    perturb_midpoint_payload,
    read_jsonl,
    run_variant,
    success_components,
    write_json,
    write_jsonl,
)


def midpoint_variants() -> list[str]:
    return [
        "midpoint",
        "delta-p010",
        "delta-m010",
        "rand1-p005",
        "rand1-m005",
        "rand2-p005",
        "rand2-m005",
    ]


def outcome_row(
    *,
    alpha: float | None,
    outcome: ReplayOutcome,
    fingerprint_a,
    fingerprint_b,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "alpha": alpha,
        "name": outcome.name,
        "returncode": outcome.returncode,
        "runId": outcome.run_id,
        "runDir": str(outcome.run_dir),
    }
    if outcome.stdout_tail:
        row["stdoutTail"] = outcome.stdout_tail
    if outcome.stderr_tail:
        row["stderrTail"] = outcome.stderr_tail
    if outcome.results_path is not None:
        row["resultsPath"] = str(outcome.results_path)
    if outcome.returncode == 0 and outcome.fingerprint is not None:
        row["distToA"] = l2_distance(outcome.fingerprint, fingerprint_a)
        row["distToB"] = l2_distance(outcome.fingerprint, fingerprint_b)
        row["dominantOrder"] = outcome.dominant_order
        row["dominantAmplitude"] = outcome.dominant_amplitude
    return row


def bisect_transition(
    *,
    cli_binary: Path,
    output_root: Path,
    pair_slug_value: str,
    source_specimen,
    specimen_a,
    specimen_b,
    left: dict[str, Any],
    right: dict[str, Any],
    rounds: int,
    db_path: Path | None,
) -> list[dict[str, Any]]:
    low = left
    high = right
    outcomes: list[dict[str, Any]] = []
    for round_index in range(rounds):
        alpha = (float(low["alpha"]) + float(high["alpha"])) / 2.0
        variant_slug = f"bisect-{int(round(float(low['alpha']) * 1000)):04d}-{int(round(float(high['alpha']) * 1000)):04d}-{round_index}"
        payload = interpolate_payload(specimen_a, specimen_b, alpha)
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=pair_slug_value,
            variant_slug=variant_slug,
            source_specimen=source_specimen,
            payload=payload,
            reason=f"fiber-bisect:{pair_slug_value}:{alpha:.6f}",
            run_id=f"fiber-{pair_slug_value}-{variant_slug}",
            db_path=db_path,
        )
        row = outcome_row(
            alpha=alpha,
            outcome=outcome,
            fingerprint_a=specimen_a.baseline_fingerprint,
            fingerprint_b=specimen_b.baseline_fingerprint,
        )
        outcomes.append(row)
        if (row.get("returncode") == 0) == (low.get("returncode") == 0):
            low = row
        else:
            high = row
    return outcomes


def build_transition_graph(bridge_rows: list[dict[str, Any]], midpoint_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        (row for row in bridge_rows if isinstance(row.get("alpha"), (int, float))),
        key=lambda row: float(row["alpha"]),
    )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in ordered:
        nodes.append(
            {
                "id": row["name"],
                "kind": "bridge",
                "alpha": row["alpha"],
                "success": row.get("returncode") == 0,
            }
        )
    previous_success = None
    for row in ordered:
        if row.get("returncode") == 0:
            if previous_success is not None:
                edges.append(
                    {
                        "source": previous_success["name"],
                        "target": row["name"],
                        "family": "continuation",
                    }
                )
            previous_success = row
        else:
            previous_success = None
    for row in midpoint_rows:
        nodes.append(
            {
                "id": row["name"],
                "kind": "perturbation",
                "success": row.get("returncode") == 0,
            }
        )
        if row["name"] != "midpoint" and row.get("returncode") == 0:
            edges.append(
                {
                    "source": "midpoint",
                    "target": row["name"],
                    "family": "midpoint-perturbation",
                }
            )
    barrier_brackets = [
        {
            "leftAlpha": float(left["alpha"]),
            "leftSuccess": left.get("returncode") == 0,
            "rightAlpha": float(right["alpha"]),
            "rightSuccess": right.get("returncode") == 0,
        }
        for left, right in adjacent_status_brackets(ordered)
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "barrierBrackets": barrier_brackets,
        "successComponents": [
            {
                "fromAlpha": float(component[0]["alpha"]),
                "toAlpha": float(component[-1]["alpha"]),
                "members": [row["name"] for row in component],
            }
            for component in success_components(ordered)
        ],
    }


def run_pair_study(
    *,
    cli_binary: Path,
    output_root: Path,
    pair: CandidatePair,
    coarse_alphas: list[float],
    bisect_rounds: int,
    param_delta: float,
    random_scale: float,
    db_path: Path | None,
) -> dict[str, Any]:
    pair_slug_value = pair_slug(pair)
    source_specimen = pair.specimen_a
    bridge_rows: list[dict[str, Any]] = []

    for alpha in coarse_alphas:
        if alpha == 0.0:
            bridge_rows.append(
                {
                    "alpha": 0.0,
                    "name": "bridge-a000",
                    "returncode": 0,
                    "distToA": 0.0,
                    "distToB": l2_distance(
                        pair.specimen_a.baseline_fingerprint,
                        pair.specimen_b.baseline_fingerprint,
                    ),
                    "dominantOrder": pair.specimen_a.dominant_order,
                    "dominantAmplitude": pair.specimen_a.dominant_amplitude,
                }
            )
            continue
        if alpha == 1.0:
            bridge_rows.append(
                {
                    "alpha": 1.0,
                    "name": "bridge-a1000",
                    "returncode": 0,
                    "distToA": l2_distance(
                        pair.specimen_a.baseline_fingerprint,
                        pair.specimen_b.baseline_fingerprint,
                    ),
                    "distToB": 0.0,
                    "dominantOrder": pair.specimen_b.dominant_order,
                    "dominantAmplitude": pair.specimen_b.dominant_amplitude,
                }
            )
            continue
        variant_slug = f"bridge-a{int(round(alpha * 1000)):03d}"
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=pair_slug_value,
            variant_slug=variant_slug,
            source_specimen=source_specimen,
            payload=interpolate_payload(pair.specimen_a, pair.specimen_b, alpha),
            reason=f"fiber-bridge:{pair_slug_value}:{alpha:.6f}",
            run_id=f"fiber-{pair_slug_value}-{variant_slug}",
            db_path=db_path,
        )
        bridge_rows.append(
            outcome_row(
                alpha=alpha,
                outcome=outcome,
                fingerprint_a=pair.specimen_a.baseline_fingerprint,
                fingerprint_b=pair.specimen_b.baseline_fingerprint,
            )
        )

    bisection_rows: list[dict[str, Any]] = []
    for left, right in adjacent_status_brackets(bridge_rows):
        bisection_rows.extend(
            bisect_transition(
                cli_binary=cli_binary,
                output_root=output_root,
                pair_slug_value=pair_slug_value,
                source_specimen=source_specimen,
                specimen_a=pair.specimen_a,
                specimen_b=pair.specimen_b,
                left=left,
                right=right,
                rounds=bisect_rounds,
                db_path=db_path,
            )
        )

    all_bridge_rows = sorted(
        bridge_rows + bisection_rows,
        key=lambda row: (float(row["alpha"]), row["name"]),
    )

    midpoint_payload = interpolate_payload(pair.specimen_a, pair.specimen_b, 0.5)
    midpoint_rows: list[dict[str, Any]] = []
    midpoint_fingerprint = None
    for variant_name in midpoint_variants():
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=pair_slug_value,
            variant_slug=variant_name,
            source_specimen=source_specimen,
            payload=perturb_midpoint_payload(
                midpoint_payload,
                variant_name=variant_name,
                param_delta=param_delta,
                random_scale=random_scale,
            ),
            reason=f"fiber-midpoint:{pair_slug_value}:{variant_name}",
            run_id=f"fiber-{pair_slug_value}-{variant_name}",
            db_path=db_path,
        )
        row = outcome_row(
            alpha=None,
            outcome=outcome,
            fingerprint_a=pair.specimen_a.baseline_fingerprint,
            fingerprint_b=pair.specimen_b.baseline_fingerprint,
        )
        if variant_name == "midpoint" and outcome.fingerprint is not None:
            midpoint_fingerprint = outcome.fingerprint
        midpoint_rows.append(row)

    if midpoint_fingerprint is None:
        raise SystemExit(f"{pair_slug_value}: midpoint replay failed")
    for row in midpoint_rows:
        results_path = row.get("resultsPath")
        if row.get("returncode") == 0 and isinstance(results_path, str):
            result_rows = read_jsonl(Path(results_path))
            fingerprint, _, _ = extract_result_metrics(result_rows[0])
            row["distToMidpoint"] = l2_distance(fingerprint, midpoint_fingerprint)

    graph = build_transition_graph(all_bridge_rows, midpoint_rows)
    pair_summary = {
        "candidateRank": pair.rank,
        "candidate": pair.row,
        "pairSlug": pair_slug_value,
        "localBridge": {
            "rows": all_bridge_rows,
            "successfulAlphas": [
                float(row["alpha"]) for row in all_bridge_rows if row.get("returncode") == 0
            ],
            "failedAlphas": [
                float(row["alpha"]) for row in all_bridge_rows if row.get("returncode") != 0
            ],
            "hasInteriorFailureBand": has_interior_failure_band(all_bridge_rows),
            "maxContiguousSuccessFromA": max_contiguous_success_from_a(all_bridge_rows),
        },
        "midpointNeighborhood": {
            "rows": midpoint_rows,
            "successCount": sum(1 for row in midpoint_rows if row.get("returncode") == 0),
            "failureCount": sum(1 for row in midpoint_rows if row.get("returncode") != 0),
            "maxDistToMidpoint": max(
                (
                    float(row["distToMidpoint"])
                    for row in midpoint_rows
                    if row.get("returncode") == 0 and "distToMidpoint" in row
                ),
                default=None,
            ),
        },
        "localTransitionGraph": graph,
    }
    pair_dir = output_root / "pairs" / pair_slug_value
    pair_dir.mkdir(parents=True, exist_ok=True)
    write_json(pair_dir / "summary.json", pair_summary)
    return pair_summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local fiber continuation and midpoint perturb studies for top qd pairs."
    )
    parser.add_argument("--candidates", required=True, help="Path to fiber-candidate candidates.json")
    parser.add_argument("--output", required=True, help="Output root for study artifacts")
    parser.add_argument(
        "--cli-binary",
        default="./.build/arm64-apple-macosx/release/LeniaCLI",
        help="Path to LeniaCLI release binary",
    )
    parser.add_argument("--replay-root", required=True, help="Root directory containing replay runs")
    parser.add_argument("--compendium", help="Optional compendium SQLite path for indexing")
    parser.add_argument("--skip-index", action="store_true", help="Do not index local variants into the compendium")
    parser.add_argument("--top-pairs", type=int, default=5, help="Number of top-ranked pairs to study")
    parser.add_argument(
        "--coarse-alphas",
        default="0,0.12,0.25,0.38,0.5,0.62,0.75,0.88,1",
        help="Comma-separated coarse interpolation grid",
    )
    parser.add_argument("--bisect-rounds", type=int, default=3, help="Bisection rounds per success/failure bracket")
    parser.add_argument("--param-delta", type=float, default=0.01, help="Midpoint perturbation magnitude for direct parameter deltas")
    parser.add_argument("--random-scale", type=float, default=0.005, help="Midpoint perturbation magnitude for random parameter steps")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_root = Path(args.output).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    replay_root = Path(args.replay_root).expanduser().resolve()
    db_path = None if args.skip_index else Path(args.compendium).expanduser().resolve() if args.compendium else None
    pairs = load_candidate_pairs(
        Path(args.candidates).expanduser().resolve(),
        replay_root,
        args.top_pairs,
    )
    coarse_alphas = coarse_alpha_grid(args.coarse_alphas)
    pair_summaries = [
        run_pair_study(
            cli_binary=Path(args.cli_binary).expanduser().resolve(),
            output_root=output_root,
            pair=pair,
            coarse_alphas=coarse_alphas,
            bisect_rounds=args.bisect_rounds,
            param_delta=args.param_delta,
            random_scale=args.random_scale,
            db_path=db_path,
        )
        for pair in pairs
    ]

    transition_edges = [
        {"pairSlug": pair_summary["pairSlug"], **edge}
        for pair_summary in pair_summaries
        for edge in pair_summary["localTransitionGraph"]["edges"]
    ]
    barrier_brackets = [
        {"pairSlug": pair_summary["pairSlug"], **bracket}
        for pair_summary in pair_summaries
        for bracket in pair_summary["localTransitionGraph"]["barrierBrackets"]
    ]
    study_summary = {
        "version": 1,
        "candidatesPath": str(Path(args.candidates).expanduser().resolve()),
        "outputRoot": str(output_root),
        "pairCount": len(pair_summaries),
        "topPairs": args.top_pairs,
        "skipIndex": args.skip_index,
        "coarseAlphas": coarse_alphas,
        "bisectRounds": args.bisect_rounds,
        "paramDelta": args.param_delta,
        "randomScale": args.random_scale,
        "interiorFailurePairCount": sum(
            1 for pair in pair_summaries if pair["localBridge"]["hasInteriorFailureBand"]
        ),
        "midpointRobustPairCount": sum(
            1 for pair in pair_summaries if pair["midpointNeighborhood"]["failureCount"] == 0
        ),
        "transitionEdgeCount": len(transition_edges),
        "barrierBracketCount": len(barrier_brackets),
        "pairs": [
            {
                "pairSlug": pair["pairSlug"],
                "candidateRank": pair["candidateRank"],
                "hasInteriorFailureBand": pair["localBridge"]["hasInteriorFailureBand"],
                "maxContiguousSuccessFromA": pair["localBridge"]["maxContiguousSuccessFromA"],
                "midpointSuccessCount": pair["midpointNeighborhood"]["successCount"],
                "midpointFailureCount": pair["midpointNeighborhood"]["failureCount"],
                "maxDistToMidpoint": pair["midpointNeighborhood"]["maxDistToMidpoint"],
                "pairSummaryPath": str(output_root / "pairs" / pair["pairSlug"] / "summary.json"),
            }
            for pair in pair_summaries
        ],
    }
    write_json(output_root / "study-summary.json", study_summary)
    write_jsonl(output_root / "transition-edges.jsonl", transition_edges)
    write_jsonl(output_root / "barrier-brackets.jsonl", barrier_brackets)
    print(
        "Local fiber study complete: "
        f"pairs={len(pair_summaries)} "
        f"interiorFailurePairs={study_summary['interiorFailurePairCount']} "
        f"midpointRobustPairs={study_summary['midpointRobustPairCount']} "
        f"output={output_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
