from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

from lenia_swarm_analysis.fiber.continuation import summarize_stateful_continuation
from lenia_swarm_analysis.fiber.survival_scoring import (
    load_terminal_trace,
    score_role_pair,
)

DEFAULT_AXES = ("m.0:0.03:0.001:0.999", "s.0:0.015:0.001:0.999", "R:0.75:1.0:")
ROLE_SLUGS = {
    "nearestTerminalCentroidSpecimenId": "nearest",
    "farthestTerminalSpecimenId": "farthest",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected a JSON object")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_=-]+", "-", value).strip("-")


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _rel_or_str(path: Path, root: Path | None) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _parse_specimen_id(specimen_id: str) -> tuple[str, int] | None:
    parts = specimen_id.split("|")
    if len(parts) != 3 or not parts[0].startswith("result:"):
        return None
    try:
        return parts[0].split(":", 1)[1], int(parts[2])
    except ValueError:
        return None


def resolve_export_bundle(
    specimen_id: str,
    *,
    flow_runs_root: Path,
    path_root: Path | None,
) -> dict[str, Any]:
    parsed = _parse_specimen_id(specimen_id)
    if parsed is None:
        return {"specimenId": specimen_id, "resolved": False, "reason": "unparseable specimen id"}
    run_id, seed = parsed
    exports = flow_runs_root / run_id / "exports"
    seed_suffix = str(seed % 10000)
    matches = sorted(exports.glob(f"*-{seed_suffix}-*")) if exports.exists() else []
    if not matches:
        return {
            "specimenId": specimen_id,
            "runId": run_id,
            "seed": seed,
            "resolved": False,
            "reason": "no export bundle matching seed suffix",
        }
    bundle = matches[0]
    base = _read_json(bundle / "base.json")
    params = base.get("params")
    if not isinstance(params, dict):
        raise SystemExit(f"{bundle}: missing base.params")
    return {
        "specimenId": specimen_id,
        "runId": run_id,
        "seed": seed,
        "seedSuffix": seed_suffix,
        "resolved": True,
        "bundle": _rel_or_str(bundle, path_root),
        "centerValues": _numeric_param_paths(params),
    }


def _numeric_param_paths(params: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in params.items():
        if isinstance(value, (int, float)):
            finite = _finite(value)
            if finite is not None:
                values[str(key)] = finite
            continue
        if isinstance(value, list):
            for index, item in enumerate(value):
                finite = _finite(item)
                if finite is not None:
                    values[f"{key}.{index}"] = finite
                if isinstance(item, list):
                    for inner_index, inner_item in enumerate(item):
                        inner = _finite(inner_item)
                        if inner is not None:
                            values[f"{key}.{index}.{inner_index}"] = inner
    return values


def parse_axis_spec(value: str) -> dict[str, Any]:
    parts = value.split(":")
    if len(parts) not in (2, 3, 4):
        raise argparse.ArgumentTypeError(
            "axis must be path:delta[:lower[:upper]], for example m.0:0.03:0.001:0.999"
        )
    path = parts[0]
    if not path:
        raise argparse.ArgumentTypeError("axis path cannot be empty")
    try:
        delta = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid axis delta: {parts[1]}") from exc
    lower = _parse_optional_bound(parts[2]) if len(parts) >= 3 else None
    upper = _parse_optional_bound(parts[3]) if len(parts) >= 4 else None
    if lower is not None and upper is not None and lower > upper:
        raise argparse.ArgumentTypeError("axis lower bound cannot exceed upper bound")
    return {"path": path, "delta": delta, "lower": lower, "upper": upper}


def _parse_optional_bound(value: str) -> float | None:
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid axis bound: {value}") from exc
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, lower: float | None, upper: float | None) -> float:
    if lower is not None:
        value = max(lower, value)
    if upper is not None:
        value = min(upper, value)
    return value


