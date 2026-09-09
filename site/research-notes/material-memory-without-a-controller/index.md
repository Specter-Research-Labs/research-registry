---
title: "Material Memory Without a Controller"
release: "draft"
source_id: "D-004"
toc: true
---

# Material Memory: Experiment Receipt

This note is the short record behind [Material Memory Without a Controller](../../blog/jolt-material-memory/). A minimal Jolt assembly receives only local, history-dependent updates to friction, stiffness, and plasticity; we ran `imprint`, `hysteresis`, and `damage` regimes across CPU and Metal.

The campaign comprises 1,920 runs: a 960-run baseline (three scenarios, two backends, four memory conditions, 40 seeds), then 480-run plasticity ablations and a 480-run line-versus-staggered body-plan sweep.

Memory retains a post-pulse displacement in the line layout (`MRI = 1.656849`) and leaves a positive hysteresis signal (`DeltaK_on_vs_off = +0.124968`). After damage it is worse than both controls on both backends (`-0.429246` CPU, `-0.429271` Metal), and weakening the rule makes that failure worse. Changing the layout preserves imprint but flips hysteresis (`+0.124968` to `-0.082789`). In the first competing-target pilot, the memory-on condition is also least overwritten (`+0.347354`, against `+0.521726` with memory off).

So this substrate retains commitments; it does not yet remap flexibly after injury. The next discriminating run is the reverse `B → A` pulse order, followed by unguided recovery and basin-depth measurements.
