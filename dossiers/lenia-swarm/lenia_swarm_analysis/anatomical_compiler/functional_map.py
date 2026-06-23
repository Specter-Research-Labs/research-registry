"""First functional morphospace slice: complexity x recovery.

Tests the hypothesis that the (high complexity, high recovery) corner -- structured creatures
that regenerate their form after a lesion -- is nearly empty. Builds a corpus spanning
structure (coherent 3c15 creatures plus random rules that make blobs), runs it through the
batched corpus-eval on the metal-full oracle under two conditions (clean baseline and a
mid-rollout ablation), and maps each creature's complexity against how far its form drifts
after the damage. A re-pooling blob sits low-complexity / low-drift; a fragile structured
creature sits high-complexity / high-drift; a regenerator would sit high-complexity / low-drift.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from lenia_swarm_analysis.anatomical_compiler._codec import GenotypeCodec
from lenia_swarm_analysis.anatomical_compiler.forward_sim import DEFAULT_BINARY, _merged_env

_DRIFT_FIELDS = ("occupancy_mean", "gyration", "largest_component_fraction")


def _random_params(n: int, codec: GenotypeCodec, ranges: dict[str, list[float]],
                   rng: np.random.Generator) -> list[dict[str, Any]]:
    """Random genotypes (mostly blobs) to span the low-structure end of the corpus."""
    la, lb, lw = codec.bump_lengths

    def u(key: str, m: int) -> list[float]:
        lo, hi = ranges[key]
        return list(rng.uniform(lo, hi, size=m))

    out: list[dict[str, Any]] = []
    for _ in range(n):
        p: dict[str, Any] = {"R": float(rng.uniform(ranges["R"][0], ranges["R"][1]))}
        for key in ("m", "s", "h", "r"):
            p[key] = u(key, codec.kernel_count)
        p["a"] = [u("a", la) for _ in range(codec.kernel_count)]
        p["b"] = [u("b", lb) for _ in range(codec.kernel_count)]
        p["w"] = [u("w", lw) for _ in range(codec.kernel_count)]
        out.append(p)
    return out


def _build_corpus(seeds_path: Path, n_random: int, ranges: dict[str, list[float]],
                  seed: int) -> tuple[list[dict[str, Any]], np.ndarray]:
    coherent = [json.loads(line)["params"]
                for line in seeds_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    codec = GenotypeCodec.from_params(coherent[0])
    random_params = _random_params(n_random, codec, ranges, np.random.default_rng(seed))
    corpus = coherent + random_params
    is_coherent = np.array([True] * len(coherent) + [False] * len(random_params))
    return corpus, is_coherent


def _run_eval(binary: Path, base_config: dict, search_config: dict, corpus: list[dict],
              out_dir: Path, *, root: Path, name: str) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = out_dir / f"{name}_config.json"
    search_path = out_dir / f"{name}_search.json"
    corpus_path = out_dir / f"{name}_corpus.jsonl"
    config_path.write_text(json.dumps(base_config), encoding="utf-8")
    search_path.write_text(json.dumps(search_config), encoding="utf-8")
    corpus_path.write_text("\n".join(json.dumps({"params": p}) for p in corpus), encoding="utf-8")
    run_out = out_dir / name
    cmd = [
        str(binary), "discover", "evaluate",
        "--config", str(config_path), "--search", str(search_path),
        "--corpus", str(corpus_path), "--init-seed", "0", "--output", str(run_out),
    ]
    env = {"SPECTER_ARTIFACT_ROOT": str(out_dir / "artifacts")}
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=1800,
                               env=_merged_env(env), cwd=str(root))
    if completed.returncode != 0:
        raise RuntimeError(f"evaluate ({name}) failed:\n{completed.stderr[-2000:]}")
    results = sorted(run_out.rglob("results.jsonl"))
    rows = [json.loads(line) for line in results[-1].read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return [r["metrics"] for r in rows]


def _scatter(complexity: np.ndarray, drift: np.ndarray, is_coherent: np.ndarray,
             out_png: Path) -> None:
    W, H, pad = 900, 640, 70
    img = Image.new("RGB", (W, H), (11, 14, 20))
    d = ImageDraw.Draw(img)
    cx0, cx1 = complexity.min(), max(complexity.max(), complexity.min() + 1e-6)
    dy0, dy1 = 0.0, max(drift.max(), 0.05)

    def px(c: float) -> float:
        return pad + (c - cx0) / (cx1 - cx0) * (W - 2 * pad)

    def py(v: float) -> float:
        return H - pad - (v - dy0) / (dy1 - dy0) * (H - 2 * pad)

    d.rectangle([pad, pad, W - pad, H - pad], outline=(90, 100, 115))
    # highlight the hypothesized-empty corner: high complexity, low drift
    d.rectangle([px((cx0 + cx1) / 2), py(dy1), W - pad, py((dy0 + dy1) / 2)],
                fill=(26, 30, 22))
    d.text((px((cx0 + cx1) / 2) + 8, py(dy1) + 8), "regenerators?", fill=(120, 150, 90))
    for c, v, coh in zip(complexity, drift, is_coherent, strict=False):
        x, y = px(float(c)), py(float(v))
        col = (255, 140, 0) if coh else (90, 130, 200)
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
    d.text((pad, H - pad + 14), "complexity ->", fill=(150, 160, 175))
    d.text((10, pad - 18), "form drift after ablation (low = recovered) ->", fill=(150, 160, 175))
    d.text((W - pad - 200, pad - 18), "orange=coherent  blue=random", fill=(150, 160, 175))
    img.save(out_png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/base/paper_random_3c_15k_128.json")
    parser.add_argument("--search", default="configs/search/search_track1_coherent_128.json")
    parser.add_argument("--seeds", default="outputs/anatomical-compiler/3c15/coherent_seeds.jsonl")
    parser.add_argument("--n-random", type=int, default=150)
    parser.add_argument("--ablate-step", type=int, default=400)
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--ablate-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", default="outputs/anatomical-compiler/3c15/functional_map")
    args = parser.parse_args(argv)

    root = Path.cwd()
    base = json.loads((root / args.base).read_text(encoding="utf-8"))
    ranges = base["params"]["ranges"]
    patch = base["init"]["patches"][0]
    search = json.loads((root / args.search).read_text(encoding="utf-8"))
    search = deepcopy(search)
    search["steps"] = args.steps
    search["warmup_steps"] = args.ablate_step          # record only the post-ablation window
    search["complexity"] = {"enabled": True, "scales": [0, 1, 2, 3], "target": None,
                            "polar": True, "backend": "png"}
    out_dir = (root / args.output).resolve()

    corpus, is_coherent = _build_corpus(
        (root / args.seeds).resolve(), args.n_random, ranges, args.seed)
    binary = root / DEFAULT_BINARY

    baseline_config = deepcopy(base)
    ablation_config = deepcopy(base)
    ablation_config["profile"] = "experimental"
    ablation_config["interventions"] = [{
        "version": 1, "type": "zero_state_patch", "step": args.ablate_step,
        "patch": {"center": patch["center"], "size": args.ablate_size},
    }]

    print(f"corpus: {len(corpus)} creatures "
          f"({int(is_coherent.sum())} coherent + {int((~is_coherent).sum())} random)")
    print("running baseline ...")
    base_metrics = _run_eval(
        binary, baseline_config, search, corpus, out_dir, root=root, name="baseline")
    print("running ablation ...")
    abl_metrics = _run_eval(
        binary, ablation_config, search, corpus, out_dir, root=root, name="ablation")

    n = min(len(base_metrics), len(abl_metrics), len(corpus))
    complexity = np.array([float(base_metrics[i].get("complexity_mean") or 0.0) for i in range(n)])
    drift = np.empty(n)
    for i in range(n):
        b, a = base_metrics[i], abl_metrics[i]
        rels = [abs((b.get(f) or 0.0) - (a.get(f) or 0.0)) / (abs(b.get(f) or 0.0) + 1e-9)
                for f in _DRIFT_FIELDS]
        drift[i] = float(np.mean(rels))

    coh = is_coherent[:n]
    out_dir.mkdir(parents=True, exist_ok=True)
    _scatter(complexity, drift, coh, out_dir / "complexity_recovery.png")
    report = {
        "n": n, "ablateStep": args.ablate_step, "steps": args.steps,
        "complexityRange": [float(complexity.min()), float(complexity.max())],
        "driftRange": [float(drift.min()), float(drift.max())],
        "highComplexityLowDriftCount": int(np.sum(
            (complexity > np.median(complexity)) & (drift < np.median(drift)))),
        "perCreature": [{"complexity": float(complexity[i]), "drift": float(drift[i]),
                         "coherent": bool(coh[i])} for i in range(n)],
    }
    (out_dir / "functional_map.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\ncomplexity {report['complexityRange'][0]:.2f}-{report['complexityRange'][1]:.2f}, "
          f"drift {report['driftRange'][0]:.2f}-{report['driftRange'][1]:.2f}")
    print(f"high-complexity & low-drift (the regenerator corner): "
          f"{report['highComplexityLowDriftCount']}/{n}")
    print(f"wrote {out_dir}/complexity_recovery.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
