# Research Modes

Defines the paper-grounded entrypoints in `lenia-swarm`.

Implementation detail belongs in [PaperGroundedLanes](../internals/PaperGroundedLanes.md). Config families and canonical entry files are mapped in [Config Map](../configs/README.md).

## Registry

| Mode | Paper anchor | Public entrypoint | Config family | Current scope |
| --- | --- | --- | --- | --- |
| Flow tasks | Flow-Lenia 2022 | `LeniaCLI discover evolve` | `configs/base/`, `configs/search/`, `configs/es/` | task-conditioned optimization |
| RD validation | Reaction-Diffusion Lenia 2023 | `LeniaCLI discover rd-2023` | paper bundle + `configs/presets/` | mathematical validation/emulation |
| Sensorimotor | Hamon et al. 2024 | `LeniaCLI discover sensorimotor-2024` | paper bundle + `configs/presets/` | goal-conditioned diversity search |
| QD | LeniaBreeder 2024 | `LeniaCLI discover qd-2024` | `configs/presets/`, `configs/sweeps/`, `configs/es/` | MAP-Elites and AURORA repertoire search |
| Ecology | Flow-Lenia ecology 2025 | `LeniaCLI discover ecology-2025` | paper bundle + `configs/presets/` | intrinsic-evolution ecology runs |
| Curiosity | AI scientist 2025 | `LeniaCLI discover curiosity-2025` | paper bundle + `configs/presets/` | curiosity-driven universe exploration |
| Atlas | Lenia parameter space 2026 | `LeniaCLI discover atlas-2026` | paper bundle + `configs/presets/` | classical Lenia atlas runs |

Retired user-facing names:

- `leniabreeder-2024`
- `flowlenia-ecology-2025`
- `ai-scientist-2025`

Those names may still appear in config directories and older artifacts because they remain provenance labels.

## Shared Rules

- Paper-specific logic must live above the shared simulator.
- No research mode may silently change the core Flow-Lenia equations.
- The invariant guard is [LeniaCoreTests.swift](../../Tests/LeniaCoreTests/LeniaCoreTests.swift), especially `testPopulationKernelsMatchSingleKernelPath`.
- Durable run outputs should go to `SPECTER_ARTIFACT_ROOT` when set; otherwise the mode writes to the explicit `--output` path.
- Contract changes to run outputs must remain deterministic and rerunnable from captured configs.

## Mode Surfaces

### Flow tasks

Entrypoint:

- `LeniaCLI discover evolve --config <task.json> --es <optimizer.json> --output <dir>`

Primary outputs:

- `summary.json`
- `history.jsonl`
- task-specific run artifacts captured by `evolve`

Notes:

- This mode is for explicit objectives such as directed motion, angular motion, obstacle navigation, and chemotaxis.
- It is not a repertoire builder and it is not a compendium writer.

### RD validation

Entrypoint:

- `LeniaCLI discover rd-2023 --config-dir <dir> --output <dir>`

Primary outputs:

- `summary.json`
- validation/emulation reports written by the mode

Notes:

- This mode is a validator.
- It is not a discovery lane and it does not write compendium rows.

### Sensorimotor

Entrypoint:

- `LeniaCLI discover sensorimotor-2024 --config-dir <dir> --output <dir>`

Primary outputs:

- `summary.json`
- `history.jsonl`
- archive/evaluation artifacts written by the mode

Notes:

- This mode implements the 2024 agency-discovery protocol.
- It is archive-based, not compendium-indexed.

### QD

Entrypoints:

- `LeniaCLI discover qd-2024 --config-dir <dir> --algorithm me --output <dir>`
- `LeniaCLI discover qd-2024 --config-dir <dir> --algorithm aurora --output <dir>`
- `LeniaCLI discover qd-2024 --distributed --algorithm me ...`

Primary outputs:

- `summary.json`
- `history.jsonl`
- `metrics.csv`
- `best.json`
- `repertoire/centroids.json`
- `repertoire/occupied.json`

Additional outputs:

- `aurora-diagnostics.jsonl` for AURORA
- `distributed.json` for distributed MAP-Elites

Notes:

