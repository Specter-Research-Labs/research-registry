"""Clustering excess against array size in one implementation: 30, 50, 100, 200 and 400 distinct values.

Pairs Bubble with Selection, Bubble with Insertion and Insertion with Selection, 40 runs per size,
each scored against 200 label shuffles. Also records separation, the largest gap between the types'
swap-time distributions, and the correlation between position and type at each run's peak
(positive when the first-named type sits to the right). Run seeds 5000 + t and shuffle seeds t, so
the 100-cell rows repeat null_n100.py.
Usage: python size_trend.py <out.json>
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import (clustering_traj, mean_ci, position_gradient, run_trial, score_against_shuffles, swap_time_ks,
                 temporal_sep)

SIZES = [30, 50, 100, 200, 400]
TRIALS = 40
PERMS = 200
PAIRS = [("Bubble", "Selection"), ("Bubble", "Insertion"), ("Insertion", "Selection")]


def one(task):
    n, ta, tb, t = task
    r = run_trial(ta, tb, n, seed=5000 + t, max_ticks=500_000_000)
    assert r["sorted"], task
    is_a = np.array([x == ta for x in r["types"]])
    row = score_against_shuffles(r["snaps"], is_a, perm_seed=t, perms=PERMS)
    peak_frame = int(np.argmax(clustering_traj(r["snaps"], is_a)))
    row.update(separation=float(temporal_sep(r["swappers"], r["types"], ta, tb)),
               swap_time_ks=swap_time_ks(r["swappers"], is_a),
               position_gradient_at_peak=position_gradient(r["snaps"][peak_frame], is_a),
               swaps=len(r["swappers"]))
    return f"{n}:{ta}+{tb}", t, row


if __name__ == "__main__":
    tasks = [(n, a, b, t) for n in reversed(SIZES) for a, b in PAIRS for t in range(TRIALS)]
    rows = {f"{n}:{a}+{b}": [None] * TRIALS for n in SIZES for a, b in PAIRS}
    with ProcessPoolExecutor(12) as pool:
        for name, t, row in pool.map(one, tasks):
            rows[name][t] = row
    results = {}
    for n in SIZES:
        for a, b in PAIRS:
            name = f"{n}:{a}+{b}"
            rs = rows[name]
            s = {k: float(np.mean([x[k] for x in rs])) for k in rs[0]}
            s["excess_ci95"] = mean_ci([x["excess"] for x in rs])[1:]
            s["frac_perm_p_below_0_05"] = float(np.mean([x["perm_p"] < 0.05 for x in rs]))
            results[name] = dict(summary=s, rows=rs)
            print(f"{name:26s} excess={s['excess']:+.3f} [{s['excess_ci95'][0]:+.3f},{s['excess_ci95'][1]:+.3f}] "
                  f"peak={s['peak']:.3f} null={s['perm_null_peak']:.3f} sep={s['separation']:.3f} "
                  f"ks={s['swap_time_ks']:.3f} grad={s['position_gradient_at_peak']:+.3f} swaps={s['swaps']:.0f}",
                  flush=True)
    meta = dict(sizes=SIZES, trials=TRIALS, permutations=PERMS, trial_seeds="5000+t", permutation_seeds="t",
                scheduler="uniform", simulator="sim.py")
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, results=results), indent=1) + "\n")
