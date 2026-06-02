# Paper-Grounded Runs

Paper reproductions are separate run families, not ad hoc sweeps.

Each paper asks a different question, searches a different space, and measures
success differently. One generic command would hide those differences.

## Entrypoints

The current paper-grounded entrypoints are:

- `evolve` with [paper configs](../../configs/papers/flowlenia-2022/) for the 2022 Flow-Lenia task suite
- `reaction-diffusion-2023` for the 2023 reaction-diffusion validation work
- `sensorimotor-2024` for the 2024 agency-discovery work
- `qd-2024` for the 2024 quality-diversity work
- `ecology-2025` for the 2025 Flow-Lenia intrinsic-evolution ecology work
- `curiosity-2025` for the 2025 curiosity-driven universe exploration work
- `atlas-2026` for the 2026 classical Lenia parameter-space atlas

The old user-facing names `leniabreeder-2024`, `flowlenia-ecology-2025`, and
`ai-scientist-2025` are retired. Config directories keep paper names for
provenance, not as CLI vocabulary.

## Source Papers

- [Flow-Lenia 2022](https://releases.specterlab.org/records/lenia/2022/001-2022-flow-lenia-towards-open-ended-evolution-in-cellular-automata-through-mass-conservation-and-parameter-localization.pdf)
- [Reaction-Diffusion Lenia 2023](https://releases.specterlab.org/records/lenia/2023/001-2023-implementation-of-lenia-as-a-reaction-diffusion-system.pdf)
- [Discovering Sensorimotor Agency 2024](https://releases.specterlab.org/records/lenia/2024/001-2024-discovering-sensorimotor-agency-in-cellular-automata-using-diversity-search.pdf)
- [Toward Artificial Open-Ended Evolution within Lenia using Quality-Diversity 2024](https://releases.specterlab.org/records/lenia/2024/002-2024-toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity.pdf)
- [Exploring Flow-Lenia Universes with a Curiosity-driven AI Scientist 2025](https://releases.specterlab.org/records/lenia/2025/001-2025-exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-discovering-diverse-ecosystem-dynamics.pdf)
- [Flow-Lenia Emergent Evolutionary Dynamics 2025](https://releases.specterlab.org/records/lenia/2025/002-2025-flow-lenia-emergent-evolutionary-dynamics-in-mass-conservative-continuous-cellular-automata.pdf)
- [Visualizing the Structure of Lenia Parameter Space 2026](https://releases.specterlab.org/records/lenia/2026/001-2026-visualizing-the-structure-of-lenia-parameter-space.pdf)

## Why These Are Separate

- The 2022 paper is task-conditioned optimization, not open-ended discovery.
- The 2024 agency paper is goal-conditioned diversity search with a curriculum and robustness battery.
- The 2024 QD paper is repertoire discovery with MAP-Elites and AURORA.
- The 2025 papers move from isolated organisms to ecosystem- and universe-scale discovery metrics.
- The 2026 atlas paper maps parameter space before glider or creature hunting.

These are different experiments. Share core simulation code where possible; do
not flatten them into one search API.

## Map

### Flow-Lenia 2022

Primary code:

- [Evolution.swift](../../Sources/LeniaCore/Layer/Evolution.swift)
- [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift)
- [flowlenia-2022 configs](../../configs/papers/flowlenia-2022/)

What we re-implemented:

- directed motion
- angular motion
- obstacle navigation
- chemotaxis
- paper-style OpenES loop with antithetic Gaussian noise
- paper-locked task configs and output capture

Role:

- Reproducible task runner for motion and navigation.
- Separates optimization and morphology debugging from open-ended discovery.

Known gap:

- Public sources do not include every original experiment wrapper, so parity is against the published paper/config regime rather than unpublished internal scripts.

### Reaction-Diffusion 2023

Primary code:

- [ReactionDiffusionLenia2023.swift](../../Sources/LeniaCore/Layer/ReactionDiffusionLenia2023.swift)
- [ReactionDiffusion2023Command.swift](../../Sources/LeniaCLI/ReactionDiffusion2023Command.swift)
- [reaction-diffusion-lenia-2023 configs](../../configs/papers/reaction-diffusion-lenia-2023/)

What we re-implemented:

- validation and emulation tools around the reaction-diffusion interpretation
- asymptotic/original comparison outputs

Role:

- Core validation path.
- Checks whether the continuous dynamics remain mathematically defensible,
  rather than only visually plausible.

Known gap:

- This is a validator, not a discovery engine. Keep it small.

### Sensorimotor 2024

Primary code:

- [SensorimotorLenia2024.swift](../../Sources/LeniaCore/Layer/SensorimotorLenia2024.swift)
- [Sensorimotor2024Command.swift](../../Sources/LeniaCLI/Sensorimotor2024Command.swift)
- [sensorimotor-lenia-2024 configs](../../configs/papers/sensorimotor-lenia-2024/)

What we re-implemented:

- history/archive bootstrap
- goal sampling curriculum
- source selection and mutation
- local optimization toward sampled goals
- paper-style evaluation battery for movement, agency, and obstacle robustness

Role:

- Closest to the earlier "motion without convincing organisms" failure mode.
- Principled discovery loop instead of score-only sweeps.

Known gap:

- Real paper-scale runs matter more than more support code. This work now
  needs broad experiments and result comparison.

### QD 2024

Primary code:

- [LeniaBreeder2024.swift](../../Sources/LeniaCore/Layer/LeniaBreeder2024.swift)
- [LeniaBreeder2024Command.swift](../../Sources/LeniaCLI/LeniaBreeder2024Command.swift)
- [leniabreeder-2024 configs](../../configs/papers/leniabreeder-2024/)

What we re-implemented:

- MAP-Elites repertoire search around the Aquarium-centered structured genotype space
- time-series metrics after a developmental phase
- hard viability filtering for empty/full/spread failures
- AURORA with a VAE-trained latent descriptor
- COM-centered `32x32x3` phenotype crops
- `8`-dimensional latent descriptors
- unsupervised descriptor as mean latent trajectory
- unsupervised fitness as negative average latent dispersion

Role:

- Repertoire discovery, not one-winner search.
- Broad species discovery when stepping stones and diversity matter.

Known gap:

- The open issue is paper-scale validation, not missing AURORA machinery.

### Ecology 2025

Primary code:

- [FlowLeniaEcology2025.swift](../../Sources/LeniaCore/Layer/FlowLeniaEcology2025.swift)
- [FlowLeniaEcology2025Command.swift](../../Sources/LeniaCLI/FlowLeniaEcology2025Command.swift)
- [flowlenia-ecology-2025 configs](../../configs/papers/flowlenia-ecology-2025/)

What we re-implemented:

- paper-locked intrinsic-evolution ecology runs
- evolutionary activity and diversity-oriented summaries
- strict validation of the paper regime before execution

Role:

- Moves the dossier from isolated specimens to ecosystem behavior.
- Long-run multispecies work.

Known gap:

- Judge this work by long-horizon ecology outputs, not small smoke tests.

### Curiosity 2025

Primary code:

- [AIScientist2025.swift](../../Sources/LeniaCore/Layer/AIScientist2025.swift)
- [AIScientist2025Command.swift](../../Sources/LeniaCLI/AIScientist2025Command.swift)
- [ai-scientist-2025 configs](../../configs/papers/ai-scientist-2025/)

What we re-implemented:

- curiosity-driven Flow-Lenia universe exploration
- paper-specific goal spaces for ecosystem and movement modes
- archive/coverage accounting
- MP4-size and non-neutral activity style metrics

Role:

- Open-ended universe discovery.
- Replaces narrow creature ranking with system-level novelty metrics.

Known gap:

- As with ecology, the real test is paper-scale exploration, not tiny smoke coverage.

### Atlas 2026

Primary code:

- [Atlas2026.swift](../../Sources/LeniaCore/Layer/Atlas2026.swift)
- [Atlas2026Command.swift](../../Sources/LeniaCLI/Atlas2026Command.swift)
- [lenia-atlas-2026 configs](../../configs/papers/lenia-atlas-2026/)

What we re-implemented:

- classical Lenia `mu`/`sigma` atlas
- public-style polygon-library input
- paper-style batch semantics and phase-map export

Role:

- Maps the search space before glider or creature mining.
- Corrects blind classical Lenia sweeps.

Known gap:

- The remaining work is full atlas scale and result inspection, not another sweep heuristic.

## Shared Engineering Choices

These run families share one principle: paper-specific logic lives above the
core simulator.

That means:

- shared core simulation stays in [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift) and related runtime code
- paper-specific runners live in `Sources/LeniaCore/Layer/`
- user-facing entrypoints live in `Sources/LeniaCLI/`
- paper configs live under [configs/papers](../../configs/papers/)

This separation matters because it lets us reproduce papers without silently changing the core equations.

## Metal and MLX

The heavy runs use the MLX/Metal path on Apple Silicon.

Relevant code:

- [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift)
- [Evolution.swift](../../Sources/LeniaCore/Layer/Evolution.swift)
- [SignpostSupport.swift](../../Sources/LeniaCore/Layer/SignpostSupport.swift)

What has already been done:

- release-path runs for long paper jobs
- Instruments/signpost support for hot-path profiling
- rollout sync cleanup so metrics do not force unnecessary host/device barriers
- external artifact/log routing for long runs on remote volumes

The current hotspot conclusion is still the same:

- `reintegrationBatched` remains the strongest custom-kernel candidate if we need another serious speed step

## Invariants

Paper-specific commands can add runners, descriptors, and evaluation logic.
They must not silently rewrite the core Flow-Lenia equations.

The guardrail is the invariant test in [LeniaCoreTests.swift](../../Tests/LeniaCoreTests/LeniaCoreTests.swift), especially `testPopulationKernelsMatchSingleKernelPath`.

When paper work needs a new command, the rule is:

- add it in a paper runner
- prove it with focused tests
- keep the core path numerically consistent

## Reading Order

For the current architecture:

1. [FlowLeniaImplementationMap](./FlowLeniaImplementationMap.md)
2. [PaperGroundedRuns](./PaperGroundedRuns.md)
3. [SpeciesKnobs](./SpeciesKnobs.md)

For operating these runs:

1. [LocalCLI](../contracts/LocalCLI.md)
2. [ArtifactLayout](../contracts/ArtifactLayout.md)
3. [Reproducibility](../contracts/Reproducibility.md)
