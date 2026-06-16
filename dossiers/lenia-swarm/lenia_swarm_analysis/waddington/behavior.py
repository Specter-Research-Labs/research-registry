"""Behavioural fingerprints of the family creatures, and the key test: do the named families
separate better by BEHAVIOUR than by terminal SHAPE?

We only keep coherent, localized, surviving creatures (the eyeball criterion, automated), then build
a per-creature dynamical fingerprint from the trajectory -- drift, pulsation, rotation/asymmetry
cycling, periodicity -- the actual family signatures (rotators spin, spinners pulse) that net
displacement misses. Then we compare the silhouette over families in behaviour space vs shape space
on the same creatures.
"""

from __future__ import annotations

import json

import numpy as np

from ._common import AXIS, is_coherent, pca2, silhouette, zscore
from .family_pipeline import CREATURE_FAMILY, _load_family_trajectories
from .study import FIGURES_DIR, STUDY_ROOT

FEATURES = (
    "drift", "path_speed", "directedness", "occ_pulsation", "gyr_pulsation",
    "elong_osc", "compact_osc", "asym_cycling", "rotsym_osc", "frag_var", "periodicity",
)
SUMMARY = STUDY_ROOT / "family_behavior.json"


def _torus_disp(a, b, n):
    d = np.abs(a - b)
    d = np.minimum(d, n - d)
    return float(np.hypot(d[0], d[1]))


def _periodicity(series: np.ndarray) -> float:
    s = series - series.mean()
    if len(s) < 6 or np.allclose(s, 0):
        return 0.0
    power = np.abs(np.fft.rfft(s))[1:]
    return float(power.max() / (power.sum() + 1e-9))


def _fingerprint(t: dict) -> dict:
    ax = t["axes"]
    c = t["centers"]
    n = t["grid_n"]
    steps = len(ax)
    seg = np.array([_torus_disp(c[i], c[i - 1], n) for i in range(1, len(c))])
    net = _torus_disp(c[-1], c[0], n)
    return {
        "drift": net / steps,
        "path_speed": float(seg.sum()) / steps,
        "directedness": net / max(float(seg.sum()), 1e-6),
        "occ_pulsation": float(np.std(ax[:, AXIS["coverage"]])),
        "gyr_pulsation": float(np.std(ax[:, AXIS["spread"]])),
        "elong_osc": float(np.std(ax[:, AXIS["elongation"]])),
        "compact_osc": float(np.std(ax[:, AXIS["compactness"]])),
        "asym_cycling": float(
            np.std(ax[:, AXIS["bilateral_symmetry"]]) + np.std(ax[:, AXIS["axial_polarity"]])
        ),
        "rotsym_osc": float(np.std(ax[:, AXIS["rotational_symmetry"]])),
        "frag_var": float(np.std(ax[:, AXIS["fragmentation"]])),
        "periodicity": _periodicity(ax[:, AXIS["coverage"]]),
    }


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    family_map = json.loads(CREATURE_FAMILY.read_text())
    trajs = _load_family_trajectories(family_map)
    stable = [t for t in trajs if is_coherent(t["axes"])]
    print(f"{len(stable)}/{len(trajs)} coherent/stable creatures after filter")
    fams = np.array([t["family"] for t in stable])

    behav = np.array([[_fingerprint(t)[f] for f in FEATURES] for t in stable])
    behav_z = zscore(behav)
    shape_z = zscore(np.array([t["axes"][-1] for t in stable]))

    sil_behav = silhouette(behav_z, fams)
    sil_shape = silhouette(shape_z, fams)
    bc = pca2(behav_z)[0]
    sc = pca2(shape_z)[0]

    uniq = sorted(set(fams.tolist()))
    colors = plt.cm.tab20(np.linspace(0, 1, len(uniq)))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(20, 9))
    for fam, col in zip(uniq, colors, strict=True):
        m = fams == fam
        a1.scatter(sc[m, 0], sc[m, 1], s=14, color=col, alpha=0.6, lw=0, label=fam)
        a1.annotate(fam, sc[m].mean(0), fontsize=8, weight="bold")
        a2.scatter(bc[m, 0], bc[m, 1], s=14, color=col, alpha=0.6, lw=0, label=fam)
        a2.annotate(fam, bc[m].mean(0), fontsize=8, weight="bold")
    a1.set_title(f"Terminal SHAPE space (16-axis)  silhouette={sil_shape:.3f}")
    a2.set_title(f"BEHAVIOUR space (dynamical fingerprint)  silhouette={sil_behav:.3f}")
    for a in (a1, a2):
        a.set_xlabel("PC1")
        a.set_ylabel("PC2")
    a2.legend(markerscale=2, fontsize=6, ncol=2)
    fig.suptitle("Do the named families separate better by behaviour than by shape?")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_behavior_vs_shape.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    per_family = {}
    for fam in uniq:
        m = fams == fam
        per_family[fam] = {
            "n": int(m.sum()),
            **{f: round(float(behav[m, i].mean()), 4) for i, f in enumerate(FEATURES)},
        }
    summary = {
        "n_stable": len(stable),
        "n_total": len(trajs),
        "silhouette_shape": round(sil_shape, 3),
        "silhouette_behavior": round(sil_behav, 3),
        "per_family_behavior": per_family,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {SUMMARY}")
    print(f"silhouette  shape={sil_shape:.3f}  behavior={sil_behav:.3f}")
