"""Independent minimal reimplementation of Zhang et al. cell-view sorting (1D, no frozen cells).

Rules follow the published code (Zhangtaining/cell_research, modules/multithread):
  Bubble: pick left/right at random; swap if out of order with that neighbour.
  Gnome (dossier variant): swap left if smaller than left, else right if bigger than right.
  Insertion: only if prefix [0,pos) is non-decreasing; swap left if smaller than left.
  InsertionNoWait: Insertion without the prefix gate.
  DelayedBubble: Bubble with the Insertion prefix gate.
  Selection: ideal pointer starting at left boundary; if value >= cell at ideal, pointer += 1;
             else swap with cell at ideal.
  InsertionK<k>, BubbleK<k>: the move of Insertion or Bubble behind a graded wait, which
             requires only the nearest k cells to the left to be in order (k = 0 and k = 1 never wait;
             k >= position is Insertion's full wait).
  StableSelection: Selection that does not jump while a cell between it and its target holds
             its own value or the target's value, so equal values never pass each other.
  AdjSelection: Selection's pointer with a one-step move toward the target past whatever
             neighbour stands there (the adjacent variant of Exp25).
  AdjStrictSelection: AdjSelection that steps only past a strictly out-of-order neighbour.
  JumpInsertion: a cell moves left past the whole run of strictly larger cells next to it in one
             move, and the cells it passes each shift one place right, so nothing passes an equal.
  BubbleEq: Bubble that also swaps with an equal neighbour.
Schedulers:
  uniform: each tick one uniformly random cell executes one move().
  burst:   a uniformly random cell executes a geometric number of consecutive move() calls
           (mean B), mimicking a thread holding the GIL for a time slice.
"""
from __future__ import annotations

import random
import re

import numpy as np

GRADED = re.compile(r"^(Insertion|Bubble)K(\d+)$")


class Sim:
    def __init__(self, values, types, rng, count_equal_passes=False):
        self.count_equal_passes = count_equal_passes
        self.equal_pass_count = 0
        self.vals = list(values)
        self.types = list(types)
        self.n = len(values)
        self.rng = rng
        self.ideal = [0] * self.n
        self.cell_at = list(range(self.n))
        self.pos = list(range(self.n))
        self.first_desc = self._first_desc()

    def _first_desc(self):
        v = self.vals
        for j in range(1, self.n):
            if v[self.cell_at[j]] < v[self.cell_at[j - 1]]:
                return j
        return self.n

    def value_at(self, p):
        return self.vals[self.cell_at[p]]

    def swap_pos(self, p, q):
        if self.count_equal_passes:
            self.equal_pass_count += self.equal_passes(p, q)
        a, b = self.cell_at[p], self.cell_at[q]
        self.cell_at[p], self.cell_at[q] = b, a
        self.pos[a], self.pos[b] = q, p
        self.first_desc = self._first_desc()

    def insert_left(self, p, j):
        moved = self.cell_at[j:p]
        c = self.cell_at[p]
        self.cell_at[j:p + 1] = [c] + moved
        for q in range(j, p + 1):
            self.pos[self.cell_at[q]] = q
        self.first_desc = self._first_desc()

    def gate(self, p):
        return p <= self.first_desc

    def graded_gate(self, p, k):
        lo = p - k + 1
        if lo <= 1:
            return self.gate(p)
        for j in range(p - 1, lo - 1, -1):
            if self.value_at(j) < self.value_at(j - 1):
                return False
        return True

    def equal_passes(self, p, q):
        lo, hi = min(p, q), max(p, q)
        a, b = self.value_at(lo), self.value_at(hi)
        between = [self.value_at(j) for j in range(lo + 1, hi)]
        return between.count(a) + between.count(b) + (a == b)

    def move(self, c):
        t = self.types[c]
        p = self.pos[c]
        v = self.vals[c]
        n = self.n
        base = t.rstrip("'")
        if base in ("Bubble", "DelayedBubble"):
            if base == "DelayedBubble" and not self.gate(p):
                return False
            if self.rng.random() < 0.5:
                if p + 1 < n and v > self.value_at(p + 1):
                    self.swap_pos(p, p + 1)
                    return True
            else:
                if p > 0 and v < self.value_at(p - 1):
                    self.swap_pos(p, p - 1)
                    return True
            return False
        if base == "Gnome":
            if p > 0 and v < self.value_at(p - 1):
                self.swap_pos(p, p - 1)
                return True
            if p + 1 < n and v > self.value_at(p + 1):
                self.swap_pos(p, p + 1)
                return True
            return False
        if base in ("Insertion", "InsertionNoWait"):
            if base == "Insertion" and not self.gate(p):
                return False
            if p > 0 and v < self.value_at(p - 1):
                self.swap_pos(p, p - 1)
                return True
            return False
        if base == "Selection":
            i = self.ideal[c]
            if i == p or i >= n:
                return False
            if v >= self.value_at(i):
                self.ideal[c] = i + 1
                return False
            self.swap_pos(p, i)
            return True
        if base == "JumpInsertion":
            j = p
            while j > 0 and self.value_at(j - 1) > v:
                j -= 1
            if j == p:
                return False
            self.insert_left(p, j)
            return True
        if base == "BubbleEq":
            if self.rng.random() < 0.5:
                if p + 1 < n and v >= self.value_at(p + 1):
                    self.swap_pos(p, p + 1)
                    return True
            else:
                if p > 0 and v <= self.value_at(p - 1):
                    self.swap_pos(p, p - 1)
                    return True
            return False
        g = GRADED.match(base)
        if g:
            if not self.graded_gate(p, int(g.group(2))):
                return False
            if g.group(1) == "Insertion":
                if p > 0 and v < self.value_at(p - 1):
                    self.swap_pos(p, p - 1)
                    return True
                return False
            if self.rng.random() < 0.5:
                if p + 1 < n and v > self.value_at(p + 1):
                    self.swap_pos(p, p + 1)
                    return True
            else:
                if p > 0 and v < self.value_at(p - 1):
                    self.swap_pos(p, p - 1)
                    return True
            return False
        if base in ("StableSelection", "AdjSelection", "AdjStrictSelection"):
            i = self.ideal[c]
            if i == p or i >= n:
                return False
            w = self.value_at(i)
            if v >= w:
                self.ideal[c] = i + 1
                return False
            if base == "StableSelection":
                lo, hi = min(p, i), max(p, i)
                for j in range(lo + 1, hi):
                    if self.value_at(j) in (v, w):
                        return False
                self.swap_pos(p, i)
                return True
            q = p - 1 if i < p else p + 1
            if base == "AdjStrictSelection":
                u = self.value_at(q)
                if (q < p and u <= v) or (q > p and u >= v):
                    return False
            self.swap_pos(p, q)
            return True
        raise ValueError(t)

    def sorted(self):
        return self.first_desc == self.n

    def labels(self):
        return [self.types[c] for c in self.cell_at]


