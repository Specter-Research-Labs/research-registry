"""Perturbation assays on the MLX map: the measurement primitive for the functional
morphospace.

A creature's *function* is how it behaves across a family of conditions, not a property of one
rollout. The perturbation tier of that family (recovery from damage, response to repeated
stimulation) is pure field manipulation, so it runs batched and in-process on the MLX map over
a whole population, using the robust descriptors (occupancy, gyration, single-body coherence)
that match the Swift oracle. The environment-coupled tier (sensing, navigation) needs the Swift
metal-full coupling and lives elsewhere.

recovery_assay: grow each creature, ablate a chunk mid-rollout, and measure how far the
terminal form drifts from the un-ablated terminal. Small drift = the creature regenerates
toward its form = canalization / robustness, the most Levin-central function.
"""

from __future__ import annotations

from dataclasses import dataclass

import mlx.core as mx
import numpy as np

from lenia_swarm_analysis.anatomical_compiler.mlx_coherence import _component_metrics
from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import (
    _coordinate_grids,
    centroid_and_gyration,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    make_init,
    rollout,
)

# Translation-invariant terminal descriptors used to compare forms across conditions.
TERMINAL_FIELDS: tuple[str, ...] = ("mass", "occupancy", "gyration", "lcf")


def _terminal_descriptors(
    a: mx.array, config: LeniaConfig, occupancy_threshold: float,
    grid_x: mx.array, grid_y: mx.array,
) -> np.ndarray:
    """[B, len(TERMINAL_FIELDS)] translation-invariant descriptors of a settled field."""
    field = a.sum(axis=-1)
    mass, _, _, gyr = centroid_and_gyration(field, config, grid_x, grid_y)
    occ = (field > occupancy_threshold).astype(mx.float32).mean(axis=(1, 2))
    mx.eval(mass, gyr, occ)
    summed = np.asarray(field)
    mass_n, gyr_n, occ_n = np.asarray(mass), np.asarray(gyr), np.asarray(occ)
    lcf = np.array([_component_metrics(summed[i], occupancy_threshold)[0]
                    for i in range(summed.shape[0])])
    return np.stack([mass_n, occ_n, gyr_n, lcf], axis=1)


def _ablate(field: mx.array, center: tuple[int, int], size: int) -> mx.array:
    """Zero a square patch of the state (a clean lesion), returning a new array."""
    out = np.asarray(field)
    half = size // 2
    cx, cy = center
    out = out.copy()
    out[:, cx - half:cx - half + size, cy - half:cy - half + size, :] = 0.0
    return mx.array(out)


@dataclass
class RecoveryResult:
    baseline: np.ndarray     # [B, TERMINAL_FIELDS] un-ablated terminal descriptors
    perturbed: np.ndarray    # [B, TERMINAL_FIELDS] post-ablation terminal descriptors
    relative_change: np.ndarray    # [B, TERMINAL_FIELDS] per-descriptor |b-p|/|b| (group-fair)
    recovery_distance: np.ndarray  # [B] mean relative terminal drift (low = recovered)

    # Note: low drift alone is not "robust" - a structureless blob re-pools trivially after a
    # lesion while a structured creature has structure to lose, so recovery must be read
    # alongside form complexity (lcf, moments). The functional morphospace pairs the two.


def recovery_assay(
    genotype: GenotypeBatch, config: LeniaConfig, *,
    center: tuple[int, int], size: int, occupancy_threshold: float,
    perturb_step: int = 400, total_steps: int = 900, ablate_size: int = 30,
    init_seed: int = 0,
) -> RecoveryResult:
    """Grow each creature to perturb_step, then run two continuations from that state, one
    clean and one with a square lesion, and compare the terminal forms. The standardized
    distance between them is the recovery score (small = regenerates toward its form)."""
    grid_x, grid_y = _coordinate_grids(config)
    a0 = make_init(config, seed=init_seed, center=center, size=size, batch=genotype.batch)
    mid = rollout(a0, genotype, config, perturb_step)
    mx.eval(mid)

    tail = total_steps - perturb_step
    baseline_end = rollout(mid, genotype, config, tail)
    perturbed_end = rollout(_ablate(mid, center, ablate_size), genotype, config, tail)

    baseline = _terminal_descriptors(baseline_end, config, occupancy_threshold, grid_x, grid_y)
    perturbed = _terminal_descriptors(perturbed_end, config, occupancy_threshold, grid_x, grid_y)
    relative_change = np.abs(baseline - perturbed) / (np.abs(baseline) + 1e-9)
    return RecoveryResult(
        baseline=baseline, perturbed=perturbed, relative_change=relative_change,
        recovery_distance=relative_change.mean(axis=1),
    )
