from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json


def _default_output_dir(root: Path) -> Path:
    return root.parent.parent / "topology-generator-bidirectional" / root.name


def _load_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return payload


def _load_rows(summary: dict[str, Any], summary_path: Path) -> list[dict[str, Any]]:
    rows_path_value = summary.get("rowsPath")
    rows_path = (
        Path(rows_path_value).expanduser().resolve()
        if isinstance(rows_path_value, str)
        else summary_path.parent / "rows.json"
    )
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"{rows_path}: expected a JSON array")
    typed_rows = [row for row in rows if isinstance(row, dict)]
    if len(typed_rows) != len(rows):
        raise SystemExit(f"{rows_path}: rows must be JSON objects")
    return typed_rows


def _edge_key(summary: dict[str, Any]) -> tuple[str, int, str]:
    source = summary.get("source", {})
    if not isinstance(source, dict):
        raise SystemExit("Malformed continuation summary source")
    generator_id = source.get("generatorId")
    edge_index = source.get("edgeIndex")
    representation = source.get("representation")
    if not isinstance(generator_id, str) or not isinstance(edge_index, int) or not isinstance(
        representation, str
    ):
        raise SystemExit("Continuation summary is missing generator edge identity")
    return generator_id, edge_index, representation


def _row_map(rows: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
    mapping: dict[float, dict[str, Any]] = {}
    for row in rows:
        global_alpha = row.get("globalAlpha")
        if not isinstance(global_alpha, (int, float)):
            continue
        mapping[round(float(global_alpha), 6)] = row
    return mapping


def _row_divergence(left: dict[str, Any], right: dict[str, Any]) -> float:
    return math.sqrt(
        (float(left.get("distToA", 0.0)) - float(right.get("distToA", 0.0))) ** 2
        + (float(left.get("distToB", 0.0)) - float(right.get("distToB", 0.0))) ** 2
    )


def _pair_record(
    key: tuple[str, int, str],
    left_summary: dict[str, Any],
    right_summary: dict[str, Any],
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    left_summary_path: Path,
    right_summary_path: Path,
) -> dict[str, Any]:
    left_map = _row_map(left_rows)
    right_map = _row_map(right_rows)
    comparable_alphas = sorted(set(left_map) & set(right_map))
    left_continuation = left_summary.get("continuation", {})
    right_continuation = right_summary.get("continuation", {})
    if not isinstance(left_continuation, dict) or not isinstance(right_continuation, dict):
        raise SystemExit("Malformed continuation blocks in anchor summaries")

    divergences = [
        _row_divergence(left_map[alpha], right_map[alpha]) for alpha in comparable_alphas
    ]
    support_gaps = [
        abs(
            float(left_map[alpha].get("distToCycleSupport", 0.0))
            - float(right_map[alpha].get("distToCycleSupport", 0.0))
        )
        for alpha in comparable_alphas
    ]
    label_disagreements = sum(
        left_map[alpha].get("controlLabel") != right_map[alpha].get("controlLabel")
        for alpha in comparable_alphas
    )
    representative_disagreements = sum(
        left_map[alpha].get("nearestRepresentativeSpecimenId")
        != right_map[alpha].get("nearestRepresentativeSpecimenId")
        for alpha in comparable_alphas
    )
    return {
        "generatorId": key[0],
        "edgeIndex": key[1],
        "representation": key[2],
        "leftSummaryPath": str(left_summary_path),
        "rightSummaryPath": str(right_summary_path),
        "comparableCount": len(comparable_alphas),
        "labelDisagreementCount": label_disagreements,
        "representativeDisagreementCount": representative_disagreements,
        "maxAnchorDistanceDelta": max(divergences, default=0.0),
        "meanAnchorDistanceDelta": statistics.fmean(divergences) if divergences else 0.0,
        "maxCycleSupportGap": max(support_gaps, default=0.0),
        "meanCycleSupportGap": statistics.fmean(support_gaps) if support_gaps else 0.0,
        "leftContinuation": left_continuation,
        "rightContinuation": right_continuation,
    }


def analyze_bidirectional_summaries(summary_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    by_key: dict[
        tuple[str, int, str],
        dict[str, tuple[dict[str, Any], list[dict[str, Any]], Path]],
    ] = {}
    for summary_path in summary_paths:
        summary = _load_summary(summary_path)
        source_anchor = summary.get("sourceAnchor")
        if source_anchor not in {"left", "right"}:
            continue
        key = _edge_key(summary)
        by_key.setdefault(key, {})[str(source_anchor)] = (
            summary,
            _load_rows(summary, summary_path),
            summary_path,
        )

    records: list[dict[str, Any]] = []
    for key, anchors in sorted(by_key.items()):
        if set(anchors) != {"left", "right"}:
            continue
        left_summary, left_rows, left_path = anchors["left"]
        right_summary, right_rows, right_path = anchors["right"]
        records.append(
            _pair_record(
                key,
                left_summary,
                right_summary,
                left_rows,
                right_rows,
                left_path,
                right_path,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    aggregate = {
        "version": 1,
        "packetKind": "topology_generator_bidirectional_analysis_v1",
        "pairCount": len(records),
        "pairs": records,
        "aggregate": {
            "pairCount": len(records),
            "meanLabelDisagreementRate": (
                statistics.fmean(
                    item["labelDisagreementCount"] / max(item["comparableCount"], 1)
                    for item in records
                )
                if records
                else 0.0
            ),
            "meanRepresentativeDisagreementRate": (
                statistics.fmean(
                    item["representativeDisagreementCount"] / max(item["comparableCount"], 1)
                    for item in records
                )
                if records
                else 0.0
            ),
            "maxAnchorDistanceDelta": max(
                (float(item["maxAnchorDistanceDelta"]) for item in records),
                default=0.0,
            ),
            "meanAnchorDistanceDelta": (
                statistics.fmean(float(item["meanAnchorDistanceDelta"]) for item in records)
                if records
                else 0.0
            ),
            "topPairs": sorted(
                records,
                key=lambda item: (
                    float(item["meanAnchorDistanceDelta"]),
                    item["labelDisagreementCount"],
                    item["representativeDisagreementCount"],
                ),
            )[:8],
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return aggregate


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare left- and right-anchor continuation packets for generator edges."
    )
    parser.add_argument(
        "--summary",
        action="append",
        required=True,
        help="Path to a continuation summary.json; pass multiple times",
    )
    parser.add_argument("--output", help="Output directory for bidirectional comparison packet")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    summary_paths = [Path(item).expanduser().resolve() for item in args.summary]
    for path in summary_paths:
        if not path.is_file():
            raise SystemExit(f"Missing continuation summary: {path}")
    root = summary_paths[0].parent.parent.parent
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(root).resolve()
    )
    analyze_bidirectional_summaries(summary_paths, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
