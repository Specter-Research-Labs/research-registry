"""Coherence descriptors from an MLX rollout: the signal that separates a coherent,
self-maintaining creature from a space-filling texture of equal mass and spread.

Occupancy and gyration cannot tell a tight organism from a filament lattice, so the
coherent-creature search needs different descriptors, the ones the Swift coherent harvest
scores on: how much of the mass sits in one connected body, how few pieces it breaks into,
whether it holds its shape over time, and whether it moves as a unit. The connected
components are labelled on the CPU (scipy) from the summed-mass field the fast MLX rollout
produces, so the rollout stays on the GPU and only the final field is pulled down.

Per genotype the descriptors are:
    largest_component_fraction  mass in the biggest connected body / total mass
    component_count             number of connected pieces above the occupancy threshold
    gyration_mean               mean radius of gyration over the recorded window
    gyration_std                its std over the window (form-stability; small = holds shape)
    center_velocity             centroid displacement per recorded step (moves as a body)
    occupancy_mean              fraction of cells above the occupancy threshold
"""

from __future__ import annotations

from dataclasses import dataclass

import mlx.core as mx
import numpy as np
from scipy import ndimage

from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import _coordinate_grids
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    compile_kernels,
    make_step,
    position_grid,
)

COHERENCE_FIELDS: tuple[str, ...] = (
    "largest_component_fraction",
    "component_count",
    "gyration_mean",
    "gyration_std",
    "center_velocity",
    "occupancy_mean",
)

_EIGHT = np.ones((3, 3), dtype=bool)


@dataclass
class FrameSample:
    mass: np.ndarray        # [B] total summed mass
    gyration: np.ndarray    # [B]
    occupancy: np.ndarray   # [B]
    center_x: np.ndarray    # [B]
    center_y: np.ndarray    # [B]


def _frame_sample(
    a: mx.array, config: LeniaConfig, occupancy_threshold: float,
    grid_x: mx.array, grid_y: mx.array,
) -> FrameSample:
    field = a.sum(axis=-1)
    mass = field.sum(axis=(1, 2))
    occupancy = (field > occupancy_threshold).astype(mx.float32).mean(axis=(1, 2))
    safe = mx.maximum(mass, 1e-6)
    cx = (field * grid_x[None]).sum(axis=(1, 2)) / safe + 0.5
    cy = (field * grid_y[None]).sum(axis=(1, 2)) / safe + 0.5
    dx = mx.abs(grid_x[None] - cx[:, None, None])
    dy = mx.abs(grid_y[None] - cy[:, None, None])
    dx = mx.minimum(dx, float(config.sx) - dx)
    dy = mx.minimum(dy, float(config.sy) - dy)
    gyr = (field * (dx * dx + dy * dy)).sum(axis=(1, 2)) / safe
    mx.eval(mass, gyr, occupancy, cx, cy)
    return FrameSample(
        mass=np.asarray(mass), gyration=np.asarray(gyr), occupancy=np.asarray(occupancy),
        center_x=np.asarray(cx), center_y=np.asarray(cy),
    )


def _component_metrics(
    field: np.ndarray, occupancy_threshold: float, min_fraction: float = 0.002
) -> tuple[float, int]:
    """Largest connected component mass fraction and component count for one summed-mass
    field. Components below min_fraction of total mass are treated as debris and dropped
    from the count."""
    total = float(field.sum())
    if total < 1e-6:
        return 0.0, 0
    labels, n = ndimage.label(field > occupancy_threshold, structure=_EIGHT)
    if n == 0:
        return 0.0, 0
    masses = ndimage.sum_labels(field, labels, index=np.arange(1, n + 1))
    largest = float(masses.max()) / total
    count = int((masses >= min_fraction * total).sum())
    return largest, count


def rollout_coherence(
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
    """Run the rollout and return the [B, len(COHERENCE_FIELDS)] coherence matrix."""
    grid = position_grid(config) if pos_grid is None else pos_grid
    kernels = compile_kernels(genotype, config)
    step = make_step(config, compile_step=compile_step)
    grid_x, grid_y = _coordinate_grids(config)

    record_steps = {
        s for s in range(1, steps + 1)
        if s > warmup and (s - warmup) % record_interval == 0
    }
    gyrations: list[np.ndarray] = []
    occupancies: list[np.ndarray] = []
    first_center: tuple[np.ndarray, np.ndarray] | None = None
    last_center: tuple[np.ndarray, np.ndarray] | None = None
    sample_count = 0

    a = a0
    for t in range(1, steps + 1):
        a = step(a, grid, kernels)
        if t in record_steps:
            fs = _frame_sample(a, config, occupancy_threshold, grid_x, grid_y)
            gyrations.append(fs.gyration)
            occupancies.append(fs.occupancy)
            if first_center is None:
                first_center = (fs.center_x, fs.center_y)
            last_center = (fs.center_x, fs.center_y)
            sample_count += 1
        elif t % 32 == 0:
            mx.eval(a)
    if first_center is None or last_center is None:
        raise ValueError("no post-warmup samples recorded; check steps/warmup/interval")

    mx.eval(a)
    final = np.asarray(a.sum(axis=-1))  # [B, sx, sy]
    batch = final.shape[0]
    lcf = np.empty(batch)
    ccount = np.empty(batch)
    for b in range(batch):
        lcf[b], ccount[b] = _component_metrics(final[b], occupancy_threshold)

    gyr = np.stack(gyrations, axis=0)
    period = max(sample_count - 1, 1) * record_interval
    fx, fy = first_center
    lx, ly = last_center
    sx, sy = float(config.sx), float(config.sy)
    ddx = np.abs(lx - fx)
    ddx = np.minimum(ddx, sx - ddx)
    ddy = np.abs(ly - fy)
    ddy = np.minimum(ddy, sy - ddy)
    velocity = np.sqrt(ddx * ddx + ddy * ddy) / period

    return np.stack([
        lcf,
        ccount,
        gyr.mean(axis=0),
        gyr.std(axis=0),
        velocity,
        np.stack(occupancies, axis=0).mean(axis=0),
    ], axis=1)
