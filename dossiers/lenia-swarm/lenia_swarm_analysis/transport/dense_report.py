from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

KNOWN_VARIANTS = {"mh", "hbias", "mbias"}
KNOWN_SCALES = {"small", "medium", "large"}
KNOWN_PROFILES = {"tight", "wide"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _require_runs(packet: dict[str, Any]) -> list[dict[str, Any]]:
    runs = packet.get("runs")
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
        raise SystemExit("stateful continuation batch packet is missing runs[]")
    return [row for row in runs if isinstance(row, dict)]


def _winner_map(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = packet.get("groups")
    if not isinstance(groups, list) or any(not isinstance(row, dict) for row in groups):
        raise SystemExit("transport winner packet is missing groups[]")
    result: dict[str, dict[str, Any]] = {}
    for row in groups:
        control_group = row.get("controlGroup")
        winner = row.get("winnerByCompositeScore")
        if not isinstance(control_group, str) or not isinstance(winner, dict):
            raise SystemExit("transport winner packet group is incomplete")
        result[control_group] = winner
    return result


def _canonical_group(control_group: str) -> str:
    tokens = [token for token in control_group.split("-") if token]
    if not tokens:
        raise SystemExit("controlGroup must be non-empty")
    if len(tokens) >= 2 and tokens[-1] in KNOWN_PROFILES and tokens[-2] in KNOWN_SCALES:
        return "-".join(tokens[:-2])
    if len(tokens) >= 2 and tokens[-1] in KNOWN_SCALES and tokens[-2] in KNOWN_VARIANTS:
        return "-".join(tokens[:-2])
    if tokens[-1] in KNOWN_SCALES:
        return "-".join(tokens[:-1])
    return control_group


def build_transport_dense_report(
    *,
    dense_batch_packet_path: Path,
    transport_winner_packet_path: Path,
) -> dict[str, Any]:
    dense_packet = _read_json(dense_batch_packet_path)
    winner_packet = _read_json(transport_winner_packet_path)
    winner_map = _winner_map(winner_packet)
    dense_runs = _require_runs(dense_packet)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in dense_runs:
        tags = row.get("tags")
        if not isinstance(tags, dict):
            raise SystemExit("dense batch run is missing tags")
        control_group = tags.get("controlGroup")
        role = tags.get("role")
        if not isinstance(control_group, str) or not isinstance(role, str):
            raise SystemExit("dense batch run tags are incomplete")
        if role != "loop":
            continue
        groups.setdefault(control_group, []).append(row)

    group_rows: list[dict[str, Any]] = []
    for control_group in sorted(groups):
        canonical_group = _canonical_group(control_group)
        if canonical_group not in winner_map:
            raise SystemExit(f"missing winner summary for {control_group}")
        sparse = winner_map[canonical_group]
        dense_rows = sorted(
            groups[control_group],
            key=lambda row: (
                -float(row["endpointTransportedStateDistance"]),
                str(row["name"]),
            ),
        )
        top_dense = dense_rows[0]
        sparse_state = float(sparse["deltaStateClosure"])
        sparse_ratio = float(sparse["deltaRatio"])
        group_rows.append(
            {
                "controlGroup": control_group,
                "canonicalGroup": canonical_group,
                "denseLoopCount": len(dense_rows),
                "denseTopLoopName": str(top_dense["name"]),
                "densePointCount": int(top_dense["pointCount"]),
                "denseStateClosure": float(top_dense["endpointTransportedStateDistance"]),
                "denseRatio": float(top_dense["transportToPhenotypeRatio"]),
                "denseMaxStateFromStart": float(top_dense["maxTransportedStateDistanceFromStart"]),
                "sparseWinnerControlGroup": str(sparse["controlGroup"]),
                "sparseWinnerStateSurplus": sparse_state,
                "sparseWinnerRatioSurplus": sparse_ratio,
                "denseRuns": [
                    {
                        "name": str(row["name"]),
                        "pointCount": int(row["pointCount"]),
                        "stateClosure": float(row["endpointTransportedStateDistance"]),
                        "ratio": float(row["transportToPhenotypeRatio"]),
                        "maxStateFromStart": float(row["maxTransportedStateDistanceFromStart"]),
                    }
                    for row in dense_rows
                ],
            }
        )

    return {
        "version": 1,
        "packetKind": "transport_dense_report_v1",
        "sourceDenseBatchPacket": str(dense_batch_packet_path),
        "sourceTransportWinnerPacket": str(transport_winner_packet_path),
        "groupCount": len(group_rows),
        "topGroups": [row["controlGroup"] for row in group_rows],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare dense winner-loop runs against sparse winner selections."
    )
    parser.add_argument("--dense-batch-packet", required=True, help="Path to dense batch packet")
    parser.add_argument(
        "--transport-winner-packet",
        required=True,
        help="Path to transport winner packet",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_transport_dense_report(
        dense_batch_packet_path=Path(args.dense_batch_packet).expanduser().resolve(),
        transport_winner_packet_path=Path(args.transport_winner_packet).expanduser().resolve(),
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(args.dense_batch_packet).expanduser().resolve().parent
        / "transport-dense-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport dense report:"
        f" groups={report['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
