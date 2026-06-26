"""Stage 1, fiber-dimension triangulation: cross-check the participation-ratio
fiber dimension with a bias-corrected intrinsic-dimension estimator.

The review flagged that the local fiber dimension in Stage 0 is a participation
ratio capped by the neighborhood size and biased downward at small sample. This
module estimates the same quantity a different, neighborhood-free way. For a
forward map genotype -> phenotype, the generic fiber dimension is the dimension of
the genotype manifold minus the dimension of the phenotype manifold it lands on
(rank-nullity for the map's local linearization). So we estimate the intrinsic
dimension of the genotype cloud and of the phenotype cloud separately with TwoNN
(Facco, d'Errico, Rodriguez, Laio 2017), which uses only the ratio of each point's
first two neighbor distances and is reliable below dimension ~20, and report their
difference as the fiber dimension. A fat fiber shows up as ID_genotype well above
ID_phenotype.

Runs on deduplicated distinct genotypes, the same population as the revised Stage 0.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler.fiber_wellposedness import (
    _build_matrices,
    _eligible_configs,
    _load_config_rows,
    _pairwise_distances,
    _participation_ratio,
    _robust_scale,
    unique_genotype_indices,
)


def _twonn(matrix: np.ndarray, *, discard: float = 0.1) -> float | None:
    """TwoNN intrinsic-dimension estimate of a point cloud.

    Each point contributes mu = r2 / r1, the ratio of its two nearest neighbor
    distances; under a locally uniform density log(mu) is exponential with rate
    equal to the intrinsic dimension, so a line through the origin fit of
    -log(1 - F(mu)) against log(mu) recovers it. The largest-mu tail is discarded
    because it is where the uniform-density assumption breaks.
    """
    count = matrix.shape[0]
    if count < 10:
        return None
    distances = _pairwise_distances(matrix)
    mus: list[float] = []
    for index in range(count):
        ordered = np.sort(distances[index])
        positive = ordered[ordered > 0]
        if positive.shape[0] < 2 or positive[0] <= 0:
            continue
        mus.append(float(positive[1] / positive[0]))
    if len(mus) < 10:
        return None
    mu_sorted = np.sort(np.asarray(mus, dtype=np.float64))
    n = mu_sorted.shape[0]
    empirical = np.arange(1, n + 1, dtype=np.float64) / n
    keep = int(round(n * (1.0 - discard)))
    x = np.log(mu_sorted[:keep])
    y = -np.log1p(-empirical[:keep])
    denom = float(np.sum(x * x))
    if denom <= 1e-12:
        return None
    return float(np.sum(x * y) / denom)


def _mle_id(matrix: np.ndarray, *, k1: int = 10, k2: int = 20) -> float | None:
    """Levina-Bickel maximum-likelihood intrinsic dimension with the
    MacKay-Ghahramani averaging (average the per-point inverse estimates, then
    invert), a second estimator independent of TwoNN's two-neighbor ratio.
    """
    count = matrix.shape[0]
    if count <= k2 + 1:
        return None
    distances = _pairwise_distances(matrix)
    mean_log_ratios: list[float] = []
    for index in range(count):
        ordered = np.sort(distances[index])
        positive = ordered[ordered > 0]
        if positive.shape[0] <= k2:
            continue
        for k in range(k1, k2 + 1):
            radii = positive[:k]
            if np.any(radii <= 0):
                continue
            total = float(np.sum(np.log(radii[-1] / radii[:-1])))
            if total <= 1e-12:
                continue
            mean_log_ratios.append(total / (k - 1))
    if not mean_log_ratios:
        return None
    return float(1.0 / np.mean(mean_log_ratios))


def run(
    compendium_path: Path,
    *,
    min_count: int,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{compendium_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    try:
        for config_hash, _ in _eligible_configs(connection, min_count):
            rows = _load_config_rows(connection, config_hash)
            matrices = _build_matrices(rows)
            if matrices is None:
                skipped.append(
                    {"config": config_hash, "reason": "inconsistent genotype length"}
                )
                continue
            genotype, phenotype, present = matrices
            keep = unique_genotype_indices(genotype)
            if keep.shape[0] < min_count:
                skipped.append(
                    {
                        "config": config_hash,
                        "reason": f"only {keep.shape[0]} distinct genotypes",
                    }
                )
                continue
            genotype_scaled = _robust_scale(genotype[keep], present=None)
            phenotype_scaled = _robust_scale(phenotype[keep], present=present[keep])
            if genotype_scaled.shape[1] == 0 or phenotype_scaled.shape[1] == 0:
                skipped.append({"config": config_hash, "reason": "no varying columns"})
                continue
            genotype_id = _twonn(genotype_scaled)
            phenotype_id = _twonn(phenotype_scaled)
            genotype_mle = _mle_id(genotype_scaled)
            phenotype_mle = _mle_id(phenotype_scaled)
            global_eigenvalues = (
                np.linalg.svd(
                    genotype_scaled - genotype_scaled.mean(axis=0, keepdims=True),
                    compute_uv=False,
                )
                ** 2
            )
            results.append(
                {
                    "config": config_hash,
                    "distinctCount": int(keep.shape[0]),
                    "genotypeColumns": int(genotype_scaled.shape[1]),
                    "phenotypeColumns": int(phenotype_scaled.shape[1]),
                    "genotypeIntrinsicDimension": genotype_id,
                    "phenotypeIntrinsicDimension": phenotype_id,
                    "fiberDimension": (
                        genotype_id - phenotype_id
                        if genotype_id is not None and phenotype_id is not None
                        else None
                    ),
                    "genotypeIntrinsicDimensionMle": genotype_mle,
                    "phenotypeIntrinsicDimensionMle": phenotype_mle,
                    "fiberDimensionMle": (
                        genotype_mle - phenotype_mle
                        if genotype_mle is not None and phenotype_mle is not None
                        else None
                    ),
                    "genotypeParticipationRatio": _participation_ratio(global_eigenvalues),
                }
            )
    finally:
        connection.close()

    return {
        "compendium": str(compendium_path),
        "minCount": min_count,
        "estimator": "twonn",
        "configs": results,
        "skipped": skipped,
    }


def _format_table(report: dict[str, Any]) -> str:
    header = (
        f"{'config':<26}{'n':>5}"
        f"{'ID_G':>7}{'ID_P':>7}{'fiber':>7}"
        f"{'ID_G_ml':>9}{'ID_P_ml':>9}{'fib_ml':>8}{'gPR':>7}"
    )
    lines = [header, "-" * len(header)]
    for entry in report["configs"]:

        def cell(value: float | None, width: int) -> str:
            text = "na" if value is None else f"{value:.1f}"
            return f"{text:>{width}}"

        lines.append(
            f"{entry['config']:<26}{entry['distinctCount']:>5}"
            + cell(entry["genotypeIntrinsicDimension"], 7)
            + cell(entry["phenotypeIntrinsicDimension"], 7)
            + cell(entry["fiberDimension"], 7)
            + cell(entry["genotypeIntrinsicDimensionMle"], 9)
            + cell(entry["phenotypeIntrinsicDimensionMle"], 9)
            + cell(entry["fiberDimensionMle"], 8)
            + cell(entry["genotypeParticipationRatio"], 7)
        )
    for entry in report["skipped"]:
        lines.append(f"{entry['config']:<26} skipped: {entry['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compendium", default="artifacts/compendium.sqlite")
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/stage1_fiber_dimension.json",
    )
    parser.add_argument("--min-count", type=int, default=50)
    args = parser.parse_args(argv)

    compendium_path = Path(args.compendium).expanduser().resolve()
    if not compendium_path.is_file():
        raise SystemExit(f"Missing compendium: {compendium_path}")

    report = run(compendium_path, min_count=args.min_count)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(_format_table(report))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
