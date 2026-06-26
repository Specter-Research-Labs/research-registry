"""TDA family descriptor off the opt-in native field: cubical persistent homology and Zernike
symmetry-order moments, tested for family- and species-level separability.

Cubical PH (GUDHI, superlevel-set filtration on mass via the negated field) replaces brittle
single-threshold cavity/component counts with lifetime-weighted features: a true ring scores a
long-lived H1 bar, a faint dimple scores near zero. Each diagram is summarized by persistence
entropy + statistics (Wasserstein-stable, which matters because the replays are approximate).

Zernike moments give an aliasing-resistant symmetry-order spectrum: the magnitude |Z_{n,m}| is
rotation invariant and an exact N-fold shape has energy only at m that are multiples of N, so the
m-spectrum reads off the rotational order directly. The angular harmonics (from the stored
descriptor) are kept as a same-run baseline. Both topology and symmetry are computed per frame then
medianed, because a rotator averaged across frames blurs into a ring (lost N-fold, faked hole).

Species are recovered from the config stem (Astridae-3A5, Radidae-3R4, Dentidae-2D7) and separate
far better than the broad families. Runs on the existing family traces, no re-sim.
"""

from __future__ import annotations

import base64
import json
import math

import numpy as np

from ..transformation_metrics import (
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from ._common import AXIS, is_coherent, iter_family_traces, silhouette, zscore
from .family_pipeline import CREATURE_FAMILY, FIELD_RESOLUTION, LOCAL_DIR, REPLAY_DIR
from .study import FIGURES_DIR, STUDY_ROOT

ZERNIKE_NMAX = 10
SYM_ORDERS = 8  # symmetry-order spectrum m = 1..8
HARM_ORDERS = 6  # angular-FFT harmonics baseline orders 1..6 (7..8 alias from the fingerprint)
ZERNIKE_RES = 64  # the creature is cropped + rescaled to fill this disk (scale-invariant symmetry)
PH_FEATURES = (
    "h0_entropy", "h0_bars", "h0_maxlife", "h0_sumlife",
    "h1_entropy", "h1_bars", "h1_maxlife", "h1_sumlife",
)
MIN_SPECIES = 3  # a species needs >= this many coherent creatures to enter the silhouette
SUMMARY = STUDY_ROOT / "family_tda.json"


def _field(row: dict) -> np.ndarray | None:
    """The opt-in centered Float16 native field (peak-normalized to 1), full dynamic range -- not
    the 8-bit fingerprint. None if the trace predates field capture."""
    b = row.get("fieldF16Base64")
    res = row.get("fieldResolution")
    if not b or res != FIELD_RESOLUTION:
        return None
    a = np.frombuffer(base64.b64decode(b), dtype="<f2").astype(np.float32)
    if a.size != FIELD_RESOLUTION * FIELD_RESOLUTION:
        return None
    return a.reshape(FIELD_RESOLUTION, FIELD_RESOLUTION)


def _scale_normalize(field: np.ndarray, out: int, thresh: float = 0.02) -> np.ndarray | None:
    """Crop to the creature's bounding box, pad to square, rescale to out x out. Removes the
    creature-small-in-a-mostly-empty-frame effect so the symmetry order is read at the creature's
    own scale, not the native grid's."""
    from scipy.ndimage import zoom

    ys, xs = np.where(field > thresh)
    if ys.size == 0:
        return None
    crop = field[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    side = max(crop.shape)
    sq = np.zeros((side, side), dtype=field.dtype)
    oy, ox = (side - crop.shape[0]) // 2, (side - crop.shape[1]) // 2
    sq[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop
    z = zoom(sq, out / side, order=1)
    fixed = np.zeros((out, out), dtype=z.dtype)
    h, w = min(out, z.shape[0]), min(out, z.shape[1])
    fixed[:h, :w] = z[:h, :w]
    return fixed


def _zernike_basis() -> tuple[np.ndarray, dict[tuple[int, int], np.ndarray]]:
    """Per-pixel theta and the masked radial polynomials R_{n,m} on the unit disk, precomputed once
    for the fixed scale-normalized grid (the geometry is identical for every cropped creature)."""
    res = ZERNIKE_RES
    grid = (np.arange(res) - (res - 1) / 2) / (res / 2)
    x, y = np.meshgrid(grid, grid)
    rho = np.hypot(x, y)
    theta = np.arctan2(y, x)
    mask = rho <= 1.0
    radial: dict[tuple[int, int], np.ndarray] = {}
    for m in range(0, SYM_ORDERS + 1):
        for n in range(m, ZERNIKE_NMAX + 1):
            if (n - m) % 2:
                continue
            poly = np.zeros_like(rho)
            for k in range((n - m) // 2 + 1):
                coef = ((-1) ** k * math.factorial(n - k)) / (
                    math.factorial(k)
                    * math.factorial((n + m) // 2 - k)
                    * math.factorial((n - m) // 2 - k)
                )
                poly += coef * rho ** (n - 2 * k)
            radial[(n, m)] = poly * mask
    return theta, radial


def _zernike_spectrum(field: np.ndarray, theta: np.ndarray,
                      radial: dict[tuple[int, int], np.ndarray]) -> np.ndarray | None:
    scaled = _scale_normalize(field, ZERNIKE_RES)
    if scaled is None:
        return None
    total = scaled.sum()
    if total <= 0:
        return None
    f = scaled / total
    spectrum = np.zeros(SYM_ORDERS)
    for (n, m), poly in radial.items():
        if m == 0:
            continue
        amp = (n + 1) / math.pi * np.sum(f * poly * np.exp(-1j * m * theta))
        spectrum[m - 1] += abs(amp)
    s = spectrum.sum()
    return spectrum / s if s > 0 else None


def _cubical_features(field: np.ndarray) -> np.ndarray | None:
    import gudhi

    mx = field.max()
    if mx <= 0:
        return None
    g = field / mx
    cc = gudhi.CubicalComplex(top_dimensional_cells=(-g))
    cc.persistence()
    feats: list[float] = []
    for dim in (0, 1):
        ints = cc.persistence_intervals_in_dimension(dim)
        life = np.array([d - b for b, d in ints if np.isfinite(d) and d - b > 0])
        if life.size:
            p = life / life.sum()
            feats += [float(-(p * np.log(p)).sum()), float(life.size),
                      float(life.max()), float(life.sum())]
        else:
            feats += [0.0, 0.0, 0.0, 0.0]
    return np.array(feats)


def _species_of(stem: str) -> str | None:
    # lowercase: parity vs motile configs capitalize the same species differently
    # (Astridae-3A5 vs astridae-3a5), and species identity is case-insensitive.
    parts = stem.lower().split("-")
    return f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else None


def _species_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for idx in LOCAL_DIR.rglob("exports/index.jsonl"):
        rel = idx.relative_to(LOCAL_DIR).parts
        if len(rel) < 2:
            continue
        sp = _species_of(rel[1])
        if sp is None:
            continue
        for line in idx.read_text().splitlines():
            if not line.strip():
                continue
            cid = json.loads(line).get("creatureId")
            if cid:
                out[str(cid)] = sp
    return out


def descriptor(rows: list[dict], src: str, theta: np.ndarray,
               radial: dict[tuple[int, int], np.ndarray]) -> dict | None:
    """Per-creature TDA descriptor from its trace rows: per-frame-median PH + Zernike + harmonics,
    plus the settled axes and the representative (median settled) field. None if degenerate or
    incoherent. Per-frame-then-median because a rotator averaged across frames blurs into a ring,
    which would both wash out its N-fold Zernike signature and fake an H1 hole."""
    settled = rows[len(rows) * 2 // 3:] or rows
    fields, axvecs, harms = [], [], []
    try:
        for r in settled:
            t = r["terminal"]
            fld = _field(r)
            h = (t.get("angularSymmetry") or {}).get("harmonics") or []
            if fld is None or len(h) < HARM_ORDERS:
                raise ValueError
            raw = extract_terminal_raw_axes_from_descriptors(
                terminal=t,
                trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0}, specimen_id=src,
            )
            axvecs.append([float(transform_axes(raw)[a]) for a in AXIS])
            fields.append(fld)
            harms.append(np.asarray(h[:HARM_ORDERS], dtype=float))
    except (SystemExit, ValueError, KeyError, TypeError):
        return None
    if len(fields) < 2 or not is_coherent(np.array(axvecs)):
        return None
    phs = [p for p in (_cubical_features(f) for f in fields) if p is not None]
    zks = [z for z in (_zernike_spectrum(f, theta, radial) for f in fields) if z is not None]
    if len(phs) < 2 or len(zks) < 2:
        return None
    harm = np.median(np.array(harms), axis=0)
    fa = np.array(fields)
    # internal dynamics: frame-to-frame change of the COM-centered field (translation removed), so
    # this isolates pulsing/rotation in place -- a creature can be COM-static yet very much alive.
    changes = [np.abs(fa[i + 1] - fa[i]).sum() / (np.abs(fa[i]).sum() + 1e-9)
               for i in range(len(fa) - 1)]
    return {
        "ph": np.median(np.array(phs), axis=0),
        "zk": np.median(np.array(zks), axis=0),
        "harm": harm / (harm.sum() + 1e-9),
        "axes": np.array(axvecs),
        "field": fields[-1],  # a single settled snapshot; a median would smear a moving creature
        "internal_change": float(np.median(changes)) if changes else 0.0,
    }


def _load(family_map: dict, species_map: dict) -> list[dict]:
    theta, radial = _zernike_basis()
    out = []
    for fam, src, rows in iter_family_traces(REPLAY_DIR, family_map):
        d = descriptor(rows, src, theta, radial)
        if d is None:
            continue
        out.append({"family": fam, "species": species_map.get(src), "src": src,
                    "ph": d["ph"], "zk": d["zk"], "harm": d["harm"]})
    return out


def _level_silhouettes(feats: dict[str, np.ndarray], labels: np.ndarray) -> dict[str, float]:
    return {name: round(silhouette(zscore(m), labels), 3) for name, m in feats.items()}


def build() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    family_map = json.loads(CREATURE_FAMILY.read_text())
    species_map = _species_map()
    data = _load(family_map, species_map)
    print(f"{len(data)} coherent creatures with fingerprints "
          f"({sum(d['species'] is not None for d in data)} with species)")

    fams = np.array([d["family"] for d in data])
    ph = np.array([d["ph"] for d in data])
    zk = np.array([d["zk"] for d in data])
    harm = np.array([d["harm"] for d in data])
    combined = np.hstack([ph, zk])
    feats = {
        "harmonics": harm, "ph": ph, "zernike": zk,
        "combined": combined, "combined_all": np.hstack([harm, ph, zk]),
    }

    sil_family = _level_silhouettes(feats, fams)

    has_sp = np.array([d["species"] is not None for d in data])
    species = np.array([d["species"] for d in data if d["species"] is not None])
    counts = {s: int((species == s).sum()) for s in set(species.tolist())}
    keep_sp = np.array([has_sp[i] and counts.get(data[i]["species"], 0) >= MIN_SPECIES
                        for i in range(len(data))])
    sp_labels = np.array([data[i]["species"] for i in range(len(data)) if keep_sp[i]])
    n_species = len(set(sp_labels.tolist()))
    sil_species = _level_silhouettes(
        {k: v[keep_sp] for k, v in feats.items()}, sp_labels
    ) if n_species >= 2 else {}

    uniq = sorted(set(fams.tolist()))
    colors = plt.cm.tab20(np.linspace(0, 1, len(uniq)))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(20, 9))
    order = ["harmonics", "ph", "zernike", "combined", "combined_all"]
    xpos = np.arange(len(order))
    fam_vals = [sil_family[k] for k in order]
    sp_vals = [sil_species.get(k, 0.0) for k in order]
    a1.bar(xpos - 0.2, fam_vals, 0.4, label="family (14)", color="#6a8caf")
    a1.bar(xpos + 0.2, sp_vals, 0.4, label=f"species ({n_species})", color="#7ee0a0")
    a1.axhline(0, color="#444", lw=0.8)
    for x, fv, sv in zip(xpos, fam_vals, sp_vals, strict=True):
        a1.text(x - 0.2, fv + (0.004 if fv >= 0 else -0.012), f"{fv:.3f}", ha="center", fontsize=8)
        a1.text(x + 0.2, sv + (0.004 if sv >= 0 else -0.012), f"{sv:.3f}", ha="center", fontsize=8)
    a1.set_xticks(xpos)
    a1.set_xticklabels(order, rotation=20)
    a1.set_ylabel("silhouette (separability)")
    a1.set_title("Family vs species separability by descriptor")
    a1.legend(fontsize=9)
    orders = np.arange(1, SYM_ORDERS + 1)
    for fam, col in zip(uniq, colors, strict=True):
        a2.plot(orders, zk[fams == fam].mean(0), color=col, marker="o", label=fam)
    a2.set_title("Mean Zernike symmetry-order spectrum by family (N-fold order)")
    a2.set_xlabel("rotational order m")
    a2.set_ylabel("normalized |Z| power")
    a2.legend(fontsize=6, ncol=2)
    fig.suptitle("Do families/species separate by cubical-PH topology + Zernike symmetry?")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_tda.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)

    per_family = {}
    for fam in uniq:
        m = fams == fam
        per_family[fam] = {
            "n": int(m.sum()),
            "zernike_peak_order": int(np.argmax(zk[m].mean(0)) + 1),
            "zernike_1to8": [round(float(x), 3) for x in zk[m].mean(0)],
            "h1_maxlife": round(float(ph[m, PH_FEATURES.index("h1_maxlife")].mean()), 3),
            "h0_bars": round(float(ph[m, PH_FEATURES.index("h0_bars")].mean()), 2),
        }
    summary = {
        "n_creatures": len(data),
        "n_species_kept": n_species,
        "min_species_count": MIN_SPECIES,
        "silhouette_family": sil_family,
        "silhouette_species": sil_species,
        "reference": {"harmonics_topology": 0.044, "shape": -0.041, "behavior": -0.117},
        "per_family": per_family,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {SUMMARY}")
    print(f"family   silhouette  {sil_family}")
    print(f"species  silhouette  {sil_species}")
