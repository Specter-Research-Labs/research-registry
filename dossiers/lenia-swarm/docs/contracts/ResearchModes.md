---
summary: "The Lenia paper reproductions, from the Flow-Lenia task suite to quality-diversity, ecology, curiosity and atlas runs, with entry points, outputs and gaps."
---

# Paper reproductions

Paper reproductions are separate run families, not ad hoc sweeps. Each paper asks a different question, searches a different space, and measures success differently, and one generic command would hide those differences. They share the core simulator and nothing else.

Config families and canonical entry files are listed in the [config map](../configs/README.md).

## Registry

| Mode | Paper anchor | Public entrypoint | Config family | Scope |
| --- | --- | --- | --- | --- |
| Flow tasks | Flow-Lenia 2022 | `LeniaCLI discover evolve` | `configs/base/`, `configs/search/`, `configs/es/` | task-conditioned optimization |
| RD validation | Reaction-Diffusion Lenia 2023 | `LeniaCLI discover rd-2023` | paper bundle + `configs/presets/` | mathematical validation and emulation |
| Sensorimotor | Hamon et al. 2024 | `LeniaCLI discover sensorimotor-2024` | paper bundle + `configs/presets/` | goal-conditioned diversity search |
| QD | LeniaBreeder 2024 | `LeniaCLI discover qd-2024` | `configs/presets/`, `configs/sweeps/`, `configs/es/` | MAP-Elites and AURORA repertoire search |
| Ecology | Flow-Lenia ecology 2025 | `LeniaCLI discover ecology-2025` | paper bundle + `configs/presets/` | intrinsic-evolution ecology runs |
| Curiosity | AI scientist 2025 | `LeniaCLI discover curiosity-2025` | paper bundle + `configs/presets/` | curiosity-driven universe exploration |
| Atlas | Lenia parameter space 2026 | `LeniaCLI discover atlas-2026` | paper bundle + `configs/presets/` | classical Lenia atlas runs |

The 2022 paper is task-conditioned optimization, not open-ended discovery. The 2024 agency paper is goal-conditioned diversity search with a curriculum and a robustness battery. The 2024 QD paper builds repertoires with MAP-Elites and AURORA. The 2025 papers move from isolated organisms to ecosystem- and universe-scale discovery metrics. The 2026 atlas maps parameter space before any glider or creature hunting.

The old user-facing names `leniabreeder-2024`, `flowlenia-ecology-2025`, and `ai-scientist-2025` are retired. They still appear in config directories and older artifacts as provenance labels, not as CLI vocabulary.

## Shared rules

- Paper-specific logic lives above the shared simulator: core simulation in [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift) and related runtime code, paper runners in `Sources/LeniaCore/Layer/`, user-facing entrypoints in `Sources/LeniaCLI/`, paper configs under [configs/papers](../../configs/papers/).
- No research mode may silently change the core Flow-Lenia equations. The guard is [LeniaCoreTests.swift](../../Tests/LeniaCoreTests/LeniaCoreTests.swift), especially `testPopulationKernelsMatchSingleKernelPath`. A new paper command goes in a paper runner, is proven with focused tests, and keeps the core path numerically consistent.
- Durable run outputs go to `SPECTER_ARTIFACT_ROOT` when set; otherwise the mode writes to the explicit `--output` path.
- Changes to run outputs must remain deterministic and rerunnable from captured configs.

## Modes

### Flow tasks (Flow-Lenia 2022)

Entrypoint:

- `LeniaCLI discover evolve --config <task.json> --es <optimizer.json> --output <dir>`, with [paper configs](../../configs/papers/flowlenia-2022/).

Primary outputs: `summary.json`, `history.jsonl`, and the task-specific run artifacts captured by `evolve`.

Code: [Evolution.swift](../../Sources/LeniaCore/Layer/Search/Evolution.swift), [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift).

What we re-implemented:

- directed motion, angular motion, obstacle navigation and chemotaxis tasks,
- the paper-style OpenES loop with antithetic Gaussian noise,
- paper-locked task configs and output capture.

This is a reproducible task runner for motion and navigation, which keeps optimization and morphology debugging apart from open-ended discovery. It is not a repertoire builder and does not write to the compendium.

Known gap: public sources do not include every original experiment wrapper, so parity is against the published paper and config regime, not unpublished internal scripts.

### RD validation (Reaction-Diffusion Lenia 2023)

Entrypoint:

