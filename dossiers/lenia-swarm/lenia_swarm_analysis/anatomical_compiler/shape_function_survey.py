"""Shape-to-function coupling across many harvests, with axes matched to a reference.

shape_function_coupling fits one harvest and names its functional PCs by index. Across harvests
the PCs can rotate or reorder, so each harvest's PC loadings are matched to a reference
functional_morphospace.json by absolute cosine, and the fits onto raw functional metrics are
reported as well because they do not depend on the PCs at all. Drop-one R2 attributes each fit to
the shape metrics. --compact-bodies restricts a harvest to records whose largest component holds
nearly all mass and that have at most two components.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.anatomical_compiler.functional_morphospace import _METRICS, _pca
from lenia_swarm_analysis.anatomical_compiler.shape_function_coupling import (
    _SHAPE_METRICS,
    _load_blocks,
    _regress,
    _standardize,
)

COMPACT_BODY_FRACTION = 0.99
COMPACT_BODY_COMPONENTS = 2
_AXIS_NAMES = ("locomotion", "activity", "tortuosity")
_TRAVEL = ("speed_mean", "path_length", "displacement", "center_velocity")
# Single-metric drop-one R2 understates collinear blocks, so size and anisotropy are also
# attributed as groups.
_SHAPE_GROUPS = {
    "size": ("gyration", "occupancy_mean", "moment_density", "mass_mean"),
    "anisotropy": ("largest_component_anisotropy", "moment_anisotropy"),
    "integrity": ("largest_component_fraction", "component_count"),
}


def _reference_loadings(path: Path) -> np.ndarray:
    report = json.loads(path.read_text(encoding="utf-8"))
    if tuple(report["metrics"]) != _METRICS:
        raise SystemExit(f"{path}: metrics {report['metrics']} differ from {_METRICS}")
    return np.array([
        [{item["metric"]: item["weight"] for item in report["loadings"][f"PC{pc + 1}"]}[m]
         for m in _METRICS]
        for pc in range(3)
    ])


def _fit(shape: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    r2, coef = _regress(shape, (target - target.mean()) / (target.std() + 1e-12))
    drop_one = {
        name: round(r2 - _regress(np.delete(shape, i, axis=1), target)[0], 4)
        for i, name in enumerate(_SHAPE_METRICS)
    }
    groups = {
        name: [_SHAPE_METRICS.index(metric) for metric in members]
        for name, members in _SHAPE_GROUPS.items()
    }
    return {
        "r2": round(r2, 4),
        "dropGroupR2": {
            name: round(r2 - _regress(np.delete(shape, cols, axis=1), target)[0], 4)
            for name, cols in groups.items()
        },
        "groupOnlyR2": {
            name: round(_regress(shape[:, cols], target)[0], 4) for name, cols in groups.items()
        },
        "standardizedCoef": {n: round(float(c), 4) for n, c in zip(_SHAPE_METRICS, coef, strict=True)},
        "dropOneR2": drop_one,
    }


def survey_harvest(harvest: Path, *, reference: np.ndarray, compact_bodies: bool) -> dict[str, Any]:
    shape_raw, func_raw = _load_blocks(harvest)
    if compact_bodies:
        lcf = shape_raw[:, _SHAPE_METRICS.index("largest_component_fraction")]
        components = shape_raw[:, _SHAPE_METRICS.index("component_count")]
        keep = (lcf >= COMPACT_BODY_FRACTION) & (components <= COMPACT_BODY_COMPONENTS)
        shape_raw, func_raw = shape_raw[keep], func_raw[keep]
    shape = _standardize(shape_raw)
    scores, components_, explained = _pca(func_raw)
    loadings = components_[:3]
    cosine = np.abs(loadings @ reference.T) / np.outer(
        np.linalg.norm(loadings, axis=1), np.linalg.norm(reference, axis=1))
    pcs = []
    for pc in range(3):
        match = int(cosine[pc].argmax())
        pcs.append({
            "index": pc + 1,
            "indexLabel": _AXIS_NAMES[pc],
            "matchedLabel": _AXIS_NAMES[match],
            "matchCosine": round(float(cosine[pc, match]), 4),
            "varianceShare": round(float(explained[pc]), 4),
            "r2FromShape": round(_regress(shape, scores[:, pc])[0], 4),
        })
    return {
        "harvest": str(harvest),
        "compactBodies": compact_bodies,
        "n": int(shape.shape[0]),
        "pcs": pcs,
        "metricFits": {key: _fit(shape, func_raw[:, i]) for i, key in enumerate(_METRICS)
                       if key in _TRAVEL or key == "variance_mean"},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harvest", required=True, action="append", type=Path, dest="harvests")
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--compact-bodies", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    reference = _reference_loadings(args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for harvest in args.harvests:
            row = survey_harvest(harvest.resolve(), reference=reference,
                                 compact_bodies=args.compact_bodies)
            handle.write(json.dumps(row) + "\n")
            fits = "  ".join(f"{k}={v['r2']:.2f}" for k, v in row["metricFits"].items())
            print(f"{harvest.parent.name} n={row['n']}  {fits}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
