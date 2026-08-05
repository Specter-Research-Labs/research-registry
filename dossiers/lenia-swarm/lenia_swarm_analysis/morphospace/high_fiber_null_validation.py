from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from duckdb import DuckDBPyConnection

from .common_morphology import FEATURE_SPACE_ID as COMMON_FEATURE_SPACE_ID
from .derive_lenia_features import FEATURE_SPACE_ID as TERMINAL_FEATURE_SPACE_ID

TRACK1_FAMILY_ALGORITHMS: dict[str, str] = {
    "2c10_r17_20": "fl-2c10-r17-20-initshift-harvest",
    "2c10_r7_10": "fl-2c10-r7-10-initshift-harvest",
    "2c20": "fl-2c20-harvest",
    "3c15": "fl-3c15-harvest",
}

DEFAULT_COMMON_REGION_AXES: tuple[str, ...] = (
    "elongation",
    "bilateral_symmetry",
    "radial_symmetry",
    "compactness",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "median": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "min": _finite_or_none(float(np.min(array))),
        "mean": _finite_or_none(float(np.mean(array))),
        "median": _finite_or_none(float(np.median(array))),
        "max": _finite_or_none(float(np.max(array))),
    }


def _rms_dispersion(matrix: np.ndarray) -> float:
    if matrix.shape[0] == 0:
        return 0.0
    variance = np.var(matrix, axis=0)
    return float(math.sqrt(float(np.sum(variance))))


def _one_sided_ge_pvalue(*, observed: float, null_values: list[float]) -> float | None:
    if not null_values:
        return None
    exceedances = sum(value >= observed for value in null_values)
    return float((1 + exceedances) / (len(null_values) + 1))


def _percentile_le(*, observed: float, values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(value <= observed for value in values) / len(values))