- `LeniaCLI discover rd-2023 --config-dir <dir> --output <dir>`, with [reaction-diffusion-lenia-2023 configs](../../configs/papers/reaction-diffusion-lenia-2023/).

Primary outputs: `summary.json` and the validation and emulation reports written by the mode.

Code: [RD23.swift](../../Sources/LeniaCore/Layer/Papers/RD23.swift), [RD23Command.swift](../../Sources/LeniaCLI/RD23Command.swift).

What we re-implemented: validation and emulation tools around the reaction-diffusion interpretation, and asymptotic-versus-original comparison outputs.

This is the core validation path. It checks whether the continuous dynamics remain mathematically defensible, not only visually plausible. It is a validator, not a discovery command, writes no compendium rows, and should stay small.

### Sensorimotor (2024)

Entrypoint:

- `LeniaCLI discover sensorimotor-2024 --config-dir <dir> --output <dir>`, with [sensorimotor-lenia-2024 configs](../../configs/papers/sensorimotor-lenia-2024/).

Primary outputs: `summary.json`, `history.jsonl`, and the archive and evaluation artifacts written by the mode.

Code: [Sensorimotor24.swift](../../Sources/LeniaCore/Layer/Papers/Sensorimotor24.swift), [Sensorimotor24Command.swift](../../Sources/LeniaCLI/Sensorimotor24Command.swift).

What we re-implemented:

- history and archive bootstrap,
- the goal-sampling curriculum,
- source selection and mutation,
- local optimization toward sampled goals,
- the paper-style evaluation battery for movement, agency, and obstacle robustness.

This implements the 2024 agency-discovery protocol: a principled discovery loop in place of score-only sweeps, and the mode closest to the earlier failure of finding motion without convincing organisms. It is archive-based, not compendium-indexed.

Known gap: real paper-scale runs matter more than more support code; the work needs broad experiments and result comparison.

### QD (LeniaBreeder 2024)

Entrypoints:

- `LeniaCLI discover qd-2024 --config-dir <dir> --algorithm me --output <dir>`
- `LeniaCLI discover qd-2024 --config-dir <dir> --algorithm aurora --output <dir>`
- `LeniaCLI discover qd-2024 --distributed --algorithm me ...`

Configs: [leniabreeder-2024](../../configs/papers/leniabreeder-2024/).

Primary outputs: `summary.json`, `history.jsonl`, `metrics.csv`, `best.json`, `repertoire/centroids.json`, `repertoire/occupied.json`; also `aurora-diagnostics.jsonl` for AURORA and `distributed.json` for distributed MAP-Elites.

Code: [QD24.swift](../../Sources/LeniaCore/Layer/Papers/QD24.swift), [QD24Command.swift](../../Sources/LeniaCLI/QD24Command.swift).

What we re-implemented:

- MAP-Elites repertoire search around the Aquarium-centered structured genotype space,
- time-series metrics after a developmental phase,
- hard viability filtering for empty, full and spread failures,
- AURORA with a VAE-trained latent descriptor,
- COM-centered `32x32x3` phenotype crops,
- `8`-dimensional latent descriptors,
- the unsupervised descriptor as the mean latent trajectory,
- unsupervised fitness as negative average latent dispersion.

This is repertoire discovery, not one-winner search, for broad species discovery when stepping stones and diversity matter. It writes repertoire artifacts, not run-library exports, and is not indexed into `compendium.sqlite`, so its outputs do not reach compendium indexing, taxonomy assignment, the ecology export, or morphometrics thresholding. Distributed support exists for `--algorithm me` only.

Known gap: paper-scale validation, not missing AURORA machinery.

### Ecology (Flow-Lenia 2025)

Entrypoint:

- `LeniaCLI discover ecology-2025 --config-dir <dir> --output <dir>`, with [flowlenia-ecology-2025 configs](../../configs/papers/flowlenia-ecology-2025/).

Primary outputs: `summary.json` and the ecology metrics and artifacts written by the mode.

Code: [Ecology25.swift](../../Sources/LeniaCore/Layer/Papers/Ecology25.swift), [Ecology25Command.swift](../../Sources/LeniaCLI/Ecology25Command.swift).

What we re-implemented: paper-locked intrinsic-evolution ecology runs, evolutionary activity and diversity summaries, and strict validation of the paper regime before execution.

This moves the dossier from isolated specimens to long-run multispecies ecosystem behavior. It is separate from the compendium and indexer pipeline, and from the compendium-based [ecology export](../universe/Ecology.md).

Known gap: judge it by long-horizon ecology outputs, not small smoke tests.

