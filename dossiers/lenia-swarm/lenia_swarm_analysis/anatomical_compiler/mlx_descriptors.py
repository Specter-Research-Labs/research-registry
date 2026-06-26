"""Phenotype descriptors computed from an MLX rollout, matching the Swift engine.

These reproduce the per-frame reductions in FlowLenia's Metal summary kernels and the
trajectory aggregation in RolloutAccumulator, for the init-robust shape descriptors the
compiler conditions on. Per recorded post-warmup frame (single channel):

    mass       = sum(field)
    variance   = max(mean(field^2) - mean(field)^2, 0)        cell-density variance
    energy     = sum(field^2)
    occupancy  = mean(field > occupancy_threshold)
    centroid   = sum(field * x) / mass  (and y), in cell units + 0.5
    gyration   = sum(field * (dx^2 + dy^2)) / mass             torus min-distance to centroid

Aggregated over the recorded frames: mass_mean and mass_std (population std) over the
per-frame mass; variance_mean, energy_mean, occupancy_mean as plain means; gyration is the
last recorded frame's value, not a mean (matching RolloutAccumulator.lastGyration).

complexity_mean (the multiscale compression metric) is intentionally not reproduced here;
it depends on PNG-compressed sizes of the rendered field and is not part of this surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import mlx.core as mx
import numpy as np

from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    compile_kernels,
    make_step,
    position_grid,
)

DESCRIPTOR_FIELDS: tuple[str, ...] = (
    "mass_mean",
    "mass_std",
    "occupancy_mean",
    "variance_mean",
    "energy_mean",
    "gyration",
)


@dataclass
class FrameStats:
    mass: mx.array       # [B]
    variance: mx.array   # [B]
    energy: mx.array     # [B]
    occupancy: mx.array  # [B]
    gyration: mx.array   # [B]


def _coordinate_grids(config: LeniaConfig) -> tuple[mx.array, mx.array]:
    x = mx.broadcast_to(
        mx.arange(config.sx, dtype=mx.float32).reshape(config.sx, 1),
        (config.sx, config.sy),
    )
    y = mx.broadcast_to(
        mx.arange(config.sy, dtype=mx.float32).reshape(1, config.sy),
        (config.sx, config.sy),
    )
    return x, y


def frame_stats(
    a: mx.array, config: LeniaConfig, occupancy_threshold: float,
    grid_x: mx.array, grid_y: mx.array,
) -> FrameStats:
    field = a.sum(axis=-1)                              # [B, sx, sy], single-channel mass
    cell_count = float(config.sx * config.sy)
    mass = field.sum(axis=(1, 2))
    sum_sq = (field * field).sum(axis=(1, 2))
    mean_cell = mass / cell_count
    variance = mx.maximum(sum_sq / cell_count - mean_cell * mean_cell, 0.0)
    energy = sum_sq
    occupancy = (field > occupancy_threshold).astype(mx.float32).mean(axis=(1, 2))

    safe_mass = mx.maximum(mass, 1e-6)
    center_x = (field * grid_x[None]).sum(axis=(1, 2)) / safe_mass + 0.5
    center_y = (field * grid_y[None]).sum(axis=(1, 2)) / safe_mass + 0.5
    dx = mx.abs(grid_x[None] - center_x[:, None, None])
    dy = mx.abs(grid_y[None] - center_y[:, None, None])
    dx = mx.minimum(dx, float(config.sx) - dx)
    dy = mx.minimum(dy, float(config.sy) - dy)
    gyration = (field * (dx * dx + dy * dy)).sum(axis=(1, 2)) / safe_mass
    return FrameStats(mass=mass, variance=variance, energy=energy,
                      occupancy=occupancy, gyration=gyration)


def rollout_descriptors(
    a0: mx.array,
    genotype: GenotypeBatch,
    config: LeniaConfig,
    *,
    steps: int,
    warmup: int,
    record_interval: int,
    occupancy_threshold: float,
    pos_grid: mx.array | None = None,
    compile_step: bool = True,
) -> np.ndarray:
    """Run the rollout and return the [B, len(DESCRIPTOR_FIELDS)] descriptor matrix,
    sampling at the same post-warmup schedule as the Swift engine."""
    grid = position_grid(config) if pos_grid is None else pos_grid
    kernels = compile_kernels(genotype, config)
    step = make_step(config, compile_step=compile_step)
    grid_x, grid_y = _coordinate_grids(config)

    record_steps = {
        s for s in range(1, steps + 1)
        if s > warmup and (s - warmup) % record_interval == 0
    }
    mass_samples: list[np.ndarray] = []
    variance_samples: list[np.ndarray] = []
    energy_samples: list[np.ndarray] = []
    occupancy_samples: list[np.ndarray] = []
    last_gyration: np.ndarray | None = None

    a = a0
    for t in range(1, steps + 1):
        a = step(a, grid, kernels)
        if t in record_steps:
            stats = frame_stats(a, config, occupancy_threshold, grid_x, grid_y)
            mx.eval(stats.mass, stats.variance, stats.energy, stats.occupancy, stats.gyration)
            mass_samples.append(np.asarray(stats.mass))
            variance_samples.append(np.asarray(stats.variance))
            energy_samples.append(np.asarray(stats.energy))
            occupancy_samples.append(np.asarray(stats.occupancy))
            last_gyration = np.asarray(stats.gyration)
        elif t % 32 == 0:
            mx.eval(a)
    if last_gyration is None:
        raise ValueError("no post-warmup samples recorded; check steps/warmup/interval")

    mass = np.stack(mass_samples, axis=0)
    return np.stack([
        mass.mean(axis=0),
        mass.std(axis=0),
        np.stack(occupancy_samples, axis=0).mean(axis=0),
        np.stack(variance_samples, axis=0).mean(axis=0),
        np.stack(energy_samples, axis=0).mean(axis=0),
        last_gyration,
    ], axis=1)
