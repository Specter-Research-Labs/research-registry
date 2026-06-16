"""Compute Waddington landscapes from the ingested per-step development traces.

For each rule config we read the per-step terminal descriptors, recompute the canonical 16 terminal
axes per step (so the dynamic trajectory lives in the same morphospace as the endpoint analysis),
embed every step in a 2D PCA basis shared across all four configs, then per config build:
  - the endpoint potential U = -log p over terminal states,
  - the drift field v(x) = E[dx/dt | x] and its Helmholtz-Hodge split into a gradient landscape
    plus a divergence-free flux (the circulation a scalar landscape cannot represent),
  - basin maxima of the terminal density.
The shared basis makes the four landscapes and their endpoint/dynamic views directly comparable.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np

from ..transformation_metrics import (
    TERMINAL_AXIS_IDS,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from .ingest import STUDY_MAP_PATH
from .study import CONFIGS, STUDY_ROOT, WAREHOUSE_DB

GRID = 64
SMOOTH_SIGMA = 1.4
RESULT_PATH = STUDY_ROOT / "landscapes.npz"
SUMMARY_PATH = STUDY_ROOT / "landscape_summary.json"


def _torus_velocity(cx: list[float], cy: list[float], steps: list[int], n: float) -> list[float]:
    speeds = [0.0]
    for i in range(1, len(cx)):
        dx = abs(cx[i] - cx[i - 1])
        dy = abs(cy[i] - cy[i - 1])
        dx = min(dx, n - dx)
        dy = min(dy, n - dy)
        speeds.append(float(np.hypot(dx, dy) / max(steps[i] - steps[i - 1], 1)))
    return speeds


def load_config_trajectories(conn: duckdb.DuckDBPyConnection, study_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT ds.specimen_id, ds.step, ds.center_x, ds.center_y, ds.width,
               ds.terminal_descriptor_json
        FROM development_samples ds
        JOIN study_specimens ss USING (specimen_id)
        WHERE ss.study_id = ?
        ORDER BY ds.specimen_id, ds.step
        """,
        [study_id],
    ).fetchall()
    by_specimen: dict[str, list] = {}
    for sid, step, cx, cy, width, terminal_json in rows:
        by_specimen.setdefault(sid, []).append(
            (int(step), float(cx), float(cy), int(width), terminal_json)
        )

    trajectories = []
    for sid, samples in by_specimen.items():
        if len(samples) < 3:
            continue
        samples.sort(key=lambda r: r[0])
        steps = [s[0] for s in samples]
        cxs = [s[1] for s in samples]
        cys = [s[2] for s in samples]
        grid_n = float(samples[0][3])
        speeds = _torus_velocity(cxs, cys, steps, grid_n)
        axes_seq = []
        for k, sample in enumerate(samples):
            terminal = json.loads(sample[4])
            raw = extract_terminal_raw_axes_from_descriptors(
                terminal=terminal,
                trajectory={"centerVelocity": speeds[k], "pathTortuosity": 0.0},
                specimen_id=sid,
            )
            transformed = transform_axes(raw)
            axes_seq.append([float(transformed[a]) for a in TERMINAL_AXIS_IDS])
        trajectories.append({"id": sid, "steps": steps, "axes": np.array(axes_seq)})
    return trajectories


def gaussian_kernel(sigma: float) -> np.ndarray:
    radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(x**2) / (2 * sigma**2))
    return k / k.sum()


def smooth2d(grid: np.ndarray, sigma: float) -> np.ndarray:
    k = gaussian_kernel(sigma)
    out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, grid)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, out)


