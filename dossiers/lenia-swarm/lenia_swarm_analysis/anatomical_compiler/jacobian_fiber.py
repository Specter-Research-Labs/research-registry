"""Stage 1 closeout: the fiber dimension by the most direct method, the Jacobian
null space of the forward map.

For the map genotype -> shape descriptor, the Jacobian's null space is exactly the
local fiber: the genotype directions that leave the shape unchanged. Its rank is how
many descriptor dimensions the genotype can actually control locally. We compute the
Jacobian by central finite differences through the real simulator (deterministic at
a fixed initial condition), then read its effective rank from the singular values.

This is the third, independent estimate of the fiber, after TwoNN and MLE. The
cross-check that ties everything together: the Jacobian rank should land near the
phenotype intrinsic dimension (about 6 from TwoNN), because that is how many
independent shape directions the genotype can steer. If it does, the fat fiber is
confirmed by a direct per-point measurement, not just neighbor statistics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler._codec import (
    PHENOTYPE_FIELDS,
    GenotypeCodec,
    Standardizer,
    clamp_params,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator


def _shape_std(
    genotype_vec: np.ndarray,
    codec: GenotypeCodec,
    ranges: dict[str, list[float]],
    simulator: ForwardSimulator,
    cond_std: Standardizer,
) -> np.ndarray | None:
    params, _ = clamp_params(codec.unflatten(genotype_vec), ranges)
    phenotype = simulator.evaluate(params, init_seed=0)
    if not phenotype.get("is_stable"):
        return None
    values = []
    for field in PHENOTYPE_FIELDS:
        raw = phenotype.get(field)
        if raw is None:
            return None
        values.append(float(raw))
    return cond_std.forward(np.asarray(values, dtype=np.float64)[None, :])[0]


def _jacobian(
    genotype_vec: np.ndarray,
    genotype_scale: np.ndarray,
    codec: GenotypeCodec,
    ranges: dict[str, list[float]],
    simulator: ForwardSimulator,
    cond_std: Standardizer,
    *,
    epsilon: float,
) -> np.ndarray | None:
    dim = genotype_vec.shape[0]
    columns: list[np.ndarray] = []
    for index in range(dim):
        step = np.zeros(dim)
        step[index] = epsilon * genotype_scale[index]
        plus = _shape_std(genotype_vec + step, codec, ranges, simulator, cond_std)
        minus = _shape_std(genotype_vec - step, codec, ranges, simulator, cond_std)
        if plus is None or minus is None:
            return None
        columns.append((plus - minus) / (2.0 * epsilon))
    return np.stack(columns, axis=1)


def _effective_rank(singular: np.ndarray) -> dict[str, Any]:
    eigen = singular**2
    positive = eigen[eigen > 1e-18]
    participation = (
        float(np.sum(positive) ** 2 / np.sum(positive**2)) if positive.size else 0.0
    )
    threshold = singular.max() * 0.05 if singular.size else 0.0
    count = int(np.sum(singular > threshold))
    return {"participationRank": participation, "thresholdRank": count}


def run(
    dataset_path: Path,
    base_config_path: Path,
    search_config_path: Path,
    *,
    genotypes: int,
    epsilon: float,
    steps: int,
    seed: int,
) -> dict[str, Any]:
    codec, genotype, phenotype = load_dataset(dataset_path)
    rng = np.random.default_rng(seed)
    index = rng.permutation(genotype.shape[0])[:genotypes]
    cond_std = Standardizer.fit(phenotype)
    genotype_scale = genotype.std(axis=0)
    root = Path.cwd()
    ranges = json.loads(base_config_path.read_text(encoding="utf-8"))["params"]["ranges"]
    simulator = ForwardSimulator(
        base_config_path, search_config_path, dossier_root=root,
        steps=steps, init_seed=0, timeout_seconds=600.0,
    )

    per_genotype: list[dict[str, Any]] = []
    for i in index:
        jacobian = _jacobian(
            genotype[i], genotype_scale, codec, ranges, simulator, cond_std,
            epsilon=epsilon,
        )
        if jacobian is None:
            continue
        singular = np.linalg.svd(jacobian, compute_uv=False)
        ranks = _effective_rank(singular)
        per_genotype.append({
            "participationRank": ranks["participationRank"],
            "thresholdRank": ranks["thresholdRank"],
            "fiberDimFull": codec.dim - ranks["participationRank"],
            "singular": [float(s) for s in singular],
        })

    participation = [g["participationRank"] for g in per_genotype]
    return {
        "dataset": str(dataset_path),
        "genotypeDim": codec.dim,
        "descriptorDim": len(PHENOTYPE_FIELDS),
        "epsilon": epsilon,
        "evaluated": len(per_genotype),
        "meanParticipationRank": float(np.mean(participation)) if participation else None,
        "meanThresholdRank": (
            float(np.mean([g["thresholdRank"] for g in per_genotype])) if per_genotype else None
        ),
        "meanFiberDimFull": (
            float(np.mean([g["fiberDimFull"] for g in per_genotype])) if per_genotype else None
        ),
        "perGenotype": per_genotype,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--genotypes", type=int, default=12)
    parser.add_argument("--epsilon", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/stage1_jacobian_fiber.json"
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    report = run(
        (root / args.dataset).resolve(),
        (root / args.base).resolve(),
        (root / args.search).resolve(),
        genotypes=args.genotypes, epsilon=args.epsilon, steps=args.steps, seed=args.seed,
    )
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"genotype dim {report['genotypeDim']}, descriptor dim {report['descriptorDim']}")
    print(f"evaluated {report['evaluated']} genotypes (epsilon={report['epsilon']})")
    print(f"mean Jacobian rank (participation) = {report['meanParticipationRank']:.2f}  "
          f"(threshold count {report['meanThresholdRank']:.1f})")
    print(f"  -> the genotype controls ~this many of {report['descriptorDim']} shape directions")
    print(f"mean fiber dim (full {report['genotypeDim']}-space) = {report['meanFiberDimFull']:.1f}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
