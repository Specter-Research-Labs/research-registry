"""Capture developmental trajectories for a batch of genotypes, the input to the
dynamic Waddington landscape.

Each row is one genotype's path through the 12-axis morphospace over the run, plus
its terminal phenotype. Unlike the endpoint-only warehouse, this records the whole
flow toward the attractor, which is what makes the forward landscape (basins) and
the inverse compiler (fibers) two views of one map.

A second mode (`--canalization`) re-runs each of a few genotypes from several
initial conditions, to measure whether the trajectories funnel to the same shape
regardless of where they started (canalization).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lenia_swarm_analysis.anatomical_compiler.forward_sim import ForwardSimulator


def _load_genotypes(dataset_path: Path, count: int) -> list[dict]:
    genotypes: list[dict] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if not record["phenotype"].get("is_stable"):
                continue
            genotypes.append(record["params"])
            if len(genotypes) >= count:
                break
    return genotypes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl",
    )
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--stride", type=int, default=100)
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument(
        "--output",
        default="outputs/anatomical-compiler/trajectories_3k_1c_128.jsonl",
    )
    parser.add_argument(
        "--canalization",
        type=int,
        default=0,
        help="If >0, run this many initial conditions per genotype for a small set",
    )
    parser.add_argument("--canalization-genotypes", type=int, default=8)
    args = parser.parse_args(argv)

    root = Path.cwd()
    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, timeout_seconds=600.0,
    )
    genotypes = _load_genotypes((root / args.dataset).resolve(), args.count)
    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.canalization > 0:
        written = 0
        with output_path.open("w", encoding="utf-8") as handle:
            for genotype_index, genotype in enumerate(genotypes[: args.canalization_genotypes]):
                for init_seed in range(args.canalization):
                    trajectory = simulator.developmental_trajectory(
                        genotype, init_seed=init_seed, stride=args.stride
                    )
                    handle.write(json.dumps({
                        "genotypeIndex": genotype_index,
                        "initSeed": init_seed,
                        "path": trajectory["path"],
                        "terminal": trajectory["terminal"],
                    }) + "\n")
                    written += 1
        print(f"Wrote {written} canalization trajectories "
              f"({args.canalization_genotypes}g x {args.canalization}ic) to {output_path}")
        return 0

    written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for genotype in genotypes:
            trajectory = simulator.developmental_trajectory(
                genotype, init_seed=0, stride=args.stride
            )
            handle.write(json.dumps({
                "params": genotype,
                "path": trajectory["path"],
                "terminal": trajectory["terminal"],
            }) + "\n")
            written += 1
    print(f"Wrote {written} trajectories to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
