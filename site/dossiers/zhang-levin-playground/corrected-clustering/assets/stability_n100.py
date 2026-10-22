"""Which rules let islands outlast the sort: 100 cells holding values 1 to 10, ten of each.

Selection is split along reach and stability. AdjSelection keeps Selection's pointer but steps one
place at a time past whatever neighbour stands there (Exp25's neighbour-only variant), so it can
pass an equal; AdjStrictSelection steps only past a strictly larger or smaller neighbour, so it
cannot. JumpInsertion is a far-reaching rule that cannot pass an equal: a cell moves left past
the whole run of strictly larger cells next to it in one move. StableSelection is Selection that
refuses any jump with its own value or its target's value in between. BubbleEq is Bubble that also
swaps equal neighbours, an instability with no far reach and no pointer. Each partner runs against
Bubble and against Insertion. Peak and final share of same-type neighbours are scored against 200
label shuffles; runs that do not sort within the tick budget are reported, not scored at the end.
Run seeds 7000 + t and shuffle seeds t, as in duplicates_n100.py.
Usage: python stability_n100.py <out.json>
"""
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import Sim, clustering_traj, mean_ci, position_gradient, score_against_shuffles

N = 100
TRIALS = 40
PERMS = 200
MAX_TICKS = 20_000_000
STALL_TICKS = 2_000_000
PARTNERS = ["Selection", "AdjSelection", "AdjStrictSelection", "JumpInsertion"]
PAIRS = [(a, b) for b in PARTNERS for a in ("Bubble", "Insertion")] + [("Bubble", "BubbleEq"),
                                                                     ("Bubble", "StableSelection")]


def run(ta, tb, seed):
    rng = random.Random(seed)
    values = [i % 10 for i in range(N)]
    rng.shuffle(values)
    types = [ta] * (N // 2) + [tb] * (N - N // 2)
    rng.shuffle(types)
    sim = Sim(values, types, rng, count_equal_passes=True)
    snaps = [list(sim.cell_at)]
    budget = STALL_TICKS if tb == "StableSelection" else MAX_TICKS
    ticks = 0
    while not sim.sorted() and ticks < budget:
        ticks += 1
        if sim.move(rng.randrange(N)):
            snaps.append(list(sim.cell_at))
    return types, values, np.array(snaps, dtype=np.int16), sim, ticks


def claim_order(final, values, is_b):
    """Mean over blocks of equal values of the correlation between rank in the block and type."""
    rs = []
    for v in range(10):
        block = [c for c in final if values[c] == v]
        lab = np.asarray(is_b)[block].astype(float)
        if 0 < lab.sum() < len(lab):
            rs.append(np.corrcoef(np.arange(len(lab)), lab)[0, 1])
    return float(np.mean(rs))


def one(task):
    ta, tb, t = task
    types, values, snaps, sim, ticks = run(ta, tb, 7000 + t)
    is_a = np.array([x == ta for x in types])
    row = score_against_shuffles(snaps, is_a, perm_seed=t, perms=PERMS)
    peak_frame = int(np.argmax(clustering_traj(snaps, is_a)))
    row.update(
        sorted=bool(sim.sorted()), ticks=ticks, swaps=len(snaps) - 1, equal_passes=sim.equal_pass_count,
        position_gradient_at_peak=position_gradient(snaps[peak_frame], is_a),
        claim_order_final=claim_order(list(snaps[-1]), values, ~is_a),
        equal_value_order_kept=bool(all(
            [c for c in snaps[0] if values[c] == v] == [c for c in snaps[-1] if values[c] == v] for v in range(10))),
    )
    return f"{ta}+{tb}", t, row


if __name__ == "__main__":
    tasks = [(a, b, t) for a, b in PAIRS for t in range(TRIALS)]
    rows = {f"{a}+{b}": [None] * TRIALS for a, b in PAIRS}
    with ProcessPoolExecutor(16) as pool:
        for name, t, row in pool.map(one, tasks, chunksize=2):
            rows[name][t] = row
    results = {}
    for a, b in PAIRS:
        name = f"{a}+{b}"
        rs = rows[name]
        done = [x for x in rs if x["sorted"]]
        s = dict(n_sorted=len(done), swaps=float(np.mean([x["swaps"] for x in rs])),
                 equal_passes=float(np.mean([x["equal_passes"] for x in rs])),
                 excess_peak=mean_ci([x["excess"] for x in rs]),
                 peak=float(np.mean([x["peak"] for x in rs])),
                 position_gradient_at_peak=float(np.mean([x["position_gradient_at_peak"] for x in rs])))
        if len(done) >= 2:
            s.update(final=float(np.mean([x["final"] for x in done])),
                     perm_null_final=float(np.mean([x["perm_null_final"] for x in done])),
                     excess_final=mean_ci([x["excess_final"] for x in done]),
                     claim_order_final=float(np.mean([x["claim_order_final"] for x in done])),
                     order_kept=int(sum(x["equal_value_order_kept"] for x in done)))
        results[name] = dict(summary=s, rows=rs)
        fin = (f"final={s['final']:.3f} null={s['perm_null_final']:.3f} excess_final={s['excess_final'][0]:+.3f} "
               f"[{s['excess_final'][1]:+.3f},{s['excess_final'][2]:+.3f}] claim={s['claim_order_final']:+.3f} "
               f"kept={s['order_kept']}") if "final" in s else "unscored"
        print(f"{name:30s} sorted={s['n_sorted']}/{TRIALS} swaps={s['swaps']:.0f} eqpass={s['equal_passes']:.0f} "
              f"peak_excess={s['excess_peak'][0]:+.3f} grad={s['position_gradient_at_peak']:+.3f} {fin}", flush=True)
    meta = dict(n_cells=N, values="1 to 10, ten cells each", trials=TRIALS, permutations=PERMS,
                max_ticks=MAX_TICKS, stable_selection_max_ticks=STALL_TICKS, trial_seeds="7000+t",
                permutation_seeds="t", scheduler="uniform", simulator="sim.py")
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, results=results), indent=1) + "\n")
