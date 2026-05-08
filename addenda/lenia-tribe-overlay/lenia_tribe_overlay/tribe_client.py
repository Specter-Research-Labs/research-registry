from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class StimulusTensor:
    name: str
    stimulus_class: str
    video: np.ndarray  # shape (T, H, W, 3), uint8 frames at TRIBE's expected fps
    duration_seconds: float


@dataclass(frozen=True)
class TribePrediction:
    stimulus_name: str
    voxels: np.ndarray  # shape (n_voxels,) float32 predicted activation


class TribeClient(Protocol):
    """Minimal surface the rest of this dossier depends on.

    Implemented in task #2 once TRIBE v2 weights have been pulled and the
    real forward-pass shape is known. Kept narrow on purpose so the sanity
    gate, ROI mapping, and analysis code can be written and tested against
    a fake before real inference is wired up.
    """

    @property
    def checkpoint_revision(self) -> str: ...

    @property
    def n_voxels(self) -> int: ...

    def predict(self, stimulus: StimulusTensor) -> TribePrediction: ...
