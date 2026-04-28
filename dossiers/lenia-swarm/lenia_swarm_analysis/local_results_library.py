from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from lenia_swarm_analysis._io import read_json, read_json_array, write_jsonl


def _apple_reference_seconds(now: datetime) -> float:
    reference = datetime(2001, 1, 1, tzinfo=UTC)
    return (now - reference).total_seconds()


def _config_hash(config_path: Path, search_path: Path) -> str:
    components = sorted(
        [
            ("config", config_path.read_bytes()),
            ("search", search_path.read_bytes()),
        ],
        key=lambda item: item[0],
    )
    digest = hashlib.sha256()
    for label, payload in components:
        digest.update(label.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(payload)
        digest.update(b"\x00")
    return digest.hexdigest()[:12]


def _deterministic_uuid(stable_key: str) -> str:
    digest = bytearray(hashlib.sha256(stable_key.encode("utf-8")).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x50
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(digest)))


def _creature_name(specimen: str, index: int, fingerprint_hash: str | None) -> str:
    suffix = fingerprint_hash or f"{index:04d}"
    return f"{specimen}-hotspot-{index:04d}-{suffix}"


def _phenotype_from_run_config(run_config: dict[str, Any], init_seed: int) -> dict[str, Any]:
    init = run_config.get("init")
    if not isinstance(init, dict):
        raise SystemExit("run config is missing init block")
    return {
        "seed": init_seed,
        "patches": init["patches"],
        "a_uniform": init["a_uniform"],
        "p_uniform": init.get("p_uniform"),
        "state_patch": init.get("state_patch"),
        "p_state_patch": init.get("p_state_patch"),
    }


def _research_metadata(run_dir: Path, specimen: str) -> dict[str, Any]:
    return {
        "local_results_source": "top_json_replay_adapter_v1",
        "local_results_run_dir": str(run_dir),
        "morphospace_ready": True,
        "hotspot_specimen": specimen,
    }


def _runtime_family(source_mode: str) -> str:
    normalized = source_mode.strip().lower()
    if normalized == "qd-2024":
        return "qd24_paper"
    if normalized == "sensorimotor-2024":
        return "sensorimotor24_paper"
    return "flow_lenia"


def _runtime_capabilities(research_metadata: dict[str, Any]) -> list[str]:
    capabilities = {"archive", "warehouse_ingest"}
    if bool(research_metadata.get("morphospace_ready")):
        capabilities.add("topology")
    return sorted(capabilities)


