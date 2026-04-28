#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from lenia_swarm_analysis.fiber._common import (
    extract_result_metrics,
    interpolate_payload,
    l2_distance,
    load_candidate_pairs,
    pair_slug,
    perturb_midpoint_payload,
    read_json,
    read_jsonl,
    run_variant,
    write_json,
)


def barrier_segments(rows: list[dict]) -> list[dict]:
    ordered = sorted(
        (row for row in rows if isinstance(row.get("alpha"), (int, float))),
        key=lambda row: float(row["alpha"]),
    )
    segments: list[dict] = []
    left_success = None
    failure_rows: list[dict] = []
    for row in ordered:
        success = row.get("returncode") == 0
        if success:
            if failure_rows and left_success is not None:
                segments.append(
                    {
                        "leftSuccess": left_success,
                        "failureRows": list(failure_rows),
                        "rightSuccess": row,
                    }
                )
                failure_rows = []
            left_success = row
        elif left_success is not None:
            failure_rows.append(row)
    return segments


def anchor_variants(prefix: str) -> list[str]:
    return [
        f"{prefix}-baseline",
        f"{prefix}-delta-p010",
        f"{prefix}-delta-m010",
        f"{prefix}-rand1-p005",
        f"{prefix}-rand1-m005",
        f"{prefix}-rand2-p005",
        f"{prefix}-rand2-m005",
    ]


