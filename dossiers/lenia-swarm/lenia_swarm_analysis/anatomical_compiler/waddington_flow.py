"""The dynamic Waddington landscape, built from developmental trajectories.

The endpoint landscape can only show where creatures end up. With per-step
trajectories we can show the flow: every creature's path through morphospace as it
develops, the valleys it settles into (basins), and whether it actually rolls
downhill (does the developmental drift follow the negative gradient of the
potential, the Waddington picture).

This is the forward face of the same map the anatomical compiler inverts. A basin
here is the image of a compiler fiber: the set of genotypes whose creatures flow
into this valley.

Input is the trajectory JSONL from `trajectory_dataset`. Output is a JSON summary
and a self-contained SVG of the landscape with its drift field.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter

from lenia_swarm_analysis.morphospace.common_morphology import AXIS_IDS

GRID = 48


def _load(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (points, displacements, is_terminal) over all trajectory steps.

    points[i] is one step's 12 axes; displacements[i] is the move to the next step
    in the same trajectory (zero at the last step); is_terminal marks last steps.
    """
    points: list[list[float]] = []
    displacements: list[list[float]] = []
    terminal: list[bool] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            steps = json.loads(line)["path"]
            vectors = [[float(step["axes"][axis]) for axis in AXIS_IDS] for step in steps]
            for index, vector in enumerate(vectors):
                points.append(vector)
                if index + 1 < len(vectors):
                    displacements.append(
                        [b - a for a, b in zip(vector, vectors[index + 1], strict=True)]
                    )
                    terminal.append(False)
                else:
                    displacements.append([0.0] * len(vector))
                    terminal.append(True)
    return (
        np.asarray(points, dtype=np.float64),
        np.asarray(displacements, dtype=np.float64),
        np.asarray(terminal, dtype=bool),
    )


def _grid_index(coords: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    span = np.where(hi - lo > 1e-9, hi - lo, 1.0)
    cells = ((coords - lo) / span * (GRID - 1)).astype(np.int64)
    return np.clip(cells, 0, GRID - 1)


def run(path: Path) -> dict[str, Any]:
    points, displacements, terminal = _load(path)
    mean = points.mean(axis=0)
    std = points.std(axis=0)
    std[std < 1e-8] = 1.0
    standardized = (points - mean) / std

    centered = standardized - standardized.mean(axis=0)
    _, singular, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:2]
    variance = (singular**2) / float(np.sum(singular**2))
    coords = centered @ components.T
    drift = (displacements / std) @ components.T

    lo, hi = coords.min(axis=0), coords.max(axis=0)
    cells = _grid_index(coords, lo, hi)

    density = np.zeros((GRID, GRID), dtype=np.float64)
    np.add.at(density, (cells[:, 0], cells[:, 1]), 1.0)
    density = gaussian_filter(density, sigma=1.2)
    potential = -np.log(density + density[density > 0].min() * 0.5)

    drift_x = np.zeros((GRID, GRID))
    drift_y = np.zeros((GRID, GRID))
    drift_n = np.zeros((GRID, GRID))
    moving = ~terminal
    np.add.at(drift_x, (cells[moving, 0], cells[moving, 1]), drift[moving, 0])
    np.add.at(drift_y, (cells[moving, 0], cells[moving, 1]), drift[moving, 1])
    np.add.at(drift_n, (cells[moving, 0], cells[moving, 1]), 1.0)
    with np.errstate(invalid="ignore"):
        mean_drift_x = np.where(drift_n > 0, drift_x / drift_n, 0.0)
        mean_drift_y = np.where(drift_n > 0, drift_y / drift_n, 0.0)

    grad_y, grad_x = np.gradient(gaussian_filter(potential, sigma=1.0))
    mask = drift_n >= 3
    flow = np.stack([mean_drift_x[mask], mean_drift_y[mask]], axis=1)
    downhill = np.stack([-grad_x[mask], -grad_y[mask]], axis=1)
    flow_norm = np.linalg.norm(flow, axis=1)
    downhill_norm = np.linalg.norm(downhill, axis=1)
    good = (flow_norm > 1e-9) & (downhill_norm > 1e-9)
    cosines = np.sum(flow[good] * downhill[good], axis=1) / (flow_norm[good] * downhill_norm[good])
    alignment = float(np.mean(cosines))

    terminal_cells = cells[terminal]
    endpoint_density = np.zeros((GRID, GRID))
    np.add.at(endpoint_density, (terminal_cells[:, 0], terminal_cells[:, 1]), 1.0)
    endpoint_density = gaussian_filter(endpoint_density, sigma=1.2)
    basins = _peaks(endpoint_density)

    axis_loadings = {
        AXIS_IDS[i]: [float(components[0, i]), float(components[1, i])]
        for i in range(len(AXIS_IDS))
    }
    return {
        "trajectoryPoints": int(points.shape[0]),
        "pc1Variance": float(variance[0]),
        "pc2Variance": float(variance[1]),
        "flowDownhillAlignment": alignment,
        "basinCount": len(basins),
        "basins": [
            {"pc1": float(b[0]), "pc2": float(b[1]), "weight": float(b[2])} for b in basins
        ],
        "axisLoadings": axis_loadings,
        "_render": {
            "coords": coords, "lo": lo, "hi": hi, "potential": potential,
            "driftx": mean_drift_x, "drifty": mean_drift_y, "driftn": drift_n,
            "terminal_coords": coords[terminal],
        },
    }


