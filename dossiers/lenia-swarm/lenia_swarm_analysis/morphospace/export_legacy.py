from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from duckdb import DuckDBPyConnection

from lenia_swarm_analysis.transform.atlas import build_transformation_atlas_packet
from lenia_swarm_analysis.transform.family_comparison import (
    build_transformation_family_comparison_packet,
)
from lenia_swarm_analysis.transform.focal import (
    _baseline_summary,
    _condition_summary,
)
from lenia_swarm_analysis.transform.topology_packet import build_transformation_topology_packet
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    DEVELOPMENTAL_AXIS_SPECS,
    TERMINAL_AXIS_IDS,
    TERMINAL_AXIS_SPECS,
)


def _export_baseline_rows(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not trials:
        return []
    if all(isinstance(trial.get("meanMetrics"), dict) for trial in trials):
        return sorted(
            trials,
            key=lambda row: (str(row.get("environmentLabel")), int(row.get("rowCount", 0))),
        )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        environment = trial.get("environmentLabel")
        metrics = trial.get("metrics")
        if not isinstance(environment, str) or not isinstance(metrics, dict):
            continue
        grouped.setdefault(environment, []).append(metrics)
    return [
        _baseline_summary(environment_label=environment, rows=rows)
        for environment, rows in sorted(grouped.items())
    ]


def _export_response_rows(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not trials:
        return []
    if all(isinstance(trial.get("meanMetrics"), dict) for trial in trials):
        return sorted(
            trials,
            key=lambda row: (
                str(row.get("environmentLabel")),
                str(row.get("perturbationLabel")),
            ),
        )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for trial in trials:
        environment = trial.get("environmentLabel")
        perturbation = trial.get("perturbationLabel")
        metrics = trial.get("metrics")
        if (
            not isinstance(environment, str)
            or not isinstance(perturbation, str)
            or not isinstance(metrics, dict)
        ):
            continue
        grouped.setdefault((environment, perturbation), []).append(metrics)
    return [
        _condition_summary(
            environment_label=environment,
            perturbation_label=perturbation,
            rows=rows,
        )
        for (environment, perturbation), rows in sorted(grouped.items())
    ]


def _specimen_rows(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT specimens.specimen_id, specimens.run_id, specimens.campaign_id,
               specimens.source_kind, specimens.family_kind, specimens.regime_family,
               specimens.geometry_family, specimens.canonical_family, specimens.provenance_json
        FROM study_specimens
        JOIN specimens USING (specimen_id)
        WHERE study_specimens.study_id = ?
        ORDER BY specimen_id
        """,
        [study_id],
    ).fetchall()
    resolved: list[dict[str, Any]] = []
    for row in rows:
        provenance = json.loads(row[8]) if row[8] else {}
        resolved.append(
            {
                "specimenId": row[0],
                "runId": row[1],
                "campaignId": row[2],
                "sourceKind": row[3],
                "familyKind": row[4],
                "regimeFamily": row[5],
                "geometryFamily": row[6],
                "canonicalFamily": row[7],
                "provenance": provenance,
            }
        )
    return resolved


def export_replay_packet(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, Any]:
    specimens = _specimen_rows(connection, study_id=study_id)
    rows: list[dict[str, Any]] = []
    for specimen in specimens:
        specimen_id = specimen["specimenId"]
        terminal_axes = {
            axis_id: value
            for axis_id, value in connection.execute(
                """
                SELECT axis_id, raw_value FROM specimen_axes
                WHERE specimen_id = ? AND axis_family = 'terminal'
                ORDER BY axis_id
                """,
                [specimen_id],
            ).fetchall()
        }
        developmental_axes = {
            axis_id: value
            for axis_id, value in connection.execute(
                """
                SELECT axis_id, raw_value FROM specimen_axes
                WHERE specimen_id = ? AND axis_family = 'developmental'
                ORDER BY axis_id
                """,
                [specimen_id],
            ).fetchall()
        }
        steps = [
            int(row[0])
            for row in connection.execute(
                """
                SELECT step FROM development_samples
                WHERE specimen_id = ?
                ORDER BY step
                """,
                [specimen_id],
            ).fetchall()
        ]
        trace_axes: dict[str, list[float]] = {}
        for axis_id, _step, raw_value in connection.execute(
            """
            SELECT axis_id, step, raw_value
            FROM development_sample_axes
            WHERE specimen_id = ?
            ORDER BY axis_id, step
            """,
            [specimen_id],
        ).fetchall():
            trace_axes.setdefault(str(axis_id), []).append(float(raw_value))
        provenance = specimen["provenance"]
        rows.append(
            {
                "specimenId": specimen_id,
                "specimenName": provenance.get("specimenName", specimen_id),
                "runId": specimen["runId"],
                "campaignId": specimen["campaignId"],
                "sourceKind": specimen["sourceKind"],
                "sourceRunId": provenance.get("sourceRunId", specimen["runId"]),
                "sourceCampaignId": provenance.get("sourceCampaignId", specimen["campaignId"]),
                "sourceInputPath": provenance.get("sourceInputPath", ""),
                "sourceMode": provenance.get("sourceMode"),
                "sourceAlgorithm": provenance.get("sourceAlgorithm"),
                "regimeFamily": specimen["regimeFamily"],
                "geometryFamily": specimen["geometryFamily"],
                "canonicalFamily": specimen["canonicalFamily"],
                "familyKind": specimen["familyKind"],
                "initialConditionFamily": provenance.get("initialConditionFamily", "unknown"),
                "replayRunId": provenance.get("replayRunId", specimen["runId"]),
                "replaySteps": provenance.get("replaySteps", 0),
                "recordEvery": provenance.get("recordEvery", 0),
                "includeInitial": provenance.get("includeInitial", False),
                "sampleCount": len(steps),
                "capturedSteps": steps,
                "developmentTracePath": provenance.get("developmentTracePath"),
                "developmentFramesDir": provenance.get("developmentFramesDir"),
                "resultsPath": provenance.get(
                    "resultsPath", specimen["provenance"].get("resultsPath", "")
                ),
                "terminal": provenance.get("terminal"),
                "trajectory": provenance.get("trajectory"),
                "terminalAxes": terminal_axes,
                "transformedTerminalAxes": {
                    axis_id: value
                    for axis_id, value in connection.execute(
                        """
                        SELECT axis_id, transformed_value FROM specimen_axes
                        WHERE specimen_id = ? AND axis_family = 'terminal'
                        ORDER BY axis_id
                        """,
                        [specimen_id],
                    ).fetchall()
                },
                "developmentalAxes": developmental_axes,
                "transformedDevelopmentalAxes": {
                    axis_id: value
                    for axis_id, value in connection.execute(
                        """
                        SELECT axis_id, transformed_value FROM specimen_axes
                        WHERE specimen_id = ? AND axis_family = 'developmental'
                        ORDER BY axis_id
                        """,
                        [specimen_id],
                    ).fetchall()
                },
                "traceSteps": steps,
                "traceAxes": trace_axes,
                "traceCenterVelocity": trace_axes.get("center_velocity", []),
            }
        )
    return {
        "version": 1,
        "packetKind": "transformation_replay_packet_v1",
        "sourceArtifact": f"duckdb://study/{study_id}",
        "summary": {
            "specimenCount": len(rows),
            "terminalAxisCount": len(TERMINAL_AXIS_IDS),
            "developmentalAxisCount": len(DEVELOPMENTAL_AXIS_IDS),
            "familyKinds": sorted(
                {str(row["familyKind"]) for row in rows if row["familyKind"] is not None}
            ),
            "regimeFamilies": sorted(
                {str(row["regimeFamily"]) for row in rows if row["regimeFamily"] is not None}
            ),
            "geometryFamilies": sorted(
                {str(row["geometryFamily"]) for row in rows if row["geometryFamily"] is not None}
            ),
            "canonicalFamilies": sorted(
                {str(row["canonicalFamily"]) for row in rows if row["canonicalFamily"] is not None}
            ),
        },
        "groupCounts": {
            "familyKind": _counts(rows, "familyKind"),
            "regimeFamily": _counts(rows, "regimeFamily"),
            "geometryFamily": _counts(rows, "geometryFamily"),
            "canonicalFamily": _counts(rows, "canonicalFamily"),
        },
        "terminalAxes": list(TERMINAL_AXIS_SPECS),
        "developmentalAxes": list(DEVELOPMENTAL_AXIS_SPECS),
        "specimens": rows,
    }


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def export_atlas_packet(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    top_exemplars_per_axis: int,
    baseline_atlas_path: Path | None = None,
) -> dict[str, Any]:
    replay_packet = export_replay_packet(connection, study_id=study_id)
    with tempfile.TemporaryDirectory(prefix="morphospace-atlas-") as tmpdir:
        replay_path = Path(tmpdir) / "replay.json"
        replay_path.write_text(
            json.dumps(replay_packet, indent=2, sort_keys=True), encoding="utf-8"
        )
        packet = build_transformation_atlas_packet(
            replay_packet_path=replay_path,
            baseline_atlas_path=baseline_atlas_path,
            top_exemplars_per_axis=top_exemplars_per_axis,
        )
    packet["sourceArtifact"] = f"duckdb://study/{study_id}"
    return packet


def export_focal_packet(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, Any]:
    specimens = _specimen_rows(connection, study_id=study_id)
    packet_specimens: list[dict[str, Any]] = []
    skipped_specimens: list[dict[str, str]] = []
    perturbation_rows = connection.execute(
        """
        SELECT trial_id, specimen_id, phase_name, environment, perturbation, raw_response_json
        FROM perturbation_trials
        WHERE study_id = ?
        ORDER BY specimen_id, environment, perturbation
        """,
        [study_id],
    ).fetchall()
    grouped_trials: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for trial_id, specimen_id, phase_name, environment, perturbation, raw_json in perturbation_rows:
        grouped_trials.setdefault(str(specimen_id), []).append(
            (
                str(trial_id),
                str(phase_name) if phase_name is not None else "",
                str(environment),
                str(perturbation),
                str(raw_json),
            )
        )
    for specimen in specimens:
        specimen_id = specimen["specimenId"]
        raw_axes = {
            axis_id: value
            for axis_id, value in connection.execute(
                """
                SELECT axis_id, raw_value
                FROM specimen_axes
                WHERE specimen_id = ?
                ORDER BY axis_id
                """,
                [specimen_id],
            ).fetchall()
        }
        transformed_axes = {
            axis_id: value
            for axis_id, value in connection.execute(
                """
                SELECT axis_id, transformed_value
                FROM specimen_axes
                WHERE specimen_id = ?
                ORDER BY axis_id
                """,
                [specimen_id],
            ).fetchall()
        }
        missing_terminal_axes = [
            axis_id for axis_id in TERMINAL_AXIS_IDS if axis_id not in raw_axes
        ]
        if missing_terminal_axes:
            skipped_specimens.append(
                {
                    "specimenId": specimen_id,
                    "phaseName": "",
                    "reason": "missing terminal axes: " + ", ".join(missing_terminal_axes),
                }
            )
            continue
        baseline_trials: list[dict[str, Any]] = []
        response_trials: list[dict[str, Any]] = []
        context_trials: list[dict[str, Any]] = []
        phase_name = None
        for _trial_id, trial_phase_name, _environment, perturbation, raw_json in grouped_trials.get(
            specimen_id, []
        ):
            phase_name = phase_name or trial_phase_name
            payload = json.loads(raw_json)
            if isinstance(payload, dict):
                context_trials.append(payload)
            if perturbation == "baseline":
                if isinstance(payload, dict):
                    baseline_trials.append(payload)
            else:
                if isinstance(payload, dict):
                    response_trials.append(payload)
        baseline_rows = _export_baseline_rows(baseline_trials)
        response_rows = _export_response_rows(response_trials)
        fragility_values = [
            float(row["meanFragilityScore"])
            for row in response_rows
            if isinstance(row.get("meanFragilityScore"), (int, float))
        ]
        robustness_values = [
            float(row["meanRobustnessScore"])
            for row in response_rows
            if isinstance(row.get("meanRobustnessScore"), (int, float))
        ]
        by_environment = {}
        by_perturbation = {}
        for row in response_rows:
            environment = row["environmentLabel"]
            perturbation = row["perturbationLabel"]
            by_environment.setdefault(environment, []).append(float(row["meanFragilityScore"]))
            by_perturbation.setdefault(perturbation, []).append(float(row["meanFragilityScore"]))
        packet_specimens.append(
            {
                "specimenId": specimen_id,
                "specimenName": specimen["provenance"].get("specimenName", specimen_id),
                "phaseName": phase_name,
                "runId": specimen["runId"],
                "campaignId": specimen["campaignId"],
                "sourceKind": specimen["sourceKind"],
                "familyKind": specimen["familyKind"],
                "regimeFamily": specimen["regimeFamily"],
                "geometryFamily": specimen["geometryFamily"],
                "canonicalFamily": specimen["canonicalFamily"],
                "selectedBy": specimen["provenance"].get("selectedBy", []),
                "dominantProgram": specimen["provenance"].get("dominantProgram"),
                "rawAxes": raw_axes,
                "transformedAxes": transformed_axes,
                "contextTrials": context_trials,
                "baselineByEnvironment": baseline_rows,
                "responseByCondition": response_rows,
                "fragilitySummary": {
                    "meanFragilityScore": (sum(fragility_values) / len(fragility_values))
                    if fragility_values
                    else 0.0,
                    "maxFragilityScore": max(fragility_values, default=0.0),
                    "meanRobustnessScore": (sum(robustness_values) / len(robustness_values))
                    if robustness_values
                    else 0.0,
                    "minRobustnessScore": min(robustness_values, default=0.0),
                    "mostFragileCondition": (
                        sorted(
                            response_rows,
                            key=lambda row: (
                                -float(row["meanFragilityScore"]),
                                str(row["environmentLabel"]),
                                str(row["perturbationLabel"]),
                            ),
                        )[0]
                        if response_rows
                        else None
                    ),
                    "mostRobustCondition": (
                        sorted(
                            response_rows,
                            key=lambda row: (
                                float(row["meanFragilityScore"]),
                                str(row["environmentLabel"]),
                                str(row["perturbationLabel"]),
                            ),
                        )[0]
                        if response_rows
                        else None
                    ),
                },
            }
        )
    if not packet_specimens:
        raise SystemExit(f"duckdb://study/{study_id}: no topology-ready focal specimens found")
    selection_histogram = _counts_from_lists(packet_specimens, "selectedBy")
    ensemble = _aggregate_focal_ensemble(packet_specimens)
    return {
        "version": 1,
        "packetKind": "transformation_focal_packet_v1",
        "sourceArtifacts": {
            "focalStudy": f"duckdb://study/{study_id}",
        },
        "summary": {
            "selectedSpecimenCount": len(packet_specimens),
            "selectedCanonicalCount": len(packet_specimens),
            "selectedFrozenCount": 0,
            "skippedSpecimenCount": len(skipped_specimens),
            "selectionAxisHistogram": selection_histogram,
            "conditionCount": sum(
                len(specimen["responseByCondition"]) for specimen in packet_specimens
            ),
            "environmentCount": len(
                {
                    row["environmentLabel"]
                    for specimen in packet_specimens
                    for row in specimen["responseByCondition"]
                }
            ),
            "perturbationCount": len(
                {
                    row["perturbationLabel"]
                    for specimen in packet_specimens
                    for row in specimen["responseByCondition"]
                }
            ),
            "terminalAxisCount": len(TERMINAL_AXIS_IDS),
            "developmentalAxisCount": len(DEVELOPMENTAL_AXIS_IDS),
            "regimeFamilies": sorted(
                {
                    specimen["regimeFamily"]
                    for specimen in packet_specimens
                    if specimen["regimeFamily"]
                }
            ),
            "geometryFamilies": sorted(
                {
                    specimen["geometryFamily"]
                    for specimen in packet_specimens
                    if specimen["geometryFamily"]
                }
            ),
            "canonicalFamilies": sorted(
                {
                    specimen["canonicalFamily"]
                    for specimen in packet_specimens
                    if specimen["canonicalFamily"]
                }
            ),
        },
        "limitations": [
            (
                "Warehouse focal export currently reflects stored condition summaries "
                "rather than per-repeat trial traces."
            ),
        ],
        "skippedSpecimens": skipped_specimens,
        "specimens": packet_specimens,
        "ensemble": ensemble,
    }


def _counts_from_lists(specimens: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for specimen in specimens:
        for value in specimen.get(key, []):
            counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _aggregate_focal_ensemble(specimens: list[dict[str, Any]]) -> dict[str, Any]:
    def aggregate(key: str) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = {}
        for specimen in specimens:
            value = specimen.get(key)
            if not isinstance(value, str) or not value:
                continue
            fragility = specimen["fragilitySummary"]["meanFragilityScore"]
            buckets.setdefault(value, []).append(float(fragility))
        return [
            {
                key: group_value,
                "meanFragilityScore": sum(values) / len(values),
                "conditionCount": len(values),
            }
            for group_value, values in sorted(buckets.items())
        ]

    by_perturbation: dict[str, list[float]] = {}
    by_environment: dict[str, list[float]] = {}
    for specimen in specimens:
        for row in specimen["responseByCondition"]:
            by_perturbation.setdefault(row["perturbationLabel"], []).append(
                float(row["meanFragilityScore"])
            )
            by_environment.setdefault(row["environmentLabel"], []).append(
                float(row["meanFragilityScore"])
            )
    return {
        "byPerturbation": [
            {"perturbationLabel": key, "meanFragilityScore": sum(values) / len(values)}
            for key, values in sorted(by_perturbation.items())
        ],
        "byEnvironment": [
            {"environmentLabel": key, "meanFragilityScore": sum(values) / len(values)}
            for key, values in sorted(by_environment.items())
        ],
        "byRegimeFamily": aggregate("regimeFamily"),
        "byGeometryFamily": aggregate("geometryFamily"),
        "byCanonicalFamily": aggregate("canonicalFamily"),
    }


def export_topology_packet(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT topology_run_id, space_kind, group_key, group_value, summary_json
        FROM topology_runs
        WHERE study_id = ?
        ORDER BY space_kind, coalesce(group_key, ''), coalesce(group_value, '')
        """,
        [study_id],
    ).fetchall()
    if not rows:
        child_rows = connection.execute(
            """
            SELECT study_id
            FROM studies
            WHERE parent_study_id = ? AND study_kind = 'topology_run'
            ORDER BY study_id
            """,
            [study_id],
        ).fetchall()
        child_ids = [str(row[0]) for row in child_rows]
        if child_ids:
            raise SystemExit(
                f"Study {study_id} has no direct topology runs. "
                f"Use one of its topology child studies instead: {', '.join(child_ids)}"
            )
        raise SystemExit(f"Study {study_id} has no topology runs")
    spaces: dict[str, dict[str, Any]] = {}
    for _topology_run_id, space_kind, group_key, group_value, summary_json in rows:
        spaces.setdefault(str(space_kind), {"groups": {}})
        summary = json.loads(summary_json)
        if group_key is None:
            spaces[str(space_kind)]["global"] = summary
            continue
        group_entries = spaces[str(space_kind)]["groups"].setdefault(str(group_key), [])
        group_entries.append(
            {
                str(group_key): str(group_value),
                "pointCount": summary.get("pointCount", 0),
                "topology": summary,
            }
        )
    summary_row = connection.execute(
        """
        SELECT input_query_json
        FROM topology_runs
        WHERE study_id = ?
        ORDER BY topology_run_id
        LIMIT 1
        """,
        [study_id],
    ).fetchone()
    source_summary = (
        json.loads(summary_row[0]) if summary_row is not None and summary_row[0] else {}
    )
    return {
        "version": 1,
        "packetKind": "transformation_topology_packet_v1",
        "sourceArtifact": f"duckdb://study/{study_id}",
        "summary": {
            "specimenCount": int(source_summary.get("specimenCount", 0)),
            "sourcePacketKind": str(source_summary.get("sourcePacketKind", "warehouse")),
            "spaces": list(spaces),
        },
        "limitations": [
            "Warehouse topology export reuses stored topology runs.",
        ],
        "spaces": spaces,
    }


def export_family_comparison_packet(
    connection: DuckDBPyConnection,
    *,
    atlas_study_id: str,
    focal_study_id: str | None,
    atlas_topology_study_id: str | None,
    focal_topology_study_id: str | None,
    canonical_families: list[str] | None,
) -> dict[str, Any]:
    atlas_packet = export_atlas_packet(
        connection,
        study_id=atlas_study_id,
        top_exemplars_per_axis=5,
    )
    focal_packet = (
        export_focal_packet(connection, study_id=focal_study_id)
        if focal_study_id is not None
        else None
    )
    atlas_topology_packet = (
        export_topology_packet(connection, study_id=atlas_topology_study_id)
        if atlas_topology_study_id is not None
        else None
    )
    focal_topology_packet = (
        export_topology_packet(connection, study_id=focal_topology_study_id)
        if focal_topology_study_id is not None
        else None
    )
    with tempfile.TemporaryDirectory(prefix="morphospace-family-") as tmpdir:
        tmp = Path(tmpdir)
        atlas_path = tmp / "atlas.json"
        atlas_path.write_text(json.dumps(atlas_packet, indent=2, sort_keys=True), encoding="utf-8")
        focal_path = None
        if focal_packet is not None:
            focal_path = tmp / "focal.json"
            focal_path.write_text(
                json.dumps(focal_packet, indent=2, sort_keys=True), encoding="utf-8"
            )
        atlas_topology_path = None
        if atlas_topology_packet is not None:
            atlas_topology_path = tmp / "atlas-topology.json"
            atlas_topology_path.write_text(
                json.dumps(atlas_topology_packet, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        focal_topology_path = None
        if focal_topology_packet is not None:
            focal_topology_path = tmp / "focal-topology.json"
            focal_topology_path.write_text(
                json.dumps(focal_topology_packet, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        packet = build_transformation_family_comparison_packet(
            atlas_packet_path=atlas_path,
            focal_packet_path=focal_path,
            atlas_topology_packet_path=atlas_topology_path,
            focal_topology_packet_path=focal_topology_path,
            canonical_families=canonical_families,
        )
    packet["sourceArtifacts"] = {
        "atlasStudy": f"duckdb://study/{atlas_study_id}",
        "focalStudy": None if focal_study_id is None else f"duckdb://study/{focal_study_id}",
        "atlasTopologyStudy": None
        if atlas_topology_study_id is None
        else f"duckdb://study/{atlas_topology_study_id}",
        "focalTopologyStudy": None
        if focal_topology_study_id is None
        else f"duckdb://study/{focal_topology_study_id}",
    }
    return packet


def compute_and_store_topology(
    connection: DuckDBPyConnection,
    *,
    study_id: str,
    source_packet_kind: str,
    min_group_size: int,
    max_homology_dim: int,
) -> str:
    if source_packet_kind == "atlas":
        packet = export_atlas_packet(connection, study_id=study_id, top_exemplars_per_axis=5)
    elif source_packet_kind == "focal":
        packet = export_focal_packet(connection, study_id=study_id)
    else:
        raise SystemExit(f"Unsupported source packet kind: {source_packet_kind}")
    with tempfile.TemporaryDirectory(prefix="morphospace-topology-") as tmpdir:
        packet_path = Path(tmpdir) / f"{source_packet_kind}.json"
        packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
        topology_packet = build_transformation_topology_packet(
            atlas_packet_path=packet_path,
            min_group_size=min_group_size,
            max_homology_dim=max_homology_dim,
        )
        topology_path = Path(tmpdir) / "topology.json"
        topology_path.write_text(
            json.dumps(topology_packet, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        from .ingest_topology import ingest_topology_packet

        return ingest_topology_packet(
            connection,
            topology_packet_path=topology_path,
            parent_study_id=study_id,
            label=f"{study_id}-{source_packet_kind}-topology",
        )
