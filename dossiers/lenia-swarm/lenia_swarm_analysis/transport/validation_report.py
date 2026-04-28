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


def _require_dict_list(value: Any, *, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{name} must be a JSON array of objects")
    return [row for row in value if isinstance(row, dict)]


def _parse_labeled_packet(value: str) -> tuple[str, Path]:
    if "=" in value:
        label, raw_path = value.split("=", 1)
        label = label.strip()
        if not label:
            raise SystemExit("--packet label must be non-empty")
        return label, Path(raw_path).expanduser().resolve()
    path = Path(value).expanduser().resolve()
    return path.stem, path


def _winner_map(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = _require_dict_list(packet.get("groups"), name="groups")
    mapping: dict[str, dict[str, Any]] = {}
    for row in groups:
        winner = row.get("winnerByCompositeScore")
        if not isinstance(winner, dict):
            raise SystemExit("winner packet group is missing winnerByCompositeScore")
        mapping[str(winner["controlGroup"])] = {
            "canonicalGroup": str(row["controlGroup"]),
            "winnerControlGroup": str(winner["controlGroup"]),
            "winnerDeltaStateClosure": float(winner["deltaStateClosure"]),
            "winnerDeltaRatio": float(winner["deltaRatio"]),
            "winnerPacketLabel": str(winner["packetLabel"]),
        }
    return mapping


def build_transport_validation_report(
    *,
    transport_winner_packet_path: Path,
    labeled_validation_packets: list[tuple[str, Path]],
) -> dict[str, Any]:
    if not labeled_validation_packets:
        raise SystemExit("at least one validation packet is required")

    winner_map = _winner_map(_read_json(transport_winner_packet_path))
    group_rows: list[dict[str, Any]] = []
    skipped_groups: list[dict[str, str]] = []
    for packet_label, packet_path in labeled_validation_packets:
        packet = _read_json(packet_path)
        groups = _require_dict_list(packet.get("groups"), name="groups")
        for row in groups:
            validation_group = str(row["controlGroup"])
            if not validation_group.endswith("-validation"):
                raise SystemExit(
                    f"{validation_group}: validation control group must end with -validation"
                )
            winner_control_group = validation_group[: -len("-validation")]
            if winner_control_group not in winner_map:
                skipped_groups.append(
                    {
                        "packetLabel": packet_label,
                        "validationControlGroup": validation_group,
                        "reason": "missing sparse winner",
                    }
                )
                continue
            winner = winner_map[winner_control_group]
            best_control = row.get("bestControl")
            if not isinstance(best_control, dict):
                raise SystemExit(f"{validation_group}: missing bestControl")
            validation_delta_state = float(row["loopMinusBestControlStateClosure"] or 0.0)
            validation_delta_ratio = float(row["loopMinusBestControlRatio"] or 0.0)
            group_rows.append(
                {
                    "packetLabel": packet_label,
                    "validationControlGroup": validation_group,
                    "winnerControlGroup": winner_control_group,
                    "canonicalGroup": winner["canonicalGroup"],
                    "validationTopLoop": str(row["topLoop"]["name"]),
                    "validationBestControl": str(best_control["name"]),
                    "validationBestControlKind": str(best_control["kind"]),
                    "validationDeltaStateClosure": validation_delta_state,
                    "validationDeltaRatio": validation_delta_ratio,
                    "winnerDeltaStateClosure": float(winner["winnerDeltaStateClosure"]),
                    "winnerDeltaRatio": float(winner["winnerDeltaRatio"]),
                    "validationMinusWinnerDeltaState": (
                        validation_delta_state - float(winner["winnerDeltaStateClosure"])
                    ),
                    "validationMinusWinnerDeltaRatio": (
                        validation_delta_ratio - float(winner["winnerDeltaRatio"])
                    ),
                    "survivesValidationByState": validation_delta_state > 0.0,
                    "survivesValidationByRatio": validation_delta_ratio > 0.0,
                    "survivesValidationStrongly": (
                        validation_delta_state > 0.0 and validation_delta_ratio > 0.0
                    ),
                }
            )

    interesting = sorted(
        group_rows,
        key=lambda row: (
            -float(row["validationDeltaStateClosure"]),
            -float(row["validationDeltaRatio"]),
            str(row["validationControlGroup"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "transport_validation_report_v1",
        "sourceTransportWinnerPacket": str(transport_winner_packet_path),
        "sourceValidationPackets": [
            {"label": label, "path": str(path)} for label, path in labeled_validation_packets
        ],
        "groupCount": len(group_rows),
        "skippedGroupCount": len(skipped_groups),
        "survivesValidationStronglyCount": sum(
            1 for row in group_rows if bool(row["survivesValidationStrongly"])
        ),
        "topGroups": [row["validationControlGroup"] for row in interesting[:8]],
        "skippedGroups": skipped_groups,
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare dense winner-validation controls against sparse winner groups."
    )
    parser.add_argument(
        "--transport-winner-packet",
        required=True,
        help="Path to transport winner packet",
    )
    parser.add_argument(
        "--packet",
        action="append",
        default=[],
        help="Validation loop packet input as LABEL=/absolute/path.json",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    labeled_packets = [_parse_labeled_packet(value) for value in args.packet]
    report = build_transport_validation_report(
        transport_winner_packet_path=Path(args.transport_winner_packet).expanduser().resolve(),
        labeled_validation_packets=labeled_packets,
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else labeled_packets[0][1].parent / "transport-validation-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport validation report:"
        f" groups={report['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
