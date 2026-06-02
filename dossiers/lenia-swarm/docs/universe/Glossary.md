# Glossary

## Params Pipeline

- `KernelParams`: serialized kernel parameter set (`r`, `b`, `w`, `a`, `m`, `s`, `h`, `R`). Codable struct, used as `genotype` on `SavedCreature` and `SimulationResultData.params`.
- `KernelParamRanges`: per-parameter min/max bounds for random sampling and mutation.
- `ResolvedParams`: runtime-resolved version of kernel params with seed; call `.toKernelParams()` to serialize.

## Creature Anatomy

- genotype (`SavedCreature.genotype`): `KernelParams` defining the kernel configuration.
- initial condition (`SavedCreature.initialCondition`): `InitConfig` specifying seed, patches, uniform ranges, and state patches that define the starting grid state.
- initial condition family: string classifier for the initial condition type (uniform, patched, state-patch).
- phenotype: measurable behavioral outcomes from a run (motion, mass, occupancy, activity). Not a stored field on `SavedCreature` — this word refers to observable dynamics, not the initial condition.

## Evaluation Tiers

- metrics (`SimulationMetrics`): creature-level summary stats (mass, speed, occupancy, gyration, heading) from world snapshots, plus ecosystem-level summaries (`activity*`, `survivalSteps`) from activity traces.
- morphometrics (`Morphometrics`): derived morphology features computed from metrics (tortuosity, limb count, symmetry).
- descriptor bundle (`MorphospaceDescriptorBundle`): genotype + phenotype descriptors used for morphospace embedding.

## Species and Taxonomy

- taxonomy: family/genus/species grouping layer over indexed creatures.
- species fingerprint: canonical genotype vector hash used for species-level identity.

## Core Terms

- Flow Lenia: mass-transport variant of Lenia that updates state via flow + reintegration.
- ecology embedding: exported parameter-space table used for cross-run structure analysis.
- compendium: SQLite index over run artifacts and derived records.
- run id: immutable run identifier used to join artifacts, logs, and indexed rows.
- config hash: topology fingerprint for reproducibility and comparability.
- universe: the physics rules and parameter space governing simulation — `LeniaBaseConfig` / `LeniaRuntimeConfig`. Grid topology, kernel structure, connectivity, flow/reintegration parameters, resolved kernel params. Normally fixed for a run; beam mutation promotes universe parameters into the world state, making them locally varying.
- world state: the instantaneous spatial state of the grid — `WorldState` (width/height/channels/values). Changes each timestep under the universe's rules. Includes the activity field (mass per channel), parameter embedding field, and food field when present.
- ecosystem: emergent population-level dynamics measured over a trajectory — `ActivitySummary` (time series of species counts, diversity, EAP/EAC/EAN). Requires multiple timesteps and component tracking. The `activity*` fields on `SimulationMetrics` are time-collapsed ecosystem observations.

## Usage Notes

- Use "morphology" for descriptive language and interpretation.
- Use "morphometrics" for stored computed fields.
- Use "taxonomy" only for explicit grouping assignments, not informal labels.
- Use "phenotype" for observable behavior; use "initial condition" for the `InitConfig` starting state.
- `SimulationMetrics` spans two levels — creature-level metrics (mass, speed, shape) from world snapshots, and ecosystem-level metrics (`activity*`, `survivalSteps`) from activity summaries.
