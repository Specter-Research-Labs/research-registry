# Parity Ledger v0

This ledger names the original EmbryoMaker surfaces that define the first
mathematical parity target.

It is intentionally narrower than "all legacy code."

## Rule

For the first parity milestone, if a benchmark depends on one of the surfaces
below, the v2 implementation should preserve:

- the same state variables,
- the same update order,
- the same event semantics,
- and the same numerical mode where relevant.

## Primary Original Modules

### Main iteration loop

Source surface:

- `src/core/model.mod.f90`
- primary subroutine: `iteracio`

This is the scheduler surface that matters most. The early v2 scheduler should
 preserve the same conceptual order for parity lanes:

1. update cell centroids
2. rebuild neighbors
3. restore neighbors if enabled
4. compute force step / delta selection
5. update gene state
6. apply gene-to-behavior nexus
7. integrate positions
8. apply noise
9. apply filters and write outputs

If we intentionally change this order later, that should happen after the parity
 benchmarks pass.

### Mechanics

Source surface:

- `src/core/biomechanic.mod.f90`

First-pass parity targets:

- `iterdiferencial`
- `rungekutta4`
- `adaptive_rungekutta`
- `forces`

These define:

- overdamped mechanics
- delta selection
- RK4 substep behavior
- force accumulation order

Important note:

The original RK4 path can rebuild neighbors and reevaluate forces at substeps.
That is not an implementation detail if it changes the benchmark trajectory.

### Neighbor construction

Source surface:

- `src/core/neighboring.mod.f90`

First-pass parity targets:

- `iniboxes`
- `iniboxes_p`
- `neighbor_build`

This defines the contact candidate set and therefore changes both mechanics and
diffusion behavior.

### Gene and signaling layer

Source surface:

- `src/core/genetic.mod.f90`

First-pass parity targets:

- gene state semantics
- extracellular and intracellular diffusion semantics
- secretion and receptor-style coupling semantics
- gene-to-behavior effect table semantics

Important note:

The old public abstraction is not the one to preserve. What must be preserved is
the mathematics, not the giant index-coded matrix API.

### Gene-to-behavior nexus

Source surface:

- `src/core/nexus.mod.f03`

First-pass parity target:

- the mechanism by which internal gene state becomes changes in cell properties
  and behavior

This is one of the places where apparent "parameter updates" are actually part
of the mathematical model.

### Growth, division, and topology changes

Source surfaces:

- `src/core/growth.mod.f90`
- `src/core/mitosis.mod.f90`
- `src/core/death.mod.f90`
- `src/core/ecm.mod.f90`

First-pass parity target:

- event semantics that change topology or cell state in benchmark cases

Division parity is especially important because it can change later mechanics
and field coupling in ways that are not recoverable by endpoint-only matching.

## Core Legacy State To Map

### Node-like hot state

The legacy `nod` surface includes, among other things:

- position
- equilibrium and interaction distances
- elastic, adhesion, and repulsion terms
- polarity-related terms
- mobility and deformation terms
- differentiation state
- cell ownership
- epithelial pairing
- fixation and division flags

The v2 core does not need to preserve the legacy storage layout, but it does
need a declared image for every variable that matters in chosen benchmark lanes.

### Cell-like hot state

The legacy `cel` surface includes:

- centroid
- polarization
- cell-cycle phase
- EMT timer
- node membership
- division thresholds

These are not optional for the first developmental benchmark panel.

## First Numerical Modes To Preserve

The parity target should include:

- Euler
- RK4
- adaptive RK

for the specific benchmark lanes where the original uses them.

The v2 engine can later add cleaner or faster modes, but not before the parity
lane is anchored.

## First Benchmark Panel

The first transcription and baseline panel should include one case for each of:

1. contact-driven sorting
2. epithelial shape change
3. polarity-driven directed growth
4. one topology-changing event lane

Recommended original preset set:

- cell sorting
- invagination
- epithelial directed growth
- one of apoptosis or ECM secretion

That is enough to test:

- contacts
- forces
- integration
- polarity
- events

without exploding scope immediately.

## Comparison Surfaces

For each parity case, save and compare:

- counts over time
- selected node or cell trajectories
- centroids
- field totals if used
- event counts
- final class

For early parity, a handful of selected trajectories is better than a large pile
of ad hoc screenshots.

## Baseline Execution Note

The original runtime should be treated as a reference instrument.

The clean baseline path is:

- build the original in a pinned Linux environment
- run the selected benchmark cases in non-graphical mode
- save structured outputs and selected snapshots
- freeze toolchain provenance beside the outputs

The current Apple-silicon workstation is fine for the v2 scaffold, but not the
cleanest first baseline host for the original code.
