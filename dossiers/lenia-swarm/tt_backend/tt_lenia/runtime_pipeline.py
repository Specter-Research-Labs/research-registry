from __future__ import annotations

from collections.abc import Callable
import time

import numpy as np

from .config import BatchedConfig, CompiledKernels
from .outputs import StepOutputs
from .stages.flow import compute_flow
from .stages.gather_spectra import gather_kernel_spectra_numpy
from .stages.growth import growth_bell, growth_reduce
from .stages.reintegration import build_pos_grid, reintegrate


ReintegrationFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _record_timing(timings: dict[str, float] | None, name: str, started_at: float) -> None:
    if timings is None:
        return
    timings[name] = timings.get(name, 0.0) + (time.perf_counter() - started_at)


def _fft_forward_numpy(mass: np.ndarray) -> np.ndarray:
    return np.fft.fft2(mass, axes=(1, 2))


def _fft_inverse_numpy(spectra: np.ndarray) -> np.ndarray:
    return np.fft.ifft2(spectra, axes=(1, 2)).real.astype(np.float32)


def execute_front_half_host_step(
    config: BatchedConfig,
    kernels: CompiledKernels,
    mass: np.ndarray,
    *,
    capture_stages: bool = False,
    timings: dict[str, float] | None = None,
) -> StepOutputs:
    started_at = time.perf_counter()
    fft_out = _fft_forward_numpy(mass)
    _record_timing(timings, "fft", started_at)
    started_at = time.perf_counter()
    spec_re, spec_im = gather_kernel_spectra_numpy(
        fft_out.real.astype(np.float32, copy=False),
        fft_out.imag.astype(np.float32, copy=False),
        kernels.fK.real.astype(np.float32, copy=False),
        kernels.fK.imag.astype(np.float32, copy=False),
        kernels.c0_idxs,
    )
    _record_timing(timings, "spectra", started_at)
    spectra = (spec_re + 1j * spec_im).astype(np.complex64)
    started_at = time.perf_counter()
    uk = _fft_inverse_numpy(spectra)
    _record_timing(timings, "ifft", started_at)
    started_at = time.perf_counter()
    growth_out = growth_bell(uk, kernels.m, kernels.s, kernels.h)
    u = growth_reduce(growth_out, kernels.c1_mask)
    _record_timing(timings, "growth", started_at)
    if not capture_stages:
        return StepOutputs(mass=mass, u=u)
    return StepOutputs(
        mass=mass,
        fft_out=fft_out,
        spectra=spectra,
        uk=uk,
        growth_out=growth_out,
        u=u,
    )


def execute_post_spectral_host_step(
    config: BatchedConfig,
    kernels: CompiledKernels,
    mass: np.ndarray,
    uk: np.ndarray,
    *,
    fft_out: np.ndarray | None = None,
    spectra: np.ndarray | None = None,
    capture_stages: bool = False,
    pos_grid: np.ndarray | None = None,
    reintegration_impl: ReintegrationFn | None = None,
) -> StepOutputs:
    grid = build_pos_grid(config.sx, config.sy) if pos_grid is None else pos_grid
    if reintegration_impl is None:
        def reintegrate_fn(current_mass: np.ndarray, flow: np.ndarray) -> np.ndarray:
            return reintegrate(
                current_mass,
                flow,
                pos_grid=grid,
                dt=config.dt,
                dd=config.dd,
                sigma=config.sigma,
                use_torus=config.border == "torus",
                sx=config.sx,
                sy=config.sy,
            )
    else:
        reintegrate_fn = reintegration_impl

    growth_out = growth_bell(uk, kernels.m, kernels.s, kernels.h)
    u = growth_reduce(growth_out, kernels.c1_mask)
    return execute_post_growth_host_step(
        config,
        mass,
        u,
        fft_out=fft_out,
        spectra=spectra,
        uk=uk,
        growth_out=growth_out,
        capture_stages=capture_stages,
        reintegration_impl=reintegrate_fn,
    )


