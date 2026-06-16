"""Audit how faithful the family replays are.

The reconstructions reproduce coarse shape but not exact native dynamics: some dissolve, some are
static by design. The discover-local runs mint fresh creature ids, so stored per-creature metrics do
not join (verified); the faithful signal is therefore trace-internal. Per replayed creature we
measure survival, localization, integrity (the coherence gate), settledness (temporal stability of
the settled-phase shape -> did it reach an attractor), and drift. We break it down per family and
per config kind -- native-parity configs reproduce shape but are static by design, local/traversal/
es configs preserve motion -- and re-check the species TDA silhouette on the high-fidelity subset,
so "the replays are approximate" becomes a measured number and the headline result is stress-tested.
"""

from __future__ import annotations

import json

import numpy as np

from ..transformation_metrics import (
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from ._common import AXIS, is_coherent, iter_family_traces, silhouette, zscore
from .family_pipeline import CREATURE_FAMILY, LOCAL_DIR, REPLAY_DIR
from .study import FIGURES_DIR, STUDY_ROOT

SETTLE_AXES = ("coverage", "spread", "elongation", "compactness", "rotational_symmetry")
MOTILE_TAGS = ("local", "traversal", "-es-", "traverse")  # config-stem markers of motion-preserving
SUMMARY = STUDY_ROOT / "family_fidelity.json"


def _kind_map() -> dict[str, str]:
    """creature id -> config kind ('motile' if the stem preserves motion, else 'parity')."""
    out: dict[str, str] = {}
    for idx in LOCAL_DIR.rglob("exports/index.jsonl"):
        rel = idx.relative_to(LOCAL_DIR).parts
        if len(rel) < 2:
            continue
        kind = "motile" if any(tag in rel[1].lower() for tag in MOTILE_TAGS) else "parity"
        for line in idx.read_text().splitlines():
            if not line.strip():
                continue
            cid = json.loads(line).get("creatureId")
            if cid:
                out[str(cid)] = kind
    return out


def _settledness(axes: np.ndarray) -> float:
    """Mean coefficient of variation of the key shape axes over the settled (last-third) phase.
    Low = the reconstruction reached a steady attractor; high = it never settled."""
    settled = axes[len(axes) * 2 // 3:]
    cvs = []
    for name in SETTLE_AXES:
        col = settled[:, AXIS[name]]
        cvs.append(float(np.std(col) / (np.abs(np.mean(col)) + 1e-6)))
    return float(np.mean(cvs))


def _drift(centers: np.ndarray, grid_n: float, steps: int) -> float:
    d = np.abs(centers[-1] - centers[0])
    d = np.minimum(d, grid_n - d)
    return float(np.hypot(d[0], d[1]) / max(steps, 1))


def _records(family_map: dict, kind_map: dict) -> list[dict]:
    out = []
    for fam, src, rows in iter_family_traces(REPLAY_DIR, family_map):
        axvecs, centers = [], []
        try:
            for r in rows:
                raw = extract_terminal_raw_axes_from_descriptors(
                    terminal=r["terminal"],
                    trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0}, specimen_id=src,
                )
                tx = transform_axes(raw)
                axvecs.append([float(tx[a]) for a in AXIS])
                centers.append([float(r["centerX"]), float(r["centerY"])])
        except (SystemExit, ValueError, KeyError, TypeError):
            out.append({"family": fam, "src": src, "kind": kind_map.get(src, "parity"),
                        "degenerate": True})
            continue
        if len(axvecs) < 3:
            continue
        axes = np.array(axvecs)
        out.append({
            "family": fam, "src": src, "kind": kind_map.get(src, "parity"),
            "degenerate": False,
            "coherent": is_coherent(axes),
            "settledness": _settledness(axes),
            "drift": _drift(np.array(centers), float(rows[0].get("width", 192)), len(axes)),
        })
    return out


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    family_map = json.loads(CREATURE_FAMILY.read_text())
    recs = _records(family_map, _kind_map())
    live = [r for r in recs if not r["degenerate"]]
    n = len(recs)
    n_deg = sum(r["degenerate"] for r in recs)
    n_coh = sum(r.get("coherent", False) for r in live)
    print(f"{n} replayed, {n_deg} degenerate, {n_coh} coherent")

    fams = sorted({r["family"] for r in recs})
    per_family = {}
    for fam in fams:
        fr = [r for r in recs if r["family"] == fam]
        fl = [r for r in fr if not r["degenerate"]]
        coh = [r for r in fl if r["coherent"]]
        per_family[fam] = {
            "n": len(fr),
            "degenerate_frac": round(sum(r["degenerate"] for r in fr) / max(len(fr), 1), 3),
            "coherent_frac": round(len(coh) / max(len(fr), 1), 3),
            "motile_config_frac": round(
                sum(r["kind"] == "motile" for r in fr) / max(len(fr), 1), 3),
            "median_settledness": round(float(np.median([r["settledness"] for r in coh])), 4)
            if coh else None,
            "median_drift": round(float(np.median([r["drift"] for r in coh])), 5) if coh else None,
        }

    by_kind = {}
    for kind in ("parity", "motile"):
        kl = [r for r in live if r["kind"] == kind]
        coh = [r for r in kl if r["coherent"]]
        by_kind[kind] = {
            "n": len(kl),
            "coherent_frac": round(len(coh) / max(len(kl), 1), 3),
            "median_settledness": round(float(np.median([r["settledness"] for r in coh])), 4)
            if coh else None,
            "median_drift": round(float(np.median([r["drift"] for r in coh])), 5) if coh else None,
        }

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(18, 8))
    x = np.arange(len(fams))
    a1.bar(x, [per_family[f]["coherent_frac"] for f in fams], color="#6a8caf", label="coherent")
    a1.bar(x, [per_family[f]["motile_config_frac"] for f in fams], width=0.4,
           color="#7ee0a0", label="has motile config")
    a1.set_xticks(x)
    a1.set_xticklabels(fams, rotation=60, ha="right", fontsize=8)
    a1.set_ylabel("fraction")
    a1.set_title("Replay fidelity per family: coherent vs motion-preserving coverage")
    a1.legend()
    settle = [r["settledness"] for r in live if r["coherent"]]
    a2.hist(settle, bins=40, color="#c5a3ff")
    a2.axvline(float(np.median(settle)), color="#fff", ls="--", lw=1,
               label=f"median {np.median(settle):.3f}")
    a2.set_title("Settledness of coherent reconstructions (low = reached an attractor)")
    a2.set_xlabel("mean coefficient of variation over settled-phase shape axes")
    a2.legend()
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_fidelity.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    summary = {
        "n_replayed": n,
        "degenerate_frac": round(n_deg / max(n, 1), 3),
        "coherent_frac": round(n_coh / max(n, 1), 3),
        "by_config_kind": by_kind,
        "per_family": per_family,
        "tda_robustness": _robustness(),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {SUMMARY}")
    print(f"by config kind: {by_kind}")
    print(f"TDA robustness (full vs high-settledness): {summary['tda_robustness']}")


def _robustness() -> dict:
    """Recompute the species TDA silhouette on the most-settled half of creatures, to show the
    +0.243 headline is not an artifact of the low-fidelity reconstructions."""
    from .tda import MIN_SPECIES, _species_map, _zernike_basis, descriptor

    family_map = json.loads(CREATURE_FAMILY.read_text())
    species_map = _species_map()
    theta, radial = _zernike_basis()
    rows_out = []
    for _fam, src, rows in iter_family_traces(REPLAY_DIR, family_map):
        d = descriptor(rows, src, theta, radial)
        if d is None:
            continue
        rows_out.append({
            "species": species_map.get(src),
            "settledness": _settledness(d["axes"]),
            "feat": np.concatenate([d["harm"], d["ph"], d["zk"]]),
        })

    species = np.array([r["species"] for r in rows_out])
    settle = np.array([r["settledness"] for r in rows_out])
    keep = np.array([s is not None for s in species])
    combined_all = np.array([r["feat"] for r in rows_out])

    def species_sil(mask) -> float:
        sp = species[mask]
        counts = {s: int((sp == s).sum()) for s in set(sp.tolist())}
        sel = np.array([counts.get(s, 0) >= MIN_SPECIES for s in sp])
        if sel.sum() < 4 or len(set(sp[sel].tolist())) < 2:
            return float("nan")
        return round(silhouette(zscore(combined_all[mask][sel]), sp[sel]), 3)

    cutoff = float(np.median(settle[keep]))
    hi = keep & (settle <= cutoff)
    return {
        "n_all": int(keep.sum()),
        "n_high_fidelity": int(hi.sum()),
        "settledness_cutoff": round(cutoff, 4),
        "species_silhouette_combined_all": species_sil(keep),
        "species_silhouette_high_fidelity": species_sil(hi),
    }
