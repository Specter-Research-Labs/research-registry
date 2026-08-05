from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from lenia_swarm_analysis.morphospace.common_morphology import (
    FEATURE_SPACE_ID as COMMON_FEATURE_SPACE_ID,
)
from lenia_swarm_analysis.morphospace.derive_lenia_features import (
    FEATURE_SPACE_ID as TERMINAL_FEATURE_SPACE_ID,
)
from lenia_swarm_analysis.morphospace.ingest_compendium import ingest_compendium
from lenia_swarm_analysis.morphospace.promote_results import promote_results_jsonl
from lenia_swarm_analysis.morphospace.warehouse import connect_database
from lenia_swarm_analysis.morphospace_cli import refresh_compendium_warehouse


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def _init_compendium(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                run_name TEXT NOT NULL,
                host_id TEXT,
                output_root TEXT,
                run_dir TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                config_hash TEXT,
                source_mode TEXT,
                source_algorithm TEXT
            );
            CREATE TABLE results (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                seed INTEGER NOT NULL,
                init_seed INTEGER NOT NULL,
                score REAL,
                filters_passed INTEGER NOT NULL,
                backend TEXT NOT NULL,
                implementation_json TEXT NOT NULL,
                score_weights_json TEXT,
                metrics_json TEXT NOT NULL,
                params_json TEXT NOT NULL,
                sweep_json TEXT,
                worker_id TEXT
            );
            CREATE TABLE specimens (
                id TEXT PRIMARY KEY,
                result_id TEXT,
                creature_id TEXT,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                source_kind TEXT NOT NULL,
                recorded_at TEXT,
                seed INTEGER,
                init_seed INTEGER,
                source_mode TEXT,
                source_algorithm TEXT,
                config_hash TEXT,
                initial_condition_family TEXT,
                descriptor_version INTEGER NOT NULL,
                symmetry_policy TEXT NOT NULL,
                genotype_descriptor_json TEXT NOT NULL,
                terminal_descriptor_json TEXT NOT NULL,
                trajectory_descriptor_json TEXT,
                activity_path TEXT,
                fingerprint_path TEXT,
                provenance_json TEXT,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT
            );
            CREATE UNIQUE INDEX specimens_result_id
                ON specimens(result_id)
                WHERE result_id IS NOT NULL;
            CREATE UNIQUE INDEX specimens_creature_id
                ON specimens(creature_id)
                WHERE creature_id IS NOT NULL;
            CREATE TABLE creatures (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                campaign_id TEXT,
                recorded_at TEXT NOT NULL,
                init_seed INTEGER,
                score REAL,
                is_stable INTEGER NOT NULL,
                mass_mean REAL,
                mass_std REAL,
                mass_min REAL,
                mass_max REAL,
                occupancy_mean REAL,
                variance_mean REAL,
                energy_mean REAL,
                speed_mean REAL,
                path_length REAL,
                displacement REAL,
                gyration REAL,
                center_velocity REAL,
                velocity_x REAL,
                velocity_y REAL,
                heading_rad REAL,
                complexity_mean REAL,
                complexity_target_score REAL,
                activity_eac_mean REAL,
                activity_ean_mean REAL,
                activity_diversity_mean REAL,
                activity_species_mean REAL,
                taxonomy_family_id TEXT,
                taxonomy_genus_id TEXT,
                taxonomy_species_id TEXT,
                taxonomy_confidence REAL,
                taxonomy_method TEXT,
                taxonomy_version INTEGER,
                morphometrics_json TEXT,
                morphometrics_method TEXT,
                morphometrics_version INTEGER,
                config_hash TEXT,
                source_mode TEXT,
                source_algorithm TEXT,
                research_metadata_json TEXT,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT,
                canonical_specimen_id TEXT,
                trait_labels_json TEXT,
                score_weights_json TEXT,
                genotype_json TEXT,
                initial_condition_json TEXT,
                sweep_json TEXT,
                metrics_json TEXT
            );
            """
        )
    finally:
        connection.close()


def _result(seed: int) -> dict[str, object]:
    return {
        "backend": "metal-full",
        "descriptor_bundle": {
            "descriptorVersion": 2,
            "symmetryPolicy": "translation_kernel_permutation_v1",
            "genotype": {
                "version": 1,
                "kernelCount": 20,
                "vectorLength": 180,
                "vector": [0.1, 0.2, 0.3],
                "hash12": f"genotype{seed}",
                "canonicalizer": "test",
            },
            "terminal": {
                "version": 2,
                "descriptorVersion": 2,
                "borderMode": "torus",
                "normalizationPolicy": "border_aware_com_center_peak_q32_u8_v2",
                "finalMass": 12.0,
                "finalOccupancy": 0.12,
                "finalGyration": 5.0,
                "fingerprintResolution": 32,
                "fingerprintU8": [0, 1, 0, 0] * 256,
                "fingerprintHash12": f"terminal{seed}",
                "angularSymmetry": {"normalizedEntropy": 0.5},
            },
            "trajectory": {
                "version": 1,
                "centerVelocity": 0.2,
                "displacement": 3.0,
                "pathLength": 4.0,
                "pathTortuosity": 1.3333333333333333,
                "movementEfficiency": 0.75,
            },
        },
        "filters": {},
        "filters_passed": True,
        "implementation": {"mode": "flowlenia_2022_paper_equations"},
        "init_seed": seed,
        "initial_condition_family": "initfam:test",
        "metrics": {
            "is_stable": False,
            "mass_mean": 12.0,
            "mass_std": 0.1,
            "mass_min": 11.9,
            "mass_max": 12.1,
            "occupancy_mean": 0.12,
            "variance_mean": 0.03,
            "energy_mean": 0.4,
            "speed_mean": 0.2,
            "path_length": 4.0,
            "displacement": 3.0,
            "gyration": 5.0,
            "center_velocity": 0.2,
            "velocity_x": 0.1,
            "velocity_y": 0.1,
            "heading_rad": 0.5,
        },
        "params": {"R": [10.0], "m": [0.2]},
        "score": 2.5,
        "score_weights": {"displacement": 0.35},
        "seed": seed,
        "sweep": {"seed": seed},
    }


def test_promote_results_jsonl_projects_results_into_canonical_compendium(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "config.json",
        {
            "grid": {"sx": 128, "sy": 128},
            "channels": 2,
            "connectivity": [[5, 5], [5, 5]],
            "flow": {"dt": 0.2, "n": 2, "theta_A": 2},
            "implementation": {"mode": "flowlenia_2022_paper_equations"},
            "reintegration": {"border": "torus"},
            "food": None,
            "walls": None,
            "chemotaxis": None,
            "init": {
                "patches": [{"center": [64, 64], "size": 40}],
                "a_uniform": {"low": 0, "high": 1},
            },
        },
    )
    _write_json(
        run_dir / "search.json",
        {
            "count": 2,
            "seed_start": 10,
            "steps": 1200,
            "record_interval": 50,
            "score_weights": {"displacement": 0.35},
        },
    )
    _write_jsonl(run_dir / "results.jsonl", [_result(10), _result(10), _result(11)])
    compendium = tmp_path / "compendium.sqlite"
    _init_compendium(compendium)

    payload = promote_results_jsonl(
        compendium_path=compendium,
        run_dir=run_dir,
        run_id="test-run",
        batch_size=1,
    )

    assert payload["promotedRows"] == 2
    assert payload["counts"] == {"results": 2, "specimens": 2, "creatures": 2}
    connection = sqlite3.connect(compendium)
    try:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM creatures c
            JOIN specimens s ON s.id = c.canonical_specimen_id
            WHERE c.run_id = 'test-run'
            """
        ).fetchone()[0] == 2
        name, metadata_json = connection.execute(
            """
            SELECT name, research_metadata_json
            FROM creatures
            WHERE run_id = 'test-run'
            ORDER BY init_seed
            LIMIT 1
            """
        ).fetchone()
        assert name == "fl-2c20k-motion-128-10"
        metadata = json.loads(metadata_json)
        assert metadata["runProfile"] == "FL-2C20K-motion-128"
        assert metadata["kernelCount"] == 20
    finally:
        connection.close()

    warehouse = connect_database(tmp_path / "warehouse.duckdb")
    try:
        study_id = ingest_compendium(
            warehouse,
            compendium_path=compendium,
            run_id="test-run",
        )
        assert warehouse.execute(
            "SELECT COUNT(*) FROM specimens WHERE run_id = 'test-run'"
        ).fetchone()[0] == 2
        assert warehouse.execute(
            "SELECT run_id FROM studies WHERE study_id = ?",
            [study_id],
        ).fetchone()[0] == "test-run"
    finally:
        warehouse.close()

    refresh_payload = refresh_compendium_warehouse(
        warehouse_path=tmp_path / "warehouse-fast.duckdb",
        compendium_path=compendium,
        run_id="test-run",
    )
    assert refresh_payload["runId"] == "test-run"
    assert refresh_payload["terminalObservationsUpdated"] == 2
    assert refresh_payload["commonObservationsUpdated"] == 2
    fast_warehouse = connect_database(tmp_path / "warehouse-fast.duckdb")
    try:
        assert fast_warehouse.execute(
            """
            SELECT COUNT(DISTINCT observation_id)
            FROM comparison_feature_values_vw
            WHERE run_id = 'test-run' AND feature_space_id = ?
            """,
            [TERMINAL_FEATURE_SPACE_ID],
        ).fetchone()[0] == 2
        assert fast_warehouse.execute(
            """
            SELECT COUNT(DISTINCT observation_id)
            FROM comparison_feature_values_vw
            WHERE run_id = 'test-run' AND feature_space_id = ?
            """,
            [COMMON_FEATURE_SPACE_ID],
        ).fetchone()[0] == 2
    finally:
        fast_warehouse.close()
