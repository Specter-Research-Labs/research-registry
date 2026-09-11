"""Render the report's measured visuals from its public, path-free data packet.

Run from the repository root with the Lenia analysis environment:
    python dossiers/lenia-swarm/ops/render_morphospace_report.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "site/assets/blog/lenia-morphospace-report"
d = json.loads((OUT / "visual-data.json").read_text())
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "text.color": "#131821",
        "axes.labelcolor": "#131821",
        "axes.edgecolor": "#b9b5a9",
        "xtick.color": "#63665f",
        "ytick.color": "#63665f",
        "svg.fonttype": "none",
        "svg.hashsalt": "morphospace-report",
    }
)
colors = {
    "lenia_swarm": "#9ca7a6",
    "dryad_fish_body_shape_20240112": "#254fd4",
    "embryomaker_legacy_snapshots": "#d7553e",
    "selected": "#14795c",
}
points = d["points"]
xy = np.array([[p["x"], p["y"]] for p in points])
selected = np.array([p["selected"] for p in points])
src = np.array([p["source"] for p in points])
var = d["projection"]["variance"]
for mobile in [False, True]:
    if mobile:
        fig, (ax, overview) = plt.subplots(
            2, 1, figsize=(4.5, 8), layout="constrained", facecolor="#fffdf7"
        )
    else:
        fig, (ax, overview) = plt.subplots(
            1,
            2,
            figsize=(13, 6),
            gridspec_kw={"width_ratios": [2.1, 1]},
            layout="constrained",
            facecolor="#fffdf7",
        )
    for a in [ax, overview]:
        a.set_facecolor("#fffdf7")
        a.spines[["top", "right"]].set_visible(False)
        a.grid(alpha=0.17, zorder=0)
        for source in colors:
            m = selected if source == "selected" else src == source
            a.scatter(
                xy[m, 0],
                xy[m, 1],
                s=12 if source == "selected" else 7,
                c=colors[source],
                alpha=0.8 if source == "selected" else 0.4,
                linewidths=0,
                rasterized=True,
                zorder=4 if source == "selected" else 2,
            )
        a.set_xlabel(f"PC1 · {var[0]:.1%} of Lenia variance")
    ax.set_ylabel(f"PC2 · {var[1]:.1%} of Lenia variance")
    ax.set_xlim(-4, 17)
    ax.set_ylim(-7, 7)
    ax.set_title("A closer view of the populated region", loc="left", fontweight="bold", pad=20)
    center = np.median(xy[selected], axis=0)
    ax.annotate(
        "Selected neighborhood\n256 observations",
        xy=center,
        xytext=(7, 4.5),
        fontsize=12,
        color=colors["selected"],
        weight="bold",
        arrowprops={"arrowstyle": "->", "color": colors["selected"], "lw": 1.4},
    )
    overview.set_title("The full map", loc="left", fontweight="bold", pad=20)
    overview.add_patch(Rectangle((-4, -7), 21, 14, fill=False, ls="--", ec="#131821", lw=1))
    overview.text(0.02, 0.02, "Dashed box = closer view", transform=overview.transAxes, fontsize=9)
    fig.savefig(
        OUT / ("fig-measured-map-mobile.svg" if mobile else "fig-measured-map.svg"),
        metadata={"Date": None},
    )
    plt.close(fig)

cmap = LinearSegmentedColormap.from_list("matter", ["#111722", "#3856b3", "#c1d5ed", "#fffdf7"])
for p in d["portraits"]:
    a = np.array(p["mass"])
    fig, ax = plt.subplots(figsize=(1.6, 1.6), dpi=120)
    fig.subplots_adjust(0, 0, 1, 1)
    ax.imshow(a, cmap=cmap, vmin=0, vmax=1, origin="lower", interpolation="nearest")
    ax.axis("off")
    fig.savefig(OUT / f"specimen-{p['id'][:8].lower()}.png", dpi=120)
    plt.close(fig)


def projected(points):
    a = np.array(points)
    a -= a.mean(0)
    _, _, v = np.linalg.svd(a, full_matrices=False)
    out = a @ v[:2].T
    for i in range(2):
        if v[i, np.argmax(abs(v[i]))] < 0:
            out[:, i] *= -1
    return out / max(np.ptp(out[:, 0]), np.ptp(out[:, 1]))


for key, color in [("fish", "#254fd4"), ("embryomaker", "#d7553e")]:
    a = projected(d["comparison"][key]["points"])
    fig, ax = plt.subplots(figsize=(4, 3), layout="constrained", facecolor="#fffdf7")
    ax.set_facecolor("#fffdf7")
    ax.scatter(
        a[:, 0],
        a[:, 1],
        s=32 if key == "fish" else 1.4,
        color=color,
        alpha=1 if key == "fish" else 0.62,
        linewidths=0,
        rasterized=key != "fish",
    )
    ax.set_aspect("equal")
    ax.set_xlim(-0.57, 0.57)
    ax.set_ylim(-0.4, 0.4)
    ax.axis("off")
    fig.savefig(OUT / f"fig-neighbor-{key}.svg", metadata={"Date": None})
    plt.close(fig)
a = np.array(d["comparison"]["leniaFingerprint"])
fig, ax = plt.subplots(figsize=(4, 3), facecolor="#fffdf7")
ax.imshow(a, cmap=cmap, origin="upper", interpolation="nearest")
ax.axis("off")
fig.savefig(OUT / "fig-neighbor-lenia.svg", metadata={"Date": None})
plt.close(fig)
for p in [OUT / "fig-measured-map.svg", OUT / "fig-measured-map-mobile.svg"]:
    p.write_text(p.read_text().replace("'DejaVu Sans'", "Arial, sans-serif"))
print("Rendered map, reference point clouds, and five initial-state portraits.")
