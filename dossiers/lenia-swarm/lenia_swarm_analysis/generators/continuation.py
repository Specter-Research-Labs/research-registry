from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_json


def _default_output_dir(root: Path) -> Path:
    return root.parent / "topology-generator-continuation" / root.name


def _load_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return payload


def _run_record(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source", {})
    continuation = payload.get("continuation", {})
    if not isinstance(source, dict) or not isinstance(continuation, dict):
        raise SystemExit(f"{path}: malformed continuation summary")
    success_count = int(continuation.get("successCount", 0))
    ambiguous_count = int(continuation.get("ambiguousCount", 0))
    branch_switch_count = int(continuation.get("branchSwitchCount", 0))
    record = {
        "summaryPath": str(path),
        "representation": source.get("representation"),
        "generatorId": source.get("generatorId"),
        "edgeIndex": source.get("edgeIndex"),
        "sourceAnchor": payload.get("sourceAnchor"),
        "alphaCount": payload.get("alphaCount"),
        "successCount": success_count,
        "failureCount": int(continuation.get("failureCount", 0)),
        "ambiguousCount": ambiguous_count,
        "branchSwitchCount": branch_switch_count,
        "hasReentry": bool(continuation.get("hasReentry", False)),
        "visitsNonEndpointRepresentative": bool(
            continuation.get("visitsNonEndpointRepresentative", False)
        ),
        "representativeVisitCount": int(continuation.get("representativeVisitCount", 0)),
        "endpointPhenotypeDistance": float(continuation.get("endpointPhenotypeDistance", 0.0)),
        "maxEscapeRatio": float(continuation.get("maxEscapeRatio", 0.0)),
        "maxNearestAnchorDistance": float(continuation.get("maxNearestAnchorDistance", 0.0)),
        "maxDistanceToCycleSupport": float(continuation.get("maxDistanceToCycleSupport", 0.0)),
        "maxStepPhenotypeDelta": float(continuation.get("maxStepPhenotypeDelta", 0.0)),
        "ambiguityRate": (ambiguous_count / success_count) if success_count else 0.0,
        "switchRate": (branch_switch_count / success_count) if success_count else 0.0,
    }
    return record


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "runCount": 0,
            "representations": {},
            "topRuns": [],
        }

    def summarize(group: list[dict[str, Any]]) -> dict[str, Any]:
        ambiguity_rates = [float(item["ambiguityRate"]) for item in group]
        switch_rates = [float(item["switchRate"]) for item in group]
        escape_ratios = [float(item["maxEscapeRatio"]) for item in group]
        support_distances = [float(item["maxDistanceToCycleSupport"]) for item in group]
        visit_counts = [int(item["representativeVisitCount"]) for item in group]
        return {
            "runCount": len(group),
            "reentryCount": sum(bool(item["hasReentry"]) for item in group),
            "nonEndpointVisitCount": sum(
                bool(item["visitsNonEndpointRepresentative"]) for item in group
            ),
            "ambiguityRateMean": statistics.fmean(ambiguity_rates),
            "ambiguityRateMedian": statistics.median(ambiguity_rates),
            "switchRateMean": statistics.fmean(switch_rates),
            "switchRateMedian": statistics.median(switch_rates),
            "maxEscapeRatioMean": statistics.fmean(escape_ratios),
            "maxEscapeRatioMedian": statistics.median(escape_ratios),
            "maxDistanceToCycleSupportMean": statistics.fmean(support_distances),
            "maxDistanceToCycleSupportMedian": statistics.median(support_distances),
            "representativeVisitCountMean": statistics.fmean(visit_counts),
            "representativeVisitCountMedian": statistics.median(visit_counts),
        }

    by_representation: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        representation = str(record["representation"])
        by_representation.setdefault(representation, []).append(record)

    top_runs = sorted(
        records,
        key=lambda item: (
            not bool(item["hasReentry"]),
            not bool(item["visitsNonEndpointRepresentative"]),
            float(item["ambiguityRate"]),
            float(item["maxEscapeRatio"]),
            -int(item["representativeVisitCount"]),
        ),
    )
    return {
        "runCount": len(records),
        "representations": {
            key: summarize(value)
            for key, value in sorted(by_representation.items())
        },
        "topRuns": top_runs[:8],
    }


def analyze_continuation_summaries(summary_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    records = [_run_record(path, _load_summary(path)) for path in summary_paths]
    aggregate = {
        "version": 1,
        "packetKind": "topology_generator_continuation_analysis_v1",
        "runCount": len(records),
        "runs": records,
        "aggregate": _aggregate(records),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return aggregate


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate generator-edge continuation summaries for topology analysis."
    )
    parser.add_argument(
        "--summary",
        action="append",
        required=True,
        help="Path to a continuation summary.json; pass multiple times",
    )
    parser.add_argument("--output", help="Output directory for the continuation packet")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    summary_paths = [Path(item).expanduser().resolve() for item in args.summary]
    for path in summary_paths:
        if not path.is_file():
            raise SystemExit(f"Missing continuation summary: {path}")
    root = summary_paths[0].parent.parent
    output_dir = (
        Path(args.output).expanduser().resolve()
        if args.output
        else _default_output_dir(root).resolve()
    )
    analyze_continuation_summaries(summary_paths, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
