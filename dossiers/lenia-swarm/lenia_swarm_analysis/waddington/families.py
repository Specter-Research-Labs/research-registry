"""Curated-family morphospace from the compendium taxonomy.

The harvest/random populations are dominated by static blobs; the genuinely life-like, motile,
coherent creatures are the named families (Chakazul Section 2 taxonomy: Folidae gliders, Astridae
rotators, Pterifera fliers, ...). Those carry per-creature behaviour/shape metrics in the
compendium even though their original run artifacts are not on disk, so we embed those metrics and
colour by family to show the families occupy distinct morphotype regions.

Run with scipy + matplotlib. Reads compendium.sqlite directly (not the study warehouse).
"""

from __future__ import annotations

import json

import duckdb
import numpy as np

from ._common import pca2, silhouette, zscore
from .study import DOSSIER_ROOT, FIGURES_DIR, STUDY_ROOT

COMPENDIUM = DOSSIER_ROOT / "artifacts" / "compendium.sqlite"
METRICS = (
    "speed_mean", "displacement", "path_length", "gyration",
    "occupancy_mean", "mass_mean", "mass_std", "variance_mean", "energy_mean",
)
SUMMARY = STUDY_ROOT / "families.json"


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    conn = duckdb.connect()
    conn.execute("INSTALL sqlite; LOAD sqlite;")
    conn.execute(f"ATTACH '{COMPENDIUM}' AS c (TYPE sqlite, READ_ONLY);")
    cols = ", ".join(f"cr.{m}" for m in METRICS)
    rows = conn.execute(
        f"""
        SELECT a.family, {cols}, cr.is_stable
        FROM c.section2_taxonomy_assignments a
        JOIN c.creatures cr ON cr.id = a.creature_id
        WHERE cr.speed_mean IS NOT NULL AND cr.gyration IS NOT NULL
        """
    ).fetchall()
    families = np.array([r[0] for r in rows])
    raw = np.array([
        [float(v) if v is not None else np.nan for v in r[1:1 + len(METRICS)]] for r in rows
    ])
    keep = np.isfinite(raw).all(axis=1)
    families, raw = families[keep], raw[keep]
    # log-scale the heavy-tailed motion/size metrics, then z-score
    z = zscore(np.sign(raw) * np.log1p(np.abs(raw)))
    coords, comps, var_ratio = pca2(z)

    uniq = sorted(set(families.tolist()))
    colors = plt.cm.tab20(np.linspace(0, 1, len(uniq)))
    fig, ax = plt.subplots(figsize=(11, 9))
    centroids = {}
    for fam, col in zip(uniq, colors, strict=True):
        m = families == fam
        ax.scatter(coords[m, 0], coords[m, 1], s=14, color=col, alpha=0.7, lw=0, label=fam)
        centroids[fam] = coords[m].mean(0)
        ax.annotate(fam, centroids[fam], fontsize=8, weight="bold")
    ax.set_title(
        f"Curated-family morphospace (behaviour+shape metrics, "
        f"{len(families)} creatures, {len(uniq)} families)\n"
        f"PC1+PC2 = {100*(var_ratio[0]+var_ratio[1]):.0f}% variance"
    )
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.legend(markerscale=2, fontsize=7, ncol=2, loc="best")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_morphospace.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    sil = silhouette(z, families)

    summary = {
        "n_creatures": int(len(families)),
        "n_families": len(uniq),
        "explained_variance_ratio": [float(x) for x in var_ratio],
        "silhouette_over_families": round(sil, 3),
        "pc1_loadings": {METRICS[i]: round(float(comps[0, i]), 3) for i in range(len(METRICS))},
        "pc2_loadings": {METRICS[i]: round(float(comps[1, i]), 3) for i in range(len(METRICS))},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {SUMMARY}")
    print(f"families={len(uniq)} creatures={len(families)} "
          f"var={100*(var_ratio[0]+var_ratio[1]):.0f}% silhouette={sil:.3f}")


if __name__ == "__main__":
    build()
