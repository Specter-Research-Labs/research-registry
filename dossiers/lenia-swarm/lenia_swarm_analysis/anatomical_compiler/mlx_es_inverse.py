"""Evolution-strategy inverse search on the MLX forward map.

Given a target phenotype (in the robust descriptor space the MLX map reproduces
faithfully: mass_mean, mass_std, occupancy_mean, gyration), search the genotype with a
batched cross-entropy method whose every candidate is a full Flow-Lenia rollout on the
GPU. Because the whole population advances in one compiled step, a generation of dozens
of 1200-step rollouts costs seconds, which is what makes ES (the smoothed-gradient route
the Lyapunov diagnostic settled on) practical here.

The objective is the standardized distance over the robust descriptors only. energy_mean
and variance_mean are deliberately excluded: the MLX rollout and the Swift engine select
different stable attractors for the second moments on sensitive genotypes, so conditioning
on them would optimize against an unreproducible target. Winners are re-simulated through
the Swift binary to report the true phenotype and confirm the hit transfers.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np

from lenia_swarm_analysis.anatomical_compiler._codec import (
    PHENOTYPE_FIELDS,
    GenotypeCodec,
    Standardizer,
    clamp_params,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator
from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import (
    DESCRIPTOR_FIELDS,
    rollout_descriptors,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    make_init,
)

ROBUST_FIELDS: tuple[str, ...] = ("mass_mean", "mass_std", "occupancy_mean", "gyration")
_ROBUST_INDEX = tuple(DESCRIPTOR_FIELDS.index(f) for f in ROBUST_FIELDS)
_PHENOTYPE_ROBUST_INDEX = tuple(PHENOTYPE_FIELDS.index(f) for f in ROBUST_FIELDS)


@dataclass
class ESConfig:
    steps: int = 1200
    warmup: int = 50
    record_interval: int = 25
    occupancy_threshold: float = 0.05
    iterations: int = 8
    population: int = 32
    elites: int = 8
    init_sigma_scale: float = 0.3
    sigma_floor_scale: float = 0.05
    init_seed: int = 0


def _vectors_to_genotype_batch(
    vectors: np.ndarray, codec: GenotypeCodec, ranges: dict[str, list[float]]
) -> GenotypeBatch:
    params = [clamp_params(codec.unflatten(v), ranges)[0] for v in vectors]
    return GenotypeBatch.from_param_dicts(params)


def _robust_descriptors(
    vectors: np.ndarray, codec: GenotypeCodec, ranges: dict[str, list[float]],
    config: LeniaConfig, es: ESConfig, center: tuple[int, int], size: int,
) -> np.ndarray:
    geno = _vectors_to_genotype_batch(vectors, codec, ranges)
    a0 = make_init(config, seed=es.init_seed, center=center, size=size, batch=geno.batch)
    mx.eval(a0)
    full = rollout_descriptors(
        a0, geno, config, steps=es.steps, warmup=es.warmup,
        record_interval=es.record_interval, occupancy_threshold=es.occupancy_threshold,
    )
    return full[:, _ROBUST_INDEX]


def search(
    target_robust: np.ndarray,
    start_mean: np.ndarray,
    genotype_scale: np.ndarray,
    standardizer: Standardizer,
    *,
    codec: GenotypeCodec,
    ranges: dict[str, list[float]],
    config: LeniaConfig,
    es: ESConfig,
    center: tuple[int, int],
    size: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    target_std = standardizer.forward(target_robust[None, :])[0]
    mean = start_mean.copy()
    sigma = es.init_sigma_scale * genotype_scale
    start_robust = _robust_descriptors(
        mean[None, :], codec, ranges, config, es, center, size
    )[0]
    best_cost = float(
        np.linalg.norm(standardizer.forward(start_robust[None, :])[0] - target_std)
    )
    best_vec = mean.copy()
    best_robust = start_robust.copy()
    history: list[float] = []
    trace: list[dict[str, Any]] = []

    def trace_point(iteration: int) -> dict[str, Any]:
        params, _ = clamp_params(codec.unflatten(best_vec), ranges)
        return {
            "iteration": iteration,
            "cost": best_cost,
            "genotype": params,
            "robust": {
                field: float(best_robust[j]) for j, field in enumerate(ROBUST_FIELDS)
            },
        }

    trace.append(trace_point(0))
    for iteration in range(1, es.iterations + 1):
        samples = mean[None, :] + sigma[None, :] * rng.standard_normal(
            (es.population, mean.shape[0])
        )
        robust = _robust_descriptors(samples, codec, ranges, config, es, center, size)
        costs = np.linalg.norm(standardizer.forward(robust) - target_std, axis=1)
        order = np.argsort(costs)
        elite = samples[order[: es.elites]]
        mean = elite.mean(axis=0)
        sigma = elite.std(axis=0) + es.sigma_floor_scale * genotype_scale
        if costs[order[0]] < best_cost:
            best_cost = float(costs[order[0]])
            best_vec = samples[order[0]].copy()
            best_robust = robust[order[0]].copy()
        history.append(best_cost)
        trace.append(trace_point(iteration))
    best_params, _ = clamp_params(codec.unflatten(best_vec), ranges)
    return {
        "bestCost": best_cost,
        "bestParams": best_params,
        "history": history,
        "trace": trace,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument(
        "--dataset", default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl"
    )
    parser.add_argument("--targets", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--elites", type=int, default=8)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output", default="outputs/anatomical-compiler/mlx_es_inverse.json"
    )
    args = parser.parse_args(argv)

    root = Path.cwd()
    base_config = json.loads((root / args.base).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base_config)
    search_config = json.loads((root / args.search).read_text(encoding="utf-8"))
    ranges = base_config["params"]["ranges"]
    patch = base_config["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])

    codec, genotype, phenotype_robust = load_dataset((root / args.dataset).resolve())
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(genotype.shape[0])
    target_index = order[: args.targets]
    pool_index = order[args.targets :]
    genotype_scale = genotype[pool_index].std(axis=0)

    es = ESConfig(
        steps=args.steps, occupancy_threshold=float(search_config["occupancy_threshold"]),
        iterations=args.iterations, population=args.population, elites=args.elites,
    )

    # The target is defined by re-simulating the held-out genotype through the Swift
    # binary at the canonical init, so it is a true forward-map phenotype in the same
    # robust space the search reports against.
    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, init_seed=0, timeout_seconds=600.0,
    )

    # Standardize the robust descriptors over the dataset's Swift phenotypes so the
    # objective weights each on the same scale; the columns are sliced from the aligned
    # phenotype matrix load_dataset returns, in ROBUST_FIELDS order.
    pool_robust = phenotype_robust[pool_index][:, _PHENOTYPE_ROBUST_INDEX]
    standardizer = Standardizer.fit(phenotype_robust[:, _PHENOTYPE_ROBUST_INDEX])
    pool_robust_std = standardizer.forward(pool_robust)

    results: list[dict[str, Any]] = []
    for index in target_index:
        target_phenotype = simulator.evaluate(codec.unflatten(genotype[index]), init_seed=0)
        target_robust = np.asarray(
            [float(target_phenotype[f]) for f in ROBUST_FIELDS], dtype=np.float64
        )
        # Warm start from the pool genotype whose phenotype is nearest the target in
        # robust space: the compiler returns a fiber sample, the search refines it.
        nearest = int(
            np.argmin(
                np.linalg.norm(
                    pool_robust_std - standardizer.forward(target_robust[None, :])[0],
                    axis=1,
                )
            )
        )
        start_mean = genotype[pool_index[nearest]]
        outcome = search(
            target_robust, start_mean, genotype_scale, standardizer,
            codec=codec, ranges=ranges, config=config, es=es,
            center=center, size=size, rng=rng,
        )
        found_phenotype = simulator.evaluate(outcome["bestParams"], init_seed=0)
        found_robust = np.asarray(
            [float(found_phenotype[f]) for f in ROBUST_FIELDS], dtype=np.float64
        )
        swift_cost = float(
            np.linalg.norm(
                standardizer.forward(found_robust[None, :])[0]
                - standardizer.forward(target_robust[None, :])[0]
            )
        )
        results.append({
            "targetIndex": int(index),
            "target": {f: float(target_robust[j]) for j, f in enumerate(ROBUST_FIELDS)},
            "found": {f: float(found_robust[j]) for j, f in enumerate(ROBUST_FIELDS)},
            "mlxCost": outcome["bestCost"],
            "swiftCost": swift_cost,
            "history": outcome["history"],
        })
        print(f"target {int(index)}: MLX cost {outcome['bestCost']:.3f} -> "
              f"Swift re-sim cost {swift_cost:.3f}")
        for f in ROBUST_FIELDS:
            tv = target_phenotype[f]
            fv = found_phenotype[f]
            print(f"    {f:16s} target {tv:10.3f}  found {fv:10.3f}  "
                  f"rel {abs(fv - tv) / (abs(tv) + 1e-9) * 100:5.1f}%")

    report = {
        "robustFields": list(ROBUST_FIELDS),
        "population": es.population,
        "iterations": es.iterations,
        "elites": es.elites,
        "steps": es.steps,
        "perTarget": results,
        "meanSwiftCost": float(np.mean([r["swiftCost"] for r in results])) if results else None,
    }
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nmean Swift re-sim cost {report['meanSwiftCost']:.3f} (0 is a perfect hit)")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
