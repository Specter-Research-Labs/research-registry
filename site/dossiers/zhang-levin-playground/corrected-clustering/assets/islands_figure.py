"""Draws the islands figure: which type sits at each position as one run sorts.

One run per pair, 100 distinct values, run seed 5000 (the first run of null_n100.py),
with its peak scored against 200 shuffles of its own type labels (shuffle seed 0).
Bubble cells are blue, the other type orange.
Usage: python islands_figure.py <out.png>
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import clustering_traj, run_trial

N = 100
SEED = 5000
ROWS = 200
PERMS = 200
PANELS = [
    ("Bubble", "Insertion", "Insertion"),
    ("Bubble", "DelayedBubble", "Bubble that waits"),
    ("Bubble", "InsertionNoWait", "Insertion that never waits"),
]
BLUE = "#3a4ea3"
ORANGE = "#b5502e"

fig, axes = plt.subplots(1, 3, figsize=(10.4, 4.6), sharey=True)
for ax, (ta, tb, label_b) in zip(axes, PANELS):
    r = run_trial(ta, tb, N, seed=SEED, max_ticks=50_000_000)
    assert r["sorted"]
    is_b = np.array([x == tb for x in r["types"]])
    snaps = r["snaps"]
    idx = np.linspace(0, len(snaps) - 1, ROWS).round().astype(int)
    grid = is_b[snaps[idx]].astype(int)
    ax.imshow(grid, aspect="auto", interpolation="nearest", cmap=ListedColormap([BLUE, ORANGE]),
              extent=(0, N, 100, 0))
    C = clustering_traj(snaps, is_b)
    rng = np.random.default_rng(0)
    null = np.mean([clustering_traj(snaps, rng.permutation(is_b)).max() for _ in range(PERMS)])
    ax.set_title(f"Bubble with {label_b}", fontsize=10.5, loc="left", pad=22)
    ax.text(0, -2.5, f"peak {C.max():.2f}, shuffled labels {null:.2f}", fontsize=9, color="#555", va="bottom")
    ax.set_xlabel("position in the array")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].set_ylabel("percent of swaps completed")
fig.tight_layout()
fig.savefig(sys.argv[1], dpi=200)
