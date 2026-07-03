"""Cubical-persistence signature of a density field, so the compiler can specify
arrangement (a ring, a lattice) and not just bulk statistics.

Occupancy and gyration are arrangement-blind: a ring and a disk of equal area and spread
map to the same scalars, so a search that scores only on them cannot tell "hold the loop"
from "fill the loop in". The fix is a topological descriptor. We read the summed-mass field
as a greyscale image and take its cubical persistence: H0 tracks connected high-density
bodies, H1 tracks the loops they enclose (a ring has one persistent H1 class, a disk none).

Design of the signature (fixed so every field maps into one comparable vector):
  - The field is normalised by its own max to [0, 1], because we specify the shape of the
    arrangement, not its absolute density; a mask target and a live creature of the same
    form must compare as close even at different mass scales.
  - Filtration is the negated density, so the sublevel sets of gudhi's CubicalComplex are
    the superlevel (high-density) sets of the field: bright regions are the object. The
    filtration therefore ranges exactly over [-1, 0] (birth) with persistence in [0, 1].
  - Each diagram becomes a persistence image on a fixed RESOLUTION x RESOLUTION grid over
    that (birth, persistence) box, gaussian-splatted with bandwidth SIGMA and weighted by
    persistence so a dominant loop dominates and pixel-scale noise (low persistence) barely
    registers. H0 and H1 images are concatenated into one fixed-length vector, so every
    field, whatever its mass or component count, produces the same-length comparable
    signature. Essential H0 classes (death = +inf) are clipped to the top of the
    filtration (0.0), giving the dominant body a persistence equal to its peak density.
"""

from __future__ import annotations

import gudhi
import numpy as np

RESOLUTION = 24
BIRTH_RANGE = (-1.0, 0.0)
PERS_RANGE = (0.0, 1.0)
SIGMA = 0.04
MIN_PERSISTENCE = 0.1

_BIRTH_CENTERS = np.linspace(BIRTH_RANGE[0], BIRTH_RANGE[1], RESOLUTION)
_PERS_CENTERS = np.linspace(PERS_RANGE[0], PERS_RANGE[1], RESOLUTION)
_SIGNATURE_LENGTH = 2 * RESOLUTION * RESOLUTION


def _diagrams(field2d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (H0, H1) persistence diagrams as (k, 2) birth/persistence arrays for the
    superlevel-set filtration of the field. An empty field has no topology and returns two
    empty diagrams, which maps to a zero signature (maximally far from any nonempty target,
    the correct semantics for a rule that annihilated the form)."""
    fmax = float(field2d.max())
    if fmax <= 1e-9:
        empty = np.empty((0, 2))
        return empty, empty
    negated = -(field2d / fmax)
    complex_ = gudhi.CubicalComplex(top_dimensional_cells=negated)
    complex_.persistence()
    out: list[np.ndarray] = []
    for dim in (0, 1):
        intervals = complex_.persistence_intervals_in_dimension(dim)
        if len(intervals) == 0:
            out.append(np.empty((0, 2)))
            continue
        births = intervals[:, 0]
        deaths = np.where(np.isinf(intervals[:, 1]), BIRTH_RANGE[1], intervals[:, 1])
        out.append(np.stack([births, deaths - births], axis=1))
    return out[0], out[1]


def _diagram_to_image(diagram: np.ndarray) -> np.ndarray:
    if len(diagram) == 0:
        return np.zeros(RESOLUTION * RESOLUTION)
    births = diagram[:, 0]
    pers = diagram[:, 1]
    db = _BIRTH_CENTERS[:, None] - births[None, :]
    dp = _PERS_CENTERS[:, None] - pers[None, :]
    gauss_b = np.exp(-(db * db) / (2.0 * SIGMA * SIGMA))
    gauss_p = np.exp(-(dp * dp) / (2.0 * SIGMA * SIGMA))
    image = np.einsum("in,jn,n->ij", gauss_b, gauss_p, pers)
    return image.reshape(-1)


def persistence_image(field2d: np.ndarray) -> np.ndarray:
    """Fixed-length H0||H1 persistence-image signature of a 2D summed-mass field."""
    h0, h1 = _diagrams(field2d)
    return np.concatenate([_diagram_to_image(h0), _diagram_to_image(h1)])


def topo_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def feature_counts(
    field2d: np.ndarray, min_persistence: float = MIN_PERSISTENCE
) -> tuple[int, int]:
    """Count H0 bodies and H1 loops above min_persistence, dropping pixel-scale noise."""
    h0, h1 = _diagrams(field2d)
    n0 = int((h0[:, 1] >= min_persistence).sum()) if len(h0) else 0
    n1 = int((h1[:, 1] >= min_persistence).sum()) if len(h1) else 0
    return n0, n1
