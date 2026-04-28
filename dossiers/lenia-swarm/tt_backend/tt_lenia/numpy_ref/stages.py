"""Pure-NumPy implementations of all 7 Flow Lenia pipeline stages.

Each function matches the corresponding Swift code in FlowLenia.swift
and the paper equations in docs/internals/FlowLeniaImplementationMap.md.

Tensor layout: [batch, sx, sy, ...] with float32 throughout.
"""
from __future__ import annotations

import numpy as np


def fft_forward(A: np.ndarray) -> np.ndarray:
    """Stage 1: 2D FFT of mass field. A: [batch, sx, sy, channels]."""
    return np.fft.fft2(A, axes=(1, 2))


def gather_kernel_spectra(
    fA: np.ndarray, fK: np.ndarray, c0_idxs: np.ndarray
) -> np.ndarray:
    """Stage 2: Spectral multiply — select source channel per kernel, multiply by kernel spectrum.

    fA: [batch, sx, sy, channels] complex
    fK: [1, sx, sy, nb_k] complex
    c0_idxs: [nb_k] int — source channel index per kernel
    Returns: [batch, sx, sy, nb_k] complex
    """
    fAK = fA[:, :, :, c0_idxs]
    return fAK * fK


def fft_inverse(fAKfK: np.ndarray) -> np.ndarray:
    """Stage 3: Inverse 2D FFT, take real part. Returns [batch, sx, sy, nb_k]."""
    return np.fft.ifft2(fAKfK, axes=(1, 2)).real.astype(np.float32)


def growth(
    UK: np.ndarray, m: np.ndarray, s: np.ndarray, h: np.ndarray
) -> np.ndarray:
    """Stage 4a: Gaussian bell growth function.

    UK: [batch, sx, sy, nb_k]
    m, s, h: [nb_k] (broadcast to [1, 1, 1, nb_k])
    Returns: [batch, sx, sy, nb_k] — scaled growth per kernel
    """
    m_b = m.reshape(1, 1, 1, -1)
    s_b = s.reshape(1, 1, 1, -1)
    h_b = h.reshape(1, 1, 1, -1)
    diff = (UK - m_b) / s_b
    bell = np.exp(-0.5 * diff * diff)
    return (2.0 * bell - 1.0) * h_b


def growth_reduce(
    G: np.ndarray, c1_mask: np.ndarray
) -> np.ndarray:
    """Stage 4b: Route growth to channels via connectivity mask.

    G: [batch, sx, sy, nb_k]
    c1_mask: [channels, nb_k]
    Returns U: [batch, sx, sy, channels]
    """
    return np.einsum("bxyk,ck->bxyc", G, c1_mask)


def mass_field(
    A: np.ndarray, chem_channel: int | None, include_in_mass: bool
) -> np.ndarray:
    """Compute scalar mass field (sum across channels, optionally excluding chem)."""
    total = A.sum(axis=-1, keepdims=True)
    if chem_channel is not None and not include_in_mass:
        chem = A[:, :, :, chem_channel:chem_channel+1]
        total = total - chem
    return total


def sobel_periodic(A: np.ndarray) -> np.ndarray:
    """Sobel gradient on [batch, sx, sy, C] with periodic boundary.

    Returns [batch, sx, sy, 2, C] where dim 3 is (gy, gx).
    Matches sobelBatchedPeriodic in FlowLenia.swift: stacked([gy, gx], axis: 3).
    """
    a00 = np.roll(np.roll(A, 1, axis=1), 1, axis=2)
    a01 = np.roll(A, 1, axis=1)
    a02 = np.roll(np.roll(A, 1, axis=1), -1, axis=2)
    a10 = np.roll(A, 1, axis=2)
    a12 = np.roll(A, -1, axis=2)
    a20 = np.roll(np.roll(A, -1, axis=1), 1, axis=2)
    a21 = np.roll(A, -1, axis=1)
    a22 = np.roll(np.roll(A, -1, axis=1), -1, axis=2)

    gx = (a00 + 2.0 * a10 + a20) - (a02 + 2.0 * a12 + a22)
    gy = (a00 + 2.0 * a01 + a02) - (a20 + 2.0 * a21 + a22)

    return np.stack([gy, gx], axis=3)