def run_anchor_family(
    *,
    cli_binary: Path,
    output_root: Path,
    pair_slug_value: str,
    source_specimen,
    payload: dict,
    fingerprint_left,
    fingerprint_right,
    db_path: Path | None,
    prefix: str,
    param_delta: float,
    random_scale: float,
) -> dict:
    rows: list[dict] = []
    anchor_payloads = {
        f"{prefix}-baseline": payload,
        f"{prefix}-delta-p010": perturb_midpoint_payload(payload, variant_name="delta-p010", param_delta=param_delta, random_scale=random_scale),
        f"{prefix}-delta-m010": perturb_midpoint_payload(payload, variant_name="delta-m010", param_delta=param_delta, random_scale=random_scale),
        f"{prefix}-rand1-p005": perturb_midpoint_payload(payload, variant_name="rand1-p005", param_delta=param_delta, random_scale=random_scale),
        f"{prefix}-rand1-m005": perturb_midpoint_payload(payload, variant_name="rand1-m005", param_delta=param_delta, random_scale=random_scale),
        f"{prefix}-rand2-p005": perturb_midpoint_payload(payload, variant_name="rand2-p005", param_delta=param_delta, random_scale=random_scale),
        f"{prefix}-rand2-m005": perturb_midpoint_payload(payload, variant_name="rand2-m005", param_delta=param_delta, random_scale=random_scale),
    }

    anchor_fingerprint = None
    for variant_name in anchor_variants(prefix):
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=pair_slug_value,
            variant_slug=variant_name,
            source_specimen=source_specimen,
            payload=anchor_payloads[variant_name],
            reason=f"fiber-reconvergence:{pair_slug_value}:{variant_name}",
            run_id=f"fiber-{pair_slug_value}-{variant_name}",
            db_path=db_path,
        )
        row = {
            "name": variant_name,
            "returncode": outcome.returncode,
            "runId": outcome.run_id,
            "runDir": str(outcome.run_dir),
        }
        if outcome.stderr_tail:
            row["stderrTail"] = outcome.stderr_tail
        if outcome.returncode == 0 and outcome.fingerprint is not None:
            row["distToLeftAnchor"] = l2_distance(outcome.fingerprint, fingerprint_left)
            row["distToRightAnchor"] = l2_distance(outcome.fingerprint, fingerprint_right)
            row["dominantOrder"] = outcome.dominant_order
            row["dominantAmplitude"] = outcome.dominant_amplitude
            if variant_name.endswith("baseline"):
                anchor_fingerprint = outcome.fingerprint
        rows.append(row)

    if anchor_fingerprint is None:
        raise SystemExit(f"{prefix}: baseline reconvergence replay failed")
    for row in rows:
        if row.get("returncode") == 0:
            results_path = (
                Path(output_root)
                / "variants"
                / pair_slug_value
                / row["name"]
                / "replay"
                / "campaigns"
            )
            matches = list(results_path.glob("*/results.jsonl"))
            if len(matches) == 1:
                result_rows = read_jsonl(matches[0])
                fingerprint, _, _ = extract_result_metrics(result_rows[0])
                row["distToOwnAnchor"] = l2_distance(fingerprint, anchor_fingerprint)
                row["closerTo"] = (
                    "left" if row["distToLeftAnchor"] <= row["distToRightAnchor"] else "right"
                )
    return {
        "rows": rows,
        "successCount": sum(1 for row in rows if row.get("returncode") == 0),
        "failureCount": sum(1 for row in rows if row.get("returncode") != 0),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run reconvergence trials from both sides of local barrier bands."
    )
    parser.add_argument("--pair-summary", required=True, help="Path to a local pair summary JSON")
    parser.add_argument("--output", required=True, help="Output root for reconvergence artifacts")
    parser.add_argument(
        "--cli-binary",
        default="./.build/arm64-apple-macosx/release/LeniaCLI",
        help="Path to LeniaCLI release binary",
    )
    parser.add_argument("--replay-root", required=True, help="Root directory containing replay runs")
    parser.add_argument("--compendium", help="Optional compendium SQLite path for indexing")
    parser.add_argument("--skip-index", action="store_true", help="Do not index reconvergence variants")
    parser.add_argument("--param-delta", type=float, default=0.01, help="Direct perturbation magnitude")
    parser.add_argument("--random-scale", type=float, default=0.005, help="Random perturbation magnitude")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    pair_summary = read_json(Path(args.pair_summary).expanduser().resolve())
    candidate_row = pair_summary["candidate"]
    pair = load_candidate_pairs(
        Path(args.pair_summary).parent.parent.parent.parent / "tmp-single-candidate.json",
        Path(args.replay_root).expanduser().resolve(),
        1,
    ) if False else None

    pair = load_candidate_pairs(
        _write_temp_candidate(Path(args.output).expanduser().resolve(), candidate_row),
        Path(args.replay_root).expanduser().resolve(),
        1,
    )[0]
    pair_slug_value = str(pair_summary.get("pairSlug") or pair_slug(pair))
    segments = barrier_segments(pair_summary["localBridge"]["rows"])
    output_root = Path(args.output).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    db_path = None if args.skip_index else Path(args.compendium).expanduser().resolve() if args.compendium else None
    segment_summaries: list[dict] = []
    for index, segment in enumerate(segments, start=1):
        left_alpha = float(segment["leftSuccess"]["alpha"])
        right_alpha = float(segment["rightSuccess"]["alpha"])
        left_payload = interpolate_payload(pair.specimen_a, pair.specimen_b, left_alpha)
        right_payload = interpolate_payload(pair.specimen_a, pair.specimen_b, right_alpha)
        family_root = output_root / f"segment-{index:02d}"
        left_family = run_anchor_family(
            cli_binary=Path(args.cli_binary).expanduser().resolve(),
            output_root=family_root,
            pair_slug_value=pair_slug_value,
            source_specimen=pair.specimen_a,
            payload=left_payload,
            fingerprint_left=pair.specimen_a.baseline_fingerprint,
            fingerprint_right=pair.specimen_b.baseline_fingerprint,
            db_path=db_path,
            prefix=f"left-{left_alpha:.3f}",
            param_delta=args.param_delta,
            random_scale=args.random_scale,
        )
        right_family = run_anchor_family(
            cli_binary=Path(args.cli_binary).expanduser().resolve(),
            output_root=family_root,
            pair_slug_value=pair_slug_value,
            source_specimen=pair.specimen_a,
            payload=right_payload,
            fingerprint_left=pair.specimen_a.baseline_fingerprint,
            fingerprint_right=pair.specimen_b.baseline_fingerprint,
            db_path=db_path,
            prefix=f"right-{right_alpha:.3f}",
            param_delta=args.param_delta,
            random_scale=args.random_scale,
        )
        summary = {
            "segmentIndex": index,
            "leftSuccessAlpha": left_alpha,
            "rightSuccessAlpha": right_alpha,
            "failureAlphaRange": [
                float(segment["failureRows"][0]["alpha"]),
                float(segment["failureRows"][-1]["alpha"]),
            ],
            "leftFamily": left_family,
            "rightFamily": right_family,
        }
        write_json(family_root / "summary.json", summary)
        segment_summaries.append(summary)

    study_summary = {
        "version": 1,
        "pairSummaryPath": str(Path(args.pair_summary).expanduser().resolve()),
        "pairSlug": pair_slug_value,
        "segmentCount": len(segment_summaries),
        "segments": segment_summaries,
    }
    write_json(output_root / "study-summary.json", study_summary)
    print(
        "Reconvergence study complete: "
        f"segments={len(segment_summaries)} output={output_root}"
    )
    return 0


def _write_temp_candidate(output_root: Path, candidate_row: dict) -> Path:
    path = output_root / "tmp-single-candidate.json"
    write_json(path, [candidate_row])
    return path


if __name__ == "__main__":
    raise SystemExit(main())
