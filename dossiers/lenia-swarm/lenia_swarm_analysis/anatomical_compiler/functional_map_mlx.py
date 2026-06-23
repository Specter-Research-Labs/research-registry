"""Body-seeded functional map: complexity x recovery, with each creature run from its OWN
form rather than a generic noise seed.

The noise-seeded map washed out because every rule makes a similar blob from noise. Here each
creature is grown to its most coherent body (best of a few seeds, the form-compiler way), and
the recovery assay ablates THAT body, so structure can express and the complexity x recovery
relation can actually be read. Runs on MLX because per-creature seeds are trivial in-process;
the descriptors are the robust ones (occupancy, gyration, single-body coherence) plus an
edge-density complexity proxy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np
from PIL import Image, ImageDraw

from lenia_swarm_analysis.anatomical_compiler.functional_map import _build_corpus
from lenia_swarm_analysis.anatomical_compiler.mlx_assays import _ablate, _terminal_descriptors
from lenia_swarm_analysis.anatomical_compiler.mlx_coherence import _component_metrics
from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import _coordinate_grids
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    make_init,
    rollout,
)


def _grow_bodies(corpus: list[dict[str, Any]], config: LeniaConfig, *,
                 center: tuple[int, int], size: int, occupancy_threshold: float,
                 n_seeds: int, steps: int, chunk: int) -> np.ndarray:
    """For each creature, run a few noise seeds to settle and keep the most coherent body."""
    pairs = [(i, s) for i in range(len(corpus)) for s in range(n_seeds)]
    settled = np.empty((len(pairs), config.sx, config.sy, config.channels), np.float32)
    for c0 in range(0, len(pairs), chunk):
        sub = pairs[c0:c0 + chunk]
        geno = GenotypeBatch.from_param_dicts([corpus[i] for i, _ in sub])
        inits = mx.concatenate(
            [make_init(config, seed=s, center=center, size=size, batch=1) for _, s in sub],
            axis=0,
        )
        a = rollout(inits, geno, config, steps)
        mx.eval(a)
        settled[c0:c0 + len(sub)] = np.asarray(a)
    bodies = np.empty((len(corpus), config.sx, config.sy, config.channels), np.float32)
    for i in range(len(corpus)):
        cand = settled[i * n_seeds:(i + 1) * n_seeds]
        lcfs = [_component_metrics(cand[j].sum(-1), occupancy_threshold)[0] for j in range(n_seeds)]
        bodies[i] = cand[int(np.argmax(lcfs))]
    return bodies


def _complexity(bodies: np.ndarray) -> np.ndarray:
    """Edge density of the summed-mass body: structured forms carry more boundary per mass
    than a smooth blob."""
    f = bodies.sum(-1)
    gx = np.abs(np.diff(f, axis=1, append=f[:, -1:, :]))
    gy = np.abs(np.diff(f, axis=2, append=f[:, :, -1:]))
    return (gx + gy).sum(axis=(1, 2)) / (f.sum(axis=(1, 2)) + 1e-9)


def _recovery(bodies: np.ndarray, corpus: list[dict[str, Any]], config: LeniaConfig, *,
              center: tuple[int, int], ablate_size: int, occupancy_threshold: float,
              steps: int, chunk: int) -> np.ndarray:
    """Re-seed each body clean and lesioned, run forward, and return the relative terminal
    drift over the robust descriptors (low = the form regenerated)."""
    grid_x, grid_y = _coordinate_grids(config)
    base = np.empty((len(corpus), 4))
    abl = np.empty((len(corpus), 4))
    for c0 in range(0, len(corpus), chunk):
        params = corpus[c0:c0 + chunk]
        geno = GenotypeBatch.from_param_dicts(params)
        body = mx.array(bodies[c0:c0 + len(params)])
        base_end = rollout(body, geno, config, steps)
        abl_end = rollout(_ablate(body, center, ablate_size), geno, config, steps)
        base[c0:c0 + len(params)] = _terminal_descriptors(
            base_end, config, occupancy_threshold, grid_x, grid_y)
        abl[c0:c0 + len(params)] = _terminal_descriptors(
            abl_end, config, occupancy_threshold, grid_x, grid_y)
    return (np.abs(base - abl) / (np.abs(base) + 1e-9)).mean(axis=1)


def _scatter(complexity: np.ndarray, drift: np.ndarray, is_coherent: np.ndarray,
             out_png: Path) -> None:
    W, H, pad = 900, 640, 70
    img = Image.new("RGB", (W, H), (11, 14, 20))
    d = ImageDraw.Draw(img)
    cx0, cx1 = float(complexity.min()), float(max(complexity.max(), complexity.min() + 1e-6))
    dy0, dy1 = 0.0, float(max(drift.max(), 0.05))

    def px(c: float) -> float:
        return pad + (c - cx0) / (cx1 - cx0) * (W - 2 * pad)

    def py(v: float) -> float:
        return H - pad - (v - dy0) / (dy1 - dy0) * (H - 2 * pad)

    # regenerator corner: high complexity (right), low drift (bottom)
    d.rectangle([px((cx0 + cx1) / 2), py((dy0 + dy1) / 2), W - pad, py(dy0)], fill=(26, 30, 22))
    d.text((px((cx0 + cx1) / 2) + 8, py(dy0) - 16), "regenerators?", fill=(120, 150, 90))
    d.rectangle([pad, pad, W - pad, H - pad], outline=(90, 100, 115))
    for c, v, coh in zip(complexity, drift, is_coherent, strict=False):
        x, y = px(float(c)), py(float(v))
        col = (255, 140, 0) if coh else (90, 130, 200)
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
    d.text((pad, H - pad + 14), "complexity (edge density) ->", fill=(150, 160, 175))
    d.text((10, pad - 18), "form drift after ablation (low=recovered)", fill=(150, 160, 175))
    d.text((W - pad - 200, pad - 18), "orange=coherent  blue=random", fill=(150, 160, 175))
    img.save(out_png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_random_3c_15k_128.json")
    parser.add_argument("--seeds", default="outputs/anatomical-compiler/3c15/coherent_seeds.jsonl")
    parser.add_argument("--n-random", type=int, default=40)
    parser.add_argument("--n-seeds", type=int, default=3)
    parser.add_argument("--body-steps", type=int, default=500)
    parser.add_argument("--recovery-steps", type=int, default=500)
    parser.add_argument("--ablate-size", type=int, default=40)
    parser.add_argument("--chunk", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", default="outputs/anatomical-compiler/3c15/functional_map_mlx")
    args = parser.parse_args(argv)

    root = Path.cwd()
    base = json.loads((root / args.base).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base)
    ranges = base["params"]["ranges"]
    patch = base["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])
    occ = 0.05

    corpus, is_coherent = _build_corpus(
        (root / args.seeds).resolve(), args.n_random, ranges, args.seed)
    print(f"corpus: {len(corpus)} creatures "
          f"({int(is_coherent.sum())} coherent + {int((~is_coherent).sum())} random)")
    print("growing bodies ...")
    bodies = _grow_bodies(corpus, config, center=center, size=size, occupancy_threshold=occ,
                          n_seeds=args.n_seeds, steps=args.body_steps, chunk=args.chunk)
    complexity = _complexity(bodies)
    print("running ablation recovery ...")
    drift = _recovery(bodies, corpus, config, center=center, ablate_size=args.ablate_size,
                      occupancy_threshold=occ, steps=args.recovery_steps, chunk=args.chunk)

    out_dir = (root / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _scatter(complexity, drift, is_coherent, out_dir / "complexity_recovery.png")
    corr = float(np.corrcoef(complexity, drift)[0, 1])
    coh = is_coherent
    report = {
        "n": len(corpus), "corr_complexity_drift": corr,
        "coherent": {"complexity": float(complexity[coh].mean()),
                     "drift": float(drift[coh].mean())},
        "random": {"complexity": float(complexity[~coh].mean()),
                   "drift": float(drift[~coh].mean())},
        "perCreature": [{"complexity": float(complexity[i]), "drift": float(drift[i]),
                         "coherent": bool(coh[i])} for i in range(len(corpus))],
    }
    (out_dir / "functional_map.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\ncorr(complexity, drift) = {corr:.3f}")
    print(f"coherent: complexity {complexity[coh].mean():.3f} drift {drift[coh].mean():.3f}")
    print(f"random:   complexity {complexity[~coh].mean():.3f} drift {drift[~coh].mean():.3f}")
    print(f"wrote {out_dir}/complexity_recovery.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
