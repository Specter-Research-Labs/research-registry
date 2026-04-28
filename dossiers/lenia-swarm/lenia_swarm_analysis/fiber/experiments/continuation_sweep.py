#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.fiber._common import (
    CandidateSpecimen,
    coarse_alpha_grid,
    extract_result_metrics,
    interpolate_payload,
    l2_distance,
    read_jsonl,
    resolve_library_source_export_dir,
    run_variant,
    sanitize,
    write_json,
)
from lenia_swarm_analysis.generators.reentry import (
    classify_control_label,
    read_json,
    summarize_continuation_rows,
)


@dataclass(frozen=True)
class GeneratorEdgeContext:
    packet_path: Path
    representation: str
    source_manifest: str | None
    generator_id: str
    edge_index: int
    representative_ids: list[str]
    member_ids: list[str]
    left: CandidateSpecimen
    right: CandidateSpecimen


@dataclass(frozen=True)
class AnchorTraversal:
    source_anchor: str
    source_specimen: CandidateSpecimen
    start_specimen: CandidateSpecimen
    end_specimen: CandidateSpecimen

    def global_alpha(self, anchor_alpha: float) -> float:
        return anchor_alpha if self.source_anchor == "left" else 1.0 - anchor_alpha

    def payload(
        self,
        left: CandidateSpecimen,
        right: CandidateSpecimen,
        anchor_alpha: float,
    ) -> dict[str, Any]:
        if self.source_anchor == "left":
            return interpolate_payload(left, right, anchor_alpha)
        return interpolate_payload(right, left, anchor_alpha)


def parse_specimen_id(specimen_id: str) -> tuple[str, str, str]:
    if ":" not in specimen_id:
        raise SystemExit(f"Malformed specimen id: {specimen_id}")
    source_kind, rest = specimen_id.split(":", maxsplit=1)
    parts = rest.split("|")
    if len(parts) != 3:
        raise SystemExit(f"Malformed specimen id: {specimen_id}")
    return source_kind, parts[0], parts[1]


def replay_campaign_dir(replay_root: Path, specimen_id: str) -> Path:
    _, run_id, campaign_id = parse_specimen_id(specimen_id)
    return replay_root / run_id / "campaigns" / campaign_id


def load_generator_specimen(specimen_id: str, replay_root: Path) -> CandidateSpecimen:
    campaign_dir = replay_campaign_dir(replay_root, specimen_id)
    library_rows = read_jsonl(campaign_dir / "library/index.jsonl")
    if len(library_rows) != 1:
        raise SystemExit(f"{campaign_dir}: expected exactly one library row")
    export_dir = resolve_library_source_export_dir(
        library_rows[0],
        campaign_dir=campaign_dir,
    )
    payload = read_json(export_dir / "payload.json")
    elite = payload.get("elite")
    cell_seed = elite.get("cell") if isinstance(elite, dict) else None
    if not isinstance(cell_seed, int):
        raise SystemExit(f"{export_dir}: payload is missing elite.cell")
    result_rows = read_jsonl(campaign_dir / "results.jsonl")
    if len(result_rows) != 1:
        raise SystemExit(f"{campaign_dir}: expected exactly one result row")
    fingerprint, dominant_order, dominant_amplitude = extract_result_metrics(result_rows[0])
    _, run_id, campaign_id = parse_specimen_id(specimen_id)
    return CandidateSpecimen(
        run_id=run_id,
        campaign_id=campaign_id,
        specimen_id=specimen_id,
        seed=cell_seed,
        dominant_order=dominant_order,
        dominant_amplitude=dominant_amplitude,
        source_export_dir=export_dir,
        source_meta=read_json(export_dir / "meta.json"),
        payload=payload,
        baseline_fingerprint=fingerprint,
    )


def cached_specimen(
    specimen_id: str,
    replay_root: Path,
    cache: dict[str, CandidateSpecimen],
) -> CandidateSpecimen:
    specimen = cache.get(specimen_id)
    if specimen is None:
        specimen = load_generator_specimen(specimen_id, replay_root)
        cache[specimen_id] = specimen
    return specimen


