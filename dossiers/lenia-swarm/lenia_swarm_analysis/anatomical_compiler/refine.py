"""Stage 3, first cut: refine a genotype to hit a target shape precisely.

The compiler returns a fiber, a spread of genotypes whose shapes scatter around the
requested one, because the fiber is fat. To turn one fiber sample into a precise hit
we search locally: a cross-entropy-method loop over the genotype, every candidate
evaluated by actually re-simulating it, driving the init-robust shape descriptor to
the target. This is the evolution-in-the-loop refiner; the differentiable-Lenia
gradient version is the later, sharper tool, but this one needs only the harness we
already have and the real forward map, so there is no fidelity gap.

Each target's refined error is reported against two references from Stage 2: the
cINN's typical error (about 2.98 standardized units) and the empirical floor (about
1.90), the best the nearest training genotypes achieve.
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

UNSTABLE_COST = 12.0


def _shape_vector(phenotype: dict[str, Any]) -> np.ndarray | None:
    values = []
    for field in PHENOTYPE_FIELDS:
        raw = phenotype.get(field)
        if raw is None:
            return None
        values.append(float(raw))
    return np.asarray(values, dtype=np.float64)


def _cost(
    genotype_vec: np.ndarray,
    codec: GenotypeCodec,
    ranges: dict[str, list[float]],
    simulator: ForwardSimulator,
    cond_std: Standardizer,
    target_std: np.ndarray,
) -> float:
    params, _ = clamp_params(codec.unflatten(genotype_vec), ranges)
    phenotype = simulator.evaluate(params)
    if not phenotype.get("is_stable"):
        return UNSTABLE_COST
    vector = _shape_vector(phenotype)
    if vector is None:
        return UNSTABLE_COST
    return float(np.linalg.norm(cond_std.forward(vector[None, :])[0] - target_std))


def refine_one(
    target_std: np.ndarray,
    start_mean: np.ndarray,
    genotype_scale: np.ndarray,
    *,
    codec: GenotypeCodec,
    ranges: dict[str, list[float]],
    simulator: ForwardSimulator,
    cond_std: Standardizer,
    rng: np.random.Generator,
    iterations: int,
    population: int,
    elites: int,
) -> dict[str, Any]:
    mean = start_mean.copy()
    sigma = 0.4 * genotype_scale
    best_cost = float("inf")
    best_vec = mean.copy()
    start_cost: float | None = None
    for _ in range(iterations):
        samples = mean[None, :] + sigma[None, :] * rng.standard_normal(
            (population, mean.shape[0])
        )
        costs = np.array([
            _cost(sample, codec, ranges, simulator, cond_std, target_std)
            for sample in samples
        ])
        if start_cost is None:
            start_cost = float(np.min(costs))
        order = np.argsort(costs)
        elite_samples = samples[order[:elites]]
        mean = elite_samples.mean(axis=0)
        sigma = elite_samples.std(axis=0) + 0.05 * genotype_scale
        if costs[order[0]] < best_cost:
            best_cost = float(costs[order[0]])
            best_vec = samples[order[0]].copy()
    refined_params, _ = clamp_params(codec.unflatten(best_vec), ranges)
    return {
        "startCost": start_cost,
        "refinedCost": best_cost,
        "refinedGenotype": refined_params,
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
    parser.add_argument("--output", default="outputs/anatomical-compiler/stage3_refine.json")
    parser.add_argument("--targets", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--elites", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    root = Path.cwd()
    codec, genotype, phenotype = load_dataset((root / args.dataset).resolve())
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(genotype.shape[0])
    target_index = order[: args.targets]
    pool_index = order[args.targets :]

    cond_std = Standardizer.fit(phenotype[pool_index])
    genotype_scale = genotype[pool_index].std(axis=0)
    ranges = json.loads((root / args.base).read_text(encoding="utf-8"))["params"]["ranges"]
    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, init_seed=0, timeout_seconds=600.0,
    )

    results: list[dict[str, Any]] = []
    for index in target_index:
        # Define the target at the canonical init (seed 0), so the forward map is a
        # deterministic genotype->shape and a precise hit is actually achievable;
        # using the dataset phenotype (generated at a varying init) would leave an
        # irreducible init-mismatch floor.
        target_phenotype = simulator.evaluate(codec.unflatten(genotype[index]), init_seed=0)
        target_vector = _shape_vector(target_phenotype)
        if target_vector is None:
            continue
        target_std = cond_std.forward(target_vector[None, :])[0]
        start_mean = genotype[pool_index[rng.integers(pool_index.shape[0])]]
        outcome = refine_one(
            target_std, start_mean, genotype_scale,
            codec=codec, ranges=ranges, simulator=simulator, cond_std=cond_std, rng=rng,
            iterations=args.iterations, population=args.population, elites=args.elites,
        )
        results.append(
            {"startCost": outcome["startCost"], "refinedCost": outcome["refinedCost"]}
        )
        print(
            f"target {int(index)}: start {outcome['startCost']:.2f} "
            f"-> refined {outcome['refinedCost']:.2f}"
        )

    starts = [r["startCost"] for r in results if r["startCost"] is not None]
    refined = [r["refinedCost"] for r in results]
    best = min(refined) if refined else None
    report = {
        "targets": len(results),
        "targetInitSeed": 0,
        "meanStartCost": float(np.mean(starts)) if starts else None,
        "meanRefinedCost": float(np.mean(refined)) if refined else None,
        "bestRefinedCost": best,
        "perTarget": results,
    }
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nmean start {report['meanStartCost']:.2f} -> refined "
          f"{report['meanRefinedCost']:.2f} (best {best:.2f}); a precise hit is ~0")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
