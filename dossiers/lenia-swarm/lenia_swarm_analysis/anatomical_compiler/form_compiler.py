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
from pathlib import Path
from typing import Any

import mlx.core as mx
import numpy as np
from PIL import Image

from lenia_swarm_analysis.anatomical_compiler._codec import (
    PHENOTYPE_FIELDS,
    GenotypeCodec,
    Standardizer,
    clamp_params,
)
from lenia_swarm_analysis.anatomical_compiler.form_topology import (
    persistence_image,
    topo_distance,
)
from lenia_swarm_analysis.anatomical_compiler.mlx_coherence import _component_metrics
from lenia_swarm_analysis.anatomical_compiler.mlx_descriptors import (
    _coordinate_grids,
    centroid_and_gyration,
)
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

# Weight of the topology term. Drift is O(0.1-1) (relative occupancy change + lost
# coherence) and topo_distance between a held ring and a collapsed disk is O(1) (a lost H1
# class), so at weight 1.0 the topology term is scale-comparable to drift and neither
# dominates; the ring-vs-disk validation confirms the two terms trade off in that range.
TOPO_WEIGHT = 1.0


@dataclass
class FormTarget:
    field: mx.array          # [1, sx, sy, C] the target form, used as both target and seed
    lcf: float
    occupancy: float
    liveness: float          # the form's own per-step churn while self-maintaining (anchor)
    signature: np.ndarray    # cubical-persistence image of the summed-mass form


def _occupancy(field: np.ndarray, threshold: float) -> float:
    return float((field > threshold).mean())


def load_mask_target(
    mask_path: Path, config: LeniaConfig, *, occupancy_threshold: float, liveness: float,
    total_mass: float,
) -> FormTarget:
    """Read a PNG or .npy into a soft [0, 1] field at the config resolution and lift it to
    a FormTarget: the form is placed in channel 0 (summed mass == the mask), matching how
    the single-channel regime reads occupancy and topology off the summed field.

    The mask specifies arrangement, not amount, so the raw greyscale is rescaled to
    total_mass, the mass of a real settled creature in this regime (a regime-calibrated
    anchor supplied by the caller). This matters because Flow-Lenia conserves mass exactly:
    re-seeding a hand-drawn mask at its literal 0/1 density lands far outside the growth
    band and dissolves regardless of rule, so the seed mass must sit where the regime's
    dynamics are viable. Occupancy, coherence and the persistence signature are unchanged by
    this rescale as long as the occupied cells stay above the occupancy threshold: occupancy
    and lcf threshold on density, and the signature normalises by the field max.

    Liveness has no natural value for a mask (a mask is not a settled creature), so it too
    is passed in from the anchor by the caller."""
    if config.channels != 1:
        raise NotImplementedError(
            "mask targets are single-channel greyscale; embedding into "
            f"{config.channels} channels is undefined"
        )
    if mask_path.suffix == ".npy":
        raw = np.load(mask_path).astype(np.float64)
    else:
        raw = np.asarray(Image.open(mask_path).convert("L"), dtype=np.float64) / 255.0
    if raw.shape != (config.sx, config.sy):
        image = Image.fromarray((np.clip(raw, 0.0, 1.0) * 255).astype(np.uint8))
        image = image.resize((config.sy, config.sx), Image.Resampling.BILINEAR)
        raw = np.asarray(image, dtype=np.float64) / 255.0
    if raw.sum() <= 0.0:
        raise ValueError(f"mask {mask_path} has no occupied cells")
    raw = raw * (total_mass / raw.sum())
    field_np = np.zeros((1, config.sx, config.sy, config.channels), dtype=np.float32)
    field_np[0, :, :, 0] = raw
    lcf, _ = _component_metrics(raw, occupancy_threshold)
    return FormTarget(
        field=mx.array(field_np), lcf=lcf,
        occupancy=_occupancy(raw, occupancy_threshold), liveness=liveness,
        signature=persistence_image(raw),
    )


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
            # Normalize by the sampling interval so target and candidate liveness stay
            # comparable when they are measured with different strides.
            delta = mx.abs(a - prev).mean(axis=(1, 2, 3)) / stride
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
        liveness=float(lb[0]), signature=persistence_image(summed[best]),
    )


