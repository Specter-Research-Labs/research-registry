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


def _coord_code(value: str) -> str:
    token = value.split(".", 1)[0]
    cleaned = "".join(ch for ch in token if ch.isalnum())
    return cleaned or "coord"


def _loop_vertices(loop_row: dict[str, Any]) -> tuple[list[str], list[list[float]], str]:
    loop_spec = loop_row.get("loopSpec")
    if not isinstance(loop_spec, dict):
        raise SystemExit("loop row is missing loopSpec")
    coordinates = loop_spec.get("coordinates")
    vertices = loop_spec.get("vertices")
    if not isinstance(coordinates, list) or any(not isinstance(v, str) for v in coordinates):
        raise SystemExit("loopSpec is missing coordinates")
    if not isinstance(vertices, list) or any(not isinstance(row, list) for row in vertices):
        raise SystemExit("loopSpec is missing vertices")
    if len(coordinates) != 2 or len(vertices) < 5:
        raise SystemExit("validation batch expects 2D closed loops with five vertices")
    return (
        [str(value) for value in coordinates],
        [[float(item) for item in row] for row in vertices],
        str(loop_spec.get("name") or loop_row["name"]),
    )


def _control_values(control_row: dict[str, Any]) -> tuple[str, list[float]]:
    coordinate = control_row.get("coordinate")
    values = control_row.get("values")
    if not isinstance(coordinate, str):
        raise SystemExit("control row is missing coordinate")
    if not isinstance(values, list) or any(not isinstance(v, (int, float)) for v in values):
        raise SystemExit("control row is missing values")
    return coordinate, [float(value) for value in values]


def _winner_sources(packet: dict[str, Any]) -> dict[str, Path]:
    sources = _require_dict_list(packet.get("sourcePackets"), name="sourcePackets")
    mapping: dict[str, Path] = {}
    for row in sources:
        label = row.get("label")
        raw_path = row.get("path")
        if not isinstance(label, str) or not isinstance(raw_path, str):
            raise SystemExit("sourcePackets entries need label and path")
        mapping[label] = Path(raw_path).expanduser().resolve()
    return mapping


def _winner_groups(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = _require_dict_list(packet.get("groups"), name="groups")
    return {str(row["controlGroup"]): row for row in groups}


def _loop_packet_group(loop_packet: dict[str, Any], control_group: str) -> dict[str, Any]:
    groups = _require_dict_list(loop_packet.get("groups"), name="groups")
    for row in groups:
        if str(row.get("controlGroup")) == control_group:
            return row
    raise SystemExit(f"{control_group}: missing loop packet group")


def _batch_rows(batch_packet: dict[str, Any], control_group: str) -> list[dict[str, Any]]:
    rows = _require_dict_list(batch_packet.get("runs"), name="runs")
    selected = [
        row
        for row in rows
        if isinstance(row.get("tags"), dict)
        and str(row["tags"].get("controlGroup")) == control_group
    ]
    if not selected:
        raise SystemExit(f"{control_group}: missing batch rows")
    return selected


def _loop_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row.get("tags"), dict) and str(row["tags"].get("role")) == "loop"
    ]


def _control_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row.get("tags"), dict) and str(row["tags"].get("role")) == "control"
    ]