def compute_flow(
    U: np.ndarray,
    A: np.ndarray,
    *,
    theta_a: float,
    n: int,
    gradient_boundary: str,
    alpha_mode: str,
    flow_clip: str,
    chem_channel: int | None,
    chem_include_in_mass: bool,
    dd: int,
    sigma: float,
    wall_potential: np.ndarray | None = None,
) -> np.ndarray:
    """Stage 5: Compute flow field from affinity U and mass A.

    U: [batch, sx, sy, channels]
    A: [batch, sx, sy, channels]
    Returns F: [batch, sx, sy, 2, channels] where dim 3 is (fy, fx).
    """
    if wall_potential is not None:
        U = U + wall_potential

    nabla_U = sobel_periodic(U)
    mass = mass_field(A, chem_channel, chem_include_in_mass)
    nabla_A = sobel_periodic(mass)

    if alpha_mode == "mass":
        powered = np.power(mass / theta_a, float(n))
        alpha = np.clip(powered, 0.0, 1.0)
    elif alpha_mode == "per_channel":
        powered = np.power(A / theta_a, float(n))
        alpha = np.clip(powered, 0.0, 1.0)
    else:
        raise ValueError(f"Unknown alpha_mode: {alpha_mode}")

    alpha_exp = np.expand_dims(alpha, axis=3)
    F = (1.0 - alpha_exp) * nabla_U - alpha_exp * nabla_A

    if flow_clip == "always":
        max_flow = float(dd) - sigma
        F = np.clip(F, -max_flow, max_flow)

    return F.astype(np.float32)


def reintegration(
    X: np.ndarray,
    F: np.ndarray,
    *,
    pos_grid: np.ndarray,
    dt: float,
    dd: int,
    sigma: float,
    use_torus: bool,
    sx: int,
    sy: int,
) -> np.ndarray:
    """Stage 6: Mass-conserving advection via reintegration tracking.

    X: [batch, sx, sy, channels] — mass (or any field to advect)
    F: [batch, sx, sy, 2, channels] — flow field, dim 3 is (fy, fx)
    pos_grid: [1, sx, sy, 2, 1] — cell center positions
    Returns: [batch, sx, sy, channels]
    """
    ma = float(dd) - sigma
    clip_max = min(1.0, 2.0 * sigma)
    area_scale = 1.0 / (4.0 * sigma * sigma)

    out = np.zeros_like(X)

    for dx in range(-dd, dd + 1):
        for dy in range(-dd, dd + 1):
            Xr = np.roll(np.roll(X, dx, axis=1), dy, axis=2)
            pgr = np.roll(np.roll(pos_grid, dx, axis=1), dy, axis=2)
            Fr = np.roll(np.roll(F, dx, axis=1), dy, axis=2)

            dtF = dt * Fr
            clipped = np.clip(dtF, -ma, ma)
            mur = pgr + clipped

            if not use_torus:
                min_bound = np.array([sigma, sigma], dtype=np.float32).reshape(1, 1, 1, 2, 1)
                max_bound = np.array([sy - sigma, sx - sigma], dtype=np.float32).reshape(1, 1, 1, 2, 1)
                mur = np.clip(mur, min_bound, max_bound)

            d_min = np.abs(pos_grid - mur)

            if use_torus:
                for ix in [-sx, 0, sx]:
                    for iy in [-sy, 0, sy]:
                        if ix == 0 and iy == 0:
                            continue
                        shift = np.array([iy, ix], dtype=np.float32).reshape(1, 1, 1, 2, 1)
                        d_candidate = np.abs(pos_grid - (mur + shift))
                        d_min = np.minimum(d_min, d_candidate)

            sz = np.clip(0.5 - d_min + sigma, 0.0, clip_max)

            sz_y = sz[:, :, :, 0, :]
            sz_x = sz[:, :, :, 1, :]
            area = sz_y * sz_x

            out = out + Xr * area

    return (out * area_scale).astype(np.float32)


def mass_summary(A: np.ndarray) -> dict[str, np.ndarray]:
    """Stage 7: Compute mass statistics per batch element.

    A: [batch, sx, sy, channels]
    Returns dict with total_mass [batch, channels], etc.
    """
    total_mass = A.sum(axis=(1, 2))
    return {"total_mass": total_mass}


def build_pos_grid(sx: int, sy: int) -> np.ndarray:
    """Build position grid matching FlowLenia.swift posGrid construction.

    Returns [1, sx, sy, 2, 1] where dim 3 is (y, x) and values are cell centers (i+0.5).
    """
    coords_x = np.arange(sx, dtype=np.float32)
    coords_y = np.arange(sy, dtype=np.float32)
    X, Y = np.meshgrid(coords_x, coords_y, indexing="ij")
    pos = np.stack([Y, X], axis=-1) + 0.5
    return pos[np.newaxis, :, :, :, np.newaxis]
