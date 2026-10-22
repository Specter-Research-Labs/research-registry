"""One-ulp ensemble members of a Flow Lenia field, the single definition every engine uses.

A member nudges one percent of the occupied cells (summed mass at least `OCCUPIED`) by one
float32 ulp per channel, up or down at random, so that ensembles sample the divergence that
one-ulp differences between engines cause. Seed 0 is the unperturbed field.
"""

from __future__ import annotations

import numpy as np

OCCUPIED = 0.01
FRACTION = 0.01


def one_ulp_member(field: np.ndarray, seed: int, role_index: int) -> np.ndarray:
    """Member `seed` of a float32 [x, y, channel] field; draws depend on (seed, role_index)."""
    if field.dtype != np.float32 or field.ndim != 3:
        raise ValueError(f"need a float32 [x, y, channel] field, got {field.dtype} {field.shape}")
    member = field.copy()
    if seed == 0:
        return member
    i, j = np.nonzero(field.sum(2, dtype=float) >= OCCUPIED)
    if not len(i):
        raise ValueError("field has no occupied cell to perturb")
    rng = np.random.default_rng([seed, role_index])
    n = max(1, int(round(FRACTION * len(i))))
    k = rng.choice(len(i), n, replace=False)
    sign = rng.choice([-1, 1], size=(n, field.shape[2]))
    up, down = np.float32(np.inf), np.float32(0)
    for m, (x, y) in enumerate(zip(i[k], j[k], strict=True)):
        for ch in range(field.shape[2]):
            member[x, y, ch] = np.nextafter(member[x, y, ch], up if sign[m, ch] > 0 else down)
    if (member < 0).any() or not (member != field).any():
        raise ValueError(f"member {seed} is negative or equals the field")
    return member
