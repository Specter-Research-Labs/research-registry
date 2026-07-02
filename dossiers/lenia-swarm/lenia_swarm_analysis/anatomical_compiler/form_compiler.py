"""The form-to-rule compiler: given a target form, find rules that hold it.

This is the fixed-point inverse. A self-maintaining creature is its own seed, so we fix
the initial condition to the target form itself and search only the genotype for the
property "this form is a stable fixed point": re-seeded with the form, the dynamics keep
it as one coherent body that does not dissolve or spread. The search signal is the form
drift after re-seeding (low = the rule holds the form), validated to separate holding
rules from non-holding ones by roughly 7x.

A cross-entropy search over the genotype, every candidate re-seeded with the form and
rolled forward on the batched MLX map, drives the drift down; the elite set at
convergence is a sample of the genotype fiber over the form (the rules that hold it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mlx.core as mx
import numpy as np

from lenia_swarm_analysis.anatomical_compiler._codec import (
    GenotypeCodec,
    clamp_params,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_coherence import _component_metrics
from lenia_swarm_analysis.anatomical_compiler.mlx_lenia import (
    GenotypeBatch,
    LeniaConfig,
    compile_kernels,
    make_init,
    make_step,
    position_grid,
    rollout,
)

# Weight of the anti-freeze penalty in the compile objective: a rule that freezes the
# creature (liveness -> 0) is pushed this far up, comparable to a badly-broken form.
LIVENESS_WEIGHT = 0.4


@dataclass
class FormTarget:
    field: mx.array          # [1, sx, sy, C] the target form, used as both target and seed
    lcf: float
    occupancy: float
    liveness: float          # the form's own per-step churn while self-maintaining (anchor)


def _occupancy(field: np.ndarray, threshold: float) -> float:
    return float((field > threshold).mean())


def _rollout_scores(
    a0: mx.array, geno: GenotypeBatch, config: LeniaConfig, steps: int, stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Roll forward and return (final summed-mass field [B, sx, sy], liveness [B]).
    Liveness is the mean per-stride change of the full state, so a frozen creature reads
    ~0 while both a glider and a stationary breather read well above 0."""
    grid = position_grid(config)
    step = make_step(config)
    kernels = compile_kernels(geno, config)
    a = a0
    prev = a0
    acc: mx.array | None = None
    count = 0
    for t in range(1, steps + 1):
        a = step(a, grid, kernels)
        if t % stride == 0:
            delta = mx.abs(a - prev).mean(axis=(1, 2, 3))
            acc = delta if acc is None else acc + delta
            mx.eval(a, acc)
            count += 1
            prev = a
    mx.eval(a)
    liveness = np.asarray(acc / count) if acc is not None else np.zeros(a.shape[0])
    return np.asarray(a.sum(axis=-1)), liveness


def grow_body(
    rule: dict[str, Any], config: LeniaConfig, *, center: tuple[int, int], size: int,
    occupancy_threshold: float, n_seeds: int = 6, steps: int = 600,
) -> FormTarget:
    """Run a rule from several noise seeds and return the most coherent settled body as a
    target form (the creature, lifted out to serve as its own seed)."""
    geno = GenotypeBatch.from_param_dicts([rule] * n_seeds)
    inits = mx.concatenate(
        [make_init(config, seed=s, center=center, size=size, batch=1) for s in range(n_seeds)],
        axis=0,
    )
    a = rollout(inits, geno, config, steps)
    summed = np.asarray(a.sum(axis=-1))
    best, best_lcf = 0, -1.0
    for s in range(n_seeds):
        lcf, _ = _component_metrics(summed[s], occupancy_threshold)
        if lcf > best_lcf:
            best_lcf, best = lcf, s
    field = mx.array(np.asarray(a[best])[None])
    # The form's own natural activity (anchor for the liveness floor): re-seed the body
    # under its rule and measure how much it churns while self-maintaining.
    _, lb = _rollout_scores(field, GenotypeBatch.from_param_dicts([rule]), config, 120, 20)
    return FormTarget(
        field=field, lcf=best_lcf, occupancy=_occupancy(summed[best], occupancy_threshold),
        liveness=float(lb[0]),
    )


