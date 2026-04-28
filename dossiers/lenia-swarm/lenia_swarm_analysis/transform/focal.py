from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, cast

from lenia_swarm_analysis._io import read_json, read_jsonl
from lenia_swarm_analysis.transformation_metrics import (
    DEVELOPMENTAL_AXIS_IDS,
    TERMINAL_AXIS_IDS,
    developmental_trace_from_samples,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)

BASELINE_METRIC_KEYS = (
    "score",
    "centerVelocity",
    "displacement",
    "pathLength",
    "finalMass",
    "occupancyMean",
    "varianceMean",
    "gyration",
)

RESPONSE_METRIC_KEYS = (
    "postPerturbationDivergence",
    "returnToBaselineScore",
    "redirectedBehaviorScore",
    "massRetentionRatio",
    "displacementRatio",
    "occupancyDelta",
    "varianceDelta",
    "score",
    "centerVelocity",
)


def _phase_name(specimen: dict[str, Any], index: int) -> str:
    phase_name = specimen.get("phaseName")
    if isinstance(phase_name, str) and phase_name:
        return phase_name
    specimen_name = specimen.get("specimenName")
    if not isinstance(specimen_name, str) or not specimen_name:
        raise SystemExit("focal specimen is missing phaseName and specimenName")
    sanitized = "".join(
        character if character.isalnum() else "-"
        for character in specimen_name.lower()
    ).strip("-")
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    if not sanitized:
        raise SystemExit(f"invalid specimenName for focal specimen {specimen.get('specimenId')}")
    return f"focal-{sanitized}-{index}"


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    if not values:
        return None
    return float(mean(values))


def _metric_summary(
    rows: list[dict[str, Any]],
    *,
    metric_keys: tuple[str, ...],
) -> dict[str, float]:
    summary: dict[str, float] = {}
    for key in metric_keys:
        value = _mean_metric(rows, key)
        if value is not None:
            summary[key] = value
    return summary


