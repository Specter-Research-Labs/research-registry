from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    axis_spec,
    coarse_family_kind,
    extract_terminal_raw_axes_from_row,
    preferred_family_kind,
    quantiles,
    robust_center_scale,
    transform_axes,
    zscore,
)


def _analysis_axis_value(axis_id: str, value: Any, row: dict[str, Any]) -> float:
    if value is None and axis_id == "locomotion_onset_step":
        replay_steps = int(row.get("replaySteps", 0))
        record_every = int(row.get("recordEvery", 1))
        return float(replay_steps + max(record_every, 1))
    if not isinstance(value, (int, float)):
        raise SystemExit(f"{row.get('specimenId', 'unknown')}: missing numeric axis {axis_id}")
    return float(value)


def _specimen_row_from_terminal_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_axes = extract_terminal_raw_axes_from_row(row)
    return {
        "specimenId": str(row["specimenId"]),
        "runId": str(row["runId"]),
        "campaignId": row.get("campaignId"),
        "sourceKind": str(row.get("sourceKind", "unknown")),
        "familyKind": coarse_family_kind(row),
        "regimeFamily": None,
        "geometryFamily": None,
        "canonicalFamily": None,
        "rawAxes": raw_axes,
        "transformedAxes": transform_axes(raw_axes),
    }


def _specimen_row_from_replay_record(record: dict[str, Any]) -> dict[str, Any]:
    terminal_axes = record.get("terminalAxes")
    developmental_axes = record.get("developmentalAxes")
    if not isinstance(terminal_axes, dict) or not isinstance(developmental_axes, dict):
        raise SystemExit("Replay packet specimen is missing terminalAxes or developmentalAxes")
    missing_terminal_axes = [
        axis_id for axis_id in TERMINAL_AXIS_IDS if axis_id not in terminal_axes
    ]
    if missing_terminal_axes:
        raise SystemExit(
            "Replay packet specimen is missing terminal axes required for atlas topology: "
            + ", ".join(missing_terminal_axes)
        )
    raw_axes = {
        axis_id: float(terminal_axes[axis_id])
        for axis_id in TERMINAL_AXIS_IDS
    }
    for axis_id in DEVELOPMENTAL_AXIS_IDS:
        raw_axes[axis_id] = _analysis_axis_value(axis_id, developmental_axes.get(axis_id), record)
    return {
        "specimenId": str(record["specimenId"]),
        "runId": str(record["runId"]),
        "campaignId": record.get("campaignId"),
        "sourceKind": str(record.get("sourceKind", "unknown")),
        "familyKind": preferred_family_kind(record),
        "regimeFamily": record.get("regimeFamily"),
        "geometryFamily": record.get("geometryFamily"),
        "canonicalFamily": record.get("canonicalFamily"),
        "rawAxes": raw_axes,
        "transformedAxes": transform_axes(raw_axes),
    }


