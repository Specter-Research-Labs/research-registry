---
summary: "Map of the Lenia Swarm documentation: where to start, how creatures are measured and grouped, how to run sweeps and paper reproductions, and how the simulator is built."
---

# Lenia Swarm docs

Lenia Swarm runs Flow Lenia simulations, indexes the persistent patterns they produce into a SQLite compendium, and measures and groups those patterns. `LeniaCLI` and `LeniaStudio` do the computation; `spctr surface` preserves and publishes declared surfaces such as `lenia-compendium`.

## Start here

- [Primer](./universe/Primer.md): what is simulated and recorded, the physics terms, and the glossary.
- [Running a local sweep](./contracts/LocalCLI.md): build `LeniaCLI`, run a sweep, read the run directory, and keep it reproducible.
- [Config map](./configs/README.md): the config families every run starts from.

## Measuring and grouping creatures

- [Morphology and morphometrics](./universe/Morphology.md): the vocabulary of form and behavior, and the measurements stored for each creature.
- [Taxonomy](./universe/Taxonomy.md): how `LeniaCLI analyze taxonomy` assigns family, genus and species IDs.
- [Ecology](./universe/Ecology.md): how creatures spread across parameter space, and the `LeniaCLI analyze ecology` export.

## Running experiments

- [Paper reproductions](./contracts/ResearchModes.md): the seven paper-grounded run families, their entry points, outputs, code and gaps.
- [The compendium](./contracts/CompendiumSchema.md): schema, migrations, indexer behavior, Studio reads, and the exact-version rule.

## Inside the simulator

- [FlowLenia.swift parameter mapping](./internals/FlowLeniaImplementationMap.md): how the Swift parameters map onto the Flow-Lenia paper's equations.
- [Flow coordinates and the reference regression](./flow-spatial-conventions.md): axis order and gradient signs in the integrator, and the tests against the reference implementation.
- [Species knobs for glider search](./internals/SpeciesKnobs.md): which parameters define a species and which can vary.

## Layout

- `universe/`: concepts and research vocabulary.
- `contracts/`: interfaces and guarantees (CLI, schema, run directory, reproducibility).
- `configs/`: configuration families and canonical entry files.
- `internals/`: implementation details tied to source files.
