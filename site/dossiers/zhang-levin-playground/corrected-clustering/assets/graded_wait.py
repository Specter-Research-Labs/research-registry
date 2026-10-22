"""Graded wait: a cell waits until only the nearest k cells to its left are in order.

Two families at 100 distinct values, each half Bubble: Bubble with InsertionK<k> (Insertion's
move behind a k-wait) and Bubble with BubbleK<k> (Bubble's move behind a k-wait). k = 0 is no
wait, k = 100 is Insertion's full wait. Reference pairs without a graded wait give the
between-family comparison at the same size. Two further timing and placement measures are
recorded per run: the largest gap between the types' cumulative swap-time distributions, and the
correlation between position and type at the run's peak (positive when the first type, Bubble,
sits to the right). Every run is scored against 200 label shuffles,
and its separation is the gap between the two types' mean swap times (sim.temporal_sep).
Run seeds 5000 + t and shuffle seeds t, as in null_n100.py.
Usage: python graded_wait.py <out.json>
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import (clustering_traj, mean_ci, position_gradient, run_trial, score_against_shuffles, swap_time_ks,
                 temporal_sep)

N = 100
TRIALS = 40
PERMS = 200
KS = [0, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 100]
FAMILIES = {"InsertionK": "Bubble with Insertion's move behind a k-wait",
            "BubbleK": "Bubble with Bubble's move behind a k-wait"}
REFERENCE = [("Bubble", "Bubble'"), ("Bubble", "Gnome"), ("Bubble", "Selection"), ("Insertion", "Selection")]
SETTINGS = [(f"Bubble+{fam}{k}", "Bubble", f"{fam}{k}") for fam in FAMILIES for k in KS] + \
           [(f"{a}+{b}", a, b) for a, b in REFERENCE]


def one(task):
    name, ta, tb, t = task
    r = run_trial(ta, tb, N, seed=5000 + t, max_ticks=50_000_000)
    assert r["sorted"], task
    is_a = np.array([x == ta for x in r["types"]])
    row = score_against_shuffles(r["snaps"], is_a, perm_seed=t, perms=PERMS)
    peak_frame = int(np.argmax(clustering_traj(r["snaps"], is_a)))
    row.update(separation=float(temporal_sep(r["swappers"], r["types"], ta, tb)),
               swap_time_ks=swap_time_ks(r["swappers"], is_a),
               position_gradient_at_peak=position_gradient(r["snaps"][peak_frame], is_a),
               swaps=len(r["swappers"]), ticks=r["ticks"])
    return name, t, row


def pearson(x, y):
    return float(np.corrcoef(x, y)[0, 1])


if __name__ == "__main__":
    tasks = [(name, ta, tb, t) for name, ta, tb in SETTINGS for t in range(TRIALS)]
    rows = {name: [None] * TRIALS for name, _, _ in SETTINGS}
    with ProcessPoolExecutor(16) as pool:
        for name, t, row in pool.map(one, tasks, chunksize=4):
            rows[name][t] = row
    results = {}
    for name, ta, tb in SETTINGS:
        rs = rows[name]
        s = {k: float(np.mean([x[k] for x in rs])) for k in rs[0]}
        s["excess_ci95"] = mean_ci([x["excess"] for x in rs])[1:]
        s["separation_ci95"] = mean_ci([x["separation"] for x in rs])[1:]
        s["frac_perm_p_below_0_05"] = float(np.mean([x["perm_p"] < 0.05 for x in rs]))
        s["within_setting_r_sep_excess"] = pearson([x["separation"] for x in rs], [x["excess"] for x in rs])
        results[name] = dict(summary=s, rows=rs)
        print(f"{name:28s} sep={s['separation']:.3f} excess={s['excess']:+.3f} "
              f"[{s['excess_ci95'][0]:+.3f},{s['excess_ci95'][1]:+.3f}] peak={s['peak']:.3f} "
              f"null={s['perm_null_peak']:.3f} ks={s['swap_time_ks']:.3f} grad={s['position_gradient_at_peak']:+.3f} swaps={s['swaps']:.0f} ticks={s['ticks']:.0f}", flush=True)

    def means(names):
        return ([results[n]["summary"]["separation"] for n in names], [results[n]["summary"]["excess"] for n in names])

    fam_names = {fam: [f"Bubble+{fam}{k}" for k in KS] for fam in FAMILIES}
    ref_names = [f"{a}+{b}" for a, b in REFERENCE] + ["Bubble+InsertionK0", "Bubble+InsertionK100"]
    corr = {}
    for fam, names in fam_names.items():
        sx, ex = means(names)
        slope, icept = np.polyfit(sx, ex, 1)
        corr[fam] = dict(r=pearson(sx, ex), slope=float(slope), intercept=float(icept))
    sx, ex = means(ref_names)
    slope, icept = np.polyfit(sx, ex, 1)
    corr["between_rules"] = dict(names=ref_names, r=pearson(sx, ex), slope=float(slope), intercept=float(icept))
    sx, ex = means(fam_names["InsertionK"] + fam_names["BubbleK"])
    corr["both_families"] = dict(r=pearson(sx, ex))
    for k, v in corr.items():
        print(k, {a: b for a, b in v.items() if a != "names"})
    meta = dict(n_cells=N, trials=TRIALS, permutations=PERMS, ks=KS, trial_seeds="5000+t", permutation_seeds="t",
                scheduler="uniform", simulator="sim.py", families=FAMILIES)
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, correlations=corr, results=results), indent=1) + "\n")