def loop_for_axis(
    axis: dict[str, Any],
    center: float,
    *,
    samples_per_segment: int,
) -> dict[str, Any]:
    delta = float(axis["delta"])
    lower = axis.get("lower")
    upper = axis.get("upper")
    values = [
        _clamp(center - delta, lower, upper),
        _clamp(center, lower, upper),
        _clamp(center + delta, lower, upper),
    ]
    return {
        "version": 1,
        "closed": False,
        "coordinates": [str(axis["path"])],
        "vertices": [[value] for value in values],
        "samples_per_segment": int(samples_per_segment),
    }


def _p_value(family_row: dict[str, Any]) -> float | None:
    terminal_null = family_row.get("terminalLabelShuffleNull")
    if not isinstance(terminal_null, dict):
        return None
    return _finite(terminal_null.get("ratioOneSidedPValue"))


def _ranked_pairs(
    ranks: dict[str, Any],
    *,
    limit: int,
    flow_runs_root: Path,
    path_root: Path | None,
) -> list[dict[str, Any]]:
    nearest = ranks.get("nearestTerminalCentroid", [])
    farthest = ranks.get("farthestTerminal", [])
    if not isinstance(nearest, list) or not isinstance(farthest, list):
        return []
    pairs = []
    for nearest_row, farthest_row in zip(nearest, farthest, strict=False):
        if not isinstance(nearest_row, dict) or not isinstance(farthest_row, dict):
            continue
        nearest_id = nearest_row.get("specimenId")
        farthest_id = farthest_row.get("specimenId")
        if not isinstance(nearest_id, str) or not isinstance(farthest_id, str):
            continue
        if nearest_id == farthest_id:
            continue
        nearest_bundle = resolve_export_bundle(
            nearest_id,
            flow_runs_root=flow_runs_root,
            path_root=path_root,
        )
        farthest_bundle = resolve_export_bundle(
            farthest_id,
            flow_runs_root=flow_runs_root,
            path_root=path_root,
        )
        if not nearest_bundle.get("resolved") or not farthest_bundle.get("resolved"):
            continue
        pairs.append(
            {
                "pairIndex": len(pairs) + 1,
                "nearestTerminalCentroidSpecimenId": nearest_id,
                "farthestTerminalSpecimenId": farthest_id,
                "nearestTerminalCentroidRank": nearest_row,
                "farthestTerminalRank": farthest_row,
                "resolvedExamples": {
                    "nearestTerminalCentroidSpecimenId": nearest_bundle,
                    "farthestTerminalSpecimenId": farthest_bundle,
                },
            }
        )
        if len(pairs) >= limit:
            break
    return pairs


