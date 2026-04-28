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


def _require_runs(packet: dict[str, Any]) -> list[dict[str, Any]]:
    runs = packet.get("runs")
    if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
        raise SystemExit("stateful continuation batch packet is missing runs[]")
    return [row for row in runs if isinstance(row, dict)]


def _float_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows]


def _stable(values: list[float], *, tolerance: float = 1e-12) -> bool:
    if not values:
        return True
    return max(values) - min(values) <= tolerance


def build_transport_repro_report(batch_packet_path: Path) -> dict[str, Any]:
    packet = _read_json(batch_packet_path)
    runs = _require_runs(packet)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in runs:
        tags = row.get("tags")
        if not isinstance(tags, dict):
            raise SystemExit("repro batch run is missing tags")
        control_group = tags.get("controlGroup")
        kind = tags.get("kind")
        role = tags.get("role")
        if not all(isinstance(value, str) for value in (control_group, kind, role)):
            raise SystemExit("repro batch run tags are incomplete")
        groups.setdefault((str(control_group), str(kind)), []).append(row)

    group_rows: list[dict[str, Any]] = []
    for (control_group, kind), rows in sorted(groups.items()):
        phenotype_values = _float_values(rows, "endpointPhenotypeDistance")
        state_values = _float_values(rows, "endpointTransportedStateDistance")
        ratio_values = _float_values(rows, "transportToPhenotypeRatio")
        row_role = rows[0]["tags"]["role"]
        group_rows.append(
            {
                "controlGroup": control_group,
                "kind": kind,
                "role": str(row_role),
                "repeatCount": len(rows),
                "phenotypeClosureMin": min(phenotype_values),
                "phenotypeClosureMax": max(phenotype_values),
                "phenotypeClosureRange": max(phenotype_values) - min(phenotype_values),
                "stateClosureMin": min(state_values),
                "stateClosureMax": max(state_values),
                "stateClosureRange": max(state_values) - min(state_values),
                "ratioMin": min(ratio_values),
                "ratioMax": max(ratio_values),
                "ratioRange": max(ratio_values) - min(ratio_values),
                "phenotypeStable": _stable(phenotype_values),
                "stateStable": _stable(state_values),
                "ratioStable": _stable(ratio_values),
                "runNames": [str(row["name"]) for row in rows],
            }
        )

    control_groups = sorted({row["controlGroup"] for row in group_rows})
    summary_rows: list[dict[str, Any]] = []
    for control_group in control_groups:
        members = [row for row in group_rows if row["controlGroup"] == control_group]
        summary_rows.append(
            {
                "controlGroup": control_group,
                "kindCount": len(members),
                "allKindsStable": all(
                    row["phenotypeStable"] and row["stateStable"] and row["ratioStable"]
                    for row in members
                ),
                "maxStateClosureRange": max(row["stateClosureRange"] for row in members),
                "maxRatioRange": max(row["ratioRange"] for row in members),
                "kinds": members,
            }
        )

    return {
        "version": 1,
        "packetKind": "transport_repro_report_v1",
        "sourceBatchPacket": str(batch_packet_path),
        "groupCount": len(summary_rows),
        "topGroups": [row["controlGroup"] for row in summary_rows],
        "groups": summary_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize repeat stability for winner-loop transport batches."
    )
    parser.add_argument("--batch-packet", required=True, help="Path to batch packet JSON")
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    batch_packet_path = Path(args.batch_packet).expanduser().resolve()
    report = build_transport_repro_report(batch_packet_path)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else batch_packet_path.parent / "transport-repro-report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport repro report:"
        f" groups={report['groupCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
