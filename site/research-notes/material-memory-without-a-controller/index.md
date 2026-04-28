---
title: "Material Memory Without a Controller"
release: "draft"
provenance: "assistant-drafted"
source_id: "D-004"
toc: true
---

# Material Memory Without a Controller

A minimal Jolt rigid-body assembly with local, history-dependent updates and no centralized
controller. Each body receives local updates to friction, stiffness, and plasticity from
interaction history. The question: what does the substrate retain after perturbation, and
what gets in the way?

## Setup

Three forcing regimes:

- `imprint`: a pulse drives the system, then guidance is removed.
- `hysteresis`: the drive ramps through reversals.
- `damage`: the system is imprinted, perturbed, and forced to continue.

Main campaign:

- 3 scenarios
- 2 backends (CPU, Metal)
- 4 policy/memory conditions
- 40 seeds

Baseline: **960 runs**. Two follow-up sweeps:

- **480 runs** of damage-only plasticity ablations.
- **480 runs** of line-versus-staggered layout generalization.

Total: **1,920 runs** plus direct video inspection of selected trajectories.

![Connected substrate render](../../assets/blog/jolt-material-memory/fig-hero-substrate.png)

## Results

### Imprint

Memory-on, line layout: `MRI = 1.656849`. A transient pulse leaves a persistent offset. The
post-pulse state does not relax to baseline.

![Imprint retention index](../../assets/blog/jolt-material-memory/fig-imprint-mri.png)

![Imprint memory comparison](../../assets/blog/jolt-material-memory/fig-imprint-memory-plate.png)

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-imprint-line-on.mp4"></video>
  <figcaption>Imprint, line layout, memory on, CPU backend.</figcaption>
</figure>

### Hysteresis

Memory-on, line layout, positive against both controls:

- `HLA = 0.011828`
- `DeltaK_on_vs_off = +0.124968`
- `DeltaK_on_vs_inertial_control = +0.004841`

The on-vs-inertial gap is small but positive. The response depends on the path taken, not
only the current input.

![Baseline control separation](../../assets/blog/jolt-material-memory/fig-delta-k-controls.png)

### Damage

Memory-on is worse than both memory-off and inertial control on both backends:

- `damage cpu`: `DeltaK_on_vs_off = -0.429246`
- `damage metal`: `DeltaK_on_vs_off = -0.429271`

The damage recovery index is also negative. The substrate does not remap toward the prior target.

![Damage recovery summary](../../assets/blog/jolt-material-memory/fig-damage-recovery.png)

![Damage memory comparison](../../assets/blog/jolt-material-memory/fig-damage-memory-plate.png)

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-damage-line-on.mp4"></video>
  <figcaption>Damage, line layout, memory on, CPU backend.</figcaption>
</figure>

## Plasticity Variants

Weakening the memory rule made damage worse, not better. Four variants:

| Variant | `DeltaK_on_vs_off` |
|---|---|
| `baseline` | -0.434 |
| `fast_forget` | -0.661 |
| `soft_cap` | -0.692 |
| `low_ceiling` | -0.743 |

The recovery metric stayed negative under every variant.

![Damage ablation recovery](../../assets/blog/jolt-material-memory/fig-damage-ablation-recovery.png)

## Layout Generalization

Same memory condition, two body plans:

| Regime | Line `DeltaK_on_vs_off` | Staggered `DeltaK_on_vs_off` |
|---|---|---|
| `imprint` | +0.050358 | +0.070632 |
| `hysteresis` | +0.124968 | **-0.082789** |
| `damage` | negative | negative |

`hysteresis` flips sign under the staggered layout. The same local rule expresses differently
under a different geometry.

![Layout-dependent Delta K](../../assets/blog/jolt-material-memory/fig-layout-delta-k-controls.png)

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-hysteresis-staggered-on.mp4"></video>
  <figcaption>Hysteresis, staggered layout, memory on, CPU backend.</figcaption>
</figure>

## Competing Targets

Two-pulse pilot: pulse A drives toward one target, quiet interval, pulse B drives toward the
opposite target, guidance removed. Only `A → B` order tested so far; reverse order is still
outstanding.

All conditions finish closer to the second target, but memory-on is least overwritten:

| Condition | `overwrite_index` |
|---|---|
| `memory off` | +0.521726 |
| `inertial_control` | +0.434607 |
| `memory on` | +0.347354 |

![Competing-target overwrite index](../../assets/blog/jolt-material-memory/fig-competing-overwrite.png)

![Competing-target memory comparison](../../assets/blog/jolt-material-memory/fig-competing-memory-plate.png)

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-competing-targets-line-on.mp4"></video>
  <figcaption>Competing targets, line layout, memory on, CPU backend.</figcaption>
</figure>

## Limits

The system does not remap adaptively after damage. The line-layout `imprint` and `hysteresis`
runs are effectively deterministic: repeatable trajectory classes, not sampled distributions.

What works: local material memory creates persistent commitments. Those commitments help
retention and obstruct reorganization.

## Next

- Reverse-order competing-targets panel.
- Unguided remapping after injury.
- Basin-depth measurements for imprinted states.
- Broader body-plan sweeps.

Order-sensitive overwriting, spontaneous return to a prior target, or a measurable basin of
attraction would move the result from "persistent commitments" toward set-points.

---

That is the draft.
