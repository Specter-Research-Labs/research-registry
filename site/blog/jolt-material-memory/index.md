---
release: "draft"
---

# Material Memory Without a Controller

A physical substrate with only local, history-dependent updates. No controller. What does it
retain after perturbation?

It turns out it retains quite a lot. After damage it can also cling to the wrong thing instead of
remapping. That part is more interesting than the positive results.

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

That is a concrete retained trace, not just transient movement during forcing.

![Imprint retention index](../../assets/blog/jolt-material-memory/fig-imprint-mri.png)

![Imprint memory comparison](../../assets/blog/jolt-material-memory/fig-imprint-memory-plate.png)

The 3D trajectory makes the point visually. The bodies are driven, settle, and remain displaced in
a coordinated way after the pulse has ended.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-imprint-line-on.mp4"></video>
  <figcaption>Imprint, line layout, memory on, CPU backend. The post-pulse state does not relax back to the original baseline.</figcaption>
</figure>

On `imprint`, the material acquires a preferred post-perturbation state. Yes.

## The Substrate Has Internal State

The `hysteresis` task asks something slightly different. If we reverse the forcing, does the
response depend only on the current input, or on the path the system took to get there?

In the line layout, the answer is clear. The memory-on condition has a positive hysteresis loop
area and a positive `DeltaK` against both controls:

- `HLA = 0.011828`
- `DeltaK_on_vs_off = +0.124968`
- `DeltaK_on_vs_inertial_control = +0.004841`

That last number is small, but it matters. It says the line-layout hysteresis effect is not only a
damping artifact.

The system carries state, not just momentum.

![Baseline control separation](../../assets/blog/jolt-material-memory/fig-delta-k-controls.png)

## Damage Is the Point

The most important result in the dossier is not the positive one. It is the negative one.

In the `damage` scenario, memory-on is worse than both memory-off and inertial control on both
backends in the original campaign:

- `damage cpu`: `DeltaK_on_vs_off = -0.429246`
- `damage metal`: `DeltaK_on_vs_off = -0.429271`

Under the new damage recovery index, the picture does not improve. The memory-on condition shows a
negative median recovery tendency instead of a clean remapping back toward the prior target.

![Damage recovery summary](../../assets/blog/jolt-material-memory/fig-damage-recovery.png)

![Damage memory comparison](../../assets/blog/jolt-material-memory/fig-damage-memory-plate.png)

The video is useful here because the failure does not look like simple chaos. It looks like a
substrate that has learned a prior organization strongly enough to drag that commitment into the
wrong regime.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-damage-line-on.mp4"></video>
  <figcaption>Damage, line layout, memory on, CPU backend. The remembered organization does not become flexible recovery.</figcaption>
</figure>

The memory is not a neutral state variable. It stores commitments, and those commitments impede
recovery. That is more interesting than a system that just helps on every metric.

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

That matters because it rules out a lazy explanation. The problem is not just "too much
plasticity." The current failure seems structural. Making the memory weaker along the obvious axes
did not convert it into adaptive remapping.

## Body Plan Changes What the Memory Means

The second follow-up asked whether the positive result belonged to the memory rule alone or to the
combination of memory rule and body plan.

We reran the baseline memory condition on two layouts:

- `line`
- `staggered`

The result was mixed in a useful way.

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

This is not yet the full overwrite story because we have only run the `A -> B` order so far, not
the reverse-order panel. But the first result is already informative.

All directed conditions finish closer to the second target than to the first, so the later pulse
still matters. But the memory-on condition is the **least** overwritten:

- `memory off`: `overwrite_index = +0.521726`
- `inertial_control`: `overwrite_index = +0.434607`
- `memory on`: `overwrite_index = +0.347354`

In other words, the substrate with material memory does not most strongly adopt the latest target.
It retains more of the earlier commitment than either control.

![Competing-target overwrite index](../../assets/blog/jolt-material-memory/fig-competing-overwrite.png)

![Competing-target memory comparison](../../assets/blog/jolt-material-memory/fig-competing-memory-plate.png)

The 3D run makes the same point in motion. The second pulse clearly pulls the assembly across, but
the final tail does not collapse cleanly onto the new target.

<figure>
  <video controls playsinline muted preload="metadata" src="../../assets/blog/jolt-material-memory/video-competing-targets-line-on.mp4"></video>
  <figcaption>Competing targets, line layout, memory on, CPU backend. The later pulse wins directionally, but the remembered state is not overwritten cleanly.</figcaption>
</figure>

The commitments persist across conflicting guidance. We still need the reverse-order companion to
test true order sensitivity, not just one-sided overwrite resistance.

## This Is Not Yet Homeostasis

None of this is adaptive memory. The system does not reliably remap after injury, and it does not
generalize across body plans. The line-layout `imprint` and `hysteresis` runs are also effectively
deterministic under the current dynamics — they are repeatable trajectory classes, not sampled
distributions.

What holds up: local material memory creates persistent commitments in a minimal rigid-body
substrate. Those commitments help retention and obstruct reorganization.

## What the System Appears to Preserve

The three regimes point at the same underlying question: what does the substrate preserve?

`imprint` suggests the substrate can acquire a preferred state.

`hysteresis` suggests that this preferred state is not a momentary displacement but part of a
path-dependent internal organization.

`damage` suggests the remembered organization gets sticky in the wrong way. No clean regenerative
remapping yet. The substrate over-preserves a prior commitment.

## What We Need Next

The next experiments should characterize the remembered target itself, not just whether memory
improves efficiency.

The most immediate batch is:

- competing targets and false memory
- unguided remapping after injury
- basin-depth measurements for imprinted states
- broader body-plan sweeps

Order-sensitive overwriting, spontaneous return to a prior target, or a measurable basin of
attraction would push the story from "persistent commitments" toward set-points. If none of that
shows up, the substrate stores traces but not flexible goals.

So far the system remembers things and sometimes that memory gets in the way. That is the draft.
