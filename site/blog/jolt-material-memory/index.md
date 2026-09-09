---
release: "draft"
---

# Material Memory Without a Controller

A physical substrate with only local, history-dependent updates and no controller can retain a
trace of a pulse. After damage, that same trace drags the assembly toward an organization it can
no longer use.

## What We Ran

The core system is a minimal Jolt rigid-body assembly. There is no centralized controller. Each
body only gets local updates to friction, stiffness, and plasticity from interaction history. We
then ask the assembly to operate in three regimes:

- `imprint`: a pulse drives the system, then guidance is removed
- `hysteresis`: the drive ramps through reversals
- `damage`: the system is imprinted, perturbed, and forced to continue

The main campaign used:

- 3 scenarios
- 2 backends
- 4 policy/memory conditions
- 40 seeds

That baseline matrix is **960 runs**. We then ran two follow-up sweeps:

- **480 runs** of damage-only plasticity ablations
- **480 runs** of line-versus-staggered layout generalization

So the current read is based on **1,920 runs** plus direct video inspection of selected trajectories.

![Connected substrate render](../../assets/blog/jolt-material-memory/fig-hero-substrate.png)

## The Substrate Retains a Trace

The cleanest positive result is the `imprint` task. A transient pulse leaves behind a persistent
offset after the pulse is gone. In the baseline campaign, the memory-on condition shows a strong
positive MRI:

- `MRI = 1.656849` in the line layout baseline campaign

The offset remains after forcing ends.

![Imprint retention index](../../assets/blog/jolt-material-memory/fig-imprint-mri.png)

![Imprint memory comparison](../../assets/blog/jolt-material-memory/fig-imprint-memory-plate.png)

The 3D trajectory shows the bodies settling into a coordinated displacement after the pulse.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-imprint-line-on.mp4"></video>
  <figcaption>Imprint, line layout, memory on, CPU backend. The post-pulse state does not relax back to the original baseline.</figcaption>
</figure>

On `imprint`, the material acquires a preferred post-perturbation state.

## The Substrate Has Internal State

The `hysteresis` task asks something slightly different. If we reverse the forcing, does the
response depend only on the current input, or on the path the system took to get there?

In the line layout, the answer is clear. The memory-on condition has a positive hysteresis loop
area and a positive `DeltaK` against both controls:

- `HLA = 0.011828`
- `DeltaK_on_vs_off = +0.124968`
- `DeltaK_on_vs_inertial_control = +0.004841`

The last number is small, but separates the line-layout effect from damping alone.

The system carries state, not just momentum.

![Baseline control separation](../../assets/blog/jolt-material-memory/fig-delta-k-controls.png)

## Damage Turns the Trace Against Recovery

In the `damage` scenario, memory-on is worse than both memory-off and inertial control on both
backends in the original campaign:

- `damage cpu`: `DeltaK_on_vs_off = -0.429246`
- `damage metal`: `DeltaK_on_vs_off = -0.429271`

Under the new damage recovery index, the picture does not improve. The memory-on condition shows a
negative median recovery tendency instead of a clean remapping back toward the prior target.

![Damage recovery summary](../../assets/blog/jolt-material-memory/fig-damage-recovery.png)

![Damage memory comparison](../../assets/blog/jolt-material-memory/fig-damage-memory-plate.png)

The failure is not simple chaos. The assembly carries its prior organization into the wrong regime.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-damage-line-on.mp4"></video>
  <figcaption>Damage, line layout, memory on, CPU backend. The remembered organization does not become flexible recovery.</figcaption>
</figure>

The memory is not a neutral state variable. It stores commitments, and those commitments impede
recovery.

## Simply Weakening Plasticity Did Not Fix It

The first repair attempt was the obvious one: reduce the severity of the memory rule.

We ran a damage-only ablation over four named variants:

- `baseline`
- `soft_cap`
- `fast_forget`
- `low_ceiling`

