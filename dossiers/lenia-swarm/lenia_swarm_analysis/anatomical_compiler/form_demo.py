"""The form compiler, end to end and visible: hand it a creature's form, get a rule that
grows it, and see the result.

Given a target creature, lift its body out as the target form, then compile a rule that
holds that form starting from a DIFFERENT coherent creature (so it is a real search, not a
look-up). The output is a three-panel image: the target form we asked for, the compiled
rule re-seeded with that form (does it hold it?), and the compiled rule grown from a plain
noise seed (is it a genuine creature on its own, or a degenerate hold?). The three channels
are rendered straight to RGB, so the multi-channel structure shows in colour.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlx.core as mx
import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler._codec import (
    GenotypeCodec,
    clamp_params,
)
from lenia_swarm_analysis.anatomical_compiler.form_compiler import (
    compile_form,
    grow_body,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    make_init,
    rollout,
)


def _colorize_channels(field: np.ndarray, *, upscale: int = 4) -> Image.Image:
    """Map a [sx, sy, C<=3] field straight to RGB on a dark ground, normalised per image."""
    sx, sy, c = field.shape
    rgb = np.zeros((sx, sy, 3), dtype=np.float32)
    rgb[:, :, :c] = np.clip(field[:, :, : min(c, 3)], 0.0, None)
    vmax = max(float(rgb.max()), 1e-3)
    image = Image.fromarray((np.clip(rgb / vmax, 0, 1) * 255).astype(np.uint8), mode="RGB")
    return image.resize((sy * upscale, sx * upscale), Image.Resampling.NEAREST)


def _run(rule_vec: np.ndarray, a0: mx.array, codec: GenotypeCodec,
         ranges: dict[str, list[float]], config: LeniaConfig, steps: int) -> np.ndarray:
    params, _ = clamp_params(codec.unflatten(rule_vec), ranges)
    geno = GenotypeBatch.from_param_dicts([params])
    a = rollout(a0, geno, config, steps)
    mx.eval(a)
    return np.asarray(a[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_random_3c_15k_128.json")
    parser.add_argument("--seeds",
                        default="outputs/anatomical-compiler/3c15/coherent_seeds.jsonl")
    parser.add_argument("--target-index", type=int, default=0,
                        help="creature whose form is the target")
    parser.add_argument("--start-index", type=int, default=1,
                        help="different creature to start the search from")
    parser.add_argument("--name", default="form_demo")
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--population", type=int, default=24)
    parser.add_argument("--steps", type=int, default=180)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    root = Path.cwd()
    base = json.loads((root / args.base).read_text(encoding="utf-8"))
    config = LeniaConfig.from_base_config(base)
    ranges = base["params"]["ranges"]
    patch = base["init"]["patches"][0]
    center = (int(patch["center"][0]), int(patch["center"][1]))
    size = int(patch["size"])
    occ = 0.05

    rules = [json.loads(line)["params"] for line in
             (root / args.seeds).read_text(encoding="utf-8").splitlines() if line.strip()]
    codec = GenotypeCodec.from_params(rules[0])
    gscale = np.asarray([codec.flatten(p) for p in rules]).std(axis=0)
    gscale[gscale < 1e-6] = 0.05
    rng = np.random.default_rng(args.seed)

    target_rule = rules[args.target_index]
    start_vec = np.asarray(codec.flatten(rules[args.start_index]))

    print(f"growing target form from creature {args.target_index} ...")
    target = grow_body(target_rule, config, center=center, size=size, occupancy_threshold=occ)
    print(f"  target form: lcf={target.lcf:.2f} occ={target.occupancy:.3f} "
          f"liveness={target.liveness:.4f}")

    print(f"compiling a rule that holds it, starting from creature {args.start_index} ...")
    result = compile_form(
        target, start_vec, gscale, codec=codec, ranges=ranges, config=config, rng=rng,
        iterations=args.iterations, population=args.population, steps=args.steps,
        occupancy_threshold=occ,
    )
    print(f"  drift {result.start_objective:.2f} -> {result.best_drift:.3f}  "
          f"liveness {result.best_liveness:.4f} (target {target.liveness:.4f})")

    # Panels: target form | compiled rule re-seeded with the form | compiled rule from noise
    held = _run(result.best_vector, target.field, codec, ranges, config, args.steps)
    noise_seed = make_init(config, seed=0, center=center, size=size, batch=1)
    from_noise = _run(result.best_vector, noise_seed, codec, ranges, config, 600)
    panels = [
        ("target form", np.asarray(target.field[0])),
        ("compiled, holding the form", held),
        ("compiled, grown from noise", from_noise),
    ]
    imgs = [_colorize_channels(p) for _, p in panels]
    gap = 18
    w = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
    montage = Image.new("RGB", (w, imgs[0].height), (11, 14, 20))
    x = 0
    for im in imgs:
        montage.paste(im, (x, 0))
        x += im.width + gap

    out_dir = (root / "outputs/anatomical-compiler/compiled" / args.name).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    montage.save(out_dir / "form_compile.png")
    (out_dir / "result.json").write_text(json.dumps({
        "targetIndex": args.target_index, "startIndex": args.start_index,
        "targetForm": {"lcf": target.lcf, "occupancy": target.occupancy,
                       "liveness": target.liveness},
        "bestDrift": result.best_drift, "bestLiveness": result.best_liveness,
        "startObjective": result.start_objective, "history": result.history,
        "bestRule": clamp_params(codec.unflatten(result.best_vector), ranges)[0],
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {out_dir}/form_compile.png  (panels: {', '.join(n for n, _ in panels)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
