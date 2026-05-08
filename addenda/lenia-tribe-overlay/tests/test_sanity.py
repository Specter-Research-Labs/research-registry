from __future__ import annotations

import numpy as np
import pytest

from lenia_tribe_overlay.probes import probe_set
from lenia_tribe_overlay.sanity import VARIANCE_FLOOR, SanityFailure, run_gate
from lenia_tribe_overlay.tribe_client import StimulusTensor, TribePrediction
from lenia_tribe_overlay.tribe_fake import FakeTribeClient


def test_fake_client_passes_gate() -> None:
    client = FakeTribeClient(seed=0)
    report = run_gate(client, seed=0)
    assert report.checkpoint_revision == "fake-1"
    assert report.across_stimulus_variance > VARIANCE_FLOOR
    assert set(report.per_stimulus_mean) == {s.name for s in probe_set(seed=0)}


def test_constant_client_fails_variance_check() -> None:
    class ConstantClient:
        checkpoint_revision = "constant"
        n_voxels = 16

        def predict(self, stimulus: StimulusTensor) -> TribePrediction:
            return TribePrediction(stimulus.name, np.full(self.n_voxels, 0.5, dtype=np.float32))

    with pytest.raises(SanityFailure, match="variance collapse"):
        run_gate(ConstantClient(), seed=0)


def test_probe_set_has_required_classes() -> None:
    classes = {s.stimulus_class for s in probe_set()}
    assert "biomotion_positive" in classes
    assert "static" in classes
