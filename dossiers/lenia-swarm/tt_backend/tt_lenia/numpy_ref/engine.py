"""NumPy reference engine for Flow Lenia.

Composes the 7 pipeline stages into a full simulation step.
This is the validation oracle for the TTNN backend.
"""
from __future__ import annotations

import numpy as np

from ..config import BatchedConfig, CompiledKernels
from ..outputs import StepOutputs
from ..runtime_pipeline import execute_host_step
from . import stages


class NumpyFlowLeniaEngine:
    def __init__(self, config: BatchedConfig, kernels: CompiledKernels):
        self.config = config
        self.kernels = kernels
        self.pos_grid = stages.build_pos_grid(config.sx, config.sy)
        self.use_torus = config.border == "torus"

    def step(self, mass: np.ndarray, capture_stages: bool = False) -> StepOutputs:
        return execute_host_step(
            self.config,
            self.kernels,
            mass,
            capture_stages=capture_stages,
            pos_grid=self.pos_grid,
        )

    def run(self, mass: np.ndarray, steps: int) -> np.ndarray:
        """Run multiple steps, return final mass."""
        state = mass
        for _ in range(steps):
            result = self.step(state)
            state = result.mass
        return state
