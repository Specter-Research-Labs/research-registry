"""Verify DFT-as-matmul matches numpy.fft.fft2 for grid sizes we care about."""
import numpy as np
import pytest


def dft_matrix(N: int) -> np.ndarray:
    """Construct the N x N DFT matrix W where W[i,j] = exp(-2*pi*i*j/N)."""
    n = np.arange(N)
    return np.exp(-2j * np.pi * np.outer(n, n) / N).astype(np.complex64)


def dft_2d_matmul(x: np.ndarray, W_rows: np.ndarray, W_cols: np.ndarray) -> np.ndarray:
    """2D DFT via two matrix multiplies: W_rows @ x @ W_cols^T."""
    return W_rows @ x @ W_cols.T


@pytest.mark.parametrize("N", [64, 128, 256])
def test_dft_matches_fft_real_input(N: int):
    rng = np.random.default_rng(0)
    x = rng.standard_normal((N, N)).astype(np.float32)

    W = dft_matrix(N)
    result_matmul = dft_2d_matmul(x.astype(np.complex64), W, W)
    result_fft = np.fft.fft2(x)

    assert np.allclose(result_matmul, result_fft, atol=1e-2), (
        f"Max diff: {np.max(np.abs(result_matmul - result_fft))}"
    )


@pytest.mark.parametrize("N", [64, 128, 256])
def test_inverse_dft_roundtrip(N: int):
    rng = np.random.default_rng(1)
    x = rng.standard_normal((N, N)).astype(np.float32)

    W = dft_matrix(N)
    W_inv = np.conj(W) / N

    forward = dft_2d_matmul(x.astype(np.complex64), W, W)
    recovered = dft_2d_matmul(forward, W_inv, W_inv).real

    assert np.allclose(recovered, x, atol=1e-2), (
        f"Max diff: {np.max(np.abs(recovered - x))}"
    )


def test_dft_parseval():
    """Parseval's theorem: energy in spatial domain equals energy in frequency domain / N^2."""
    N = 128
    rng = np.random.default_rng(2)
    x = rng.standard_normal((N, N)).astype(np.float32)

    spatial_energy = np.sum(x * x)
    F = np.fft.fft2(x)
    freq_energy = np.sum(np.abs(F) ** 2) / (N * N)

    assert np.isclose(spatial_energy, freq_energy, rtol=1e-4)
