"""Flow Lenia step with the semantics of the Swift Metal pipeline, in a chosen precision.

This mirrors MetalSpectral.swift and MetalPipeline.swift for the torus, non-localized,
mass-alpha configuration that the large searches run. Metal is the semantic authority;
float64 here is the precision yardstick that device backends are measured against.

Layouts follow Metal: mass and affinity are [batch, sx, sy, channels], flow is
[batch, sx, sy, channels, 2] with (flowX, flowY), and kernel spectra are the real
part of the compiled fK, [sx, sy, kernels].
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MetalStepConfig:
    dt: float
    dd: int
    sigma: float
    theta_a: float
    n: int
    clip_flow: bool


@dataclass(frozen=True)
class MetalKernels:
    spectra: np.ndarray
    c0: np.ndarray
    output_weights: np.ndarray
    m: np.ndarray
    s: np.ndarray
    h: np.ndarray

    @classmethod
    def from_reference(cls, arrays: dict[str, np.ndarray]) -> "MetalKernels":
        fk_re = arrays["kernel_fK_re"]
        fk_im = arrays["kernel_fK_im"]
        if fk_re.ndim != 4 or fk_re.shape[0] != 1:
            raise ValueError(f"expected kernel_fK_re of shape [1, sx, sy, K], got {fk_re.shape}")
        if np.abs(fk_im).max() > 1e-5 * np.abs(fk_re).max():
            raise ValueError("Metal transport requires real kernel spectra")
        return cls(
            spectra=fk_re[0],
            c0=arrays["kernel_c0"].astype(np.int64),
            output_weights=arrays["kernel_c1_mask"],
            m=arrays["kernel_m"],
            s=arrays["kernel_s"],
            h=arrays["kernel_h"],
        )


def potential(mass: np.ndarray, kernels: MetalKernels, dtype=np.float64) -> np.ndarray:
    sx, sy = mass.shape[1:3]
    spectra = np.fft.rfft2(mass.astype(dtype), axes=(1, 2))
    response = spectra[..., kernels.c0] * kernels.spectra[:, : sy // 2 + 1].astype(dtype)
    return np.fft.irfft2(response, s=(sx, sy), axes=(1, 2)).astype(dtype)


def affinity(pot: np.ndarray, kernels: MetalKernels, dtype=np.float64) -> np.ndarray:
    m = kernels.m.astype(dtype)
    s = kernels.s.astype(dtype)
    h = kernels.h.astype(dtype)
    diff = (pot - m) / s
    contribution = (dtype(2) * np.exp(dtype(-0.5) * diff * diff) - dtype(1)) * h
    return np.einsum("bxyk,ck->bxyc", contribution, kernels.output_weights.astype(dtype))


def _sobel(field: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    def at(ox: int, oy: int) -> np.ndarray:
        return np.roll(field, (-ox, -oy), axis=(1, 2))

    gx = (at(1, -1) + 2 * at(1, 0) + at(1, 1)) - (at(-1, -1) + 2 * at(-1, 0) + at(-1, 1))
    gy = (at(-1, 1) + 2 * at(0, 1) + at(1, 1)) - (at(-1, -1) + 2 * at(0, -1) + at(1, -1))
    return gx, gy


def flow(u: np.ndarray, mass: np.ndarray, cfg: MetalStepConfig, dtype=np.float64) -> np.ndarray:
    u = u.astype(dtype)
    matter = mass.astype(dtype).sum(axis=-1, keepdims=True)
    gx_a, gy_a = _sobel(matter)
    gx_u, gy_u = _sobel(u)
    alpha = np.clip((matter / dtype(cfg.theta_a)) ** cfg.n, 0, 1)
    flw = np.stack([gx_u * (1 - alpha) - gx_a * alpha, gy_u * (1 - alpha) - gy_a * alpha], axis=-1)
    if cfg.clip_flow:
        max_advection = dtype(cfg.dd) - dtype(cfg.sigma)
        flw = np.clip(flw, -max_advection, max_advection)
    return flw


def reintegrate(
    mass: np.ndarray, flw: np.ndarray, cfg: MetalStepConfig, dtype=np.float64
) -> np.ndarray:
    sx, sy = mass.shape[1:3]
    max_advection = dtype(cfg.dd) - dtype(cfg.sigma)
    if not min(sx, sy) * 0.5 > cfg.dd + max_advection:
        raise ValueError(f"torus {sx}x{sy} is too small for local transport with dd {cfg.dd}")
    sigma = dtype(cfg.sigma)
    clip_max = min(dtype(1), 2 * sigma)
    mass = mass.astype(dtype)
    shift = np.clip(flw.astype(dtype) * dtype(cfg.dt), -max_advection, max_advection)
    positive = mass > 0
    source_mass = np.where(positive, mass, 0)
    total = np.zeros_like(mass)
    for dx in range(-cfg.dd, cfg.dd + 1):
        for dy in range(-cfg.dd, cfg.dd + 1):
            src_mass = np.roll(source_mass, (dx, dy), axis=(1, 2))
            src_shift = np.roll(shift, (dx, dy), axis=(1, 2))
            d_x = np.abs(dtype(dx) - src_shift[..., 0])
            d_y = np.abs(dtype(dy) - src_shift[..., 1])
            sz_y = np.clip(0.5 - d_y + sigma, 0, clip_max)
            sz_x = np.clip(0.5 - d_x + sigma, 0, clip_max)
            total += src_mass * sz_y * sz_x
    return total * (1 / (4 * sigma * sigma))


def step(
    mass: np.ndarray, kernels: MetalKernels, cfg: MetalStepConfig, dtype=np.float64
) -> dict[str, np.ndarray]:
    pot = potential(mass, kernels, dtype)
    u = affinity(pot, kernels, dtype)
    flw = flow(u, mass, cfg, dtype)
    return {
        "potential": pot,
        "affinity": u,
        "flow": flw,
        "mass": reintegrate(mass, flw, cfg, dtype),
    }


def rollout(
    mass: np.ndarray, kernels: MetalKernels, cfg: MetalStepConfig, steps: int, dtype=np.float64
) -> np.ndarray:
    state = mass.astype(dtype)
    for _ in range(steps):
        state = step(state, kernels, cfg, dtype)["mass"]
    return state
