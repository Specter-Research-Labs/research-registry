"""Identical-rule controls and chimeras at the original paper's array size (100 cells).

Scores each per-swap clustering trajectory against 200 label shuffles of the same
trajectory, and records where in the run the peak occurs.
Usage: python null_n100.py <out.json>
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import clustering_traj, run_trial

N = 100
TRIALS = 40
PERMS = 200
GRID = np.linspace(0, 1, 101)
PAIRS = [
    ("Bubble", "Bubble'"),
    ("Insertion", "Insertion'"),
    ("Selection", "Selection'"),
    ("Bubble", "Selection"),
    ("Bubble", "Insertion"),
    ("Insertion", "Selection"),
]


def on_grid(curve):
    return np.interp(GRID, np.linspace(0, 1, len(curve)), curve)


def run_pair(pair):
    ta, tb = pair
    rows, curves, null_curves = [], [], []
    for t in range(TRIALS):
        r = run_trial(ta, tb, N, seed=5000 + t, max_ticks=50_000_000)
        assert r["sorted"], (pair, t)
        is_a = np.array([x == ta for x in r["types"]])
        C = clustering_traj(r["snaps"], is_a)
        rng = np.random.default_rng(t)
        null = [clustering_traj(r["snaps"], rng.permutation(is_a)) for _ in range(PERMS)]
        perm_max = np.array([c.max() for c in null])
        curves.append(on_grid(C))
        null_curves.append(np.mean([on_grid(c) for c in null], axis=0))
        rows.append(dict(
            peak=float(C.max()),
            peak_position=float(np.argmax(C) / (len(C) - 1)),
            perm_null_peak=float(perm_max.mean()),
            excess=float(C.max() - perm_max.mean()),
            perm_p=float((1 + np.sum(perm_max >= C.max())) / (1 + PERMS)),
            swaps=len(r["swappers"]),
        ))
    summary = {k: float(np.mean([x[k] for x in rows])) for k in rows[0]}
    summary["peak_sd"] = float(np.std([x["peak"] for x in rows], ddof=1))
    excess = np.array([x["excess"] for x in rows])
    half = 1.96 * excess.std(ddof=1) / np.sqrt(len(excess))
    summary["excess_ci95"] = [float(excess.mean() - half), float(excess.mean() + half)]
    summary["frac_perm_p_below_0_05"] = float(np.mean([x["perm_p"] < 0.05 for x in rows]))
    summary["mean_curve"] = np.mean(curves, axis=0).round(5).tolist()
    summary["mean_null_curve"] = np.mean(null_curves, axis=0).round(5).tolist()
    return f"{ta}+{tb}", dict(summary=summary, rows=rows)


if __name__ == "__main__":
    with ProcessPoolExecutor(len(PAIRS)) as pool:
        results = dict(pool.map(run_pair, PAIRS))
    for k, v in results.items():
        s = v["summary"]
        print(f"{k:24s} peak={s['peak']:.3f} null={s['perm_null_peak']:.3f} excess={s['excess']:+.3f} "
              f"[{s['excess_ci95'][0]:+.3f},{s['excess_ci95'][1]:+.3f}] at={s['peak_position']:.2f} "
              f"p<.05={s['frac_perm_p_below_0_05']:.2f} swaps={s['swaps']:.0f}", flush=True)
    meta = dict(n_cells=N, trials=TRIALS, permutations=PERMS, trial_seeds="5000+t", permutation_seeds="t",
                scheduler="uniform", simulator="sim.py")
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, results=results), indent=1) + "\n")