def outcome_row(
    *,
    anchor_alpha: float,
    global_alpha: float,
    source_anchor: str,
    fingerprint: np.ndarray,
    dominant_order: int | None,
    dominant_amplitude: float | None,
    variant: str,
    run_id: str,
    run_dir: str,
    context: GeneratorEdgeContext,
    representative_fingerprints: dict[str, np.ndarray],
    member_fingerprints: dict[str, np.ndarray],
    previous_fingerprint: np.ndarray | None,
) -> dict[str, Any]:
    dist_to_a = l2_distance(fingerprint, context.left.baseline_fingerprint)
    dist_to_b = l2_distance(fingerprint, context.right.baseline_fingerprint)
    representative_id, representative_distance = min(
        (
            (specimen_id, l2_distance(fingerprint, specimen_fingerprint))
            for specimen_id, specimen_fingerprint in representative_fingerprints.items()
        ),
        key=lambda item: item[1],
    )
    member_id, member_distance = min(
        (
            (specimen_id, l2_distance(fingerprint, specimen_fingerprint))
            for specimen_id, specimen_fingerprint in member_fingerprints.items()
        ),
        key=lambda item: item[1],
    )
    return {
        "anchorAlpha": anchor_alpha,
        "globalAlpha": global_alpha,
        "sourceAnchor": source_anchor,
        "variant": variant,
        "returncode": 0,
        "runId": run_id,
        "runDir": run_dir,
        "controlLabel": classify_control_label(dist_to_a=dist_to_a, dist_to_b=dist_to_b),
        "distToA": dist_to_a,
        "distToB": dist_to_b,
        "dominantOrder": dominant_order,
        "dominantAmplitude": dominant_amplitude,
        "nearestRepresentativeSpecimenId": representative_id,
        "distToNearestRepresentative": representative_distance,
        "nearestCycleMemberSpecimenId": member_id,
        "distToCycleSupport": member_distance,
        "stepPhenotypeDelta": (
            l2_distance(fingerprint, previous_fingerprint)
            if previous_fingerprint is not None
            else None
        ),
    }


def failed_row(
    *,
    anchor_alpha: float,
    global_alpha: float,
    source_anchor: str,
    variant: str,
    run_id: str,
    run_dir: str,
    returncode: int,
) -> dict[str, Any]:
    return {
        "anchorAlpha": anchor_alpha,
        "globalAlpha": global_alpha,
        "sourceAnchor": source_anchor,
        "variant": variant,
        "returncode": returncode,
        "runId": run_id,
        "runDir": run_dir,
    }


def generator_packet_contexts(
    packet: dict[str, Any],
    replay_root: Path,
    *,
    top_generators: int,
    edge_keys: set[tuple[str, int]] | None = None,
) -> list[GeneratorEdgeContext]:
    generators = packet.get("generators")
    if not isinstance(generators, list) or not generators:
        raise SystemExit("generator packet is missing generators")
    specimen_cache: dict[str, CandidateSpecimen] = {}
    contexts: list[GeneratorEdgeContext] = []
    for generator in generators[:top_generators]:
        if not isinstance(generator, dict):
            raise SystemExit("generator rows must be objects")
        generator_id = generator.get("generatorId")
        representation = packet.get("representation")
        if not isinstance(generator_id, str) or not isinstance(representation, str):
            raise SystemExit("generator packet is missing generatorId or representation")
        representative_ids = [str(item) for item in generator.get("representativeSpecimenIds", [])]
        member_ids = [str(item) for item in generator.get("memberSpecimenIds", [])]
        cycle_edges = generator.get("cycleEdges", [])
        if not isinstance(cycle_edges, list):
            raise SystemExit(f"{generator_id}: cycleEdges must be a list")
        for edge_index, edge in enumerate(cycle_edges):
            if not isinstance(edge, dict):
                raise SystemExit(f"{generator_id}: edge rows must be objects")
            if edge_keys is not None and (generator_id, edge_index) not in edge_keys:
                continue
            left_id = edge.get("fromSpecimenId")
            right_id = edge.get("toSpecimenId")
            if not isinstance(left_id, str) or not isinstance(right_id, str):
                raise SystemExit(f"{generator_id}: edge is missing fromSpecimenId/toSpecimenId")
            left = cached_specimen(left_id, replay_root, specimen_cache)
            right = cached_specimen(right_id, replay_root, specimen_cache)
            contexts.append(
                GeneratorEdgeContext(
                    packet_path=Path(packet["packetPath"]) if "packetPath" in packet else Path(),
                    representation=representation,
                    source_manifest=packet.get("sourceManifest"),
                    generator_id=generator_id,
                    edge_index=edge_index,
                    representative_ids=representative_ids,
                    member_ids=member_ids,
                    left=left,
                    right=right,
                )
            )
    return contexts


def packet_path_from_summary_dir(packet_dir: Path) -> Path:
    return packet_dir / "generator-packet.json"


def packet_from_path(packet_path: Path) -> dict[str, Any]:
    packet = read_json(packet_path)
    packet["packetPath"] = str(packet_path)
    return packet


def anchor_traversal(context: GeneratorEdgeContext, source_anchor: str) -> AnchorTraversal:
    if source_anchor == "left":
        return AnchorTraversal(
            source_anchor="left",
            source_specimen=context.left,
            start_specimen=context.left,
            end_specimen=context.right,
        )
    if source_anchor == "right":
        return AnchorTraversal(
            source_anchor="right",
            source_specimen=context.right,
            start_specimen=context.right,
            end_specimen=context.left,
        )
    raise SystemExit(f"Unsupported source anchor: {source_anchor}")