def _condition_summary(
    *,
    environment_label: str,
    perturbation_label: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        raise SystemExit(
            f"empty focal condition rows for {environment_label}/{perturbation_label}"
        )
    divergence_values = [
        float(row["postPerturbationDivergence"])
        for row in rows
        if isinstance(row.get("postPerturbationDivergence"), (int, float))
    ]
    return_to_baseline_values = [
        float(row["returnToBaselineScore"])
        for row in rows
        if isinstance(row.get("returnToBaselineScore"), (int, float))
    ]
    if not divergence_values or not return_to_baseline_values:
        raise SystemExit(
            "missing intervention metrics for focal condition "
            f"{environment_label}/{perturbation_label}"
        )
    return {
        "environmentLabel": environment_label,
        "perturbationLabel": perturbation_label,
        "rowCount": len(rows),
        "meanMetrics": _metric_summary(rows, metric_keys=RESPONSE_METRIC_KEYS),
        "meanFragilityScore": float(mean(divergence_values)),
        "maxFragilityScore": float(max(divergence_values)),
        "meanRobustnessScore": float(mean(return_to_baseline_values)),
        "minRobustnessScore": float(min(return_to_baseline_values)),
    }


def _baseline_summary(*, environment_label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise SystemExit(f"missing baseline rows for environment {environment_label}")
    return {
        "environmentLabel": environment_label,
        "rowCount": len(rows),
        "meanMetrics": _metric_summary(rows, metric_keys=BASELINE_METRIC_KEYS),
    }


def _extreme_condition(
    conditions: list[dict[str, Any]],
    *,
    metric_key: str,
    reverse: bool,
) -> dict[str, Any]:
    condition = sorted(
        conditions,
        key=lambda row: (
            -float(row[metric_key]) if reverse else float(row[metric_key]),
            str(row["environmentLabel"]),
            str(row["perturbationLabel"]),
        ),
    )[0]
    return {
        "environmentLabel": condition["environmentLabel"],
        "perturbationLabel": condition["perturbationLabel"],
        metric_key: float(condition[metric_key]),
    }


def _aggregate_conditions(
    conditions: list[dict[str, Any]],
    *,
    group_key: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for condition in conditions:
        value = condition.get(group_key)
        if value is None:
            continue
        grouped[str(value)].append(condition)
    summaries: list[dict[str, Any]] = []
    for group_value, group_conditions in sorted(grouped.items()):
        summaries.append(
            {
                group_key: group_value,
                "conditionCount": len(group_conditions),
                "meanFragilityScore": float(
                    mean(float(row["meanFragilityScore"]) for row in group_conditions)
                ),
                "maxFragilityScore": float(
                    max(float(row["maxFragilityScore"]) for row in group_conditions)
                ),
                "meanRobustnessScore": float(
                    mean(float(row["meanRobustnessScore"]) for row in group_conditions)
                ),
                "minRobustnessScore": float(
                    min(float(row["minRobustnessScore"]) for row in group_conditions)
                ),
            }
        )
    return summaries


def _descriptor_bundle_from_result_row(result_row: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("descriptorBundle", "descriptor_bundle"):
        bundle = result_row.get(key)
        if isinstance(bundle, dict):
            return bundle
    return None


def _endpoint_payload(
    *,
    result_row: dict[str, Any],
    specimen_id: str,
) -> dict[str, Any] | None:
    bundle = _descriptor_bundle_from_result_row(result_row)
    if not isinstance(bundle, dict):
        return None
    terminal = bundle.get("terminal")
    trajectory = bundle.get("trajectory")
    if not isinstance(terminal, dict) or not isinstance(trajectory, dict):
        return None
    raw_axes = extract_terminal_raw_axes_from_descriptors(
        terminal=terminal,
        trajectory=trajectory,
        specimen_id=specimen_id,
    )
    return {
        "terminalDescriptor": terminal,
        "trajectoryDescriptor": trajectory,
        "rawAxes": raw_axes,
        "transformedAxes": transform_axes(raw_axes),
    }


def _load_development_trace_payload(
    *,
    trace_path: Path,
    specimen_id: str,
    meander_final: float,
) -> dict[str, Any]:
    trace_rows = read_jsonl(trace_path)
    ordered = sorted(trace_rows, key=lambda row: int(row["step"]))
    development = developmental_trace_from_samples(
        specimen_id=specimen_id,
        trace_samples=ordered,
        meander_final=meander_final,
    )
    sampled_rows: list[dict[str, Any]] = []
    center_velocity_trace = development["traceAxes"].get("center_velocity", [])
    for index, row in enumerate(ordered):
        terminal = row.get("terminal")
        if not isinstance(terminal, dict):
            raise SystemExit(f"{trace_path}: trace row missing terminal descriptor")
        center_velocity = (
            float(center_velocity_trace[index])
            if index < len(center_velocity_trace)
            else 0.0
        )
        raw_axes = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal,
            trajectory={
                "centerVelocity": center_velocity,
                "pathTortuosity": meander_final,
            },
            specimen_id=specimen_id,
        )
        raw_axes["center_x"] = float(row["centerX"])
        raw_axes["center_y"] = float(row["centerY"])
        sampled_rows.append(
            {
                "step": int(row["step"]),
                "centerX": float(row["centerX"]),
                "centerY": float(row["centerY"]),
                "rawAxes": raw_axes,
                "transformedAxes": transform_axes(
                    {
                        key: value
                        for key, value in raw_axes.items()
                        if key not in {"center_x", "center_y"}
                    }
                ),
            }
        )
    return {
        "developmentTracePath": str(trace_path),
        "sampleCount": len(sampled_rows),
        "capturedSteps": [int(row["step"]) for row in sampled_rows],
        "developmentalAxes": development["developmentalAxes"],
        "transformedDevelopmentalAxes": development["transformedDevelopmentalAxes"],
        "samples": sampled_rows,
    }


def _phase_trial_rows(
    *,
    specimen_id: str,
    phase_dir: Path,
    metric_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    runs_path = phase_dir / "runs.jsonl"
    results_path = phase_dir / "results.jsonl"
    run_rows = read_jsonl(runs_path) if runs_path.exists() else []
    result_rows = read_jsonl(results_path) if results_path.exists() else []

    if run_rows and len(run_rows) != len(metric_rows):
        raise SystemExit(
            f"{runs_path}: intervention runs do not align with metrics rows "
            f"({len(run_rows)} vs {len(metric_rows)})"
        )
    if result_rows:
        if not run_rows:
            raise SystemExit(f"{results_path}: focal endpoint results require runs.jsonl")
        if len(result_rows) != len(run_rows):
            raise SystemExit(
                f"{results_path}: intervention results do not align with run rows "
                f"({len(result_rows)} vs {len(run_rows)})"
            )

    result_by_run_id: dict[str, dict[str, Any]] = {}
    run_by_run_id: dict[str, dict[str, Any]] = {}
    for index, run_row in enumerate(run_rows):
        run_id = run_row.get("runID")
        if isinstance(run_id, str) and run_id:
            run_by_run_id[run_id] = run_row
            if result_rows:
                result_by_run_id[run_id] = result_rows[index]

    trial_rows: list[dict[str, Any]] = []
    for index, metric_row in enumerate(metric_rows):
        run_id_value = metric_row.get("runID")
        if not isinstance(run_id_value, str) or not run_id_value:
            if index < len(run_rows):
                candidate = run_rows[index].get("runID")
                run_id_value = str(candidate) if candidate is not None else None
        run_row = None
        if isinstance(run_id_value, str) and run_id_value:
            run_row = run_by_run_id.get(run_id_value)
        if run_row is None and index < len(run_rows):
            run_row = run_rows[index]

        environment_label = metric_row.get("environmentLabel")
        perturbation_label = metric_row.get("perturbationLabel")
        if not isinstance(environment_label, str) or not environment_label:
            environment_label = (
                str(run_row.get("environmentLabel"))
                if isinstance(run_row, dict) and run_row.get("environmentLabel") is not None
                else ""
            )
        if not isinstance(perturbation_label, str) or not perturbation_label:
            perturbation_label = (
                str(run_row.get("perturbationLabel"))
                if isinstance(run_row, dict) and run_row.get("perturbationLabel") is not None
                else ""
            )
        if not environment_label or not perturbation_label:
            raise SystemExit(
                f"{phase_dir}: focal trial row is missing "
                "environment/perturbation labels"
            )

        repeat_index = 0
        if isinstance(run_row, dict):
            repeat_value = run_row.get("repeatIndex")
            if isinstance(repeat_value, int):
                repeat_index = repeat_value
            elif isinstance(repeat_value, float):
                repeat_index = int(repeat_value)

        endpoint = None
        if isinstance(run_id_value, str) and run_id_value:
            result_row = result_by_run_id.get(run_id_value)
            if result_row is not None:
                endpoint = _endpoint_payload(result_row=result_row, specimen_id=specimen_id)

        trial_row: dict[str, Any] = {
            "runId": run_id_value,
            "repeatIndex": repeat_index,
            "environmentLabel": environment_label,
            "perturbationLabel": perturbation_label,
            "metrics": metric_row,
            "summaryPath": str(phase_dir / "metrics.jsonl"),
            "resultsPath": str(results_path) if results_path.exists() else None,
        }
        if endpoint is not None:
            trial_row["endpointTerminalDescriptor"] = endpoint["terminalDescriptor"]
            trial_row["endpointTrajectoryDescriptor"] = endpoint["trajectoryDescriptor"]
            trial_row["endpointRawAxes"] = endpoint["rawAxes"]
            trial_row["endpointTransformedAxes"] = endpoint["transformedAxes"]
        if isinstance(run_row, dict):
            trace_path_value = run_row.get("developmentTracePath")
            if isinstance(trace_path_value, str) and trace_path_value:
                if endpoint is None:
                    raise SystemExit(
                        f"{phase_dir}: focal trial {run_id_value} has "
                        "developmentTracePath but no endpoint result"
                    )
                trace_path = Path(trace_path_value).expanduser().resolve()
                if not trace_path.exists():
                    raise SystemExit(f"{trace_path}: missing focal development trace")
                trajectory = endpoint.get("trajectoryDescriptor")
                if not isinstance(trajectory, dict):
                    raise SystemExit(
                        f"{phase_dir}: focal trial {run_id_value} is missing "
                        "endpoint trajectory descriptor"
                    )
                meander_final = float(trajectory.get("pathTortuosity", 0.0) or 0.0)
                trial_row["developmentTrace"] = _load_development_trace_payload(
                    trace_path=trace_path,
                    specimen_id=specimen_id,
                    meander_final=meander_final,
                )
        trial_rows.append(trial_row)
    return trial_rows


def build_transformation_focal_packet(
    *,
    focal_spec_path: Path,
    campaign_root: Path,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    spec = read_json(focal_spec_path)
    if spec.get("schemaVersion") != 1:
        raise SystemExit(f"{focal_spec_path}: unsupported focal spec schemaVersion")
    atlas_packet_path = Path(str(spec["sourceAtlasPacket"])).expanduser().resolve()
    atlas_packet = read_json(atlas_packet_path)
    if atlas_packet.get("packetKind") != "developmental_transformation_atlas_v2":
        raise SystemExit(
            f"{atlas_packet_path}: focal packet expects developmental_transformation_atlas_v2"
        )
    atlas_specimens_raw = atlas_packet.get("specimens")
    if not isinstance(atlas_specimens_raw, list) or not atlas_specimens_raw:
        raise SystemExit(f"{atlas_packet_path}: atlas packet has no specimens")
    atlas_by_specimen_id = {
        str(specimen["specimenId"]): specimen for specimen in atlas_specimens_raw
    }

    selected_canonical = spec.get("selectedCanonical")
    if not isinstance(selected_canonical, list) or not selected_canonical:
        raise SystemExit(f"{focal_spec_path}: focal spec has no selectedCanonical entries")

    specimens: list[dict[str, Any]] = []
    all_condition_rows: list[dict[str, Any]] = []
    selection_axis_counts: Counter[str] = Counter()
    environments: set[str] = set()
    perturbations: set[str] = set()
    regime_families: set[str] = set()
    geometry_families: set[str] = set()
    canonical_families: set[str] = set()
    skipped_specimens: list[dict[str, str]] = []

    for index, selected_value in enumerate(selected_canonical):
        if not isinstance(selected_value, dict):
            raise SystemExit(f"{focal_spec_path}: selectedCanonical must contain objects")
        selected_raw = cast(dict[str, Any], selected_value)
        specimen_id = str(selected_raw["specimenId"])
        atlas_specimen = atlas_by_specimen_id.get(specimen_id)
        if atlas_specimen is None:
            raise SystemExit(
                f"{focal_spec_path}: focal specimen {specimen_id} missing from source atlas"
            )
        phase_name = _phase_name(selected_raw, index)
        phase_dir = campaign_root / phase_name
        metrics_path = phase_dir / "metrics.jsonl"
        if not metrics_path.exists():
            if allow_incomplete:
                skipped_specimens.append(
                    {
                        "specimenId": specimen_id,
                        "phaseName": phase_name,
                        "reason": "missing focal phase metrics",
                    }
                )
                continue
            else:
                raise SystemExit(f"{metrics_path}: missing focal phase metrics")
        metric_rows = read_jsonl(metrics_path)
        trial_rows = _phase_trial_rows(
            specimen_id=specimen_id,
            phase_dir=phase_dir,
            metric_rows=metric_rows,
        )
        baseline_rows_by_environment: dict[str, list[dict[str, Any]]] = defaultdict(list)
        response_rows_by_condition: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in metric_rows:
            environment_label = row.get("environmentLabel")
            perturbation_label = row.get("perturbationLabel")
            if not isinstance(environment_label, str) or not environment_label:
                raise SystemExit(f"{metrics_path}: metric row is missing environmentLabel")
            if not isinstance(perturbation_label, str) or not perturbation_label:
                raise SystemExit(f"{metrics_path}: metric row is missing perturbationLabel")
            if perturbation_label == "baseline":
                baseline_rows_by_environment[environment_label].append(row)
            else:
                response_rows_by_condition[(environment_label, perturbation_label)].append(row)
        if not baseline_rows_by_environment or not response_rows_by_condition:
            if allow_incomplete:
                missing_piece = "baseline" if not baseline_rows_by_environment else "intervention"
                skipped_specimens.append(
                    {
                        "specimenId": specimen_id,
                        "phaseName": phase_name,
                        "reason": f"missing focal phase {missing_piece} metrics",
                    }
                )
                continue
            if not baseline_rows_by_environment:
                raise SystemExit(f"{metrics_path}: no baseline rows found")
            raise SystemExit(f"{metrics_path}: no intervention rows found")

        baseline_by_environment = [
            _baseline_summary(environment_label=environment_label, rows=rows)
            for environment_label, rows in sorted(baseline_rows_by_environment.items())
        ]
        response_conditions = [
            _condition_summary(
                environment_label=environment_label,
                perturbation_label=perturbation_label,
                rows=rows,
            )
            for (environment_label, perturbation_label), rows in sorted(
                response_rows_by_condition.items()
            )
        ]
        for condition in response_conditions:
            all_condition_rows.append(
                {
                    **condition,
                    "specimenId": specimen_id,
                    "regimeFamily": atlas_specimen.get("regimeFamily"),
                    "geometryFamily": atlas_specimen.get("geometryFamily"),
                    "canonicalFamily": atlas_specimen.get("canonicalFamily"),
                }
            )
        selected_by_raw = selected_raw.get("selectedBy", [])
        selected_by = [str(axis) for axis in selected_by_raw if isinstance(axis, str)]
        selection_axis_counts.update(selected_by)
        regime_family = atlas_specimen.get("regimeFamily")
        geometry_family = atlas_specimen.get("geometryFamily")
        canonical_family = atlas_specimen.get("canonicalFamily")
        if isinstance(regime_family, str):
            regime_families.add(regime_family)
        if isinstance(geometry_family, str):
            geometry_families.add(geometry_family)
        if isinstance(canonical_family, str):
            canonical_families.add(canonical_family)
        environments.update(
            str(entry["environmentLabel"]) for entry in baseline_by_environment
        )
        perturbations.update(
            str(entry["perturbationLabel"]) for entry in response_conditions
        )

        specimens.append(
            {
                "specimenId": specimen_id,
                "specimenName": str(selected_raw.get("specimenName", specimen_id)),
                "phaseName": phase_name,
                "runId": atlas_specimen.get("runId"),
                "campaignId": atlas_specimen.get("campaignId"),
                "sourceKind": atlas_specimen.get("sourceKind"),
                "familyKind": (
                    canonical_family
                    or geometry_family
                    or atlas_specimen.get("familyKind")
                ),
                "regimeFamily": regime_family,
                "geometryFamily": geometry_family,
                "canonicalFamily": canonical_family,
                "selectedBy": selected_by,
                "dominantProgram": atlas_specimen.get("dominantProgram"),
                "rawAxes": atlas_specimen.get("rawAxes"),
                "transformedAxes": atlas_specimen.get("transformedAxes"),
                "contextTrials": trial_rows,
                "baselineByEnvironment": baseline_by_environment,
                "responseByCondition": response_conditions,
                "fragilitySummary": {
                    "meanFragilityScore": float(
                        mean(float(row["meanFragilityScore"]) for row in response_conditions)
                    ),
                    "maxFragilityScore": float(
                        max(float(row["maxFragilityScore"]) for row in response_conditions)
                    ),
                    "meanRobustnessScore": float(
                        mean(float(row["meanRobustnessScore"]) for row in response_conditions)
                    ),
                    "minRobustnessScore": float(
                        min(float(row["minRobustnessScore"]) for row in response_conditions)
                    ),
                    "mostFragileCondition": _extreme_condition(
                        response_conditions,
                        metric_key="meanFragilityScore",
                        reverse=True,
                    ),
                    "mostRobustCondition": _extreme_condition(
                        response_conditions,
                        metric_key="meanFragilityScore",
                        reverse=False,
                    ),
                },
            }
        )

    if not specimens:
        raise SystemExit(
            f"{campaign_root}: no complete focal specimens found"
            + (" while allow_incomplete was enabled" if allow_incomplete else "")
        )

    by_environment = _aggregate_conditions(all_condition_rows, group_key="environmentLabel")
    by_perturbation = _aggregate_conditions(all_condition_rows, group_key="perturbationLabel")
    by_regime_family = _aggregate_conditions(all_condition_rows, group_key="regimeFamily")
    by_canonical_family = _aggregate_conditions(
        all_condition_rows,
        group_key="canonicalFamily",
    )

    return {
        "version": 1,
        "packetKind": "transformation_focal_packet_v1",
        "sourceArtifacts": {
            "focalSpec": str(focal_spec_path),
            "campaignRoot": str(campaign_root),
            "sourceAtlasPacket": str(atlas_packet_path),
        },
        "summary": {
            "selectedSpecimenCount": len(specimens),
            "selectedCanonicalCount": int(spec.get("selectedCanonicalCount", len(specimens))),
            "selectedFrozenCount": int(spec.get("selectedFrozenCount", 0)),
            "skippedSpecimenCount": len(skipped_specimens),
            "environmentCount": len(environments),
            "perturbationCount": len(perturbations),
            "conditionCount": len(all_condition_rows),
            "terminalAxisCount": len(TERMINAL_AXIS_IDS),
            "developmentalAxisCount": len(DEVELOPMENTAL_AXIS_IDS),
            "selectionAxisHistogram": dict(sorted(selection_axis_counts.items())),
            "regimeFamilies": sorted(regime_families),
            "geometryFamilies": sorted(geometry_families),
            "canonicalFamilies": sorted(canonical_families),
        },
        "limitations": [
            (
                "Focal responses include per-trial developmental traces only when the "
                "underlying intervention campaign captured them; older campaign roots remain "
                "metric-only."
            ),
            (
                "The current focal generator selects canonical exemplars only; frozen-atlas "
                "baseline exemplars remain a later extension."
            ),
        ]
        + (
            [
                (
                    "This packet was built with allow_incomplete enabled, so unfinished focal "
                    "phases were skipped explicitly rather than treated as fatal."
                )
            ]
            if allow_incomplete
            else []
        ),
        "skippedSpecimens": skipped_specimens,
        "specimens": specimens,
        "ensemble": {
            "byEnvironment": by_environment,
            "byPerturbation": by_perturbation,
            "byRegimeFamily": by_regime_family,
            "byCanonicalFamily": by_canonical_family,
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a focal robustness packet from Flow atlas intervention-battery outputs."
    )
    parser.add_argument(
        "--focal-spec",
        required=True,
        help="Path to flow-transformation-atlas-focal-spec.json",
    )
    parser.add_argument(
        "--campaign-root",
        required=True,
        help="Path to the focal campaign output root containing per-phase metrics.jsonl files",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Skip unfinished focal phases instead of failing",
    )
    parser.add_argument("--output", help="Output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    focal_spec_path = Path(args.focal_spec).expanduser().resolve()
    campaign_root = Path(args.campaign_root).expanduser().resolve()
    packet = build_transformation_focal_packet(
        focal_spec_path=focal_spec_path,
        campaign_root=campaign_root,
        allow_incomplete=bool(args.allow_incomplete),
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else focal_spec_path.parent / "transformation-focal-packet.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Transformation focal packet:"
        f" specimens={packet['summary']['selectedSpecimenCount']}"
        f" output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
