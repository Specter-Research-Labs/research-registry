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


def _run_kind(row: dict[str, Any]) -> str:
    tags = row.get("tags")
    if isinstance(tags, dict):
        kind = tags.get("kind")
        if isinstance(kind, str) and kind:
            return kind
    return "untagged"


def _run_role(row: dict[str, Any]) -> str:
    tags = row.get("tags")
    if isinstance(tags, dict):
        role = tags.get("role")
        if isinstance(role, str) and role:
            return role
    return "loop" if _run_kind(row) == "square" else "control"


def _group_key(row: dict[str, Any]) -> str:
    tags = row.get("tags")
    if isinstance(tags, dict):
        control_group = tags.get("controlGroup")
        if isinstance(control_group, str) and control_group:
            return control_group
    return str(row["name"])


def _run_summary(row: dict[str, Any]) -> dict[str, Any]:
    phenotype = float(row["endpointPhenotypeDistance"])
    transported = float(row["endpointTransportedStateDistance"])
    return {
        "name": str(row["name"]),
        "kind": _run_kind(row),
        "bundle": str(row["bundle"]),
        "endpointPhenotypeDistance": phenotype,
        "endpointTransportedStateDistance": transported,
        "transportToPhenotypeRatio": transported / max(phenotype, 1e-12),
        "pointCount": int(row["pointCount"]),
    }


def build_loop_transport_packet(batch_packet_path: Path) -> dict[str, Any]:
    batch = _read_json(batch_packet_path)
    runs = batch.get("runs")
    if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
        raise SystemExit(f"{batch_packet_path}: runs must be a JSON array of objects")

    groups_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in runs:
        groups_by_key.setdefault(_group_key(row), []).append(row)

    group_rows: list[dict[str, Any]] = []
    for key in sorted(groups_by_key):
        rows = groups_by_key[key]
        loop_candidates = [row for row in rows if _run_role(row) == "loop"]
        controls = [row for row in rows if _run_role(row) != "loop"]
        if not loop_candidates:
            continue
        loop_rows = sorted(
            (_run_summary(row) for row in loop_candidates),
            key=lambda row: float(row["endpointTransportedStateDistance"]),
            reverse=True,
        )
        control_rows = sorted(
            (_run_summary(row) for row in controls),
            key=lambda row: (
                -float(row["endpointTransportedStateDistance"]),
                row["name"],
            ),
        )
        loop_summary = loop_rows[0]
        best_control = control_rows[0] if control_rows else None
        group_rows.append(
            {
                "controlGroup": key,
                "topLoop": loop_summary,
                "loops": loop_rows,
                "controls": control_rows,
                "bestControl": best_control,
                "loopMinusBestControlStateClosure": (
                    loop_summary["endpointTransportedStateDistance"]
                    - best_control["endpointTransportedStateDistance"]
                    if best_control is not None
                    else None
                ),
                "loopMinusBestControlPhenotypeClosure": (
                    loop_summary["endpointPhenotypeDistance"]
                    - best_control["endpointPhenotypeDistance"]
                    if best_control is not None
                    else None
                ),
                "loopMinusBestControlRatio": (
                    loop_summary["transportToPhenotypeRatio"]
                    - best_control["transportToPhenotypeRatio"]
                    if best_control is not None
                    else None
                ),
            }
        )

    interesting = sorted(
        group_rows,
        key=lambda row: (
            -float(row["loopMinusBestControlStateClosure"] or 0.0),
            -float(row["topLoop"]["endpointTransportedStateDistance"]),
            str(row["controlGroup"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "loop_transport_packet_v1",
        "sourceBatchPacket": str(batch_packet_path),
        "groupCount": len(group_rows),
        "topGroups": [row["controlGroup"] for row in interesting[:8]],
        "groups": group_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare closed stateful transport loops against matched controls."
    )
    parser.add_argument("--batch-packet", required=True, help="Path to batch packet JSON")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    batch_packet_path = Path(args.batch_packet).expanduser().resolve()
    packet = build_loop_transport_packet(batch_packet_path)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (batch_packet_path.parent / "loop-transport-packet.json").resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Loop transport packet:"
        f" groups={packet['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
