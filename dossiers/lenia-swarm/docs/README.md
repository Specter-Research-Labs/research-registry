# lenia-swarm docs

Use this map to navigate Lenia Swarm research framing, contracts, configs, internals, and decisions.

## Lanes

- `universe/`: conceptual language, ontology, interpretation, and research framing.
- `contracts/`: executable interfaces and guarantees (CLI, schema, artifact layout, reproducibility rules).
- `configs/`: configuration families and canonical entry files.
- `internals/`: implementation details tied directly to source files.
- `decisions/`: ADRs that capture the rationale for durable structure choices.

Use universe for research framing, contracts for durable interfaces, configs for run inputs, and internals for implementation details.

`LeniaCLI` and `LeniaStudio` own computation. `spctr surface` owns preservation and publication of
declared surfaces such as `lenia-compendium`.

## Start Here

- [Primer](./universe/Primer.md)
- [Glossary](./universe/Glossary.md)
- [Config Map](./configs/README.md)

## Universe

- [Physics](./universe/Physics.md)
- [Morphology](./universe/Morphology.md)
- [Ecology](./universe/Ecology.md)
- [Taxonomy](./universe/Taxonomy.md)

## Contracts

- [LocalCLI](./contracts/LocalCLI.md)
- [ResearchModes](./contracts/ResearchModes.md)
- [CompendiumSchema](./contracts/CompendiumSchema.md)
- [ComparativeMorphospace](./contracts/ComparativeMorphospace.md)
- [MorphometricsAndTraits](./contracts/MorphometricsAndTraits.md)
- [EcologyCLI](./contracts/EcologyCLI.md)
- [ArtifactLayout](./contracts/ArtifactLayout.md)
- [Reproducibility](./contracts/Reproducibility.md)

## Configs

- [Config Map](./configs/README.md)

## Internals

- [FlowLeniaImplementationMap](./internals/FlowLeniaImplementationMap.md)
- [PaperGroundedLanes](./internals/PaperGroundedLanes.md)
- [IndexerInternals](./internals/IndexerInternals.md)
- [StudioCompendiumInternals](./internals/StudioCompendiumInternals.md)

## Reading Paths

Research orientation:

1. `universe/Primer.md`
2. `universe/Physics.md`
3. `universe/Morphology.md`
4. `universe/Ecology.md`
5. `universe/Taxonomy.md`

Run and operate:

1. `contracts/LocalCLI.md`
2. `contracts/ResearchModes.md`
3. `contracts/ArtifactLayout.md`
4. `contracts/Reproducibility.md`
5. `contracts/CompendiumSchema.md`
6. `configs/README.md`

Implement and debug:

1. `internals/FlowLeniaImplementationMap.md`
2. `internals/PaperGroundedLanes.md`
3. `internals/IndexerInternals.md`
4. `internals/StudioCompendiumInternals.md`