def run_edge(
    *,
    cli_binary: Path,
    output_root: Path,
    replay_root: Path,
    context: GeneratorEdgeContext,
    alphas: list[float],
    source_anchor: str,
    db_path: Path | None,
    specimen_cache: dict[str, CandidateSpecimen],
) -> dict[str, Any]:
    traversal = anchor_traversal(context, source_anchor)
    edge_slug = sanitize(
        f"{context.representation}-{context.generator_id}-edge{context.edge_index:02d}-"
        f"{traversal.source_anchor}-"
        f"{context.left.campaign_id}-{context.right.campaign_id}"
    )
    representative_fingerprints = {
        specimen_id: cached_specimen(specimen_id, replay_root, specimen_cache).baseline_fingerprint
        for specimen_id in context.representative_ids
    }
    member_fingerprints = {
        specimen_id: cached_specimen(specimen_id, replay_root, specimen_cache).baseline_fingerprint
        for specimen_id in context.member_ids
    }
    rows: list[dict[str, Any]] = []
    previous_fingerprint: np.ndarray | None = None
    for anchor_alpha in alphas:
        global_alpha = traversal.global_alpha(anchor_alpha)
        variant_slug = f"{traversal.source_anchor}-a{int(round(anchor_alpha * 10000)):04d}"
        if anchor_alpha == 0.0:
            row = outcome_row(
                anchor_alpha=anchor_alpha,
                global_alpha=global_alpha,
                source_anchor=traversal.source_anchor,
                fingerprint=traversal.start_specimen.baseline_fingerprint,
                dominant_order=traversal.start_specimen.dominant_order,
                dominant_amplitude=traversal.start_specimen.dominant_amplitude,
                variant=variant_slug,
                run_id=f"edge-{edge_slug}",
                run_dir=f"endpoint:{traversal.source_anchor}",
                context=context,
                representative_fingerprints=representative_fingerprints,
                member_fingerprints=member_fingerprints,
                previous_fingerprint=previous_fingerprint,
            )
            rows.append(row)
            previous_fingerprint = traversal.start_specimen.baseline_fingerprint
            continue
        if anchor_alpha == 1.0:
            row = outcome_row(
                anchor_alpha=anchor_alpha,
                global_alpha=global_alpha,
                source_anchor=traversal.source_anchor,
                fingerprint=traversal.end_specimen.baseline_fingerprint,
                dominant_order=traversal.end_specimen.dominant_order,
                dominant_amplitude=traversal.end_specimen.dominant_amplitude,
                variant=variant_slug,
                run_id=f"edge-{edge_slug}",
                run_dir=(
                    f"endpoint:{'right' if traversal.source_anchor == 'left' else 'left'}"
                ),
                context=context,
                representative_fingerprints=representative_fingerprints,
                member_fingerprints=member_fingerprints,
                previous_fingerprint=previous_fingerprint,
            )
            rows.append(row)
            previous_fingerprint = traversal.end_specimen.baseline_fingerprint
            continue
        outcome = run_variant(
            cli_binary=cli_binary,
            output_root=output_root,
            pair_slug_value=edge_slug,
            variant_slug=variant_slug,
            source_specimen=traversal.source_specimen,
            payload=traversal.payload(context.left, context.right, anchor_alpha),
            reason=(
                f"generator-continuation:{context.generator_id}:{context.edge_index}:"
                f"{traversal.source_anchor}:{anchor_alpha:.4f}"
            ),
            run_id=(
                f"generator-cont-{context.generator_id}-e{context.edge_index:02d}-"
                f"{variant_slug}"
            ),
            db_path=db_path,
        )
        if outcome.returncode != 0 or outcome.fingerprint is None:
            rows.append(
                failed_row(
                    anchor_alpha=anchor_alpha,
                    global_alpha=global_alpha,
                    source_anchor=traversal.source_anchor,
                    variant=variant_slug,
                    run_id=outcome.run_id,
                    run_dir=str(outcome.run_dir),
                    returncode=outcome.returncode,
                )
            )
            previous_fingerprint = None
            continue
        row = outcome_row(
            anchor_alpha=anchor_alpha,
            global_alpha=global_alpha,
            source_anchor=traversal.source_anchor,
            fingerprint=outcome.fingerprint,
            dominant_order=outcome.dominant_order,
            dominant_amplitude=outcome.dominant_amplitude,
            variant=variant_slug,
            run_id=outcome.run_id,
            run_dir=str(outcome.run_dir),
            context=context,
            representative_fingerprints=representative_fingerprints,
            member_fingerprints=member_fingerprints,
            previous_fingerprint=previous_fingerprint,
        )
        rows.append(row)
        previous_fingerprint = outcome.fingerprint
    summary = {
        "source": {
            "packetPath": str(context.packet_path),
            "generatorId": context.generator_id,
            "edgeIndex": context.edge_index,
            "representation": context.representation,
            "sourceManifest": context.source_manifest,
            "representativeSpecimenIds": context.representative_ids,
            "memberSpecimenIds": context.member_ids,
            "sourceKind": "generator_edge",
        },
        "leftSpecimenId": context.left.specimen_id,
        "rightSpecimenId": context.right.specimen_id,
        "sourceAnchor": traversal.source_anchor,
        "alphaCount": len(alphas),
        "globalAlphaRange": [
            min(float(row["globalAlpha"]) for row in rows),
            max(float(row["globalAlpha"]) for row in rows),
        ],
        "chart": {
            "name": "qd24_identity_mutscale_v1",
            "transform": "identity",
            "genotypeSize": int(len(context.left.payload["elite"]["genotype"])),
            "isoSigma": 0.005,
            "lineSigma": 0.05,
        },
        "continuation": summarize_continuation_rows(
            rows,
            target_control_label="B" if traversal.source_anchor == "left" else "A",
        ),
    }
    return {
        "rows": rows,
        "summary": summary,
    }


