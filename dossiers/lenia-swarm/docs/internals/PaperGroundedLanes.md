# Paper-Grounded Lanes

Treats the major paper reproductions as first-class research lanes, not as ad hoc sweeps.

The lane model exists for one reason: each paper asks a different question, uses a different search space, and evaluates success differently. A single generic search surface cannot represent all of them without becoming vague or misleading.

## Main Surfaces

The current paper-grounded entrypoints are:

- `evolve` with [paper configs](../../configs/papers/flowlenia-2022/) for the 2022 Flow-Lenia task suite
- `reaction-diffusion-2023` for the 2023 reaction-diffusion validation lane
- `sensorimotor-2024` for the 2024 agency-discovery lane
- `qd-2024` for the 2024 quality-diversity lane
- `ecology-2025` for the 2025 Flow-Lenia intrinsic-evolution ecology lane
- `curiosity-2025` for the 2025 curiosity-driven universe exploration lane
- `atlas-2026` for the 2026 classical Lenia parameter-space atlas

The old user-facing names `leniabreeder-2024`, `flowlenia-ecology-2025`, and `ai-scientist-2025` are retired. The config directories keep the paper names because they are provenance surfaces, not the main CLI vocabulary.

## Source Papers

- [Flow-Lenia 2022](https://releases.specterlab.org/records/lenia/2022/001-2022-flow-lenia-towards-open-ended-evolution-in-cellular-automata-through-mass-conservation-and-parameter-localization.pdf)
- [Reaction-Diffusion Lenia 2023](https://releases.specterlab.org/records/lenia/2023/001-2023-implementation-of-lenia-as-a-reaction-diffusion-system.pdf)
- [Discovering Sensorimotor Agency 2024](https://releases.specterlab.org/records/lenia/2024/001-2024-discovering-sensorimotor-agency-in-cellular-automata-using-diversity-search.pdf)
- [Toward Artificial Open-Ended Evolution within Lenia using Quality-Diversity 2024](https://releases.specterlab.org/records/lenia/2024/002-2024-toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity.pdf)
- [Exploring Flow-Lenia Universes with a Curiosity-driven AI Scientist 2025](https://releases.specterlab.org/records/lenia/2025/001-2025-exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-discovering-diverse-ecosystem-dynamics.pdf)
- [Flow-Lenia Emergent Evolutionary Dynamics 2025](https://releases.specterlab.org/records/lenia/2025/002-2025-flow-lenia-emergent-evolutionary-dynamics-in-mass-conservative-continuous-cellular-automata.pdf)
- [Visualizing the Structure of Lenia Parameter Space 2026](https://releases.specterlab.org/records/lenia/2026/001-2026-visualizing-the-structure-of-lenia-parameter-space.pdf)

## Why These Lanes Exist

- The 2022 paper is task-conditioned optimization, not open-ended discovery.
- The 2024 agency paper is goal-conditioned diversity search with a curriculum and robustness battery.
- The 2024 QD paper is repertoire discovery with MAP-Elites and AURORA.
- The 2025 papers move from isolated organisms to ecosystem- and universe-scale discovery metrics.
- The 2026 atlas paper maps parameter space before glider or creature hunting.

Those are different research programs. They should share core simulation code when possible, but they should not be flattened into one search API.

## Lane Map

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

Why it is useful:

- It gives a reproducible task harness for motion and navigation.
- It lets us debug optimization and morphology separately from open-ended discovery.

Main remaining gap:

- Public sources do not include every original experiment wrapper, so parity is against the published paper/config regime rather than unpublished internal scripts.

### Reaction-Diffusion 2023

Primary code:

- [ReactionDiffusionLenia2023.swift](../../Sources/LeniaCore/Layer/ReactionDiffusionLenia2023.swift)
- [ReactionDiffusion2023Command.swift](../../Sources/LeniaCLI/ReactionDiffusion2023Command.swift)
- [reaction-diffusion-lenia-2023 configs](../../configs/papers/reaction-diffusion-lenia-2023/)

What we re-implemented:

- validation and emulation harnesses around the reaction-diffusion interpretation
- asymptotic/original comparison outputs

Why it is useful:

- It is the core-validation lane.
- It checks whether our continuous Lenia-like dynamics remain mathematically defensible rather than only visually plausible.

Main remaining gap:

- This lane is a validator, not a discovery engine. It should stay small and sharp.

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

Why it is useful:

- This is the lane closest to our earlier “motion without convincing organisms” failure mode.
- It gives a principled discovery loop instead of score-only sweeps.

Main remaining gap:

- Real paper-scale runs still matter more than more harness code. This lane now needs broad experiments and result comparison.

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

Why it is useful:

- This lane discovers repertoires, not one winner.
- It is the right tool for broad species discovery when we care about stepping stones and diversity.

Main remaining gap:

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

Why it is useful:

- It moves us from isolated specimens to ecosystem behavior.
- It is the correct lane for long-run multispecies questions.

Main remaining gap:

- This lane should be judged by long-horizon ecology outputs, not by small smoke tests.

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

Why it is useful:

- It is the open-ended universe discovery lane.
- It replaces narrow creature ranking with system-level novelty metrics.

Main remaining gap:

- As with ecology, the real test is paper-scale exploration, not tiny smoke coverage.

### Atlas 2026

Primary code:

- [Atlas2026.swift](../../Sources/LeniaCore/Layer/Atlas2026.swift)
- [Atlas2026Command.swift](../../Sources/LeniaCLI/Atlas2026Command.swift)
- [lenia-atlas-2026 configs](../../configs/papers/lenia-atlas-2026/)

What we re-implemented:

- classical Lenia `mu`/`sigma` atlas lane
- public-style polygon-library input
- paper-style batch semantics and phase-map export

Why it is useful:

- It maps the search space before we try to mine it for gliders or creatures.
- It is the cleanest correction to blind classical Lenia sweeps.

Main remaining gap:

- The remaining work is full atlas scale and result inspection, not another sweep heuristic.

## Shared Engineering Choices

These lanes share one principle: paper-specific logic lives above the core simulator.

That means:

- shared core simulation stays in [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift) and related runtime code
- paper-specific runners live in `Sources/LeniaCore/Layer/`
- user-facing entrypoints live in `Sources/LeniaCLI/`
- paper configs live under [configs/papers](../../configs/papers/)

This separation matters because it lets us reproduce papers without silently changing the core equations.

## Metal and MLX

The heavy lanes are intended to run on the MLX/Metal path on Apple Silicon.

Relevant code:

- [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift)
- [Evolution.swift](../../Sources/LeniaCore/Layer/Evolution.swift)
- [SignpostSupport.swift](../../Sources/LeniaCore/Layer/SignpostSupport.swift)

What has already been done:

- release-path runs for long paper lanes
- Instruments/signpost support for hot-path profiling
- rollout sync cleanup so metrics do not force unnecessary host/device barriers
- external artifact/log routing for long runs on remote volumes

The current hotspot conclusion is still the same:

- `reintegrationBatched` remains the strongest custom-kernel candidate if we need another serious speed step

## Invariants

The paper lanes are allowed to add runners, descriptors, and evaluation logic. They are not allowed to silently rewrite the core Flow-Lenia equations.

The guardrail is the invariant test in [LeniaCoreTests.swift](../../Tests/LeniaCoreTests/LeniaCoreTests.swift), especially `testPopulationKernelsMatchSingleKernelPath`.

When a lane needs a paper-specific surface, the correct move is:

- add it in a paper runner
- prove it with focused tests
- keep the core path numerically consistent

## What To Read Next

For the current architecture:

1. [FlowLeniaImplementationMap](./FlowLeniaImplementationMap.md)
2. [PaperGroundedLanes](./PaperGroundedLanes.md)
3. [SpeciesKnobs](./SpeciesKnobs.md)

For operating these lanes:

1. [LocalCLI](../contracts/LocalCLI.md)
2. [ArtifactLayout](../contracts/ArtifactLayout.md)
3. [Reproducibility](../contracts/Reproducibility.md)