def run_trial(type_a, type_b, n, seed, scheduler="uniform", burst_mean=50, max_ticks=5_000_000):
    rng = random.Random(seed)
    values = list(range(n))
    rng.shuffle(values)
    types = [type_a] * (n // 2) + [type_b] * (n - n // 2)
    rng.shuffle(types)
    sim = Sim(values, types, rng)
    snaps = [list(sim.cell_at)]
    swappers = []
    ticks = 0
    while not sim.sorted() and ticks < max_ticks:
        c = rng.randrange(n)
        k = 1 if scheduler == "uniform" else 1 + int(rng.expovariate(1.0 / burst_mean))
        for _ in range(k):
            ticks += 1
            p_before = sim.pos[c]
            if sim.move(c):
                other = sim.cell_at[p_before]
                swappers.append((c, other))
                snaps.append(list(sim.cell_at))
                if sim.sorted():
                    break
    return dict(types=types, snaps=np.array(snaps, dtype=np.int16), swappers=swappers,
                sorted=sim.sorted(), ticks=ticks)


def clustering_traj(snaps, labels_by_cell):
    lab = np.asarray(labels_by_cell)[snaps]
    return (lab[:, 1:] == lab[:, :-1]).mean(axis=1)


def temporal_sep(swappers, types, ta, tb):
    m = max(1, len(swappers) - 1)
    ta_t, tb_t = [], []
    for i, (a, b) in enumerate(swappers):
        for c in (a, b):
            (ta_t if types[c] == ta else tb_t).append(i / m)
    if not ta_t or not tb_t:
        return float("nan")
    return abs(np.mean(ta_t) - np.mean(tb_t))


def score_against_shuffles(snaps, is_a, perm_seed, perms=200):
    """Peak and final share of same-type neighbours, each scored against `perms` label shuffles."""
    C = clustering_traj(snaps, is_a)
    rng = np.random.default_rng(perm_seed)
    null_peak, null_final = np.empty(perms), np.empty(perms)
    for j in range(perms):
        Cp = clustering_traj(snaps, rng.permutation(is_a))
        null_peak[j], null_final[j] = Cp.max(), Cp[-1]
    return dict(
        peak=float(C.max()),
        peak_position=float(np.argmax(C) / max(1, len(C) - 1)),
        perm_null_peak=float(null_peak.mean()),
        excess=float(C.max() - null_peak.mean()),
        perm_p=float((1 + np.sum(null_peak >= C.max())) / (1 + perms)),
        final=float(C[-1]),
        perm_null_final=float(null_final.mean()),
        excess_final=float(C[-1] - null_final.mean()),
    )


def mean_ci(x):
    x = np.asarray(x, dtype=float)
    half = 1.96 * x.std(ddof=1) / np.sqrt(len(x))
    return [float(x.mean()), float(x.mean() - half), float(x.mean() + half)]


def swap_time_ks(swappers, is_a):
    """Largest gap between the two types' cumulative distributions of swap times (0 to 1)."""
    m = max(1, len(swappers) - 1)
    times = np.repeat(np.arange(len(swappers)) / m, 2)
    who = np.asarray(is_a)[np.asarray(swappers).ravel()]
    ta, tb = np.sort(times[who]), np.sort(times[~who])
    grid = np.linspace(0, 1, 201)
    return float(np.max(np.abs(np.searchsorted(ta, grid, side="right") / len(ta)
                               - np.searchsorted(tb, grid, side="right") / len(tb))))


def position_gradient(snap, is_a):
    """Correlation between position and being of the first type in one arrangement."""
    lab = np.asarray(is_a)[snap].astype(float)
    return float(np.corrcoef(np.arange(len(lab)), lab)[0, 1])