def _axis_statistics(
    rows: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for axis_id in axis_ids:
        transformed = [float(row["transformedAxes"][axis_id]) for row in rows]
        raw = [float(row["rawAxes"][axis_id]) for row in rows]
        center, scale = robust_center_scale(transformed)
        stats[axis_id] = {
            "rawQuantiles": quantiles(raw),
            "transformedQuantiles": quantiles(transformed),
            "center": center,
            "scale": scale,
        }
    return stats


def _grouped_axis_statistics(
    rows: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
    group_key: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        raw_group = row.get(group_key)
        if raw_group is None:
            continue
        grouped[str(raw_group)].append(row)
    stats: dict[str, dict[str, dict[str, Any]]] = {}
    for group, group_rows in sorted(grouped.items()):
        stats[group] = _axis_statistics(group_rows, axis_ids=axis_ids)
    return stats


def _annotated_rows(
    rows: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
    global_stats: dict[str, dict[str, Any]],
    group_key: str,
    group_stats: dict[str, dict[str, dict[str, Any]]],
    dominant_axis_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in rows:
        group = row.get(group_key)
        group_name = str(group) if group is not None else None
        global_z = {
            axis_id: zscore(
                float(row["transformedAxes"][axis_id]),
                center=float(global_stats[axis_id]["center"]),
                scale=float(global_stats[axis_id]["scale"]),
            )
            for axis_id in axis_ids
        }
        if group_name is not None and group_name in group_stats:
            local_z = {
                axis_id: zscore(
                    float(row["transformedAxes"][axis_id]),
                    center=float(group_stats[group_name][axis_id]["center"]),
                    scale=float(group_stats[group_name][axis_id]["scale"]),
                )
                for axis_id in axis_ids
            }
        else:
            local_z = global_z
        dominant_axis = max(
            dominant_axis_ids,
            key=lambda axis_id: (float(local_z[axis_id]), axis_id),
        )
        annotated.append(
            {
                **row,
                "globalZ": global_z,
                "groupZ": local_z,
                "analysisGroup": group_name,
                "dominantProgram": dominant_axis,
            }
        )
    return annotated


def _focal_entry(row: dict[str, Any], axis_id: str, *, score_key: str) -> dict[str, Any]:
    return {
        "specimenId": str(row["specimenId"]),
        "runId": str(row["runId"]),
        "campaignId": row.get("campaignId"),
        "sourceKind": str(row["sourceKind"]),
        "familyKind": str(row["familyKind"]),
        "regimeFamily": row.get("regimeFamily"),
        "geometryFamily": row.get("geometryFamily"),
        "canonicalFamily": row.get("canonicalFamily"),
        "rawValue": float(row["rawAxes"][axis_id]),
        "transformedValue": float(row["transformedAxes"][axis_id]),
        "globalZ": float(row["globalZ"][axis_id]),
        "score": float(row[score_key][axis_id]),
    }


def _top_rows(
    rows: list[dict[str, Any]],
    *,
    axis_id: str,
    score_key: str,
    limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (-float(row[score_key][axis_id]), str(row["specimenId"])),
    )
    return [_focal_entry(row, axis_id, score_key=score_key) for row in ranked[:limit]]


def _group_summaries(
    annotated_rows: list[dict[str, Any]],
    *,
    axis_ids: tuple[str, ...],
    group_key: str,
    group_stats: dict[str, dict[str, dict[str, Any]]],
    dominant_axis_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for group_name in sorted(group_stats):
        group_rows = [row for row in annotated_rows if str(row.get(group_key)) == group_name]
        dominant_counts = Counter(str(row["dominantProgram"]) for row in group_rows)
        dominant_programs = [
            {
                "axisId": axis_id,
                "count": count,
                "fraction": count / len(group_rows),
            }
            for axis_id, count in dominant_counts.most_common()
            if axis_id in dominant_axis_ids
        ]
        axes = [
            {
                "axisId": axis_id,
                "rawQuantiles": group_stats[group_name][axis_id]["rawQuantiles"],
                "transformedQuantiles": group_stats[group_name][axis_id]["transformedQuantiles"],
            }
            for axis_id in axis_ids
        ]
        summaries.append(
            {
                group_key: group_name,
                "specimenCount": len(group_rows),
                "dominantPrograms": dominant_programs,
                "axes": axes,
            }
        )
    return summaries


def _pairwise_group_contrasts(
    *,
    group_stats: dict[str, dict[str, dict[str, Any]]],
    axis_ids: tuple[str, ...],
    group_key: str,
) -> list[dict[str, Any]]:
    groups = sorted(group_stats)
    rows: list[dict[str, Any]] = []
    for left_index, group_a in enumerate(groups):
        for group_b in groups[left_index + 1 :]:
            for axis_id in axis_ids:
                transformed_a = float(
                    group_stats[group_a][axis_id]["transformedQuantiles"]["median"]
                )
                transformed_b = float(
                    group_stats[group_b][axis_id]["transformedQuantiles"]["median"]
                )
                rows.append(
                    {
                        "groupKey": group_key,
                        "groupA": group_a,
                        "groupB": group_b,
                        "axisId": axis_id,
                        "medianDeltaTransformed": transformed_b - transformed_a,
                        "higherMedianGroup": group_b if transformed_b >= transformed_a else group_a,
                        "absoluteMedianDeltaTransformed": abs(transformed_b - transformed_a),
                    }
                )
    return sorted(
        rows,
        key=lambda row: (
            -float(row["absoluteMedianDeltaTransformed"]),
            str(row["axisId"]),
            str(row["groupA"]),
            str(row["groupB"]),
        ),
    )


def _axis_rows(
    *,
    axis_ids: tuple[str, ...],
    global_stats: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for axis_id in axis_ids:
        spec = axis_spec(axis_id)
        rows.append(
            {
                **spec,
                "globalRawQuantiles": global_stats[axis_id]["rawQuantiles"],
                "globalTransformedQuantiles": global_stats[axis_id]["transformedQuantiles"],
            }
        )
    return rows


def _dominant_programs(
    annotated_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts = Counter(str(row["dominantProgram"]) for row in annotated_rows)
    total = len(annotated_rows)
    return [
        {"axisId": axis_id, "count": count, "fraction": count / total}
        for axis_id, count in counts.most_common()
    ]


def _baseline_comparison(
    *,
    baseline_packet_path: Path | None,
    global_stats: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if baseline_packet_path is None:
        return None
    baseline = read_json(baseline_packet_path)
    axes = baseline.get("axes")
    if not isinstance(axes, list):
        raise SystemExit(f"{baseline_packet_path}: baseline atlas is missing axes")
    baseline_by_axis: dict[str, float] = {}
    for row in axes:
        if not isinstance(row, dict):
            continue
        axis_id = row.get("id")
        global_raw = row.get("globalRawQuantiles")
        if isinstance(axis_id, str) and isinstance(global_raw, dict):
            median_value = global_raw.get("median")
            if isinstance(median_value, (int, float)):
                baseline_by_axis[axis_id] = float(median_value)
    shared_axes = []
    for axis_id, baseline_median in sorted(baseline_by_axis.items()):
        if axis_id not in global_stats:
            continue
        current_median = float(global_stats[axis_id]["rawQuantiles"]["median"])
        shared_axes.append(
            {
                "axisId": axis_id,
                "currentMedian": current_median,
                "baselineMedian": baseline_median,
                "medianDelta": current_median - baseline_median,
            }
        )
    return {
        "sourceArtifact": str(baseline_packet_path),
        "sharedAxes": shared_axes,
    }


def build_transformation_atlas_packet(
    *,
    rows_path: Path | None = None,
    replay_packet_path: Path | None = None,
    baseline_atlas_path: Path | None = None,
    top_exemplars_per_axis: int,
) -> dict[str, Any]:
    if rows_path is None and replay_packet_path is None:
        raise SystemExit("transformation atlas requires either --rows or --replay-packet")
    if rows_path is not None and replay_packet_path is not None:
        raise SystemExit("transformation atlas accepts either --rows or --replay-packet, not both")

    if rows_path is not None:
        raw_rows = read_jsonl(rows_path)
        specimen_rows = [_specimen_row_from_terminal_row(row) for row in raw_rows]
        axis_ids = TERMINAL_AXIS_IDS
        dominant_axis_ids = TERMINAL_AXIS_IDS
        group_key = "familyKind"
        packet_kind = "developmental_transformation_atlas_v1"
        version = 1
        source_artifact = str(rows_path)
        baseline_comparison = None
        limitations = [
            (
                "The current atlas still lacks full intermediate shape trajectories, "
                "but it now includes direct terminal fingerprint morphology metrics."
            ),
            (
                "Current family kinds are coarse prefixes of initialConditionFamily, "
                "so fine init-seed diversity is collapsed."
            ),
        ]
    else:
        if replay_packet_path is None:
            raise SystemExit("atlas v2 requires a replay packet path")
        replay_packet_path = replay_packet_path.resolve()
        replay_packet = read_json(replay_packet_path)
        if replay_packet.get("packetKind") != "transformation_replay_packet_v1":
            raise SystemExit("atlas v2 expects transformation_replay_packet_v1")
        replay_specimens = replay_packet.get("specimens")
        if not isinstance(replay_specimens, list) or not replay_specimens:
            raise SystemExit(f"{replay_packet_path}: replay packet has no specimens")
        specimen_rows = [_specimen_row_from_replay_record(record) for record in replay_specimens]
        axis_ids = TERMINAL_AXIS_IDS + DEVELOPMENTAL_AXIS_IDS
        dominant_axis_ids = DEVELOPMENTAL_AXIS_IDS
        group_key = (
            "canonicalFamily"
            if any(row.get("canonicalFamily") is not None for row in specimen_rows)
            else "familyKind"
        )
        packet_kind = "developmental_transformation_atlas_v2"
        version = 2
        source_artifact = str(replay_packet_path)
        baseline_comparison = _baseline_comparison(
            baseline_packet_path=baseline_atlas_path,
            global_stats=_axis_statistics(specimen_rows, axis_ids=axis_ids),
        )
        limitations = [
            (
                "Locomotion onset is imputed as replaySteps + recordEvery when no sampled "
                "center-velocity crossing occurs, so late-onset medians reflect a censoring policy."
            ),
            (
                "Transformation-signature topology here is descriptor-space topology, not the "
                "full pixel fingerprint topology used in the separate phenotype-space pipeline."
            ),
        ]

    global_stats = _axis_statistics(specimen_rows, axis_ids=axis_ids)
    group_stats = _grouped_axis_statistics(specimen_rows, axis_ids=axis_ids, group_key=group_key)
    annotated_rows = _annotated_rows(
        specimen_rows,
        axis_ids=axis_ids,
        global_stats=global_stats,
        group_key=group_key,
        group_stats=group_stats,
        dominant_axis_ids=dominant_axis_ids,
    )
    axis_rows = _axis_rows(axis_ids=axis_ids, global_stats=global_stats)
    focal_overall = [
        {
            "axisId": axis_id,
            "topPositiveGlobal": _top_rows(
                annotated_rows,
                axis_id=axis_id,
                score_key="globalZ",
                limit=top_exemplars_per_axis,
            ),
        }
        for axis_id in axis_ids
    ]
    focal_grouped = [
        {
            group_key: group_name,
            "axisId": axis_id,
            "topPositiveGroup": _top_rows(
                [row for row in annotated_rows if str(row.get(group_key)) == group_name],
                axis_id=axis_id,
                score_key="groupZ",
                limit=top_exemplars_per_axis,
            ),
        }
        for group_name in sorted(group_stats)
        for axis_id in axis_ids
    ]
    ensemble: dict[str, Any] = {
        "dominantPrograms": _dominant_programs(annotated_rows),
        group_key: _group_summaries(
            annotated_rows,
            axis_ids=axis_ids,
            group_key=group_key,
            group_stats=group_stats,
            dominant_axis_ids=dominant_axis_ids,
        ),
        "pairwiseContrasts": _pairwise_group_contrasts(
            group_stats=group_stats,
            axis_ids=axis_ids,
            group_key=group_key,
        ),
    }
    if version == 2:
        for extra_group_key in ("regimeFamily", "geometryFamily", "canonicalFamily", "familyKind"):
            extra_stats = _grouped_axis_statistics(
                specimen_rows,
                axis_ids=axis_ids,
                group_key=extra_group_key,
            )
            if not extra_stats:
                continue
            ensemble[extra_group_key] = _group_summaries(
                annotated_rows,
                axis_ids=axis_ids,
                group_key=extra_group_key,
                group_stats=extra_stats,
                dominant_axis_ids=dominant_axis_ids,
            )
    packet: dict[str, Any] = {
        "version": version,
        "packetKind": packet_kind,
        "sourceArtifact": source_artifact,
        "summary": {
            "specimenCount": len(annotated_rows),
            "axisCount": len(axis_ids),
            "terminalAxisCount": len(TERMINAL_AXIS_IDS),
            "developmentalAxisCount": len(axis_ids) - len(TERMINAL_AXIS_IDS),
            "topExemplarsPerAxis": top_exemplars_per_axis,
            "analysisGroupKey": group_key,
            "familyKinds": sorted({str(row["familyKind"]) for row in annotated_rows}),
        },
        "limitations": limitations,
        "axes": axis_rows,
        "ensemble": ensemble,
        "focal": {
            "overallByAxis": focal_overall,
            "byAnalysisGroupAndAxis": focal_grouped,
        },
    }
    if version == 1:
        packet["ensemble"]["families"] = packet["ensemble"].pop("familyKind")
        packet["ensemble"]["pairwiseContrasts"] = [
            {
                **row,
                "familyA": row["groupA"],
                "familyB": row["groupB"],
                "higherMedianFamily": row["higherMedianGroup"],
            }
            for row in packet["ensemble"]["pairwiseContrasts"]
        ]
        packet["focal"]["byFamilyAndAxis"] = [
            {
                "familyKind": row["familyKind"],
                "axisId": row["axisId"],
                "topPositiveFamily": row["topPositiveGroup"],
            }
            for row in packet["focal"].pop("byAnalysisGroupAndAxis")
        ]
    if version == 2:
        packet["analysisPolicies"] = {
            "locomotion_onset_step": {
                "nonePolicy": "replay_steps_plus_record_every",
            }
        }
        packet["baselineComparison"] = baseline_comparison
        packet["specimens"] = [
            {
                "specimenId": row["specimenId"],
                "runId": row["runId"],
                "campaignId": row["campaignId"],
                "sourceKind": row["sourceKind"],
                "familyKind": row["familyKind"],
                "regimeFamily": row["regimeFamily"],
                "geometryFamily": row["geometryFamily"],
                "canonicalFamily": row["canonicalFamily"],
                "rawAxes": row["rawAxes"],
                "transformedAxes": row["transformedAxes"],
                "dominantProgram": row["dominantProgram"],
            }
            for row in annotated_rows
        ]
    return packet


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build developmental transformation atlas packets from terminal "
            "or replay-time artifacts."
        )
    )
    parser.add_argument("--rows", help="Path to topology JSONL rows for v1 atlas")
    parser.add_argument(
        "--replay-packet",
        help="Path to transformation_replay_packet_v1 JSON for replay-time v2 atlas",
    )
    parser.add_argument(
        "--baseline-atlas",
        help="Optional baseline developmental_transformation_atlas_v1 JSON for v2 comparisons",
    )
    parser.add_argument(
        "--top-exemplars-per-axis",
        type=int,
        default=5,
        help="How many focal exemplars to keep for each axis",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    rows_path = Path(args.rows).expanduser().resolve() if args.rows else None
    replay_packet_path = (
        Path(args.replay_packet).expanduser().resolve() if args.replay_packet else None
    )
    baseline_atlas_path = (
        Path(args.baseline_atlas).expanduser().resolve() if args.baseline_atlas else None
    )
    packet = build_transformation_atlas_packet(
        rows_path=rows_path,
        replay_packet_path=replay_packet_path,
        baseline_atlas_path=baseline_atlas_path,
        top_exemplars_per_axis=args.top_exemplars_per_axis,
    )
    if replay_packet_path is not None:
        default_root = replay_packet_path.parent
    else:
        if rows_path is None:
            raise SystemExit("atlas output requires either --rows or --replay-packet")
        default_root = rows_path.parent
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else default_root / "transformation-atlas-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transformation atlas:"
        f" specimens={packet['summary']['specimenCount']}"
        f" axes={packet['summary']['axisCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
