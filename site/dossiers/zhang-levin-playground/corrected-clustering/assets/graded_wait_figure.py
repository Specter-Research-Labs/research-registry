"""Graded wait at 100 cells: excess over shuffles and separation against the wait's reach k.

Usage: python graded_wait_figure.py <graded_wait.json> <out.png>
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#1d1f23"
MUTED = "#6a707b"
GRID = "#e4e5e8"
FAMILIES = [("InsertionK", "Insertion's move", "#b5502e", "o"), ("BubbleK", "Bubble's move", "#3a4ea3", "s")]

data = json.load(open(sys.argv[1]))
ks = data["provenance"]["ks"]
res = data["results"]
x = list(range(len(ks)))
labels = [str(k) for k in ks[:-1]] + ["all"]

fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6), sharex=True)
panels = [("excess", "excess_ci95", "Excess over shuffled labels"),
          ("separation", "separation_ci95", "Separation of swap times")]
for ax, (key, ci_key, title) in zip(axes, panels):
    for i, (fam, name, colour, marker) in enumerate(FAMILIES):
        s = [res[f"Bubble+{fam}{k}"]["summary"] for k in ks]
        y = [r[key] for r in s]
        lo = [r[ci_key][0] for r in s]
        hi = [r[ci_key][1] for r in s]
        off = -0.12 if i == 0 else 0.12
        xs = [v + off for v in x]
        ax.vlines(xs, lo, hi, color=colour, lw=1.2, alpha=0.6)
        ax.plot(xs, y, color=colour, lw=2, marker=marker, ms=6, mec="white", mew=1.2, label=f"Bubble with {name} behind a k-wait")
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_title(title, loc="left", fontsize=10.5, color=INK)
    ax.set_xticks(x, labels, fontsize=8.5)
    ax.set_xlabel("k, cells to the left that must be in order", fontsize=9, color=INK)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.set_ylim(-0.02, 0.1)
axes[0].legend(frameon=False, fontsize=8.5, loc="lower right")
fig.tight_layout()
fig.savefig(sys.argv[2], dpi=200)
