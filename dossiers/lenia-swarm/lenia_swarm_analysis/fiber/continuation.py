from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decode_fingerprint_u8(value: Any) -> np.ndarray:
    if isinstance(value, list):
        return np.asarray([float(item) / 255.0 for item in value], dtype=np.float64)
    if isinstance(value, str):
        raw = np.frombuffer(base64.b64decode(value), dtype=np.uint8)
        return raw.astype(np.float64) / 255.0
    raise SystemExit("fingerprintU8 must be a list or base64 string")


def _decode_state_patch(state_patch: dict[str, Any]) -> np.ndarray:
    encoding = state_patch.get("encoding")
    data = state_patch.get("data")
    if encoding != "f32le" or not isinstance(data, str):
        raise SystemExit("state patch must use f32le base64 encoding")
    raw = base64.b64decode(data)
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def _l2(lhs: np.ndarray, rhs: np.ndarray) -> float:
    return float(np.linalg.norm(lhs - rhs) / max(1, lhs.size))


def build_open_path_loop_spec(
    *,
    coordinate: str,
    values: list[float],
    name: str | None,
) -> dict[str, Any]:
    if len(values) < 2:
        raise SystemExit("stateful continuation requires at least two coordinate values")
    return build_loop_spec(
        coordinates=[coordinate],
        vertices=[[float(value)] for value in values],
        name=name or f"stateful-{coordinate}",
        closed=False,
        samples_per_segment=1,
    )


def build_loop_spec(
    *,
    coordinates: list[str],
    vertices: list[list[float]],
    name: str,
    closed: bool,
    samples_per_segment: int,
) -> dict[str, Any]:
    if not coordinates:
        raise SystemExit("stateful continuation requires at least one coordinate")
    if len(vertices) < 2:
        raise SystemExit("stateful continuation requires at least two vertices")
    if samples_per_segment < 1:
        raise SystemExit("samples_per_segment must be at least 1")
    coordinate_count = len(coordinates)
    normalized_vertices: list[list[float]] = []
    for index, vertex in enumerate(vertices):
        if len(vertex) != coordinate_count:
            raise SystemExit(
                f"vertex {index} width {len(vertex)} does not match coordinates {coordinate_count}"
            )
        normalized_vertices.append([float(value) for value in vertex])
    return {
        "version": 1,
        "name": name,
        "closed": bool(closed),
        "coordinates": coordinates,
        "vertices": normalized_vertices,
        "samples_per_segment": int(samples_per_segment),
    }


