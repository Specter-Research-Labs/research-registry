from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class StepOutputs:
    mass: np.ndarray
    fft_out: np.ndarray | None = None
    spectra: np.ndarray | None = None
    uk: np.ndarray | None = None
    growth_out: np.ndarray | None = None
    u: np.ndarray | None = None
    flow: np.ndarray | None = None
