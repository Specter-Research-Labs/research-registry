from __future__ import annotations

import numpy as np

from .tribe_client import StimulusTensor, TribePrediction


class FakeTribeClient:
    """Stand-in TribeClient used to develop the gate and analysis layer before real
    TRIBE inference is wired up. Returns deterministic, class-conditioned predictions
    chosen so the sanity gate passes for sensible probe sets and fails cleanly when
    obviously broken (e.g. constant predictions, or biomotion_positive below static).

    invariant: the bias table here is fixed; if a future change makes the gate trivially
    pass for any client, that is a bug in the gate, not in this fake.
    """

    _CHECKPOINT = "fake-1"
    _CLASS_BIAS = {
        "static": 0.10,
        "noise": 0.18,
        "grating": 0.22,
        "rigid_motion": 0.28,
        "scrambled": 0.20,
        "biomotion_positive": 0.45,
        "lenia": 0.30,
    }

    def __init__(self, seed: int = 0, n_voxels: int = 1024) -> None:
        self._rng = np.random.default_rng(seed)
        self._n_voxels = n_voxels

    @property
    def checkpoint_revision(self) -> str:
        return self._CHECKPOINT

    @property
    def n_voxels(self) -> int:
        return self._n_voxels

    def predict(self, stimulus: StimulusTensor) -> TribePrediction:
        if stimulus.stimulus_class not in self._CLASS_BIAS:
            raise ValueError(
                f"FakeTribeClient has no bias entry for class {stimulus.stimulus_class!r}; "
                "add one explicitly rather than letting an unseen class default silently."
            )
        bias = self._CLASS_BIAS[stimulus.stimulus_class]
        noise = self._rng.normal(loc=0.0, scale=0.02, size=self._n_voxels).astype(np.float32)
        voxels = (bias + noise).astype(np.float32)
        return TribePrediction(stimulus_name=stimulus.name, voxels=voxels)
