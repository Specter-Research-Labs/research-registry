from __future__ import annotations

from pathlib import Path

import numpy as np

from tt_lenia.config import compile_kernels, load_config, resolve_connectivity, resolve_params
from tt_lenia.runtime_pipeline import _fft_forward_numpy, _fft_inverse_numpy
from tt_lenia.stages.gather_spectra import gather_kernel_spectra_numpy
from tt_lenia.stages.spectral_local import MAX_ROW_ELEMS, TW, compact_spatial_kernels, convolve_compact_spatial_numpy


def _paper_kernels():
    config_path = Path(__file__).resolve().parents[2] / "configs" / "base" / "paper_base_3k_1c_128.json"
    config, raw = load_config(config_path)
    c0, c1 = resolve_connectivity(raw)
    params = resolve_params(raw, config.nb_k)
    kernels = compile_kernels(params, config, c0, c1)
    return config, kernels


def test_compact_spatial_kernels_are_local_for_paper_base() -> None:
    _, kernels = _paper_kernels()
    compact = compact_spatial_kernels(kernels.fK, kernels.c0_idxs)
    areas = [kernel.weights.shape[0] * kernel.weights.shape[1] for kernel in compact]
    assert max(areas) <= 21 * 21


def test_compact_spatial_kernel_guard_accepts_two_channel_paper_base() -> None:
    config_path = Path(__file__).resolve().parents[2] / "configs" / "base" / "paper_base_2c_128.json"
    config, raw = load_config(config_path)
    c0, _ = resolve_connectivity(raw)
    params = resolve_params(raw, config.nb_k)
    kernels = compile_kernels(params, config, c0, [[] for _ in range(config.channels)])
    compact = compact_spatial_kernels(kernels.fK, kernels.c0_idxs)
    max_width = max(kernel.weights.shape[1] for kernel in compact)

    assert TW + max_width - 1 <= MAX_ROW_ELEMS


def test_compact_spatial_convolution_matches_fft_front_half() -> None:
    _, kernels = _paper_kernels()
    compact = compact_spatial_kernels(kernels.fK, kernels.c0_idxs)

    rng = np.random.default_rng(0)
    mass = rng.uniform(0.0, 1.0, size=(2, 128, 128, 1)).astype(np.float32)

    fft_out = _fft_forward_numpy(mass)
    spec_re, spec_im = gather_kernel_spectra_numpy(
        fft_out.real.astype(np.float32, copy=False),
        fft_out.imag.astype(np.float32, copy=False),
        kernels.fK.real.astype(np.float32, copy=False),
        kernels.fK.imag.astype(np.float32, copy=False),
        kernels.c0_idxs,
    )
    uk_fft = _fft_inverse_numpy((spec_re + 1j * spec_im).astype(np.complex64))
    uk_local = convolve_compact_spatial_numpy(mass, compact)

    assert np.allclose(uk_local, uk_fft, atol=5.0e-5, rtol=5.0e-4)