- `qd-2024` writes repertoire artifacts, not run-library exports.
- `qd-2024` is not auto-indexed into `compendium.sqlite`.
- There is currently no built-in bridge from `qd-2024` outputs to:
  - compendium indexing
  - taxonomy assignment
  - ecology export
  - morphometrics thresholding
- Distributed support currently exists for `--algorithm me` only.

### Ecology

Entrypoint:

- `LeniaCLI discover ecology-2025 --config-dir <dir> --output <dir>`

Primary outputs:

- `summary.json`
- ecology metrics/artifacts written by the mode

Notes:

- This mode studies long-run ecosystem dynamics.
- It is separate from the compendium/indexer pipeline.

### Curiosity

Entrypoint:

- `LeniaCLI discover curiosity-2025 --config-dir <dir> --output <dir>`

Primary outputs:

- `summary.json`
- archive/coverage artifacts written by the mode

Notes:

- This mode is system-level exploration, not per-creature indexing.

### Atlas

Entrypoint:

- `LeniaCLI discover atlas-2026 --config-dir <dir> --output <dir>`

Primary outputs:

- `summary.json`
- `data/phases/*.json`
- `data/kernels/**/mu_*/sigma_*.json`

Notes:

- This mode maps classical parameter space.
- It does not auto-populate the compendium.

## Compendium Boundary

The compendium remains the indexed database produced by `LeniaCLI index ingest`.

Relevant docs:

- [CompendiumSchema](./CompendiumSchema.md)
- [ArtifactLayout](./ArtifactLayout.md)
- [IndexerInternals](../internals/IndexerInternals.md)

Current writer-of-record surfaces:

- `LeniaCLI index ingest`
- `LeniaCLI discover local` when auto-indexing is enabled

Research modes do not become compendium-visible unless they emit an artifact layout that the indexer understands and are then indexed explicitly.

Current status by mode:

| Mode | Auto-indexes into compendium | Emits indexer-ready library/export bundles |
| --- | --- | --- |
| Flow tasks | No | No |
| RD validation | No | No |
| Sensorimotor | No | No |
| QD | No | No |
| Ecology | No | No |
| Curiosity | No | No |
| Atlas | No | No |

## Apple Silicon Note

These modes are intended to run on the MLX/Metal path on Apple Silicon.

Current performance facts that affect the contract:

- batched evaluation is the default expectation for the heavy modes,
- `qd-2024` has local and distributed MAP-Elites paths,
- `reintegrationBatched` remains the main custom-kernel candidate if another major speed step is needed.

## Papers

- [Flow-Lenia 2022](https://releases.specterlab.org/records/lenia/2022/001-2022-flow-lenia-towards-open-ended-evolution-in-cellular-automata-through-mass-conservation-and-parameter-localization.pdf)
- [Reaction-Diffusion Lenia 2023](https://releases.specterlab.org/records/lenia/2023/001-2023-implementation-of-lenia-as-a-reaction-diffusion-system.pdf)
- [Discovering Sensorimotor Agency in Cellular Automata using Diversity Search 2024](https://releases.specterlab.org/records/lenia/2024/001-2024-discovering-sensorimotor-agency-in-cellular-automata-using-diversity-search.pdf)
- [Toward Artificial Open-Ended Evolution within Lenia using Quality-Diversity 2024](https://releases.specterlab.org/records/lenia/2024/002-2024-toward-artificial-open-ended-evolution-within-lenia-using-quality-diversity.pdf)
- [Exploring Flow-Lenia Universes with a Curiosity-driven AI Scientist 2025](https://releases.specterlab.org/records/lenia/2025/001-2025-exploring-flow-lenia-universes-with-a-curiosity-driven-ai-scientist-discovering-diverse-ecosystem-dynamics.pdf)
- [Flow-Lenia Emergent Evolutionary Dynamics 2025](https://releases.specterlab.org/records/lenia/2025/002-2025-flow-lenia-emergent-evolutionary-dynamics-in-mass-conservative-continuous-cellular-automata.pdf)
- [Visualizing the Structure of Lenia Parameter Space 2026](https://releases.specterlab.org/records/lenia/2026/001-2026-visualizing-the-structure-of-lenia-parameter-space.pdf)
