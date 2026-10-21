"""Independent minimal reimplementation of Zhang et al. cell-view sorting (1D, no frozen cells).

Rules follow the published code (Zhangtaining/cell_research, modules/multithread):
  Bubble: pick left/right at random; swap if out of order with that neighbour.
  Gnome (dossier variant): swap left if smaller than left, else right if bigger than right.
  Insertion: only if prefix [0,pos) is non-decreasing; swap left if smaller than left.
  InsertionNoWait: Insertion without the prefix gate.
  DelayedBubble: Bubble with the Insertion prefix gate.
  Selection: ideal pointer starting at left boundary; if value >= cell at ideal, pointer += 1;
             else swap with cell at ideal.
Schedulers:
  uniform: each tick one uniformly random cell executes one move().
  burst:   a uniformly random cell executes a geometric number of consecutive move() calls
           (mean B), mimicking a thread holding the GIL for a time slice.
"""
from __future__ import annotations

import random

import numpy as np


class Sim:
    def __init__(self, values, types, rng):
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
        a, b = self.cell_at[p], self.cell_at[q]
        self.cell_at[p], self.cell_at[q] = b, a
        self.pos[a], self.pos[b] = q, p
        self.first_desc = self._first_desc()

    def gate(self, p):
        return p <= self.first_desc

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
