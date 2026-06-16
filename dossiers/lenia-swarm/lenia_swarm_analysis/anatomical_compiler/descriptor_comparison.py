"""Stage 1 of the anatomical compiler: does a richer phenotype descriptor sharpen
the inverse fiber?

Stage 0 measured well-posedness with the coarse creature-table metrics (mass,
speed, gyration and friends). Here we hold the genotype fixed and swap the
phenotype for the 16 terminal morphometric axes from the morphospace warehouse
(elongation, compactness, symmetry, locomotion and so on), then re-measure inverse
locality and local fiber dimension on the identical creatures. Because the
genotype is unchanged between the two phenotype variants, the metrics-to-warehouse
delta is robust to the open question of how to represent exchangeable-kernel
genotypes; only the absolute numbers carry that caveat.

The comparison is restricted to creatures that have all 16 warehouse axes, per
config, and to configs that retain enough such creatures.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from lenia_swarm_analysis.anatomical_compiler.fiber_wellposedness import (
    PHENOTYPE_COLUMNS,
    _config_summary,
    _genotype_vector,
    _phenotype_vector,
    _robust_scale,
    unique_genotype_indices,
)

AXIS_IDS: tuple[str, ...] = (
    "axial_polarity",
    "bilateral_symmetry",
    "boundary_complexity",
    "cavity_count",
    "center_offset",
    "compactness",
    "coverage",
    "elongation",
    "fragmentation",
    "left_right_asymmetry",
    "locomotion",
    "meander",
    "radial_symmetry",
    "rotational_symmetry",
    "spread",
    "symmetry_focus",
)


def _eligible_configs(connection: sqlite3.Connection, min_count: int) -> list[str]:
    cursor = connection.execute(
        "SELECT config_hash FROM creatures "
        "WHERE is_stable = 1 AND config_hash IS NOT NULL "
        "GROUP BY config_hash HAVING COUNT(*) >= ? ORDER BY COUNT(*) DESC",
        (min_count,),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _stable_rows(
    connection: sqlite3.Connection, config_hash: str
) -> dict[str, sqlite3.Row]:
    columns = ", ".join(("id", "genotype_json", "morphometrics_json", *PHENOTYPE_COLUMNS))
    cursor = connection.execute(
        f"SELECT {columns} FROM creatures "
        "WHERE config_hash = ? AND is_stable = 1 AND genotype_json IS NOT NULL",
        (config_hash,),
    )
    return {str(row["id"]): row for row in cursor.fetchall()}


def _warehouse_axes(
    duckdb_connection: duckdb.DuckDBPyConnection,
    ids: list[str],
    axes: tuple[str, ...],
) -> dict[str, np.ndarray]:
    duckdb_connection.execute("CREATE OR REPLACE TEMP TABLE query_ids(id VARCHAR)")
    duckdb_connection.executemany(
        "INSERT INTO query_ids VALUES (?)", [(identifier,) for identifier in ids]
    )
    rows = duckdb_connection.execute(
        """
        SELECT specimens.source_creature_id, specimen_axes.axis_id,
               specimen_axes.transformed_value
        FROM query_ids
        JOIN specimens ON specimens.source_creature_id = query_ids.id
        JOIN specimen_axes ON specimen_axes.specimen_id = specimens.specimen_id
        WHERE specimen_axes.axis_id IN ?
          AND specimen_axes.transformed_value IS NOT NULL
        """,
        [list(axes)],
    ).fetchall()
    axis_index = {axis_id: position for position, axis_id in enumerate(axes)}
    partial: dict[str, np.ndarray] = {}
    filled: dict[str, int] = {}
    for creature_id, axis_id, value in rows:
        vector = partial.setdefault(creature_id, np.full(len(axes), np.nan))
        vector[axis_index[axis_id]] = float(value)
        filled[creature_id] = filled.get(creature_id, 0) + 1
    return {
        creature_id: vector
        for creature_id, vector in partial.items()
        if filled[creature_id] == len(axes)
    }


def _build(
    rows: dict[str, sqlite3.Row], warehouse: dict[str, np.ndarray]
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    ids = sorted(identifier for identifier in rows if identifier in warehouse)
    genotype_rows: list[list[float]] = []
    metric_rows: list[list[float]] = []
    present_rows: list[list[bool]] = []
    warehouse_rows: list[np.ndarray] = []
    expected_length: int | None = None
    for identifier in ids:
        vector = _genotype_vector(rows[identifier]["genotype_json"])
        if expected_length is None:
            expected_length = len(vector)
        elif len(vector) != expected_length:
            return None
        genotype_rows.append(vector)
        values, present = _phenotype_vector(rows[identifier])
        metric_rows.append(values)
        present_rows.append(present)
        warehouse_rows.append(warehouse[identifier])
    return (
        ids,
        np.asarray(genotype_rows, dtype=np.float64),
        np.asarray(metric_rows, dtype=np.float64),
        np.asarray(present_rows, dtype=bool),
        np.stack(warehouse_rows, axis=0),
    )


def run(
    compendium_path: Path,
    morphospace_path: Path,
    *,
    axes: tuple[str, ...],
    min_count: int,
    min_covered: int,
    neighbor_k: int,
    fiber_k: int,
    null_repeats: int,
    seed: int,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{compendium_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    duckdb_connection = duckdb.connect(str(morphospace_path), read_only=True)
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        rng = np.random.default_rng(seed)
        for config_hash in _eligible_configs(connection, min_count):
            rows = _stable_rows(connection, config_hash)
            warehouse = _warehouse_axes(duckdb_connection, list(rows), axes)
            if len(warehouse) < min_covered:
                continue
            built = _build(rows, warehouse)
            if built is None:
                skipped.append(
                    {"config": config_hash, "reason": "inconsistent genotype length"}
                )
                continue
            ids, genotype, metrics, present, warehouse_matrix = built
            keep = unique_genotype_indices(genotype)
            if keep.shape[0] < min_covered:
                skipped.append(
                    {
                        "config": config_hash,
                        "reason": f"only {keep.shape[0]} distinct genotypes",
                    }
                )
                continue
            genotype = genotype[keep]
            metrics, present, warehouse_matrix = (
                metrics[keep],
                present[keep],
                warehouse_matrix[keep],
            )
            ids = [ids[index] for index in keep]
            genotype_scaled = _robust_scale(genotype, present=None)
            metrics_scaled = _robust_scale(metrics, present=present)
            warehouse_scaled = _robust_scale(warehouse_matrix, present=None)
            if (
                genotype_scaled.shape[1] == 0
                or metrics_scaled.shape[1] == 0
                or warehouse_scaled.shape[1] == 0
            ):
                skipped.append({"config": config_hash, "reason": "no varying columns"})
                continue
            metrics_summary = _config_summary(
                genotype_scaled,
                metrics_scaled,
                neighbor_k=neighbor_k,
                fiber_k=fiber_k,
                null_repeats=null_repeats,
                rng=rng,
            )
            warehouse_summary = _config_summary(
                genotype_scaled,
                warehouse_scaled,
                neighbor_k=neighbor_k,
                fiber_k=fiber_k,
                null_repeats=null_repeats,
                rng=rng,
            )
            results.append(
                {
                    "config": config_hash,
                    "count": len(ids),
                    "metrics": metrics_summary,
                    "warehouse": warehouse_summary,
                }
            )
    finally:
        duckdb_connection.close()
        connection.close()

    return {
        "compendium": str(compendium_path),
        "morphospace": str(morphospace_path),
        "axes": list(axes),
        "minCount": min_count,
        "minCovered": min_covered,
        "neighborK": neighbor_k,
        "fiberK": fiber_k,
        "nullRepeats": null_repeats,
        "seed": seed,
        "configs": results,
        "skipped": skipped,
    }


def _format_table(report: dict[str, Any]) -> str:
    header = (
        f"{'config':<26}{'n':>5}"
        f"{'inv_met':>9}{'inv_wh':>9}"
        f"{'nFib_met':>10}{'nFib_wh':>9}"
        f"{'spr_met':>9}{'spr_wh':>9}"
    )
    lines = [header, "-" * len(header)]
    for entry in report["configs"]:
        metrics = entry["metrics"]
        warehouse = entry["warehouse"]

        def cell(value: float | None, width: int) -> str:
            text = "na" if value is None else f"{value:.2f}"
            return f"{text:>{width}}"

        lines.append(
            f"{entry['config']:<26}{entry['count']:>5}"
            + cell(metrics["inverseLocalityRatio"], 9)
            + cell(warehouse["inverseLocalityRatio"], 9)
            + cell(metrics["normalizedFiberScore"], 10)
            + cell(warehouse["normalizedFiberScore"], 9)
            + cell(metrics["distanceSpearman"], 9)
            + cell(warehouse["distanceSpearman"], 9)
        )
    for entry in report["skipped"]:
        lines.append(f"{entry['config']:<26} skipped: {entry['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compendium", default="artifacts/compendium.sqlite")
    parser.add_argument("--morphospace", default="artifacts/morphospace.duckdb")
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/stage1_descriptor_comparison.json",
    )
    parser.add_argument(
        "--axes",
        default=",".join(AXIS_IDS),
        help="Comma-separated warehouse axis ids to use as the rich descriptor",
    )
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--min-covered", type=int, default=50)
    parser.add_argument("--neighbor-k", type=int, default=8)
    parser.add_argument("--fiber-k", type=int, default=15)
    parser.add_argument("--null-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260616)
    args = parser.parse_args(argv)

    compendium_path = Path(args.compendium).expanduser().resolve()
    morphospace_path = Path(args.morphospace).expanduser().resolve()
    if not compendium_path.is_file():
        raise SystemExit(f"Missing compendium: {compendium_path}")
    if not morphospace_path.is_file():
        raise SystemExit(f"Missing morphospace warehouse: {morphospace_path}")

    axes = tuple(axis.strip() for axis in args.axes.split(",") if axis.strip())
    report = run(
        compendium_path,
        morphospace_path,
        axes=axes,
        min_count=args.min_count,
        min_covered=args.min_covered,
        neighbor_k=args.neighbor_k,
        fiber_k=args.fiber_k,
        null_repeats=args.null_repeats,
        seed=args.seed,
    )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(_format_table(report))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
