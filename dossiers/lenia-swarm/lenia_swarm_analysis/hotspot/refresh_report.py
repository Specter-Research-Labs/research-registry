from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _require_rows(packet: dict[str, Any], *, name: str) -> list[dict[str, Any]]:
    rows = packet.get("runs")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SystemExit(f"{name}: runs[] is required")
    return [row for row in rows if isinstance(row, dict)]


def _baseline_key(name: str, coordinate: str) -> tuple[str, str]:
    specimen = name.split("-", 1)[0]
    return specimen, coordinate


def _baseline_map(atlas_packet: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = _require_rows(atlas_packet, name="atlas packet")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        name = row.get("name")
        coordinate = row.get("coordinate")
        if not isinstance(name, str) or not isinstance(coordinate, str):
            raise SystemExit("atlas run is missing name or coordinate")
        result[_baseline_key(name, coordinate)] = row
    return result


def build_hotspot_transport_refresh_report(
    *,
    refresh_batch_packet_path: Path,
    baseline_atlas_packet_path: Path,
) -> dict[str, Any]:
    refresh_packet = _read_json(refresh_batch_packet_path)
    atlas_packet = _read_json(baseline_atlas_packet_path)
    refresh_rows = _require_rows(refresh_packet, name="refresh batch packet")
    baseline_rows = _baseline_map(atlas_packet)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in refresh_rows:
        tags = row.get("tags")
        if not isinstance(tags, dict):
            raise SystemExit("refresh batch run is missing tags")
        control_group = tags.get("controlGroup")
        profile = tags.get("profile")
        coordinate = tags.get("coordinate")
        specimen = tags.get("specimen")
        candidate_id = tags.get("candidateId")
        required = (control_group, profile, coordinate, specimen, candidate_id)
        if not all(isinstance(value, str) for value in required):
            raise SystemExit("refresh batch tags are incomplete")
        baseline = baseline_rows.get((specimen, coordinate))
        if baseline is None:
            raise SystemExit(f"missing atlas baseline for {specimen} {coordinate}")
        refresh_ratio = float(row["transportToPhenotypeRatio"])
        refresh_state = float(row["endpointTransportedStateDistance"])
        baseline_ratio = float(baseline["transportToPhenotypeRatio"])
        baseline_state = float(baseline["endpointTransportedStateDistance"])
        grouped.setdefault(control_group, []).append(
            {
                "candidateId": candidate_id,
                "profile": profile,
                "coordinate": coordinate,
                "specimen": specimen,
                "refreshRunName": str(row["name"]),
                "refreshPacketPath": str(row["packetPath"]),
                "refreshRatio": refresh_ratio,
                "refreshStateDistance": refresh_state,
                "baselineRunName": str(baseline["name"]),
                "baselineRatio": baseline_ratio,
                "baselineStateDistance": baseline_state,
                "deltaRatioVsBaseline": refresh_ratio - baseline_ratio,
                "deltaStateDistanceVsBaseline": refresh_state - baseline_state,
            }
        )

    group_rows: list[dict[str, Any]] = []
    for control_group in sorted(grouped):
        rows = sorted(
            grouped[control_group],
            key=lambda row: (
                row["candidateId"],
                row["profile"],
                row["coordinate"],
            ),
        )
        best_ratio = max(rows, key=lambda row: float(row["deltaRatioVsBaseline"]))
        best_state = max(rows, key=lambda row: float(row["deltaStateDistanceVsBaseline"]))
        group_rows.append(
            {
                "controlGroup": control_group,
                "runCount": len(rows),
                "positiveRatioDeltaCount": sum(
                    1 for row in rows if float(row["deltaRatioVsBaseline"]) > 0.0
                ),
                "positiveStateDeltaCount": sum(
                    1 for row in rows if float(row["deltaStateDistanceVsBaseline"]) > 0.0
                ),
                "bestByRatioDelta": best_ratio,
                "bestByStateDelta": best_state,
                "runs": rows,
            }
        )

    top_groups = sorted(
        group_rows,
        key=lambda row: (
            -float(row["bestByRatioDelta"]["deltaRatioVsBaseline"]),
            -float(row["bestByStateDelta"]["deltaStateDistanceVsBaseline"]),
            str(row["controlGroup"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "hotspot_transport_refresh_report_v1",
        "sourceRefreshBatchPacket": str(refresh_batch_packet_path),
        "sourceBaselineAtlasPacket": str(baseline_atlas_packet_path),
        "groupCount": len(group_rows),
        "topGroups": [row["controlGroup"] for row in top_groups],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare hotspot neighborhood refresh transport runs "
            "against the baseline atlas."
        )
    )
    parser.add_argument(
        "--refresh-batch-packet",
        required=True,
        help="Path to stateful_continuation_batch_packet_v1 for hotspot refresh runs",
    )
    parser.add_argument(
        "--baseline-atlas-packet",
        required=True,
        help="Path to baseline stateful_continuation_batch_packet_v1 atlas",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_hotspot_transport_refresh_report(
        refresh_batch_packet_path=Path(args.refresh_batch_packet).expanduser().resolve(),
        baseline_atlas_packet_path=Path(args.baseline_atlas_packet).expanduser().resolve(),
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(args.refresh_batch_packet).expanduser().resolve().parent
        / "hotspot-transport-refresh-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Hotspot transport refresh report:"
        f" groups={report['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
