"""Render the four-config endpoint and dynamic Waddington landscapes to PNG.

Reads landscapes.npz / landscape_summary.json. Run with matplotlib available, e.g.
uv run --with matplotlib python -m lenia_swarm_analysis.waddington.render
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .landscape import RESULT_PATH, SUMMARY_PATH
from .study import CONFIGS, FIGURES_DIR


def _extent(d):
    ex, ey = d["edges_x"], d["edges_y"]
    return [ex[0], ex[-1], ey[0], ey[-1]], ex, ey


def render_endpoint(d, summary) -> None:
    extent, _, _ = _extent(d)
    fig, axes = plt.subplots(2, 2, figsize=(12, 10.5))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        u = np.ma.masked_invalid(d[f"u_endpoint_{config.config_hash}"])
        ax.imshow(u.T, origin="lower", extent=extent, aspect="auto", cmap="terrain")
        info = summary["configs"][config.config_hash]
        ax.set_title(f"{config.label}  (basins={info['n_basins']})")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
    fig.suptitle("Endpoint potential U = -log p over terminal morphospace, by rule (shared basis)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "endpoint_landscapes.png", dpi=130)
    plt.close(fig)


def render_drift(d, summary) -> None:
    extent, ex, ey = _extent(d)
    cx = 0.5 * (ex[:-1] + ex[1:])
    cy = 0.5 * (ey[:-1] + ey[1:])
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    fig, axes = plt.subplots(2, 2, figsize=(12, 10.5))
    for ax, config in zip(axes.ravel(), CONFIGS, strict=True):
        h = config.config_hash
        occ = d[f"occ_{h}"]
        u = np.ma.masked_where(~occ, d[f"u_drift_{h}"])
        vx = np.ma.masked_where(~occ, d[f"vx_{h}"])
        vy = np.ma.masked_where(~occ, d[f"vy_{h}"])
        im = ax.imshow(u.T, origin="lower", extent=extent, aspect="auto", cmap="terrain")
        step = max(1, occ.shape[0] // 24)
        ax.quiver(
            gx[::step, ::step], gy[::step, ::step], vx[::step, ::step], vy[::step, ::step],
            color="black", scale_units="xy", angles="xy", width=0.004,
        )
        info = summary["configs"][h]
        ax.set_title(f"{config.label}  flux={info['flux_fraction']:.2f}")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        fig.colorbar(im, ax=ax, shrink=0.7)
    fig.suptitle("Dynamic landscape U (v ~ -grad U) with drift field, by rule (shared basis)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "dynamic_landscapes.png", dpi=130)
    plt.close(fig)


def render() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    d = np.load(RESULT_PATH)
    summary = json.loads(SUMMARY_PATH.read_text())
    render_endpoint(d, summary)
    render_drift(d, summary)
    print(f"wrote figures to {FIGURES_DIR}")
    for p in sorted(FIGURES_DIR.glob("*.png")):
        print(f"  {p}")


if __name__ == "__main__":
    render()
