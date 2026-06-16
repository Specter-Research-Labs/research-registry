"""Stage 0 of the anatomical compiler: measure how well-posed the phenotype to
genotype inverse map is, directly from the compendium.

For each physics config with enough viable (stable) creatures we build a genotype
matrix and a phenotype matrix over those creatures, then measure three things:

- forward locality (genotype -> phenotype): do genotype neighbors share a
  phenotype? A small ratio means the forward map is locally smooth.
- inverse locality (phenotype -> genotype): do phenotype neighbors share a
  genotype? A ratio near 1 (near the shuffled null) means the inverse fiber is
  fat and the inverse is ill-posed; a ratio well below the null means the
  phenotype pins the genotype.
- local fiber dimension: among a creature's phenotype neighbors, how many
  independent genotype directions are free. This is the participation ratio of
  the local genotype scatter, an estimate of the neutral-set dimension.

Genotype and phenotype columns are scaled robustly (median / IQR) and
constant columns are dropped, so a config that varies only its growth params
(h, m, s) over fixed kernels is handled without special casing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

PHENOTYPE_COLUMNS: tuple[str, ...] = (
    "mass_mean",
    "mass_std",
    "mass_min",
    "mass_max",
    "occupancy_mean",
    "variance_mean",
    "energy_mean",
    "speed_mean",
    "path_length",
    "displacement",
    "gyration",
    "center_velocity",
    "complexity_mean",
)

MORPHOMETRIC_KEYS: tuple[str, ...] = (
    "pathTortuosity",
    "movementEfficiency",
)


def _floats(value: Any) -> list[float]:
    return [float(item) for item in value]


def _kernel_matrix(genotype_json: str) -> np.ndarray:
    """Per-kernel parameter rows for one genotype.

    Row k is the concatenation of kernel k's params (m, s, h, r, a, b, w). The
    global R is excluded because it is shared across kernels. Used for the
    permutation-invariant genotype distance on configs whose kernels are
    genuinely exchangeable.
    """
    payload = json.loads(genotype_json)
    r, m, s, h = payload["r"], payload["m"], payload["s"], payload["h"]
    a, b, w = payload["a"], payload["b"], payload["w"]
    rows: list[list[float]] = []
    for index in range(len(m)):
        row = [float(m[index]), float(s[index]), float(h[index]), float(r[index])]
        row.extend(_floats(a[index]))
        row.extend(_floats(b[index]))
        row.extend(_floats(w[index]))
        rows.append(row)
    return np.asarray(rows, dtype=np.float64)


def _genotype_vector(genotype_json: str) -> list[float]:
    payload = json.loads(genotype_json)
    if not isinstance(payload, dict):
        raise ValueError("genotype_json is not an object")
    r, m, s, h = payload["r"], payload["m"], payload["s"], payload["h"]
    a, b, w = payload["a"], payload["b"], payload["w"]
    out: list[float] = [float(payload["R"])]
    for index in range(len(m)):
        out.extend((float(m[index]), float(s[index]), float(h[index]), float(r[index])))
        out.extend(_floats(a[index]))
        out.extend(_floats(b[index]))
        out.extend(_floats(w[index]))
    return out


def _phenotype_vector(row: sqlite3.Row) -> tuple[list[float], list[bool]]:
    values: list[float] = []
    present: list[bool] = []
    for column in PHENOTYPE_COLUMNS:
        raw = row[column]
        if raw is None:
            values.append(0.0)
            present.append(False)
        else:
            values.append(float(raw))
            present.append(True)
    morph_raw = row["morphometrics_json"]
    morph = json.loads(morph_raw) if morph_raw else {}
    for key in MORPHOMETRIC_KEYS:
        raw = morph.get(key)
        if raw is None:
            values.append(0.0)
            present.append(False)
        else:
            values.append(float(raw))
            present.append(True)
    return values, present


def _robust_scale(matrix: np.ndarray, present: np.ndarray | None) -> np.ndarray:
    columns: list[np.ndarray] = []
    for index in range(matrix.shape[1]):
        column = matrix[:, index]
        if present is not None and not present[:, index].all():
            continue
        median = float(np.median(column))
        q75, q25 = np.percentile(column, [75.0, 25.0])
        scale = float(q75 - q25)
        if scale <= 1e-12:
            std = float(np.std(column))
            if std <= 1e-12:
                continue
            scale = std
        columns.append((column - median) / scale)
    if not columns:
        return np.zeros((matrix.shape[0], 0), dtype=np.float64)
    return np.stack(columns, axis=1)


def _pairwise_distances(matrix: np.ndarray) -> np.ndarray:
    gram = matrix @ matrix.T
    squared = np.diag(gram)
    distances = squared[:, None] + squared[None, :] - 2.0 * gram
    np.maximum(distances, 0.0, out=distances)
    np.sqrt(distances, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def _neighbors(distances: np.ndarray, k: int) -> np.ndarray:
    count = distances.shape[0]
    effective = min(max(1, k), count - 1)
    neighbors = np.empty((count, effective), dtype=np.int64)
    for index in range(count):
        row = distances[index].copy()
        row[index] = np.inf
        candidates = np.argpartition(row, effective - 1)[:effective]
        neighbors[index] = candidates[np.argsort(row[candidates])]
    return neighbors


def _mean_neighbor_distance(
    target_distances: np.ndarray, neighbors: np.ndarray
) -> float:
    rows = np.arange(neighbors.shape[0])[:, None]
    return float(np.mean(target_distances[rows, neighbors]))


def _pearson(lhs: np.ndarray, rhs: np.ndarray) -> float | None:
    lhs_c = lhs - lhs.mean()
    rhs_c = rhs - rhs.mean()
    lhs_n = float(np.linalg.norm(lhs_c))
    rhs_n = float(np.linalg.norm(rhs_c))
    if lhs_n <= 1e-12 or rhs_n <= 1e-12:
        return None
    return float(np.dot(lhs_c, rhs_c) / (lhs_n * rhs_n))


def _participation_ratio(eigenvalues: np.ndarray) -> float:
    positive = eigenvalues[eigenvalues > 1e-12]
    if positive.size == 0:
        return 0.0
    total = float(np.sum(positive))
    return float(total * total / float(np.sum(positive * positive)))


def _local_fiber_dimension(
    genotype_scaled: np.ndarray, phenotype_neighbors: np.ndarray
) -> float:
    ratios: list[float] = []
    for index in range(phenotype_neighbors.shape[0]):
        block = genotype_scaled[phenotype_neighbors[index]]
        centered = block - block.mean(axis=0, keepdims=True)
        eigenvalues = np.linalg.svd(centered, compute_uv=False) ** 2
        ratios.append(_participation_ratio(eigenvalues))
    return float(np.mean(ratios))


def _inverse_ratio(
    genotype_distances: np.ndarray,
    phenotype_distances: np.ndarray,
    *,
    neighbor_k: int,
) -> float | None:
    tri = np.triu_indices(genotype_distances.shape[0], k=1)
    mean_genotype = float(np.mean(genotype_distances[tri]))
    if mean_genotype <= 1e-12:
        return None
    phenotype_neighbors = _neighbors(phenotype_distances, neighbor_k)
    return _mean_neighbor_distance(genotype_distances, phenotype_neighbors) / mean_genotype


def _injective_baseline_distances(
    genotype_scaled: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """A synthetic phenotype produced by a smooth bijection of the genotype.

    A random rotation followed by a tanh keeps the map injective on the bounded
    scaled domain, so the inverse-locality ratio it produces is the reference for
    a perfectly invertible map under this exact pipeline. The gap between the
    observed inverse ratio and this baseline is what actually measures fiber width;
    the shuffled null only tests whether any locality exists at all.
    """
    dimension = genotype_scaled.shape[1]
    rotation, _ = np.linalg.qr(rng.standard_normal((dimension, dimension)))
    synthetic = np.tanh(genotype_scaled @ rotation)
    return _pairwise_distances(synthetic)


def _config_summary(
    genotype_scaled: np.ndarray,
    phenotype_scaled: np.ndarray,
    *,
    neighbor_k: int,
    fiber_k: int,
    null_repeats: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    count = genotype_scaled.shape[0]
    genotype_distances = _pairwise_distances(genotype_scaled)
    phenotype_distances = _pairwise_distances(phenotype_scaled)

    tri = np.triu_indices(count, k=1)
    mean_genotype = float(np.mean(genotype_distances[tri]))
    mean_phenotype = float(np.mean(phenotype_distances[tri]))
    genotype_constant = float(np.std(genotype_distances[tri])) <= 1e-12
    phenotype_constant = float(np.std(phenotype_distances[tri])) <= 1e-12

    correlation = _pearson(genotype_distances[tri], phenotype_distances[tri])
    spearman = (
        None
        if genotype_constant or phenotype_constant
        else float(spearmanr(genotype_distances[tri], phenotype_distances[tri]).statistic)
    )

    clonal_neighbor_distances = genotype_distances[
        np.arange(count), _neighbors(genotype_distances, 1).ravel()
    ]
    clonal_fraction = float(
        np.mean(clonal_neighbor_distances <= 1e-9 * max(mean_genotype, 1e-12))
    )

    genotype_neighbors = _neighbors(genotype_distances, neighbor_k)
    phenotype_neighbors = _neighbors(phenotype_distances, neighbor_k)

    forward_ratio = (
        _mean_neighbor_distance(phenotype_distances, genotype_neighbors) / mean_phenotype
        if mean_phenotype > 1e-12
        else None
    )
    inverse_ratio = _inverse_ratio(
        genotype_distances, phenotype_distances, neighbor_k=neighbor_k
    )

    genotype_self = (
        _mean_neighbor_distance(genotype_distances, genotype_neighbors) / mean_genotype
        if mean_genotype > 1e-12
        else None
    )
    injective_ratio = _inverse_ratio(
        genotype_distances,
        _injective_baseline_distances(genotype_scaled, rng),
        neighbor_k=neighbor_k,
    )
    normalized_fiber = (
        (inverse_ratio - injective_ratio) / (1.0 - injective_ratio)
        if inverse_ratio is not None
        and injective_ratio is not None
        and injective_ratio < 1.0
        else None
    )
    asymmetry = (
        inverse_ratio - forward_ratio
        if inverse_ratio is not None and forward_ratio is not None
        else None
    )

    degenerate = mean_genotype <= 1e-12
    null_ratios: list[float] = []
    if not degenerate:
        for _ in range(null_repeats):
            permutation = rng.permutation(count)
            shuffled = phenotype_neighbors_permuted(phenotype_neighbors, permutation)
            null_ratios.append(
                _mean_neighbor_distance(genotype_distances, shuffled) / mean_genotype
            )
    null_array = np.asarray(null_ratios, dtype=np.float64)
    null_mean = float(np.mean(null_array)) if null_array.size else None
    null_std = float(np.std(null_array)) if null_array.size else None
    inverse_z = (
        (inverse_ratio - null_mean) / null_std
        if inverse_ratio is not None and null_mean is not None and null_std
        else None
    )

    subsample_ratios: list[float] = []
    subsample_size = max(neighbor_k + 1, int(round(0.8 * count)))
    if not degenerate and subsample_size < count:
        for _ in range(40):
            index = rng.choice(count, size=subsample_size, replace=False)
            block = np.ix_(index, index)
            value = _inverse_ratio(
                genotype_distances[block],
                phenotype_distances[block],
                neighbor_k=neighbor_k,
            )
            if value is not None:
                subsample_ratios.append(value)
    interval = (
        [float(np.percentile(subsample_ratios, 5)), float(np.percentile(subsample_ratios, 95))]
        if subsample_ratios
        else None
    )

    fiber_neighbors = _neighbors(phenotype_distances, fiber_k)
    fiber_dimension = _local_fiber_dimension(genotype_scaled, fiber_neighbors)
    global_eigenvalues = (
        np.linalg.svd(
            genotype_scaled - genotype_scaled.mean(axis=0, keepdims=True),
            compute_uv=False,
        )
        ** 2
    )
    genotype_dimension = _participation_ratio(global_eigenvalues)

    return {
        "count": int(count),
        "genotypeColumns": int(genotype_scaled.shape[1]),
        "phenotypeColumns": int(phenotype_scaled.shape[1]),
        "neighborK": int(min(max(1, neighbor_k), count - 1)),
        "fiberK": int(min(max(1, fiber_k), count - 1)),
        "distanceCorrelation": correlation,
        "distanceSpearman": spearman,
        "forwardLocalityRatio": forward_ratio,
        "inverseLocalityRatio": inverse_ratio,
        "inverseRatioInterval": interval,
        "genotypeSelfLocality": genotype_self,
        "injectiveBaselineRatio": injective_ratio,
        "normalizedFiberScore": normalized_fiber,
        "forwardInverseAsymmetry": asymmetry,
        "inverseNullMean": null_mean,
        "inverseNullStd": null_std,
        "inverseZ": inverse_z,
        "clonalFraction": clonal_fraction,
        "localFiberDimension": fiber_dimension,
        "genotypeEffectiveDimension": genotype_dimension,
        "fiberDimensionFraction": (
            fiber_dimension / genotype_dimension
            if genotype_dimension > 1e-9
            else None
        ),
    }


def phenotype_neighbors_permuted(
    neighbors: np.ndarray, permutation: np.ndarray
) -> np.ndarray:
    inverse = np.empty_like(permutation)
    inverse[permutation] = np.arange(permutation.shape[0])
    return inverse[neighbors[permutation]]


def _load_config_rows(
    connection: sqlite3.Connection, config_hash: str
) -> list[sqlite3.Row]:
    columns = ", ".join(("id", "genotype_json", "morphometrics_json", *PHENOTYPE_COLUMNS))
    cursor = connection.execute(
        f"SELECT {columns} FROM creatures "
        "WHERE config_hash = ? AND is_stable = 1 AND genotype_json IS NOT NULL",
        (config_hash,),
    )
    return cursor.fetchall()


def _eligible_configs(
    connection: sqlite3.Connection, min_count: int
) -> list[tuple[str, int]]:
    cursor = connection.execute(
        "SELECT config_hash, COUNT(*) n FROM creatures "
        "WHERE is_stable = 1 AND config_hash IS NOT NULL "
        "GROUP BY config_hash HAVING n >= ? ORDER BY n DESC",
        (min_count,),
    )
    return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]


def _build_matrices(
    rows: list[sqlite3.Row],
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    genotype_rows: list[list[float]] = []
    phenotype_rows: list[list[float]] = []
    present_rows: list[list[bool]] = []
    expected_length: int | None = None
    for row in rows:
        vector = _genotype_vector(row["genotype_json"])
        if expected_length is None:
            expected_length = len(vector)
        elif len(vector) != expected_length:
            return None
        genotype_rows.append(vector)
        phenotype_values, present = _phenotype_vector(row)
        phenotype_rows.append(phenotype_values)
        present_rows.append(present)
    genotype = np.asarray(genotype_rows, dtype=np.float64)
    phenotype = np.asarray(phenotype_rows, dtype=np.float64)
    present = np.asarray(present_rows, dtype=bool)
    return genotype, phenotype, present


def unique_genotype_indices(genotype: np.ndarray) -> np.ndarray:
    """Indices of distinct genotypes, dropping near-exact duplicates.

    Search archives re-evaluate and clone genotypes, so a config can hold hundreds
    of identical parameter vectors. Those near-zero genotype distances trivially
    deflate the inverse-locality ratio (a phenotype neighbor that is a genotype
    clone costs nothing), inflating apparent invertibility. Keeping one
    representative per duplicate cluster removes that artifact.
    """
    distances = _pairwise_distances(genotype)
    nonzero = distances[distances > 0]
    scale = float(np.median(nonzero)) if nonzero.size else 1.0
    threshold = 1e-6 * scale
    kept: list[int] = []
    claimed = np.zeros(genotype.shape[0], dtype=bool)
    for index in range(genotype.shape[0]):
        if claimed[index]:
            continue
        kept.append(index)
        claimed |= distances[index] <= threshold
    return np.asarray(kept, dtype=np.int64)


def run(
    compendium_path: Path,
    *,
    min_count: int,
    neighbor_k: int,
    fiber_k: int,
    null_repeats: int,
    seed: int,
    dedup: bool,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{compendium_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        configs = _eligible_configs(connection, min_count)
        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        rng = np.random.default_rng(seed)
        for config_hash, stable_count in configs:
            rows = _load_config_rows(connection, config_hash)
            matrices = _build_matrices(rows)
            if matrices is None:
                skipped.append(
                    {"config": config_hash, "reason": "inconsistent genotype length"}
                )
                continue
            genotype, phenotype, present = matrices
            if dedup:
                keep = unique_genotype_indices(genotype)
                genotype, phenotype, present = genotype[keep], phenotype[keep], present[keep]
            if genotype.shape[0] < min_count:
                skipped.append(
                    {
                        "config": config_hash,
                        "reason": f"only {genotype.shape[0]} distinct genotypes",
                    }
                )
                continue
            genotype_scaled = _robust_scale(genotype, present=None)
            phenotype_scaled = _robust_scale(phenotype, present=present)
            if genotype_scaled.shape[1] == 0 or phenotype_scaled.shape[1] == 0:
                skipped.append(
                    {"config": config_hash, "reason": "no varying columns"}
                )
                continue
            summary = _config_summary(
                genotype_scaled,
                phenotype_scaled,
                neighbor_k=neighbor_k,
                fiber_k=fiber_k,
                null_repeats=null_repeats,
                rng=rng,
            )
            summary["config"] = config_hash
            summary["stableCount"] = stable_count
            summary["distinctCount"] = int(genotype.shape[0])
            results.append(summary)
    finally:
        connection.close()

    return {
        "compendium": str(compendium_path),
        "minCount": min_count,
        "neighborK": neighbor_k,
        "fiberK": fiber_k,
        "nullRepeats": null_repeats,
        "seed": seed,
        "dedup": dedup,
        "configs": results,
        "skipped": skipped,
    }


def _cell(value: float | None, width: int, decimals: int) -> str:
    text = "na" if value is None else f"{value:.{decimals}f}"
    return f"{text:>{width}}"


def _format_table(report: dict[str, Any]) -> str:
    header = (
        f"{'config':<26}{'n':>5}{'spear':>7}{'fwd':>6}{'inv':>6}{'inj':>6}"
        f"{'nFib':>7}{'asym':>7}{'clonal':>8}{'fiber':>7}{'gPR':>7}"
    )
    lines = [header, "-" * len(header)]
    for entry in report["configs"]:
        lines.append(
            f"{entry['config']:<26}"
            f"{entry['count']:>5}"
            + _cell(entry["distanceSpearman"], 7, 2)
            + _cell(entry["forwardLocalityRatio"], 6, 2)
            + _cell(entry["inverseLocalityRatio"], 6, 2)
            + _cell(entry["injectiveBaselineRatio"], 6, 2)
            + _cell(entry["normalizedFiberScore"], 7, 2)
            + _cell(entry["forwardInverseAsymmetry"], 7, 2)
            + _cell(entry["clonalFraction"], 8, 2)
            + _cell(entry["localFiberDimension"], 7, 1)
            + _cell(entry["genotypeEffectiveDimension"], 7, 1)
        )
    for entry in report["skipped"]:
        lines.append(f"{entry['config']:<26} skipped: {entry['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compendium",
        default="artifacts/compendium.sqlite",
        help="Path to the compendium sqlite database",
    )
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/stage0_fiber_wellposedness.json",
        help="Path to write the JSON report",
    )
    parser.add_argument("--min-count", type=int, default=50)
    parser.add_argument("--neighbor-k", type=int, default=8)
    parser.add_argument("--fiber-k", type=int, default=15)
    parser.add_argument("--null-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260616)
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Keep near-duplicate genotypes instead of collapsing clones",
    )
    args = parser.parse_args(argv)

    compendium_path = Path(args.compendium).expanduser().resolve()
    if not compendium_path.is_file():
        raise SystemExit(f"Missing compendium: {compendium_path}")

    report = run(
        compendium_path,
        min_count=args.min_count,
        neighbor_k=args.neighbor_k,
        fiber_k=args.fiber_k,
        null_repeats=args.null_repeats,
        seed=args.seed,
        dedup=not args.no_dedup,
    )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(_format_table(report))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
