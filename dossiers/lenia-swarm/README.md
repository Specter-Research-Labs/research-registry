# lenia-swarm

Distributed parameter search for Flow Lenia across Apple machines using Swift Distributed Actors and MLX Swift.

## Documentation

- `docs/README.md`: documentation map (runbooks, concepts, configs, internals).
- `docs/configs/README.md`: compact map of the config families and canonical entry files.
- `docs/universe/`: concept docs (physics, morphology, ecology, taxonomy).
- `docs/contracts/`: CLI/schema/artifact/reproducibility contracts.
- `docs/internals/`: implementation-level references and maps.
- `docs/decisions/`: ADRs for long-lived doc and schema decisions.
- `ops/docs/TTBackend.md` and `ops/docs/TTBackendPerformance.md` (repo root): TT backend operation,
  launcher rules, and performance facts.

## Architecture

Controller-worker topology over a SWIM gossip cluster, with an MLX Swift physics engine for
GPU-accelerated Flow Lenia simulation.

- `LeniaCore`: physics engine, distributed actors, and search infrastructure.
- `LeniaCLI`: headless workflows under `discover`, `orchestrate`, `index`, `analyze`,
  `intervene`, and `publish`.
- `LeniaStudio`: macOS SwiftUI app for local exploration, host mode, and worker mode.

`DistributedCluster` handles cluster communication. Worker failures are detected automatically;
pending jobs are requeued.

## Requirements

- macOS 15+
- Swift 6.0+
- Xcode (required for Metal shader compilation)

## Environment

Enter the local project shell from `dossiers/lenia-swarm/`:

```bash
nix develop
```

If you use direnv, `direnv allow` is equivalent. The shell auto-runs `uv sync` for the Python
analysis package and `swift package resolve` for the Swift package graph.

## Building

Use `xcodebuild` for app and CLI builds that need bundled Metal resources:

```bash
# Build CLI (discover/orchestrate/index/analyze/intervene/publish plus benchmark/export-reference)
xcodebuild build -scheme LeniaCLI -destination 'platform=OS X' -configuration Release

# Build Studio (macOS app)
xcodebuild build -scheme LeniaStudio -destination 'platform=OS X' -configuration Release

# Binary locations
~/Library/Developer/Xcode/DerivedData/lenia-swarm-*/Build/Products/Release/LeniaCLI
~/Library/Developer/Xcode/DerivedData/lenia-swarm-*/Build/Products/Release/LeniaStudio
```

For convenience:
```bash
alias lenia-cli="$(find ~/Library/Developer/Xcode/DerivedData -name 'LeniaCLI' -path '*/Release/*' ! -path '*.dSYM*' -type f 2>/dev/null | head -1)"
alias lenia-studio="open $(find ~/Library/Developer/Xcode/DerivedData -name 'LeniaStudio' -path '*/Release/*' ! -path '*.dSYM*' -type f 2>/dev/null | head -1)"
```

LeniaStudio needs MLX's Metal library. In the Nix dev shell, `MLX_METAL_PATH` is auto-detected.
Outside the shell, set it manually if needed:

```bash
export MLX_METAL_PATH=/path/to/mlx.metallib
```

Example locations:

- `dossiers/lenia-swarm/.build/arm64-apple-macosx/debug/mlx.metallib`
- `<site-packages>/mlx/lib/mlx.metallib`

## Verification

Use the dossier-local `Makefile` for the standard checks:

```bash
make check
```

Useful individual targets:

- `make check-swift`: package-level Swift tests.
- `make check-python`: Ruff, Ty, and Pytest for `lenia_swarm_analysis/`.
- `make smoke-deterministic`: fixed-seed local determinism check.
- `make smoke-cluster`: controller+worker smoke run.

## Usage

### Grouped CLI Tree

