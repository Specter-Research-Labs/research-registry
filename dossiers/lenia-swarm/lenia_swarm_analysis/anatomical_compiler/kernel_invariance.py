"""Stage 1, kernel-ordering control: how much of the apparent phenotype to
genotype invertibility in multi-kernel configs is real, and how much is an
artifact of the arbitrary order kernels happen to be stored in?

For configs whose kernels are genuinely exchangeable (more than one kernel, with
the structural params varying across creatures) the stored kernel order is
arbitrary, so euclidean distance on the flattened genotype counts a pure
relabeling as a real difference. The fix is a permutation-invariant distance: for
each pair of creatures match their kernels by optimal assignment and sum the
matched per-kernel distances. Sorting the kernels instead is not a fix, it forces
the sort-key dimension to be monotonic and collapses the apparent genotype
dimension.

We report the inverse locality ratio under both the stored-order euclidean
distance and the matched distance, with a shuffled-pairing null for each. If the
matched ratio rises toward the null while the euclidean one sat below it, the
euclidean signal was kernel-ordering rather than genotype.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from lenia_swarm_analysis.anatomical_compiler.fiber_wellposedness import (
    PHENOTYPE_COLUMNS,
    _kernel_matrix,
    _mean_neighbor_distance,
    _neighbors,
    _phenotype_vector,
    _robust_scale,
    phenotype_neighbors_permuted,
)


def _robust_scale_kernels(kernels: list[np.ndarray]) -> list[np.ndarray]:
    pooled = np.concatenate(kernels, axis=0)
    median = np.median(pooled, axis=0)
    q75, q25 = np.percentile(pooled, [75.0, 25.0], axis=0)
    scale = q75 - q25
    fallback = np.std(pooled, axis=0)
    scale = np.where(scale > 1e-12, scale, fallback)
    keep = scale > 1e-12
    median = median[keep]
    scale = scale[keep]
    return [(kernel[:, keep] - median) / scale for kernel in kernels]


def _matched_distance(left: np.ndarray, right: np.ndarray) -> float:
    costs = cdist(left, right, metric="euclidean")
    rows, columns = linear_sum_assignment(costs * costs)
    return float(np.sqrt(np.sum(costs[rows, columns] ** 2)))


def _stored_order_distance(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.sqrt(np.sum((left - right) ** 2)))


def _distance_matrix(
    kernels: list[np.ndarray], *, matched: bool
) -> np.ndarray:
    count = len(kernels)
    distances = np.zeros((count, count), dtype=np.float64)
    for i in range(count):
        for j in range(i + 1, count):
            if matched:
                value = _matched_distance(kernels[i], kernels[j])
            else:
                value = _stored_order_distance(kernels[i], kernels[j])
            distances[i, j] = value
            distances[j, i] = value
    return distances


def _pairwise_distances(matrix: np.ndarray) -> np.ndarray:
    gram = matrix @ matrix.T
    squared = np.diag(gram)
    distances = squared[:, None] + squared[None, :] - 2.0 * gram
    np.maximum(distances, 0.0, out=distances)
    np.sqrt(distances, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def _inverse_ratio(
    genotype_distances: np.ndarray,
    phenotype_neighbors: np.ndarray,
    *,
    null_repeats: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    tri = np.triu_indices(genotype_distances.shape[0], k=1)
    mean_genotype = float(np.mean(genotype_distances[tri]))
    observed = _mean_neighbor_distance(genotype_distances, phenotype_neighbors)
    ratio = observed / mean_genotype if mean_genotype > 1e-12 else None
    nulls: list[float] = []
    for _ in range(null_repeats):
        permutation = rng.permutation(genotype_distances.shape[0])
        shuffled = phenotype_neighbors_permuted(phenotype_neighbors, permutation)
        nulls.append(_mean_neighbor_distance(genotype_distances, shuffled) / mean_genotype)
    null_array = np.asarray(nulls, dtype=np.float64)
    null_mean = float(np.mean(null_array))
    null_std = float(np.std(null_array))
    z = (ratio - null_mean) / null_std if ratio is not None and null_std else None
    return {"ratio": ratio, "nullMean": null_mean, "z": z}


def _load(connection: sqlite3.Connection, config_hash: str) -> tuple[
    list[np.ndarray], np.ndarray, np.ndarray, bool
] | None:
    columns = ", ".join(("genotype_json", "morphometrics_json", *PHENOTYPE_COLUMNS))
    rows = connection.execute(
        f"SELECT {columns} FROM creatures "
        "WHERE config_hash = ? AND is_stable = 1 AND genotype_json IS NOT NULL",
        (config_hash,),
    ).fetchall()
    try:
        kernels = [_kernel_matrix(row["genotype_json"]) for row in rows]
    except ValueError:
        return None
    metric_rows = [_phenotype_vector(row) for row in rows]
    metrics = np.asarray([values for values, _ in metric_rows], dtype=np.float64)
    present = np.asarray([flags for _, flags in metric_rows], dtype=bool)
    structural = np.stack([kernel[:, 3] for kernel in kernels], axis=0)
    r_varies = bool(np.any(np.std(structural, axis=0) > 1e-9))
    return kernels, metrics, present, r_varies


def run(
    compendium_path: Path,
    *,
    min_count: int,
    neighbor_k: int,
    null_repeats: int,
    seed: int,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{compendium_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    results: list[dict[str, Any]] = []
    try:
        cursor = connection.execute(
            "SELECT config_hash FROM creatures "
            "WHERE is_stable = 1 AND config_hash IS NOT NULL "
            "GROUP BY config_hash HAVING COUNT(*) >= ? ORDER BY COUNT(*) DESC",
            (min_count,),
        )
        config_hashes = [str(row[0]) for row in cursor.fetchall()]
        rng = np.random.default_rng(seed)
        for config_hash in config_hashes:
            loaded = _load(connection, config_hash)
            if loaded is None:
                continue
            kernels, metrics, present, r_varies = loaded
            kernel_count = kernels[0].shape[0]
            if kernel_count < 2 or not r_varies:
                continue
            if len({kernel.shape for kernel in kernels}) != 1:
                continue
            scaled_kernels = _robust_scale_kernels(kernels)
            phenotype_scaled = _robust_scale(metrics, present=present)
            phenotype_distances = _pairwise_distances(phenotype_scaled)
            phenotype_neighbors = _neighbors(phenotype_distances, neighbor_k)
            euclidean = _inverse_ratio(
                _distance_matrix(scaled_kernels, matched=False),
                phenotype_neighbors,
                null_repeats=null_repeats,
                rng=rng,
            )
            matched = _inverse_ratio(
                _distance_matrix(scaled_kernels, matched=True),
                phenotype_neighbors,
                null_repeats=null_repeats,
                rng=rng,
            )
            results.append(
                {
                    "config": config_hash,
                    "count": len(kernels),
                    "kernelCount": int(kernel_count),
                    "euclidean": euclidean,
                    "matched": matched,
                }
            )
    finally:
        connection.close()

    return {
        "compendium": str(compendium_path),
        "minCount": min_count,
        "neighborK": neighbor_k,
        "nullRepeats": null_repeats,
        "seed": seed,
        "configs": results,
    }


def _format_table(report: dict[str, Any]) -> str:
    header = (
        f"{'config':<26}{'n':>5}{'K':>4}"
        f"{'inv_euc':>9}{'z_euc':>8}{'inv_match':>11}{'z_match':>9}"
    )
    lines = [header, "-" * len(header)]
    for entry in report["configs"]:

        def cell(value: float | None, width: int) -> str:
            text = "na" if value is None else f"{value:.2f}"
            return f"{text:>{width}}"

        lines.append(
            f"{entry['config']:<26}{entry['count']:>5}{entry['kernelCount']:>4}"
            + cell(entry["euclidean"]["ratio"], 9)
            + cell(entry["euclidean"]["z"], 8)
            + cell(entry["matched"]["ratio"], 11)
            + cell(entry["matched"]["z"], 9)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compendium", default="artifacts/compendium.sqlite")
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/stage1_kernel_invariance.json",
    )
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--neighbor-k", type=int, default=8)
    parser.add_argument("--null-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260616)
    args = parser.parse_args(argv)

    compendium_path = Path(args.compendium).expanduser().resolve()
    if not compendium_path.is_file():
        raise SystemExit(f"Missing compendium: {compendium_path}")

    report = run(
        compendium_path,
        min_count=args.min_count,
        neighbor_k=args.neighbor_k,
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