def _form_scores(
    vectors: np.ndarray, target: FormTarget, codec: GenotypeCodec,
    ranges: dict[str, list[float]], config: LeniaConfig, *, steps: int, stride: int,
    occupancy_threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Re-seed the target form into each rule and score (drift, liveness, topo_dist). Drift
    is the relative occupancy change plus loss of single-body coherence (low = form held);
    liveness is the per-step churn (low = frozen); topo_dist is the persistence-image
    distance of the terminal arrangement from the target's (low = same loops/bodies)."""
    params = [clamp_params(codec.unflatten(v), ranges)[0] for v in vectors]
    geno = GenotypeBatch.from_param_dicts(params)
    a0 = mx.broadcast_to(target.field, (len(params), config.sx, config.sy, config.channels))
    summed, liveness = _rollout_scores(a0, geno, config, steps, stride)
    drift = np.empty(len(params))
    topo = np.empty(len(params))
    for i in range(len(params)):
        lcf, _ = _component_metrics(summed[i], occupancy_threshold)
        occ = _occupancy(summed[i], occupancy_threshold)
        drift[i] = abs(occ - target.occupancy) / (target.occupancy + 1e-9) + max(
            0.0, target.lcf - lcf
        )
        topo[i] = topo_distance(persistence_image(summed[i]), target.signature)
    return drift, liveness, topo


def _objective(
    drift: np.ndarray, liveness: np.ndarray, topo: np.ndarray, target_liveness: float
) -> np.ndarray:
    """Hold the form AND its arrangement AND stay at least as alive as the anchor. The
    liveness floor cannot be dropped: a frozen field has zero drift and a frozen ring even
    scores a perfect topology match, so without the anti-freeze term the trivial winner is
    a rule that simply stops the dynamics."""
    penalty = np.maximum(0.0, 1.0 - liveness / (target_liveness + 1e-9))
    return drift + LIVENESS_WEIGHT * penalty + TOPO_WEIGHT * topo


def select_warm_start(
    target: FormTarget, genotype: np.ndarray, phenotype_full: np.ndarray,
    codec: GenotypeCodec, ranges: dict[str, list[float]], config: LeniaConfig,
    *, k: int, steps: int, occupancy_threshold: float,
    exclude_indices: set[int] | None = None,
) -> tuple[np.ndarray, float, float, float]:
    """Pick the CEM warm start by which dataset rule actually holds the re-seeded form.

    A fixed anchor rule is a poor start: most rules dissolve a re-seeded form, so the CEM
    can begin on a flat, uninformative part of the objective. Instead take the k dataset
    rules whose settled occupancy and gyration are nearest the form's (a cheap descriptor
    prefilter on the precomputed phenotype table), re-seed the form into all of them in one
    batched rollout, and start from the lowest form objective. Returns the start vector and
    its (drift, liveness, topo_dist)."""
    grid_x, grid_y = _coordinate_grids(config)
    _, _, _, gyr = centroid_and_gyration(
        target.field.sum(axis=-1), config, grid_x, grid_y
    )
    mx.eval(gyr)
    target_desc = np.array([[target.occupancy, float(np.asarray(gyr)[0])]])
    cols = [PHENOTYPE_FIELDS.index("occupancy_mean"), PHENOTYPE_FIELDS.index("gyration")]
    sub = phenotype_full[:, cols]
    standardizer = Standardizer.fit(sub)
    distances = np.linalg.norm(
        standardizer.forward(sub) - standardizer.forward(target_desc)[0], axis=1
    )
    ordered = np.argsort(distances)
    if exclude_indices:
        ordered = np.asarray([i for i in ordered if int(i) not in exclude_indices])
    candidates = genotype[ordered[:k]]
    if len(candidates) == 0:
        raise ValueError("no warm-start candidates remain after exclusions")
    stride = max(1, steps // 8)
    drift, liveness, topo = _form_scores(
        candidates, target, codec, ranges, config, steps=steps, stride=stride,
        occupancy_threshold=occupancy_threshold,
    )
    best = int(np.argmin(_objective(drift, liveness, topo, target.liveness)))
    return candidates[best].copy(), float(drift[best]), float(liveness[best]), float(topo[best])


@dataclass
class CompileResult:
    best_vector: np.ndarray
    best_objective: float
    best_drift: float
    best_liveness: float
    best_topo: float
    target_liveness: float
    start_objective: float
    history: list[float]
    trace_vectors: list[np.ndarray]
    trace_drifts: list[float]
    trace_liveness: list[float]
    trace_topology: list[float]
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

    def score(
        vecs: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        drift, liveness, topo = _form_scores(
            vecs, target, codec, ranges, config, steps=steps, stride=stride,
            occupancy_threshold=occupancy_threshold,
        )
        return _objective(drift, liveness, topo, target.liveness), drift, liveness, topo

    mean = start_vector.copy()
    sigma = init_sigma_scale * genotype_scale
    s_obj, s_drift, s_live, s_topo = score(start_vector[None, :])
    start_objective = float(s_obj[0])
    best_obj, best_vec = start_objective, mean.copy()
    best_drift, best_live, best_topo = float(s_drift[0]), float(s_live[0]), float(s_topo[0])
    history: list[float] = []
    trace_vectors = [best_vec.copy()]
    trace_drifts = [best_drift]
    trace_liveness = [best_live]
    trace_topology = [best_topo]
    elite_vecs = start_vector[None, :]
    elite_objs = s_obj
    for _ in range(iterations):
        samples = mean[None, :] + sigma[None, :] * rng.standard_normal(
            (population, mean.shape[0])
        )
        obj, drift, live, topo = score(samples)
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
            best_topo = float(topo[order[0]])
        history.append(best_obj)
        trace_vectors.append(best_vec.copy())
        trace_drifts.append(best_drift)
        trace_liveness.append(best_live)
        trace_topology.append(best_topo)
    return CompileResult(
        best_vector=best_vec, best_objective=best_obj, best_drift=best_drift,
        best_liveness=best_live, best_topo=best_topo, target_liveness=target.liveness,
        start_objective=start_objective, history=history,
        trace_vectors=trace_vectors, trace_drifts=trace_drifts,
        trace_liveness=trace_liveness, trace_topology=trace_topology,
        elite_vectors=elite_vecs, elite_objectives=elite_objs,
    )
