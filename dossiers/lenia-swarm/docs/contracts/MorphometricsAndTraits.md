# Morphometrics and Trait Policy

## Purpose

Defines the morphology surface used by compendium indexing and downstream ecology/warehouse analysis.

Scope:

- what is computed today,
- what is stored in `creatures.morphometrics_json`,
- what remains in policy or planning.

## Inputs

Available per creature:

- `SimulationMetrics` (path, displacement, mass stats, occupancy, energy, speed, gyration, center velocity, optional complexity).
- optional `ActivitySummary` time series (`speciesCount`, `diversity`, `eac`, `ean`) when activity JSONL is present.

## Implemented Morphometrics (v1)

Method metadata written by indexer:

- `morphometrics_method = "lenia-swarm:morphometrics"`
- `morphometrics_version = 1`

Fields currently computed:

- `pathTortuosity = pathLength / displacement` when `displacement > 1e-6`, else `null`.
- `movementEfficiency = displacement / pathLength` when `pathLength > 1e-6`, else `null`.
- `activitySpeciesMax = max(speciesCount)` when activity exists.
- `activitySpeciesStd = std(speciesCount)` when activity exists.
- `activityDiversityStd = std(diversity)` when activity exists.
- `activityEacMax = max(eac)` when activity exists.
- `activityEanMax = max(ean)` when activity exists.

If activity summaries are missing, all `activity*` morphometric fields are `null`.

## Invariants and Caveats

- Expected geometric invariant: `pathLength >= displacement`.
- When only two samples exist, `pathLength == displacement` is expected and does not imply a bug.
- Tortuosity distributions are only meaningful when recordings include enough temporal samples.

## Trait Policy (Planned)

Trait labels (for example mover, wanderer, swarm, complex) are not yet first-class stored outputs.

Current status:

- the indexer stores raw morphometrics, not discrete trait labels.

When trait labels become first-class, we will persist:

- trait method name,
- trait version,
- threshold-set identifier (for reproducibility).

## Analysis Workflow

The supported CLI surface is `LeniaCLI analyze ecology`, which exports parameter-space embeddings and summary artifacts from the canonical compendium.
