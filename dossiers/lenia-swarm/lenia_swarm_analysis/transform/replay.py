from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from lenia_swarm_analysis._io import read_jsonl
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_SPECS,
    TERMINAL_AXIS_SPECS,
    compute_center_velocity_trace,
    developmental_trace_from_samples,
    extract_terminal_raw_axes_from_row,
    preferred_family_kind,
    transform_axes,
)


def _validate_trace_steps(
    *,
    specimen_id: str,
    expected_steps: list[int],
    trace_samples: list[dict[str, Any]],
) -> list[int]:
    ordered = sorted(trace_samples, key=lambda row: int(row["step"]))
    observed_steps = [int(row["step"]) for row in ordered]
    if expected_steps and observed_steps != expected_steps:
        raise SystemExit(
            f"{specimen_id}: capturedSteps mismatch between summary row and trace file"
        )
    return observed_steps


def _specimen_record(summary_row: dict[str, Any]) -> dict[str, Any]:
    specimen_id = str(summary_row.get("specimenId", "unknown"))
    trace_path_raw = summary_row.get("developmentTracePath")
    if not isinstance(trace_path_raw, str) or not trace_path_raw:
        raise SystemExit(f"{specimen_id}: missing developmentTracePath")
    trace_path = Path(trace_path_raw).expanduser().resolve()
    trace_samples = read_jsonl(trace_path)
    expected_steps = [int(step) for step in summary_row.get("capturedSteps", [])]
    observed_steps = _validate_trace_steps(
        specimen_id=specimen_id,
        expected_steps=expected_steps,
        trace_samples=trace_samples,
    )
    sample_count = int(summary_row.get("sampleCount", len(trace_samples)))
    if sample_count != len(trace_samples):
        raise SystemExit(
            f"{specimen_id}: sampleCount={sample_count} "
            f"but trace contains {len(trace_samples)} rows"
        )
    trajectory = summary_row.get("trajectory")
    if not isinstance(trajectory, dict):
        raise SystemExit(f"{specimen_id}: missing trajectory descriptor")
    terminal_axes = extract_terminal_raw_axes_from_row(summary_row)
    transformed_terminal_axes = transform_axes(terminal_axes)
    meander_final = float(terminal_axes["meander"])
    development = developmental_trace_from_samples(
        specimen_id=specimen_id,
        trace_samples=trace_samples,
        meander_final=meander_final,
    )
    return {
        "specimenId": specimen_id,
        "specimenName": str(summary_row.get("specimenName", specimen_id)),
        "runId": str(summary_row.get("runId", summary_row.get("sourceRunId", "unknown"))),
        "campaignId": summary_row.get("campaignId"),
        "sourceKind": str(summary_row.get("sourceKind", "unknown")),
        "sourceRunId": str(summary_row.get("sourceRunId", "unknown")),
        "sourceCampaignId": summary_row.get("sourceCampaignId"),
        "sourceInputPath": str(summary_row.get("sourceInputPath", "")),
        "sourceMode": summary_row.get("sourceMode"),
        "sourceAlgorithm": summary_row.get("sourceAlgorithm"),
        "regimeFamily": summary_row.get("regimeFamily"),
        "geometryFamily": summary_row.get("geometryFamily"),
        "canonicalFamily": summary_row.get("canonicalFamily"),
        "familyKind": preferred_family_kind(summary_row),
        "initialConditionFamily": str(summary_row.get("initialConditionFamily", "unknown")),
        "replayRunId": str(summary_row.get("replayRunId", "unknown")),
        "replaySteps": int(summary_row.get("replaySteps", 0)),
        "recordEvery": int(summary_row.get("recordEvery", 0)),
        "includeInitial": bool(summary_row.get("includeInitial", False)),
        "sampleCount": sample_count,
        "capturedSteps": observed_steps,
        "developmentTracePath": str(trace_path),
        "developmentFramesDir": summary_row.get("developmentFramesDir"),
        "resultsPath": str(summary_row.get("resultsPath", "")),
        "terminal": summary_row.get("terminal"),
        "trajectory": trajectory,
        "terminalAxes": terminal_axes,
        "transformedTerminalAxes": transformed_terminal_axes,
        "developmentalAxes": development["developmentalAxes"],
        "transformedDevelopmentalAxes": development["transformedDevelopmentalAxes"],
        "traceSteps": development["steps"],
        "traceAxes": development["traceAxes"],
        "traceCenterVelocity": compute_center_velocity_trace(trace_samples),
    }


def build_transformation_replay_packet(*, development_traces_path: Path) -> dict[str, Any]:
    summary_rows = read_jsonl(development_traces_path)
    specimens = [_specimen_record(row) for row in summary_rows]
    regime_counts = Counter(
        str(record["regimeFamily"]) for record in specimens if record["regimeFamily"] is not None
    )
    geometry_counts = Counter(
        str(record["geometryFamily"])
        for record in specimens
        if record["geometryFamily"] is not None
    )
    canonical_counts = Counter(
        str(record["canonicalFamily"])
        for record in specimens
        if record["canonicalFamily"] is not None
    )
    family_counts = Counter(str(record["familyKind"]) for record in specimens)
    return {
        "version": 1,
        "packetKind": "transformation_replay_packet_v1",
        "sourceArtifact": str(development_traces_path),
        "summary": {
            "specimenCount": len(specimens),
            "terminalAxisCount": len(TERMINAL_AXIS_SPECS),
            "developmentalAxisCount": len(DEVELOPMENTAL_AXIS_SPECS),
            "familyKinds": sorted(family_counts),
            "regimeFamilies": sorted(regime_counts),
            "geometryFamilies": sorted(geometry_counts),
            "canonicalFamilies": sorted(canonical_counts),
        },
        "groupCounts": {
            "familyKind": dict(sorted(family_counts.items())),
            "regimeFamily": dict(sorted(regime_counts.items())),
            "geometryFamily": dict(sorted(geometry_counts.items())),
            "canonicalFamily": dict(sorted(canonical_counts.items())),
        },
        "terminalAxes": list(TERMINAL_AXIS_SPECS),
        "developmentalAxes": list(DEVELOPMENTAL_AXIS_SPECS),
        "specimens": specimens,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a replay-time developmental transformation packet."
    )
    parser.add_argument(
        "--development-traces",
        required=True,
        help="Path to replay output development-traces.jsonl",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    traces_path = Path(args.development_traces).expanduser().resolve()
    packet = build_transformation_replay_packet(development_traces_path=traces_path)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else traces_path.parent / "transformation-replay-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transformation replay packet:"
        f" specimens={packet['summary']['specimenCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