def build_spec_from_null_validation(
    *,
    null_validation: dict[str, Any],
    null_validation_path: Path,
    flow_runs_root: Path,
    output_root: Path,
    cli_binary: str,
    path_root: Path | None,
    families: list[str] | None,
    positive_regions: list[str] | None,
    pair_limit: int,
    axes: list[dict[str, Any]],
    samples_per_segment: int,
    p_value_max: float,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    selected_families = set(families or [])
    selected_regions = set(positive_regions or [])
    for region_row in null_validation.get("regions", []):
        if not isinstance(region_row, dict):
            continue
        region = region_row.get("region")
        if not isinstance(region, str):
            continue
        if selected_regions and region not in selected_regions:
            continue
        family_rows = region_row.get("families")
        if not isinstance(family_rows, dict):
            continue
        for family, family_row in family_rows.items():
            if selected_families and family not in selected_families:
                continue
            if not isinstance(family_row, dict) or family_row.get("status") != "measured":
                continue
            p_value = _p_value(family_row)
            if not selected_regions and (p_value is None or p_value > p_value_max):
                continue
            positive_pairs = _ranked_pairs(
                family_row.get("exampleRanks", {}),
                limit=pair_limit,
                flow_runs_root=flow_runs_root,
                path_root=path_root,
            )
            append_runs(
                runs,
                case="positive",
                family=str(family),
                region=region,
                source_region=region,
                region_rank=None,
                pairs=positive_pairs,
                axes=axes,
                output_root=output_root,
                cli_binary=cli_binary,
                samples_per_segment=samples_per_segment,
            )
            control_region, control_pairs = _select_control_pairs(
                family_row,
                pair_limit=pair_limit,
                flow_runs_root=flow_runs_root,
                path_root=path_root,
            )
            if control_region is not None:
                append_runs(
                    runs,
                    case="control",
                    family=str(family),
                    region=control_region,
                    source_region=region,
                    region_rank=None,
                    pairs=control_pairs,
                    axes=axes,
                    output_root=output_root,
                    cli_binary=cli_binary,
                    samples_per_segment=samples_per_segment,
                )
            sources.append(
                {
                    "family": str(family),
                    "positiveRegion": region,
                    "positivePValue": p_value,
                    "positivePairCount": len(positive_pairs),
                    "controlRegion": control_region,
                    "controlPairCount": len(control_pairs),
                }
            )
    return {
        "packetKind": "fiber_survival_assay_spec_v1",
        "generatedAt": _now(),
        "sourceNullValidation": _rel_or_str(null_validation_path, path_root),
        "flowRunsRoot": _rel_or_str(flow_runs_root, path_root),
        "outputRoot": _rel_or_str(output_root, path_root),
        "cliBinary": cli_binary,
        "pathRoot": str(path_root) if path_root is not None else None,
        "pairLimit": pair_limit,
        "samplesPerSegment": samples_per_segment,
        "pValueMax": p_value_max,
        "axes": axes,
        "sources": sources,
        "runCount": len(runs),
        "runs": runs,
    }


def _select_control_pairs(
    family_row: dict[str, Any],
    *,
    pair_limit: int,
    flow_runs_root: Path,
    path_root: Path | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    controls = family_row.get("otherRegionControls")
    if not isinstance(controls, dict):
        return None, []
    bottom = controls.get("bottomByRatio", [])
    if not isinstance(bottom, list):
        return None, []
    for candidate in bottom:
        if not isinstance(candidate, dict):
            continue
        region = candidate.get("region")
        if not isinstance(region, str):
            continue
        pairs = _ranked_pairs(
            candidate.get("exampleRanks", {}),
            limit=pair_limit,
            flow_runs_root=flow_runs_root,
            path_root=path_root,
        )
        if pairs:
            return region, pairs
    return None, []


def append_runs(
    runs: list[dict[str, Any]],
    *,
    case: str,
    family: str,
    region: str,
    source_region: str,
    region_rank: int | None,
    pairs: list[dict[str, Any]],
    axes: list[dict[str, Any]],
    output_root: Path,
    cli_binary: str,
    samples_per_segment: int,
) -> None:
    for pair in pairs:
        pair_index = int(pair["pairIndex"])
        for role, bundle in pair["resolvedExamples"].items():
            center = bundle.get("centerValues")
            if not isinstance(center, dict):
                continue
            for axis in axes:
                axis_path = str(axis["path"])
                center_value = _finite(center.get(axis_path))
                if center_value is None:
                    continue
                source_key = hashlib.sha1(source_region.encode("utf-8")).hexdigest()[:10]
                name = _slug(
                    f"{case}-{family}-src{source_key}-p{pair_index}"
                    f"-{ROLE_SLUGS[role]}-{axis_path}"
                )
                loop_path = output_root / "loops" / f"{name}.json"
                run_output = output_root / "runs" / name
                loop = loop_for_axis(
                    axis,
                    center_value,
                    samples_per_segment=samples_per_segment,
                )
                runs.append(
                    {
                        "name": name,
                        "case": case,
                        "pairIndex": pair_index,
                        "family": family,
                        "region": region,
                        "sourceRegion": source_region,
                        "regionRank": region_rank,
                        "role": role,
                        "axis": axis_path,
                        "bundle": bundle["bundle"],
                        "loopPath": str(loop_path),
                        "outputPath": str(run_output),
                        "loop": loop,
                        "command": [
                            cli_binary,
                            "intervene",
                            "holonomy",
                            "--bundle",
                            str(bundle["bundle"]),
                            "--loop",
                            str(loop_path),
                            "--output",
                            str(run_output),
                            "--no-promotion",
                            "--run-id",
                            f"fiber-survival-{name}",
                        ],
                    }
                )


def write_loops(spec: dict[str, Any]) -> int:
    count = 0
    for run in spec.get("runs", []):
        if not isinstance(run, dict):
            continue
        loop_path = Path(str(run["loopPath"]))
        _write_json(loop_path, run["loop"])
        count += 1
    return count


def run_spec(
    spec: dict[str, Any],
    *,
    output: Path,
    jobs: int,
    rerun: bool,
    limit: int | None,
) -> dict[str, Any]:
    runs = [run for run in spec.get("runs", []) if isinstance(run, dict)]
    if limit is not None:
        runs = runs[:limit]
    cwd = Path(str(spec["pathRoot"])) if spec.get("pathRoot") else None
    records: list[dict[str, Any]] = []
    to_run: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        manifest_path = Path(str(run["outputPath"])) / "holonomy-manifest.json"
        if manifest_path.exists() and not rerun:
            records.append(_run_record(index, run, "skipped_completed", manifest_path))
            continue
        to_run.append({"index": index, "run": run})

    started = time.monotonic()
    if to_run:
        worker_count = max(1, int(jobs))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_execute_run, item["index"], item["run"], cwd): item
                for item in to_run
            }
            for future in as_completed(futures):
                records.append(future.result())
    records.sort(key=lambda row: int(row["index"]))
    completed = sum(1 for row in records if row["status"] == "completed")
    failed = sum(1 for row in records if row["status"] == "failed")
    skipped = sum(1 for row in records if row["status"] == "skipped_completed")
    packet = {
        "packetKind": "fiber_survival_assay_run_log_v1",
        "generatedAt": _now(),
        "sourceSpec": spec.get("sourceSpec", spec.get("sourceNullValidation")),
        "requestedRunCount": len(runs),
        "executedRunCount": len(to_run),
        "completedRunCount": completed,
        "failedRunCount": failed,
        "skippedCompletedRunCount": skipped,
        "jobs": max(1, int(jobs)),
        "durationSeconds": time.monotonic() - started,
        "runs": records,
    }
    _write_json(output, packet)
    return packet


