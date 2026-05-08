from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

from . import paths


@dataclass(frozen=True)
class CorrelationCell:
    roi: str
    axis: str
    pearson_r: float


@dataclass(frozen=True)
class CorrelationReport:
    n_specimens: int
    rois: list[str]
    axes: list[str]
    cells: list[CorrelationCell]

    def max_per_roi(self) -> dict[str, CorrelationCell]:
        out: dict[str, CorrelationCell] = {}
        for cell in self.cells:
            cur = out.get(cell.roi)
            if cur is None or abs(cell.pearson_r) > abs(cur.pearson_r):
                out[cell.roi] = cell
        return out

    def to_json(self) -> str:
        return json.dumps(
            {
                "n_specimens": self.n_specimens,
                "rois": self.rois,
                "axes": self.axes,
                "cells": [
                    {"roi": c.roi, "axis": c.axis, "pearson_r": c.pearson_r} for c in self.cells
                ],
            },
            indent=2,
            sort_keys=True,
        )


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson r on two 1-D float arrays.

    invariant: returns 0.0 (with no division-by-zero) when either column is constant,
    because correlation is undefined there. The caller can detect zero-variance columns
    via the n_specimens count and the descriptor matrix it built.
    """
    x = x.astype(np.float64)
    y = y.astype(np.float64)
    xm = x - x.mean()
    ym = y - y.mean()
    denom = float(np.sqrt((xm * xm).sum() * (ym * ym).sum()))
    if denom == 0.0:
        return 0.0
    return float((xm * ym).sum() / denom)


def correlate(overlay_path: Path) -> CorrelationReport:
    raw: object = json.loads(overlay_path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"overlay {overlay_path} root must be an object")
    payload = cast(dict[str, object], raw)
    rois_obj = payload.get("rois")
    rows_obj = payload.get("rows")
    if not isinstance(rois_obj, list) or not isinstance(rows_obj, list):
        raise ValueError(f"overlay {overlay_path} must have list 'rois' and 'rows'")
    rois = [str(r) for r in rois_obj]
    if len(rows_obj) < 4:
        raise ValueError(
            f"overlay {overlay_path} has only {len(rows_obj)} linked rows; "
            "need at least 4 to compute a meaningful correlation"
        )
    typed_rows: list[dict[str, object]] = []
    for r in rows_obj:
        if not isinstance(r, dict):
            raise ValueError(f"overlay {overlay_path} contains non-object row")
        typed_rows.append(cast(dict[str, object], r))

    first_axes = typed_rows[0].get("descriptor_axes")
    if not isinstance(first_axes, dict):
        raise ValueError(f"overlay {overlay_path}: row missing 'descriptor_axes' object")
    axes = sorted(str(k) for k in cast(dict[str, object], first_axes).keys())

    n = len(typed_rows)
    roi_matrix = np.zeros((n, len(rois)), dtype=np.float64)
    axis_matrix = np.zeros((n, len(axes)), dtype=np.float64)
    for i, row in enumerate(typed_rows):
        roi_scores = row.get("roi_scores")
        descriptor_axes = row.get("descriptor_axes")
        if not isinstance(roi_scores, dict) or not isinstance(descriptor_axes, dict):
            raise ValueError(f"overlay row {i} missing roi_scores or descriptor_axes")
        roi_dict = cast(dict[str, object], roi_scores)
        axis_dict = cast(dict[str, object], descriptor_axes)
        for j, roi in enumerate(rois):
            if roi not in roi_dict:
                raise KeyError(f"overlay row {i} missing roi {roi!r}")
            roi_matrix[i, j] = float(roi_dict[roi])  # ty: ignore[invalid-argument-type]
        for k, axis in enumerate(axes):
            if axis not in axis_dict:
                raise KeyError(f"overlay row {i} missing axis {axis!r}")
            axis_matrix[i, k] = float(axis_dict[axis])  # ty: ignore[invalid-argument-type]

    cells: list[CorrelationCell] = []
    for j, roi in enumerate(rois):
        for k, axis in enumerate(axes):
            r = _pearson(roi_matrix[:, j], axis_matrix[:, k])
            cells.append(CorrelationCell(roi=roi, axis=axis, pearson_r=r))

    return CorrelationReport(n_specimens=n, rois=rois, axes=axes, cells=cells)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pearson-correlate each ROI score with each lenia_terminal_v1 axis "
            "to check whether the TRIBE score is redundant or new."
        )
    )
    parser.add_argument("--overlay-report", type=Path, required=True)
    parser.add_argument(
        "--redundancy-threshold",
        type=float,
        default=0.85,
        help="abs(r) above this against any axis flags the ROI as redundant.",
    )
    args = parser.parse_args(argv)

    report = correlate(args.overlay_report)
    out_dir = paths.ensure(paths.artifact_root() / "correlations")
    stem = args.overlay_report.stem
    out = out_dir / f"{stem}.correlation.json"
    out.write_text(report.to_json())

    header = ["roi", *report.axes]
    print("\t".join(header))
    by_roi: dict[str, dict[str, float]] = {}
    for cell in report.cells:
        by_roi.setdefault(cell.roi, {})[cell.axis] = cell.pearson_r
    for roi in report.rois:
        cells = [roi]
        for axis in report.axes:
            cells.append(f"{by_roi[roi][axis]:+.3f}")
        print("\t".join(cells))

    print(f"\ncorrelation report: {out}")
    print(f"n_specimens: {report.n_specimens}")
    print()
    verdict_lines: list[str] = []
    for roi, top in report.max_per_roi().items():
        tag = "REDUNDANT" if abs(top.pearson_r) >= args.redundancy_threshold else "candidate-new"
        verdict_lines.append(
            f"  {roi:<12} top axis: {top.axis:<24} r={top.pearson_r:+.3f}  {tag}"
        )
    print("verdict (per-ROI top correlation):")
    for line in verdict_lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
