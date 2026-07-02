"""Does form predict behavior? Regress the functional axes of the harvest against its shape
descriptors, for the same creatures at the same characteristic inits.

The shape morphospace and the functional morphospace are built from one harvest. If shape fixed
function, the functional axes would be fully recoverable from the shape block; if they are
independent, shape explains little. This fits each functional principal axis from the shape
descriptors and reports the explained variance, the honest measure of how much behavior the form
pins down.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from lenia_swarm_analysis.anatomical_compiler.functional_morphospace import _HARVEST, _pca

_SHAPE_METRICS = (
    "gyration", "occupancy_mean", "largest_component_fraction",
    "largest_component_anisotropy", "moment_anisotropy", "moment_density",
    "component_count", "mass_mean",
)
_FUNC_LOG = ("speed_mean", "path_length", "displacement", "center_velocity")
_FUNC_LIN = ("variance_mean", "energy_mean")


def _load_blocks(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    rows = [r for r in rows if r.get("filters_passed")]
    shape = np.stack([np.array([float(r["metrics"].get(k) or 0.0) for r in rows])
                      for k in _SHAPE_METRICS], axis=1)
    func_cols = []
    for key in _FUNC_LOG + _FUNC_LIN:
        v = np.array([float(r["metrics"].get(key) or 0.0) for r in rows])
        func_cols.append(np.log1p(v) if key in _FUNC_LOG else v)
    return shape, np.stack(func_cols, axis=1)


def _standardize(matrix: np.ndarray) -> np.ndarray:
    return (matrix - matrix.mean(axis=0)) / (matrix.std(axis=0) + 1e-12)


def _regress(x: np.ndarray, y: np.ndarray) -> tuple[float, np.ndarray]:
    design = np.column_stack([np.ones(len(x)), x])
    coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    pred = design @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / (ss_tot + 1e-12), coef[1:]


def _scatter(actual: np.ndarray, pred: np.ndarray, r2: float, out_png: Path) -> None:
    W, H, pad = 760, 760, 70
    img = Image.new("RGB", (W, H), (11, 14, 20))
    d = ImageDraw.Draw(img)
    lo = float(min(actual.min(), pred.min()))
    hi = float(max(actual.max(), pred.max()))

    def p(v: float) -> float:
        return pad + (v - lo) / (hi - lo + 1e-12) * (W - 2 * pad)

    d.rectangle([pad, pad, W - pad, H - pad], outline=(90, 100, 115))
    d.line([p(lo), H - pad - (p(lo) - pad), p(hi), H - pad - (p(hi) - pad)], fill=(70, 80, 95))
    for i in range(len(actual)):
        x, y = p(float(actual[i])), H - pad - (p(float(pred[i])) - pad)
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(90, 130, 200))
    d.text((pad, H - pad + 14), "actual functional PC1 ->", fill=(150, 160, 175))
    d.text((12, pad - 20), f"predicted from shape (R2={r2:.2f}) ->", fill=(150, 160, 175))
    img.save(out_png)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harvest", default=_HARVEST)
    parser.add_argument("--output", default="outputs/anatomical-compiler/functional-morphospace")
    args = parser.parse_args(argv)

    root = Path.cwd()
    shape_raw, func_raw = _load_blocks((root / args.harvest).resolve())
    shape = _standardize(shape_raw)
    func_scores, _, func_explained = _pca(func_raw)

    axis_names = ["locomotion", "activity", "tortuosity"]
    results = []
    for axis in range(3):
        r2, coef = _regress(shape, func_scores[:, axis])
        ranked = sorted(zip(_SHAPE_METRICS, coef, strict=False), key=lambda kv: -abs(kv[1]))
        results.append({
            "axis": axis_names[axis],
            "funcVarianceShare": round(float(func_explained[axis]), 3),
            "r2FromShape": round(r2, 3),
            "topShapePredictors": [{"metric": m, "coef": round(float(c), 3)}
                                   for m, c in ranked[:3]],
        })

    out_dir = (root / args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    r2_loco, _ = _regress(shape, func_scores[:, 0])
    pred = np.column_stack([np.ones(len(shape)), shape]) @ np.linalg.lstsq(
        np.column_stack([np.ones(len(shape)), shape]), func_scores[:, 0], rcond=None)[0]
    _scatter(func_scores[:, 0], pred, r2_loco, out_dir / "shape_predicts_function.png")
    report = {"n": int(shape.shape[0]), "shapeMetrics": list(_SHAPE_METRICS), "axes": results}
    (out_dir / "shape_function_coupling.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    print(f"n={shape.shape[0]}  shape->function explained variance (R2):")
    for r in results:
        top = ", ".join(f"{p['metric']}{p['coef']:+.2f}" for p in r["topShapePredictors"])
        print(f"  {r['axis']:11s} ({r['funcVarianceShare']:.0%} of function): "
              f"R2={r['r2FromShape']:.2f}   [{top}]")
    print(f"wrote {out_dir}/shape_predicts_function.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