def _run_record(
    index: int,
    run: dict[str, Any],
    status: str,
    manifest_path: Path,
) -> dict[str, Any]:
    return {
        "index": index,
        "name": run.get("name"),
        "case": run.get("case"),
        "family": run.get("family"),
        "sourceRegion": run.get("sourceRegion"),
        "region": run.get("region"),
        "role": run.get("role"),
        "axis": run.get("axis"),
        "outputPath": run.get("outputPath"),
        "manifestPath": str(manifest_path),
        "status": status,
        "returnCode": 0,
    }


def _execute_run(index: int, run: dict[str, Any], cwd: Path | None) -> dict[str, Any]:
    command = run.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise SystemExit(f"{run.get('name', index)}: missing string command array")
    manifest_path = Path(str(run["outputPath"])) / "holonomy-manifest.json"
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    status = "completed" if completed.returncode == 0 and manifest_path.exists() else "failed"
    record = _run_record(index, run, status, manifest_path)
    record.update(
        {
            "returnCode": completed.returncode,
            "durationSeconds": time.monotonic() - started,
            "stdoutTail": completed.stdout[-4000:],
            "stderrTail": completed.stderr[-4000:],
            "command": command,
        }
    )
    return record


def summarize_completed_runs(spec: dict[str, Any], *, output: Path) -> dict[str, Any]:
    rows = []
    traces_by_key: dict[tuple[str, int, str, str, str, str, str], dict[str, Any]] = {}
    packet_dir = output.parent / "packets"
    trace_dir = output.parent / "terminal-traces"
    for run in spec.get("runs", []):
        if not isinstance(run, dict):
            continue
        manifest_path = Path(str(run["outputPath"])) / "holonomy-manifest.json"
        if not manifest_path.exists():
            continue
        packet = summarize_stateful_continuation(manifest_path)
        packet_path = packet_dir / f"{run['name']}.json"
        _write_json(packet_path, packet)
        terminal_trace = load_terminal_trace(manifest_path)
        trace_path = trace_dir / f"{run['name']}.json"
        _write_json(trace_path, terminal_trace)
        key = (
            str(run["case"]),
            int(run["pairIndex"]),
            str(run["family"]),
            str(run.get("sourceRegion", run["region"])),
            str(run["region"]),
            str(run["axis"]),
            str(run["role"]),
        )
        traces_by_key[key] = terminal_trace
        rows.append(
            {
                "name": run["name"],
                "case": run["case"],
                "pairIndex": int(run["pairIndex"]),
                "family": run["family"],
                "sourceRegion": run.get("sourceRegion", run["region"]),
                "region": run["region"],
                "role": run["role"],
                "axis": run["axis"],
                "packetPath": str(packet_path),
                "terminalTracePath": str(trace_path),
                "pointCount": packet["pointCount"],
                "endpointPhenotypeDistance": packet["endpointPhenotypeDistance"],
                "endpointTransportedStateDistance": packet[
                    "endpointTransportedStateDistance"
                ],
                "endpointTerminalDistance": terminal_trace["endpointTerminalDistance"],
                "maxTerminalDistanceFromStart": terminal_trace[
                    "maxTerminalDistanceFromStart"
                ],
                "maxTerminalStepDelta": terminal_trace["maxTerminalStepDelta"],
                "topEndpointTerminalAxisDeltas": terminal_trace["topEndpointAxisDeltas"],
                "outputPath": run["outputPath"],
            }
        )
    pair_scores = []
    pair_keys = sorted(
        {
            (case, pair_index, family, source_region, region, axis)
            for case, pair_index, family, source_region, region, axis, _ in traces_by_key
        }
    )
    for case, pair_index, family, source_region, region, axis in pair_keys:
        nearest = traces_by_key.get(
            (
                case,
                pair_index,
                family,
                source_region,
                region,
                axis,
                "nearestTerminalCentroidSpecimenId",
            )
        )
        farthest = traces_by_key.get(
            (
                case,
                pair_index,
                family,
                source_region,
                region,
                axis,
                "farthestTerminalSpecimenId",
            )
        )
        if nearest is None or farthest is None:
            continue
        pair_scores.append(
            {
                "case": case,
                "pairIndex": pair_index,
                "family": family,
                "sourceRegion": source_region,
                "region": region,
                "axis": axis,
                **score_role_pair(nearest_trace=nearest, farthest_trace=farthest),
            }
        )
    return {
        "packetKind": "fiber_survival_assay_panel_v1",
        "generatedAt": _now(),
        "sourceSpec": spec.get("sourceSpec", spec.get("sourceNullValidation")),
        "completedRunCount": len(rows),
        "rolePairScoreCount": len(pair_scores),
        "rolePairScores": pair_scores,
        "runs": sorted(rows, key=lambda row: str(row["name"])),
    }


