"""The anatomical compiler, end to end: feed a target phenotype, get a rule and the
creature it grows.

Given a target form (a reference creature from the dataset, or an explicit set of shape
descriptors), the pipeline proposes a starting rule near the answer, refines it with the
batched MLX evolution strategy on the robust shape descriptors, verifies the winner on the
Swift oracle, and renders the creature the compiled rule actually grows. The proposal is
pluggable: nearest known rule today, the cINN once trained.

The objective and the report use only the descriptors the MLX map reproduces faithfully
(mass_mean, mass_std, occupancy_mean, gyration); the Swift re-simulation reports the full
phenotype so the hit can be read against the request the way the oracle sees it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler._codec import (
    PHENOTYPE_FIELDS,
    GenotypeCodec,
    Standardizer,
    load_dataset,
)
from lenia_swarm_analysis.anatomical_compiler.forward_sim import (
    DEFAULT_BINARY,
    ForwardSimulator,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_es_inverse import (
    _PHENOTYPE_ROBUST_INDEX,
    ROBUST_FIELDS,
    ESConfig,
    _robust_descriptors,
    search,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import LeniaConfig
from lenia_swarm_analysis.anatomical_compiler.mlx_validate import (
    _load_frames,
    _run_with_frames,
)

# black -> orange -> pale, matching the dossier accent; density 0 is background.
_CMAP_X = (0.0, 0.5, 1.0)
_CMAP_R = (11, 255, 255)
_CMAP_G = (14, 102, 240)
_CMAP_B = (20, 0, 210)


def _robust_from_phenotype(phenotype: dict[str, Any]) -> np.ndarray:
    return np.asarray([float(phenotype[f]) for f in ROBUST_FIELDS], dtype=np.float64)


def _colorize(field: np.ndarray, *, upscale: int = 4) -> Image.Image:
    clamped = np.clip(field, 0.0, 1.0)
    rgb = np.stack(
        [
            np.interp(clamped, _CMAP_X, _CMAP_R),
            np.interp(clamped, _CMAP_X, _CMAP_G),
            np.interp(clamped, _CMAP_X, _CMAP_B),
        ],
        axis=-1,
    ).astype(np.uint8)
    image = Image.fromarray(rgb, mode="RGB")
    if upscale != 1:
        image = image.resize(
            (image.width * upscale, image.height * upscale), Image.Resampling.NEAREST
        )
    return image


def render_creature(
    genotype: dict[str, Any], output_png: Path, *,
    binary: Path, base_config: dict[str, Any], search_config: dict[str, Any],
    dossier_root: Path, steps: int, init_seed: int, timeout: float,
) -> Image.Image:
    """Re-simulate a rule through the Swift binary and save the settled creature."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        output_dir = Path(raw) / "out"
        _run_with_frames(
            binary, base_config, search_config, genotype, output_dir,
            init_seed=init_seed, steps=steps, stride=steps,
            dossier_root=dossier_root, timeout=timeout,
        )
        frames = _load_frames(output_dir)
    final = frames[max(frames)]
    if final.ndim == 3:
        final = final[:, :, 0]
    image = _colorize(final)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_png)
    return image


def _resolve_target(
    args: argparse.Namespace, codec: GenotypeCodec, genotype: np.ndarray,
    phenotype_full: np.ndarray, simulator: ForwardSimulator,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any] | None, dict[str, Any] | None]:
    """Return (target_robust, target_condition_7, target_params, target_phenotype).

    target_condition_7 is the full PHENOTYPE_FIELDS vector the cINN conditions on; for an
    explicit request the unspecified fields are filled from the dataset median.
    target_params is set only when the target is a reference creature, so the target
    creature itself can be rendered for comparison."""
    robust_cols = list(_PHENOTYPE_ROBUST_INDEX)
    if args.target_index is not None:
        params = codec.unflatten(genotype[args.target_index])
        phenotype = simulator.evaluate(params, init_seed=0)
        cond7 = np.asarray([float(phenotype[f]) for f in PHENOTYPE_FIELDS], dtype=np.float64)
        return cond7[robust_cols], cond7, params, phenotype
    if args.target is not None:
        requested = json.loads(args.target)
        cond7 = np.median(phenotype_full, axis=0)
        for j, col in enumerate(_PHENOTYPE_ROBUST_INDEX):
            if ROBUST_FIELDS[j] in requested:
                cond7[col] = float(requested[ROBUST_FIELDS[j]])
        return cond7[robust_cols], cond7, None, None
    raise SystemExit("provide --target-index or --target")


