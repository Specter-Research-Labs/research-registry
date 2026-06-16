"""Re-run the Stage 0 well-posedness and Stage 1 fiber-dimension measurements on a
fresh harness-generated dataset, to check the fat-fiber and curved-near-injective
findings hold on clean data rather than the clone-contaminated historical
compendium.

Input is the JSONL written by `forward_sim.generate_dataset` (rows of {params,
phenotype}) for one fully-specified regime. The genotype is flattened from the
explicit params; the phenotype is the same metric bundle used in Stage 0. Only
stable creatures are kept, genotypes are deduplicated as a safety check (fresh
random sampling should produce none), and the identical calibrated metrics and
intrinsic-dimension estimators run on the result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler.fiber_dimension import _mle_id, _twonn
from lenia_swarm_analysis.anatomical_compiler.fiber_wellposedness import (
    _config_summary,
    _genotype_vector,
    _participation_ratio,
    _robust_scale,
    unique_genotype_indices,
)

PHENOTYPE_FIELDS: tuple[str, ...] = (
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
    "path_tortuosity",
    "movement_efficiency",
)


def _load(dataset_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    genotype_rows: list[list[float]] = []
    phenotype_rows: list[list[float]] = []
    present_rows: list[list[bool]] = []
    total = 0
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            total += 1
            record = json.loads(line)
            phenotype = record["phenotype"]
            if not phenotype.get("is_stable"):
                continue
            genotype_rows.append(_genotype_vector(json.dumps(record["params"])))
            values: list[float] = []
            present: list[bool] = []
            for field in PHENOTYPE_FIELDS:
                raw = phenotype.get(field)
                if raw is None:
                    values.append(0.0)
                    present.append(False)
                else:
                    values.append(float(raw))
                    present.append(True)
            phenotype_rows.append(values)
            present_rows.append(present)
    return (
        np.asarray(genotype_rows, dtype=np.float64),
        np.asarray(phenotype_rows, dtype=np.float64),
        np.asarray(present_rows, dtype=bool),
        total,
    )


def run(
    dataset_path: Path,
    *,
    neighbor_k: int,
    fiber_k: int,
    null_repeats: int,
    seed: int,
) -> dict[str, Any]:
    genotype, phenotype, present, total = _load(dataset_path)
    stable = genotype.shape[0]
    keep = unique_genotype_indices(genotype)
    genotype, phenotype, present = genotype[keep], phenotype[keep], present[keep]

    genotype_scaled = _robust_scale(genotype, present=None)
    phenotype_scaled = _robust_scale(phenotype, present=present)

    rng = np.random.default_rng(seed)
    summary = _config_summary(
        genotype_scaled,
        phenotype_scaled,
        neighbor_k=neighbor_k,
        fiber_k=fiber_k,
        null_repeats=null_repeats,
        rng=rng,
    )

    genotype_id = _twonn(genotype_scaled)
    phenotype_id = _twonn(phenotype_scaled)
    genotype_mle = _mle_id(genotype_scaled)
    phenotype_mle = _mle_id(phenotype_scaled)
    centered_genotype = genotype_scaled - genotype_scaled.mean(axis=0, keepdims=True)
    global_eigenvalues = np.linalg.svd(centered_genotype, compute_uv=False) ** 2

    return {
        "dataset": str(dataset_path),
        "total": total,
        "stable": stable,
        "distinct": int(keep.shape[0]),
        "wellposedness": summary,
        "dimension": {
            "genotypeTwoNN": genotype_id,
            "phenotypeTwoNN": phenotype_id,
            "fiberTwoNN": (
                genotype_id - phenotype_id
                if genotype_id is not None and phenotype_id is not None
                else None
            ),
            "genotypeMle": genotype_mle,
            "phenotypeMle": phenotype_mle,
            "fiberMle": (
                genotype_mle - phenotype_mle
                if genotype_mle is not None and phenotype_mle is not None
                else None
            ),
            "genotypeParticipationRatio": _participation_ratio(global_eigenvalues),
        },
    }


def _format(report: dict[str, Any]) -> str:
    s = report["wellposedness"]
    d = report["dimension"]

    def f(value: float | None, decimals: int = 2) -> str:
        return "na" if value is None else f"{value:.{decimals}f}"

    return "\n".join(
        [
            f"dataset: {report['dataset']}",
            f"total={report['total']} stable={report['stable']} distinct={report['distinct']}",
            "",
            "well-posedness (calibrated):",
            f"  spearman={f(s['distanceSpearman'])} forward={f(s['forwardLocalityRatio'])} "
            f"inverse={f(s['inverseLocalityRatio'])} injective={f(s['injectiveBaselineRatio'])}",
            f"  normalizedFiberScore={f(s['normalizedFiberScore'])} "
            f"asymmetry={f(s['forwardInverseAsymmetry'])} z={f(s['inverseZ'], 1)} "
            f"clonal={f(s['clonalFraction'])}",
            "",
            "fiber dimension:",
            f"  TwoNN: ID_G={f(d['genotypeTwoNN'],1)} ID_P={f(d['phenotypeTwoNN'],1)} "
            f"fiber={f(d['fiberTwoNN'],1)}",
            f"  MLE:   ID_G={f(d['genotypeMle'],1)} ID_P={f(d['phenotypeMle'],1)} "
            f"fiber={f(d['fiberMle'],1)}",
            f"  participation ratio (genotype) = {f(d['genotypeParticipationRatio'],1)}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/stage1_fresh_fiber.json",
    )
    parser.add_argument("--neighbor-k", type=int, default=8)
    parser.add_argument("--fiber-k", type=int, default=15)
    parser.add_argument("--null-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260616)
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset).expanduser().resolve()
    if not dataset_path.is_file():
        raise SystemExit(f"Missing dataset: {dataset_path}")

    report = run(
        dataset_path,
        neighbor_k=args.neighbor_k,
        fiber_k=args.fiber_k,
        null_repeats=args.null_repeats,
        seed=args.seed,
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(_format(report))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
