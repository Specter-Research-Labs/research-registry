from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, cast

import duckdb
import numpy as np
import pytest

from lenia_swarm_analysis.morphospace import feature_tda_profile as feature_tda_profile_module
from lenia_swarm_analysis.morphospace.common_morphology import (
    AXIS_IDS as COMMON_MORPHOLOGY_AXIS_IDS,
)
from lenia_swarm_analysis.morphospace.common_morphology import (
    FEATURE_SPACE_ID as COMMON_MORPHOLOGY_FEATURE_SPACE_ID,
)
from lenia_swarm_analysis.morphospace.common_morphology import (
    point_cloud_shape_features,
)
from lenia_swarm_analysis.morphospace.derive_anatomy import derive_anatomy
from lenia_swarm_analysis.morphospace.derive_context_outcomes import (
    derive_context_outcomes,
)
from lenia_swarm_analysis.morphospace.derive_creature_signals import (
    derive_creature_signals,
)
from lenia_swarm_analysis.morphospace.derive_fibers import derive_fibers
from lenia_swarm_analysis.morphospace.derive_status import derive_status
from lenia_swarm_analysis.morphospace.derive_trajectories import derive_trajectories
from lenia_swarm_analysis.morphospace.export_biological import (
    export_biological_study,
)
from lenia_swarm_analysis.morphospace.export_creature_discovery import (
    export_creature_discovery,
)
from lenia_swarm_analysis.morphospace.export_legacy import (
    export_atlas_packet,
    export_family_comparison_packet,
    export_focal_packet,
    export_replay_packet,
    export_topology_packet,
)
from lenia_swarm_analysis.morphospace.ingest_compendium import ingest_compendium
from lenia_swarm_analysis.morphospace.ingest_focal import ingest_focal_packet
from lenia_swarm_analysis.morphospace.ingest_library import ingest_library_index
from lenia_swarm_analysis.morphospace.ingest_replay import ingest_replay_batch
from lenia_swarm_analysis.morphospace.resolve_discovery_exports import (
    resolve_discovery_exports,
)
from lenia_swarm_analysis.morphospace.run_topology import run_topology
from lenia_swarm_analysis.morphospace.run_universality import run_universality
from lenia_swarm_analysis.morphospace.warehouse import (
    connect_database,
    normalize_optional_timestamp,
    register_context,
    register_specimen_study,
    register_study,
    replace_feature_axes,
    replace_feature_values,
    upsert_feature_space,
    upsert_morphospace_source,
    upsert_observation,
    upsert_specimen,
)
from lenia_swarm_analysis.morphospace_cli import (
    derive_common_morphology_packet,
    import_dryad_fish_dataset,
    import_embryomaker_snapshots_dataset,
    import_reference_bundle_dataset,
    refresh_compendium_warehouse,
)
from lenia_swarm_analysis.morphospace_cli import (
    main as morphospace_main,
)
from lenia_swarm_analysis.transform.atlas import (
    build_transformation_atlas_packet,
)
from lenia_swarm_analysis.transform.focal import (
    build_transformation_focal_packet,
)
from lenia_swarm_analysis.transform.replay import (
    build_transformation_replay_packet,
)
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
)

Fingerprint = Sequence[int]
TraceSample = tuple[float, float, float, Fingerprint]
FocalRun = tuple[
    str,
    str,
    tuple[float, float],
    Sequence[TraceSample],
    dict[str, object],
]
FocalResult = tuple[float, float, float, Fingerprint]

