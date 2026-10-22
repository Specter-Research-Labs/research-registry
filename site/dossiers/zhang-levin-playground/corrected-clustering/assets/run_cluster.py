import json
import sys

import numpy as np
from scipy import stats

sys.path.insert(0, sys.argv[1])
from sim import clustering_traj, run_trial, temporal_sep

N = 50
TRIALS = 40
PERMS = 200
PAIRS = [
    ("Bubble", "Insertion"),
    ("Bubble", "InsertionNoWait"),
    ("Bubble", "Bubble'"),
    ("Bubble", "DelayedBubble"),
    ("Bubble", "Gnome"),
    ("Bubble", "Selection"),
    ("Insertion", "Selection"),
]
exact_null = (N // 2 - 1) / (N - 1)
out = {}
for sched in ("uniform", "burst"):
    for ta, tb in PAIRS:
        rows = []
        for t in range(TRIALS):
            r = run_trial(ta, tb, N, seed=1000 + t, scheduler=sched)
            types = r["types"]
            is_a = np.array([x == ta for x in types])
            C = clustering_traj(r["snaps"], is_a)
            rng = np.random.default_rng(t)
            perm_max = []
            for _ in range(PERMS):
                Cp = clustering_traj(r["snaps"], rng.permutation(is_a))
                perm_max.append(Cp.max())
            perm_max = np.array(perm_max)
            rows.append(dict(
                dC_code=float(C.max() - 0.5),
                dC_exact=float(C.max() - exact_null),
                perm_mean=float(perm_max.mean() - 0.5),
                excess=float(C.max() - perm_max.mean()),
                pval=float((perm_max >= C.max()).mean()),
                Cmean=float(C.mean() - exact_null),
                C_final=float(C[-1] - exact_null),
                swaps=len(r["swappers"]),
                sep=float(temporal_sep(r["swappers"], types, ta, tb)),
                sorted=r["sorted"],
            ))
        k = f"{sched}:{ta}+{tb}"
        agg = {f: float(np.mean([x[f] for x in rows])) for f in rows[0] if f != "sorted"}
        agg["sd_dC_code"] = float(np.std([x["dC_code"] for x in rows], ddof=1))
        agg["frac_p05"] = float(np.mean([x["pval"] < 0.05 for x in rows]))
        agg["all_sorted"] = all(x["sorted"] for x in rows)
        agg["rho_dC_swaps"] = float(stats.spearmanr([x["dC_code"] for x in rows], [x["swaps"] for x in rows])[0])
        out[k] = dict(agg=agg, rows=rows)
        a = agg
        print(f"{k:38s} dC={a['dC_code']:.3f}±{a['sd_dC_code']:.3f} permnull={a['perm_mean']:.3f} "
              f"excess={a['excess']:+.3f} p<.05={a['frac_p05']:.2f} Cmean={a['Cmean']:+.3f} "
              f"swaps={a['swaps']:.0f} sep={a['sep']:.3f} rho(dC,swaps)={a['rho_dC_swaps']:+.2f} sorted={a['all_sorted']}",
              flush=True)

json.dump(out, open(sys.argv[2], "w"))
