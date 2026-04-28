from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tt_lenia.config import (
    BatchedConfig,
    CompiledKernels,
    compile_kernels,
    load_config,
    resolve_connectivity,
    resolve_params,
)

CONFIGS_DIR = Path(__file__).resolve().parents[1] / ".." / "configs" / "base"


@pytest.fixture
def paper_config_path() -> Path:
    return CONFIGS_DIR / "paper_base_3k_1c_128.json"


@pytest.fixture
def paper_config(paper_config_path: Path) -> tuple[BatchedConfig, dict]:
    return load_config(paper_config_path)


@pytest.fixture
def paper_kernels(paper_config: tuple[BatchedConfig, dict]) -> CompiledKernels:
    config, raw = paper_config
    c0, c1 = resolve_connectivity(raw)
    params = resolve_params(raw, config.nb_k)
    return compile_kernels(params, config, c0, c1)


@pytest.fixture
def random_mass_1c_128() -> np.ndarray:
    rng = np.random.default_rng(42)
    mass = np.zeros((1, 128, 128, 1), dtype=np.float32)
    mass[0, 44:84, 44:84, 0] = rng.uniform(0, 1, size=(40, 40)).astype(np.float32)
    return mass
