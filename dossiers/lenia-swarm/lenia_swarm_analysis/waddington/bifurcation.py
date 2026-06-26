"""Genotype-space bifurcation pilot: the companion to the phenotype-space Waddington landscape.

Holding the rule architecture and initial condition fixed, sweep two growth knobs (m, s) of a real
Flow-Lenia soliton across a grid, run each setting through the engine, and read the terminal
phenotype. Colouring that (m, s) plane by what grows exposes the bifurcation set: smooth regions
(one attractor type) separated by sharp boundaries (fold catastrophes) where the phenotype changes
discontinuously. Running each genotype from two initial masses (full vs half amplitude) adds the
hysteresis test: where the full seed lives but the half seed dies is a bistable region, and a
bistable wedge that narrows to a point is the signature of a cusp catastrophe -- the codim-2
organizing centre, and the literal genotype-space analogue of Waddington's one-genome-two-fates.

This is the bifurcation diagram (system B: the genotype->phenotype map), distinct from the
state-space relaxation landscape the rest of this module builds (system A). No re-implementation of
Lenia: every point is the real engine via `discover local`.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .family_pipeline import CLI, CONFIG_ROOT
from .study import FIGURES_DIR, STUDY_ROOT

# scutidae-S4-a is a verified stable, localized, non-spreading single-channel Flow-Lenia soliton
# (one component, occupancy ~0.06, unchanged from 600 to 1200 steps), unlike the orbium-parity
# config which fragments. Its growth knobs (m~0.42, s~0.088) sit on the thin soliton tongue between
# the explode and dead regimes, the right place to look for the cusp where those two folds meet.
BASE_CONFIG = next(
    CONFIG_ROOT.glob("**/Scutidae-S4-a-qd24-additive-native-parity-mlx.json")
)
M_RANGE = (0.30, 0.55)
S_RANGE = (0.03, 0.13)
GRID_N = 28  # (m, s) resolution; fine enough to resolve the thin soliton tongue
SIM_GRID = 128
SIM_STEPS = 600  # let solitons settle rather than read a filling transient as "explode"
AMPLITUDES = (1.0, 0.5)  # full vs half initial mass: the critical-mass / hysteresis test
RESULT = STUDY_ROOT / "bifurcation.npz"
OUT = FIGURES_DIR / "bifurcation.png"


def _search_cfg(path: Path) -> None:
    path.write_text(json.dumps({
        "count": 1, "seed_start": 0, "seed_stride": 1, "seeds_per_job": 1, "batch_size": 1,
        "steps": SIM_STEPS, "record_interval": SIM_STEPS, "warmup_steps": 0,
        "occupancy_threshold": 0.05, "component_threshold": 0.05, "mass_channel": -1,
        "score_weights": {}, "filters": {}, "overrides": {}, "top_k": 1,
        "moments": {"enabled": True, "threshold": 0.03},
        "collection": {"enabled": True, "export_enabled": False,
                       "require_filters_passed": False, "require_stable": False},
    }))


def _scale_patch(state_patch: dict, amp: float) -> dict:
    if amp == 1.0:
        return state_patch
    raw = np.frombuffer(base64.b64decode(state_patch["data"]), dtype="<f4") * amp
    out = dict(state_patch)
    out["data"] = base64.b64encode(raw.astype("<f4").tobytes()).decode("ascii")
    return out


def _run_point(base: dict, m: float, s: float, amp: float, work: Path, search: Path) -> dict:
    cfg = json.loads(json.dumps(base))
    cfg["backend"] = "mlx"
    cfg["grid"] = {"sx": SIM_GRID, "sy": SIM_GRID}
    cfg["run"] = {"steps": SIM_STEPS}
    cfg["params"] = dict(cfg["params"])
    cfg["params"]["m"] = [float(m)]
    cfg["params"]["s"] = [float(s)]
    cfg["init"] = dict(cfg["init"])
    cfg["init"]["state_patch"] = _scale_patch(cfg["init"]["state_patch"], amp)
    cfg_path = work / "c.json"
    cfg_path.write_text(json.dumps(cfg))
    out = work / "o"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run(
        [str(CLI), "discover", "local", "--config", str(cfg_path), "--search", str(search),
         "--backend", "mlx", "--no-promotion", "--output", str(out)],
        capture_output=True, text=True,
    )
    res = list(out.rglob("results.jsonl"))
    if not res:
        return {}
    return json.loads(res[0].read_text().splitlines()[0]).get("metrics", {}) or {}


def sweep() -> None:
    base = json.loads(BASE_CONFIG.read_text())
    ms = np.linspace(*M_RANGE, GRID_N)
    ss = np.linspace(*S_RANGE, GRID_N)
    fields = ("occupancy_mean", "mass_mean", "gyration", "component_count", "speed_mean")
    data = {amp: {f: np.full((GRID_N, GRID_N), np.nan) for f in fields} for amp in AMPLITUDES}
    work = Path(tempfile.mkdtemp())
    search = work / "s.json"
    _search_cfg(search)
    total = GRID_N * GRID_N * len(AMPLITUDES)
    done = 0
    for amp in AMPLITUDES:
        for i, s in enumerate(ss):
            for j, m in enumerate(ms):
                met = _run_point(base, m, s, amp, work, search)
                for f in fields:
                    v = met.get(f)
                    if v is not None:
                        data[amp][f][i, j] = float(v)
                done += 1
            print(f"amp={amp} row s={s:.4f} done ({done}/{total})", flush=True)
    save = {"m_vals": ms, "s_vals": ss, "amplitudes": np.array(AMPLITUDES)}
    for amp in AMPLITUDES:
        for f in fields:
            save[f"{f}__{amp}"] = data[amp][f]
    STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(RESULT, **save)
    print(f"wrote {RESULT}")


def _regime(occ: np.ndarray, comp: np.ndarray) -> np.ndarray:
    """0 dead, 1 localized/alive, 2 filled/exploded."""
    r = np.full(occ.shape, 1, dtype=int)
    r[np.isnan(occ) | (occ < 0.002)] = 0
    r[(occ > 0.18) | (comp > 30)] = 2
    return r


def render() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    d = np.load(RESULT)
    ms, ss = d["m_vals"], d["s_vals"]
    ext = [ms[0], ms[-1], ss[0], ss[-1]]
    full = 1.0
    occ = d[f"occupancy_mean__{full}"]
    mass = d[f"mass_mean__{full}"]
    comp = d[f"component_count__{full}"]
    speed = d[f"speed_mean__{full}"]
    reg_full = _regime(occ, comp)
    reg_half = _regime(d["occupancy_mean__0.5"], d["component_count__0.5"])
    # bistable: full-init reaches a structure, half-init dies (critical mass)
    bistable = ((reg_full >= 1) & (reg_half == 0)).astype(float)

    fig, ax = plt.subplots(2, 3, figsize=(18, 11))

    def show(a, arr, title, **kw):
        im = a.imshow(arr, origin="lower", extent=ext, aspect="auto", **kw)
        a.set_title(title, fontsize=11)
        a.set_xlabel("m  (growth centre)")
        a.set_ylabel("s  (growth width)")
        fig.colorbar(im, ax=a, shrink=0.8)

    show(ax[0, 0], _regime(occ, comp), "regime (0 dead / 1 alive / 2 explode), full seed",
         cmap="viridis")
    show(ax[0, 1], occ, "terminal occupancy", cmap="magma")
    show(ax[0, 2], np.ma.masked_invalid(comp), "component count (log)", cmap="cividis",
         norm=LogNorm(vmin=1, vmax=max(2, np.nanmax(comp))))
    show(ax[1, 0], np.ma.masked_invalid(mass), "terminal mass", cmap="magma")
    show(ax[1, 1], np.ma.masked_invalid(speed), "speed (movers)", cmap="inferno")
    im = ax[1, 2].imshow(bistable, origin="lower", extent=ext, aspect="auto", cmap="Reds",
                         vmin=0, vmax=1)
    ax[1, 2].contour(np.linspace(*ext[:2], len(ms)), np.linspace(*ext[2:], len(ss)),
                     reg_full, levels=[0.5, 1.5], colors="cyan", linewidths=1.0)
    ax[1, 2].set_title("bistable wedge: full seed lives, half seed dies\n(cyan = full-seed regime "
                       "boundaries; a narrowing wedge = cusp)", fontsize=11)
    ax[1, 2].set_xlabel("m  (growth centre)")
    ax[1, 2].set_ylabel("s  (growth width)")
    fig.colorbar(im, ax=ax[1, 2], shrink=0.8)

    fig.suptitle("Flow-Lenia genotype-space bifurcation slice (m, s): cliffs are folds, "
                 "a narrowing bistable wedge is a cusp", fontsize=13)
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    n_alive = int((reg_full == 1).sum())
    n_bi = int(bistable.sum())
    print(f"wrote {OUT}")
    print(f"regimes (full seed): dead={int((reg_full==0).sum())} alive={n_alive} "
          f"explode={int((reg_full==2).sum())}; bistable cells={n_bi}")


def build() -> None:
    sweep()
    render()
