from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

RUNTIME_CAPABILITIES = ["archive", "topology", "warehouse_ingest"]
LOCAL_PROJECTION_OWNER = "local"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _optional_json(value: Any) -> str | None:
    if value is None:
        return None
    if value == {}:
        return None
    return _json(value)


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _config_hash(config_path: Path, search_path: Path) -> str:
    digest = hashlib.sha256()
    for label, path in (("config", config_path), ("search", search_path)):
        digest.update(label.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()[:12]


def _deterministic_uuid(stable_key: str) -> str:
    digest = bytearray(hashlib.sha256(stable_key.encode("utf-8")).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x50
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(digest))).upper()


def _iter_jsonl(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected a JSON object")
            yield row


def _metric(metrics: dict[str, Any], key: str) -> Any:
    value = metrics.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    return None


def _initial_condition(config: dict[str, Any], init_seed: int) -> dict[str, Any] | None:
    init = config.get("init")
    if not isinstance(init, dict):
        return None
    return {
        "seed": init_seed,
        "patches": init.get("patches"),
        "a_uniform": init.get("a_uniform"),
        "p_uniform": init.get("p_uniform"),
        "state_patch": init.get("state_patch"),
        "p_state_patch": init.get("p_state_patch"),
    }


def _kernel_count(config: dict[str, Any]) -> int | None:
    connectivity = config.get("connectivity")
    if not isinstance(connectivity, list):
        return None
    total = 0
    for row in connectivity:
        if not isinstance(row, list):
            return None
        for value in row:
            if not isinstance(value, int | float):
                return None
            total += int(value)
    return total


def _grid_label(config: dict[str, Any]) -> str:
    grid = config.get("grid")
    if not isinstance(grid, dict):
        return "unknown-grid"
    sx = grid.get("sx")
    sy = grid.get("sy")
    if sx == sy and isinstance(sx, int):
        return str(sx)
    if isinstance(sx, int) and isinstance(sy, int):
        return f"{sx}x{sy}"
    return "unknown-grid"


def _run_profile(config: dict[str, Any]) -> str:
    channels = config.get("channels")
    kernels = _kernel_count(config)
    grid = _grid_label(config)
    channel_label = f"{channels}C" if isinstance(channels, int) else "unknownC"
    kernel_label = f"{kernels}K" if isinstance(kernels, int) else "unknownK"
    return f"FL-{channel_label}{kernel_label}-motion-{grid}"


def _creature_name(config: dict[str, Any], seed: int) -> str:
    return f"{_run_profile(config).lower()}-{seed}"


def _manifest(
    *,
    row: dict[str, Any],
    run_id: str,
    result_id: str,
    specimen_id: str,
    creature_id: str,
    config_hash: str,
    source_mode: str,
    source_algorithm: str,
    recorded_at: str,
    initial_condition: dict[str, Any] | None,
    research_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": 1,
        "specimenID": specimen_id,
        "creatureID": creature_id,
        "runID": run_id,
        "campaignID": None,
        "sourceKind": "result",
        "sourceMode": source_mode,
        "sourceAlgorithm": source_algorithm,
        "runtimeFamily": "flow_lenia",
        "runtimeCapabilities": RUNTIME_CAPABILITIES,
        "configHash": config_hash,
        "recordedAt": recorded_at,
        "initialConditionFamily": row.get("initial_condition_family"),
        "taxonomy": {
            "familyID": row.get("initial_condition_family"),
            "genusID": None,
            "speciesID": None,
            "confidence": None,
            "method": None,
            "version": None,
        },
        "traitLabels": None,
        "replay": {
            "bundleKind": None,
            "exportDir": None,
            "baseConfigPath": None,
            "searchConfigPath": None,
            "payloadPath": None,
        },
        "snapshots": {
            "genotype": row.get("params"),
            "initialCondition": initial_condition,
            "metrics": row.get("metrics"),
            "descriptorBundle": row.get("descriptor_bundle"),
            "morphometrics": None,
        },
        "researchMetadata": {
            **research_metadata,
            "resultID": result_id,
        },
    }


def _result_values(row: dict[str, Any], *, run_id: str) -> tuple[Any, ...]:
    seed = int(row["seed"])
    init_seed = int(row.get("init_seed", seed))
    result_id = f"{run_id}|overall|{seed}"
    return (
        result_id,
        run_id,
        None,
        seed,
        init_seed,
        row.get("score"),
        int(bool(row.get("filters_passed"))),
        str(row.get("backend") or ""),
        _json(row.get("implementation") or {}),
        _optional_json(row.get("score_weights")),
        _json(row.get("metrics") or {}),
        _json(row.get("params") or {}),
        _optional_json(row.get("sweep")),
        row.get("worker_id"),
    )


def _projection_values(
    row: dict[str, Any],
    *,
    run_id: str,
    run_dir: Path,
    config_hash: str,
    source_mode: str,
    source_algorithm: str,
    recorded_at: str,
    config: dict[str, Any],
    research_metadata: dict[str, Any],
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    seed = int(row["seed"])
    init_seed = int(row.get("init_seed", seed))
    result_id = f"{run_id}|overall|{seed}"
    specimen_id = f"result:{result_id}"
    creature_id = _deterministic_uuid(f"{run_id}|overall|{seed}|{init_seed}")
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    descriptor_bundle = row.get("descriptor_bundle")
    if not isinstance(descriptor_bundle, dict):
        raise ValueError(f"{run_dir}/results.jsonl seed {seed}: missing descriptor_bundle")
    genotype = descriptor_bundle.get("genotype")
    terminal = descriptor_bundle.get("terminal")
    trajectory = descriptor_bundle.get("trajectory")
    if not isinstance(genotype, dict) or not isinstance(terminal, dict):
        raise ValueError(
            f"{run_dir}/results.jsonl seed {seed}: "
            "descriptor_bundle lacks genotype/terminal"
        )
    descriptor_version = int(descriptor_bundle.get("descriptorVersion", 1))
    symmetry_policy = str(
        descriptor_bundle.get("symmetryPolicy") or "translation_kernel_permutation_v1"
    )
    initial_condition = _initial_condition(config, init_seed)
    manifest = _manifest(
        row=row,
        run_id=run_id,
        result_id=result_id,
        specimen_id=specimen_id,
        creature_id=creature_id,
        config_hash=config_hash,
        source_mode=source_mode,
        source_algorithm=source_algorithm,
        recorded_at=recorded_at,
        initial_condition=initial_condition,
        research_metadata=research_metadata,
    )
    runtime_capabilities_json = _json(RUNTIME_CAPABILITIES)
    manifest_json = _json(manifest)
    initial_condition_family = row.get("initial_condition_family")
    score_weights_json = _optional_json(row.get("score_weights"))
    metrics_json = _json(metrics)
    params_json = _json(row.get("params") or {})
    sweep_json = _optional_json(row.get("sweep"))

    specimen_values = (
        specimen_id,
        specimen_id,
        creature_id,
        run_id,
        None,
        "result",
        recorded_at,
        seed,
        init_seed,
        source_mode,
        source_algorithm,
        config_hash,
        initial_condition_family,
        descriptor_version,
        symmetry_policy,
        _json(genotype),
        _json(terminal),
        _optional_json(trajectory),
        None,
        None,
        _json(
            {
                "sourceKind": "result",
                "sourceRef": specimen_id,
                "sourcePath": str((run_dir / "results.jsonl").resolve()),
            }
        ),
        "flow_lenia",
        runtime_capabilities_json,
        manifest_json,
    )
    creature_values = (
        creature_id,
        _creature_name(config, seed),
        LOCAL_PROJECTION_OWNER,
        run_id,
        None,
        recorded_at,
        init_seed,
        row.get("score"),
        int(bool(metrics.get("is_stable"))),
        _metric(metrics, "mass_mean"),
        _metric(metrics, "mass_std"),
        _metric(metrics, "mass_min"),
        _metric(metrics, "mass_max"),
        _metric(metrics, "occupancy_mean"),
        _metric(metrics, "variance_mean"),
        _metric(metrics, "energy_mean"),
        _metric(metrics, "speed_mean"),
        _metric(metrics, "path_length"),
        _metric(metrics, "displacement"),
        _metric(metrics, "gyration"),
        _metric(metrics, "center_velocity"),
        _metric(metrics, "velocity_x"),
        _metric(metrics, "velocity_y"),
        _metric(metrics, "heading_rad"),
        None,
        None,
        None,
        None,
        None,
        None,
        initial_condition_family,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        config_hash,
        source_mode,
        source_algorithm,
        _json(research_metadata),
        "flow_lenia",
        runtime_capabilities_json,
        manifest_json,
        specimen_id,
        None,
        score_weights_json,
        params_json,
        _optional_json(initial_condition),
        sweep_json,
        metrics_json,
    )
    return specimen_values, creature_values


def _ensure_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    run_dir: Path,
    config_hash: str,
    source_mode: str,
    source_algorithm: str,
    recorded_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO runs (
            run_id, run_name, host_id, output_root, run_dir, indexed_at,
            config_hash, source_mode, source_algorithm
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            run_name = excluded.run_name,
            host_id = COALESCE(excluded.host_id, runs.host_id),
            output_root = excluded.output_root,
            run_dir = excluded.run_dir,
            indexed_at = excluded.indexed_at,
            config_hash = excluded.config_hash,
            source_mode = excluded.source_mode,
            source_algorithm = excluded.source_algorithm
        """,
        (
            run_id,
            run_id,
            LOCAL_PROJECTION_OWNER,
            str(run_dir.parent),
            str(run_dir),
            recorded_at,
            config_hash,
            source_mode,
            source_algorithm,
        ),
    )


def _flush(
    connection: sqlite3.Connection,
    *,
    results: list[tuple[Any, ...]],
    specimens: list[tuple[Any, ...]],
    creatures: list[tuple[Any, ...]],
) -> None:
    connection.executemany(
        """
        INSERT OR REPLACE INTO results (
            id, run_id, campaign_id, seed, init_seed, score, filters_passed,
            backend, implementation_json, score_weights_json, metrics_json,
            params_json, sweep_json, worker_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        results,
    )
    connection.executemany(
        """
        INSERT INTO specimens (
            id, result_id, creature_id, run_id, campaign_id, source_kind, recorded_at,
            seed, init_seed, source_mode, source_algorithm, config_hash,
            initial_condition_family, descriptor_version, symmetry_policy,
            genotype_descriptor_json, terminal_descriptor_json, trajectory_descriptor_json,
            activity_path, fingerprint_path, provenance_json, runtime_family,
            runtime_capabilities_json, specimen_manifest_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            result_id = excluded.result_id,
            creature_id = excluded.creature_id,
            run_id = excluded.run_id,
            campaign_id = excluded.campaign_id,
            source_kind = excluded.source_kind,
            recorded_at = excluded.recorded_at,
            seed = excluded.seed,
            init_seed = excluded.init_seed,
            source_mode = excluded.source_mode,
            source_algorithm = excluded.source_algorithm,
            config_hash = excluded.config_hash,
            initial_condition_family = excluded.initial_condition_family,
            descriptor_version = excluded.descriptor_version,
            symmetry_policy = excluded.symmetry_policy,
            genotype_descriptor_json = excluded.genotype_descriptor_json,
            terminal_descriptor_json = excluded.terminal_descriptor_json,
            trajectory_descriptor_json = excluded.trajectory_descriptor_json,
            activity_path = excluded.activity_path,
            fingerprint_path = excluded.fingerprint_path,
            provenance_json = excluded.provenance_json,
            runtime_family = excluded.runtime_family,
            runtime_capabilities_json = excluded.runtime_capabilities_json,
            specimen_manifest_json = excluded.specimen_manifest_json
        """,
        specimens,
    )
    connection.executemany(
        """
        INSERT INTO creatures (
            id, name, owner_id, run_id, campaign_id, recorded_at, init_seed, score,
            is_stable, mass_mean, mass_std, mass_min, mass_max, occupancy_mean,
            variance_mean, energy_mean, speed_mean, path_length, displacement,
            gyration, center_velocity, velocity_x, velocity_y, heading_rad,
            complexity_mean, complexity_target_score, activity_eac_mean,
            activity_ean_mean, activity_diversity_mean, activity_species_mean,
            taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id,
            taxonomy_confidence, taxonomy_method, taxonomy_version,
            morphometrics_json, morphometrics_method, morphometrics_version,
            config_hash, source_mode, source_algorithm, research_metadata_json,
            runtime_family, runtime_capabilities_json, specimen_manifest_json,
            canonical_specimen_id, trait_labels_json, score_weights_json,
            genotype_json, initial_condition_json, sweep_json, metrics_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            owner_id = excluded.owner_id,
            run_id = excluded.run_id,
            campaign_id = excluded.campaign_id,
            recorded_at = excluded.recorded_at,
            init_seed = excluded.init_seed,
            score = excluded.score,
            is_stable = excluded.is_stable,
            mass_mean = excluded.mass_mean,
            mass_std = excluded.mass_std,
            mass_min = excluded.mass_min,
            mass_max = excluded.mass_max,
            occupancy_mean = excluded.occupancy_mean,
            variance_mean = excluded.variance_mean,
            energy_mean = excluded.energy_mean,
            speed_mean = excluded.speed_mean,
            path_length = excluded.path_length,
            displacement = excluded.displacement,
            gyration = excluded.gyration,
            center_velocity = excluded.center_velocity,
            velocity_x = excluded.velocity_x,
            velocity_y = excluded.velocity_y,
            heading_rad = excluded.heading_rad,
            taxonomy_family_id = excluded.taxonomy_family_id,
            config_hash = excluded.config_hash,
            source_mode = excluded.source_mode,
            source_algorithm = excluded.source_algorithm,
            research_metadata_json = excluded.research_metadata_json,
            runtime_family = excluded.runtime_family,
            runtime_capabilities_json = excluded.runtime_capabilities_json,
            specimen_manifest_json = excluded.specimen_manifest_json,
            canonical_specimen_id = excluded.canonical_specimen_id,
            score_weights_json = excluded.score_weights_json,
            genotype_json = excluded.genotype_json,
            initial_condition_json = excluded.initial_condition_json,
            sweep_json = excluded.sweep_json,
            metrics_json = excluded.metrics_json
        """,
        creatures,
    )


def promote_results_jsonl(
    *,
    compendium_path: Path,
    run_dir: Path,
    run_id: str,
    source_mode: str = "atlas-random",
    source_algorithm: str = "fl-2c20-motion-scorev2",
    batch_size: int = 2048,
) -> dict[str, Any]:
    results_path = run_dir / "results.jsonl"
    config_path = run_dir / "config.json"
    search_path = run_dir / "search.json"
    if not results_path.exists():
        raise FileNotFoundError(results_path)
    config = _read_json_object(config_path)
    search = _read_json_object(search_path)
    config_hash = _config_hash(config_path, search_path)
    recorded_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    research_metadata = {
        "morphospace_ready": True,
        "canonical_export_available": False,
        "local_results_source": "results_jsonl_promotion_v1",
        "local_results_run_dir": str(run_dir),
        "runProfile": _run_profile(config),
        "kernelCount": _kernel_count(config),
        "grid": config.get("grid"),
        "channels": config.get("channels"),
        "connectivity": config.get("connectivity"),
        "flow": config.get("flow"),
        "implementation": config.get("implementation"),
        "reintegration": config.get("reintegration"),
        "search": {
            "count": search.get("count"),
            "seed_start": search.get("seed_start"),
            "steps": search.get("steps"),
            "record_interval": search.get("record_interval"),
            "score_weights": search.get("score_weights"),
        },
        "food": config.get("food") is not None,
        "walls": config.get("walls") is not None,
        "chemotaxis": config.get("chemotaxis") is not None,
    }

    connection = sqlite3.connect(compendium_path)
    try:
        connection.execute("PRAGMA busy_timeout = 60000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        _ensure_run(
            connection,
            run_id=run_id,
            run_dir=run_dir,
            config_hash=config_hash,
            source_mode=source_mode,
            source_algorithm=source_algorithm,
            recorded_at=recorded_at,
        )
        connection.commit()

        result_values: list[tuple[Any, ...]] = []
        specimen_values: list[tuple[Any, ...]] = []
        creature_values: list[tuple[Any, ...]] = []
        seen_result_ids: set[str] = set()
        promoted = 0
        for row in _iter_jsonl(results_path):
            seed = int(row["seed"])
            result_id = f"{run_id}|overall|{seed}"
            if result_id in seen_result_ids:
                continue
            seen_result_ids.add(result_id)
            result_values.append(_result_values(row, run_id=run_id))
            specimen, creature = _projection_values(
                row,
                run_id=run_id,
                run_dir=run_dir,
                config_hash=config_hash,
                source_mode=source_mode,
                source_algorithm=source_algorithm,
                recorded_at=recorded_at,
                config=config,
                research_metadata=research_metadata,
            )
            specimen_values.append(specimen)
            creature_values.append(creature)
            if len(result_values) >= batch_size:
                with connection:
                    _flush(
                        connection,
                        results=result_values,
                        specimens=specimen_values,
                        creatures=creature_values,
                    )
                promoted += len(result_values)
                result_values.clear()
                specimen_values.clear()
                creature_values.clear()
        if result_values:
            with connection:
                _flush(
                    connection,
                    results=result_values,
                    specimens=specimen_values,
                    creatures=creature_values,
                )
            promoted += len(result_values)

        counts = {
            name: connection.execute(
                f"SELECT COUNT(*) FROM {name} WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            for name in ("results", "specimens", "creatures")
        }
        return {
            "compendiumPath": str(compendium_path),
            "runDir": str(run_dir),
            "runId": run_id,
            "configHash": config_hash,
            "sourceMode": source_mode,
            "sourceAlgorithm": source_algorithm,
            "promotedRows": promoted,
            "counts": counts,
        }
    finally:
        connection.close()
