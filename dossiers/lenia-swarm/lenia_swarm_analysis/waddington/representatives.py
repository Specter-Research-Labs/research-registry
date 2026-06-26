"""Pick one canonical Flow-Lenia representative per family: the most family-typical coherent
creature, chosen as nearest (in z-scored TDA signature -- symmetry order + persistent homology) to
the family median, and render the representatives' settled fields.

These are genuine Flow-Lenia attractors of each morphotype. Where a family is rendered static, that
is the honest Flow-Lenia answer: the family's native glide is classic-Lenia asymmetric growth, which
a mass-conserving engine does not reproduce, so its faithful Flow-Lenia form is a stable shape.
Families that do glide in Flow-Lenia (or have a motile config) show up as movers.
"""

from __future__ import annotations

import json

import numpy as np

from ._common import iter_family_traces, zscore
from .family_pipeline import CREATURE_FAMILY, REPLAY_DIR
from .fidelity import _drift
from .study import FIGURES_DIR, STUDY_ROOT
from .tda import _species_map, _zernike_basis, descriptor

PATH_MOVER_FRACTION = 0.5  # total COM path > half a grid = the COM travels (orbit/glide)
GLIDE_NET_FRACTION = 0.1  # net displacement > 10% of grid = directed glide (vs orbit in place)
FROZEN_CHANGE = 0.02  # internal field change/frame below this = frozen (else alive in place)
SUMMARY = STUDY_ROOT / "family_representatives.json"


def _motion_type(net_frac: float, path_frac: float, internal: float) -> str:
    """Four honest classes. COM travel (orbiter/glider) is rare; most creatures are stationary but
    internally dynamic (pulsing/rotating in place) -- alive, just not gliding -- and only a couple
    are genuinely frozen."""
    if path_frac > PATH_MOVER_FRACTION:
        return "glider" if net_frac > GLIDE_NET_FRACTION else "orbiter"
    return "frozen" if internal < FROZEN_CHANGE else "pulsing"


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    family_map = json.loads(CREATURE_FAMILY.read_text())
    species_map = _species_map()
    theta, radial = _zernike_basis()

    creatures = []
    for fam, src, rows in iter_family_traces(REPLAY_DIR, family_map):
        d = descriptor(rows, src, theta, radial)
        if d is None:
            continue
        centers = np.array([[float(r["centerX"]), float(r["centerY"])] for r in rows])
        grid_n = float(rows[0].get("width", 192))
        net_frac = _drift(centers, grid_n, 1) / grid_n  # net displacement (translation)
        seg = np.abs(np.diff(centers, axis=0))
        seg = np.minimum(seg, grid_n - seg)  # torus-aware per-step COM step
        path_frac = float(np.hypot(seg[:, 0], seg[:, 1]).sum()) / grid_n  # total travelled distance
        creatures.append({
            "family": fam, "src": src, "species": species_map.get(src),
            "feat": np.concatenate([d["harm"], d["ph"], d["zk"]]),
            "zk": d["zk"], "field": d["field"],
            "net_frac": net_frac, "path_frac": path_frac,
            "internal_change": d["internal_change"],
        })
    print(f"{len(creatures)} coherent creatures across families")

    fams = np.array([c["family"] for c in creatures])
    feats = zscore(np.array([c["feat"] for c in creatures]))
    uniq = sorted(set(fams.tolist()))

    picks = {}
    for fam in uniq:
        idxs = np.where(fams == fam)[0]
        # the canonical representative is the most family-typical coherent creature (nearest the
        # family median TDA signature); its motion class is then reported honestly.
        centroid = np.median(feats[idxs], axis=0)
        c = creatures[idxs[int(np.argmin(np.linalg.norm(feats[idxs] - centroid, axis=1)))]]
        picks[fam] = {
            "src": c["src"], "species": c["species"],
            "peak_symmetry_order": int(np.argmax(c["zk"]) + 1),
            "motion": _motion_type(c["net_frac"], c["path_frac"], c["internal_change"]),
            "internal_change": round(float(c["internal_change"]), 3),
            "path_frac": round(float(c["path_frac"]), 2),
            "net_frac": round(float(c["net_frac"]), 3),
            "n_family_candidates": int(len(idxs)),
            "_field": c["field"],
        }

    ncol = 4
    nrow = -(-len(uniq) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(4 * ncol, 4.2 * nrow))
    flat = axes.ravel()
    for ax in flat:
        ax.axis("off")
    for ax, fam in zip(flat, uniq, strict=False):
        p = picks[fam]
        ax.imshow(p["_field"], cmap="magma", origin="lower")
        ax.set_title(f"{fam}  (order {p['peak_symmetry_order']}, {p['motion']})", fontsize=10)
    fig.suptitle("One canonical Flow-Lenia representative per family "
                 "(nearest-to-family-median TDA; motion class labelled)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_representatives.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    for p in picks.values():
        p.pop("_field")
    counts = {cls: sum(p["motion"] == cls for p in picks.values())
              for cls in ("frozen", "pulsing", "orbiter", "glider")}
    summary = {
        "n_families": len(uniq),
        "motion_class_counts": counts,
        "n_creatures_considered": len(creatures),
        "frozen_change_threshold": FROZEN_CHANGE,
        "path_mover_fraction": PATH_MOVER_FRACTION,
        "per_family": picks,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {SUMMARY}")
    print(f"{len(uniq)} families: {counts}")
    for fam, p in picks.items():
        print(f"  {fam:12s} order {p['peak_symmetry_order']}  {p['motion']:7s} "
              f"internal={p['internal_change']:.3f} path={p['path_frac']:.2f}  {p['species']}")
