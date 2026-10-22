"""Frozen cells on a lock-free substrate: Exp25's four Selection variants with stale decisions.

Every active cell runs its own clock. At a read it looks at the array as it is, updates its
pointer and decides on one exchange (a target slot, or none). The exchange is written after a
read-to-write delay drawn from an exponential distribution with mean L, measured in units of the
mean time between one cell's reads; other cells keep reading and writing in between, so the
decision is executed on information that may have gone stale. A blind write exchanges the cell
with whoever occupies the target slot by then, from wherever the cell stands by then, without
looking again. A checked write drops the exchange unless the cell and the occupant of the target
slot both stand where they stood at the read, as a compare-and-swap on the two slots would. Exchanges themselves are atomic, so no value
is lost or duplicated. L = 0 executes each read and its write as one atomic step, which is the
one-cell-at-a-time scheduler of the locked substrate.

Variants follow exp25_selection_factorization.py: far-reaching or neighbour-only moves toward
Selection's pointer target, and rerouting (advance the pointer past a frozen target) or waiting
(keep the frozen target). Semantics: immovable (no exchange may involve a frozen cell; success
when the active cells are in order) and movable (frozen cells never act but others may move them;
success when the whole array is in order). 30 cells, 30 runs per condition, the same starting rows
and frozen positions for every variant, delay and write mode. Runs stop at a time budget, or once
the array is in order with no effective exchange still pending.
Usage: python lockfree_frozen.py <out.json>
"""
import hashlib
import heapq
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

N = 30
TRIALS = 30
BUDGET = 1000.0
SEED = 20261022
LATENCIES = [0.0, 0.1, 0.3, 1.0, 3.0]
MODES = ["blind", "checked"]
VARIANTS = ["long_range_rerouting", "long_range_stubborn", "adjacent_rerouting", "adjacent_stubborn"]
FROZEN = {"immovable": [0, 3, 6, 9], "movable": [0, 1, 2, 3]}


def setups():
    rng = random.Random(SEED)
    out = {}
    for sem, counts in FROZEN.items():
        for f in counts:
            rows = []
            for _ in range(TRIALS):
                values = list(range(N))
                rng.shuffle(values)
                rows.append((values, sorted(rng.sample(range(N), f))))
            out[(sem, f)] = rows
    return out


class Array:
    def __init__(self, values, frozen, semantics):
        self.val = list(values)
        self.cell_at = list(range(N))
        self.pos = list(range(N))
        self.frozen = [False] * N
        for i in frozen:
            self.frozen[i] = True
        self.semantics = semantics
        self.ideal = [0] * N

    def v(self, slot):
        return self.val[self.cell_at[slot]]

    def is_frozen_at(self, slot):
        return self.frozen[self.cell_at[slot]]

    def ordered(self):
        prev = -1
        for s in range(N):
            c = self.cell_at[s]
            if self.semantics == "immovable" and self.frozen[c]:
                continue
            if self.val[c] < prev:
                return False
            prev = self.val[c]
        return True

    def errors(self):
        prev, e = -1, 0
        for s in range(N):
            c = self.cell_at[s]
            if self.semantics == "immovable" and self.frozen[c]:
                continue
            if self.val[c] < prev:
                e += 1
            prev = self.val[c]
        return e

    def decide(self, c, variant):
        """Read: update the pointer and return a target slot, or None."""
        p, i, me = self.pos[c], self.ideal[c], self.val[c]
        if i == p or i < 0 or i >= N:
            return None
        far = variant.startswith("long_range")
        reroute = variant.endswith("rerouting")
        if self.is_frozen_at(i):
            if reroute:
                self.ideal[c] = i + 1
            if far and me < self.v(i):
                return i
            return None
        if me >= self.v(i):
            self.ideal[c] = i + 1
            return None
        if far:
            return i
        s = p - 1 if i < p else p + 1
        if self.is_frozen_at(s):
            return None
        return s

    def inversions(self):
        vs = [self.val[self.cell_at[s]] for s in range(N)
              if not (self.semantics == "immovable" and self.frozen[self.cell_at[s]])]
        return sum(1 for a in range(len(vs)) for b in range(a + 1, len(vs)) if vs[a] > vs[b])

    def exchange(self, c, slot):
        p = self.pos[c]
        d = self.cell_at[slot]
        self.cell_at[p], self.cell_at[slot] = d, c
        self.pos[c], self.pos[d] = slot, p