def execute_post_growth_host_step(
    config: BatchedConfig,
    mass: np.ndarray,
    u: np.ndarray,
    *,
    fft_out: np.ndarray | None = None,
    spectra: np.ndarray | None = None,
    uk: np.ndarray | None = None,
    growth_out: np.ndarray | None = None,
    capture_stages: bool = False,
    pos_grid: np.ndarray | None = None,
    reintegration_impl: ReintegrationFn | None = None,
) -> StepOutputs:
    grid = build_pos_grid(config.sx, config.sy) if pos_grid is None else pos_grid
    if reintegration_impl is None:
        def reintegrate_fn(current_mass: np.ndarray, flow: np.ndarray) -> np.ndarray:
            return reintegrate(
                current_mass,
                flow,
                pos_grid=grid,
                dt=config.dt,
                dd=config.dd,
                sigma=config.sigma,
                use_torus=config.border == "torus",
                sx=config.sx,
                sy=config.sy,
            )
    else:
        reintegrate_fn = reintegration_impl

    flow = compute_flow(
        u,
        mass,
        theta_a=config.theta_a,
        n=config.n,
        alpha_mode=config.implementation.alpha_mode,
        flow_clip=config.implementation.flow_clip,
        chem_channel=config.chem_channel,
        chem_include_in_mass=config.chem_include_in_mass,
        dd=config.dd,
        sigma=config.sigma,
    )
    return execute_post_flow_host_step(
        config,
        mass,
        flow,
        fft_out=fft_out,
        spectra=spectra,
        uk=uk,
        growth_out=growth_out,
        u=u,
        capture_stages=capture_stages,
        pos_grid=grid,
        reintegration_impl=reintegrate_fn,
    )


def execute_post_flow_host_step(
    config: BatchedConfig,
    mass: np.ndarray,
    flow: np.ndarray,
    *,
    fft_out: np.ndarray | None = None,
    spectra: np.ndarray | None = None,
    uk: np.ndarray | None = None,
    growth_out: np.ndarray | None = None,
    u: np.ndarray | None = None,
    capture_stages: bool = False,
    pos_grid: np.ndarray | None = None,
    reintegration_impl: ReintegrationFn | None = None,
) -> StepOutputs:
    grid = build_pos_grid(config.sx, config.sy) if pos_grid is None else pos_grid
    if reintegration_impl is None:
        def reintegrate_fn(current_mass: np.ndarray, current_flow: np.ndarray) -> np.ndarray:
            return reintegrate(
                current_mass,
                current_flow,
                pos_grid=grid,
                dt=config.dt,
                dd=config.dd,
                sigma=config.sigma,
                use_torus=config.border == "torus",
                sx=config.sx,
                sy=config.sy,
            )
    else:
        reintegrate_fn = reintegration_impl

    next_mass = reintegrate_fn(mass, flow)

    if not capture_stages:
        return StepOutputs(mass=next_mass)

    return StepOutputs(
        mass=next_mass,
        fft_out=fft_out,
        spectra=spectra,
        uk=uk,
        growth_out=growth_out,
        u=u,
        flow=flow,
    )


def execute_host_step(
    config: BatchedConfig,
    kernels: CompiledKernels,
    mass: np.ndarray,
    *,
    capture_stages: bool = False,
    pos_grid: np.ndarray | None = None,
    reintegration_impl: ReintegrationFn | None = None,
) -> StepOutputs:
    front_half = execute_front_half_host_step(
        config,
        kernels,
        mass,
        capture_stages=capture_stages,
    )
    return execute_post_growth_host_step(
        config,
        mass,
        front_half.u,
        fft_out=front_half.fft_out,
        spectra=front_half.spectra,
        uk=front_half.uk,
        growth_out=front_half.growth_out,
        capture_stages=capture_stages,
        pos_grid=pos_grid,
        reintegration_impl=reintegration_impl,
    )