### Curiosity (2025)

Entrypoint:

- `LeniaCLI discover curiosity-2025 --config-dir <dir> --output <dir>`, with [ai-scientist-2025 configs](../../configs/papers/ai-scientist-2025/).

Primary outputs: `summary.json` and the archive and coverage artifacts written by the mode.

Code: [Curiosity25.swift](../../Sources/LeniaCore/Layer/Papers/Curiosity25.swift), [Curiosity25Command.swift](../../Sources/LeniaCLI/Curiosity25Command.swift).

What we re-implemented: curiosity-driven Flow-Lenia universe exploration, paper-specific goal spaces for ecosystem and movement modes, archive and coverage accounting, and MP4-size and non-neutral activity metrics.

This is open-ended universe discovery with system-level novelty metrics in place of creature ranking, not per-creature indexing.

Known gap: the real test is paper-scale exploration, not smoke coverage.

### Atlas (2026)

Entrypoint:

- `LeniaCLI discover atlas-2026 --config-dir <dir> --output <dir>`, with [lenia-atlas-2026 configs](../../configs/papers/lenia-atlas-2026/).

Primary outputs: `summary.json`, `data/phases/*.json`, `data/kernels/**/mu_*/sigma_*.json`.

Code: [Atlas26.swift](../../Sources/LeniaCore/Layer/Papers/Atlas26.swift), [Atlas26Command.swift](../../Sources/LeniaCLI/Atlas26Command.swift).

What we re-implemented: the classical Lenia `mu`/`sigma` atlas, public-style polygon-library input, and paper-style batch semantics and phase-map export.

This maps classical parameter space before glider or creature mining, in place of blind classical sweeps. It does not populate the compendium.

Known gap: full atlas scale and result inspection, not another sweep heuristic.

## The compendium boundary

The compendium is written only by `LeniaCLI index ingest` and by `LeniaCLI discover local` when auto-indexing is enabled. None of the paper modes auto-indexes or emits indexer-ready library or export bundles. A mode becomes compendium-visible only if it emits an artifact layout the indexer understands and is then indexed explicitly. See [The compendium](./CompendiumSchema.md) and [Running a local sweep](./LocalCLI.md).

## Metal and MLX

These modes run on the MLX/Metal path on Apple Silicon, with batched evaluation as the default for the heavy ones.

Relevant code: [FlowLenia.swift](../../Sources/LeniaCore/Core/FlowLenia.swift), [Evolution.swift](../../Sources/LeniaCore/Layer/Search/Evolution.swift), [SignpostSupport.swift](../../Sources/LeniaCore/Layer/Infra/SignpostSupport.swift).

Done so far:

- release-path runs for long paper jobs,
- Instruments signpost support for hot-path profiling,
- rollout sync cleanup so metrics do not force unnecessary host-device barriers,
- external artifact and log routing for long runs on remote volumes.

`reintegrationBatched` remains the strongest custom-kernel candidate if another major speed step is needed.

## Papers

- [Flow-Lenia 2022](https://releases.specterlab.org/records/lenia/2022/001-2022-flow-lenia-towards-open-ended-evolution-in-cellular-automata-through-mass-conservation-and-parameter-localization.pdf)
- [Reaction-Diffusion Lenia 2023](https://releases.specterlab.org/records/lenia/2023/001-2023-implementation-of-lenia-as-a-reaction-diffusion-system.pdf)
- [Discovering Sensorimotor Agency in Cellular Automata using Diversity Search 2024](https://releases.specterlab.org/records/lenia/2024/001-2024-discovering-sensorimotor-agency-in-cellular-automata-using-diversity-search.pdf)
- [Toward Artificial Open-Ended Evolution within Lenia using Quality-Diversity 2024](https://releases.specterlab.org/records/lenia/2024/002-2024-toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity.pdf)
- [Exploring Flow-Lenia Universes with a Curiosity-driven AI Scientist 2025](https://releases.specterlab.org/records/lenia/2025/001-2025-exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-discovering-diverse-ecosystem-dynamics.pdf)
- [Flow-Lenia Emergent Evolutionary Dynamics 2025](https://releases.specterlab.org/records/lenia/2025/002-2025-flow-lenia-emergent-evolutionary-dynamics-in-mass-conservative-continuous-cellular-automata.pdf)
- [Visualizing the Structure of Lenia Parameter Space 2026](https://releases.specterlab.org/records/lenia/2026/001-2026-visualizing-the-structure-of-lenia-parameter-space.pdf)
