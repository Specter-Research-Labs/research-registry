"""Draws the three cell rules as rows of numbered cells.

Usage: python rules_figure.py <out.png>
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

INK = "#1d1f23"
MUTED = "#6a707b"
COLOURS = {"Bubble": "#3a4ea3", "Insertion": "#b5502e", "Selection": "#2f7d6d"}
ROWS = [
    ("Bubble", [2, 5, 3, 7, 1, 8, 4, 6], 1,
     "picks a neighbour at random and swaps if the pair is out of order"),
    ("Insertion", [1, 3, 6, 2, 8, 5, 4, 7], 3,
     "steps left past a larger neighbour, but only once every cell to its left is in order"),
    ("Selection", [4, 6, 2, 7, 3, 8, 1, 5], 6,
     "jumps straight to the place it believes it belongs and swaps with whoever is there"),
]

fig, axes = plt.subplots(3, 1, figsize=(7.2, 4.4))
for ax, (name, values, actor, text) in zip(axes, ROWS):
    colour = COLOURS[name]
    for i, v in enumerate(values):
        face = colour if i == actor else "white"
        ax.add_patch(Rectangle((i, 0), 0.9, 0.9, facecolor=face, edgecolor=colour if i == actor else MUTED, lw=1.2))
        ax.text(i + 0.45, 0.45, str(v), ha="center", va="center", fontsize=13,
                color="white" if i == actor else INK)
    ax.text(-0.05, 1.75, name, fontsize=12, color=colour, weight="bold", va="center")
    ax.text(-0.05, 1.25, text, fontsize=9.5, color=INK, va="center")
    if name == "Bubble":
        ax.add_patch(FancyArrowPatch((1.45, -0.08), (2.45, -0.08), connectionstyle="arc3,rad=0.6",
                                     arrowstyle="<->", mutation_scale=12, color=colour, lw=1.4))
        ax.text(8.4, 0.45, "5 > 3, swap", fontsize=9.5, color=MUTED, va="center")
    if name == "Insertion":
        ax.add_patch(FancyArrowPatch((3.45, -0.08), (2.45, -0.08), connectionstyle="arc3,rad=-0.6",
                                     arrowstyle="->", mutation_scale=12, color=colour, lw=1.4))
        ax.add_patch(Rectangle((-0.06, -0.06), 3.02, 1.02, fill=False, edgecolor=colour, lw=1, ls="--"))
        ax.text(8.4, 0.45, "1, 3, 6 in order: go", fontsize=9.5, color=MUTED, va="center")
    if name == "Selection":
        ax.add_patch(FancyArrowPatch((6.45, -0.08), (0.45, -0.08), connectionstyle="arc3,rad=-0.25",
                                     arrowstyle="<->", mutation_scale=12, color=colour, lw=1.4))
        ax.text(8.4, 0.45, "1 belongs first, swap with 4", fontsize=9.5, color=MUTED, va="center")
    ax.set_xlim(-0.2, 11.6)
    ax.set_ylim(-1.0, 2.05)
    ax.set_aspect("equal")
    ax.axis("off")
fig.tight_layout()
fig.savefig(sys.argv[1], dpi=200)
