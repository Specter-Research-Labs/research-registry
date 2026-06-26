"""Bhattacharya-style landscape panels (after Bhattacharya et al., BMC Syst Biol 2011, Fig 3-4).

Per rule, two linked views of the computed Waddington landscape:
  - a 3D quasi-potential surface (U = -log p) with the creature population sitting in its valleys,
    coloured by which basin (attractor) each creature falls into;
  - a top-down projection with filled potential contours, the drift-field streamlines (development
    flowing downhill), dashed basin boundaries, and the % occupancy of each basin.

Rows are the four rules (the analogue of the paper's parameter sweep). Reads the precomputed
landscapes.npz and pulls terminal populations from the study warehouse.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np

from .ingest import STUDY_MAP_PATH
from .landscape import GRID, RESULT_PATH, SUMMARY_PATH, find_basins, load_config_trajectories
from .study import CONFIGS, FIGURES_DIR, STUDY_ROOT, WAREHOUSE_DB

TOP_BASINS = 3
BASIN_MIN_SEP = 0.8  # PC-space distance below which two maxima are merged into one attractor
SCATTER_CAP = 500
OUT = FIGURES_DIR / "landscape_panels.png"
SUMMARY = STUDY_ROOT / "landscape_panels.json"


def _dedupe_basins(basins: list[dict], k: int) -> list[dict]:
    kept: list[dict] = []
    for b in basins:  # find_basins returns mass-descending order
        p = np.array([b["pc1"], b["pc2"]])
        if all(np.hypot(*(p - np.array([q["pc1"], q["pc2"]]))) > BASIN_MIN_SEP for q in kept):
            kept.append(b)
        if len(kept) >= k:
            break
    return kept


def _terminal_coords(conn, study_id, mean, std, comps) -> np.ndarray:
    trajs = load_config_trajectories(conn, study_id)
    term = np.array([t["axes"][-1] for t in trajs])
    return ((term - mean) / std) @ comps.T


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt

    d = np.load(RESULT_PATH)
    ex, ey = d["edges_x"], d["edges_y"]
    cx = 0.5 * (ex[:-1] + ex[1:])
    cy = 0.5 * (ey[:-1] + ey[1:])
    mesh_x, mesh_y = np.meshgrid(cx, cy)  # (GRID, GRID) indexed [y, x]
    mean, std, comps = d["mean"], d["std"], d["components"]
    study_map = json.loads(STUDY_MAP_PATH.read_text())
    flux = {h: c["flux_fraction"]
            for h, c in json.loads(SUMMARY_PATH.read_text())["configs"].items()}
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")

    colors = plt.cm.tab10(np.linspace(0, 1, TOP_BASINS))
    fig = plt.figure(figsize=(15, 5.2 * len(CONFIGS)))
    label_field_pts = np.stack([mesh_x, mesh_y], axis=-1)  # (GRID, GRID, 2)

    rng = np.random.RandomState(0)
    summary = {}
    for r, cfg in enumerate(CONFIGS):
        h = cfg.config_hash
        u = d[f"u_drift_{h}"]  # Hodge gradient quasi-potential (NaN outside the visited region)
        p = d[f"p_terminal_{h}"]
        vx, vy = d[f"vx_{h}"], d[f"vy_{h}"]
        basins = _dedupe_basins(find_basins(p, ex, ey), TOP_BASINS)
        bxy = np.array([[b["pc1"], b["pc2"]] for b in basins])
        coords = _terminal_coords(conn, study_map[h], mean, std, comps)
        assign = np.argmin(np.linalg.norm(coords[:, None, :] - bxy[None, :, :], axis=2), axis=1)
        occ_pct = [100.0 * (assign == i).mean() for i in range(len(basins))]
        finite = u[np.isfinite(u)]
        lo, hi = np.percentile(finite, 2), np.percentile(finite, 98)
        uc = np.clip(u, lo, hi)
        xl = np.percentile(coords[:, 0], [1, 99])
        yl = np.percentile(coords[:, 1], [1, 99])
        sub = rng.choice(len(coords), min(SCATTER_CAP, len(coords)), replace=False)

        ax = fig.add_subplot(len(CONFIGS), 2, 2 * r + 1, projection="3d")
        ax.plot_surface(mesh_x, mesh_y, uc.T, cmap="viridis", alpha=0.85, linewidth=0,
                        antialiased=True, rcount=GRID, ccount=GRID)
        gi = np.clip(np.digitize(coords[:, 0], ex) - 1, 0, GRID - 1)
        gj = np.clip(np.digitize(coords[:, 1], ey) - 1, 0, GRID - 1)
        zc = np.nan_to_num(uc[gi, gj], nan=lo) + (hi - lo) * 0.03
        for i in range(len(basins)):
            m = (assign == i)[sub]
            ax.scatter(coords[sub][m, 0], coords[sub][m, 1], zc[sub][m], s=8, color=colors[i],
                       depthshade=False)
        ax.set(xlim=xl, ylim=yl, xlabel="PC1", ylabel="PC2", zlabel="quasi-potential")
        ax.set_title(f"{cfg.label}   flux={flux[h]:.2f}", fontsize=11)
        ax.view_init(elev=40, azim=-58)

        ax2 = fig.add_subplot(len(CONFIGS), 2, 2 * r + 2)
        ax2.contourf(cx, cy, uc.T, levels=20, cmap="viridis")
        ax2.contour(cx, cy, uc.T, levels=20, colors="k", linewidths=0.25, alpha=0.3)
        ax2.streamplot(cx, cy, vx.T, vy.T, color="0.85", density=0.8, linewidth=0.5, arrowsize=0.7)
        for i in range(len(basins)):
            m = assign == i
            ax2.scatter(coords[m, 0], coords[m, 1], s=4, color=colors[i], alpha=0.45, lw=0)
        labels = np.argmin(
            np.linalg.norm(label_field_pts[:, :, None, :] - bxy[None, None, :, :], axis=3), axis=2
        )
        ax2.contour(cx, cy, labels, levels=np.arange(len(basins)) + 0.5,
                    colors="yellow", linewidths=1.0, linestyles="--")
        for i, b in enumerate(basins):
            ax2.scatter([b["pc1"]], [b["pc2"]], marker="*", s=220, color=colors[i],
                        edgecolor="k", linewidth=0.7, zorder=5)
            ax2.annotate(f"{occ_pct[i]:.0f}%", (b["pc1"], b["pc2"]), color="w", weight="bold",
                         fontsize=11, ha="center", va="bottom", zorder=6,
                         path_effects=[pe.withStroke(linewidth=2.5, foreground="k")])
        ax2.set(xlim=xl, ylim=yl, xlabel="PC1", ylabel="PC2")
        ax2.set_title(f"{cfg.label}: basins, drift flow, occupancy", fontsize=11)
        summary[cfg.label] = {
            "flux_fraction": round(float(flux[h]), 3),
            "n_terminal": int(len(coords)),
            "basins": [{"pc1": round(float(b["pc1"]), 3), "pc2": round(float(b["pc2"]), 3),
                        "occupancy_pct": round(occ_pct[i], 1)} for i, b in enumerate(basins)],
        }

    fig.suptitle("Computed Waddington landscape per rule: 3D quasi-potential with population "
                 "(left), top-down basins + drift flow + occupancy (right)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.99])
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {OUT} and {SUMMARY}")
    for label, s in summary.items():
        occ = " ".join(f"{b['occupancy_pct']:.0f}%" for b in s["basins"])
        print(f"  {label}: flux={s['flux_fraction']} basins[{occ}]")
