---
summary: "What Lenia Swarm simulates and records, the physics terms it uses for persistent patterns, and a glossary of the names that appear in code and data."
---

# Primer

`lenia-swarm` is a Flow Lenia experiment system for discovering and indexing persistent patterns across parameter space. This page gives the frame needed to read the rest of the docs: what is simulated, what is recorded, and what the recurring words mean.

## What the system does

The system has three coupled concerns:

- physics: how states evolve each step,
- morphology: how we summarize form and behavior,
- ecology: how populations and niches are compared across runs.

The research loop is:

1. run deterministic simulations from explicit configs,
2. extract metrics and derived morphometrics,
3. index into a versioned compendium,
4. analyze structure (taxonomy, ecology) offline.

Core objects:

- state field `A`: the simulated multi-channel lattice state.
- genotype: parameter payload controlling kernels and global parameters.
- phenotype: observed behavior summarized into metrics.
- creature record: an indexed row tying genotype, phenotype, and provenance.

## Physics

In this dossier, "physics" means the space-time properties of pattern persistence under the Flow Lenia update.

Translational regime example (`crossmap`, seed `0`):

![Crossmap translational exemplar](./assets/examples/crossmap-magma.webp)

Constrained, meandering regime example (`nnea`, seed `0`):

![NNEA meandering exemplar](./assets/examples/nnea-magma.webp)

Terms:

- `persist`: a pattern remains recognizable across many update steps.
- `invariant`: a pattern identity survives controlled changes (for example small perturbations).
- `perturbation`: a deliberate small change to state or parameters.
- `regime`: a recurring dynamical mode, such as fast translation versus low-displacement meandering.

The corpus separates regimes with trajectory statistics:

- `center_velocity`: mean translational speed of the center of mass.
- `path_length / displacement`: near `1` means straight transport; larger values mean meandering or looping motion.

Anchored examples:

- `crossmap-128-local-20260227-153007`, seed `0`: `center_velocity=0.01027`, `path/displacement=1.0026`.
- `nnea-128-local-20260227-153006`, seed `0`: `center_velocity=0.00009`, `path/displacement=9.1293`.

Prior Lenia literature describes invariance under scale, transform and deformation. Here those are research goals, not formalized benchmark suites: motion regime separation is implemented, and a full invariance test battery (scale, flip, rotate, deformation) is not.

## Glossary

### Parameter pipeline

- `KernelParams`: serialized kernel parameter set (`r`, `b`, `w`, `a`, `m`, `s`, `h`, `R`). Codable struct, used as `genotype` on `SavedCreature` and `SimulationResultData.params`.
- `KernelParamRanges`: per-parameter min/max bounds for random sampling and mutation.
- `ResolvedParams`: runtime-resolved version of kernel params with seed; call `.toKernelParams()` to serialize.

### Creature anatomy

- genotype (`SavedCreature.genotype`): `KernelParams` defining the kernel configuration.
- initial condition (`SavedCreature.initialCondition`): `InitConfig` specifying seed, patches, uniform ranges, and state patches that define the starting grid state.
- initial condition family: string classifier for the initial condition type (uniform, patched, state-patch).
- phenotype: measurable behavioral outcomes from a run (motion, mass, occupancy, activity). Not a stored field on `SavedCreature`; the word refers to observable dynamics, not the initial condition.

### Evaluation tiers

- metrics (`SimulationMetrics`): creature-level summary stats (mass, speed, occupancy, gyration, heading) from world snapshots, plus ecosystem-level summaries (`activity*`, `survivalSteps`) from activity traces.
- morphometrics (`Morphometrics`): features derived from metrics and activity traces: path tortuosity, movement efficiency, and activity maxima and spreads. See [Morphology and morphometrics](./Morphology.md).
- descriptor bundle (`MorphospaceDescriptorBundle`): genotype and phenotype descriptors used for morphospace embedding.

### Species and taxonomy

- taxonomy: family, genus and species identifiers assigned to indexed creatures by `LeniaCLI analyze taxonomy`. See [Taxonomy](./Taxonomy.md).
- species fingerprint: hash of the canonical genotype vector, used for species-level identity.

### Core terms

- Flow Lenia: mass-transport variant of Lenia that updates state via flow and reintegration.
- ecology embedding: exported parameter-space table used for cross-run structure analysis.
- compendium: SQLite index over run artifacts and derived records.
- run id: immutable run identifier used to join artifacts, logs, and indexed rows.
- config hash: topology fingerprint for reproducibility and comparability.
- universe: the physics rules and parameter space governing simulation (`LeniaBaseConfig`, `LeniaRuntimeConfig`): grid topology, kernel structure, connectivity, flow and reintegration parameters, resolved kernel params. Normally fixed for a run; beam mutation promotes universe parameters into the world state, making them locally varying.
- world state: the instantaneous spatial state of the grid (`WorldState`: width, height, channels, values). Changes each timestep under the universe's rules. Includes the activity field (mass per channel), parameter embedding field, and food field when present.
- ecosystem: population-level dynamics measured over a trajectory (`ActivitySummary`: time series of species counts, diversity, EAP/EAC/EAN). Requires multiple timesteps and component tracking. The `activity*` fields on `SimulationMetrics` are time-collapsed ecosystem observations.

### Usage notes

- Use "morphology" for descriptive language and interpretation.
- Use "morphometrics" for stored computed fields.
- Use "taxonomy" only for assigned family, genus and species identifiers, not informal labels.
- Use "phenotype" for observable behavior; use "initial condition" for the `InitConfig` starting state.
- `SimulationMetrics` spans two levels: creature-level metrics (mass, speed, shape) from world snapshots, and ecosystem-level metrics (`activity*`, `survivalSteps`) from activity summaries.

## Where to go next

- How form and behavior are measured: [Morphology and morphometrics](./Morphology.md).
- How creatures are grouped: [Taxonomy](./Taxonomy.md) and [Ecology](./Ecology.md).
- How the simulator is built: [Flow Lenia implementation map](../internals/FlowLeniaImplementationMap.md).
- How to run something: [Running a local sweep](../contracts/LocalCLI.md).
