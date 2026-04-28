#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.fiber._common import (
    CandidatePair,
    CandidateSpecimen,
    coarse_alpha_grid,
    l2_distance,
    load_candidate_pairs,
    load_specimens_from_topology_rows,
    read_json,
    read_jsonl,
    run_variant,
    sanitize,
    write_json,
)
from lenia_swarm_analysis.fiber.chart import (
    interpolate_qd24_payload_chart,
    qd24_chart_config,
)
from lenia_swarm_analysis.fiber.packets import (
    generator_by_id,
    generator_edge_pair,
    load_generator_packet,
)


def _resolve_rows_path(manifest_path: Path) -> Path:
    manifest = read_json(manifest_path)
    rows_path = manifest.get("rowsPath")
    if not isinstance(rows_path, str) or not rows_path:
        raise SystemExit(f"{manifest_path}: missing rowsPath")
    candidate = Path(rows_path)
    if candidate.is_absolute():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def _candidate_pair(
    *,
    candidates_path: Path,
    replay_root: Path,
    pair_rank: int,
) -> CandidatePair:
    pairs = load_candidate_pairs(candidates_path, replay_root, max(pair_rank, 1))
    for pair in pairs:
        if pair.rank == pair_rank:
            return pair
    raise SystemExit(f"{candidates_path}: missing pair rank {pair_rank}")


def _generator_pair(
    *,
    packet_path: Path,
    replay_root: Path,
    generator_id: str,
    edge_index: int,
    source_manifest: Path | None,
) -> tuple[CandidateSpecimen, CandidateSpecimen, dict[str, Any]]:
    packet = load_generator_packet(packet_path)
    generator = generator_by_id(packet, generator_id)
    specimen_a_id, specimen_b_id = generator_edge_pair(generator, edge_index)
    manifest_path = source_manifest
    if manifest_path is None:
        if packet.source_manifest is None:
            raise SystemExit(
                "generator packet does not provide sourceManifest; "
                "pass --source-manifest"
            )
        manifest_path = Path(packet.source_manifest).expanduser().resolve()
    rows = read_jsonl(_resolve_rows_path(manifest_path))
    specimens = load_specimens_from_topology_rows(
        rows,
        replay_root=replay_root,
        specimen_ids=[specimen_a_id, specimen_b_id],
    )
    return specimens[0], specimens[1], {
        "packetPath": str(packet_path),
        "generatorId": generator_id,
        "edgeIndex": edge_index,
        "representation": packet.representation,
        "sourceManifest": str(manifest_path),
        "representativeSpecimenIds": list(generator.representative_specimen_ids),
        "memberSpecimenIds": list(generator.member_specimen_ids),
    }


def _assign_label(
    *,
    fingerprint,
    fingerprint_a,
    fingerprint_b,
    ambiguity_threshold: float,
) -> tuple[str, float, float]:
    dist_a = l2_distance(fingerprint, fingerprint_a)
    dist_b = l2_distance(fingerprint, fingerprint_b)
    if abs(dist_a - dist_b) <= ambiguity_threshold:
        return "ambiguous", dist_a, dist_b
    return ("A", dist_a, dist_b) if dist_a < dist_b else ("B", dist_a, dist_b)


def _fingerprint_from_topology_row(row: dict[str, Any]) -> np.ndarray:
    terminal = row.get("terminal")
    fingerprint = terminal.get("fingerprintU8") if isinstance(terminal, dict) else None
    if isinstance(fingerprint, list):
        return np.asarray([float(value) / 255.0 for value in fingerprint], dtype=np.float64)
    if isinstance(fingerprint, str):
        decoded = np.frombuffer(base64.b64decode(fingerprint), dtype=np.uint8)
        return decoded.astype(np.float64) / 255.0
    raise SystemExit("topology row is missing terminal.fingerprintU8")