def run_stateful_continuation(
    *,
    cli_binary: Path,
    bundle: Path,
    coordinate: str | None,
    values: list[float] | None,
    output: Path,
    name: str | None,
    run_id: str | None,
    db: Path | None,
    export_enabled: bool,
    loop_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if loop_spec is None:
        if coordinate is None or values is None:
            raise SystemExit(
                "stateful continuation needs coordinate/values or an explicit loop spec"
            )
        loop_spec = build_open_path_loop_spec(
            coordinate=coordinate,
            values=values,
            name=name,
        )
    loop_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="lenia-stateful-loop-",
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(loop_spec, handle, indent=2, sort_keys=True)
            handle.write("\n")
            loop_path = Path(handle.name)

        command = [
            str(cli_binary),
            "intervene",
            "holonomy",
            "--bundle",
            str(bundle),
            "--loop",
            str(loop_path),
            "--output",
            str(output),
        ]
        if export_enabled:
            command.append("--export-enabled")
        if db is not None:
            command.extend(["--db", str(db)])
        if run_id:
            command.extend(["--run-id", run_id])

        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise SystemExit(
                "stateful continuation holonomy run failed\n"
                f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
            )

        holonomy_manifest_path = output / "holonomy-manifest.json"
        packet = summarize_stateful_continuation(holonomy_manifest_path)
        packet["command"] = command
        packet["stdoutTail"] = completed.stdout[-4000:]
        packet["stderrTail"] = completed.stderr[-4000:]
        packet_path = output / "stateful-continuation-packet.json"
        _write_json(packet_path, packet)
        return {
            "packet": packet,
            "packetPath": packet_path,
            "command": command,
        }
    finally:
        if loop_path is not None and loop_path.exists():
            loop_path.unlink()


def _step_summary(step_manifest_path: Path) -> dict[str, Any]:
    step_manifest = _read_json(step_manifest_path)
    results_path = Path(step_manifest["results_path"]).expanduser().resolve()
    terminal_state_path = step_manifest_path.parent / "terminal-state.json"
    result_row = json.loads(results_path.read_text(encoding="utf-8").splitlines()[0])
    terminal = result_row["descriptor_bundle"]["terminal"]
    fingerprint = _decode_fingerprint_u8(terminal["fingerprintU8"])
    state = _decode_state_patch(_read_json(terminal_state_path))
    return {
        "sequenceIndex": int(step_manifest["sequence_index"]),
        "segmentIndex": int(step_manifest["segment_index"]),
        "segmentT": float(step_manifest["segment_t"]),
        "coordinateValues": dict(step_manifest["coordinate_values"]),
        "campaignDir": str(step_manifest_path.parent),
        "fingerprint": fingerprint,
        "state": state,
    }


def summarize_stateful_continuation(holonomy_manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(holonomy_manifest_path)
    summary_path = Path(manifest["summary_path"]).expanduser().resolve()
    holonomy_summary = _read_json(summary_path)
    step_rows = [
        _step_summary(Path(path).expanduser().resolve())
        for path in manifest["step_manifest_paths"]
    ]
    if not step_rows:
        raise SystemExit(f"{holonomy_manifest_path}: no step manifests found")

    first = step_rows[0]
    previous = None
    rows: list[dict[str, Any]] = []
    for row in step_rows:
        phenotype_from_start = _l2(row["fingerprint"], first["fingerprint"])
        state_from_start = _l2(row["state"], first["state"])
        phenotype_step = None
        state_step = None
        if previous is not None:
            phenotype_step = _l2(row["fingerprint"], previous["fingerprint"])
            state_step = _l2(row["state"], previous["state"])
        rows.append(
            {
                "sequenceIndex": row["sequenceIndex"],
                "segmentIndex": row["segmentIndex"],
                "segmentT": row["segmentT"],
                "coordinateValues": row["coordinateValues"],
                "campaignDir": row["campaignDir"],
                "phenotypeDistanceFromStart": phenotype_from_start,
                "transportedStateDistanceFromStart": state_from_start,
                "phenotypeStepDelta": phenotype_step,
                "transportedStateStepDelta": state_step,
            }
        )
        previous = row

    last = step_rows[-1]
    return {
        "version": 1,
        "packetKind": "stateful_continuation_packet_v1",
        "runId": str(manifest["run_id"]),
        "bundlePath": str(manifest["bundle_path"]),
        "loopPath": str(manifest["loop_path"]),
        "coordinatePaths": list(manifest["coordinate_paths"]),
        "pointCount": len(rows),
        "campaignCount": int(holonomy_summary["campaign_count"]),
        "configTopologyHash": str(manifest["config_topology_hash"]),
        "endpointPhenotypeDistance": _l2(last["fingerprint"], first["fingerprint"]),
        "endpointTransportedStateDistance": _l2(last["state"], first["state"]),
        "maxPhenotypeDistanceFromStart": max(row["phenotypeDistanceFromStart"] for row in rows),
        "maxTransportedStateDistanceFromStart": max(
            row["transportedStateDistanceFromStart"] for row in rows
        ),
        "maxPhenotypeStepDelta": max(
            (row["phenotypeStepDelta"] for row in rows if row["phenotypeStepDelta"] is not None),
            default=0.0,
        ),
        "maxTransportedStateStepDelta": max(
            (
                row["transportedStateStepDelta"]
                for row in rows
                if row["transportedStateStepDelta"] is not None
            ),
            default=0.0,
        ),
        "rows": rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Flow-native stateful continuation by wrapping holonomy on an open path."
    )
    parser.add_argument("--cli-binary", required=True, help="Path to LeniaCLI binary")
    parser.add_argument("--bundle", required=True, help="Path to strict Flow replay bundle")
    parser.add_argument("--coordinate", required=True, help="Single parameter path, e.g. m.0")
    parser.add_argument(
        "--values",
        required=True,
        help="Comma-separated coordinate values visited in order along the continuation path",
    )
    parser.add_argument("--name", help="Optional continuation name")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--run-id", help="Optional explicit run id")
    parser.add_argument("--db", help="Optional compendium SQLite path for holonomy indexing")
    parser.add_argument(
        "--export-enabled",
        action="store_true",
        help="Write replay export bundles for each continuation step",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cli_binary = Path(args.cli_binary).expanduser().resolve()
    bundle = Path(args.bundle).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    values = [float(item.strip()) for item in args.values.split(",") if item.strip()]
    result = run_stateful_continuation(
        cli_binary=cli_binary,
        bundle=bundle,
        coordinate=args.coordinate,
        values=values,
        output=output,
        name=args.name,
        run_id=args.run_id,
        db=Path(args.db).expanduser().resolve() if args.db else None,
        export_enabled=args.export_enabled,
    )
    packet = result["packet"]
    packet_path = result["packetPath"]
    print(
        "Stateful continuation:"
        f" points={packet['pointCount']}"
        f" endpointPhenotypeDistance={packet['endpointPhenotypeDistance']:.6f}"
        f" endpointTransportedStateDistance={packet['endpointTransportedStateDistance']:.6f}"
        f" output={packet_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