FINGERPRINT_COLUMN: tuple[int, ...] = (0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
FINGERPRINT_DOUBLE_COLUMN: tuple[int, ...] = (
    0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0
)
FINGERPRINT_DIAMOND: tuple[int, ...] = (
    0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 1, 0
)
FINGERPRINT_SPARSE: tuple[int, ...] = (
    0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 1, 0
)
FINGERPRINT_OFFSET_CLUSTER: tuple[int, ...] = (
    0, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _scalar_int(connection: Any, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise AssertionError(f"query returned no rows: {query}")
    return int(row[0])


def _common_morphology_axis_metadata(connection: Any) -> dict[str, Any]:
    return {
        row[0]: json.loads(row[1])
        for row in connection.execute(
            """
            SELECT axis_id, metadata_json
            FROM feature_axes
            WHERE feature_space_id = 'common_morphology_v1'
            ORDER BY axis_id
            """
        ).fetchall()
    }


def _terminal(
    *,
    mass: float,
    occupancy: float,
    gyration: float,
    fingerprint: Fingerprint,
    entropy: float = 0.25,
) -> dict[str, object]:
    return {
        "finalMass": mass,
        "finalOccupancy": occupancy,
        "finalGyration": gyration,
        "fingerprintResolution": 4,
        "fingerprintU8": list(fingerprint),
        "angularSymmetry": {"normalizedEntropy": entropy},
        "fingerprintHash12": "hash01234567",
    }


def _result_row(
    *,
    mass: float,
    occupancy: float,
    gyration: float,
    fingerprint: Fingerprint,
) -> dict[str, object]:
    return {
        "descriptor_bundle": {
            "terminal": {
                "finalMass": mass,
                "finalOccupancy": occupancy,
                "finalGyration": gyration,
                "fingerprintResolution": 4,
                "fingerprintU8": list(fingerprint),
                "angularSymmetry": {"normalizedEntropy": 0.25},
            },
            "trajectory": {
                "centerVelocity": 0.01,
                "pathTortuosity": 2.5,
            },
        }
    }


def _trace_rows(
    *,
    base_center_x: float,
    base_center_y: float,
    samples: Sequence[TraceSample],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    steps = (0, 25, 50)
    for index, (mass, occupancy, gyration, fingerprint) in enumerate(samples):
        rows.append(
            {
                "step": steps[index],
                "centerX": base_center_x + 0.2 * index,
                "centerY": base_center_y + 0.1 * index,
                "terminal": _terminal(
                    mass=mass,
                    occupancy=occupancy,
                    gyration=gyration,
                    fingerprint=fingerprint,
                ),
            }
        )
    return rows


def _metric_row(
    run_id: str,
    perturbation_label: str,
    values: dict[str, object],
) -> dict[str, object]:
    return {
        "runID": run_id,
        "environmentLabel": "flat",
        "perturbationLabel": perturbation_label,
        **values,
    }


def _write_focal_phase(
    *,
    campaign_root: Path,
    phase_name: str,
    runs: Sequence[FocalRun],
    results: Sequence[FocalResult],
) -> None:
    phase_dir = campaign_root / phase_name
    for run_id, _perturbation_label, center, samples, _metrics in runs:
        _write_jsonl(
            phase_dir / f"{run_id}-trace.jsonl",
            _trace_rows(
                base_center_x=center[0],
                base_center_y=center[1],
                samples=samples,
            ),
        )

    _write_jsonl(
        phase_dir / "metrics.jsonl",
        [
            _metric_row(run_id, perturbation_label, metrics)
            for run_id, perturbation_label, _center, _samples, metrics in runs
        ],
    )
    _write_jsonl(
        phase_dir / "runs.jsonl",
        [
            {
                "runID": run_id,
                "repeatIndex": 0,
                "environmentLabel": "flat",
                "perturbationLabel": perturbation_label,
                "developmentTracePath": str(phase_dir / f"{run_id}-trace.jsonl"),
            }
            for run_id, perturbation_label, _center, _samples, _metrics in runs
        ],
    )
    _write_jsonl(
        phase_dir / "results.jsonl",
        [
            _result_row(
                mass=mass,
                occupancy=occupancy,
                gyration=gyration,
                fingerprint=fingerprint,
            )
            for mass, occupancy, gyration, fingerprint in results
        ],
    )


def _make_replay_fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    trace_a = tmp_path / "campaign/specimen-a/development-trace.jsonl"
    trace_b = tmp_path / "campaign/specimen-b/development-trace.jsonl"
    _write_jsonl(
        trace_a,
        [
            {
                "step": 0,
                "centerX": 1.0,
                "centerY": 1.0,
                "terminal": _terminal(
                    mass=10.0,
                    occupancy=0.10,
                    gyration=4.0,
                    fingerprint=FINGERPRINT_COLUMN,
                ),
            },
            {
                "step": 25,
                "centerX": 1.2,
                "centerY": 1.0,
                "terminal": _terminal(
                    mass=10.0,
                    occupancy=0.18,
                    gyration=6.0,
                    fingerprint=FINGERPRINT_DOUBLE_COLUMN,
                ),
            },
            {
                "step": 50,
                "centerX": 1.6,
                "centerY": 1.0,
                "terminal": _terminal(
                    mass=10.0,
                    occupancy=0.22,
                    gyration=5.0,
                    fingerprint=FINGERPRINT_DIAMOND,
                ),
            },
        ],
    )
    _write_jsonl(
        trace_b,
        [
            {
                "step": 0,
                "centerX": 2.8,
                "centerY": 2.0,
                "terminal": _terminal(
                    mass=12.0,
                    occupancy=0.08,
                    gyration=3.0,
                    entropy=0.4,
                    fingerprint=FINGERPRINT_SPARSE,
                ),
            },
            {
                "step": 25,
                "centerX": 3.0,
                "centerY": 2.0,
                "terminal": _terminal(
                    mass=12.0,
                    occupancy=0.12,
                    gyration=4.5,
                    entropy=0.35,
                    fingerprint=FINGERPRINT_OFFSET_CLUSTER,
                ),
            },
            {
                "step": 50,
                "centerX": 3.3,
                "centerY": 2.1,
                "terminal": _terminal(
                    mass=12.0,
                    occupancy=0.16,
                    gyration=5.2,
                    entropy=0.3,
                    fingerprint=FINGERPRINT_DIAMOND,
                ),
            },
        ],
    )
    traces_path = tmp_path / "development-traces.jsonl"
    summary_rows = [
        {
            "specimenId": "specimen-a",
            "specimenName": "specimen-a",
            "runId": "run-a",
            "campaignId": "campaign-a",
            "sourceKind": "result",
            "sourceRunId": "source-run-a",
            "sourceCampaignId": "source-campaign-a",
            "sourceInputPath": "/tmp/source-a.jsonl",
            "sourceMode": "campaign",
            "sourceAlgorithm": "discovery",
            "regimeFamily": "r1_mass_1c",
            "geometryFamily": "single_center_40",
            "canonicalFamily": "r1_mass_1c__single_center_40",
            "initialConditionFamily": "initfam:v2:single_patch:abcd",
            "replayRunId": "replay-a",
            "replaySteps": 600,
            "recordEvery": 25,
            "includeInitial": True,
            "sampleCount": 3,
            "capturedSteps": [0, 25, 50],
            "developmentTracePath": str(trace_a),
            "resultsPath": "/tmp/results-a.jsonl",
            "terminal": _terminal(
                mass=10.0,
                occupancy=0.22,
                gyration=5.0,
                fingerprint=FINGERPRINT_DIAMOND,
            ),
            "trajectory": {
                "centerVelocity": 0.04,
                "pathTortuosity": 3.5,
            },
        },
        {
            "specimenId": "specimen-b",
            "specimenName": "specimen-b",
            "runId": "run-b",
            "campaignId": "campaign-b",
            "sourceKind": "result",
            "sourceRunId": "source-run-b",
            "sourceCampaignId": "source-campaign-b",
            "sourceInputPath": "/tmp/source-b.jsonl",
            "sourceMode": "campaign",
            "sourceAlgorithm": "discovery",
            "regimeFamily": "r3_multikernel_1c",
            "geometryFamily": "single_offset_40",
            "canonicalFamily": "r3_multikernel_1c__single_offset_40",
            "initialConditionFamily": "initfam:v2:single_patch:efgh",
            "replayRunId": "replay-b",
            "replaySteps": 600,
            "recordEvery": 25,
            "includeInitial": True,
            "sampleCount": 3,
            "capturedSteps": [0, 25, 50],
            "developmentTracePath": str(trace_b),
            "resultsPath": "/tmp/results-b.jsonl",
            "terminal": _terminal(
                mass=12.0,
                occupancy=0.16,
                gyration=5.2,
                entropy=0.3,
                fingerprint=FINGERPRINT_DIAMOND,
            ),
            "trajectory": {
                "centerVelocity": 0.02,
                "pathTortuosity": 2.8,
            },
        },
    ]
    _write_jsonl(traces_path, summary_rows)
    return traces_path, {"rows": summary_rows}


def _make_replay_root_fixture(tmp_path: Path) -> tuple[Path, Path]:
    traces_path, fixture = _make_replay_fixture(tmp_path / "source")
    replay_root = tmp_path / "replay-root"
    rows = fixture["rows"]
    if not isinstance(rows, list):
        raise AssertionError("fixture rows must be a list")
    for index, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            raise AssertionError("fixture row must be a dict")
        row = cast(dict[str, Any], raw_row)
        campaign_dir = replay_root / "campaigns" / f"{index:04d}-{row['specimenName']}"
        trace_source = Path(str(row["developmentTracePath"]))
        trace_target = campaign_dir / "development-trace.jsonl"
        campaign_dir.mkdir(parents=True, exist_ok=True)
        trace_target.write_text(trace_source.read_text(encoding="utf-8"), encoding="utf-8")
        _write_json(
            campaign_dir / "search.json",
            {
                "steps": row["replaySteps"],
                "record_interval": row["recordEvery"],
            },
        )
        _write_jsonl(
            campaign_dir / "results.jsonl",
            [
                {
                    "descriptor_bundle": {
                        "terminal": row["terminal"],
                        "trajectory": row["trajectory"],
                    }
                }
            ],
        )
        _write_jsonl(
            campaign_dir / "library" / "index.jsonl",
            [
                {
                    "campaign_id": row["campaignId"],
                    "run_id": row["replayRunId"],
                    "recorded_at": "2026-03-26T00:00:00",
                    "config_hash": f"cfg-{index}",
                    "source_mode": "replay",
                    "source_algorithm": "canonical-replay",
                    "creature": {
                        "id": row["specimenId"],
                        "name": row["specimenName"],
                        "initialConditionFamily": row["initialConditionFamily"],
                        "descriptorBundle": {
                            "terminal": row["terminal"],
                            "trajectory": row["trajectory"],
                        },
                    },
                    "research_metadata": {
                        "mode": "replay",
                        "source_kind": row["sourceKind"],
                        "source_input_path": row["sourceInputPath"],
                        "source_run_id": row["sourceRunId"],
                        "source_campaign_id": row["sourceCampaignId"],
                        "source_mode": row["sourceMode"],
                        "source_algorithm": row["sourceAlgorithm"],
                        "source_research_metadata": {
                            "regime_family": row["regimeFamily"],
                            "geometry_family": row["geometryFamily"],
                            "canonical_family": row["canonicalFamily"],
                        },
                    },
                }
            ],
        )
        _write_json(
            campaign_dir / "replay-manifest.json",
            {
                "inputKind": row["sourceKind"],
                "inputPath": row["sourceInputPath"],
                "sourceRunId": row["sourceRunId"],
                "sourceCampaignId": row["sourceCampaignId"],
                "sourceCreatureId": row.get("sourceCreatureId", row["specimenId"]),
                "replayRunId": row["replayRunId"],
                "campaignId": row["campaignId"],
                "configHash": f"cfg-{index}",
                "searchPath": str(campaign_dir / "search.json"),
                "resultsPath": str(campaign_dir / "results.jsonl"),
                "libraryPath": str(campaign_dir / "library" / "index.jsonl"),
                "developmentTracePath": str(trace_target),
                "replayedAt": "2026-03-26T00:00:00",
            },
        )
    return replay_root, traces_path


def _make_focal_fixture(tmp_path: Path) -> tuple[Path, Path]:
    atlas_packet_path = tmp_path / "transformation-atlas-v2.json"
    _write_json(
        atlas_packet_path,
        {
            "packetKind": "developmental_transformation_atlas_v2",
            "specimens": [
                {
                    "specimenId": "specimen-a",
                    "runId": "run-a",
                    "campaignId": "campaign-a",
                    "sourceKind": "library_index",
                    "familyKind": "stale-family-kind",
                    "regimeFamily": "r1_mass_1c",
                    "geometryFamily": "single_center_40",
                    "canonicalFamily": "r1_mass_1c__single_center_40",
                    "dominantProgram": "folding_gain",
                    "rawAxes": {
                        "spread": 12.0,
                        "coverage": 0.10,
                        "compactness": 2.0,
                        "elongation": 1.4,
                        "boundary_complexity": 2.5,
                        "cavity_count": 0.0,
                        "fragmentation": 1.0,
                        "bilateral_symmetry": 0.9,
                        "radial_symmetry": 0.6,
                        "rotational_symmetry": 0.8,
                        "left_right_asymmetry": 0.1,
                        "center_offset": 0.0,
                        "axial_polarity": 0.1,
                        "locomotion": 0.01,
                        "meander": 2.0,
                        "symmetry_focus": 0.3,
                        "expansion_gain": 0.12,
                        "condensation_gain": 0.4,
                        "elongation_gain": 0.6,
                        "folding_gain": 0.8,
                        "cavity_birth": 0.0,
                        "fragmentation_gain": 0.0,
                        "locomotion_onset_step": 25.0,
                        "meander_final": 2.0,
                    },
                    "transformedAxes": {},
                },
                {
                    "specimenId": "specimen-b",
                    "runId": "run-b",
                    "campaignId": "campaign-b",
                    "sourceKind": "library_index",
                    "familyKind": "stale-family-kind",
                    "regimeFamily": "r3_multikernel_1c",
                    "geometryFamily": "single_offset_40",
                    "canonicalFamily": "r3_multikernel_1c__single_offset_40",
                    "dominantProgram": "elongation_gain",
                    "rawAxes": {
                        "spread": 20.0,
                        "coverage": 0.20,
                        "compactness": 1.5,
                        "elongation": 2.0,
                        "boundary_complexity": 3.0,
                        "cavity_count": 1.0,
                        "fragmentation": 2.0,
                        "bilateral_symmetry": 0.5,
                        "radial_symmetry": 0.25,
                        "rotational_symmetry": 0.3,
                        "left_right_asymmetry": 0.35,
                        "center_offset": 0.25,
                        "axial_polarity": 0.45,
                        "locomotion": 0.02,
                        "meander": 3.0,
                        "symmetry_focus": 0.2,
                        "expansion_gain": 0.30,
                        "condensation_gain": 0.1,
                        "elongation_gain": 1.2,
                        "folding_gain": 0.4,
                        "cavity_birth": 1.0,
                        "fragmentation_gain": 1.0,
                        "locomotion_onset_step": 50.0,
                        "meander_final": 3.0,
                    },
                    "transformedAxes": {},
                },
            ],
        },
    )

    focal_spec_path = tmp_path / "flow-transformation-atlas-focal-spec.json"
    _write_json(
        focal_spec_path,
        {
            "schemaVersion": 1,
            "runId": "focal-run",
            "sourceAtlasPacket": str(atlas_packet_path),
            "canonicalLibrary": "/tmp/library/index.jsonl",
            "selectedCanonicalCount": 2,
            "capCanonical": 2,
            "shortfallCanonical": 0,
            "selectedCanonical": [
                {
                    "specimenId": "specimen-a",
                    "specimenName": "discovery-a",
                    "phaseName": "focal-discovery-a-0",
                    "regimeFamily": "r1_mass_1c",
                    "geometryFamily": "single_center_40",
                    "canonicalFamily": "r1_mass_1c__single_center_40",
                    "sourceRunId": "run-a",
                    "selectedBy": ["folding_gain"],
                },
                {
                    "specimenId": "specimen-b",
                    "specimenName": "discovery-b",
                    "phaseName": "focal-discovery-b-1",
                    "regimeFamily": "r3_multikernel_1c",
                    "geometryFamily": "single_offset_40",
                    "canonicalFamily": "r3_multikernel_1c__single_offset_40",
                    "sourceRunId": "run-b",
                    "selectedBy": ["elongation_gain"],
                },
            ],
            "campaignPath": "/tmp/campaign.json",
        },
    )

    campaign_root = tmp_path / "campaign"
    _write_focal_phase(
        campaign_root=campaign_root,
        phase_name="focal-discovery-a-0",
        runs=[
            (
                "run-a-baseline",
                "baseline",
                (1.0, 1.0),
                [
                    (10.0, 0.10, 5.0, FINGERPRINT_COLUMN),
                    (9.5, 0.11, 5.2, FINGERPRINT_DOUBLE_COLUMN),
                    (9.0, 0.12, 5.4, FINGERPRINT_DIAMOND),
                ],
                {
                    "score": 0.5,
                    "centerVelocity": 0.001,
                    "displacement": 0.1,
                    "pathLength": 0.12,
                    "finalMass": 10.0,
                    "occupancyMean": 0.1,
                    "varianceMean": 0.02,
                    "gyration": 5.0,
                },
            ),
            (
                "run-a-m-plus",
                "m-plus",
                (1.1, 1.0),
                [
                    (10.0, 0.10, 5.0, FINGERPRINT_COLUMN),
                    (9.2, 0.09, 5.3, FINGERPRINT_DOUBLE_COLUMN),
                    (9.0, 0.09, 5.5, FINGERPRINT_DOUBLE_COLUMN),
                ],
                {
                    "postPerturbationDivergence": 0.05,
                    "returnToBaselineScore": 0.95,
                    "redirectedBehaviorScore": 0.05,
                    "massRetentionRatio": 1.0,
                    "displacementRatio": 1.1,
                    "occupancyDelta": 0.01,
                    "varianceDelta": 0.02,
                    "score": 0.45,
                    "centerVelocity": 0.002,
                },
            ),
            (
                "run-a-low-dt",
                "low-dt",
                (1.0, 1.1),
                [
                    (10.0, 0.10, 5.0, FINGERPRINT_COLUMN),
                    (8.7, 0.08, 5.8, FINGERPRINT_DIAMOND),
                    (8.0, 0.08, 6.0, FINGERPRINT_DIAMOND),
                ],
                {
                    "postPerturbationDivergence": 0.10,
                    "returnToBaselineScore": 0.90,
                    "redirectedBehaviorScore": 0.10,
                    "massRetentionRatio": 1.0,
                    "displacementRatio": 0.8,
                    "occupancyDelta": -0.01,
                    "varianceDelta": -0.02,
                    "score": 0.40,
                    "centerVelocity": 0.003,
                },
            ),
        ],
        results=[
            (10.0, 0.10, 5.0, FINGERPRINT_COLUMN),
            (9.0, 0.09, 5.5, FINGERPRINT_DOUBLE_COLUMN),
            (8.0, 0.08, 6.0, FINGERPRINT_DIAMOND),
        ],
    )
    _write_focal_phase(
        campaign_root=campaign_root,
        phase_name="focal-discovery-b-1",
        runs=[
            (
                "run-b-baseline",
                "baseline",
                (2.0, 2.0),
                [
                    (20.0, 0.20, 7.0, FINGERPRINT_DIAMOND),
                    (19.0, 0.19, 7.1, FINGERPRINT_DOUBLE_COLUMN),
                    (18.0, 0.18, 7.2, FINGERPRINT_DOUBLE_COLUMN),
                ],
                {
                    "score": 0.7,
                    "centerVelocity": 0.004,
                    "displacement": 0.3,
                    "pathLength": 0.32,
                    "finalMass": 20.0,
                    "occupancyMean": 0.2,
                    "varianceMean": 0.03,
                    "gyration": 7.0,
                },
            ),
            (
                "run-b-m-plus",
                "m-plus",
                (2.1, 2.0),
                [
                    (20.0, 0.20, 7.0, FINGERPRINT_DIAMOND),
                    (18.8, 0.19, 7.1, FINGERPRINT_DOUBLE_COLUMN),
                    (18.0, 0.18, 7.2, FINGERPRINT_DOUBLE_COLUMN),
                ],
                {
                    "postPerturbationDivergence": 0.03,
                    "returnToBaselineScore": 0.97,
                    "redirectedBehaviorScore": 0.03,
                    "massRetentionRatio": 0.99,
                    "displacementRatio": 1.2,
                    "occupancyDelta": 0.02,
                    "varianceDelta": 0.01,
                    "score": 0.66,
                    "centerVelocity": 0.005,
                },
            ),
            (
                "run-b-low-dt",
                "low-dt",
                (2.0, 2.1),
                [
                    (20.0, 0.20, 7.0, FINGERPRINT_DIAMOND),
                    (17.0, 0.17, 7.3, FINGERPRINT_COLUMN),
                    (16.0, 0.16, 7.5, FINGERPRINT_COLUMN),
                ],
                {
                    "postPerturbationDivergence": 0.20,
                    "returnToBaselineScore": 0.80,
                    "redirectedBehaviorScore": 0.20,
                    "massRetentionRatio": 0.95,
                    "displacementRatio": 0.6,
                    "occupancyDelta": -0.04,
                    "varianceDelta": -0.03,
                    "score": 0.50,
                    "centerVelocity": 0.006,
                },
            ),
        ],
        results=[
            (20.0, 0.20, 7.0, FINGERPRINT_DIAMOND),
            (18.0, 0.18, 7.2, FINGERPRINT_DOUBLE_COLUMN),
            (16.0, 0.16, 7.5, FINGERPRINT_COLUMN),
        ],
    )
    focal_packet_path = tmp_path / "transformation-focal-packet.json"
    focal_packet = build_transformation_focal_packet(
        focal_spec_path=focal_spec_path,
        campaign_root=campaign_root,
    )
    _write_json(focal_packet_path, focal_packet)
    return focal_packet_path, atlas_packet_path


def _make_compendium_fixture(
    tmp_path: Path,
    *,
    specimen_manifest: dict[str, Any] | None = None,
) -> Path:
    path = tmp_path / "compendium.sqlite"
    export_dir = tmp_path / "exports" / "creature-1"
    export_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE creatures (
                id TEXT PRIMARY KEY,
                canonical_specimen_id TEXT,
                run_id TEXT,
                campaign_id TEXT,
                source_mode TEXT,
                source_algorithm TEXT,
                config_hash TEXT,
                score REAL,
                is_stable INTEGER,
                recorded_at TEXT,
                taxonomy_family_id TEXT,
                morphometrics_json TEXT,
                genotype_json TEXT,
                initial_condition_json TEXT,
                metrics_json TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE exports (
                creature_id TEXT PRIMARY KEY,
                run_id TEXT,
                campaign_id TEXT,
                score REAL,
                filters_passed INTEGER,
                exported_at TEXT,
                payload_path TEXT,
                export_dir TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE specimens (
                id TEXT PRIMARY KEY,
                creature_id TEXT,
                run_id TEXT,
                campaign_id TEXT,
                source_kind TEXT,
                source_mode TEXT,
                source_algorithm TEXT,
                config_hash TEXT,
                initial_condition_family TEXT,
                recorded_at TEXT,
                activity_path TEXT,
                fingerprint_path TEXT,
                terminal_descriptor_json TEXT,
                trajectory_descriptor_json TEXT,
                runtime_family TEXT,
                runtime_capabilities_json TEXT,
                specimen_manifest_json TEXT
            )
            """
        )
        terminal = _terminal(
            mass=15.0,
            occupancy=0.14,
            gyration=4.2,
            fingerprint=FINGERPRINT_DIAMOND,
        )
        trajectory = {"centerVelocity": 0.02, "pathTortuosity": 2.5}
        connection.execute(
            """
            INSERT INTO creatures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "creature-1",
                "specimen-1",
                "run-1",
                "campaign-1",
                "campaign",
                "discovery",
                "cfg-hash",
                0.75,
                0,
                "2026-03-25T10:00:00",
                "fam-drifter-soliton",
                json.dumps({"pathTortuosity": 5.5, "movementEfficiency": 0.18}),
                json.dumps({"R": 12.0}),
                json.dumps({"patches": [{"center": [64, 64], "size": 40}], "seed": 3}),
                json.dumps({"mass_mean": 15.0, "occupancy_mean": 0.14}),
            ),
        )
        connection.execute(
            """
            INSERT INTO exports VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "creature-1",
                "run-1",
                "campaign-1",
                0.75,
                1,
                "2026-03-25T10:10:00",
                "/tmp/payload.json",
                str(export_dir),
            ),
        )
        connection.execute(
            """
            INSERT INTO specimens VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "specimen-1",
                "creature-1",
                "run-1",
                "campaign-1",
                "compendium_specimen",
                "campaign",
                "discovery",
                "cfg-hash",
                "initfam:v2:single_patch:abcd",
                "2026-03-25T10:15:00",
                "/tmp/activity.jsonl",
                "/tmp/fingerprint.png",
                json.dumps(terminal),
                json.dumps(trajectory),
                None,
                None,
                json.dumps(specimen_manifest) if specimen_manifest is not None else None,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_normalize_optional_timestamp_accepts_apple_reference_seconds() -> None:
    normalized = normalize_optional_timestamp(796169489.064308)
    assert normalized == datetime.fromisoformat("2026-03-25T22:11:29.064308")


def test_morphospace_library_ingest_accepts_numeric_recorded_at(tmp_path: Path) -> None:
    fingerprint = bytes(FINGERPRINT_DIAMOND)
    library_path = tmp_path / "library/index.jsonl"
    _write_jsonl(
        library_path,
        [
            {
                "campaign_id": "campaign-1",
                "config_hash": "cfg-hash",
                "recorded_at": 796169489.064308,
                "run_id": "run-1",
                "source_algorithm": "discovery",
                "source_mode": "campaign",
                "research_metadata": {
                    "regime_family": "r3_multikernel_1c",
                    "geometry_family": "single_center_40",
                    "canonical_family": "r3_multikernel_1c__single_center_40",
                },
                "creature": {
                    "id": "creature-1",
                    "initialConditionFamily": "initfam:v2:single_patch:abcd",
                    "descriptorBundle": {
                        "terminal": _terminal(
                            mass=15.0,
                            occupancy=0.14,
                            gyration=4.2,
                            fingerprint=[],
                        ),
                        "trajectory": {
                            "centerVelocity": 0.02,
                            "pathTortuosity": 2.5,
                        },
                    },
                    "score": 0.75,
                },
            }
        ],
    )
    payload = json.loads(library_path.read_text(encoding="utf-8").strip())
    payload["creature"]["descriptorBundle"]["terminal"]["fingerprintU8"] = base64.b64encode(
        fingerprint
    ).decode("ascii")
    _write_jsonl(library_path, [payload])

    connection = connect_database(tmp_path / "morphospace.duckdb")
    try:
        study_id = ingest_library_index(connection, index_path=library_path)
        row = connection.execute(
            """
            SELECT recorded_at, regime_family, geometry_family, canonical_family, family_kind
            FROM specimens
            WHERE specimen_id = 'creature-1'
            """
        ).fetchone()
        assert row is not None
        assert row[0] == datetime.fromisoformat("2026-03-25T22:11:29.064308")
        assert row[1:] == (
            "r3_multikernel_1c",
            "single_center_40",
            "r3_multikernel_1c__single_center_40",
            "r3_multikernel_1c__single_center_40",
        )
        study_row = connection.execute(
            "SELECT COUNT(*) FROM study_specimens WHERE study_id = ?",
            [study_id],
        ).fetchone()
        assert study_row is not None
        assert study_row[0] == 1
    finally:
        connection.close()


def test_morphospace_library_ingest_prefers_specimen_manifest_contract(tmp_path: Path) -> None:
    library_path = tmp_path / "library/index.jsonl"
    _write_jsonl(
        library_path,
        [
            {
                "run_id": "run-row",
                "campaign_id": "campaign-row",
                "recorded_at": "2026-03-25T20:00:00",
                "config_hash": "cfg-row",
                "source_mode": "row-mode",
                "source_algorithm": "row-algorithm",
                "research_metadata": {
                    "regime_family": "row-regime",
                    "geometry_family": "row-geometry",
                    "canonical_family": "row-canonical",
                },
                "runtime_family": "row-runtime",
                "runtime_capabilities": ["row-capability"],
                "specimen_manifest": {
                    "version": 1,
                    "specimenID": "creature-manifest",
                    "creatureID": "creature-manifest",
                    "runID": "run-manifest",
                    "campaignID": "campaign-manifest",
                    "sourceKind": "manifest-library",
                    "sourceMode": "manifest-mode",
                    "sourceAlgorithm": "manifest-algorithm",
                    "runtimeFamily": "manifest-runtime",
                    "runtimeCapabilities": [
                        "warehouse_ingest",
                        "topology",
                        "archive",
                    ],
                    "configHash": "cfg-manifest",
                    "recordedAt": "2026-03-26T00:00:00",
                    "initialConditionFamily": "manifest-init",
                    "taxonomy": {
                        "familyID": "manifest-taxonomy-family",
                    },
                    "researchMetadata": {
                        "source_export_dir": "exports/manifest-origin",
                        "source_research_metadata": {
                            "regime_family": "manifest-regime",
                            "geometry_family": "manifest-geometry",
                            "canonical_family": "manifest-canonical",
                        },
                    },
                    "replay": {
                        "exportDir": "exports/replay-manifest-origin",
                    },
                    "snapshots": {
                        "descriptorBundle": {
                            "terminal": _terminal(
                                mass=15.0,
                                occupancy=0.14,
                                gyration=4.2,
                                fingerprint=FINGERPRINT_COLUMN,
                            ),
                            "trajectory": {
                                "centerVelocity": 0.02,
                                "pathTortuosity": 2.5,
                            },
                        }
                    },
                },
                "creature": {
                    "id": "creature-manifest",
                    "name": "manifest-preferred",
                    "initialConditionFamily": "row-init",
                    "descriptorBundle": {
                        "terminal": _terminal(
                            mass=15.0,
                            occupancy=0.14,
                            gyration=4.2,
                            fingerprint=FINGERPRINT_COLUMN,
                        ),
                        "trajectory": {
                            "centerVelocity": 0.02,
                            "pathTortuosity": 2.5,
                        },
                    },
                    "score": 0.75,
                },
            }
        ],
    )

    connection = connect_database(tmp_path / "library-manifest.duckdb")
    try:
        ingest_library_index(connection, index_path=library_path)
        row = connection.execute(
            """
            SELECT source_kind, source_mode, source_algorithm, config_hash,
                   initial_condition_family, regime_family, geometry_family,
                   canonical_family, family_kind, recorded_at, export_dir,
                   runtime_family,
                   json_extract_string(runtime_capabilities_json, '$[0]'),
                   json_extract_string(runtime_capabilities_json, '$[1]'),
                   json_extract_string(runtime_capabilities_json, '$[2]'),
                   json_extract_string(specimen_manifest_json, '$.runtimeFamily'),
                   json_extract_string(
                       provenance_json,
                       '$.research_metadata.source_research_metadata.canonical_family'
                   )
            FROM specimens
            WHERE specimen_id = 'creature-manifest'
            """
        ).fetchone()
        assert row is not None
        assert row[0:9] == (
            "manifest-library",
            "manifest-mode",
            "manifest-algorithm",
            "cfg-manifest",
            "manifest-init",
            "manifest-regime",
            "manifest-geometry",
            "manifest-canonical",
            "manifest-taxonomy-family",
        )
        assert row[9] == datetime.fromisoformat("2026-03-26T00:00:00")
        assert row[10:17] == (
            "exports/replay-manifest-origin",
            "manifest-runtime",
            "archive",
            "topology",
            "warehouse_ingest",
            "manifest-runtime",
            "manifest-canonical",
        )
    finally:
        connection.close()


def test_morphospace_replay_ingest_and_atlas_export_roundtrip(tmp_path: Path) -> None:
    traces_path, _fixture = _make_replay_fixture(tmp_path)
    legacy_replay = build_transformation_replay_packet(development_traces_path=traces_path)

    connection = connect_database(tmp_path / "morphospace.duckdb")
    try:
        study_id = ingest_replay_batch(connection, development_traces_path=traces_path)
        assert _scalar_int(connection, "SELECT COUNT(*) FROM raw_jsonl_rows") == 8
        assert _scalar_int(connection, "SELECT COUNT(*) FROM development_samples") == 6
        assert derive_status(connection, study_id=study_id) == 2

        exported_replay = export_replay_packet(connection, study_id=study_id)
        assert exported_replay["summary"] == legacy_replay["summary"]
        assert exported_replay["groupCounts"] == legacy_replay["groupCounts"]
        assert [axis["id"] for axis in exported_replay["terminalAxes"]] == list(TERMINAL_AXIS_IDS)
        assert [axis["id"] for axis in exported_replay["developmentalAxes"]] == list(
            DEVELOPMENTAL_AXIS_IDS
        )
        exported_by_id = {row["specimenId"]: row for row in exported_replay["specimens"]}
        legacy_by_id = {row["specimenId"]: row for row in legacy_replay["specimens"]}
        assert set(exported_by_id) == set(legacy_by_id) == {"specimen-a", "specimen-b"}
        assert exported_by_id["specimen-b"]["familyKind"] == "r3_multikernel_1c__single_offset_40"
        assert (
            exported_by_id["specimen-a"]["developmentalAxes"]
            == legacy_by_id["specimen-a"]["developmentalAxes"]
        )

    finally:
        connection.close()

    # Build the legacy atlas from the legacy replay packet after closing the DB.
    legacy_replay_path = traces_path.parent / "legacy-replay.json"
    _write_json(legacy_replay_path, legacy_replay)
    legacy_atlas = build_transformation_atlas_packet(
        replay_packet_path=legacy_replay_path,
        top_exemplars_per_axis=3,
    )

    connection = connect_database(tmp_path / "morphospace.duckdb")
    try:
        exported_atlas = export_atlas_packet(
            connection,
            study_id=study_id,
            top_exemplars_per_axis=3,
        )
        assert exported_atlas["summary"] == legacy_atlas["summary"]
        assert {specimen["specimenId"] for specimen in exported_atlas["specimens"]} == {
            "specimen-a",
            "specimen-b",
        }
        topology_study_id = run_topology(
            connection,
            study_id=study_id,
            source_packet_kind="atlas",
            min_group_size=2,
            max_homology_dim=1,
        )
        topology_study = connection.execute(
            "SELECT study_kind, parent_study_id FROM studies WHERE study_id = ?",
            [topology_study_id],
        ).fetchone()
        assert topology_study == ("topology_run", study_id)
        topology_packet = export_topology_packet(connection, study_id=topology_study_id)
        assert (
            topology_packet["summary"]["sourcePacketKind"]
            == "developmental_transformation_atlas_v2"
        )
        assert topology_packet["summary"]["specimenCount"] == 2
        assert "transformation_signature_space" in topology_packet["spaces"]
        assert _scalar_int(connection, "SELECT COUNT(*) FROM topology_features") > 0
        with pytest.raises(SystemExit, match="topology child studies"):
            export_topology_packet(connection, study_id=study_id)
    finally:
        connection.close()


def test_morphospace_replay_root_ingest_matches_trace_summary_ingest(tmp_path: Path) -> None:
    replay_root, traces_path = _make_replay_root_fixture(tmp_path)
    legacy_replay = build_transformation_replay_packet(development_traces_path=traces_path)

    connection = connect_database(tmp_path / "replay-root.duckdb")
    try:
        study_id = ingest_replay_batch(connection, development_traces_path=replay_root)
        assert _scalar_int(connection, "SELECT COUNT(*) FROM raw_json_objects") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM raw_jsonl_rows") == 6
        exported_replay = export_replay_packet(connection, study_id=study_id)
        assert exported_replay["summary"] == legacy_replay["summary"]
        assert exported_replay["groupCounts"] == legacy_replay["groupCounts"]
        assert {specimen["specimenId"] for specimen in exported_replay["specimens"]} == {
            "specimen-a",
            "specimen-b",
        }
        assert exported_replay["specimens"][0]["familyKind"] in {
            "r1_mass_1c__single_center_40",
            "r3_multikernel_1c__single_offset_40",
        }
    finally:
        connection.close()


def test_morphospace_replay_root_ingest_prefers_library_specimen_manifest_provenance(
    tmp_path: Path,
) -> None:
    replay_root, _traces_path = _make_replay_root_fixture(tmp_path)
    library_path = replay_root / "campaigns" / "0001-specimen-a" / "library" / "index.jsonl"
    library_row = json.loads(library_path.read_text(encoding="utf-8").strip())
    library_row["creature"]["initialConditionFamily"] = "row-init"
    library_row["research_metadata"] = {
        "source_kind": "row-kind",
        "source_run_id": "row-source-run",
        "source_campaign_id": "row-source-campaign",
        "source_input_path": "row/input.json",
        "source_mode": "row-source-mode",
        "source_algorithm": "row-source-algorithm",
        "source_export_dir": "exports/row-origin",
        "source_research_metadata": {
            "regime_family": "row-regime",
            "geometry_family": "row-geometry",
            "canonical_family": "row-canonical",
        },
    }
    library_row["specimen_manifest"] = {
        "version": 1,
        "specimenID": "specimen-a",
        "creatureID": "specimen-a",
        "runID": library_row["run_id"],
        "campaignID": library_row["campaign_id"],
        "sourceKind": "library",
        "sourceMode": "replay",
        "sourceAlgorithm": "canonical-replay",
        "runtimeFamily": "flow_lenia",
        "runtimeCapabilities": ["archive", "replay", "warehouse_ingest"],
        "configHash": library_row["config_hash"],
        "recordedAt": library_row["recorded_at"],
        "initialConditionFamily": "manifest-init",
        "researchMetadata": {
            "source_kind": "manifest-kind",
            "source_run_id": "manifest-source-run",
            "source_campaign_id": "manifest-source-campaign",
            "source_input_path": "manifest/input.json",
            "source_mode": "manifest-source-mode",
            "source_algorithm": "manifest-source-algorithm",
            "source_export_dir": "exports/manifest-origin",
            "source_research_metadata": {
                "regime_family": "manifest-regime",
                "geometry_family": "manifest-geometry",
                "canonical_family": "manifest-canonical",
            },
        },
        "replay": {
            "exportDir": "exports/replay-manifest-origin",
        },
        "snapshots": {},
    }
    _write_jsonl(library_path, [library_row])

    connection = connect_database(tmp_path / "replay-manifest.duckdb")
    try:
        ingest_replay_batch(connection, development_traces_path=replay_root)
        row = connection.execute(
            """
            SELECT source_kind, source_mode, source_algorithm, run_id, campaign_id,
                   initial_condition_family, regime_family, geometry_family,
                   canonical_family, family_kind, export_dir,
                   json_extract_string(provenance_json, '$.sourceRunId'),
                   json_extract_string(provenance_json, '$.sourceInputPath'),
                   json_extract_string(provenance_json, '$.sourceExportDir')
            FROM specimens
            WHERE specimen_id = 'specimen-a'
            """
        ).fetchone()
        assert row == (
            "manifest-kind",
            "manifest-source-mode",
            "manifest-source-algorithm",
            "manifest-source-run",
            "manifest-source-campaign",
            "manifest-init",
            "manifest-regime",
            "manifest-geometry",
            "manifest-canonical",
            "manifest-canonical",
            "exports/replay-manifest-origin",
            "manifest-source-run",
            "manifest/input.json",
            "exports/replay-manifest-origin",
        )
    finally:
        connection.close()


def test_morphospace_focal_ingest_and_family_export_roundtrip(tmp_path: Path) -> None:
    traces_path, _fixture = _make_replay_fixture(tmp_path / "replay")
    focal_packet_path, _atlas_packet_path = _make_focal_fixture(tmp_path)
    legacy_focal = json.loads(focal_packet_path.read_text(encoding="utf-8"))

    connection = connect_database(tmp_path / "focal.duckdb")
    try:
        replay_study_id = ingest_replay_batch(connection, development_traces_path=traces_path)
        replay_before_focal = export_replay_packet(connection, study_id=replay_study_id)
        focal_study_id = ingest_focal_packet(connection, focal_packet_path=focal_packet_path)
        replay_after_focal = export_replay_packet(connection, study_id=replay_study_id)
        assert replay_after_focal["summary"] == replay_before_focal["summary"]
        assert {specimen["specimenId"] for specimen in replay_after_focal["specimens"]} == {
            "specimen-a",
            "specimen-b",
        }
        exported_focal = export_focal_packet(connection, study_id=focal_study_id)
        assert exported_focal["summary"] == legacy_focal["summary"]
        assert {specimen["specimenId"] for specimen in exported_focal["specimens"]} == {
            "specimen-a",
            "specimen-b",
        }
        assert _scalar_int(connection, "SELECT COUNT(*) FROM context_sample_axes") > 0

        atlas_topology_study_id = run_topology(
            connection,
            study_id=replay_study_id,
            source_packet_kind="atlas",
            min_group_size=2,
            max_homology_dim=1,
        )
        focal_topology_study_id = run_topology(
            connection,
            study_id=focal_study_id,
            source_packet_kind="focal",
            min_group_size=2,
            max_homology_dim=1,
        )
        topology_packet = export_topology_packet(connection, study_id=focal_topology_study_id)
        assert topology_packet["summary"]["sourcePacketKind"] == "transformation_focal_packet_v1"
        assert "focal_response_space" in topology_packet["spaces"]
        assert _scalar_int(connection, "SELECT COUNT(*) FROM topology_features") > 0
        with pytest.raises(SystemExit, match="topology child studies"):
            export_topology_packet(connection, study_id=focal_study_id)

        comparison = export_family_comparison_packet(
            connection,
            atlas_study_id=replay_study_id,
            focal_study_id=focal_study_id,
            atlas_topology_study_id=atlas_topology_study_id,
            focal_topology_study_id=focal_topology_study_id,
            canonical_families=[
                "r1_mass_1c__single_center_40",
                "r3_multikernel_1c__single_offset_40",
            ],
        )
        assert comparison["summary"]["familyCount"] == 2
        assert comparison["families"][0]["canonicalFamily"] == "r1_mass_1c__single_center_40"
        assert comparison["pairwise"][0]["familyA"] == "r1_mass_1c__single_center_40"
        assert comparison["sourceArtifacts"]["atlasTopologyStudy"] == (
            f"duckdb://study/{atlas_topology_study_id}"
        )
        assert comparison["sourceArtifacts"]["focalTopologyStudy"] == (
            f"duckdb://study/{focal_topology_study_id}"
        )
    finally:
        connection.close()


def test_morphospace_compendium_ingest_preserves_raw_rows_and_metadata(
    tmp_path: Path,
) -> None:
    compendium_path = _make_compendium_fixture(tmp_path)
    expected_export_dir = str(tmp_path / "exports" / "creature-1")

    connection = connect_database(tmp_path / "compendium.duckdb")
    try:
        study_id = ingest_compendium(connection, compendium_path=compendium_path)
        assert _scalar_int(connection, "SELECT COUNT(*) FROM raw_sqlite_rows") == 3
        specimen = connection.execute(
            """
            SELECT source_creature_id, search_is_stable_candidate, export_dir
            FROM specimens
            WHERE specimen_id = 'specimen-1'
            """
        ).fetchone()
        assert specimen is not None
        assert specimen[0] == "creature-1"
        assert specimen[1] is False
        assert Path(specimen[2]).resolve() == Path(expected_export_dir).resolve()
        creature_row = connection.execute(
            """
            SELECT family_kind,
                   search_is_stable_candidate,
                   export_dir,
                   json_extract_string(specimen_manifest_json, '$.taxonomy.familyID'),
                   CAST(
                       json_extract(
                           specimen_manifest_json,
                           '$.snapshots.morphometrics.pathTortuosity'
                       ) AS DOUBLE
                   ),
                   runtime_family,
                   json_extract_string(runtime_capabilities_json, '$[0]'),
                   json_extract_string(specimen_manifest_json, '$.runtimeFamily')
            FROM specimens
            WHERE specimen_id = 'specimen-1'
            """
        ).fetchone()
        assert creature_row is not None
        assert creature_row[0] == "fam-drifter-soliton"
        assert creature_row[1] is False
        assert Path(creature_row[2]).resolve() == Path(expected_export_dir).resolve()
        assert creature_row[3:] == (
            "fam-drifter-soliton",
            5.5,
            "flow_lenia",
            "archive",
            "flow_lenia",
        )
        assert resolve_discovery_exports(connection, study_id=study_id) == 1
        resolution_row = connection.execute(
            """
            SELECT resolved_export_dir, replayable, resolution_source
            FROM discovery_export_resolutions
            WHERE specimen_id = 'specimen-1'
            """
        ).fetchone()
        assert resolution_row is not None
        assert Path(resolution_row[0]).resolve() == Path(expected_export_dir).resolve()
        assert resolution_row[1:] == (True, "absolute_export_dir")
        terminal_axes = _scalar_int(
            connection,
            """
            SELECT COUNT(*)
            FROM specimen_axes
            WHERE specimen_id = 'specimen-1' AND axis_family = 'terminal'
            """,
        )
        assert terminal_axes == len(TERMINAL_AXIS_IDS)
        assert derive_status(connection, study_id=study_id) == 1
        status = connection.execute(
            """
            SELECT atlas_eligible, status_reason
            FROM specimen_status
            WHERE specimen_id = 'specimen-1'
            """
        ).fetchone()
        assert status == (False, "missing replay; missing developmental axes")
    finally:
        connection.close()


def test_morphospace_compendium_ingest_prefers_canonical_specimen_manifest(
    tmp_path: Path,
) -> None:
    manifest_export_dir = tmp_path / "exports" / "canonical-specimen"
    manifest_export_dir.mkdir(parents=True, exist_ok=True)
    compendium_path = _make_compendium_fixture(
        tmp_path,
        specimen_manifest={
            "version": 1,
            "specimenID": "specimen-1",
            "creatureID": "creature-1",
            "runID": "run-1",
            "campaignID": "campaign-1",
            "sourceKind": "canonical_specimen",
            "sourceMode": "qd-2024",
            "sourceAlgorithm": "aurora",
            "runtimeFamily": "qd24_paper",
            "runtimeCapabilities": ["topology", "archive", "replay"],
            "configHash": "cfg-manifest",
            "recordedAt": "2026-03-25T10:45:00",
            "initialConditionFamily": "initfam:manifest",
            "taxonomy": {
                "familyID": "fam-manifest",
            },
            "replay": {
                "exportDir": str(manifest_export_dir),
            },
        },
    )

    connection = connect_database(tmp_path / "compendium-manifest.duckdb")
    try:
        ingest_compendium(connection, compendium_path=compendium_path)
        row = connection.execute(
            """
            SELECT source_kind,
                   source_mode,
                   source_algorithm,
                   config_hash,
                   initial_condition_family,
                   family_kind,
                   recorded_at,
                   export_dir,
                   runtime_family,
                   json_extract_string(runtime_capabilities_json, '$[0]'),
                   json_extract_string(runtime_capabilities_json, '$[1]'),
                   json_extract_string(runtime_capabilities_json, '$[2]')
            FROM specimens
            WHERE specimen_id = 'specimen-1'
            """
        ).fetchone()
        assert row is not None
        assert row[:6] == (
            "canonical_specimen",
            "qd-2024",
            "aurora",
            "cfg-manifest",
            "initfam:manifest",
            "fam-manifest",
        )
        assert row[6] == datetime.fromisoformat("2026-03-25T10:45:00")
        assert Path(row[7]).resolve() == manifest_export_dir.resolve()
        assert row[8:] == (
            "qd24_paper",
            "archive",
            "replay",
            "topology",
        )
    finally:
        connection.close()


def test_connect_database_migrates_legacy_specimen_contract_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    connection = duckdb.connect(str(path))
    try:
        connection.execute("CREATE TABLE schema_meta (schema_version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES (5)")
        connection.execute(
            """
            CREATE TABLE specimens (
                specimen_id TEXT PRIMARY KEY,
                source_creature_id TEXT,
                study_id TEXT NOT NULL,
                run_id TEXT,
                campaign_id TEXT,
                source_kind TEXT NOT NULL,
                source_mode TEXT,
                source_algorithm TEXT,
                config_hash TEXT,
                initial_condition_family TEXT,
                regime_family TEXT,
                geometry_family TEXT,
                canonical_family TEXT,
                family_kind TEXT,
                score DOUBLE,
                filters_passed BOOLEAN,
                search_is_stable_candidate BOOLEAN,
                recorded_at TIMESTAMP,
                results_path TEXT,
                export_dir TEXT,
                activity_path TEXT,
                fingerprint_path TEXT,
                provenance_json JSON
            )
            """
        )
        connection.execute(
            """
            INSERT INTO specimens (
                specimen_id, source_creature_id, study_id, run_id, campaign_id, source_kind,
                source_mode, source_algorithm, config_hash, initial_condition_family,
                regime_family, geometry_family, canonical_family, family_kind, score,
                filters_passed, search_is_stable_candidate, recorded_at, results_path,
                export_dir, activity_path, fingerprint_path, provenance_json
            )
            VALUES (
                'specimen-legacy', 'creature-legacy', 'study-legacy', 'run-legacy', NULL, 'legacy',
                'campaign', 'discovery', 'cfg-legacy', 'initfam:legacy',
                NULL, NULL, NULL, NULL, 0.5,
                NULL, NULL, NULL, NULL,
                NULL, NULL, NULL, CAST('{}' AS JSON)
            )
            """
        )
    finally:
        connection.close()

    migrated = connect_database(path)
    try:
        columns = {
            str(row[1]) for row in migrated.execute("PRAGMA table_info('specimens')").fetchall()
        }
        assert "runtime_family" in columns
        assert "runtime_capabilities_json" in columns
        assert "specimen_manifest_json" in columns
        row = migrated.execute(
            """
            SELECT specimen_id, runtime_family, runtime_capabilities_json, specimen_manifest_json
            FROM specimens
            WHERE specimen_id = 'specimen-legacy'
            """
        ).fetchone()
        assert row == ("specimen-legacy", None, None, None)
    finally:
        migrated.close()


def test_derive_creature_signals_requires_replay_samples(tmp_path: Path) -> None:
    compendium_path = _make_compendium_fixture(tmp_path)

    connection = connect_database(tmp_path / "missing-replay.duckdb")
    try:
        study_id = ingest_compendium(connection, compendium_path=compendium_path)
        derive_anatomy(connection, study_id=study_id)
        with pytest.raises(SystemExit, match="missing development_samples"):
            derive_creature_signals(connection, study_id=study_id)
    finally:
        connection.close()


def test_morphospace_biological_derivations_and_export(tmp_path: Path) -> None:
    traces_path, _fixture = _make_replay_fixture(tmp_path / "replay")
    focal_packet_path, _atlas_packet_path = _make_focal_fixture(tmp_path / "focal")

    connection = connect_database(tmp_path / "biological.duckdb")
    try:
        replay_study_id = ingest_replay_batch(connection, development_traces_path=traces_path)
        focal_study_id = ingest_focal_packet(connection, focal_packet_path=focal_packet_path)
        assert derive_status(connection, study_id=replay_study_id) == 2
        assert derive_anatomy(connection, study_id=replay_study_id) == 2
        assert derive_creature_signals(connection, study_id=replay_study_id) == 2
        assert derive_context_outcomes(connection, study_id=focal_study_id) == 6
        assert derive_anatomy(connection, study_id=focal_study_id) >= 2
        assert derive_trajectories(connection, study_id=replay_study_id) == 2
        assert derive_trajectories(connection, study_id=focal_study_id) == 8
        assert derive_fibers(connection, study_id=replay_study_id) >= 1
        universality_run_id = run_universality(connection, study_id=replay_study_id)
        assert universality_run_id
        atlas_topology_study_id = run_topology(
            connection,
            study_id=replay_study_id,
            source_packet_kind="atlas",
            min_group_size=2,
            max_homology_dim=1,
        )
        focal_topology_study_id = run_topology(
            connection,
            study_id=focal_study_id,
            source_packet_kind="focal",
            min_group_size=2,
            max_homology_dim=1,
        )
        assert atlas_topology_study_id
        assert focal_topology_study_id
        baseline_state_count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM anatomical_states
            WHERE study_id = ?
              AND source_kind = 'specimen_baseline'
            """,
            [replay_study_id],
        ).fetchone()
        assert baseline_state_count_row is not None
        baseline_state_count = int(baseline_state_count_row[0])
        assert baseline_state_count == 2
        creature_state_row = connection.execute(
            """
            SELECT coherence_class, organization_class, creature_bucket, coherence_mean
            FROM creature_states_vw
            WHERE study_id = ? AND context_kind = 'baseline'
            ORDER BY specimen_id
            LIMIT 1
            """,
            [replay_study_id],
        ).fetchone()
        assert creature_state_row is not None
        assert creature_state_row[0] in {"coherent_body", "soft_body", "fragmented_pattern"}
        assert creature_state_row[1] is not None
        assert creature_state_row[2] is not None
        assert isinstance(creature_state_row[3], float)
        context_trial_count_row = connection.execute(
            "SELECT COUNT(*) FROM context_trials WHERE study_id = ?",
            [focal_study_id],
        ).fetchone()
        assert context_trial_count_row is not None
        context_trial_count = int(context_trial_count_row[0])
        assert context_trial_count == 6
        assert _scalar_int(connection, "SELECT COUNT(*) FROM context_sample_axes") > 0
        context_summary_rows = connection.execute(
            """
            SELECT context_kind, mean_fragility_score, mean_robustness_score,
                   goal_error_score, peak_goal_error_score,
                   cumulative_goal_error_score, body_plan_error_score,
                   body_plan_class_shift_score, control_cost_proxy,
                   trace_path_length, trace_path_length_ratio_to_reference,
                   trace_class_change_count
            FROM creature_context_summary_vw
            WHERE study_id = ?
            ORDER BY context_trial_id
            """,
            [focal_study_id],
        ).fetchall()
        assert len(context_summary_rows) == 6
        baseline_rows = [row for row in context_summary_rows if row[0] == "baseline"]
        assert baseline_rows
        assert all(float(row[1]) == 0.0 for row in baseline_rows)
        assert all(float(row[2]) == 1.0 for row in baseline_rows)
        intervention_rows = [row for row in context_summary_rows if row[0] != "baseline"]
        assert intervention_rows
        assert all(row[1] is not None for row in intervention_rows)
        assert all(row[2] is not None for row in intervention_rows)
        assert any(row[4] is not None for row in intervention_rows)
        assert any(row[5] is not None for row in intervention_rows)
        assert any(row[6] is not None for row in intervention_rows)
        assert any(row[7] is not None for row in intervention_rows)
        assert any(row[8] is not None for row in intervention_rows)
        trajectory_summary_rows = connection.execute(
            """
            SELECT summary_json
            FROM trajectory_segments
            WHERE study_id = ? AND segment_kind = 'context_response'
            ORDER BY context_trial_id
            """,
            [focal_study_id],
        ).fetchall()
        assert trajectory_summary_rows
        trajectory_payloads = [json.loads(row[0]) for row in trajectory_summary_rows]
        control_cost_values = [payload.get("controlCostProxy") for payload in trajectory_payloads]
        assert any(isinstance(value, (int, float)) for value in control_cost_values)
        assert any(
            isinstance(payload.get("tracePathLength"), (int, float))
            for payload in trajectory_payloads
        )
        assert any(
            isinstance(payload.get("peakGoalErrorScore"), (int, float))
            for payload in trajectory_payloads
        )
        assert any(
            isinstance(payload.get("tracePathLengthRatioToReference"), (int, float))
            for payload in trajectory_payloads
        )
        packet = export_biological_study(
            connection,
            study_id=replay_study_id,
            context_study_id=focal_study_id,
        )
        assert packet["packetKind"] == "biological_morphospace_study_v1"
        assert packet["summary"]["baselineStateCount"] == 2
        assert packet["baseline"]["counts"]["byCanonicalFamily"] == {
            "r1_mass_1c__single_center_40": 1,
            "r3_multikernel_1c__single_offset_40": 1,
        }
        assert packet["baseline"]["counts"]["byCreatureBucket"]
        assert packet["baseline"]["creatures"]["byCoherenceClass"]
        assert packet["baseline"]["states"][0]["creatureLabels"]["creatureBucket"] is not None
        assert "coherenceMean" in packet["baseline"]["states"][0]["creatureSignals"]
        assert packet["context"] is not None
        assert packet["context"]["outcomes"]["summary"]["contextTrialCount"] == 6
        by_context_kind = packet["context"]["outcomes"]["summary"]["byContextKind"]
        assert by_context_kind
        assert all("goalErrorScore" in row for row in by_context_kind)
        assert all("peakGoalErrorScore" in row for row in by_context_kind)
        assert all("cumulativeGoalErrorScore" in row for row in by_context_kind)
        assert all("bodyPlanErrorScore" in row for row in by_context_kind)
        assert all("bodyPlanClassShiftScore" in row for row in by_context_kind)
        assert all("controlCostProxy" in row for row in by_context_kind)
        assert all("tracePathLength" in row for row in by_context_kind)
        assert all("tracePathLengthRatioToReference" in row for row in by_context_kind)
        assert all("traceClassChangeCount" in row for row in by_context_kind)
        assert all("metricSummaries" in row for row in by_context_kind)
        assert all("relativeToTargetBaseline" in row for row in by_context_kind)
        assert all("relativeToMatchedBaseline" in row for row in by_context_kind)
        baseline_context_row = next(
            row for row in by_context_kind if row["contextKind"] == "baseline"
        )
        assert baseline_context_row["relativeToTargetBaseline"]["available"] is True
        assert "goalErrorScore" in baseline_context_row["metricSummaries"]
        assert "peakGoalErrorScore" in baseline_context_row["metricSummaries"]
        assert "bodyPlanErrorScore" in baseline_context_row["metricSummaries"]
        assert "tracePathLengthRatioToReference" in baseline_context_row["metricSummaries"]
        by_family_context = packet["context"]["outcomes"]["summary"][
            "byCanonicalFamilyAndContextKind"
        ]
        assert by_family_context
        assert all("metricSummaries" in row for row in by_family_context)
        assert all("relativeToMatchedBaseline" in row for row in by_family_context)
        discovery_packet = export_creature_discovery(connection, study_id=replay_study_id)
        assert discovery_packet["packetKind"] == "creature_discovery_v1"
        assert discovery_packet["summary"]["candidateCount"] == 2
        assert discovery_packet["summary"]["byCreatureBucket"]
        assert packet["fibers"]["summary"]["fiberGroupCount"] >= 1
        assert packet["universality"]["summary"]["universalityRunCount"] == 1
        assert len(packet["baseline"]["topology"]) == 1
        assert len(packet["context"]["topology"]) == 1
    finally:
        connection.close()


def test_morphospace_cli_refresh_compendium_outputs_json_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    compendium_path = _make_compendium_fixture(tmp_path)
    warehouse_path = tmp_path / "warehouse.duckdb"

    direct_payload = refresh_compendium_warehouse(
        warehouse_path=warehouse_path,
        compendium_path=compendium_path,
        label="fixture-study",
    )
    assert direct_payload["studyId"]
    assert direct_payload["statusUpdated"] == 1
    assert direct_payload["comparisonFeatureSpaceId"] == "lenia_terminal_v1"
    assert direct_payload["comparisonObservationsUpdated"] == 1
    assert direct_payload["comparisonFeatureValuesUpdated"] == len(TERMINAL_AXIS_IDS)
    assert direct_payload["commonFeatureSpaceId"] == "common_morphology_v1"
    assert direct_payload["commonObservationsUpdated"] == 1
    assert direct_payload["topologyStudyId"] is None

    connection = connect_database(warehouse_path)
    try:
        assert _scalar_int(connection, "SELECT COUNT(*) FROM studies") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM study_specimens") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM morphospace_sources") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM observations") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_spaces") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_values") == (
            len(TERMINAL_AXIS_IDS) + 12
        )
    finally:
        connection.close()

    replayed_warehouse = tmp_path / "warehouse-cli.duckdb"
    exit_code = morphospace_main(
        [
            "refresh-compendium",
            "--warehouse",
            str(replayed_warehouse),
            "--compendium",
            str(compendium_path),
            "--label",
            "fixture-study-cli",
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["studyId"]
    assert payload["statusUpdated"] == 1
    assert payload["comparisonFeatureSpaceId"] == "lenia_terminal_v1"
    assert payload["comparisonFeatureValuesUpdated"] == len(TERMINAL_AXIS_IDS)
    assert payload["commonFeatureSpaceId"] == "common_morphology_v1"
    assert payload["topologyStudyId"] is None


def test_morphospace_cli_exports_supported_warehouse_packets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    compendium_path = _make_compendium_fixture(tmp_path)
    warehouse_path = tmp_path / "warehouse.duckdb"

    refresh_payload = refresh_compendium_warehouse(
        warehouse_path=warehouse_path,
        compendium_path=compendium_path,
        label="fixture-study",
    )
    study_id = str(refresh_payload["studyId"])

    capsys.readouterr()
    assert morphospace_main(
        [
            "run-topology",
            "--warehouse",
            str(warehouse_path),
            "--study-id",
            study_id,
            "--json",
        ]
    ) == 0
    topology_payload = json.loads(capsys.readouterr().out)
    assert topology_payload["studyId"] == study_id
    assert topology_payload["topologyStudyId"]
    connection = connect_database(warehouse_path)
    try:
        topology_packet = export_topology_packet(
            connection,
            study_id=str(topology_payload["topologyStudyId"]),
        )
    finally:
        connection.close()
    assert topology_packet["summary"]["sourcePacketKind"] == "transformation_focal_packet_v1"
    assert topology_packet["summary"]["spaces"] == ["terminal_descriptor_space"]

    assert morphospace_main(
        [
            "derive-lenia-features",
            "--warehouse",
            str(warehouse_path),
            "--study-id",
            study_id,
            "--json",
        ]
    ) == 0
    lenia_payload = json.loads(capsys.readouterr().out)
    assert lenia_payload["featureSpaceId"] == "lenia_terminal_v1"
    assert lenia_payload["featureValueCount"] == len(TERMINAL_AXIS_IDS)

    assert morphospace_main(
        [
            "export-feature-matrix",
            "--warehouse",
            str(warehouse_path),
            "--feature-space-id",
            "lenia_terminal_v1",
            "--study-id",
            study_id,
            "--run-id",
            "run-1",
            "--source-algorithm",
            "discovery",
            "--json",
        ]
    ) == 0
    matrix_payload = json.loads(capsys.readouterr().out)
    assert matrix_payload["packetKind"] == "comparative_feature_matrix_v1"
    assert matrix_payload["summary"]["observationCount"] == 1
    assert matrix_payload["summary"]["axisCount"] == len(TERMINAL_AXIS_IDS)
    assert matrix_payload["summary"]["runCounts"] == {"run-1": 1}
    assert matrix_payload["observations"][0]["runId"] == "run-1"
    assert matrix_payload["observations"][0]["sourceAlgorithm"] == "discovery"
    assert len(matrix_payload["matrix"][0]) == len(TERMINAL_AXIS_IDS)

    with pytest.raises(SystemExit, match="missing numeric axis"):
        morphospace_main(
            [
                "run-topology",
                "--warehouse",
                str(warehouse_path),
                "--study-id",
                study_id,
                "--source-packet-kind",
                "atlas",
                "--json",
            ]
        )

    assert morphospace_main(
        [
            "export-biological",
            "--warehouse",
            str(warehouse_path),
            "--study-id",
            study_id,
            "--json",
        ]
    ) == 0
    biological_payload = json.loads(capsys.readouterr().out)
    assert biological_payload["packetKind"] == "biological_morphospace_study_v1"
    assert biological_payload["summary"]["baselineStateCount"] == 1

    assert morphospace_main(
        [
            "export-creature-discovery",
            "--warehouse",
            str(warehouse_path),
            "--study-id",
            study_id,
            "--json",
        ]
    ) == 0
    discovery_payload = json.loads(capsys.readouterr().out)
    assert discovery_payload["packetKind"] == "creature_discovery_v1"
    assert discovery_payload["summary"]["candidateCount"] == 1


def test_morphospace_cli_compares_feature_cohorts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    warehouse_path = tmp_path / "cohorts.duckdb"
    connection = connect_database(warehouse_path)
    try:
        study_id = register_study(
            connection,
            study_kind="fixture",
            label="cohort-fixture",
        )
        upsert_morphospace_source(
            connection,
            source_id="synthetic_fixture",
            source_kind="fixture",
            label="Synthetic fixture",
        )
        upsert_feature_space(
            connection,
            feature_space_id="fixture_space",
            feature_space_kind="fixture",
            label="Fixture feature space",
            version_label="v1",
            coordinate_policy="unit test coordinates",
            metric_json={"metric": "euclidean", "preferredValueColumn": "normalized_value"},
        )
        replace_feature_axes(
            connection,
            feature_space_id="fixture_space",
            axis_rows=[
                {
                    "axis_id": "x",
                    "axis_index": 0,
                    "axis_family": "fixture",
                    "label": "x",
                },
                {
                    "axis_id": "y",
                    "axis_index": 1,
                    "axis_family": "fixture",
                    "label": "y",
                },
            ],
        )
        context_id = register_context(
            connection,
            study_id=study_id,
            context_kind="baseline",
            label="baseline",
        )
        for specimen_id, run_id, source_algorithm, canonical_family, values in [
            (
                "fixture-left",
                "run-left-nofood",
                "manual-left",
                "left-family",
                {"x": 0.0, "y": 0.0},
            ),
            (
                "fixture-right",
                "run-right-food",
                "manual-right",
                "right-family",
                {"x": 3.0, "y": 4.0},
            ),
        ]:
            upsert_specimen(
                connection,
                {
                    "specimen_id": specimen_id,
                    "study_id": study_id,
                    "run_id": run_id,
                    "source_kind": "fixture",
                    "source_mode": "cohort-test",
                    "source_algorithm": source_algorithm,
                    "canonical_family": canonical_family,
                    "provenance_json": {},
                },
            )
            register_specimen_study(connection, study_id=study_id, specimen_id=specimen_id)
            observation_id = f"{specimen_id}-obs"
            upsert_observation(
                connection,
                observation_id=observation_id,
                specimen_id=specimen_id,
                study_id=study_id,
                source_id="synthetic_fixture",
                context_id=context_id,
                observation_kind="fixture_embedding",
            )
            replace_feature_values(
                connection,
                observation_id=observation_id,
                feature_space_id="fixture_space",
                value_rows=[
                    {"axis_id": axis_id, "raw_value": value, "normalized_value": value}
                    for axis_id, value in values.items()
                ],
            )
    finally:
        connection.close()

    assert morphospace_main(
        [
            "compare-feature-cohorts",
            "--warehouse",
            str(warehouse_path),
            "--feature-space-id",
            "fixture_space",
            "--left-label",
            "left",
            "--left-run-id-contains",
            "run-left",
            "--left-source-mode",
            "cohort-test",
            "--left-source-algorithm",
            "manual-left",
            "--left-canonical-family",
            "left-family",
            "--right-label",
            "right",
            "--right-run-id-contains",
            "run-right",
            "--right-source-mode",
            "cohort-test",
            "--right-source-algorithm",
            "manual-right",
            "--right-canonical-family",
            "right-family",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["packetKind"] == "comparative_feature_cohort_comparison_v1"
    assert payload["summary"]["left"]["observationCount"] == 1
    assert payload["summary"]["right"]["observationCount"] == 1
    assert payload["summary"]["left"]["filters"]["runIdContains"] == "run-left"
    assert payload["summary"]["left"]["filters"]["sourceAlgorithm"] == "manual-left"
    assert payload["summary"]["right"]["filters"]["canonicalFamily"] == "right-family"
    assert payload["summary"]["crossDistance"]["count"] == 1
    assert payload["summary"]["crossDistance"]["mean"] == 5.0
    assert payload["summary"]["leftToRightNearestDistance"]["max"] == 5.0
    assert payload["topAxisDeltas"][0]["axisId"] == "y"
    assert payload["topAxisDeltas"][0]["deltaRightMinusLeft"] == 4.0
    assert payload["nearestMatches"]["leftToRight"][0]["distance"] == 5.0
    assert payload["nearestMatches"]["leftToRight"][0]["left"]["specimenId"] == "fixture-left"
    assert payload["nearestMatches"]["leftToRight"][0]["right"]["specimenId"] == "fixture-right"
    assert payload["nearestMatches"]["leftToRight"][0]["axisDeltas"][0]["axisId"] == "y"


def test_feature_tda_profile_bounds_thresholded_large_cohorts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warehouse_path = tmp_path / "warehouse.duckdb"
    connection = connect_database(warehouse_path)
    calls: list[dict[str, Any]] = []

    def fake_ripser(matrix: np.ndarray, **kwargs: Any) -> dict[str, Any]:
        calls.append({"shape": tuple(matrix.shape), "kwargs": kwargs})
        return {
            "dgms": [
                np.asarray([[0.0, 1.0], [0.0, np.inf]], dtype=np.float64),
                np.asarray([[0.2, 0.4]], dtype=np.float64),
            ]
        }

    monkeypatch.setattr(feature_tda_profile_module, "ripser", fake_ripser)
    monkeypatch.setitem(
        feature_tda_profile_module.PROFILE_PRESETS,
        "unit",
        {
            "exact_max_observations": 4,
            "threshold_max_observations": 4,
            "threshold_sample_points": 5,
            "landmark_counts": (3,),
            "subsample_sizes": (4,),
            "subsample_replicates": 2,
            "threshold_quantiles": (0.50,),
            "pairwise_sample_points": 5,
            "min_stratum_size": 99,
            "max_strata": 0,
        },
    )
    try:
        study_id = register_study(
            connection,
            study_kind="fixture",
            label="tda-fixture",
            run_id="run-tda",
        )
        context_id = register_context(
            connection,
            study_id=study_id,
            context_kind="baseline",
            label="fixture",
        )
        upsert_morphospace_source(
            connection,
            source_id="synthetic_fixture",
            source_kind="fixture",
            label="Synthetic fixture",
        )
        upsert_feature_space(
            connection,
            feature_space_id="tda_fixture_space",
            feature_space_kind="fixture",
            label="TDA fixture space",
            version_label="v1",
            coordinate_policy="unit-test",
        )
        replace_feature_axes(
            connection,
            feature_space_id="tda_fixture_space",
            axis_rows=[
                {
                    "axis_id": "x",
                    "axis_index": 0,
                    "axis_family": "fixture",
                    "label": "x",
                    "units": None,
                    "metadata_json": {},
                },
                {
                    "axis_id": "y",
                    "axis_index": 1,
                    "axis_family": "fixture",
                    "label": "y",
                    "units": None,
                    "metadata_json": {},
                },
            ],
        )
        for index in range(10):
            specimen_id = f"specimen-{index}"
            upsert_specimen(
                connection,
                {
                    "specimen_id": specimen_id,
                    "study_id": study_id,
                    "run_id": "run-tda",
                    "source_kind": "fixture",
                    "source_mode": "unit",
                    "source_algorithm": "manual",
                    "provenance_json": {},
                },
            )
            register_specimen_study(
                connection,
                study_id=study_id,
                specimen_id=specimen_id,
            )
            observation_id = f"observation-{index}"
            upsert_observation(
                connection,
                observation_id=observation_id,
                specimen_id=specimen_id,
                study_id=study_id,
                source_id="synthetic_fixture",
                context_id=context_id,
                observation_kind="fixture_embedding",
            )
            replace_feature_values(
                connection,
                observation_id=observation_id,
                feature_space_id="tda_fixture_space",
                value_rows=[
                    {
                        "axis_id": "x",
                        "raw_value": float(index),
                        "normalized_value": float(index) / 10.0,
                    },
                    {
                        "axis_id": "y",
                        "raw_value": float(index % 3),
                        "normalized_value": float(index % 3) / 3.0,
                    },
                ],
            )

        payload = feature_tda_profile_module.run_feature_tda_profile(
            connection,
            feature_space_id="tda_fixture_space",
            profile="unit",
        )
    finally:
        connection.close()

    assert payload["summary"]["observationCount"] == 10
    assert payload["exact"]["status"] == "skipped"
    assert payload["summary"]["thresholdMaxObservations"] == 4
    assert payload["summary"]["thresholdSamplePoints"] == 5
    threshold_case = payload["thresholded"][0]
    assert threshold_case["pointCount"] == 5
    assert threshold_case["sample"]["sourcePointCount"] == 10
    assert threshold_case["sample"]["samplePointCount"] == 5
    assert calls[0]["shape"] == (5, 2)
    assert calls[0]["kwargs"]["thresh"] == threshold_case["threshold"]
    assert threshold_case["caseKind"] == "thresholded_vietoris_rips"
    assert payload["landmarks"][0]["caseKind"] == "deterministic_greedy_landmark"
    assert payload["subsamples"][0]["tda"]["caseKind"] == "fixed_random_subsample"
    assert payload["subsampleSummary"]["4"]["replicateCount"] == 2
    assert payload["subsampleSummary"]["4"]["h1CountGe010"]["count"] == 2
    claim_status = {row["id"]: row["status"] for row in payload["claimLevels"]}
    assert claim_status["deterministic_landmark_replay"] == "measured"
    assert claim_status["stochastic_subsample_robustness"] == "measured"
    assert claim_status["paper_level_topological_stability"] == (
        "not_established_by_single_packet"
    )


def test_feature_tda_full_profile_declares_strict_subsample_ladder() -> None:
    full = feature_tda_profile_module.PROFILE_PRESETS["full"]

    assert full["subsample_sizes"] == (1024, 2048, 4096, 8192, 16384)
    assert full["subsample_replicates"] >= 5


def test_common_morphology_point_cloud_features_distinguish_shapes() -> None:
    elongated = np.asarray(
        [
            [0.0, 0.0],
            [4.0, 0.0],
            [2.0, 0.2],
            [2.0, -0.2],
        ],
        dtype=np.float64,
    )
    roundish = np.asarray(
        [
            [-1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [0.0, -1.0],
        ],
        dtype=np.float64,
    )

    elongated_features = point_cloud_shape_features(elongated)
    roundish_features = point_cloud_shape_features(roundish)

    assert elongated_features["elongation"] > roundish_features["elongation"]
    assert elongated_features["anisotropy"] > roundish_features["anisotropy"]
    assert roundish_features["radial_symmetry"] > elongated_features["radial_symmetry"]
    assert set(elongated_features) == set(COMMON_MORPHOLOGY_AXIS_IDS)


def _write_dryad_fish_fixture(root: Path) -> None:
    gpa_root = root / "extracted" / "gpa" / "Slicer_GPA_output"
    provenance_root = root / "provenance"
    gpa_root.mkdir(parents=True)
    provenance_root.mkdir(parents=True)
    _write_json(
        provenance_root / "source.json",
        {
            "dataset_id": "dryad-fish-body-shape-20240112",
            "title": (
                "Data for: Phylogenetic structure of body shape in a diverse "
                "inland ichthyofauna"
            ),
            "doi": "10.5061/dryad.n2z34tn2t",
            "url": "https://datadryad.org/dataset/doi:10.5061/dryad.n2z34tn2t",
            "publication_date": "2024-01-12",
            "license": "CC0-1.0",
            "authors": ["Kevin Torgersen"],
        },
    )
    (gpa_root / "pcScores.csv").write_text(
        "\n".join(
            [
                "Sample_name,PC 1,PC 2",
                "Alosa alabamae fixture,1.0,0.0",
                "Ameiurus melas fixture,3.0,0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (gpa_root / "eigenvalues.csv").write_text(
        "\n".join(
            [
                "PC 1,2.0",
                "PC 2,1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (gpa_root / "OutputData.csv").write_text(
        "Sample_name,proc_dist,centeroid,"
        "LM 1_X,LM 1_Y,LM 1_Z,"
        "LM 2_X,LM 2_Y,LM 2_Z,"
        "LM 3_X,LM 3_Y,LM 3_Z,"
        "LM 4_X,LM 4_Y,LM 4_Z\n"
        "Alosa alabamae fixture,0.1,10.0,"
        "0.0,0.0,0.0,"
        "4.0,0.0,0.0,"
        "2.0,0.2,0.0,"
        "2.0,-0.2,0.0\n"
        "Ameiurus melas fixture,0.2,12.0,"
        "-1.0,0.0,0.0,"
        "0.0,1.0,0.0,"
        "1.0,0.0,0.0,"
        "0.0,-1.0,0.0\n",
        encoding="utf-8",
    )


def _write_distinct_dryad_fish_fixture(root: Path) -> None:
    _write_dryad_fish_fixture(root)
    gpa_root = root / "extracted" / "gpa" / "Slicer_GPA_output"
    (gpa_root / "pcScores.csv").write_text(
        "\n".join(
            [
                "Sample_name,PC 1,PC 2",
                "Cyprinella lutrensis fixture,-4.0,2.0",
                "Lepomis cyanellus fixture,6.0,-3.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (gpa_root / "OutputData.csv").write_text(
        "Sample_name,proc_dist,centeroid,"
        "LM 1_X,LM 1_Y,LM 1_Z,"
        "LM 2_X,LM 2_Y,LM 2_Z,"
        "LM 3_X,LM 3_Y,LM 3_Z,"
        "LM 4_X,LM 4_Y,LM 4_Z\n"
        "Cyprinella lutrensis fixture,0.3,14.0,"
        "-8.0,-1.0,0.0,"
        "0.0,6.0,0.0,"
        "4.0,-3.0,0.0,"
        "14.0,2.0,0.0\n"
        "Lepomis cyanellus fixture,0.4,16.0,"
        "0.0,0.0,0.0,"
        "0.0,4.0,0.0,"
        "0.0,8.0,0.0,"
        "8.0,0.0,0.0\n",
        encoding="utf-8",
    )


def _embryomaker_node_row(
    *,
    x: float,
    y: float,
    z: float,
    icel: int,
    tipus: int = 3,
) -> str:
    values = [0.0] * 35
    values[0] = x
    values[1] = y
    values[2] = z
    values[4] = 0.25
    values[5] = 0.5
    values[28] = float(tipus)
    values[29] = float(icel)
    return " ".join(f"{value:.16E}" for value in values)


def _write_embryomaker_snapshot_fixture(path: Path, *, offset: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "THIS FILE WAS WRITTEN IN THE FORMAT OF THE TEST VERSION",
                "fixture-run",
                "35 number of node parameters",
                "5 number of global variables",
                "",
                "30 functions",
                "",
                "0 unused",
                "",
                "parameters",
                "",
                " 1 1.0000000000000000E+01 getot",
                "10 3.0000000000000000E+00 nd",
                "13 1.0000000000000000E+00 rtime",
                "18 3.0000000000000000E+00 ncels",
                "19 2.0000000000000000E+00 ng",
                "",
                "G matrix: gene expression",
                "",
                "node  gene 1                 gene 2    etc...",
                "1 1.0000000000000000E+00 0.0000000000000000E+00",
                "2 0.0000000000000000E+00 1.0000000000000000E+00",
                "3 1.0000000000000000E+00 0.0000000000000000E+00",
                "",
                "node properties",
                "",
                "x y z ...",
                _embryomaker_node_row(x=offset, y=0.0, z=0.0, icel=1),
                _embryomaker_node_row(x=offset + 1.0, y=0.0, z=0.0, icel=2),
                _embryomaker_node_row(x=offset + 0.0, y=1.0, z=0.0, icel=3),
                "",
                "node properties at time 0 (nodeo)",
                "",
                "x y z ...",
                _embryomaker_node_row(x=offset, y=0.0, z=0.0, icel=1),
                _embryomaker_node_row(x=offset + 1.0, y=0.0, z=0.0, icel=2),
                _embryomaker_node_row(x=offset + 0.0, y=1.0, z=0.0, icel=3),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_morphospace_import_dryad_fish_populates_comparison_layer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_root = tmp_path / "dryad-fish"
    _write_dryad_fish_fixture(dataset_root)
    warehouse_path = tmp_path / "warehouse.duckdb"

    direct_payload = import_dryad_fish_dataset(
        warehouse_path=warehouse_path,
        dataset_root=dataset_root,
        label="fish-fixture",
    )
    assert direct_payload["specimenCount"] == 2
    assert direct_payload["observationCount"] == 2
    assert direct_payload["axisCount"] == 2
    assert direct_payload["featureValueCount"] == 4

    connection = connect_database(warehouse_path)
    try:
        assert _scalar_int(connection, "SELECT COUNT(*) FROM morphospace_sources") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM observations") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_spaces") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_axes") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_values") == 4
        axis_metadata = json.loads(
            connection.execute(
                """
                SELECT metadata_json
                FROM feature_axes
                WHERE feature_space_id = 'fish_gpa_pc_v1' AND axis_id = 'pc_01'
                """
            ).fetchone()[0]
        )
        assert axis_metadata["explainedVariance"] == 2.0 / 3.0
        normalized_rows = connection.execute(
            """
            SELECT axis_id, raw_value, normalized_value
            FROM comparison_feature_values_vw
            WHERE axis_id IN ('pc_01', 'pc_02')
            ORDER BY axis_id, raw_value
            """
        ).fetchall()
        assert normalized_rows == [
            ("pc_01", 1.0, -1.0),
            ("pc_01", 3.0, 1.0),
            ("pc_02", 0.0, 0.0),
            ("pc_02", 0.0, 0.0),
        ]
        canonical_families = {
            row[0]
            for row in connection.execute(
                "SELECT canonical_family FROM specimens ORDER BY canonical_family"
            ).fetchall()
        }
        assert canonical_families == {"Alosa alabamae", "Ameiurus melas"}
    finally:
        connection.close()

    replayed_warehouse = tmp_path / "warehouse-cli.duckdb"
    assert morphospace_main(
        [
            "import-dryad-fish",
            "--warehouse",
            str(replayed_warehouse),
            "--dataset-root",
            str(dataset_root),
            "--label",
            "fish-fixture-cli",
            "--json",
        ]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["specimenCount"] == 2
    assert cli_payload["featureSpaceId"] == "fish_gpa_pc_v1"

    assert morphospace_main(
        [
            "export-feature-matrix",
            "--warehouse",
            str(replayed_warehouse),
            "--feature-space-id",
            "fish_gpa_pc_v1",
            "--json",
        ]
    ) == 0
    matrix_payload = json.loads(capsys.readouterr().out)
    assert matrix_payload["packetKind"] == "comparative_feature_matrix_v1"
    assert matrix_payload["summary"]["observationCount"] == 2
    assert matrix_payload["summary"]["axisCount"] == 2
    assert matrix_payload["matrix"] == [[-1.0, 0.0], [1.0, 0.0]]

    assert morphospace_main(
        [
            "run-feature-tda",
            "--warehouse",
            str(replayed_warehouse),
            "--feature-space-id",
            "fish_gpa_pc_v1",
            "--max-homology-dim",
            "1",
            "--summary-only",
            "--json",
        ]
    ) == 0
    tda_payload = json.loads(capsys.readouterr().out)
    assert tda_payload["packetKind"] == "comparative_feature_tda_v1"
    assert tda_payload["summary"]["backend"] == "ripser-euclidean"
    assert tda_payload["summary"]["pairwiseDistance"]["count"] == 1
    assert tda_payload["topology"]["summaries"][0]["featureCount"] == 2
    assert "observations" not in tda_payload


def test_morphospace_import_embryomaker_snapshots_populates_comparison_layer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot_root = tmp_path / "embryomaker"
    _write_embryomaker_snapshot_fixture(snapshot_root / "IC1.fixture.output.dat")
    _write_embryomaker_snapshot_fixture(
        snapshot_root / "IC2.fixture.output.dat",
        offset=2.0,
    )
    warehouse_path = tmp_path / "warehouse.duckdb"

    direct_payload = import_embryomaker_snapshots_dataset(
        warehouse_path=warehouse_path,
        snapshot_roots=[snapshot_root],
        label="embryomaker-fixture",
    )
    assert direct_payload["snapshotCount"] == 2
    assert direct_payload["observationCount"] == 2
    assert direct_payload["axisCount"] == 7
    assert direct_payload["featureValueCount"] == 14
    assert direct_payload["familyCounts"] == {"IC1": 1, "IC2": 1}

    replay_payload = import_embryomaker_snapshots_dataset(
        warehouse_path=warehouse_path,
        snapshot_roots=[snapshot_root],
    )
    assert replay_payload["studyId"] == direct_payload["studyId"]
    assert replay_payload["observationCount"] == 2

    connection = connect_database(warehouse_path)
    try:
        assert _scalar_int(connection, "SELECT COUNT(*) FROM morphospace_sources") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM studies") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM observations") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_spaces") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_axes") == 7
        assert _scalar_int(connection, "SELECT COUNT(*) FROM feature_values") == 14
        families = {
            row[0]
            for row in connection.execute(
                "SELECT canonical_family FROM specimens ORDER BY canonical_family"
            ).fetchall()
        }
        assert families == {"IC1", "IC2"}
    finally:
        connection.close()

    replayed_warehouse = tmp_path / "warehouse-cli.duckdb"
    assert morphospace_main(
        [
            "import-embryomaker-snapshots",
            "--warehouse",
            str(replayed_warehouse),
            "--snapshot-root",
            str(snapshot_root),
            "--label",
            "embryomaker-fixture-cli",
            "--limit",
            "1",
            "--json",
        ]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["snapshotCount"] == 1
    assert cli_payload["featureSpaceId"] == "embryomaker_legacy_snapshot_v1"

    common_payload = derive_common_morphology_packet(
        warehouse_path=warehouse_path,
    )
    assert common_payload["featureSpaceId"] == COMMON_MORPHOLOGY_FEATURE_SPACE_ID
    assert common_payload["observationCount"] == 2
    assert common_payload["sourceCounts"] == {"embryomaker_legacy_snapshots": 2}

    assert morphospace_main(
        [
            "export-feature-matrix",
            "--warehouse",
            str(warehouse_path),
            "--feature-space-id",
            COMMON_MORPHOLOGY_FEATURE_SPACE_ID,
            "--source-id",
            "embryomaker_legacy_snapshots",
            "--json",
        ]
    ) == 0
    matrix_payload = json.loads(capsys.readouterr().out)
    assert matrix_payload["summary"]["observationCount"] == 2
    assert matrix_payload["summary"]["axisCount"] == len(COMMON_MORPHOLOGY_AXIS_IDS)


def test_morphospace_import_reference_bundle_registers_external_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle_root = tmp_path / "morphospace-v6"
    bundle_root.mkdir()
    (bundle_root / "within_substrate_topology.json").write_text(
        json.dumps(
            {
                "packetKind": "within_substrate_topology_v1",
                "summary": {"spaceCount": 2},
            }
        ),
        encoding="utf-8",
    )
    np.save(bundle_root / "dist_lenia.npy", np.asarray([[0.0, 1.0], [1.0, 0.0]]))
    warehouse_path = tmp_path / "warehouse.duckdb"

    direct_payload = import_reference_bundle_dataset(
        warehouse_path=warehouse_path,
        bundle_root=bundle_root,
        label="v6-fixture",
    )
    assert direct_payload["artifactCount"] == 2
    assert direct_payload["jsonObjectCount"] == 1
    assert direct_payload["npyArrayCount"] == 1
    assert direct_payload["artifactKinds"] == {"reference_json": 1, "reference_npy": 1}

    connection = connect_database(warehouse_path)
    try:
        assert _scalar_int(connection, "SELECT COUNT(*) FROM studies") == 1
        assert _scalar_int(connection, "SELECT COUNT(*) FROM artifacts") == 2
        assert _scalar_int(connection, "SELECT COUNT(*) FROM raw_json_objects") == 1
        metadata_row = connection.execute(
            """
            SELECT metadata_json
            FROM artifacts
            WHERE artifact_kind = 'reference_npy'
            """
        ).fetchone()
        assert metadata_row is not None
        metadata = json.loads(metadata_row[0])
        assert metadata["arrayShape"] == [2, 2]
        assert metadata["arrayDtype"] == "float64"
    finally:
        connection.close()

    replayed_warehouse = tmp_path / "warehouse-cli.duckdb"
    assert morphospace_main(
        [
            "import-reference-bundle",
            "--warehouse",
            str(replayed_warehouse),
            "--bundle-root",
            str(bundle_root),
            "--label",
            "v6-fixture-cli",
            "--json",
        ]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["artifactCount"] == 2
    assert cli_payload["sourceId"] == "external_morphospace_reference_bundles"


def test_scoped_common_morphology_uses_metadata_roots_for_other_fish_studies(
    tmp_path: Path,
) -> None:
    dataset_root_a = tmp_path / "dryad-fish-a"
    dataset_root_b = tmp_path / "dryad-fish-b"
    _write_dryad_fish_fixture(dataset_root_a)
    _write_distinct_dryad_fish_fixture(dataset_root_b)
    compendium_path = _make_compendium_fixture(tmp_path)
    warehouse_path = tmp_path / "warehouse.duckdb"

    refresh_compendium_warehouse(
        warehouse_path=warehouse_path,
        compendium_path=compendium_path,
        label="fixture-study",
    )
    fish_payload_a = import_dryad_fish_dataset(
        warehouse_path=warehouse_path,
        dataset_root=dataset_root_a,
        label="fish-fixture-a",
    )
    import_dryad_fish_dataset(
        warehouse_path=warehouse_path,
        dataset_root=dataset_root_b,
        label="fish-fixture-b",
    )

    direct_payload = derive_common_morphology_packet(warehouse_path=warehouse_path)
    assert direct_payload["observationCount"] == 5
    assert direct_payload["sourceCounts"] == {
        "dryad_fish_body_shape_20240112": 4,
        "lenia_swarm": 1,
    }

    connection = connect_database(warehouse_path)
    try:
        axis_metadata_before = _common_morphology_axis_metadata(connection)
    finally:
        connection.close()

    scoped_payload = derive_common_morphology_packet(
        warehouse_path=warehouse_path,
        dryad_fish_root=dataset_root_a,
        study_id=str(fish_payload_a["studyId"]),
    )
    assert scoped_payload["observationCount"] == 2
    assert scoped_payload["sourceCounts"] == direct_payload["sourceCounts"]

    connection = connect_database(warehouse_path)
    try:
        assert _common_morphology_axis_metadata(connection) == axis_metadata_before
        assert (
            _scalar_int(
                connection,
                """
                SELECT COUNT(*)
                FROM observations
                WHERE observation_kind = 'common_point_cloud_morphology'
                """,
            )
            == 5
        )
    finally:
        connection.close()


def test_morphospace_cli_derives_common_morphology_space(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset_root = tmp_path / "dryad-fish"
    _write_dryad_fish_fixture(dataset_root)
    compendium_path = _make_compendium_fixture(tmp_path)
    warehouse_path = tmp_path / "warehouse.duckdb"

    refresh_compendium_warehouse(
        warehouse_path=warehouse_path,
        compendium_path=compendium_path,
        label="fixture-study",
    )
    fish_payload = import_dryad_fish_dataset(
        warehouse_path=warehouse_path,
        dataset_root=dataset_root,
        label="fish-fixture",
    )
    direct_payload = derive_common_morphology_packet(
        warehouse_path=warehouse_path,
        dryad_fish_root=dataset_root,
    )
    assert direct_payload["featureSpaceId"] == COMMON_MORPHOLOGY_FEATURE_SPACE_ID
    assert direct_payload["observationCount"] == 3
    assert direct_payload["axisCount"] == len(COMMON_MORPHOLOGY_AXIS_IDS)
    assert direct_payload["featureValueCount"] == 3 * len(COMMON_MORPHOLOGY_AXIS_IDS)
    assert direct_payload["sourceCounts"] == {
        "dryad_fish_body_shape_20240112": 2,
        "lenia_swarm": 1,
    }

    connection = connect_database(warehouse_path)
    try:
        axis_metadata_before = {
            row[0]: json.loads(row[1])
            for row in connection.execute(
                """
                SELECT axis_id, metadata_json
                FROM feature_axes
                WHERE feature_space_id = 'common_morphology_v1'
                ORDER BY axis_id
                """
            ).fetchall()
        }
        assert (
            _scalar_int(
                connection,
                """
                SELECT COUNT(*)
                FROM feature_values
                WHERE feature_space_id = 'common_morphology_v1'
                """,
            )
            == 3 * len(COMMON_MORPHOLOGY_AXIS_IDS)
        )
        axis_ids = [
            row[0]
            for row in connection.execute(
                """
                SELECT axis_id
                FROM feature_axes
                WHERE feature_space_id = 'common_morphology_v1'
                ORDER BY axis_index
                """
            ).fetchall()
        ]
        assert tuple(axis_ids) == COMMON_MORPHOLOGY_AXIS_IDS
    finally:
        connection.close()

    scoped_payload = derive_common_morphology_packet(
        warehouse_path=warehouse_path,
        dryad_fish_root=dataset_root,
        study_id=str(fish_payload["studyId"]),
    )
    assert scoped_payload["observationCount"] == 2
    assert scoped_payload["sourceCounts"] == direct_payload["sourceCounts"]

    connection = connect_database(warehouse_path)
    try:
        axis_metadata_after = {
            row[0]: json.loads(row[1])
            for row in connection.execute(
                """
                SELECT axis_id, metadata_json
                FROM feature_axes
                WHERE feature_space_id = 'common_morphology_v1'
                ORDER BY axis_id
                """
            ).fetchall()
        }
        assert axis_metadata_after == axis_metadata_before
        assert (
            _scalar_int(
                connection,
                """
                SELECT COUNT(*)
                FROM observations
                WHERE observation_kind = 'common_point_cloud_morphology'
                """
            )
            == 3
        )
    finally:
        connection.close()

    assert morphospace_main(
        [
            "derive-common-morphology",
            "--warehouse",
            str(warehouse_path),
            "--dryad-fish-root",
            str(dataset_root),
            "--json",
        ]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["observationCount"] == 3
    assert cli_payload["sourceCounts"]["dryad_fish_body_shape_20240112"] == 2

    assert morphospace_main(
        [
            "export-feature-matrix",
            "--warehouse",
            str(warehouse_path),
            "--feature-space-id",
            COMMON_MORPHOLOGY_FEATURE_SPACE_ID,
            "--json",
        ]
    ) == 0
    matrix_payload = json.loads(capsys.readouterr().out)
    assert matrix_payload["summary"]["observationCount"] == 3
    assert matrix_payload["summary"]["axisCount"] == len(COMMON_MORPHOLOGY_AXIS_IDS)
    assert matrix_payload["summary"]["sourceCounts"] == {
        "dryad_fish_body_shape_20240112": 2,
        "lenia_swarm": 1,
    }

    assert morphospace_main(
        [
            "compare-feature-cohorts",
            "--warehouse",
            str(warehouse_path),
            "--feature-space-id",
            COMMON_MORPHOLOGY_FEATURE_SPACE_ID,
            "--left-label",
            "lenia",
            "--left-source-id",
            "lenia_swarm",
            "--right-label",
            "fish",
            "--right-source-id",
            "dryad_fish_body_shape_20240112",
            "--json",
        ]
    ) == 0
    comparison_payload = json.loads(capsys.readouterr().out)
    assert comparison_payload["packetKind"] == "comparative_feature_cohort_comparison_v1"
    assert comparison_payload["summary"]["left"]["observationCount"] == 1
    assert comparison_payload["summary"]["right"]["observationCount"] == 2
    assert comparison_payload["summary"]["crossDistance"]["count"] == 2
