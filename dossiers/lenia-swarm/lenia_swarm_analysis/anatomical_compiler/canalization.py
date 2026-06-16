"""Canalization, measured from developmental trajectories.

Run one genotype from several different initial conditions and watch the shape
trajectories. If they fan out early and then funnel to the same morphology, the
genotype is canalized: it builds the same body regardless of where it started. That
convergence is exactly a Waddington basin, and it is the trajectory-level version of
the Stage 2 finding that a creature's shape is set by its genotype while its motion
is set by where it started.

Input is the canalization JSONL from `trajectory_dataset --canalization`. We report,
per genotype, how the across-initial-condition spread of the 12 shape axes shrinks
over developmental time, and we contrast the terminal robustness of shape metrics
against motion metrics.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from lenia_swarm_analysis.morphospace.common_morphology import AXIS_IDS

SHAPE_METRICS = ("gyration", "occupancy_mean", "mass_mean")
MOTION_METRICS = ("displacement", "speed_mean", "center_velocity")


def _coefficient_of_variation(values: list[float]) -> float | None:
    array = np.asarray([v for v in values if v is not None], dtype=np.float64)
    if array.size < 2 or abs(float(np.mean(array))) < 1e-12:
        return None
    return float(np.std(array) / abs(np.mean(array)))


def run(path: Path) -> dict[str, Any]:
    by_genotype: dict[int, list[dict[str, Any]]] = defaultdict(list)
    all_axis_rows: list[list[float]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            by_genotype[record["genotypeIndex"]].append(record)
            for step in record["path"]:
                all_axis_rows.append([float(step["axes"][axis]) for axis in AXIS_IDS])

    axis_matrix = np.asarray(all_axis_rows, dtype=np.float64)
    axis_std = axis_matrix.std(axis=0)
    axis_std[axis_std < 1e-8] = 1.0

    per_genotype: list[dict[str, Any]] = []
    spread_curves: list[list[float]] = []
    for genotype_index, runs in sorted(by_genotype.items()):
        by_step: dict[int, list[np.ndarray]] = defaultdict(list)
        for record in runs:
            for step in record["path"]:
                vector = np.asarray(
                    [float(step["axes"][axis]) for axis in AXIS_IDS], dtype=np.float64
                )
                by_step[step["step"]].append(vector / axis_std)
        steps = sorted(s for s, vs in by_step.items() if len(vs) >= 2)
        spread = [float(np.mean(np.std(np.stack(by_step[s], axis=0), axis=0))) for s in steps]
        if len(spread) >= 2:
            spread_curves.append(spread)
        early = float(np.mean(spread[: max(1, len(spread) // 3)])) if spread else None
        late = float(np.mean(spread[-max(1, len(spread) // 3):])) if spread else None
        canalization_ratio = (
            late / early if early is not None and late is not None and early > 1e-9 else None
        )

        terminals = [record["terminal"] for record in runs]
        shape_cv = [
            _coefficient_of_variation([t.get(m) for t in terminals]) for m in SHAPE_METRICS
        ]
        motion_cv = [
            _coefficient_of_variation([t.get(m) for t in terminals]) for m in MOTION_METRICS
        ]
        per_genotype.append({
            "genotypeIndex": genotype_index,
            "initialConditions": len(runs),
            "spreadEarly": early,
            "spreadLate": late,
            "canalizationRatio": canalization_ratio,
            "shapeCv": _mean_or_none(shape_cv),
            "motionCv": _mean_or_none(motion_cv),
        })

    ratios = [g["canalizationRatio"] for g in per_genotype if g["canalizationRatio"] is not None]
    shape_cvs = [g["shapeCv"] for g in per_genotype if g["shapeCv"] is not None]
    motion_cvs = [g["motionCv"] for g in per_genotype if g["motionCv"] is not None]
    return {
        "genotypes": len(per_genotype),
        "meanCanalizationRatio": float(np.mean(ratios)) if ratios else None,
        "meanShapeCv": float(np.mean(shape_cvs)) if shape_cvs else None,
        "meanMotionCv": float(np.mean(motion_cvs)) if motion_cvs else None,
        "perGenotype": per_genotype,
        "_curves": spread_curves,
    }


def _mean_or_none(values: list[float | None]) -> float | None:
    finite = [v for v in values if v is not None]
    return float(np.mean(finite)) if finite else None


def _svg(report: dict[str, Any]) -> str:
    curves = report["_curves"]
    width = 640
    height = 360
    pad = 48
    pw = width - 2 * pad
    ph = height - 2 * pad
    max_len = max((len(c) for c in curves), default=1)
    all_vals = [v for c in curves for v in c]
    vmax = max(all_vals) if all_vals else 1.0
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="-apple-system,Segoe UI,Roboto,sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#0f1115"/>',
        f'<text x="{pad}" y="26" fill="#e8ebf0" font-size="15">Canalization: shape spread across '
        f'initial conditions, over developmental time</text>',
        f'<text x="{pad}" y="{height-12}" fill="#aab2c0" font-size="12">developmental step '
        f'(left = early, right = late)</text>',
    ]

    def px(i: int) -> float:
        return pad + (i / (max_len - 1 if max_len > 1 else 1)) * pw

    def py(v: float) -> float:
        return pad + (1 - v / (vmax + 1e-9)) * ph

    for curve in curves:
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(curve))
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="#7cc4ff" '
            f'stroke-width="1.6" opacity="0.6"/>'
        )
    shape_cv = report.get("meanShapeCv")
    motion_cv = report.get("meanMotionCv")
    if shape_cv is not None and motion_cv is not None:
        bar_x = width - 210
        scale = 150 / max(shape_cv, motion_cv, 1e-6)
        parts.append(
            f'<text x="{bar_x}" y="60" fill="#e8ebf0" font-size="13">terminal variation '
            f'across starts</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="74" width="{shape_cv*scale:.0f}" height="20" fill="#74e08a"/>'
            f'<text x="{bar_x}" y="110" fill="#74e08a" font-size="12">shape {shape_cv*100:.1f}% '
            f'(canalized)</text>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="124" width="{motion_cv*scale:.0f}" height="20" fill="#ff8a7a"/>'
            f'<text x="{bar_x}" y="160" fill="#ff8a7a" font-size="12">motion {motion_cv*100:.0f}% '
            f'(not canalized)</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="outputs/anatomical-compiler/canalization_3k_1c_128.jsonl",
    )
    parser.add_argument("--output", default="outputs/anatomical-compiler/canalization.json")
    parser.add_argument("--svg", default="generated/canalization.svg")
    args = parser.parse_args(argv)

    root = Path.cwd()
    path = (root / args.input).resolve()
    if not path.is_file():
        raise SystemExit(f"Missing canalization input: {path}")
    report = run(path)
    svg = _svg(report)
    report.pop("_curves")

    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    svg_path = (root / args.svg).resolve()
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")

    print(f"genotypes: {report['genotypes']}")
    print(f"mean canalization ratio (late/early spread, <1 = converging): "
          f"{report['meanCanalizationRatio']:.2f}")
    print(f"terminal shape CV  = {report['meanShapeCv']:.3f}  (canalized if small)")
    print(f"terminal motion CV = {report['meanMotionCv']:.3f}  (not canalized if large)")
    print(f"wrote {args.output} and {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