def _peaks(field: np.ndarray) -> list[tuple[float, float, float]]:
    peaks: list[tuple[int, int, float]] = []
    for i in range(1, GRID - 1):
        for j in range(1, GRID - 1):
            window = field[i - 1 : i + 2, j - 1 : j + 2]
            if field[i, j] == window.max() and field[i, j] > field.mean() + field.std():
                peaks.append((i, j, float(field[i, j])))
    peaks.sort(key=lambda p: -p[2])
    out: list[tuple[float, float, float]] = []
    for i, j, w in peaks[:8]:
        out.append((i / (GRID - 1), j / (GRID - 1), w))
    return out


def _svg(report: dict[str, Any]) -> str:
    r = report["_render"]
    lo, hi = r["lo"], r["hi"]
    potential = r["potential"]
    driftx = r["driftx"]
    drifty = r["drifty"]
    driftn = r["driftn"]
    width = 720
    height = 720
    pad = 30
    pw = width - 2 * pad
    ph = height - 2 * pad

    def sx(gx: float) -> float:
        return pad + gx / (GRID - 1) * pw

    def sy(gy: float) -> float:
        return pad + (1 - gy / (GRID - 1)) * ph

    finite = potential[np.isfinite(potential)]
    pmin, pmax = float(finite.min()), float(finite.max())
    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="-apple-system,Segoe UI,Roboto,sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#0f1115"/>',
    ]
    cw = pw / GRID + 0.6
    ch = ph / GRID + 0.6
    for i in range(GRID):
        for j in range(GRID):
            u = potential[i, j]
            t = (u - pmin) / (pmax - pmin + 1e-9)
            valley = 1 - t
            red = int(30 + valley * 90)
            green = int(40 + valley * 150)
            blue = int(70 + valley * 170)
            parts.append(
                f'<rect x="{sx(i)-cw/2:.1f}" y="{sy(j)-ch/2:.1f}" '
                f'width="{cw:.1f}" height="{ch:.1f}" fill="rgb({red},{green},{blue})"/>'
            )
    dmax = float(np.max(np.sqrt(driftx**2 + drifty**2)) + 1e-9)
    for i in range(0, GRID, 2):
        for j in range(0, GRID, 2):
            if driftn[i, j] < 3:
                continue
            dx = driftx[i, j] / dmax
            dy = drifty[i, j] / dmax
            x0 = sx(i)
            y0 = sy(j)
            x1 = x0 + dx * 13
            y1 = y0 - dy * 13
            parts.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                f'stroke="#cfe6ff" stroke-width="1.1" opacity="0.55"/>'
            )
    for coord in r["terminal_coords"]:
        gx = (coord[0] - lo[0]) / (hi[0] - lo[0] + 1e-9) * (GRID - 1)
        gy = (coord[1] - lo[1]) / (hi[1] - lo[1] + 1e-9) * (GRID - 1)
        parts.append(
            f'<circle cx="{sx(gx):.1f}" cy="{sy(gy):.1f}" r="2.4" '
            f'fill="#ffcf6b" opacity="0.85"/>'
        )
    for b in report["basins"]:
        gx = b["pc1"] * (GRID - 1)
        gy = b["pc2"] * (GRID - 1)
        parts.append(
            f'<circle cx="{sx(gx):.1f}" cy="{sy(gy):.1f}" r="9" '
            f'fill="none" stroke="#ff7a7a" stroke-width="2"/>'
        )
    parts.append(
        f'<text x="{pad}" y="20" fill="#aab2c0" font-size="13">Dynamic Waddington landscape '
        f'(valleys bright, arrows = developmental drift, yellow = where trajectories end, '
        f'red rings = basins). flow-downhill alignment {report["flowDownhillAlignment"]:.2f}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trajectories",
        default="outputs/anatomical-compiler/trajectories_3k_1c_128.jsonl",
    )
    parser.add_argument("--output", default="outputs/anatomical-compiler/waddington_flow.json")
    parser.add_argument("--svg", default="generated/waddington-landscape.svg")
    args = parser.parse_args(argv)

    root = Path.cwd()
    path = (root / args.trajectories).resolve()
    if not path.is_file():
        raise SystemExit(f"Missing trajectories: {path}")
    report = run(path)
    svg = _svg(report)
    render = report.pop("_render")
    del render

    output_path = (root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    svg_path = (root / args.svg).resolve()
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")

    print(f"trajectory points: {report['trajectoryPoints']}")
    print(f"PC1/PC2 variance:  {report['pc1Variance']:.2f} / {report['pc2Variance']:.2f}")
    print(f"basins found:      {report['basinCount']}")
    print(f"flow rolls downhill (alignment, 1=perfect): {report['flowDownhillAlignment']:.2f}")
    print(f"wrote {args.output} and {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