def hodge_decompose(vx: np.ndarray, vy: np.ndarray, occ: np.ndarray) -> tuple[np.ndarray, float]:
    """Edge-space Hodge split: fit gradient field -B u to the edge-projected velocity f. The split
    is orthogonal, so flux fraction = lsqr residual / ||f|| lies in [0, 1]. Returns (U, flux)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import lsqr

    g = vx.shape[0]
    idx = -np.ones((g, g), dtype=int)
    cells = np.argwhere(occ)
    for n, (i, j) in enumerate(cells):
        idx[i, j] = n
    n_cells = len(cells)
    e_rows: list[int] = []
    e_cols: list[int] = []
    e_data: list[float] = []
    f: list[float] = []
    e = 0
    for i, j in cells:
        a = idx[i, j]
        if i + 1 < g and occ[i + 1, j]:
            e_rows += [e, e]
            e_cols += [a, idx[i + 1, j]]
            e_data += [-1.0, 1.0]
            f.append(0.5 * (vx[i, j] + vx[i + 1, j]))
            e += 1
        if j + 1 < g and occ[i, j + 1]:
            e_rows += [e, e]
            e_cols += [a, idx[i, j + 1]]
            e_data += [-1.0, 1.0]
            f.append(0.5 * (vy[i, j] + vy[i, j + 1]))
            e += 1
    if e == 0:
        return np.full((g, g), np.nan), 0.0
    incidence = coo_matrix((e_data, (e_rows, e_cols)), shape=(e, n_cells)).tocsr()
    f_arr = np.array(f)
    result = lsqr(incidence, -f_arr, atol=1e-11, btol=1e-11, iter_lim=10000)
    u_vec = result[0] - result[0].mean()
    flux_fraction = float(result[3] / (np.linalg.norm(f_arr) + 1e-12))
    u = np.full((g, g), np.nan)
    for n, (i, j) in enumerate(cells):
        u[i, j] = u_vec[n]
    return u, flux_fraction


def find_basins(p: np.ndarray, ex: np.ndarray, ey: np.ndarray) -> list[dict]:
    cx = 0.5 * (ex[:-1] + ex[1:])
    cy = 0.5 * (ey[:-1] + ey[1:])
    thresh = p.max() * 0.05
    basins = []
    for i in range(1, p.shape[0] - 1):
        for j in range(1, p.shape[1] - 1):
            value = p[i, j]
            if value < thresh:
                continue
            if value >= p[i - 1 : i + 2, j - 1 : j + 2].max():
                basins.append({"pc1": float(cx[i]), "pc2": float(cy[j]), "mass": float(value)})
    basins.sort(key=lambda b: b["mass"], reverse=True)
    return basins


def _grid_cell(value: float, edges: np.ndarray) -> int:
    return int(np.clip(np.digitize(value, edges) - 1, 0, GRID - 1))


def build() -> None:
    mapping = json.loads(STUDY_MAP_PATH.read_text())
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")

    per_config = {}
    for config in CONFIGS:
        trajectories = load_config_trajectories(conn, mapping[config.config_hash])
        per_config[config.config_hash] = trajectories
        print(f"{config.label}: {len(trajectories)} trajectories")

    terminal_rows = [t["axes"][-1] for trajs in per_config.values() for t in trajs]
    terminal_matrix = np.array(terminal_rows)
    mean = terminal_matrix.mean(0)
    std = terminal_matrix.std(0)
    std[std == 0] = 1.0
    z = (terminal_matrix - mean) / std
    _, singular, vt = np.linalg.svd(z, full_matrices=False)
    comps = vt[:2]
    var_ratio = (singular**2 / (singular**2).sum())[:2]
    all_term_coords = z @ comps.T
    qx = np.percentile(all_term_coords[:, 0], [1, 99])
    qy = np.percentile(all_term_coords[:, 1], [1, 99])
    ex = np.linspace(qx[0], qx[1], GRID + 1)
    ey = np.linspace(qy[0], qy[1], GRID + 1)
    print(f"shared basis explained variance: {[round(float(x), 3) for x in var_ratio]}")

    saved = {"edges_x": ex, "edges_y": ey, "components": comps, "mean": mean, "std": std}
    summary = {
        "explained_variance_ratio": [float(x) for x in var_ratio],
        "pc1_loadings": {
            TERMINAL_AXIS_IDS[i]: float(comps[0, i]) for i in range(len(TERMINAL_AXIS_IDS))
        },
        "pc2_loadings": {
            TERMINAL_AXIS_IDS[i]: float(comps[1, i]) for i in range(len(TERMINAL_AXIS_IDS))
        },
        "configs": {},
    }

    for config in CONFIGS:
        trajs = per_config[config.config_hash]
        coords_seq = [((t["axes"] - mean) / std) @ comps.T for t in trajs]
        all_pts = np.vstack(coords_seq)
        term_pts = np.array([c[-1] for c in coords_seq])

        vx = np.zeros((GRID, GRID))
        vy = np.zeros((GRID, GRID))
        cnt = np.zeros((GRID, GRID))
        for c in coords_seq:
            for k in range(len(c) - 1):
                gi = _grid_cell(c[k, 0], ex)
                gj = _grid_cell(c[k, 1], ey)
                delta = c[k + 1] - c[k]
                vx[gi, gj] += delta[0]
                vy[gi, gj] += delta[1]
                cnt[gi, gj] += 1
        occ = cnt > 0
        vx[occ] /= cnt[occ]
        vy[occ] /= cnt[occ]
        vx = smooth2d(vx, SMOOTH_SIGMA)
        vy = smooth2d(vy, SMOOTH_SIGMA)
        u_drift, flux_fraction = hodge_decompose(vx, vy, occ)

        hist_term, _, _ = np.histogram2d(term_pts[:, 0], term_pts[:, 1], bins=[ex, ey])
        p_term = smooth2d(hist_term, SMOOTH_SIGMA)
        p_term /= p_term.sum()
        u_endpoint = -np.log(p_term + p_term[p_term > 0].min() * 1e-3)
        basins = find_basins(p_term, ex, ey)

        h = config.config_hash
        saved[f"u_drift_{h}"] = u_drift
        saved[f"u_endpoint_{h}"] = u_endpoint
        saved[f"p_terminal_{h}"] = p_term
        saved[f"vx_{h}"] = vx
        saved[f"vy_{h}"] = vy
        saved[f"occ_{h}"] = occ
        summary["configs"][h] = {
            "label": config.label,
            "n_trajectories": len(trajs),
            "n_points": int(all_pts.shape[0]),
            "flux_fraction": flux_fraction,
            "n_basins": len(basins),
            "basins": basins[:8],
        }
        print(f"{config.label}: flux_fraction={flux_fraction:.3f}, basins={len(basins)}")

    np.savez_compressed(RESULT_PATH, **saved)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    print(f"wrote {RESULT_PATH} and {SUMMARY_PATH}")


if __name__ == "__main__":
    build()
