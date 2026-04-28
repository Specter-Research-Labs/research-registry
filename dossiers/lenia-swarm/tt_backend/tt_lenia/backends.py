from __future__ import annotations

from .config import BatchedConfig, CompiledKernels
from .engine import TTFlowLeniaEngine
from .numpy_ref.engine import NumpyFlowLeniaEngine

REFERENCE_BACKEND = "reference"
TT_BACKEND = "tt"


def uses_ttnn_runtime(backend: str) -> bool:
    return backend == TT_BACKEND


def make_reference_engine(
    config: BatchedConfig,
    kernels: CompiledKernels,
):
    return NumpyFlowLeniaEngine(config, kernels)


def make_runtime_engine(
    backend: str,
    config: BatchedConfig,
    kernels: CompiledKernels,
    *,
    device=None,
):
    if backend == TT_BACKEND:
        return TTFlowLeniaEngine(
            config,
            kernels,
            device=device,
            front_half_mode="dft_ttlang",
            reintegration_mode="ttlang",
        )
    raise ValueError(f"Unknown TT runtime backend: {backend}. Expected '{TT_BACKEND}'.")