def compare_panel(panel: dict[str, Any]) -> dict[str, Any]:
    positive = {
        (
            str(row["family"]),
            str(row.get("sourceRegion", row["region"])),
            str(row["axis"]),
            int(row["pairIndex"]),
        ): row
        for row in panel.get("rolePairScores", [])
        if isinstance(row, dict) and row.get("case") == "positive"
    }
    control = {
        (
            str(row["family"]),
            str(row.get("sourceRegion", row["region"])),
            str(row["axis"]),
            int(row["pairIndex"]),
        ): row
        for row in panel.get("rolePairScores", [])
        if isinstance(row, dict) and row.get("case") == "control"
    }
    rows = []
    for family, source_region, axis, pair_index in sorted(set(positive) & set(control)):
        positive_row = positive[(family, source_region, axis, pair_index)]
        control_row = control[(family, source_region, axis, pair_index)]
        positive_ratio = float(positive_row["survivalRatio"])
        control_ratio = float(control_row["survivalRatio"])
        positive_end = float(positive_row["endTerminalSeparation"])
        control_end = float(control_row["endTerminalSeparation"])
        rows.append(
            {
                "family": family,
                "sourceRegion": source_region,
                "axis": axis,
                "pairIndex": pair_index,
                "positiveRegion": positive_row["region"],
                "controlRegion": control_row["region"],
                "positiveSurvivalRatio": positive_ratio,
                "controlSurvivalRatio": control_ratio,
                "survivalRatioDelta": positive_ratio - control_ratio,
                "positiveEndTerminalSeparation": positive_end,
                "controlEndTerminalSeparation": control_end,
                "endTerminalSeparationDelta": positive_end - control_end,
            }
        )
    summaries = []
    summary_keys = sorted(
        {(row["family"], row["sourceRegion"], row["axis"]) for row in rows}
    )
    for family, source_region, axis in summary_keys:
        selected = [
            row
            for row in rows
            if row["family"] == family
            and row["sourceRegion"] == source_region
            and row["axis"] == axis
        ]
        ratio_deltas = [float(row["survivalRatioDelta"]) for row in selected]
        end_deltas = [float(row["endTerminalSeparationDelta"]) for row in selected]
        summaries.append(
            {
                "family": family,
                "sourceRegion": source_region,
                "axis": axis,
                "comparisonCount": len(selected),
                "meanSurvivalRatioDelta": _mean(ratio_deltas),
                "survivalRatioDeltaMeanBootstrap95CI": _exact_bootstrap_mean_ci(
                    ratio_deltas
                ),
                "meanEndTerminalSeparationDelta": _mean(end_deltas),
                "endTerminalSeparationDeltaMeanBootstrap95CI": _exact_bootstrap_mean_ci(
                    end_deltas
                ),
                "positiveBeatsControlOnSurvivalRatio": sum(
                    1 for value in ratio_deltas if value > 0
                ),
                "positiveBeatsControlOnEndSeparation": sum(
                    1 for value in end_deltas if value > 0
                ),
                "positiveBeatsControlOnBoth": sum(
                    1
                    for row in selected
                    if row["survivalRatioDelta"] > 0
                    and row["endTerminalSeparationDelta"] > 0
                ),
            }
        )
    return {
        "packetKind": "fiber_survival_assay_comparison_v1",
        "generatedAt": _now(),
        "sourcePanel": panel.get("sourcePanel", panel.get("sourceSpec")),
        "sourceSpec": panel.get("sourceSpec"),
        "completedComparisonCount": len(rows),
        "positiveBeatsControlOnSurvivalRatio": sum(
            1 for row in rows if row["survivalRatioDelta"] > 0
        ),
        "positiveBeatsControlOnEndSeparation": sum(
            1 for row in rows if row["endTerminalSeparationDelta"] > 0
        ),
        "positiveBeatsControlOnBoth": sum(
            1
            for row in rows
            if row["survivalRatioDelta"] > 0 and row["endTerminalSeparationDelta"] > 0
        ),
        "familyAxisSummaries": summaries,
        "comparisons": rows,
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[int(position)]
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    return lower + (upper - lower) * (position - lower_index)


def _exact_bootstrap_mean_ci(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"lower": None, "upper": None}
    if len(values) == 1:
        return {"lower": values[0], "upper": values[0]}
    if len(values) > 8:
        return _normal_mean_ci(values)
    means = [
        sum(values[index] for index in indices) / len(indices)
        for indices in product(range(len(values)), repeat=len(values))
    ]
    return {"lower": _quantile(means, 0.025), "upper": _quantile(means, 0.975)}


def _normal_mean_ci(values: list[float]) -> dict[str, float | None]:
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    half_width = 1.96 * math.sqrt(variance / len(values))
    return {"lower": mean - half_width, "upper": mean + half_width}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lenia-swarm-fiber survival-assay",
        description="Build, summarize, and compare fiber survival assay packets.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-spec", help="Build an assay run spec from null validation")
    build.add_argument("--null-validation", required=True, type=Path)
    build.add_argument("--flow-runs-root", required=True, type=Path)
    build.add_argument("--output-root", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--cli-binary", default=".build/release/LeniaCLI")
    build.add_argument("--path-root", type=Path)
    build.add_argument("--family", action="append", dest="families")
    build.add_argument("--positive-region", action="append", dest="positive_regions")
    build.add_argument("--pair-limit", type=int, default=3)
    build.add_argument("--p-value-max", type=float, default=0.05)
    build.add_argument("--axis", action="append", type=parse_axis_spec)
    build.add_argument("--samples-per-segment", type=int, default=2)
    build.add_argument("--write-loops", action="store_true")

    loops = sub.add_parser("write-loops", help="Write loop JSON files from an assay spec")
    loops.add_argument("--spec", required=True, type=Path)

    run = sub.add_parser("run", help="Execute holonomy commands from an assay spec")
    run.add_argument("--spec", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--jobs", type=int, default=1)
    run.add_argument("--limit", type=int)
    run.add_argument("--rerun", action="store_true")

    summarize = sub.add_parser("summarize", help="Summarize completed holonomy runs")
    summarize.add_argument("--spec", required=True, type=Path)
    summarize.add_argument("--output", required=True, type=Path)

    compare = sub.add_parser("compare", help="Compare positive and control role-pair scores")
    compare.add_argument("--panel", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "build-spec":
        null_path = args.null_validation.resolve()
        path_root = args.path_root.resolve() if args.path_root is not None else None
        axes = args.axis or [parse_axis_spec(value) for value in DEFAULT_AXES]
        spec = build_spec_from_null_validation(
            null_validation=_read_json(null_path),
            null_validation_path=null_path,
            flow_runs_root=args.flow_runs_root.resolve(),
            output_root=args.output_root.resolve(),
            cli_binary=str(args.cli_binary),
            path_root=path_root,
            families=args.families,
            positive_regions=args.positive_regions,
            pair_limit=int(args.pair_limit),
            axes=axes,
            samples_per_segment=int(args.samples_per_segment),
            p_value_max=float(args.p_value_max),
        )
        _write_json(args.output.resolve(), spec)
        if args.write_loops:
            loop_count = write_loops(spec)
        else:
            loop_count = 0
        print(
            "Fiber survival assay spec:"
            f" runs={spec['runCount']} loops_written={loop_count} output={args.output}"
        )
        return 0
    if args.command == "write-loops":
        spec = _read_json(args.spec.resolve())
        loop_count = write_loops(spec)
        print(f"Fiber survival loops: written={loop_count}")
        return 0
    if args.command == "run":
        spec_path = args.spec.resolve()
        spec = _read_json(spec_path)
        spec["sourceSpec"] = str(spec_path)
        packet = run_spec(
            spec,
            output=args.output.resolve(),
            jobs=int(args.jobs),
            rerun=bool(args.rerun),
            limit=args.limit,
        )
        print(
            "Fiber survival run:"
            f" executed={packet['executedRunCount']}"
            f" completed={packet['completedRunCount']}"
            f" failed={packet['failedRunCount']}"
            f" skipped={packet['skippedCompletedRunCount']}"
            f" output={args.output}"
        )
        return 1 if packet["failedRunCount"] else 0
    if args.command == "summarize":
        spec_path = args.spec.resolve()
        spec = _read_json(spec_path)
        spec["sourceSpec"] = str(spec_path)
        panel = summarize_completed_runs(spec, output=args.output.resolve())
        _write_json(args.output.resolve(), panel)
        print(
            "Fiber survival panel:"
            f" completed={panel['completedRunCount']}"
            f" role_pairs={panel['rolePairScoreCount']}"
            f" output={args.output}"
        )
        return 0
    if args.command == "compare":
        panel_path = args.panel.resolve()
        panel = _read_json(panel_path)
        panel["sourcePanel"] = str(panel_path)
        comparison = compare_panel(panel)
        _write_json(args.output.resolve(), comparison)
        print(
            "Fiber survival comparison:"
            f" comparisons={comparison['completedComparisonCount']}"
            f" positive_both={comparison['positiveBeatsControlOnBoth']}"
            f" output={args.output}"
        )
        return 0
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