- `LeniaCLI discover local`: deterministic local runs and auto-indexing.
- `LeniaCLI discover evolve|rd-2023|sensorimotor-2024|qd-2024|ecology-2025|curiosity-2025|atlas-2026`: paper-grounded discovery commands.
- `LeniaCLI discover obstacle-response`: paired sham and heading-relative obstacle continuations for a fixed Flow Lenia corpus.
- `LeniaCLI discover capacity-pilot --config BASE.json --corpus CORPUS.jsonl --output RUN`: paired small/large deformations and balanced internal-channel edits of a fixed multi-channel corpus. Saves the step-1,200 checkpoint, eight branch trajectories, final Float32 fields, configuration inputs, and a repeat-continuation check. The channel write exchanges matter only between channels 0 and 1, leaves additional channels unchanged, and checks every channel inventory. Its dose is measured against total matter across all channels. The default horizon is 1,024 steps; this is a sensitivity and prediction pilot, not an assay of a rewritten restoration target.
- Add `--study development --horizon 3600` for an unperturbed world-coordinate trajectory, or `--study response --horizon 512` for paired deformations at three ages with full fields saved every 32 steps. These modes preserve the configured backend and boundaries and support single-channel additive Lenia. Periodic shears use the shortest displacement from the body centre; additive trajectories may gain or lose matter. Balanced channel writes remain restricted to the existing multichannel Flow studies.
- For the moving Flow cohort, use `--study response --checkpoint-steps 1216 --response-offsets 0,608,1184,1792 --horizon 512 --probe-horizon 512`: four preserved checkpoints and five paired branches each. The response defaults remain three offsets and a 128-step probe. The active capacity programme selects explicit Flow configurations; additive support is retained for archived comparisons only.
- For write/release comparisons on the moving Flow cohort, use `--study write-response --checkpoint-steps 1088 --write-mode positive --write-dose 0.04 --release-steps 128 --challenge-sign=1 --horizon 512`. This Flow-only study saves the prewrite field, release trajectory, and paired unchallenged/sheared continuations with full fields every 32 steps. Use `--challenge-sign=-1` for the opposite shear; modes are `sham`, `positive`, `negative`, and `scrambled`. It validates immediate visible-density and channel-inventory conservation.
- A precomputed local exchange can use `--write-mode field --write-field EDITED.f32` in `write-response`. Supply native `[x,y,channel]` Float32 values for that checkpoint; the harness checks dimensions, nonnegativity, visible-density conservation and channel inventories, and archives the input. `--challenge-axis y` transposes the existing conservative shear onto the other axis.
- Add `--study symmetry` to compare quarter-turn and axis-swap continuations at initialization and the checkpoint. Add `--study followup --horizon 512` for three sampling ages, matched passive/probe observations, and seven channel-edit histories followed by paired challenges after a 256-step wait. The delayed opposite write is a new intervention, not an exact inverse; immediate checkpoint restoration is the handling control. This harness preserves the configured engine, including any measured anisotropy, so engine corrections require a separately recorded comparison.
- `LeniaCLI orchestrate controller|worker|campaign`: distributed sweep, worker, and campaign dispatch.
- `LeniaCLI index ingest|sanity|backfill`: compendium ingest and repair.
- `LeniaCLI analyze warehouse|topology|biological|discovery|ecology|taxonomy`: warehouse refresh and derived analysis.
- `LeniaCLI intervene holonomy`: transport experiments.
- `LeniaCLI orchestrate campaign --campaign configs/campaigns/intervention-battery.json --output RUN`: the intervention battery as a declarative campaign phase.
- `LeniaCLI publish replay|compendium|atlas`: replay, media, compendium, and atlas export.
- `LeniaCLI tt run`: Tenstorrent backend trajectory execution with optional quietbox SSH/container orchestration and Studio frame export.
- `LeniaCLI benchmark` and `LeniaCLI export-reference`: standalone utility commands.
- `lenia-swarm-analysis`: canonical Python analysis CLI for TDA, fibers,
  transport, packet builders, named-family preset extraction, and warehouse
  bridge operations. Existing `lenia-swarm-*` Python commands remain
  compatibility aliases.

### Tenstorrent Runs

`LeniaCLI tt run` is the user-facing entrypoint for the TT backend. It delegates
compute to the TT Python runtime and can run on a local TT host or over SSH to
quietbox while exporting raw frame sequences that Lenia Studio can replay.
Remote runs require `--remote-root` or `LENIA_TT_REMOTE_ROOT` pointing at the
Lenia dossier on the target host.
When using dispatch's mirrored workspace, that path is the dispatch
`remote_cwd`.
For search-style batches, pass `--seed-list` with `--batch-size`; each TT run
writes `tt_run.json` so the Swift pipeline can recover candidate provenance
without duplicating scoring, collection, or Studio indexing in Python.

```bash
export LENIA_TT_REMOTE_ROOT="$(dispatch workspace plan --on quietbox --project specter-labs --json | jq -r .remote_cwd)"

LeniaCLI tt run \
  --host quietbox \
  --config configs/base/paper_base_2c_128.json \
  --output tmp/tt-runs/orbitum-128 \
  --execution-mode single \
  --tt-card-num 0 \
  --steps 300 \
  --frame-every 5

LeniaCLI tt run \
  --host quietbox \
  --config configs/base/paper_base_2c_128.json \
  --output tmp/tt-runs/fleet-128 \
  --execution-mode fleet \
  --device-list 0,1,2,3 \
  --tt-card-list 0,1,2,3 \
  --batch-size 4 \
  --steps 300 \
  --frame-every 10
```

Use `LeniaCLI --host` for the main Studio/export path. Use
`dispatch run --on quietbox --device wormhole:... -- ...` when dispatch owns
TT device reservation for backend profiling; in that mode the command is
already running in the remote workspace, so do not wrap it in another
`LeniaCLI --host` SSH hop.

### Local CLI Harness

