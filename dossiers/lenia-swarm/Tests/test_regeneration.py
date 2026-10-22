import math

import numpy as np

from lenia_swarm_analysis.morphospace.regeneration import cut_state


def _body_across_seam(n=64):
    rng = np.random.default_rng(0)
    state = np.zeros((n, n, 2), dtype=np.float32)
    rows = (np.arange(-6, 7) + n) % n
    cols = np.arange(20, 34)
    state[np.ix_(rows, cols)] = rng.uniform(0.1, 1.0, (len(rows), len(cols), 2))
    return state


def test_cut_removes_target_fraction_on_the_far_side_of_a_body_split_by_the_seam():
    state = _body_across_seam()
    cut, removed = cut_state(state, 0.0, 0.25)
    mass = state.sum(axis=-1)
    assert abs(removed - 0.25) <= mass.max() / mass.sum()
    zeroed = (mass > 0) & (cut.sum(axis=-1) == 0)
    assert set(np.flatnonzero(zeroed.any(axis=1))) <= {3, 4, 5, 6}
    np.testing.assert_array_equal(cut[~zeroed], state[~zeroed])


def test_opposite_cuts_remove_opposite_sides():
    state = _body_across_seam()
    plus = cut_state(state, math.pi / 2, 0.5)[0].sum(axis=-1) == 0
    minus = cut_state(state, -math.pi / 2, 0.5)[0].sum(axis=-1) == 0
    occupied = state.sum(axis=-1) > 0
    assert not (plus & minus & occupied).any()
    assert np.flatnonzero((plus & occupied).any(axis=0)).min() > np.flatnonzero((minus & occupied).any(axis=0)).max() - 1
