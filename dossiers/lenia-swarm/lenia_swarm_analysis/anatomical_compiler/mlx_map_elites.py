"""MAP-Elites over the morphospace on the MLX forward map.

The search dataset and the cINN cover only the forms that random rules commonly grow;
the compact, structured creatures sit in a thin tail they rarely reach. MAP-Elites
illuminates the (occupancy, gyration) plane directly: it keeps an archive with one rule
per cell, repeatedly mutates the rules it has and drops each child into the cell its form
lands in, keeping the more concentrated rule when a cell is contested. Run on the batched
MLX map, a generation of dozens of full rollouts costs seconds, so the archive fills the
plane far past where the dataset stops, and the compiler can warm-start from the nearest
elite for a target the common fiber never covers.

Behavior descriptors are occupancy_mean and gyration; the per-cell quality kept is
energy_mean, a proxy for how concentrated and structured the creature is.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler._codec import (
    GenotypeCodec,
    clamp_params,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import (
    DESCRIPTOR_FIELDS,
    rollout_descriptors,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    make_init,
)

_OCC = DESCRIPTOR_FIELDS.index("occupancy_mean")
_GYR = DESCRIPTOR_FIELDS.index("gyration")
_ENERGY = DESCRIPTOR_FIELDS.index("energy_mean")


@dataclass
class MapElitesConfig:
    occ_bins: int = 24
    occ_lo: float = 0.0
    occ_hi: float = 0.4
    gyr_bins: int = 24
    gyr_lo: float = 0.0
    gyr_hi: float = 4000.0
    generations: int = 24
    batch: int = 48
    init_samples: int = 96
    mutation_sigma_scale: float = 0.15
    steps: int = 1200
    warmup: int = 50
    record_interval: int = 25
    occupancy_threshold: float = 0.05
    init_seed: int = 0


@dataclass
class Elite:
    vector: np.ndarray
    fitness: float
    occupancy: float
    gyration: float


@dataclass
class Archive:
    config: MapElitesConfig
    cells: dict[tuple[int, int], Elite] = field(default_factory=dict)

    def cell_of(self, occupancy: float, gyration: float) -> tuple[int, int] | None:
        c = self.config
        if not (c.occ_lo <= occupancy < c.occ_hi and c.gyr_lo <= gyration < c.gyr_hi):
            return None
        i = int((occupancy - c.occ_lo) / (c.occ_hi - c.occ_lo) * c.occ_bins)
        j = int((gyration - c.gyr_lo) / (c.gyr_hi - c.gyr_lo) * c.gyr_bins)
        return min(i, c.occ_bins - 1), min(j, c.gyr_bins - 1)

    def add(self, vector: np.ndarray, fitness: float, occupancy: float, gyration: float) -> bool:
        cell = self.cell_of(occupancy, gyration)
        if cell is None:
            return False
        current = self.cells.get(cell)
        if current is None or fitness > current.fitness:
            self.cells[cell] = Elite(vector.copy(), fitness, occupancy, gyration)
            return True
        return False


def _random_genotypes(
    count: int, codec: GenotypeCodec, ranges: dict[str, list[float]],
    rng: np.random.Generator,
) -> np.ndarray:
    la, lb, lw = codec.bump_lengths

    def u(key: str, n: int) -> list[float]:
        lo, hi = ranges[key]
        return list(rng.uniform(lo, hi, size=n))

    rows: list[list[float]] = []
    for _ in range(count):
        params: dict[str, Any] = {"R": float(rng.uniform(ranges["R"][0], ranges["R"][1]))}
        for key in ("m", "s", "h", "r"):
            params[key] = u(key, codec.kernel_count)
        params["a"] = [u("a", la) for _ in range(codec.kernel_count)]
        params["b"] = [u("b", lb) for _ in range(codec.kernel_count)]
        params["w"] = [u("w", lw) for _ in range(codec.kernel_count)]
        rows.append(codec.flatten(params))
    return np.asarray(rows, dtype=np.float64)


def _evaluate(
    vectors: np.ndarray, codec: GenotypeCodec, ranges: dict[str, list[float]],
    config: LeniaConfig, me: MapElitesConfig, center: tuple[int, int], size: int,
) -> np.ndarray:
    params = [clamp_params(codec.unflatten(v), ranges)[0] for v in vectors]
    geno = GenotypeBatch.from_param_dicts(params)
    a0 = make_init(config, seed=me.init_seed, center=center, size=size, batch=geno.batch)
    return rollout_descriptors(
        a0, geno, config, steps=me.steps, warmup=me.warmup,
        record_interval=me.record_interval, occupancy_threshold=me.occupancy_threshold,
    )


def run(
    codec: GenotypeCodec, genotype_scale: np.ndarray, ranges: dict[str, list[float]],
    config: LeniaConfig, me: MapElitesConfig, center: tuple[int, int], size: int,
    *, seed: int, log: bool = True, seed_vectors: np.ndarray | None = None,
) -> Archive:
    rng = np.random.default_rng(seed)
    archive = Archive(me)

    def place_batch(vectors: np.ndarray) -> int:
        desc = _evaluate(vectors, codec, ranges, config, me, center, size)
        added = 0
        for k in range(vectors.shape[0]):
            occ, gyr, energy = desc[k, _OCC], desc[k, _GYR], desc[k, _ENERGY]
            if np.isfinite(energy) and archive.add(
                vectors[k], float(energy), float(occ), float(gyr)
            ):
                added += 1
        return added

    if seed_vectors is not None and len(seed_vectors):
        place_batch(seed_vectors)
        if log:
            print(f"resumed: {len(archive.cells)} cells from prior archive")
    place_batch(_random_genotypes(me.init_samples, codec, ranges, rng))
    if log:
        print(f"init: {len(archive.cells)} cells filled")

    for generation in range(me.generations):
        keys = list(archive.cells)
        parents = [archive.cells[keys[i]].vector
                   for i in rng.integers(0, len(keys), size=me.batch)]
        children = np.asarray(parents) + (
            me.mutation_sigma_scale * genotype_scale
            * rng.standard_normal((me.batch, genotype_scale.shape[0]))
        )
        added = place_batch(children)
        if log:
            total = me.occ_bins * me.gyr_bins
            print(f"gen {generation + 1:3d}/{me.generations}: +{added:2d} new, "
                  f"{len(archive.cells)}/{total} cells "
                  f"({100 * len(archive.cells) / total:.0f}%)")
    return archive


def _coverage_image(archive: Archive, *, upscale: int = 18) -> Image.Image:
    c = archive.config
    grid = np.zeros((c.gyr_bins, c.occ_bins, 3), dtype=np.uint8)
    grid[:, :] = (16, 19, 26)
    fits = [e.fitness for e in archive.cells.values()]
    lo, hi = (min(fits), max(fits)) if fits else (0.0, 1.0)
    span = hi - lo if hi > lo else 1.0
    for (i, j), elite in archive.cells.items():
        t = (elite.fitness - lo) / span
        grid[c.gyr_bins - 1 - j, i] = (
            int(40 + 215 * t), int(30 + 72 * t), int(20 + 10 * (1 - t))
        )
    image = Image.fromarray(grid, mode="RGB")
    return image.resize((c.occ_bins * upscale, c.gyr_bins * upscale), Image.Resampling.NEAREST)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument(
        "--dataset", default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl"
    )
    parser.add_argument("--generations", type=int, default=24)
    parser.add_argument("--batch", type=int, default=48)
    parser.add_argument("--init-samples", type=int, default=96)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resume", default=None,
                        help="archive.json to seed the initial population from")
    parser.add_argument("--output", default="outputs/anatomical-compiler/qd_archive")
    args = parser.parse_args(argv)

    root = Path.cwd()
    base_config = json.loads((root / args.base).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base_config)
    search_config = json.loads((root / args.search).read_text(encoding="utf-8"))
    ranges = base_config["params"]["ranges"]
    patch = base_config["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])

    codec, genotype, _ = load_dataset((root / args.dataset).resolve())
    genotype_scale = genotype.std(axis=0)
    me = MapElitesConfig(
        generations=args.generations, batch=args.batch, init_samples=args.init_samples,
        steps=args.steps, occupancy_threshold=float(search_config["occupancy_threshold"]),
    )
    seed_vectors = None
    if args.resume is not None:
        prior = json.loads((root / args.resume).read_text(encoding="utf-8"))
        seed_vectors = np.asarray(
            [codec.flatten(e["genotype"]) for e in prior["elites"]], dtype=np.float64
        )
    archive = run(codec, genotype_scale, ranges, config, me, center, size,
                  seed=args.seed, seed_vectors=seed_vectors)

    out_dir = (root / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    elites = [
        {"occBin": i, "gyrBin": j, "occupancy": e.occupancy, "gyration": e.gyration,
         "fitness": e.fitness, "genotype": clamp_params(codec.unflatten(e.vector), ranges)[0]}
        for (i, j), e in sorted(archive.cells.items())
    ]
    (out_dir / "archive.json").write_text(
        json.dumps({
            "cellsFilled": len(archive.cells),
            "cellsTotal": me.occ_bins * me.gyr_bins,
            "behavior": ["occupancy_mean", "gyration"],
            "quality": "energy_mean",
            "elites": elites,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _coverage_image(archive).save(out_dir / "coverage.png")

    total = me.occ_bins * me.gyr_bins
    print(f"\narchive: {len(archive.cells)}/{total} cells "
          f"({100 * len(archive.cells) / total:.0f}%) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