def build_transport_validation_batch_spec(
    *,
    transport_winner_packet_path: Path,
    groups: list[str] | None,
    output_root: Path,
    samples_per_segment: int,
) -> dict[str, Any]:
    winner_packet = _read_json(transport_winner_packet_path)
    if winner_packet.get("packetKind") != "transport_winner_packet_v1":
        raise SystemExit("validation batch expects transport_winner_packet_v1")

    source_map = _winner_sources(winner_packet)
    group_map = _winner_groups(winner_packet)
    target_groups = groups or list(group_map.keys())
    if not target_groups:
        raise SystemExit("no winner groups available for validation batch")

    runs: list[dict[str, Any]] = []
    cli_binary: str | None = None
    for canonical_group in target_groups:
        if canonical_group not in group_map:
            raise SystemExit(f"{canonical_group}: missing winner group")
        winner_group = group_map[canonical_group]
        winner = winner_group.get("winnerByCompositeScore")
        if not isinstance(winner, dict):
            raise SystemExit(f"{canonical_group}: winnerByCompositeScore is missing")
        packet_label = winner.get("packetLabel")
        control_group = winner.get("controlGroup")
        if not isinstance(packet_label, str) or not isinstance(control_group, str):
            raise SystemExit(f"{canonical_group}: winner is incomplete")
        if packet_label not in source_map:
            raise SystemExit(f"{canonical_group}: source packet {packet_label} is missing")

        loop_packet_path = source_map[packet_label]
        loop_packet = _read_json(loop_packet_path)
        batch_packet_path = Path(str(loop_packet["sourceBatchPacket"])).expanduser().resolve()
        batch_packet = _read_json(batch_packet_path)
        source_spec_path = Path(str(batch_packet["sourceSpec"])).expanduser().resolve()
        source_spec = _read_json(source_spec_path)
        current_cli_binary = str(Path(str(source_spec["cliBinary"])).expanduser().resolve())
        if cli_binary is None:
            cli_binary = current_cli_binary
        elif cli_binary != current_cli_binary:
            raise SystemExit("validation batch requires a single cliBinary")

        _loop_packet_group(loop_packet, control_group)
        batch_rows = _batch_rows(batch_packet, control_group)
        loop_rows = _loop_rows(batch_rows)
        control_rows = _control_rows(batch_rows)
        if len(loop_rows) < 2 or len(control_rows) < 2:
            raise SystemExit(f"{control_group}: validation batch needs two loops and two controls")

        specimen = None
        bundle = None
        for row in batch_rows:
            tags = row.get("tags")
            if isinstance(tags, dict) and isinstance(tags.get("specimen"), str):
                specimen = str(tags["specimen"])
            if isinstance(row.get("bundle"), str):
                bundle = str(row["bundle"])
            if specimen and bundle:
                break
        if specimen is None or bundle is None:
            raise SystemExit(f"{control_group}: missing specimen or bundle")

        validation_group = f"{control_group}-validation"
        for row in loop_rows:
            coordinates, vertices, base_name = _loop_vertices(row)
            kind = str(row["tags"]["kind"])
            runs.append(
                {
                    "name": f"{base_name}-dense",
                    "bundle": bundle,
                    "coordinates": coordinates,
                    "vertices": vertices,
                    "closed": True,
                    "samplesPerSegment": samples_per_segment,
                    "tags": {
                        "specimen": specimen,
                        "controlGroup": validation_group,
                        "kind": f"{kind}-dense",
                        "role": "loop",
                    },
                }
            )

        for row in control_rows:
            coordinate, values = _control_values(row)
            kind = str(row["tags"]["kind"])
            runs.append(
                {
                    "name": f"{row['name']}-dense",
                    "bundle": bundle,
                    "coordinate": coordinate,
                    "values": values,
                    "tags": {
                        "specimen": specimen,
                        "controlGroup": validation_group,
                        "kind": f"{kind}-dense",
                        "role": "control",
                    },
                }
            )

        coordinates, vertices, _ = _loop_vertices(loop_rows[0])
        p0, p1, p2, p3 = vertices[:4]
        code_ab = f"{_coord_code(coordinates[0])}{_coord_code(coordinates[1])}"
        code_ba = f"{_coord_code(coordinates[1])}{_coord_code(coordinates[0])}"
        runs.extend(
            [
                {
                    "name": f"{control_group}-zeroarea-{code_ab}-dense",
                    "bundle": bundle,
                    "coordinates": coordinates,
                    "vertices": [p0, p1, p2, p1, p0],
                    "closed": True,
                    "samplesPerSegment": samples_per_segment,
                    "tags": {
                        "specimen": specimen,
                        "controlGroup": validation_group,
                        "kind": f"zeroarea-{code_ab}-dense",
                        "role": "control",
                    },
                },
                {
                    "name": f"{control_group}-zeroarea-{code_ba}-dense",
                    "bundle": bundle,
                    "coordinates": coordinates,
                    "vertices": [p0, p3, p2, p3, p0],
                    "closed": True,
                    "samplesPerSegment": samples_per_segment,
                    "tags": {
                        "specimen": specimen,
                        "controlGroup": validation_group,
                        "kind": f"zeroarea-{code_ba}-dense",
                        "role": "control",
                    },
                },
            ]
        )

    if cli_binary is None:
        raise SystemExit("validation batch could not resolve cliBinary")

    return {
        "version": 1,
        "cliBinary": cli_binary,
        "outputRoot": str((output_root / "runs").resolve()),
        "runs": runs,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build dense winner-validation stateful continuation batch specs."
    )
    parser.add_argument(
        "--transport-winner-packet",
        required=True,
        help="Path to transport winner packet",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Canonical winner group to include; defaults to all groups",
    )
    parser.add_argument(
        "--samples-per-segment",
        type=int,
        default=4,
        help="Loop samples per segment for dense validation",
    )
    parser.add_argument("--output", required=True, help="Output batch-spec path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_path = Path(args.output).expanduser().resolve()
    spec = build_transport_validation_batch_spec(
        transport_winner_packet_path=Path(args.transport_winner_packet).expanduser().resolve(),
        groups=[str(value) for value in args.group] or None,
        output_root=output_path.parent,
        samples_per_segment=int(args.samples_per_segment),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transport validation batch:"
        f" runs={len(spec['runs'])}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
