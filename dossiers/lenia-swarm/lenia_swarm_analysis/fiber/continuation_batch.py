from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .continuation import build_loop_spec, run_stateful_continuation


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _resolve_param_path(params: Any, coordinate: str) -> float:
    current = params
    for raw_part in coordinate.split("."):
        if isinstance(current, dict):
            if raw_part not in current:
                raise SystemExit(f"Coordinate {coordinate} is missing path segment {raw_part}")
            current = current[raw_part]
            continue
        if isinstance(current, list):
            try:
                index = int(raw_part)
            except ValueError as exc:
                raise SystemExit(
                    f"Coordinate {coordinate} needs an integer index at segment {raw_part}"
                ) from exc
            if index < 0 or index >= len(current):
                raise SystemExit(f"Coordinate {coordinate} index {index} is out of range")
            current = current[index]
            continue
        raise SystemExit(f"Coordinate {coordinate} cannot descend through {type(current).__name__}")
    if not isinstance(current, (int, float)):
        raise SystemExit(f"Coordinate {coordinate} did not resolve to a numeric value")
    return float(current)


def _bundle_center_value(bundle: Path, coordinate: str) -> float:
    base = _read_json(bundle / "base.json")
    params = base.get("params")
    if not isinstance(params, dict):
        raise SystemExit(f"{bundle}: missing base.params")
    return _resolve_param_path(params, coordinate)


def _run_output_path(output_root: Path, name: str, raw_output: str | None) -> Path:
    if raw_output is not None:
        return Path(raw_output).expanduser().resolve()
    return (output_root / _slug(name)).resolve()


def _run_values(run_spec: dict[str, Any], center_value: float) -> list[float]:
    values = run_spec.get("values")
    if isinstance(values, list):
        return [float(value) for value in values]
    offsets = run_spec.get("offsets")
    if isinstance(offsets, list):
        return [center_value + float(offset) for offset in offsets]
    raise SystemExit("Each stateful continuation batch run needs either values or offsets")


def _run_loop_spec(
    bundle: Path,
    run_spec: dict[str, Any],
) -> tuple[str | None, float | None, list[float] | None, dict[str, Any] | None]:
    coordinate = run_spec.get("coordinate")
    if isinstance(coordinate, str):
        center_value = _bundle_center_value(bundle, coordinate)
        values = _run_values(run_spec, center_value)
        return coordinate, center_value, values, None

    coordinates = run_spec.get("coordinates")
    vertices = run_spec.get("vertices")
    if not isinstance(coordinates, list) or any(
        not isinstance(item, str) for item in coordinates
    ):
        raise SystemExit(
            "Each stateful continuation batch run needs coordinate or coordinates"
        )
    if not isinstance(vertices, list) or any(not isinstance(row, list) for row in vertices):
        raise SystemExit("Explicit loop runs need a vertices array")
    coordinate_list = [str(item) for item in coordinates]
    loop_spec = build_loop_spec(
        coordinates=coordinate_list,
        vertices=[[float(value) for value in row] for row in vertices],
        name=str(run_spec["name"]),
        closed=bool(run_spec.get("closed", False)),
        samples_per_segment=int(run_spec.get("samplesPerSegment", 1)),
    )
    return None, None, None, loop_spec


def run_batch_from_spec(spec_path: Path) -> dict[str, Any]:
    spec = _read_json(spec_path)
    cli_binary = Path(str(spec["cliBinary"])).expanduser().resolve()
    output_root = Path(str(spec["outputRoot"])).expanduser().resolve()
    default_db = spec.get("db")
    default_db_path = Path(str(default_db)).expanduser().resolve() if default_db else None
    default_export_enabled = bool(spec.get("exportEnabled", False))
    runs = spec.get("runs")
    if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
        raise SystemExit(f"{spec_path}: runs must be a JSON array of objects")

    run_rows: list[dict[str, Any]] = []
    for run_spec in runs:
        name = run_spec.get("name")
        bundle_raw = run_spec.get("bundle")
        if not isinstance(name, str) or not isinstance(bundle_raw, str):
            raise SystemExit("Each stateful continuation batch run needs name and bundle")
        bundle = Path(bundle_raw).expanduser().resolve()
        coordinate, center_value, values, loop_spec = _run_loop_spec(bundle, run_spec)
        output = _run_output_path(output_root, name, run_spec.get("output"))
        run_result = run_stateful_continuation(
            cli_binary=cli_binary,
            bundle=bundle,
            coordinate=coordinate,
            values=values,
            output=output,
            name=name,
            run_id=run_spec.get("runId") if isinstance(run_spec.get("runId"), str) else None,
            db=(
                Path(str(run_spec["db"])).expanduser().resolve()
                if isinstance(run_spec.get("db"), str)
                else default_db_path
            ),
            export_enabled=bool(run_spec.get("exportEnabled", default_export_enabled)),
            loop_spec=loop_spec,
        )
        packet = run_result["packet"]
        phenotype = float(packet["endpointPhenotypeDistance"])
        transported = float(packet["endpointTransportedStateDistance"])
        ratio = transported / max(phenotype, 1e-12)
        run_rows.append(
            {
                "name": name,
                "tags": run_spec.get("tags") if isinstance(run_spec.get("tags"), dict) else None,
                "bundle": str(bundle),
                "coordinate": coordinate,
                "centerValue": center_value,
                "values": values,
                "loopSpec": loop_spec,
                "output": str(output),
                "packetPath": str(run_result["packetPath"]),
                "pointCount": int(packet["pointCount"]),
                "endpointPhenotypeDistance": phenotype,
                "endpointTransportedStateDistance": transported,
                "transportToPhenotypeRatio": ratio,
                "maxPhenotypeDistanceFromStart": float(packet["maxPhenotypeDistanceFromStart"]),
                "maxTransportedStateDistanceFromStart": float(
                    packet["maxTransportedStateDistanceFromStart"]
                ),
            }
        )

    interesting = sorted(
        run_rows,
        key=lambda row: (
            -float(row["transportToPhenotypeRatio"]),
            -float(row["endpointTransportedStateDistance"]),
            str(row["name"]),
        ),
    )
    return {
        "version": 1,
        "packetKind": "stateful_continuation_batch_packet_v1",
        "sourceSpec": str(spec_path),
        "runCount": len(run_rows),
        "maxTransportToPhenotypeRatio": max(
            (float(row["transportToPhenotypeRatio"]) for row in run_rows),
            default=0.0,
        ),
        "maxEndpointTransportedStateDistance": max(
            (float(row["endpointTransportedStateDistance"]) for row in run_rows),
            default=0.0,
        ),
        "interestingRuns": [row["name"] for row in interesting[:8]],
        "runs": run_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a batch of Flow-native stateful continuation experiments from a JSON spec."
    )
    parser.add_argument("--spec", required=True, help="Path to batch spec JSON")
    parser.add_argument("--output", help="Output path for the aggregated batch packet JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    spec_path = Path(args.spec).expanduser().resolve()
    packet = run_batch_from_spec(spec_path)
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (
            Path(packet["sourceSpec"]).parent / "stateful-continuation-batch-packet.json"
        ).resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Stateful continuation batch:"
        f" runs={packet['runCount']}"
        f" maxTransportToPhenotypeRatio={packet['maxTransportToPhenotypeRatio']:.6f}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
