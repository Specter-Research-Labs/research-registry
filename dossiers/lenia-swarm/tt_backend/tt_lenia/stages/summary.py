"""Stage 7: Mass summary — parallel reduction over spatial dims."""
from __future__ import annotations

import numpy as np


def mass_summary(A: np.ndarray) -> dict[str, np.ndarray]:
    """Compute mass statistics per batch element.

    A: [batch, sx, sy, channels]
    Returns dict with total_mass [batch, channels].
    """
    return {"total_mass": A.sum(axis=(1, 2))}