def _axis_ids(connection: DuckDBPyConnection, feature_space_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT axis_id
        FROM feature_axes
        WHERE feature_space_id = ?
        ORDER BY axis_index, axis_id
        """,
        [feature_space_id],
    ).fetchall()
    return [str(row[0]) for row in rows]


def _pivot_sql(feature_space_id: str, axes: list[str], alias: str) -> str:
    columns = ",\n".join(
        f"                max(CASE WHEN axis_id = '{axis}' THEN normalized_value END) AS {axis}"
        for axis in axes
    )
    return f"""
        {alias} AS (
            SELECT
                specimen_id,
                run_id,
                source_algorithm,
{columns}
            FROM comparison_feature_values_vw
            WHERE feature_space_id = '{feature_space_id}'
              AND source_id = 'lenia_swarm'
              AND source_algorithm = ?
            GROUP BY specimen_id, run_id, source_algorithm
        )
    """


def _load_family_joined(
    connection: DuckDBPyConnection,
    *,
    source_algorithm: str,
    common_axes: list[str],
    terminal_axes: list[str],
) -> tuple[list[str], np.ndarray, np.ndarray]:
    common_cols = ", ".join(f"c.{axis}" for axis in common_axes)
    terminal_cols = ", ".join(f"t.{axis}" for axis in terminal_axes)
    rows = connection.execute(
        f"""
        WITH
        {_pivot_sql(COMMON_FEATURE_SPACE_ID, common_axes, 'c')},
        {_pivot_sql(TERMINAL_FEATURE_SPACE_ID, terminal_axes, 't')}
        SELECT c.specimen_id, {common_cols}, {terminal_cols}
        FROM c
        JOIN t USING (specimen_id, run_id, source_algorithm)
        WHERE {" AND ".join(f"c.{axis} IS NOT NULL" for axis in common_axes)}
          AND {" AND ".join(f"t.{axis} IS NOT NULL" for axis in terminal_axes)}
        ORDER BY c.specimen_id
        """,
        [source_algorithm, source_algorithm],
    ).fetchall()
    specimen_ids = [str(row[0]) for row in rows]
    common = np.asarray([row[1 : 1 + len(common_axes)] for row in rows], dtype=np.float64)
    terminal = np.asarray([row[1 + len(common_axes) :] for row in rows], dtype=np.float64)
    return specimen_ids, common, terminal


def _region_value(value: float) -> str:
    if value < -0.5:
        return "low"
    if value > 0.5:
        return "high"
    return "mid"


def _region_label(common_row: np.ndarray, axes: list[str], axis_indices: list[int]) -> str:
    return "|".join(
        f"{axis}:{_region_value(float(common_row[axis_index]))}"
        for axis, axis_index in zip(axes, axis_indices, strict=True)
    )


def _target_regions(packet: dict[str, Any], limit: int) -> list[str]:
    ranked = packet.get("rankedSharedHighFiberRegions")
    if isinstance(ranked, list):
        regions = [row.get("region") for row in ranked if isinstance(row, dict)]
        selected = [str(region) for region in regions if isinstance(region, str)][:limit]
    else:
        shared = packet.get("sharedRegionsAcrossAllFamilies")
        if not isinstance(shared, list):
            raise ValueError(
                "source packet does not expose ranked or shared high-fiber regions"
            )
        regions = [row.get("region") for row in shared if isinstance(row, dict)]
        selected = [str(region) for region in regions if isinstance(region, str)][:limit]
    expected_axes = list(DEFAULT_COMMON_REGION_AXES)
    for region in selected:
        actual_axes = [part.split(":", 1)[0] for part in region.split("|")]
        if actual_axes != expected_axes:
            raise ValueError(
                f"source packet region axes {actual_axes} do not match v3 axes "
                f"{expected_axes}"
            )
    return selected


def _region_indices(
    *,
    common: np.ndarray,
    common_axes: list[str],
    region_axes: tuple[str, ...],
) -> dict[str, np.ndarray]:
    axis_indices = [common_axes.index(axis) for axis in region_axes]
    rows: dict[str, list[int]] = defaultdict(list)
    for index, common_row in enumerate(common):
        rows[_region_label(common_row, list(region_axes), axis_indices)].append(index)
    return {region: np.asarray(indices, dtype=np.int64) for region, indices in rows.items()}


def _terminal_examples(
    *,
    indices: np.ndarray,
    specimen_ids: list[str],
    terminal: np.ndarray,
) -> dict[str, str]:
    ranks = _terminal_example_ranks(indices=indices, specimen_ids=specimen_ids, terminal=terminal)
    return _terminal_examples_from_ranks(ranks)


def _terminal_examples_from_ranks(ranks: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    return {
        "nearestTerminalCentroidSpecimenId": ranks["nearestTerminalCentroid"][0]["specimenId"],
        "farthestTerminalSpecimenId": ranks["farthestTerminal"][0]["specimenId"],
    }


def _terminal_example_ranks(
    *,
    indices: np.ndarray,
    specimen_ids: list[str],
    terminal: np.ndarray,
    limit: int = 6,
) -> dict[str, list[dict[str, Any]]]:
    terminal_region = terminal[indices]
    centroid = np.mean(terminal_region, axis=0)
    distances = np.linalg.norm(terminal_region - centroid, axis=1)
    nearest_order = np.argsort(distances, kind="stable")[:limit]
    farthest_order = np.argsort(-distances, kind="stable")[:limit]

    def rows(order: np.ndarray) -> list[dict[str, Any]]:
        return [
            {
                "rank": rank + 1,
                "specimenId": specimen_ids[int(indices[int(local_index)])],
                "distanceToTerminalCentroid": _finite_or_none(float(distances[int(local_index)])),
            }
            for rank, local_index in enumerate(order)
        ]

    return {
        "nearestTerminalCentroid": rows(nearest_order),
        "farthestTerminal": rows(farthest_order),
    }


def _validate_family_region(
    *,
    region: str,
    specimen_ids: list[str],
    common: np.ndarray,
    terminal: np.ndarray,
    regions: dict[str, np.ndarray],
    null_replicates: int,
    rng: np.random.Generator,
    min_region_count: int,
) -> dict[str, Any]:
    indices = regions.get(region)
    if indices is None or indices.size < min_region_count:
        return {
            "status": "skipped",
            "reason": "target region is absent or below minimum region count",
            "region": region,
            "count": int(indices.size) if indices is not None else 0,
        }

    common_region = common[indices]
    terminal_region = terminal[indices]
    common_rms = _rms_dispersion(common_region)
    terminal_rms = _rms_dispersion(terminal_region)
    ratio = terminal_rms / common_rms if common_rms > 0 else None

    null_terminal_rms: list[float] = []
    null_ratio: list[float] = []
    for _ in range(null_replicates):
        sampled_indices = rng.choice(terminal.shape[0], size=int(indices.size), replace=False)
        sampled_terminal_rms = _rms_dispersion(terminal[sampled_indices])
        null_terminal_rms.append(sampled_terminal_rms)
        if common_rms > 0:
            null_ratio.append(sampled_terminal_rms / common_rms)

    control_rows = []
    for control_region, control_indices in regions.items():
        if control_region == region or control_indices.size < min_region_count:
            continue
        control_common_rms = _rms_dispersion(common[control_indices])
        control_terminal_rms = _rms_dispersion(terminal[control_indices])
        control_example_ranks = _terminal_example_ranks(
            indices=control_indices,
            specimen_ids=specimen_ids,
            terminal=terminal,
        )
        control_rows.append(
            {
                "region": control_region,
                "count": int(control_indices.size),
                "commonRmsDispersion": _finite_or_none(control_common_rms),
                "terminalRmsDispersion": _finite_or_none(control_terminal_rms),
                "terminalToCommonDispersionRatio": (
                    _finite_or_none(control_terminal_rms / control_common_rms)
                    if control_common_rms > 0
                    else None
                ),
                "examples": _terminal_examples_from_ranks(control_example_ranks),
                "exampleRanks": control_example_ranks,
            }
        )

    control_terminal = [
        float(row["terminalRmsDispersion"])
        for row in control_rows
        if row["terminalRmsDispersion"] is not None
    ]
    control_ratios = [
        float(row["terminalToCommonDispersionRatio"])
        for row in control_rows
        if row["terminalToCommonDispersionRatio"] is not None
    ]
    example_ranks = _terminal_example_ranks(
        indices=indices,
        specimen_ids=specimen_ids,
        terminal=terminal,
    )
    return {
        "status": "measured",
        "region": region,
        "count": int(indices.size),
        "observed": {
            "commonRmsDispersion": _finite_or_none(common_rms),
            "terminalRmsDispersion": _finite_or_none(terminal_rms),
            "terminalToCommonDispersionRatio": (
                _finite_or_none(ratio) if ratio is not None else None
            ),
        },
        "examples": _terminal_examples_from_ranks(example_ranks),
        "exampleRanks": example_ranks,
        "terminalLabelShuffleNull": {
            "replicates": null_replicates,
            "terminalRmsDispersion": _summary(null_terminal_rms),
            "terminalToCommonDispersionRatio": _summary(null_ratio),
            "terminalRmsOneSidedPValue": _one_sided_ge_pvalue(
                observed=terminal_rms,
                null_values=null_terminal_rms,
            ),
            "ratioOneSidedPValue": (
                _one_sided_ge_pvalue(observed=ratio, null_values=null_ratio)
                if ratio is not None
                else None
            ),
        },
        "otherRegionControls": {
            "regionCount": len(control_rows),
            "terminalRmsPercentile": _percentile_le(
                observed=terminal_rms,
                values=control_terminal,
            ),
            "ratioPercentile": (
                _percentile_le(observed=ratio, values=control_ratios)
                if ratio is not None
                else None
            ),
            "topByRatio": sorted(
                control_rows,
                key=lambda row: float(row["terminalToCommonDispersionRatio"] or -1.0),
                reverse=True,
            )[:8],
            "bottomByRatio": sorted(
                control_rows,
                key=lambda row: float(row["terminalToCommonDispersionRatio"] or math.inf),
            )[:8],
        },
    }


def build_high_fiber_null_validation_packet(
    connection: DuckDBPyConnection,
    *,
    source_packet_path: Path,
    target_region_limit: int = 3,
    null_replicates: int = 256,
    seed: int = 20260527,
    min_region_count: int = 128,
    family_algorithms: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_packet = _read_json(source_packet_path)
    family_map = family_algorithms or TRACK1_FAMILY_ALGORITHMS
    common_axes = _axis_ids(connection, COMMON_FEATURE_SPACE_ID)
    terminal_axes = _axis_ids(connection, TERMINAL_FEATURE_SPACE_ID)
    missing_region_axes = [axis for axis in DEFAULT_COMMON_REGION_AXES if axis not in common_axes]
    if missing_region_axes:
        raise ValueError(f"missing common region axes: {', '.join(missing_region_axes)}")
    regions = _target_regions(source_packet, target_region_limit)
    rng = np.random.default_rng(seed)
    family_data: dict[str, tuple[list[str], np.ndarray, np.ndarray, dict[str, np.ndarray]]] = {}
    for family, source_algorithm in family_map.items():
        specimen_ids, common, terminal = _load_family_joined(
            connection,
            source_algorithm=source_algorithm,
            common_axes=common_axes,
            terminal_axes=terminal_axes,
        )
        indexed_regions = _region_indices(
            common=common,
            common_axes=common_axes,
            region_axes=DEFAULT_COMMON_REGION_AXES,
        )
        family_data[family] = (specimen_ids, common, terminal, indexed_regions)
    region_rows = []
    for region in regions:
        family_rows: dict[str, Any] = {}
        for family, (specimen_ids, common, terminal, indexed_regions) in family_data.items():
            family_rows[family] = _validate_family_region(
                region=region,
                specimen_ids=specimen_ids,
                common=common,
                terminal=terminal,
                regions=indexed_regions,
                null_replicates=null_replicates,
                rng=rng,
                min_region_count=min_region_count,
            )
        measured = [row for row in family_rows.values() if row["status"] == "measured"]
        region_rows.append(
            {
                "region": region,
                "measuredFamilyCount": len(measured),
                "families": family_rows,
            }
        )
    return {
        "packetKind": "track1_high_fiber_null_validation_v2",
        "sourcePacket": str(source_packet_path),
        "method": {
            "targetRegionLimit": target_region_limit,
            "nullReplicates": null_replicates,
            "seed": seed,
            "minimumRegionCount": min_region_count,
            "commonRegionAxes": list(DEFAULT_COMMON_REGION_AXES),
            "null": (
                "Terminal descriptors are randomly reassigned within the same family "
                "while the target common-morphology bin and occupancy are held fixed."
            ),
        },
        "regions": region_rows,
    }
