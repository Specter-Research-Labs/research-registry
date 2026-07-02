"""First functional morphospace: PCA over the behavioral (dynamics) metrics of a creature
harvest, each creature measured at its OWN characteristic developmental init.

The shape morphospace is warehoused already; function was the gap. A track1 harvest stores, per
creature, a unique init_seed (its developmental condition) and the locomotion/activity metrics
computed there. Under fresh noise seeds these same rules collapse to indistinguishable streaks
(the genotype does not fix the phenotype); under their own init they span orders of magnitude in
speed, path, and activity. This reduces that behavioral spread to its principal axes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_HARVEST = ("artifacts/flow-universe-runs/track1-20260520/"
           "track1b-2c10-r7-10-initshift-8192-s4090112/results.jsonl")
_LOG_METRICS = ("speed_mean", "path_length", "displacement", "center_velocity")
_LIN_METRICS = ("variance_mean", "energy_mean")
_METRICS = _LOG_METRICS + _LIN_METRICS


def _load(path: Path) -> np.ndarray:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    rows = [r for r in rows if r.get("filters_passed")]
    cols = []
    for key in _METRICS:
        v = np.array([float(r["metrics"].get(key) or 0.0) for r in rows])
        cols.append(np.log1p(v) if key in _LOG_METRICS else v)
    return np.stack(cols, axis=1)


def _pca(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0) + 1e-12
    z = (matrix - mean) / std
    u, s, vt = np.linalg.svd(z, full_matrices=False)
    scores = u * s
    explained = (s ** 2) / (s ** 2).sum()
    return scores, vt, explained


def _scatter(scores: np.ndarray, color_by: np.ndarray, out_png: Path) -> None:
    W, H, pad = 900, 700, 70
    img = Image.new("RGB", (W, H), (11, 14, 20))
    d = ImageDraw.Draw(img)
    x, y = scores[:, 0], scores[:, 1]
    x0, x1 = float(x.min()), float(x.max())
    y0, y1 = float(y.min()), float(y.max())
    c0 = float(color_by.min())
    c1 = float(color_by.max()) + 1e-9

    def px(v: float) -> float:
        return pad + (v - x0) / (x1 - x0 + 1e-12) * (W - 2 * pad)

    def py(v: float) -> float:
        return H - pad - (v - y0) / (y1 - y0 + 1e-12) * (H - 2 * pad)

    d.rectangle([pad, pad, W - pad, H - pad], outline=(90, 100, 115))
    for i in range(len(x)):
        t = (float(color_by[i]) - c0) / (c1 - c0)
        col = (int(40 + 215 * t), int(120 - 60 * t), int(200 - 160 * t))
        d.ellipse([px(x[i]) - 2, py(y[i]) - 2, px(x[i]) + 2, py(y[i]) + 2], fill=col)
    d.text((pad, H - pad + 14), "PC1 (behavioral) ->", fill=(150, 160, 175))
    d.text((10, pad - 18), "PC2 -> (color=speed: blue slow, orange fast)", fill=(150, 160, 175))
    img.save(out_png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harvest", default=_HARVEST)
    parser.add_argument("--output", default="outputs/anatomical-compiler/functional-morphospace")
    args = parser.parse_args(argv)

    root = Path.cwd()
    matrix = _load((root / args.harvest).resolve())
    scores, components, explained = _pca(matrix)
    out_dir = (root / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _scatter(scores, matrix[:, 0], out_dir / "functional_morphospace.png")

    loadings = {}
    for pc in range(min(3, len(components))):
        ranked = sorted(zip(_METRICS, components[pc], strict=False),
                        key=lambda kv: -abs(kv[1]))
        loadings[f"PC{pc + 1}"] = [{"metric": m, "weight": round(float(w), 3)} for m, w in ranked]
    report = {
        "n": int(matrix.shape[0]), "metrics": list(_METRICS),
        "explainedVariance": [round(float(e), 4) for e in explained],
        "loadings": loadings,
    }
    (out_dir / "functional_morphospace.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"n={matrix.shape[0]}  explained variance: "
          f"{', '.join(f'{e:.0%}' for e in explained)}")
    for pc, items in loadings.items():
        top = "  ".join(f"{it['metric']}={it['weight']:+.2f}" for it in items[:3])
        print(f"  {pc}: {top}")
    print(f"wrote {out_dir}/functional_morphospace.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
