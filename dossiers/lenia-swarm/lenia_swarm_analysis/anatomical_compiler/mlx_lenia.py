"""Flow Lenia forward map in MLX, a faithful port of the MLX-Swift engine.

This reimplements the genotype -> rollout map that LeniaCLI runs on Metal, but in
MLX-Python so the whole population evolves on the GPU in unified memory and the
evolution-strategy inverse loop never pays the per-genotype subprocess cost. It
targets exactly one regime, flowlenia_2022_paper_equations on a torus, the regime
the compiler's dataset was sampled from; any other mode is rejected rather than
silently approximated.

The math mirrors Sources/LeniaCore/Core/FlowLenia.swift line for line: free-kernel
sum-of-Gaussians profiles, FFT convolution, Gaussian growth, a Sobel flow field
F = grad(U)(1-alpha) - grad(mass)(alpha), and the semi-Lagrangian mass-conserving
reintegration over a (2*dd+1)^2 neighbourhood. The batch axis carries the whole
genotype population, so a single compiled step advances every candidate at once.

Array layout matches the Swift engine: the state A is [B, sx, sy, C], spatial FFTs
run over axes (1, 2), and the per-cell flow carries a 2-vector on axis 3 ordered
[dy, dx] (component 0 indexes the sy axis, component 1 the sx axis), matching the
position grid pos = stack([Y, X]).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mlx.core as mx
import numpy as np


@dataclass(frozen=True)
class LeniaConfig:
    sx: int
    sy: int
    channels: int
    connectivity: list[list[int]]
    dt: float
    n: int
    theta_a: float
    dd: int
    sigma: float
    nbk: int
    c0: tuple[int, ...]
    c1: tuple[tuple[int, ...], ...]

    @classmethod
    def from_base_config(cls, config: dict[str, Any]) -> LeniaConfig:
        mode = config["implementation"]["mode"]
        if mode != "flowlenia_2022_paper_equations":
            raise ValueError(
                f"mlx_lenia only implements flowlenia_2022_paper_equations, got {mode!r}"
            )
        border = config["reintegration"]["border"]
        if border != "torus":
            raise ValueError(f"mlx_lenia only implements the torus border, got {border!r}")
        channels = int(config["channels"])
        connectivity = [[int(v) for v in row] for row in config["connectivity"]]
        c0: list[int] = []
        c1_lists: list[list[int]] = [[] for _ in range(channels)]
        kernel = 0
        for source in range(channels):
            for dest in range(channels):
                for _ in range(connectivity[source][dest]):
                    c0.append(source)
                    c1_lists[dest].append(kernel)
                    kernel += 1
        return cls(
            sx=int(config["grid"]["sx"]),
            sy=int(config["grid"]["sy"]),
            channels=channels,
            connectivity=connectivity,
            dt=float(config["flow"]["dt"]),
            n=int(config["flow"]["n"]),
            theta_a=float(config["flow"]["theta_A"]),
            dd=int(config["reintegration"]["dd"]),
            sigma=float(config["reintegration"]["sigma"]),
            nbk=kernel,
            c0=tuple(c0),
            c1=tuple(tuple(k) for k in c1_lists),
        )


@dataclass
class GenotypeBatch:
    """A population of genotypes as stacked MLX arrays, free-kernel layout."""

    R: mx.array        # [B]
    r: mx.array        # [B, nbK]
    m: mx.array        # [B, nbK]
    s: mx.array        # [B, nbK]
    h: mx.array        # [B, nbK]
    a: mx.array        # [B, nbK, nbump]
    b: mx.array        # [B, nbK, nbump]
    w: mx.array        # [B, nbK, nbump]

    @classmethod
    def from_param_dicts(cls, params: list[dict[str, Any]]) -> GenotypeBatch:
        def stack(key: str) -> np.ndarray:
            return np.asarray([p[key] for p in params], dtype=np.float32)

        return cls(
            R=mx.array(np.asarray([p["R"] for p in params], dtype=np.float32)),
            r=mx.array(stack("r")),
            m=mx.array(stack("m")),
            s=mx.array(stack("s")),
            h=mx.array(stack("h")),
            a=mx.array(stack("a")),
            b=mx.array(stack("b")),
            w=mx.array(stack("w")),
        )

    @property
    def batch(self) -> int:
        return self.R.shape[0]


@dataclass
class CompiledKernels:
    fK: mx.array       # [B, sx, sy, nbK] complex
    m: mx.array        # [B, nbK]
    s: mx.array        # [B, nbK]
    h: mx.array        # [B, nbK]
    c0_idxs: mx.array  # [nbK] int32
    c1_mask: mx.array  # [C, nbK]


def _roll(a: mx.array, shift: tuple[int, int], axis: tuple[int, int]) -> mx.array:
    # mlx's type stubs declare shift/axis as 1-tuples, but the runtime accepts the
    # multi-axis form; this wrapper isolates the single suppression for that stub bug.
    return mx.roll(a, shift, axis)  # ty: ignore[invalid-argument-type]


def _distance_base(config: LeniaConfig) -> mx.array:
    mid_x = config.sx // 2
    mid_y = config.sy // 2
    coords_x = mx.arange(config.sx, dtype=mx.float32) - mid_x
    coords_y = mx.arange(config.sy, dtype=mx.float32) - mid_y
    x = mx.broadcast_to(coords_x.reshape(config.sx, 1), (config.sx, config.sy))
    y = mx.broadcast_to(coords_y.reshape(1, config.sy), (config.sx, config.sy))
    return mx.sqrt(x * x + y * y)


def _fftshift2(x: mx.array) -> mx.array:
    return _roll(x, (x.shape[1] // 2, x.shape[2] // 2), (1, 2))


def position_grid(config: LeniaConfig) -> mx.array:
    coords_x = mx.arange(config.sx, dtype=mx.float32)
    coords_y = mx.arange(config.sy, dtype=mx.float32)
    x = mx.broadcast_to(coords_x.reshape(config.sx, 1), (config.sx, config.sy))
    y = mx.broadcast_to(coords_y.reshape(1, config.sy), (config.sx, config.sy))
    pos = mx.stack([y, x], axis=-1) + 0.5          # [sx, sy, 2], order [Y, X]
    return pos.reshape(1, config.sx, config.sy, 2, 1)


def compile_kernels(genotype: GenotypeBatch, config: LeniaConfig) -> CompiledKernels:
    d_base = _distance_base(config)[None, :, :, None]            # [1, sx, sy, 1]
    divisor = (genotype.R[:, None] * genotype.r)[:, None, None, :]  # [B, 1, 1, nbK]
    d = d_base / divisor                                        # [B, sx, sy, nbK]
    d_exp = d[..., None]                                        # [B, sx, sy, nbK, 1]
    a = genotype.a[:, None, None, :, :]                         # [B, 1, 1, nbK, nbump]
    b = genotype.b[:, None, None, :, :]
    w = genotype.w[:, None, None, :, :]
    diff = d_exp - a
    profile = (b * mx.exp(-(diff * diff) / (2.0 * w * w))).sum(axis=-1)  # [B, sx, sy, nbK]
    sum_k = profile.sum(axis=(1, 2), keepdims=True)
    nk = profile / sum_k
    fk = mx.fft.fft2(_fftshift2(nk), axes=[1, 2])
    return CompiledKernels(
        fK=fk,
        m=genotype.m,
        s=genotype.s,
        h=genotype.h,
        c0_idxs=mx.array(np.asarray(config.c0, dtype=np.int32)),
        c1_mask=mx.array(
            np.asarray(
                [[1.0 if k in config.c1[c] else 0.0 for k in range(config.nbk)]
                 for c in range(config.channels)],
                dtype=np.float32,
            )
        ),
    )


def _growth(u: mx.array, m: mx.array, s: mx.array, h: mx.array) -> mx.array:
    m_b = m.reshape(m.shape[0], 1, 1, m.shape[1])
    s_b = s.reshape(s.shape[0], 1, 1, s.shape[1])
    h_b = h.reshape(h.shape[0], 1, 1, h.shape[1])
    diff = (u - m_b) / s_b
    return (2.0 * mx.exp(-(diff * diff) / 2.0) - 1.0) * h_b


def _sobel_periodic(a: mx.array) -> mx.array:
    a00 = _roll(a, (1, 1), (1, 2))
    a01 = _roll(a, (1, 0), (1, 2))
    a02 = _roll(a, (1, -1), (1, 2))
    a10 = _roll(a, (0, 1), (1, 2))
    a12 = _roll(a, (0, -1), (1, 2))
    a20 = _roll(a, (-1, 1), (1, 2))
    a21 = _roll(a, (-1, 0), (1, 2))
    a22 = _roll(a, (-1, -1), (1, 2))
    gx = (a00 + 2.0 * a10 + a20) - (a02 + 2.0 * a12 + a22)
    gy = (a00 + 2.0 * a01 + a02) - (a20 + 2.0 * a21 + a22)
    return mx.stack([gy, gx], axis=3)


def compute_flow(a: mx.array, kernels: CompiledKernels, config: LeniaConfig) -> mx.array:
    fa = mx.fft.fft2(a, axes=[1, 2])
    fak = mx.take(fa, kernels.c0_idxs, axis=3)
    uk = mx.fft.ifft2(fak * kernels.fK, axes=[1, 2]).real
    g = _growth(uk, kernels.m, kernels.s, kernels.h)
    growth_field = mx.matmul(g, kernels.c1_mask.T)
    nabla_u = _sobel_periodic(growth_field)
    mass = a.sum(axis=-1, keepdims=True)
    nabla_a = _sobel_periodic(mass)
    alpha = mx.clip((mass / config.theta_a) ** config.n, 0.0, 1.0)
    alpha_exp = alpha[:, :, :, None, :]
    f = nabla_u * (1.0 - alpha_exp) - nabla_a * alpha_exp
    max_flow = float(config.dd) - config.sigma
    return mx.clip(f, -max_flow, max_flow)


def reintegration(
    x: mx.array, f: mx.array, pos_grid: mx.array, config: LeniaConfig
) -> mx.array:
    dd = config.dd
    sigma = config.sigma
    ma = float(dd) - sigma
    clip_max = min(1.0, 2.0 * sigma)
    area_scale = 1.0 / (4.0 * sigma * sigma)
    sx, sy = config.sx, config.sy

    out = mx.zeros_like(x)
    torus_shifts = [(iy, ix) for ix in (-sx, 0, sx) for iy in (-sy, 0, sy)
                    if not (ix == 0 and iy == 0)]
    for dx in range(-dd, dd + 1):
        for dy in range(-dd, dd + 1):
            xr = _roll(x, (dx, dy), (1, 2))
            pgr = _roll(pos_grid, (dx, dy), (1, 2))
            fr = _roll(f, (dx, dy), (1, 2))
            mur = pgr + mx.clip(config.dt * fr, -ma, ma)
            d_min = mx.abs(pos_grid - mur)
            for iy, ix in torus_shifts:
                shift = mx.array([float(iy), float(ix)]).reshape(1, 1, 1, 2, 1)
                d_min = mx.minimum(d_min, mx.abs(pos_grid - (mur + shift)))
            sz = mx.clip(0.5 - d_min + sigma, 0.0, clip_max)
            area = sz[:, :, :, 0, :] * sz[:, :, :, 1, :]
            out = out + xr * area
    return out * area_scale


_STEP_CACHE: dict[tuple[Any, ...], Any] = {}


def _config_key(config: LeniaConfig, compile_step: bool) -> tuple[Any, ...]:
    return (
        config.sx, config.sy, config.channels, config.nbk, config.dt, config.n,
        config.theta_a, config.dd, config.sigma, config.c0, config.c1, compile_step,
    )


def _build_step(config: LeniaConfig, compile_step: bool):
    def flow_fn(a: mx.array, fk: mx.array, m: mx.array, s: mx.array, h: mx.array,
                c0_idxs: mx.array, c1_mask: mx.array) -> mx.array:
        kernels = CompiledKernels(fK=fk, m=m, s=s, h=h, c0_idxs=c0_idxs, c1_mask=c1_mask)
        return compute_flow(a, kernels, config)

    def reint_fn(a: mx.array, f: mx.array, pos_grid: mx.array) -> mx.array:
        return reintegration(a, f, pos_grid, config)

    flow = mx.compile(flow_fn) if compile_step else flow_fn
    reint = mx.compile(reint_fn) if compile_step else reint_fn

    def step(a: mx.array, pos_grid: mx.array, kernels: CompiledKernels) -> mx.array:
        f = flow(a, kernels.fK, kernels.m, kernels.s, kernels.h,
                 kernels.c0_idxs, kernels.c1_mask)
        return reint(a, f, pos_grid)

    return step


def make_step(config: LeniaConfig, *, compile_step: bool = True):
    """Return a single-step closure. The flow stage (FFT convolution) and the
    reintegration stage (the ~(2*dd+1)^2 advection loop) are compiled separately;
    MLX's compiler cannot fuse the FFT and the long roll chain into one graph, so
    splitting them is what makes mx.compile usable here.

    The compiled step is cached by regime so repeated rollouts (an ES generation, a
    MAP-Elites batch) reuse one compiled graph instead of recompiling each call; MLX
    still specialises per input shape internally."""
    key = _config_key(config, compile_step)
    cached = _STEP_CACHE.get(key)
    if cached is None:
        cached = _build_step(config, compile_step)
        _STEP_CACHE[key] = cached
    return cached


def rollout(
    a0: mx.array,
    genotype: GenotypeBatch,
    config: LeniaConfig,
    steps: int,
    *,
    pos_grid: mx.array | None = None,
    eval_every: int = 64,
    compile_step: bool = True,
) -> mx.array:
    grid = position_grid(config) if pos_grid is None else pos_grid
    kernels = compile_kernels(genotype, config)
    step = make_step(config, compile_step=compile_step)
    a = a0
    for t in range(steps):
        a = step(a, grid, kernels)
        if (t + 1) % eval_every == 0:
            mx.eval(a)
    mx.eval(a)
    return a


def make_init(config: LeniaConfig, *, seed: int, center: tuple[int, int], size: int,
              batch: int = 1) -> mx.array:
    """Build the initial field, a square uniform[0,1] patch on a zero background,
    matching the regime's init spec (single patch, single channel)."""
    key = mx.random.key(seed)
    a = mx.zeros((batch, config.sx, config.sy, config.channels))
    half = size // 2
    x0, x1 = center[0] - half, center[0] - half + size
    y0, y1 = center[1] - half, center[1] - half + size
    patch = mx.random.uniform(shape=(batch, size, size, config.channels), key=key)
    a[:, x0:x1, y0:y1, :] = patch
    return a