def _form_scores(
    vectors: np.ndarray, target: FormTarget, codec: GenotypeCodec,
    ranges: dict[str, list[float]], config: LeniaConfig, *, steps: int, stride: int,
    occupancy_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Re-seed the target form into each rule and score (drift, liveness). Drift is the
    relative occupancy change plus loss of single-body coherence (low = form held);
    liveness is the per-step churn (low = frozen)."""
    params = [clamp_params(codec.unflatten(v), ranges)[0] for v in vectors]
    geno = GenotypeBatch.from_param_dicts(params)
    a0 = mx.broadcast_to(target.field, (len(params), config.sx, config.sy, config.channels))
    summed, liveness = _rollout_scores(a0, geno, config, steps, stride)
    drift = np.empty(len(params))
    for i in range(len(params)):
        lcf, _ = _component_metrics(summed[i], occupancy_threshold)
        occ = _occupancy(summed[i], occupancy_threshold)
        drift[i] = abs(occ - target.occupancy) / (target.occupancy + 1e-9) + max(
            0.0, target.lcf - lcf
        )
    return drift, liveness


def _objective(drift: np.ndarray, liveness: np.ndarray, target_liveness: float) -> np.ndarray:
    """Hold the form AND stay at least as alive as the original creature."""
    penalty = np.maximum(0.0, 1.0 - liveness / (target_liveness + 1e-9))
    return drift + LIVENESS_WEIGHT * penalty


@dataclass
class CompileResult:
    best_vector: np.ndarray
    best_objective: float
    best_drift: float
    best_liveness: float
    target_liveness: float
    start_objective: float
    history: list[float]
    elite_vectors: np.ndarray
    elite_objectives: np.ndarray


def compile_form(
    target: FormTarget, start_vector: np.ndarray, genotype_scale: np.ndarray,
    *, codec: GenotypeCodec, ranges: dict[str, list[float]], config: LeniaConfig,
    rng: np.random.Generator, iterations: int = 8, population: int = 24, elites: int = 6,
    steps: int = 200, occupancy_threshold: float = 0.05,
    init_sigma_scale: float = 0.06, sigma_floor_scale: float = 0.01,
) -> CompileResult:
    stride = max(1, steps // 8)

    def score(vecs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        drift, liveness = _form_scores(
            vecs, target, codec, ranges, config, steps=steps, stride=stride,
            occupancy_threshold=occupancy_threshold,
        )
        return _objective(drift, liveness, target.liveness), drift, liveness

    mean = start_vector.copy()
    sigma = init_sigma_scale * genotype_scale
    s_obj, s_drift, s_live = score(start_vector[None, :])
    start_objective = float(s_obj[0])
    best_obj, best_vec = start_objective, mean.copy()
    best_drift, best_live = float(s_drift[0]), float(s_live[0])
    history: list[float] = []
    elite_vecs = start_vector[None, :]
    elite_objs = s_obj
    for _ in range(iterations):
        samples = mean[None, :] + sigma[None, :] * rng.standard_normal(
            (population, mean.shape[0])
        )
        obj, drift, live = score(samples)
        order = np.argsort(obj)
        elite_vecs = samples[order[:elites]]
        elite_objs = obj[order[:elites]]
        mean = elite_vecs.mean(axis=0)
        sigma = elite_vecs.std(axis=0) + sigma_floor_scale * genotype_scale
        if obj[order[0]] < best_obj:
            best_obj = float(obj[order[0]])
            best_vec = samples[order[0]].copy()
            best_drift = float(drift[order[0]])
            best_live = float(live[order[0]])
        history.append(best_obj)
    return CompileResult(
        best_vector=best_vec, best_objective=best_obj, best_drift=best_drift,
        best_liveness=best_live, target_liveness=target.liveness,
        start_objective=start_objective, history=history,
        elite_vectors=elite_vecs, elite_objectives=elite_objs,
    )