See `docs/contracts/LocalCLI.md` for the `LeniaCLI discover local` interface, artifact layout, and a deterministic smoke script.

### Surface Operations

`LeniaCLI` and `LeniaStudio` append into one local compendium at the shared
Lenia artifacts root: `lenia-swarm/artifacts/compendium.sqlite`, with the
warehouse beside it as `morphospace.duckdb`. A checkout under
`research-registry-workspaces/` resolves canonical artifact paths to the sibling
main `research-registry/dossiers` tree, so workspace runs append to the same
local store instead of creating workspace-local compendiums. `local_artifact_root`
in the machine `spctr` config is only for machines whose checkout layout differs.
`spctr surface sync` checkpoints the declared compendium artifacts and promotes
the current compendium snapshot:

```
spctr surface status lenia-compendium
spctr surface sync lenia-compendium
```

### Studio

Launch the macOS app for interactive exploration:

```bash
open ~/Library/Developer/Xcode/DerivedData/lenia-swarm-*/Build/Products/Release/LeniaStudio
```

Use host mode to run the controller and manage campaigns. Use worker mode to join an existing
controller, contribute search, and inspect local or cluster discoveries.

### Benchmark

Run a current local benchmark:

```bash
LeniaCLI benchmark --batch-size 16 --steps 100
```

For reproducible performance records, write dated benchmark artifacts with machine, commit, grid
size, kernel count, batch size, and build configuration.

### Controller

```bash
LeniaCLI orchestrate controller \
  --config configs/base/paper_base_1c_128.json \
  --search configs/search/search_smoke.json \
  --output ./results \
  --auto-exit
```

Run `LeniaCLI orchestrate controller --help` for all flags.

### Worker

```bash
LeniaCLI orchestrate worker \
  --port 7338 \
  --controller 192.0.2.10
```

Workers discover the controller and register automatically. The controller assigns seed ranges
until exhausted.
Run `LeniaCLI orchestrate worker --help` for all flags.

### Evolve

Run evolution strategy optimization on Lenia parameters:

```bash
LeniaCLI discover evolve \
  --config configs/base/paper_base_1c_128.json \
  --es configs/es/es_directed_motion.json \
  --output ./evolution_results
```

Run `LeniaCLI discover evolve --help` for all flags.

## Output

**Controller** writes under `<output>/overall/`:
- `results.jsonl`: all individual simulation results
- `top.json`: global top-K ranked by score
- `summary.json`: execution statistics
- `library.json`: auto-detected stable creatures (compact, surviving patterns)

**Evolve** writes to output directory:
- `best.json`: Best fitness and parameters found
- `best_config.json`: Full config with best parameters
- `history.jsonl`: Per-generation fitness statistics
- `config.json`, `es_config.json`: Input configs (copied)

Flow integrator conventions and the pinned author regression are documented in
[Flow coordinates and the reference regression](docs/flow-spatial-conventions.md).

The capacity pilot also provides `--study transport` for a passive material-ancestry audit in a clean native Flow runtime. It exports each actual pre-step channel flow and the following mass field in a fixed 256-cell window, during release and a positive x shear. Crop origin, full and cropped mass, and the exact shear centre are recorded in `transport.json`. Use the saved transport weights to trace a chosen later region backward; this does not reverse the nonlinear dynamics or introduce an additional channel. Validate the reconstructed forward transport and crop coverage before interpreting ancestry.

The `capacity-pilot --study state-response --write-mode field --write-field FIELD --release-steps 0` study replaces the mass field at a checkpoint before paired challenged and unchallenged continuations. It preserves total matter but permits changed density and channel inventories, for explicit geometry/composition counterfactuals. The `write-response` study still requires both visible density and channel inventories to be preserved. Archive the input field and its construction checks with the run.

Use `capacity-pilot --study write-release` for a balanced write followed only by its unforced release interval. It uses the same density and channel-inventory validation as `write-response`; the paired challenge is omitted so long-term target discovery does not spend compute on an unrequested disturbance.

`capacity-pilot --study state-continuation --write-mode field --write-field FIELD --checkpoint-steps 0 --horizon STEPS` resumes a mass field in the clean autonomous Flow runtime with fixed, unembedded parameters. It records relative time from the saved state and emits one continuation. This path rejects embedded parameters; archive source age and field hashes with the assay, and verify restart against an existing uninterrupted trajectory.

`capacity-pilot --study state-flow --write-mode field --write-field FIELD --checkpoint-steps 0 --horizon 128` passively records the native pre-step channel flow and the following full mass field at steps 0, 1, 2, 4, 8, 16, 32, 64, 128 and the horizon. It exports the compiled spatial kernels and channel routing for per-pathway decomposition. It uses the same fixed-parameter restart constraints as `state-continuation`; validate recorded fields against an existing continuation and reconstructed flow/transport against native outputs before interpreting a causal intervention. The sample at the horizon also advances one step to retain its corresponding next field.
