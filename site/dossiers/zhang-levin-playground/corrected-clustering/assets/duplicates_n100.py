"""Duplicate-value chimeras at the original paper's size: 100 cells holding values 1 to 10, ten of each.

Records the peak and final adjacent-match fraction of each per-swap trajectory and scores both
against 200 label shuffles of the same trajectory.
Usage: python duplicates_n100.py <out.json>
"""
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import Sim, clustering_traj

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
    ("Bubble", "DelayedBubble"),
    ("Bubble", "InsertionNoWait"),
]


def run_trial(type_a, type_b, seed, max_ticks=50_000_000):
    rng = random.Random(seed)
    values = [i % 10 for i in range(N)]
    rng.shuffle(values)
    types = [type_a] * (N // 2) + [type_b] * (N - N // 2)
    rng.shuffle(types)
    sim = Sim(values, types, rng)
    snaps = [list(sim.cell_at)]
    ticks = 0
    while not sim.sorted() and ticks < max_ticks:
        ticks += 1
        if sim.move(rng.randrange(N)):
            snaps.append(list(sim.cell_at))
    return types, values, np.array(snaps, dtype=np.int16), sim.sorted()


def on_grid(curve):
    return np.interp(GRID, np.linspace(0, 1, len(curve)), curve)


def run_pair(pair):
    ta, tb = pair
    rows, curves, null_curves = [], [], []
    for t in range(TRIALS):
        types, values, snaps, done = run_trial(ta, tb, seed=7000 + t)
        assert done, (pair, t)
        is_a = np.array([x == ta for x in types])
        C = clustering_traj(snaps, is_a)
        rng = np.random.default_rng(t)
        null = [clustering_traj(snaps, rng.permutation(is_a)) for _ in range(PERMS)]
        curves.append(on_grid(C))
        null_curves.append(np.mean([on_grid(c) for c in null], axis=0))
        null_peak = np.array([c.max() for c in null])
        null_final = np.array([c[-1] for c in null])
        rows.append(dict(
            peak=float(C.max()),
            peak_position=float(np.argmax(C) / (len(C) - 1)),
            final=float(C[-1]),
            perm_null_peak=float(null_peak.mean()),
            perm_null_final=float(null_final.mean()),
            excess_peak=float(C.max() - null_peak.mean()),
            excess_final=float(C[-1] - null_final.mean()),
            swaps=len(snaps) - 1,
            equal_value_order_kept=bool(all(
                [c for c in snaps[0] if values[c] == v] == [c for c in snaps[-1] if values[c] == v] for v in range(10))),
        ))
    summary = {k: float(np.mean([x[k] for x in rows])) for k in rows[0]}
    summary["mean_curve"] = np.mean(curves, axis=0).round(5).tolist()
    summary["mean_null_curve"] = np.mean(null_curves, axis=0).round(5).tolist()
    for k in ("excess_peak", "excess_final"):
        x = np.array([r[k] for r in rows])
        half = 1.96 * x.std(ddof=1) / np.sqrt(len(x))
        summary[k + "_ci95"] = [float(x.mean() - half), float(x.mean() + half)]
    return f"{ta}+{tb}", dict(summary=summary, rows=rows)


if __name__ == "__main__":
    with ProcessPoolExecutor(len(PAIRS)) as pool:
        results = dict(pool.map(run_pair, PAIRS))
    for k, v in results.items():
        s = v["summary"]
        print(f"{k:24s} peak={s['peak']:.3f} (null {s['perm_null_peak']:.3f}, at {s['peak_position']:.2f}) "
              f"final={s['final']:.3f} (null {s['perm_null_final']:.3f}) "
              f"excess_final={s['excess_final']:+.3f} [{s['excess_final_ci95'][0]:+.3f},{s['excess_final_ci95'][1]:+.3f}] "
              f"swaps={s['swaps']:.0f} order_kept={s['equal_value_order_kept']:.2f}", flush=True)
    meta = dict(n_cells=N, values="1 to 10, ten cells each", trials=TRIALS, permutations=PERMS,
                trial_seeds="7000+t", permutation_seeds="t", scheduler="uniform", simulator="sim.py")
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, results=results), indent=1) + "\n")
