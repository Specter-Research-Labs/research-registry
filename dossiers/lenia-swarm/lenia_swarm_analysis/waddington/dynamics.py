"""Dynamical structure of the developmental trajectories.

flux_behavior: the Helmholtz-Hodge flux is the circulation a scalar landscape cannot represent.
This tests where it lives: per cell we recover the solenoidal field (v + grad U) and per trajectory
its flux exposure, then correlate with motility (the locomotion axis) and pulsation (temporal std of
shape axes). The claim is that circulation concentrates in the motile / pulsing creatures.

trajectory_programs: cluster trajectories by the shape of their path through morphospace (not just
endpoint) into developmental "programs"/creodes, and characterize each.

Both run on the already-ingested harvest trajectories. Run with scipy + matplotlib available.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np

from ._common import AXIS, zscore
from .ingest import STUDY_MAP_PATH
from .landscape import GRID, RESULT_PATH, load_config_trajectories
from .study import CONFIGS, FIGURES_DIR, STUDY_ROOT, WAREHOUSE_DB

LOCO = AXIS["locomotion"]
COVERAGE = AXIS["coverage"]
COMPACT = AXIS["compactness"]
FRAG = AXIS["fragmentation"]
N_PROGRAMS = 5
PATH_RESAMPLE = 12

FLUX_SUMMARY = STUDY_ROOT / "flux_behavior.json"
PROGRAMS_SUMMARY = STUDY_ROOT / "trajectory_programs.json"


def _cell(value, edges):
    return int(np.clip(np.digitize(value, edges) - 1, 0, GRID - 1))


def _flux_field(vx, vy, u_drift, occ):
    """Solenoidal part of the drift field: flux = v - gradient_part = v + grad U (v ~ -grad U)."""
    u = np.where(np.isnan(u_drift), np.nanmean(u_drift[occ]) if occ.any() else 0.0, u_drift)
    dux = np.gradient(u, axis=0)
    duy = np.gradient(u, axis=1)
    fx = vx + dux
    fy = vy + duy
    mag = np.hypot(fx, fy)
    mag[~occ] = np.nan
    return mag


def _resample_path(coords: np.ndarray, n: int) -> np.ndarray:
    t = np.linspace(0, 1, len(coords))
    tt = np.linspace(0, 1, n)
    return np.column_stack([np.interp(tt, t, coords[:, d]) for d in range(coords.shape[1])])


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.cluster.vq import kmeans2
    from scipy.stats import spearmanr

    mapping = json.loads(STUDY_MAP_PATH.read_text())
    d = np.load(RESULT_PATH)
    mean, std, comps, ex, ey = d["mean"], d["std"], d["components"], d["edges_x"], d["edges_y"]
    extent = [ex[0], ex[-1], ey[0], ey[-1]]
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")

    flux_fig, flux_axes = plt.subplots(2, 2, figsize=(13, 11))
    prog_fig, prog_axes = plt.subplots(2, 2, figsize=(13, 11))
    flux_summary = {}
    prog_summary = {}

    for fax, pax, config in zip(flux_axes.ravel(), prog_axes.ravel(), CONFIGS, strict=True):
        h = config.config_hash
        trajs = load_config_trajectories(conn, mapping[h])
        coords_seq = [((t["axes"] - mean) / std) @ comps.T for t in trajs]
        flux_mag = _flux_field(d[f"vx_{h}"], d[f"vy_{h}"], d[f"u_drift_{h}"], d[f"occ_{h}"])

        # per-trajectory: flux exposure along path, motility, pulsation
        exposure, motility, pulsation = [], [], []
        motility_grid = np.full((GRID, GRID), np.nan)
        moto_acc = np.zeros((GRID, GRID))
        moto_cnt = np.zeros((GRID, GRID))
        for t, c in zip(trajs, coords_seq, strict=True):
            cells = [(_cell(p[0], ex), _cell(p[1], ey)) for p in c]
            fvals = [flux_mag[i, j] for i, j in cells if np.isfinite(flux_mag[i, j])]
            exposure.append(float(np.mean(fvals)) if fvals else np.nan)
            mot = float(np.mean(t["axes"][:, LOCO]))
            puls = float(np.std(t["axes"][:, COVERAGE]) + np.std(t["axes"][:, COMPACT]))
            motility.append(mot)
            pulsation.append(puls)
            for i, j in cells:
                moto_acc[i, j] += mot
                moto_cnt[i, j] += 1
        motility_grid[moto_cnt > 0] = moto_acc[moto_cnt > 0] / moto_cnt[moto_cnt > 0]

        exposure = np.array(exposure)
        motility = np.array(motility)
        pulsation = np.array(pulsation)
        ok = np.isfinite(exposure)
        r_mot, p_mot = spearmanr(exposure[ok], motility[ok])
        r_pul, p_pul = spearmanr(exposure[ok], pulsation[ok])
        flux_summary[config.label] = {
            "spearman_flux_vs_motility": round(float(r_mot), 3),
            "p_motility": float(f"{p_mot:.2e}"),
            "spearman_flux_vs_pulsation": round(float(r_pul), 3),
            "p_pulsation": float(f"{p_pul:.2e}"),
            "n": int(ok.sum()),
        }
        im = fax.imshow(
            np.ma.masked_invalid(flux_mag).T, origin="lower", extent=extent, aspect="auto",
            cmap="inferno",
        )
        fax.contour(
            np.linspace(ex[0], ex[-1], GRID), np.linspace(ey[0], ey[-1], GRID),
            np.ma.masked_invalid(motility_grid).T, levels=5, colors="cyan", linewidths=0.7,
            alpha=0.8,
        )
        fax.set_title(f"{config.label}: flux (heat) vs motility (cyan)  rho={r_mot:.2f}")
        fax.set_xlabel("PC1")
        fax.set_ylabel("PC2")
        flux_fig.colorbar(im, ax=fax, shrink=0.7)

        # trajectory programs: cluster resampled paths
        feats = np.array([_resample_path(c, PATH_RESAMPLE).flatten() for c in coords_seq])
        fz = zscore(feats)
        _, labels = kmeans2(fz, N_PROGRAMS, seed=0, minit="++", missing="warn")
        u_disp = np.ma.masked_invalid(d[f"u_endpoint_{h}"])
        pax.imshow(u_disp.T, origin="lower", extent=extent, aspect="auto", cmap="bone_r", alpha=0.5)
        colors = plt.cm.tab10(np.linspace(0, 1, N_PROGRAMS))
        clusters = []
        for k in range(N_PROGRAMS):
            members = np.where(labels == k)[0]
            if len(members) == 0:
                continue
            mean_path = np.mean(
                [_resample_path(coords_seq[m], PATH_RESAMPLE) for m in members], axis=0
            )
            pax.plot(mean_path[:, 0], mean_path[:, 1], color=colors[k], lw=2.5)
            pax.scatter([mean_path[-1, 0]], [mean_path[-1, 1]], color=colors[k], s=40, zorder=5)
            clusters.append({
                "program": int(k),
                "size": int(len(members)),
                "mean_motility": round(float(np.mean([motility[m] for m in members])), 3),
                "mean_pulsation": round(float(np.mean([pulsation[m] for m in members])), 3),
                "mean_fragmentation": round(
                    float(np.mean([trajs[m]["axes"][-1, FRAG] for m in members])), 3
                ),
                "net_pc_displacement": round(
                    float(np.mean(
                        [np.linalg.norm(coords_seq[m][-1] - coords_seq[m][0]) for m in members]
                    )), 2
                ),
            })
        prog_summary[config.label] = sorted(clusters, key=lambda c: -c["size"])
        pax.set_title(f"{config.label}: {len(clusters)} developmental programs")
        pax.set_xlabel("PC1")
        pax.set_ylabel("PC2")
        print(f"{config.label}: flux-motility rho={r_mot:.2f} flux-pulsation rho={r_pul:.2f}")

    flux_fig.suptitle("Where the circulation lives: Hodge flux vs creature motility")
    flux_fig.tight_layout()
    flux_fig.savefig(FIGURES_DIR / "flux_vs_behavior.png", dpi=130)
    prog_fig.suptitle("Developmental programs: clustered trajectory routes through morphospace")
    prog_fig.tight_layout()
    prog_fig.savefig(FIGURES_DIR / "developmental_programs.png", dpi=130)
    FLUX_SUMMARY.write_text(json.dumps(flux_summary, indent=2))
    PROGRAMS_SUMMARY.write_text(json.dumps(prog_summary, indent=2))
    print(f"wrote figures + {FLUX_SUMMARY.name} + {PROGRAMS_SUMMARY.name}")


if __name__ == "__main__":
    build()
