#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.fiber._common import (
    CandidatePair,
    CandidateSpecimen,
    l2_distance,
    load_candidate_pairs,
    pair_slug,
    run_variant,
    write_json,
)
from lenia_swarm_analysis.fiber.chart import (
    QD24ChartConfig,
    pair_direction_qd24_chart,
    perturb_qd24_payload_chart,
    qd24_chart_config,
)


def _anchor_specimens(pairs: list[CandidatePair], top_anchors: int) -> list[CandidateSpecimen]:
    ordered: list[CandidateSpecimen] = []
    seen: set[str] = set()
    for pair in pairs:
        for specimen in (pair.specimen_a, pair.specimen_b):
            if specimen.specimen_id in seen:
                continue
            seen.add(specimen.specimen_id)
            ordered.append(specimen)
            if len(ordered) >= top_anchors:
                return ordered
    return ordered


def _direction_bank(
    *,
    anchor: CandidateSpecimen,
    incident_pairs: list[CandidatePair],
    config: QD24ChartConfig,
    rng: np.random.Generator,
) -> list[tuple[str, np.ndarray]]:
    directions: list[tuple[str, np.ndarray]] = []
    seen_vectors: list[np.ndarray] = []
    for pair in incident_pairs:
        if pair.specimen_a.specimen_id == anchor.specimen_id:
            direction = pair_direction_qd24_chart(
                pair.specimen_a.payload,
                pair.specimen_b.payload,
                config,
            )
            label = f"pair-rank{pair.rank}-toward-b"
        else:
            direction = pair_direction_qd24_chart(
                pair.specimen_b.payload,
                pair.specimen_a.payload,
                config,
            )
            label = f"pair-rank{pair.rank}-toward-a"
        if any(float(np.linalg.norm(direction - prior)) < 1e-6 for prior in seen_vectors):
            continue
        seen_vectors.append(direction)
        directions.append((label, direction))

    for index in range(4):
        noise = rng.normal(size=config.genotype_size)
        norm = float(np.linalg.norm(noise))
        if norm == 0.0:
            continue
        directions.append((f"rand-{index + 1}", noise / norm))
    return directions


def _incident_pairs(pairs: list[CandidatePair], specimen_id: str) -> list[CandidatePair]:
    return [
        pair
        for pair in pairs
        if pair.specimen_a.specimen_id == specimen_id or pair.specimen_b.specimen_id == specimen_id
    ]


def run_anchor_cloud(
    *,
    cli_binary: Path,
    output_root: Path,
    anchor: CandidateSpecimen,
    incident_pairs: list[CandidatePair],
    step_sizes: list[float],
    db_path: Path | None,
) -> dict[str, Any]:
    config = qd24_chart_config(anchor.payload)
    rng = np.random.default_rng(anchor.seed)
    directions = _direction_bank(
        anchor=anchor,
        incident_pairs=incident_pairs,
        config=config,
        rng=rng,
    )
    anchor_slug = f"{pair_slug(incident_pairs[0])}-anchor-{anchor.specimen_id[:8]}"
    anchor_rows: list[dict[str, Any]] = []
    for direction_label, direction in directions:
        for step_size in step_sizes:
            variant_slug = f"{direction_label}-step-{int(round(step_size * 1000)):04d}"
            payload = perturb_qd24_payload_chart(
                anchor.payload,
                base_payload=anchor.payload,
                config=config,
                direction=direction,
                step_size=step_size,
                cell_seed=anchor.seed,
            )
            outcome = run_variant(
                cli_binary=cli_binary,
                output_root=output_root,
                pair_slug_value=anchor_slug,
                variant_slug=variant_slug,
                source_specimen=anchor,
                payload=payload,
                reason=f"fiber-chart-cloud:{anchor.specimen_id}:{direction_label}:{step_size:.4f}",
                run_id=(
                    f"fiber-chart-{anchor.specimen_id[:8]}-"
                    f"{direction_label}-{int(round(step_size * 1000)):04d}"
                ),
                db_path=db_path,
            )
            row: dict[str, Any] = {
                "anchorSpecimenId": anchor.specimen_id,
                "variant": variant_slug,
                "direction": direction_label,
                "stepSize": step_size,
                "returncode": outcome.returncode,
                "runId": outcome.run_id,
                "runDir": str(outcome.run_dir),
            }
            if outcome.returncode == 0 and outcome.fingerprint is not None:
                row["phenotypeDistanceToAnchor"] = l2_distance(
                    outcome.fingerprint,
                    anchor.baseline_fingerprint,
                )
                row["dominantOrder"] = outcome.dominant_order
                row["dominantAmplitude"] = outcome.dominant_amplitude
            anchor_rows.append(row)

    output_dir = output_root / "anchors" / anchor_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "anchorSpecimenId": anchor.specimen_id,
        "anchorRunId": anchor.run_id,
        "directionCount": len(directions),
        "stepCount": len(step_sizes),
        "variantCount": len(anchor_rows),
        "successCount": sum(1 for row in anchor_rows if row["returncode"] == 0),
        "chart": {
            "name": config.name,
            "genotypeSize": config.genotype_size,
            "nKernel": config.n_kernel,
            "nChannel": config.n_channel,
            "embryoSize": config.embryo_size,
            "isoSigma": config.iso_sigma,
            "lineSigma": config.line_sigma,
        },
    }
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "rows.json", anchor_rows)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local QD24 chart perturbation clouds around top fiber anchors."
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
        help="Output directory for chart-cloud artifacts",
    )
    parser.add_argument("--top-pairs", type=int, default=20, help="Top candidate pairs to inspect")
    parser.add_argument(
        "--top-anchors",
        type=int,
        default=8,
        help="Maximum distinct anchors to probe",
    )
    parser.add_argument(
        "--step-sizes",
        default="0.5,1.0,2.0,4.0",
        help="Comma-separated perturbation sizes measured in mutation-scale units",
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

    pairs = load_candidate_pairs(candidates_path, replay_root, args.top_pairs)
    anchors = _anchor_specimens(pairs, args.top_anchors)
    step_sizes = [float(value.strip()) for value in args.step_sizes.split(",") if value.strip()]
    output_root.mkdir(parents=True, exist_ok=True)

    summaries = []
    for anchor in anchors:
        summaries.append(
            run_anchor_cloud(
                cli_binary=cli_binary,
                output_root=output_root,
                anchor=anchor,
                incident_pairs=_incident_pairs(pairs, anchor.specimen_id),
                step_sizes=step_sizes,
                db_path=db_path,
            )
        )

    write_json(
        output_root / "study-summary.json",
        {
            "anchorCount": len(anchors),
            "pairCount": len(pairs),
            "stepSizes": step_sizes,
            "summaries": summaries,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