def run(task):
    sem, f, t, variant, L, mode, values, frozen = task
    arr = Array(values, frozen, sem)
    key = repr((SEED, sem, f, t, variant, L, mode)).encode()
    rng = random.Random(int.from_bytes(hashlib.sha256(key).digest()[:8], "big"))
    active = [c for c in range(N) if not arr.frozen[c]]
    heap, seq = [], 0
    for c in active:
        heapq.heappush(heap, (rng.expovariate(1.0), seq, c, "read", None))
        seq += 1
    pending = {}
    stats = dict(reads=0, writes=0, stale=0, inverting=0, blocked=0, dropped=0)
    sorted_at = 0.0 if arr.ordered() else None

    def effective_pending():
        if sem == "movable":
            return len(pending)
        return sum(1 for slot, _, _ in pending.values() if not (arr.frozen[arr.cell_at[slot]]))

    def write(c, slot, seen, p_read):
        nonlocal sorted_at
        occ = arr.cell_at[slot]
        if occ == c:
            return
        if sem == "immovable" and arr.frozen[occ]:
            stats["blocked"] += 1
            return
        changed = occ != seen or arr.pos[c] != p_read
        if changed:
            stats["stale"] += 1
            if mode == "checked":
                stats["dropped"] += 1
                return
        before = arr.inversions() if changed else 0
        arr.exchange(c, slot)
        if changed and arr.inversions() > before:
            stats["inverting"] += 1
        stats["writes"] += 1
        if arr.ordered():
            if sorted_at is None:
                sorted_at = now
        else:
            sorted_at = None

    now = 0.0
    while heap:
        now, _, c, kind, payload = heapq.heappop(heap)
        if now > BUDGET:
            break
        if kind == "read":
            stats["reads"] += 1
            slot = arr.decide(c, variant)
            if slot is None:
                heapq.heappush(heap, (now + rng.expovariate(1.0), seq, c, "read", None))
            elif L == 0:
                write(c, slot, arr.cell_at[slot], arr.pos[c])
                heapq.heappush(heap, (now + rng.expovariate(1.0), seq, c, "read", None))
            else:
                pending[c] = (slot, arr.cell_at[slot], arr.pos[c])
                heapq.heappush(heap, (now + rng.expovariate(1.0 / L), seq, c, "write", None))
            seq += 1
        else:
            slot, seen, p_read = pending.pop(c)
            write(c, slot, seen, p_read)
            heapq.heappush(heap, (now + rng.expovariate(1.0), seq, c, "read", None))
            seq += 1
        if sorted_at is not None and effective_pending() == 0:
            break
    success = sorted_at is not None and arr.ordered()
    return (sem, f, variant, L, mode, t, dict(success=bool(success), time=float(min(now, BUDGET)),
                                               errors=arr.errors(), **stats))


if __name__ == "__main__":
    S = setups()
    tasks = [(sem, f, t, var, L, mode, *S[(sem, f)][t])
             for sem, counts in FROZEN.items() for f in counts for var in VARIANTS
             for L in LATENCIES for mode in MODES for t in range(TRIALS)
             if not (L == 0 and mode == "checked")]
    rows = {}
    with ProcessPoolExecutor(16) as pool:
        for sem, f, var, L, mode, t, row in pool.map(run, tasks, chunksize=8):
            rows.setdefault((sem, f, var, L, mode), [None] * TRIALS)[t] = row
    results = {}
    for (sem, f, var, L, mode), rs in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][4], kv[0][3], kv[0][1])):
        s = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
        ok = [r["time"] for r in rs if r["success"]]
        s["n_success"] = int(sum(r["success"] for r in rs))
        s["time_to_order_successes"] = float(np.mean(ok)) if ok else None
        results.setdefault(sem, {}).setdefault(var, {}).setdefault(mode, {}).setdefault(str(L), {})[str(f)] = \
            dict(summary=s, rows=rs)
        print(f"{sem:9s} {var:22s} {mode:7s} L={L:<4} frozen={f} sorted={s['n_success']:2d}/{TRIALS} "
              f"writes={s['writes']:.0f} stale={s['stale']:.0f} inverting={s['inverting']:.0f} "
              f"dropped={s['dropped']:.0f} err={s['errors']:.2f}", flush=True)
    meta = dict(n_cells=N, trials=TRIALS, budget_time_units=BUDGET, seed=SEED, latencies=LATENCIES, modes=MODES,
                variants=VARIANTS, frozen_counts=FROZEN,
                dynamics_seed="first 8 bytes of sha256(repr((seed, semantics, frozen, trial, variant, L, mode)))",
                note="L = 0 runs once, as one atomic read-and-write per step; it has no write mode")
    Path(sys.argv[1]).write_text(json.dumps(dict(provenance=meta, results=results), indent=1) + "\n")