def _entry_from_row(
    *,
    row: dict[str, Any],
    run_id: str,
    config_hash: str,
    run_config: dict[str, Any],
    owner_id: str,
    source_mode: str,
    source_algorithm: str,
    specimen: str,
    index: int,
    recorded_at: float,
    run_dir: Path,
) -> dict[str, Any]:
    descriptor_bundle = row.get("descriptor_bundle")
    metrics = row.get("metrics")
    params = row.get("params")
    init_seed = row.get("init_seed")
    if not isinstance(descriptor_bundle, dict):
        raise SystemExit("result row is missing descriptor_bundle")
    if not isinstance(metrics, dict):
        raise SystemExit("result row is missing metrics")
    if not isinstance(params, dict):
        raise SystemExit("result row is missing params")
    if not isinstance(init_seed, int):
        raise SystemExit("result row is missing init_seed")

    genotype = descriptor_bundle.get("genotype")
    terminal = descriptor_bundle.get("terminal")
    genotype_hash = genotype.get("hash12") if isinstance(genotype, dict) else None
    fingerprint_hash = terminal.get("fingerprintHash12") if isinstance(terminal, dict) else None
    stable_key = (
        f"{run_id}|{specimen}|{index}|{init_seed}|{genotype_hash or 'nog'}|"
        f"{fingerprint_hash or 'nof'}"
    )
    creature_id = _deterministic_uuid(stable_key)
    score = row.get("score")
    score_weights = row.get("score_weights")
    sweep = row.get("sweep")
    if sweep == {}:
        sweep = None
    if score_weights == {}:
        score_weights = {}
    phenotype = _phenotype_from_run_config(run_config, init_seed)
    research_metadata = _research_metadata(run_dir, specimen)
    runtime_family = _runtime_family(source_mode)
    runtime_capabilities = _runtime_capabilities(research_metadata)
    creature = {
        "id": creature_id,
        "name": _creature_name(
            specimen,
            index,
            fingerprint_hash if isinstance(fingerprint_hash, str) else None,
        ),
        "timestamp": recorded_at,
        "ownerId": owner_id,
        "genotype": params,
        "phenotype": phenotype,
        "initialConditionFamily": row.get("initial_condition_family"),
        "descriptorBundle": descriptor_bundle,
        "metrics": metrics,
        "sweep": sweep,
        "score": score,
        "scoreWeights": score_weights,
        "configHash": config_hash,
    }
    return {
        "creature": creature,
        "campaign_id": None,
        "run_id": run_id,
        "recorded_at": recorded_at,
        "config_hash": config_hash,
        "source_mode": source_mode,
        "source_algorithm": source_algorithm,
        "research_metadata": research_metadata,
        "runtime_family": runtime_family,
        "runtime_capabilities": runtime_capabilities,
        "specimen_manifest": {
            "version": 1,
            "specimenID": creature_id,
            "creatureID": creature_id,
            "runID": run_id,
            "campaignID": None,
            "sourceKind": "library",
            "sourceMode": source_mode,
            "sourceAlgorithm": source_algorithm,
            "runtimeFamily": runtime_family,
            "runtimeCapabilities": runtime_capabilities,
            "configHash": config_hash,
            "recordedAt": recorded_at,
            "initialConditionFamily": row.get("initial_condition_family"),
            "snapshots": {
                "genotype": params,
                "initialCondition": phenotype,
                "metrics": metrics,
                "descriptorBundle": descriptor_bundle,
            },
            "researchMetadata": research_metadata,
        },
    }


def build_library_entries(
    *,
    run_dir: Path,
    run_id: str,
    owner_id: str,
    source_mode: str,
    source_algorithm: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    config_path = run_dir / "config.json"
    search_path = run_dir / "search.json"
    top_path = run_dir / "top.json"
    config = read_json(config_path)
    rows = read_json_array(top_path)
    if limit is not None:
        rows = rows[:limit]
    specimen = run_dir.parent.name
    now = datetime.now(UTC)
    recorded_at = _apple_reference_seconds(now)
    config_hash = _config_hash(config_path, search_path)
    return [
        _entry_from_row(
            row=row,
            run_id=run_id,
            config_hash=config_hash,
            run_config=config,
            owner_id=owner_id,
            source_mode=source_mode,
            source_algorithm=source_algorithm,
            specimen=specimen,
            index=index,
            recorded_at=recorded_at,
            run_dir=run_dir,
        )
        for index, row in enumerate(rows, start=1)
    ]




def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert local/top.json results into a replayable library/index.jsonl."
    )
    parser.add_argument("--run-dir", required=True, help="Local run directory containing top.json")
    parser.add_argument(
        "--run-id",
        required=True,
        help="Synthetic source run_id for the library rows",
    )
    parser.add_argument(
        "--owner-id",
        default="imgep-hotspot",
        help="ownerId for synthesized creatures",
    )
    parser.add_argument(
        "--source-mode",
        default="local-imgep-hotspot",
        help="source_mode for ResearchLibraryEntry",
    )
    parser.add_argument(
        "--source-algorithm",
        default="imgep",
        help="source_algorithm for ResearchLibraryEntry",
    )
    parser.add_argument("--limit", type=int, help="Optional cap on retained rows")
    parser.add_argument("--output", help="Output path, defaults to run-dir/library/index.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (run_dir / "library" / "index.jsonl").resolve()
    )
    entries = build_library_entries(
        run_dir=run_dir,
        run_id=args.run_id,
        owner_id=args.owner_id,
        source_mode=args.source_mode,
        source_algorithm=args.source_algorithm,
        limit=args.limit,
    )
    write_jsonl(output_path, entries)
    print(f"Local results library: entries={len(entries)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