def aggregate_study(edge_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    anchor_counts: dict[str, int] = {}
    for item in edge_summaries:
        source_anchor = str(item.get("sourceAnchor", "unknown"))
        anchor_counts[source_anchor] = anchor_counts.get(source_anchor, 0) + 1
    return {
        "packetKind": "topology_generator_continuation_sweep_v1",
        "edgeCount": len(edge_summaries),
        "edgeSuccessCount": sum(
            item["continuation"]["failureCount"] == 0 for item in edge_summaries
        ),
        "reentryEdgeCount": sum(
            bool(item["continuation"]["hasReentry"]) for item in edge_summaries
        ),
        "ambiguousEdgeCount": sum(
            item["continuation"]["ambiguousCount"] > 0 for item in edge_summaries
        ),
        "generatorIds": sorted({str(item["source"]["generatorId"]) for item in edge_summaries}),
        "anchorCounts": anchor_counts,
        "topEdges": sorted(
            edge_summaries,
            key=lambda item: (
                not bool(item["continuation"]["hasReentry"]),
                item["continuation"]["ambiguousCount"],
                item["continuation"]["maxEscapeRatio"],
                -item["continuation"]["representativeVisitCount"],
            ),
        )[:10],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a generator-edge continuation sweep from a topology generator packet."
    )
    parser.add_argument("--generator-packet", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cli-binary", required=True)
    parser.add_argument("--replay-root", required=True)
    parser.add_argument("--top-generators", type=int, default=3)
    parser.add_argument("--alpha-grid", default="0,0.25,0.5,0.75,1.0")
    parser.add_argument(
        "--source-anchor",
        choices=("left", "right", "both"),
        default="left",
        help="Which anchor-local chart to traverse",
    )
    parser.add_argument(
        "--edge-key",
        action="append",
        help="Restrict to a specific edge in generatorId:edgeIndex form; pass multiple times",
    )
    parser.add_argument("--db")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet_path = Path(args.generator_packet).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    replay_root = Path(args.replay_root).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else None
    alphas = coarse_alpha_grid(args.alpha_grid)
    edge_keys: set[tuple[str, int]] | None = None
    if args.edge_key:
        edge_keys = set()
        for raw in args.edge_key:
            if ":" not in raw:
                raise SystemExit(f"Malformed edge key: {raw}")
            generator_id, edge_index_raw = raw.rsplit(":", maxsplit=1)
            edge_keys.add((generator_id, int(edge_index_raw)))
    packet = packet_from_path(packet_path)
    contexts = generator_packet_contexts(
        packet,
        replay_root,
        top_generators=args.top_generators,
        edge_keys=edge_keys,
    )
    specimen_cache: dict[str, CandidateSpecimen] = {}
    edge_summaries: list[dict[str, Any]] = []
    anchors = ("left", "right") if args.source_anchor == "both" else (args.source_anchor,)
    for context in contexts:
        base_edge_dir = output_root / context.generator_id / f"edge{context.edge_index:02d}"
        for source_anchor in anchors:
            edge_dir = base_edge_dir / f"{source_anchor}-anchor"
            result = run_edge(
                cli_binary=cli_binary,
                output_root=edge_dir,
                replay_root=replay_root,
                context=context,
                alphas=alphas,
                source_anchor=source_anchor,
                db_path=db_path,
                specimen_cache=specimen_cache,
            )
            rows_path = edge_dir / "rows.json"
            summary = dict(result["summary"])
            summary["rowsPath"] = str(rows_path)
            write_json(rows_path, result["rows"])
            write_json(edge_dir / "summary.json", summary)
            edge_summaries.append(summary)
    write_json(output_root / "study-summary.json", aggregate_study(edge_summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
