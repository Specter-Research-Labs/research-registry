from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

APPLE_REFERENCE_UNIX = 978307200.0


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise SystemExit(f"{path}: expected a JSON array of objects")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()


def _ref_now() -> float:
    return time.time() - APPLE_REFERENCE_UNIX


def _candidate_uuid(candidate: dict[str, Any]) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        "|".join(
            [
                str(candidate["candidateId"]),
                str(candidate["sourceRunDir"]),
                str(candidate["sourceIndex"]),
                str(candidate["sourceSeed"]),
            ]
        ),
    )


def _candidate_name(candidate: dict[str, Any]) -> str:
    return (
        f"{candidate['specimen']}-imgep-{candidate['scale']}"
        f"-{int(candidate['sourceSeed']):04d}"
    )


def _candidate_base(
    *,
    config: dict[str, Any],
    source_row: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(json.dumps(config))
    payload["params"] = {
        "mode": "explicit",
        "seed": None,
        "ranges": None,
        "r": source_row["params"]["r"],
        "b": source_row["params"]["b"],
        "w": source_row["params"]["w"],
        "a": source_row["params"]["a"],
        "m": source_row["params"]["m"],
        "s": source_row["params"]["s"],
        "h": source_row["params"]["h"],
        "R": source_row["params"]["R"],
    }
    init = dict(payload.get("init", {}))
    init["seed"] = int(source_row["init_seed"])
    payload["init"] = init
    return payload


def _candidate_search(
    *,
    search: dict[str, Any],
    source_row: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(json.dumps(search))
    payload["seed_start"] = int(source_row["seed"])
    payload["count"] = 1
    payload["batch_size"] = 1
    payload["top_k"] = 1
    return payload


def _config_hash(base: dict[str, Any], search: dict[str, Any]) -> str:
    data = json.dumps({"base": base, "search": search}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(data.encode("utf-8")).hexdigest()[:12]


def _phenotype(config: dict[str, Any], init_seed: int) -> dict[str, Any]:
    init = config.get("init")
    if not isinstance(init, dict):
        raise SystemExit("config is missing init object")
    phenotype: dict[str, Any] = {"seed": init_seed}
    for key in ("patches", "a_uniform", "p_uniform", "state_patch", "p_state_patch"):
        if key in init:
            phenotype[key] = init[key]
    return phenotype


def build_imgep_hotspot_export_packet(
    *,
    report_path: Path,
    output_root: Path,
    owner_id: str,
    run_id: str,
) -> dict[str, Any]:
    report = _read_json(report_path)
    candidates = report.get("selectedCandidates")
    if not isinstance(candidates, list) or any(not isinstance(row, dict) for row in candidates):
        raise SystemExit("report is missing selectedCandidates[]")

    export_root = output_root / "exports"
    export_rows: list[dict[str, Any]] = []
    packet_candidates: list[dict[str, Any]] = []
    exported_at = _ref_now()

    for candidate in candidates:
        source_run_dir = Path(str(candidate["sourceRunDir"])).expanduser().resolve()
        source_index = int(candidate["sourceIndex"])
        top_rows = _read_json_array(source_run_dir / "top.json")
        source_row = top_rows[source_index]
        config = _read_json(Path(str(candidate["sourceConfigPath"])).expanduser().resolve())
        search = _read_json(Path(str(candidate["sourceSearchPath"])).expanduser().resolve())
        base = _candidate_base(config=config, source_row=source_row)
        replay_search = _candidate_search(search=search, source_row=source_row)
        config_hash = _config_hash(base, replay_search)
        creature_id = _candidate_uuid(candidate)
        name = _candidate_name(candidate)
        bundle_dir = export_root / f"{_sanitize(name)}-{str(creature_id).split('-')[0].upper()}"
        base_path = bundle_dir / "base.json"
        search_path = bundle_dir / "search.json"
        meta_path = bundle_dir / "meta.json"
        _write_json(base_path, base)
        _write_json(search_path, replay_search)
        creature = {
            "id": str(creature_id),
            "name": name,
            "ownerId": owner_id,
            "genotype": source_row["params"],
            "phenotype": _phenotype(config, int(source_row["init_seed"])),
            "initialConditionFamily": source_row["initial_condition_family"],
            "descriptorBundle": source_row["descriptor_bundle"],
            "metrics": source_row["metrics"],
            "score": source_row.get("score"),
            "scoreWeights": source_row.get("score_weights"),
            "configHash": config_hash,
            "timestamp": exported_at,
        }
        meta = {
            "bundleKind": "strict_replay_bundle_v1",
            "creature": creature,
            "exportedAt": exported_at,
            "filtersPassed": bool(source_row.get("filters_passed")),
            "reason": "hotspot_replay_candidate",
            "runId": run_id,
            "score": source_row.get("score"),
        }
        _write_json(meta_path, meta)
        export_record = {
            "baseConfigPath": str(base_path),
            "bundleKind": "strict_replay_bundle_v1",
            "creatureId": str(creature_id),
            "exportDir": str(bundle_dir),
            "exportedAt": exported_at,
            "filtersPassed": bool(source_row.get("filters_passed")),
            "name": name,
            "ownerId": owner_id,
            "reason": "hotspot_replay_candidate",
            "runId": run_id,
            "score": source_row.get("score"),
            "searchConfigPath": str(search_path),
        }
        export_rows.append(export_record)
        packet_candidates.append(
            {
                "candidateId": str(candidate["candidateId"]),
                "name": name,
                "controlGroup": candidate["controlGroup"],
                "scale": candidate["scale"],
                "sourceRunDir": str(source_run_dir),
                "sourceIndex": source_index,
                "exportDir": str(bundle_dir),
            }
        )

    index_path = export_root / "index.jsonl"
    _write_jsonl(index_path, export_rows)
    packet = {
        "version": 1,
        "packetKind": "imgep_hotspot_export_packet_v1",
        "sourceReport": str(report_path),
        "runId": run_id,
        "ownerId": owner_id,
        "exportRoot": str(export_root),
        "exportIndexPath": str(index_path),
        "exportCount": len(packet_candidates),
        "candidates": packet_candidates,
    }
    _write_json(output_root / "imgep-hotspot-export-packet.json", packet)
    return packet


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize strict replay bundles from selected IMGEP hotspot candidates."
    )
    parser.add_argument("--report", required=True, help="Path to imgep-hotspot-report.json")
    parser.add_argument("--output-root", required=True, help="Output directory for replay bundles")
    parser.add_argument(
        "--owner-id",
        default="imgep-hotspot-export",
        help="ownerId to embed in generated SavedCreature metadata",
    )
    parser.add_argument(
        "--run-id",
        default="imgep-hotspot-export",
        help="runId to embed in generated export metadata",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet = build_imgep_hotspot_export_packet(
        report_path=Path(args.report).expanduser().resolve(),
        output_root=Path(args.output_root).expanduser().resolve(),
        owner_id=args.owner_id,
        run_id=args.run_id,
    )
    print(
        "IMGEP hotspot export:"
        f" exported={packet['exportCount']}"
        f" index={packet['exportIndexPath']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