def _support_fingerprints(
    *,
    source_summary: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    representative_ids = source_summary.get("representativeSpecimenIds")
    member_ids = source_summary.get("memberSpecimenIds")
    manifest_path = source_summary.get("sourceManifest")
    if (
        not isinstance(representative_ids, list)
        or not representative_ids
        or any(not isinstance(item, str) for item in representative_ids)
        or not isinstance(member_ids, list)
        or any(not isinstance(item, str) for item in member_ids)
        or not isinstance(manifest_path, str)
        or not manifest_path
    ):
        return {}, {}
    rows = read_jsonl(_resolve_rows_path(Path(manifest_path).expanduser().resolve()))
    rows_by_id = {
        specimen_id: row
        for row in rows
        if isinstance((specimen_id := row.get("specimenId")), str)
    }
    representative_fingerprints: dict[str, np.ndarray] = {}
    for specimen_id in representative_ids:
        row = rows_by_id.get(specimen_id)
        if row is None:
            raise SystemExit(f"topology rows are missing representative specimen {specimen_id}")
        representative_fingerprints[specimen_id] = _fingerprint_from_topology_row(row)
    member_fingerprints: dict[str, np.ndarray] = {}
    for specimen_id in member_ids:
        row = rows_by_id.get(specimen_id)
        if row is None:
            raise SystemExit(f"topology rows are missing member specimen {specimen_id}")
        member_fingerprints[specimen_id] = _fingerprint_from_topology_row(row)
    return representative_fingerprints, member_fingerprints


def _nearest_support(
    fingerprint: np.ndarray,
    support: dict[str, np.ndarray],
) -> tuple[str | None, float | None]:
    if not support:
        return None, None
    specimen_id, exemplar = min(
        support.items(),
        key=lambda item: l2_distance(fingerprint, item[1]),
    )
    return specimen_id, l2_distance(fingerprint, exemplar)


def _continuation_slug(left: CandidateSpecimen, right: CandidateSpecimen, source: str) -> str:
    return sanitize(
        f"{source}-{left.campaign_id}-{left.seed}-{right.campaign_id}-{right.seed}"
    )


def _collapsed_labels(rows: list[dict[str, Any]]) -> list[str]:
    collapsed: list[str] = []
    for row in rows:
        label = row["controlLabel"]
        if label == "ambiguous":
            continue
        if not collapsed or collapsed[-1] != label:
            collapsed.append(label)
    return collapsed


def _has_reentry(collapsed_labels: list[str]) -> bool:
    seen_indices: dict[str, int] = {}
    for index, label in enumerate(collapsed_labels):
        previous_index = seen_indices.get(label)
        if previous_index is not None and index - previous_index >= 2:
            return True
        seen_indices.setdefault(label, index)
    return False


def _collapsed_support_ids(rows: list[dict[str, Any]], field_name: str) -> list[str]:
    collapsed: list[str] = []
    for row in rows:
        specimen_id = row.get(field_name)
        if not isinstance(specimen_id, str) or not specimen_id:
            continue
        if not collapsed or collapsed[-1] != specimen_id:
            collapsed.append(specimen_id)
    return collapsed


def _rows_summary(
    rows: list[dict[str, Any]],
    *,
    left: CandidateSpecimen,
    right: CandidateSpecimen,
    representative_ids: set[str],
) -> dict[str, Any]:
    success_rows = [row for row in rows if row["returncode"] == 0]
    labels = [row["controlLabel"] for row in success_rows if row["controlLabel"] != "ambiguous"]
    switch_count = sum(
        1
        for left_label, right_label in zip(labels, labels[1:], strict=False)
        if left_label != right_label
    )
    collapsed_labels = _collapsed_labels(success_rows)
    collapsed_representative_path = _collapsed_support_ids(
        success_rows,
        "nearestRepresentativeSpecimenId",
    )
    endpoint_distance = l2_distance(left.baseline_fingerprint, right.baseline_fingerprint)
    max_nearest_anchor_distance = max(
        (
            min(float(row["distToA"]), float(row["distToB"]))
            for row in success_rows
            if row["controlLabel"] != "failed"
        ),
        default=None,
    )
    return {
        "successCount": len(success_rows),
        "failureCount": len(rows) - len(success_rows),
        "ambiguousCount": sum(1 for row in success_rows if row["controlLabel"] == "ambiguous"),
        "branchSwitchCount": switch_count,
        "collapsedControlPath": collapsed_labels,
        "hasReentry": _has_reentry(collapsed_labels),
        "collapsedRepresentativePath": collapsed_representative_path,
        "representativeVisitCount": len(collapsed_representative_path),
        "visitsNonEndpointRepresentative": any(
            specimen_id not in representative_ids
            for specimen_id in collapsed_representative_path
        ),
        "endpointPhenotypeDistance": endpoint_distance,
        "maxNearestAnchorDistance": max_nearest_anchor_distance,
        "maxEscapeRatio": (
            None
            if max_nearest_anchor_distance is None or endpoint_distance == 0.0
            else max_nearest_anchor_distance / endpoint_distance
        ),
        "maxDistanceToCycleSupport": max(
            (
                float(row["distToCycleSupport"])
                for row in success_rows
                if row.get("distToCycleSupport") is not None
            ),
            default=None,
        ),
        "maxStepPhenotypeDelta": max(
            (
                float(row["stepPhenotypeDelta"])
                for row in success_rows
                if row.get("stepPhenotypeDelta") is not None
            ),
            default=None,
        ),
        "maxPhenotypeDistanceToA": max(
            (float(row["distToA"]) for row in success_rows),
            default=None,
        ),
        "maxPhenotypeDistanceToB": max(
            (float(row["distToB"]) for row in success_rows),
            default=None,
        ),
    }


def run_continuation(
    *,
    cli_binary: Path,
    output_root: Path,
    left: CandidateSpecimen,
    right: CandidateSpecimen,
    source_specimen: CandidateSpecimen,
    source_anchor: str,
    alphas: list[float],
    ambiguity_threshold: float,
    db_path: Path | None,
    source_summary: dict[str, Any],
) -> dict[str, Any]:
    config = qd24_chart_config(left.payload)
    continuation_slug = _continuation_slug(left, right, source_summary["sourceKind"])
    representative_fingerprints, member_fingerprints = _support_fingerprints(
        source_summary=source_summary,
    )
    rows: list[dict[str, Any]] = []
    previous_fingerprint = None
    for alpha in alphas:
        variant_slug = f"alpha-{int(round(alpha * 1000)):04d}"
        payload = interpolate_qd24_payload_chart(
            left.payload,
            right.payload,
            alpha,
            config,
            cell_seed=left.seed,
        )
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=continuation_slug,
            variant_slug=variant_slug,
            source_specimen=source_specimen,
            payload=payload,
            reason=f"fiber-chart-continuation:{continuation_slug}:{alpha:.6f}",
            run_id=(
                f"fiber-chart-continuation-{source_anchor}-"
                f"{continuation_slug}-{int(round(alpha * 1000)):04d}"
            ),
            db_path=db_path,
        )
        row: dict[str, Any] = {
            "alpha": alpha,
            "variant": variant_slug,
            "returncode": outcome.returncode,
            "runId": outcome.run_id,
            "runDir": str(outcome.run_dir),
        }
        if outcome.returncode == 0 and outcome.fingerprint is not None:
            label, dist_a, dist_b = _assign_label(
                fingerprint=outcome.fingerprint,
                fingerprint_a=left.baseline_fingerprint,
                fingerprint_b=right.baseline_fingerprint,
                ambiguity_threshold=ambiguity_threshold,
            )
            row["controlLabel"] = label
            row["distToA"] = dist_a
            row["distToB"] = dist_b
            row["dominantOrder"] = outcome.dominant_order
            row["dominantAmplitude"] = outcome.dominant_amplitude
            nearest_representative_id, dist_to_representative = _nearest_support(
                outcome.fingerprint,
                representative_fingerprints,
            )
            nearest_member_id, dist_to_cycle_support = _nearest_support(
                outcome.fingerprint,
                member_fingerprints,
            )
            row["nearestRepresentativeSpecimenId"] = nearest_representative_id
            row["distToNearestRepresentative"] = dist_to_representative
            row["nearestCycleMemberSpecimenId"] = nearest_member_id
            row["distToCycleSupport"] = dist_to_cycle_support
            row["stepPhenotypeDelta"] = (
                None
                if previous_fingerprint is None
                else l2_distance(outcome.fingerprint, previous_fingerprint)
            )
            previous_fingerprint = outcome.fingerprint
        else:
            row["controlLabel"] = "failed"
            row["stepPhenotypeDelta"] = None
        rows.append(row)

    summary = {
        "source": source_summary,
        "leftSpecimenId": left.specimen_id,
        "rightSpecimenId": right.specimen_id,
        "sourceAnchor": source_anchor,
        "alphaCount": len(alphas),
        "chart": {
            "name": config.name,
            "transform": config.transform,
            "genotypeSize": config.genotype_size,
            "isoSigma": config.iso_sigma,
            "lineSigma": config.line_sigma,
        },
        "continuation": _rows_summary(
            rows,
            left=left,
            right=right,
            representative_ids={left.specimen_id, right.specimen_id},
        ),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "summary.json", summary)
    write_json(output_root / "rows.json", rows)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run chart-aware continuation between two replay-backed QD24 specimens."
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
        help="Output directory for continuation artifacts",
    )
    parser.add_argument(
        "--alphas",
        default="0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0",
        help="Comma-separated continuation alphas including 0 and 1",
    )
    parser.add_argument(
        "--ambiguity-threshold",
        type=float,
        default=0.002,
        help="Phenotype-distance tie threshold for ambiguous control assignment",
    )
    parser.add_argument(
        "--source-anchor",
        choices=("left", "right"),
        default="left",
        help="Replay anchor bundle used for every continuation alpha",
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
                Path(args.source_manifest).expanduser().resolve()
                if args.source_manifest
                else None
            ),
        )
        source_summary["sourceKind"] = "generator_edge"

    run_continuation(
        cli_binary=cli_binary,
        output_root=output_root,
        left=left,
        right=right,
        source_specimen=left if args.source_anchor == "left" else right,
        source_anchor=args.source_anchor,
        alphas=alphas,
        ambiguity_threshold=args.ambiguity_threshold,
        db_path=db_path,
        source_summary=source_summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
