"""Replay the real Chakazul Section-2 named families and build their developmental landscape.

The curated families live as ~1500 local per-creature base configs under artifacts/configs (each a
complete qd24-additive Flow-Lenia rule + seeded init). Scaffolds vary per creature (quad4/bump4/...
kernel profiles, different dt), so each is run on its own config: `discover local` produces a strict
replay bundle, then `publish replay --development-trace` captures the per-step trajectory. We tag
each creature with its family (from the config path), ingest, and build a family-coloured 16-axis
shape morphospace + developmental programs -- the version the stored scalar metrics could not give.

generate(): run-locals -> assemble index -> capture-replay -> ingest. analyze(): family landscape.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from ..morphospace.ingest_replay import ingest_replay_batch
from ..morphospace.warehouse import connect_database
from ..transformation_metrics import (
    TERMINAL_AXIS_IDS,
    extract_terminal_raw_axes_from_descriptors,
    transform_axes,
)
from ._common import iter_family_traces, pca2, silhouette
from .study import DOSSIER_ROOT, FIGURES_DIR, STUDY_ROOT, WAREHOUSE_DB

CONFIG_ROOT = DOSSIER_ROOT / "artifacts" / "configs"
CLI = DOSSIER_ROOT / ".build" / "release" / "LeniaCLI"
FAM_ROOT = STUDY_ROOT / "families_replay"
LOCAL_DIR = FAM_ROOT / "local"
MERGED_INDEX = FAM_ROOT / "families_index.jsonl"
CREATURE_FAMILY = FAM_ROOT / "creature_family.json"
REPLAY_DIR = FAM_ROOT / "replay"
SEARCH_CONFIG = FAM_ROOT / "search_1000.json"
STUDY_ID_FILE = FAM_ROOT / "study_id.txt"
ANALYZE_SUMMARY = STUDY_ROOT / "families_landscape.json"

FAMILIES = (
    "astridae", "circidae", "cricidae", "dentidae", "folidae", "geminidae", "helicidae",
    "kronidae", "orbidae", "pterifera", "quadridae", "radidae", "scutidae", "volvidae",
)
STEPS = 1000
RECORD_INTERVAL = 25
FIELD_RESOLUTION = 128  # opt-in centered Float16 field per trace sample (for cubical PH + Zernike)


def _family_of(path: Path) -> str | None:
    # basename first: dirs like "pterifera_scutidae_..." would otherwise mislabel the creature
    name = Path(path).name.lower()
    for fam in FAMILIES:
        if fam in name:
            return fam
    low = str(path).lower()
    for fam in FAMILIES:
        if fam in low:
            return fam
    return None


def _runnable_configs() -> list[tuple[str, Path]]:
    """One coherent base config per creature: prefer the -patchfix (orientation-corrected) version,
    drop full-field-init pattern families (state_patch ~ whole grid) and ES search specs. Returns
    (family, path), family taken from the config name."""
    dirs = list(CONFIG_ROOT.glob("*section2*"))
    dirs += list(CONFIG_ROOT.glob("chakazul-lenia-lifeforms*"))
    cands: dict[str, tuple[bool, str, Path]] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*.json"):
            n = f.name.lower()
            if "manifest" in n or n.startswith("search") or "/patterns/" in str(f).lower():
                continue
            fam = _family_of(f)
            if fam is None:
                continue
            try:
                c = json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(c, dict) or "generations" in c or "population" in c:
                continue
            if not (c.get("channels") and c.get("grid") and c.get("implementation")):
                continue
            grid = (c.get("grid") or {}).get("sx") or 0
            sp = (c.get("init") or {}).get("state_patch")
            full = sp and grid and max(sp.get("width", 0), sp.get("height", 0)) >= 0.8 * grid
            if full:
                continue  # init fills the field -> global pattern, not a localized organism
            is_patchfix = "patchfix" in n
            key = f.stem.replace("-patchfix", "").replace("-mlx", "")
            if key not in cands or (is_patchfix and not cands[key][0]):
                cands[key] = (is_patchfix, fam, f)
    return sorted(((fam, f) for _, fam, f in cands.values()), key=lambda t: (t[0], str(t[1])))


def _write_search() -> None:
    FAM_ROOT.mkdir(parents=True, exist_ok=True)
    SEARCH_CONFIG.write_text(json.dumps({
        "count": 1, "seed_start": 0, "seed_stride": 1, "seeds_per_job": 1, "batch_size": 1,
        "steps": STEPS, "record_interval": RECORD_INTERVAL, "warmup_steps": 0,
        "occupancy_threshold": 0.05, "component_threshold": 0.05, "mass_channel": -1,
        "score_weights": {}, "filters": {}, "overrides": {}, "top_k": 1,
        "moments": {"enabled": True, "threshold": 0.03},
        "collection": {"enabled": True, "export_enabled": True,
                       "require_filters_passed": False, "require_stable": False},
    }))


def run_locals() -> None:
    _write_search()
    configs = _runnable_configs()
    print(f"{len(configs)} runnable family configs (patchfix-preferred, localized)")
    ok = 0
    fail = 0
    for i, (fam, cfg) in enumerate(configs):
        out = LOCAL_DIR / fam / cfg.stem
        if out.exists() and list(out.rglob("exports/index.jsonl")):
            ok += 1
            continue
        out.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [str(CLI), "discover", "local", "--config", str(cfg), "--search", str(SEARCH_CONFIG),
             "--backend", "mlx", "--no-promotion", "--output", str(out)],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and list(out.rglob("exports/index.jsonl")):
            ok += 1
        else:
            fail += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(configs)} (ok={ok} fail={fail})")
    print(f"locals done: ok={ok} fail={fail}")


def assemble_index() -> None:
    family_map: dict[str, str] = {}
    with MERGED_INDEX.open("w") as out:
        for idx in sorted(LOCAL_DIR.rglob("exports/index.jsonl")):
            fam = _family_of(idx)
            if fam is None:
                continue
            for line in idx.read_text().splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                cid = record.get("creatureId")
                if cid:
                    family_map[cid] = fam
                    out.write(line + "\n")
    CREATURE_FAMILY.write_text(json.dumps(family_map))
    print(f"merged {len(family_map)} export records across families -> {MERGED_INDEX}")


def replay() -> None:
    if REPLAY_DIR.exists():
        for p in sorted(REPLAY_DIR.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    r = subprocess.run(
        [str(CLI), "publish", "replay", "--input", str(MERGED_INDEX), "--output", str(REPLAY_DIR),
         "--no-promotion", "--development-trace", "--trace-interval", str(RECORD_INTERVAL),
         "--development-field-resolution", str(FIELD_RESOLUTION)],
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit("family replay failed")


def ingest() -> None:
    conn = connect_database(WAREHOUSE_DB)
    study_id = ingest_replay_batch(
        conn, development_traces_path=REPLAY_DIR, label="waddington-families"
    )
    conn.close()
    STUDY_ID_FILE.write_text(study_id)
    print(f"ingested families study {study_id}")


def generate() -> None:
    run_locals()
    assemble_index()
    replay()
    try:
        ingest()  # warehouse-native storage; best-effort (degenerate creatures crash shared code)
    except SystemExit as exc:
        print(f"ingest skipped (analyze reads traces directly): {exc}")
    print("FAMILY GENERATE COMPLETE")


def _axes_from_trace(rows: list[dict], sid: str):
    """Returns (axes[T,16], centers[T,2], grid_n) or None for degenerate creatures (the shared axis
    extraction raises SystemExit when a step has no finite fingerprint / symmetry)."""
    rows = sorted(rows, key=lambda x: int(x["step"]))
    axes, centers = [], []
    grid_n = None
    for r in rows:
        try:
            raw = extract_terminal_raw_axes_from_descriptors(
                terminal=r["terminal"],
                trajectory={"centerVelocity": 0.0, "pathTortuosity": 0.0}, specimen_id=sid,
            )
            t = transform_axes(raw)
            axes.append([float(t[a]) for a in TERMINAL_AXIS_IDS])
            centers.append([float(r["centerX"]), float(r["centerY"])])
            grid_n = float(r.get("width", grid_n or 192))
        except (SystemExit, ValueError, KeyError, TypeError):
            return None
    if len(axes) < 3:
        return None
    return np.array(axes), np.array(centers), grid_n


def _load_family_trajectories(family_map: dict) -> list[dict]:
    trajectories = []
    skipped = 0
    for fam, src, rows in iter_family_traces(REPLAY_DIR, family_map):
        loaded = _axes_from_trace(rows, src)
        if loaded is None:
            skipped += 1
            continue
        axes, centers, grid_n = loaded
        trajectories.append({"family": fam, "axes": axes, "centers": centers, "grid_n": grid_n})
    print(f"loaded {len(trajectories)} family trajectories ({skipped} degenerate skipped)")
    return trajectories


def analyze() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    family_map = json.loads(CREATURE_FAMILY.read_text())
    trajs = _load_family_trajectories(family_map)
    if len(trajs) < 20:
        raise SystemExit("too few family trajectories")

    term = np.array([t["axes"][-1] for t in trajs])
    fams = np.array([t["family"] for t in trajs])
    mean = term.mean(0)
    std = term.std(0)
    std[std == 0] = 1.0
    z = (term - mean) / std
    coords, comps, var_ratio = pca2(z)
    sil = silhouette(z, fams)

    uniq = sorted(set(fams.tolist()))
    colors = plt.cm.tab20(np.linspace(0, 1, len(uniq)))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(20, 9))
    for fam, col in zip(uniq, colors, strict=True):
        m = fams == fam
        a1.scatter(coords[m, 0], coords[m, 1], s=12, color=col, alpha=0.6, lw=0,
                   label=f"{fam} ({m.sum()})")
        a1.annotate(fam, coords[m].mean(0), fontsize=8, weight="bold")
        path = np.mean([np.column_stack([
            np.interp(np.linspace(0, 1, 12), np.linspace(0, 1, len(t["axes"])),
                      (((t["axes"] - mean) / std) @ comps.T)[:, d]) for d in range(2)
        ]) for t in trajs if t["family"] == fam], axis=0)
        a2.plot(path[:, 0], path[:, 1], color=col, lw=2.5, label=fam)
        a2.scatter([path[-1, 0]], [path[-1, 1]], color=col, s=40, zorder=5)
    a1.set_title(f"Family shape morphospace (16-axis terminal, {len(trajs)} creatures)\n"
                 f"PC1+PC2={100*(var_ratio[0]+var_ratio[1]):.0f}%  silhouette={sil:.3f}")
    a1.set_xlabel("PC1")
    a1.set_ylabel("PC2")
    a1.legend(markerscale=2, fontsize=6, ncol=2)
    a2.set_title("Family-mean developmental programs (creodes)")
    a2.set_xlabel("PC1")
    a2.set_ylabel("PC2")
    a2.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / "family_shape_landscape.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    summary = {
        "n_creatures": len(trajs),
        "n_families": len(uniq),
        "explained_variance_ratio": [float(x) for x in var_ratio],
        "silhouette_16axis_shape": round(sil, 3),
        "per_family_counts": {f: int((fams == f).sum()) for f in uniq},
        "pc1_loadings": {TERMINAL_AXIS_IDS[i]: round(float(comps[0, i]), 3) for i in range(16)},
        "pc2_loadings": {TERMINAL_AXIS_IDS[i]: round(float(comps[1, i]), 3) for i in range(16)},
    }
    ANALYZE_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out} and {ANALYZE_SUMMARY}")
    print(f"silhouette(16-axis shape) = {sil:.3f}  (scalar-metric space was -0.18)")
