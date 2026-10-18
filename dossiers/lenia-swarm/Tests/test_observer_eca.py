"""Observer dependence of epiplexity on elementary cellular automata, where the answer is known.

Rule 90 is linear over GF(2), so sixteen steps give x_{t+16}(i) = x_t(i-16) xor x_t(i+16) on a ring
wider than 33 cells. An observer that sees radius 16 and can represent xor must learn the rule
(S large, H -> 0). A radius-8 observer sees neither determinant and a linear softmax cannot
represent xor, so both stay at one bit with nothing to absorb (S ~ 0). The identity rule is learnable
by every observer with little structure, and rule 30 has no structure this budget can find. The
samples come from actually running the automata, so the test also guards the closed form above.
"""

from __future__ import annotations

import numpy as np
import torch

from lenia_swarm_analysis.observer.prequential import (
    epiplexity,
    init_params,
    prequential,
)

WIDTH = 63
STEPS = 16
SAMPLES = 8192
BATCH = 64
LR = 1e-2
HIDDEN = 64
SEEDS = [11, 12, 13]


def evolve(rule: int, rows: np.ndarray, steps: int) -> np.ndarray:
    table = np.array([(rule >> k) & 1 for k in range(8)], np.int64)
    for _ in range(steps):
        rows = table[4 * np.roll(rows, 1, 1) + 2 * rows + np.roll(rows, -1, 1)]
    return rows


def measure(rule: int, radius: int, hidden: int) -> tuple[np.ndarray, np.ndarray]:
    """S and H of one learner per seed, each on its own stream of random initial rows."""
    xs, ys = [], []
    for seed in SEEDS:
        rows = np.random.default_rng(seed).integers(0, 2, (SAMPLES, WIDTH))
        centre = WIDTH // 2
        xs.append(torch.from_numpy(rows[:, centre - radius:centre + radius + 1]))
        ys.append(torch.from_numpy(evolve(rule, rows, STEPS)[:, centre]))
    params = init_params(SEEDS, 2 * radius + 1, 2, hidden, "cpu")
    curve = prequential(params, torch.stack(xs), torch.stack(ys), batch=BATCH, lr=LR,
                        encode=lambda b: b.float() * 2 - 1)
    return epiplexity(curve, batch=BATCH, tail=0.1)


def test_rule_90_closed_form() -> None:
    rows = np.random.default_rng(0).integers(0, 2, (64, WIDTH))
    expected = np.roll(rows, STEPS, 1) ^ np.roll(rows, -STEPS, 1)
    assert np.array_equal(evolve(90, rows, STEPS), expected)


def test_rule_90_structure_exists_only_for_an_observer_that_can_see_and_represent_it() -> None:
    s_mlp, h_mlp = measure(90, radius=16, hidden=HIDDEN)
    s_near, h_near = measure(90, radius=8, hidden=HIDDEN)
    s_linear, h_linear = measure(90, radius=16, hidden=0)
    s_identity, h_identity = measure(204, radius=16, hidden=HIDDEN)

    assert (h_mlp < 0.1).all() and (s_mlp > 1000).all()
    for s, h in ((s_near, h_near), (s_linear, h_linear)):
        assert (h > 0.9).all() and (np.abs(s) < 300).all()
    assert (h_identity < 0.1).all() and (s_identity < s_mlp / 2).all()


def test_rule_30_stays_random_at_this_budget() -> None:
    _, h = measure(30, radius=16, hidden=HIDDEN)
    assert (h > 0.9).all()
