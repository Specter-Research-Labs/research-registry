# Architecture

`embryomaker-v2` should have a narrow compiled boundary and an explicit Python control plane.

## Layers

1. `C++23` kernel
2. binding layer
3. Python control plane
4. artifact and analysis layer

The kernel owns execution-critical simulation code only:

- state storage
- stepping
- mechanics
- fields
- regulation
- events
- checkpoints

The Python side owns:

- experiment authoring
- sweeps
- fitting
- plotting
- notebooks
- dataset collation

## Kernel Modules

- `core`: ids, numerics, RNG, errors
- `model`: static model definition
- `state`: dynamic arrays
- `mechanics`: neighbors, contacts, forces, integration
- `fields`: secretion and diffusion
- `regulation`: per-cell species and behavior modifiers
- `events`: division, death, EMT-like transitions
- `scheduler`: multi-rate stepping
- `io`: checkpoints and summaries
- `api`: narrow public surface

## Public Kernel Surface

The compiled API should stay small:

- `ModelSpec`
- `InitialStateSpec`
- `RunConfig`
- `Runner`
- `Checkpoint`
- `SummaryView`

Python should not own raw internal arrays or mutable C++ references.

## Memory Layout

The hot state should be structure-of-arrays:

- positions
- radii
- polarity
- type ids
- lineage ids
- cycle phase
- differentiation state
- alive masks

Contact state should be edge-centric, because the same graph will later support:

- mechanics
- contact-mediated signaling
- gap-junction conductance for the bioelectric extension

## Scheduler

The scheduler should be explicit and multi-rate.

Default order:

1. rebuild contacts
2. mechanics substeps
3. field deposition
4. field update
5. regulation update
6. derive behavior modifiers
7. enqueue events
8. apply events
9. emit summaries and checkpoints

## Current Scaffold

The current scaffold is intentionally small:

- a compile-tested `C++23` kernel layout surface
- a Python CLI for toolchain and parity planning
- docs that pin the architecture and parity program
- a first legacy cell-sorting transcription with SoA node and cell state
- a legacy-style box neighbor list for the first parity lane
- a mesenchymal contact graph and pair-force surface for the first parity lane
- a legacy-style outer-loop cell-sorting iteration surface with RK4 mechanics
  and post-mechanics noise
- a narrow parser for the stable subset of legacy `.dat` snapshots used by the
  cell-sorting lane

The next real implementation step is to replace the layout stub with:

- a legacy-vs-v2 comparison runner that consumes baseline snapshot artifacts
- the next benchmark lane beyond cell sorting