def _cinn_samples(
    cond7: np.ndarray, checkpoint_path: Path, count: int, seed: int
) -> np.ndarray:
    """Draw a batch of fiber samples from the cINN for the target condition."""
    import torch

    from lenia_swarm_analysis.anatomical_compiler.cinn_inverse import (
        load_checkpoint,
    )
    from lenia_swarm_analysis.anatomical_compiler.cinn_inverse import (
        sample as cinn_sample,
    )

    if not checkpoint_path.is_file():
        raise SystemExit(
            f"cINN checkpoint not found: {checkpoint_path}; train it with "
            "python -m lenia_swarm_analysis.anatomical_compiler.cinn_inverse"
        )
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    inn, geno_std, cond_std = load_checkpoint(checkpoint_path, device)
    return cinn_sample(inn, cond7, cond_std, geno_std, count=count, device=device, seed=seed)


def _gather_proposals(
    mode: str, *, cond7: np.ndarray, target_std: np.ndarray, codec: GenotypeCodec,
    genotype: np.ndarray, phenotype_full: np.ndarray, standardizer: Standardizer,
    target_index: int | None, checkpoint_path: Path, qd_archive_path: Path,
    cinn_count: int, seed: int, nearest_k: int = 12,
) -> np.ndarray:
    """Collect warm-start candidates from the requested sources (nearest known rules,
    cINN fiber samples, QD archive elites). They are scored together on the MLX map by
    the caller, so the best start can come from whichever source covers the target."""
    parts: list[np.ndarray] = []
    if mode in ("nearest", "all"):
        pool_std = standardizer.forward(phenotype_full[:, _PHENOTYPE_ROBUST_INDEX])
        pool_geno = genotype
        if target_index is not None:
            pool_std = np.delete(pool_std, target_index, axis=0)
            pool_geno = np.delete(genotype, target_index, axis=0)
        nearest = np.argsort(np.linalg.norm(pool_std - target_std, axis=1))[:nearest_k]
        parts.append(pool_geno[nearest])
    if mode in ("cinn", "all"):
        parts.append(_cinn_samples(cond7, checkpoint_path, cinn_count, seed))
    if mode in ("qd", "all"):
        if not qd_archive_path.is_file():
            raise SystemExit(
                f"QD archive not found: {qd_archive_path}; build it with "
                "python -m lenia_swarm_analysis.anatomical_compiler.mlx_map_elites"
            )
        prior = json.loads(qd_archive_path.read_text(encoding="utf-8"))
        parts.append(np.asarray(
            [codec.flatten(e["genotype"]) for e in prior["elites"]], dtype=np.float64))
    return np.vstack(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_base_3k_1c_128.json")
    parser.add_argument("--search", default="configs/search/search_crossmap_motion.json")
    parser.add_argument(
        "--dataset", default="outputs/anatomical-compiler/forward_dataset_3k_1c_128.jsonl"
    )
    parser.add_argument("--target-index", type=int, default=None,
                        help="use dataset creature N as the target form")
    parser.add_argument("--target", type=str, default=None,
                        help='explicit target, e.g. \'{"occupancy_mean":0.15,"gyration":2000}\'')
    parser.add_argument("--name", type=str, default="compiled")
    parser.add_argument("--proposal", choices=("nearest", "cinn", "qd", "all"),
                        default="all")
    parser.add_argument("--checkpoint", default="outputs/anatomical-compiler/cinn.pt")
    parser.add_argument("--qd-archive",
                        default="outputs/anatomical-compiler/qd_archive/archive.json")
    parser.add_argument("--proposals", type=int, default=64,
                        help="cINN fiber samples to draw and score for the warm start")
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--population", type=int, default=32)
    parser.add_argument("--elites", type=int, default=8)
    parser.add_argument("--steps", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    root = Path.cwd()
    base_config = json.loads((root / args.base).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base_config)
    search_config = json.loads((root / args.search).read_text(encoding="utf-8"))
    ranges = base_config["params"]["ranges"]
    patch = base_config["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])
    binary = root / DEFAULT_BINARY

    codec, genotype, phenotype_robust = load_dataset((root / args.dataset).resolve())
    rng = np.random.default_rng(args.seed)
    standardizer = Standardizer.fit(phenotype_robust[:, _PHENOTYPE_ROBUST_INDEX])

    simulator = ForwardSimulator(
        root / args.base, root / args.search, dossier_root=root,
        steps=args.steps, init_seed=0, timeout_seconds=600.0,
    )
    target_robust, cond7, target_params, target_phenotype = _resolve_target(
        args, codec, genotype, phenotype_robust, simulator
    )
    target_std = standardizer.forward(target_robust[None, :])[0]

    es = ESConfig(
        steps=args.steps, occupancy_threshold=float(search_config["occupancy_threshold"]),
        iterations=args.iterations, population=args.population, elites=args.elites,
    )
    print("target (robust): " + ", ".join(
        f"{f}={v:.3f}" for f, v in zip(ROBUST_FIELDS, target_robust, strict=False)))

    candidates = _gather_proposals(
        args.proposal, cond7=cond7, target_std=target_std, codec=codec,
        genotype=genotype, phenotype_full=phenotype_robust, standardizer=standardizer,
        target_index=args.target_index, checkpoint_path=(root / args.checkpoint).resolve(),
        qd_archive_path=(root / args.qd_archive).resolve(),
        cinn_count=args.proposals, seed=args.seed,
    )
    proposal_robust = _robust_descriptors(candidates, codec, ranges, config, es, center, size)
    proposal_costs = np.linalg.norm(standardizer.forward(proposal_robust) - target_std, axis=1)
    best = int(np.argmin(proposal_costs))
    start_mean = candidates[best]
    genotype_scale = genotype.std(axis=0)
    print(f"proposal '{args.proposal}': scored {candidates.shape[0]} candidates, "
          f"best start at MLX cost {proposal_costs[best]:.3f}")
    outcome = search(
        target_robust, start_mean, genotype_scale, standardizer,
        codec=codec, ranges=ranges, config=config, es=es,
        center=center, size=size, rng=rng,
    )
    found_params = outcome["bestParams"]

    found_phenotype = simulator.evaluate(found_params, init_seed=0)
    found_robust = _robust_from_phenotype(found_phenotype)
    swift_cost = float(np.linalg.norm(
        standardizer.forward(found_robust[None, :])[0] - target_std))

    out_dir = (root / "outputs/anatomical-compiler/compiled" / args.name).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def _render(params: dict[str, Any], png: Path) -> None:
        render_creature(
            params, png, binary=binary, base_config=base_config,
            search_config=search_config, dossier_root=root, steps=args.steps,
            init_seed=0, timeout=600.0,
        )

    _render(found_params, out_dir / "creature.png")
    if target_params is not None:
        _render(target_params, out_dir / "target.png")

    report = {
        "target": {f: float(target_robust[j]) for j, f in enumerate(ROBUST_FIELDS)},
        "found": {f: float(found_robust[j]) for j, f in enumerate(ROBUST_FIELDS)},
        "foundPhenotype": {k: found_phenotype.get(k) for k in (
            "mass_mean", "mass_std", "occupancy_mean", "variance_mean",
            "energy_mean", "gyration", "is_stable")},
        "foundGenotype": found_params,
        "mlxCost": outcome["bestCost"],
        "swiftCost": swift_cost,
        "proposal": args.proposal,
    }
    (out_dir / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True),
                                         encoding="utf-8")

    print(f"\nMLX search cost {outcome['bestCost']:.3f} -> Swift re-sim cost {swift_cost:.3f}")
    for f in ROBUST_FIELDS:
        tv = float(target_robust[ROBUST_FIELDS.index(f)])
        fv = float(found_robust[ROBUST_FIELDS.index(f)])
        print(f"    {f:16s} target {tv:10.3f}  found {fv:10.3f}  "
              f"rel {abs(fv - tv) / (abs(tv) + 1e-9) * 100:5.1f}%")
    print(f"\nwrote {out_dir}/creature.png and result.json")
    if target_params is not None:
        print(f"target creature rendered to {out_dir}/target.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