All three non-baseline variants made the damage case worse.

- `baseline`: `DeltaK_on_vs_off = -0.434`
- `fast_forget`: `DeltaK_on_vs_off = -0.661`
- `soft_cap`: `DeltaK_on_vs_off = -0.692`
- `low_ceiling`: `DeltaK_on_vs_off = -0.743`

The recovery metric also stayed negative under every tested variant.

![Damage ablation recovery](../../assets/blog/jolt-material-memory/fig-damage-ablation-recovery.png)

The problem is not simply “too much plasticity.” Weakening the rule along these axes did not turn
the failure into adaptive remapping.

## Body Plan Changes What the Memory Means

The second follow-up asked whether the positive result belonged to the memory rule alone or to the
combination of memory rule and body plan.

We reran the baseline memory condition on two layouts:

- `line`
- `staggered`

The layout sweep splits the result.

`imprint` survives the layout change and even gets slightly stronger:

- `line imprint`: `DeltaK_on_vs_off = +0.050358`
- `staggered imprint`: `DeltaK_on_vs_off = +0.070632`

But `hysteresis` flips sign:

- `line hysteresis`: `DeltaK_on_vs_off = +0.124968`
- `staggered hysteresis`: `DeltaK_on_vs_off = -0.082789`

And `damage` stays negative on both layouts.

![Layout-dependent Delta K](../../assets/blog/jolt-material-memory/fig-layout-delta-k-controls.png)

The layout is not an incidental visual detail. It is the body plan. If the same local rule
expresses memory differently under a different geometry, then morphology is part of the
computation.

The staggered hysteresis video makes that visible. The same class of local update rule no longer
supports the same reversal behavior once the assembly geometry changes.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-hysteresis-staggered-on.mp4"></video>
  <figcaption>Hysteresis, staggered layout, memory on, CPU backend. The body plan changes the expression of path-dependent state.</figcaption>
</figure>

## Competing Targets

One natural next question is whether the substrate stores the newest instruction, the strongest
instruction, or a lingering commitment to an earlier target. To probe that, we ran a small
two-pulse `competing_targets` pilot: pulse A drives the assembly toward one target, there is a
quiet interval, pulse B drives it toward the opposite target, and then guidance is removed again.

We have only run the `A -> B` order, not the reverse-order companion.

All directed conditions finish closer to the second target than to the first. The memory-on
condition is the **least** overwritten:

- `memory off`: `overwrite_index = +0.521726`
- `inertial_control`: `overwrite_index = +0.434607`
- `memory on`: `overwrite_index = +0.347354`

In other words, the substrate with material memory does not most strongly adopt the latest target.
It retains more of the earlier commitment than either control.

![Competing-target overwrite index](../../assets/blog/jolt-material-memory/fig-competing-overwrite.png)

![Competing-target memory comparison](../../assets/blog/jolt-material-memory/fig-competing-memory-plate.png)

The second pulse pulls the assembly across, but the final tail does not collapse cleanly onto the
new target.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-competing-targets-line-on.mp4"></video>
  <figcaption>Competing targets, line layout, memory on, CPU backend. The later pulse wins directionally, but the remembered state is not overwritten cleanly.</figcaption>
</figure>

The commitments persist across conflicting guidance. We still need the reverse-order companion to
test true order sensitivity, not just one-sided overwrite resistance.

## Where It Stops

The system does not remap reliably after injury or generalize across body plans. The line-layout
`imprint` and `hysteresis` runs are effectively deterministic trajectory classes, not sampled
distributions. Local material memory creates persistent commitments; those commitments help
retention and obstruct reorganization.

The next batch is:

- competing targets and false memory
- unguided remapping after injury
- basin-depth measurements for imprinted states
- broader body-plan sweeps

Reverse-order overwriting, spontaneous return to a prior target, or a measurable basin of
attraction would distinguish set-points from persistent traces. Until then, the system remembers
and sometimes that memory gets in the way.
