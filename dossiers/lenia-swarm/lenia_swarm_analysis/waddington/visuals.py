"""Illustrative and diagnostic visuals for the Waddington study.

atlas    : place real terminal fingerprints at their morphospace location, so the abstract PCA
           axes are grounded in actual creature shapes (what lives in each valley).
biascheck: split each config's specimens into two independent halves and compare basin structure
           and flux, quantifying how much the result depends on the particular 8k we sampled.

Run with: uv run --with matplotlib --with scipy python -m lenia_swarm_analysis.waddington._cli <viz>
"""

from __future__ import annotations

import base64
import json

import duckdb
import numpy as np

from ..transformation_metrics import (
    TERMINAL_AXIS_IDS,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from .ingest import STUDY_MAP_PATH
from .landscape import (
    GRID,
    RESULT_PATH,
    SMOOTH_SIGMA,
    find_basins,
    hodge_decompose,
    load_config_trajectories,
    smooth2d,
)
from .study import CONFIGS, FIGURES_DIR, WAREHOUSE_DB


def _connect():
    conn = duckdb.connect(str(WAREHOUSE_DB), read_only=True)
    conn.execute("SET memory_limit='8GB'")
    conn.execute("SET threads=4")
    return conn


def _basis(d):
    return d["mean"], d["std"], d["components"], d["edges_x"], d["edges_y"]


def load_terminals(conn, study_id, mean, std, comps):
    rows = conn.execute(
        """
        SELECT specimen_id, terminal_descriptor_json FROM (
            SELECT ds.specimen_id, ds.step, ds.terminal_descriptor_json,
                   row_number() OVER (PARTITION BY ds.specimen_id ORDER BY ds.step DESC) AS rn
            FROM development_samples ds
            JOIN study_specimens ss USING (specimen_id)
            WHERE ss.study_id = ?
        ) WHERE rn = 1
        """,
        [study_id],
    ).fetchall()
    coords, fingerprints = [], []
    for sid, terminal_json in rows:
        terminal = json.loads(terminal_json)
        raw = extract_terminal_raw_axes_from_descriptors(
            terminal=terminal,
            trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0},
            specimen_id=sid,
        )
        transformed = transform_axes(raw)
        vec = np.array([float(transformed[a]) for a in TERMINAL_AXIS_IDS])
        coords.append(((vec - mean) / std) @ comps.T)
        res = int(terminal["fingerprintResolution"])
        raw_fp = base64.b64decode(terminal["fingerprintU8"])
        fingerprints.append(np.frombuffer(raw_fp, dtype=np.uint8).reshape(res, res))
    return np.array(coords), fingerprints


def atlas() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    mapping = json.loads(STUDY_MAP_PATH.read_text())
    d = np.load(RESULT_PATH)
    mean, std, comps, ex, ey = _basis(d)
    extent = [ex[0], ex[-1], ey[0], ey[-1]]
    conn = _connect()
    cell_grid = 13
    bx = np.linspace(ex[0], ex[-1], cell_grid + 1)
    by = np.linspace(ey[0], ey[-1], cell_grid + 1)
    thumb_w = (ex[-1] - ex[0]) / cell_grid * 0.46
    thumb_h = (ey[-1] - ey[0]) / cell_grid * 0.46

    fig, axes = plt.subplots(2, 2, figsize=(13, 11.5))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        coords, fingerprints = load_terminals(conn, mapping[config.config_hash], mean, std, comps)
        u = np.ma.masked_invalid(d[f"u_endpoint_{config.config_hash}"])
        ax.imshow(u.T, origin="lower", extent=extent, aspect="auto", cmap="bone_r", alpha=0.45)
        ix = np.clip(np.digitize(coords[:, 0], bx) - 1, 0, cell_grid - 1)
        iy = np.clip(np.digitize(coords[:, 1], by) - 1, 0, cell_grid - 1)
        for ci in range(cell_grid):
            for cj in range(cell_grid):
                members = np.where((ix == ci) & (iy == cj))[0]
                if len(members) == 0:
                    continue
                cx = 0.5 * (bx[ci] + bx[ci + 1])
                cy = 0.5 * (by[cj] + by[cj + 1])
                rep = members[np.argmin(np.hypot(coords[members, 0] - cx, coords[members, 1] - cy))]
                ax.imshow(
                    fingerprints[rep].T,
                    origin="lower",
                    extent=[cx - thumb_w, cx + thumb_w, cy - thumb_h, cy + thumb_h],
                    cmap="magma",
                    interpolation="nearest",
                )
        ax.set_xlim(ex[0], ex[-1])
        ax.set_ylim(ey[0], ey[-1])
        ax.set_title(f"{config.label}")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
    fig.suptitle("Morphospace atlas: terminal fingerprints at their landscape location, by rule")
    fig.tight_layout()
    out = FIGURES_DIR / "morphospace_atlas.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"wrote {out}")


