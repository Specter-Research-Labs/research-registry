# lenia-swarm

Distributed parameter search for Flow Lenia across Apple machines using Swift Distributed Actors and MLX Swift.

## Documentation

- `docs/README.md`: documentation map (runbooks, concepts, configs, internals).
- `docs/configs/README.md`: compact map of the config families and canonical entry files.
- `docs/universe/`: concept docs (physics, morphology, ecology, taxonomy).
- `docs/contracts/`: CLI/schema/artifact/reproducibility contracts.
- `docs/internals/`: implementation-level references and maps.
- `docs/decisions/`: ADRs for long-lived doc and schema decisions.

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
- `make smoke-deterministic`: fixed-seed local determinism harness.
- `make smoke-cluster`: controller+worker smoke run.

## Usage

### Grouped CLI Tree

- `LeniaCLI discover local`: deterministic local run harness and auto-indexing.
- `LeniaCLI discover evolve|mutate|rd-2023|sensorimotor-2024|qd-2024|ecology-2025|curiosity-2025|atlas-2026`: paper-grounded discovery lanes.
- `LeniaCLI orchestrate controller|worker|campaign`: distributed sweep, worker, and campaign dispatch.
- `LeniaCLI index ingest|sanity|backfill`: compendium ingest and repair.
- `LeniaCLI analyze warehouse|topology|biological|discovery|ecology|taxonomy`: warehouse refresh and derived analysis.
- `LeniaCLI intervene battery|holonomy`: intervention batteries and transport experiments.
- `LeniaCLI publish replay|compendium|atlas`: replay, media, compendium, and atlas export.
- `LeniaCLI tt run`: Tenstorrent backend trajectory execution with optional quietbox SSH/container orchestration and Studio frame export.
- `LeniaCLI benchmark` and `LeniaCLI export-reference`: standalone utility surfaces.

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
`dispatch run --on quietbox --device wormhole:... -- ...` when dispatch should
own TT device reservation for backend profiling; in that mode the command is
already running in the remote workspace, so do not wrap it in another
`LeniaCLI --host` SSH hop.

### Local CLI Harness

See `docs/contracts/LocalCLI.md` for the `LeniaCLI discover local` interface, artifact layout, and a deterministic smoke script.

### Surface Operations

`LeniaCLI` and `LeniaStudio` compute run artifacts, compendia, and warehouse
data. `spctr surface` preserves the declared `lenia-compendium` raw roots; any
master compendium should be rebuilt from those preserved artifacts rather than
merged from local SQLite files:

```bash
spctr surface status lenia-compendium
spctr surface checkpoint lenia-compendium
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

Run `LeniaCLI orchestrate controller --help` for the full flag surface.

### Worker

```bash
LeniaCLI orchestrate worker \
  --port 7338 \
  --controller 192.0.2.10
```

Workers discover the controller and register automatically. The controller assigns seed ranges
until exhausted.
Run `LeniaCLI orchestrate worker --help` for the full flag surface.

### Evolve

Run evolution strategy optimization on Lenia parameters:

```bash
LeniaCLI discover evolve \
  --config configs/base/paper_base_1c_128.json \
  --es configs/es/es_directed_motion.json \
  --output ./evolution_results
```

Run `LeniaCLI discover evolve --help` for the full flag surface.

### Mutate

Apply mutations to parameters from search results:

```bash
LeniaCLI discover mutate \
  --config configs/base/paper_base_1c_128.json \
  --params ./results/top.json \
  --rank 0 \
  --param-jitter-std 0.05 \
  --clip
```

Run `LeniaCLI discover mutate --help` for the full flag surface.

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

**Mutate** writes to output directory:
- `config.json`: Mutated config
- `params.json`: Extracted parameters
- `mutation.json`: Mutation record
