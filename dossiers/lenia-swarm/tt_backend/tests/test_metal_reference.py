"""Pin the float64 Metal-semantics reference to the Swift Metal pipeline.

The fixture is shared with LeniaCoreTests, which checks that Swift still compiles the same
kernels and that metal-full still produces the same mass, so both sides read one file.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from tt_lenia.numpy_ref import metal

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "Tests"
    / "LeniaCoreTests"
    / "Fixtures"
    / "flowlenia-metal-torus.json"
)


def _array(entry: dict) -> np.ndarray:
    values = np.frombuffer(base64.b64decode(entry["data"]), dtype="<f4")
    return values.reshape(entry["shape"])


def test_rollout_matches_swift_metal():
    raw = json.loads(FIXTURE.read_text())
    arrays = {
        key: _array(raw[key]) for key in raw if key.startswith("kernel_") and key != "kernel_c0"
    }
    arrays["kernel_c0"] = np.array(raw["kernel_c0"])
    kernels = metal.MetalKernels.from_reference(arrays)
    cfg = metal.MetalStepConfig(**raw["step_config"])
    mass = _array(raw["mass"]["0"])
    for steps in (1, 8):
        expected = _array(raw["mass"][str(steps)])
        actual = metal.rollout(mass, kernels, cfg, steps)
        error = np.abs(actual - expected).max()
        print(f"METAL_REFERENCE steps={steps} max_abs={error:.3e}")
        assert error < 1e-5