def _cell(value, edges):
    return int(np.clip(np.digitize(value, edges) - 1, 0, GRID - 1))


def _jensen_shannon(p, q):
    p = p.flatten() + 1e-12
    q = q.flatten() + 1e-12
    p /= p.sum()
    q /= q.sum()
    m = 0.5 * (p + q)
    return float(0.5 * np.sum(p * np.log(p / m)) + 0.5 * np.sum(q * np.log(q / m)))


def _terminal_density(coords_seq, ex, ey):
    term = np.array([c[-1] for c in coords_seq])
    hist, _, _ = np.histogram2d(term[:, 0], term[:, 1], bins=[ex, ey])
    p = smooth2d(hist, SMOOTH_SIGMA)
    return p / p.sum()


def _drift_flux(coords_seq, ex, ey):
    vx = np.zeros((GRID, GRID))
    vy = np.zeros((GRID, GRID))
    cnt = np.zeros((GRID, GRID))
    for c in coords_seq:
        for k in range(len(c) - 1):
            gi = _cell(c[k, 0], ex)
            gj = _cell(c[k, 1], ey)
            delta = c[k + 1] - c[k]
            vx[gi, gj] += delta[0]
            vy[gi, gj] += delta[1]
            cnt[gi, gj] += 1
    occ = cnt > 0
    vx[occ] /= cnt[occ]
    vy[occ] /= cnt[occ]
    _, flux = hodge_decompose(smooth2d(vx, SMOOTH_SIGMA), smooth2d(vy, SMOOTH_SIGMA), occ)
    return flux


def biascheck() -> None:
    """Split each config's specimens into two hash-disjoint halves; compare basins, flux, and the
    Jensen-Shannon divergence between the two halves' terminal densities. Small divergence and
    matching basin counts mean the landscape is a property of the population, not the draw."""
    mapping = json.loads(STUDY_MAP_PATH.read_text())
    d = np.load(RESULT_PATH)
    mean, std, comps, ex, ey = _basis(d)
    conn = _connect()
    report = {}
    for config in CONFIGS:
        trajs = load_config_trajectories(conn, mapping[config.config_hash])
        coords_seq = [((t["axes"] - mean) / std) @ comps.T for t in trajs]
        halves = ([], [])
        for t, c in zip(trajs, coords_seq, strict=True):
            halves[hash(t["id"]) & 1].append(c)
        pa = _terminal_density(halves[0], ex, ey)
        pb = _terminal_density(halves[1], ex, ey)
        js = _jensen_shannon(pa, pb)
        ba = len(find_basins(pa, ex, ey))
        bb = len(find_basins(pb, ex, ey))
        fa = _drift_flux(halves[0], ex, ey)
        fb = _drift_flux(halves[1], ex, ey)
        report[config.label] = {
            "half_sizes": [len(halves[0]), len(halves[1])],
            "endpoint_density_jensen_shannon": round(js, 4),
            "basins_half_a": ba,
            "basins_half_b": bb,
            "flux_half_a": round(fa, 3),
            "flux_half_b": round(fb, 3),
        }
        print(
            f"{config.label}: JS(halves)={js:.4f}  basins={ba}/{bb}  flux={fa:.3f}/{fb:.3f}"
        )
    (FIGURES_DIR.parent / "bias_check.json").write_text(json.dumps(report, indent=2))
    print(f"wrote {FIGURES_DIR.parent / 'bias_check.json'}")


if __name__ == "__main__":
    atlas()
    biascheck()
