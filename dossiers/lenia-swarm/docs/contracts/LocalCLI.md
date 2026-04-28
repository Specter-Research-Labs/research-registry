# Local CLI Harness (`LeniaCLI discover local`)

## Purpose

`LeniaCLI discover local` runs one local parameter sweep from a base config and a search config, writes a self-contained run directory, and optionally auto-indexes into a compendium.

## Build

MLX Metal shaders are required. The checked-in metallib cache now lets `swift build` and `swift test` reuse one compiled shader bundle instead of rebuilding it for each regenerated app/test bundle.

```bash
cd dossiers/lenia-swarm
xcrun swift build -c release --product LeniaCLI
```

## Quickstart

```bash
cd dossiers/lenia-swarm

LeniaCLI discover local \
  --config configs/base/paper_base_1c_128.json \
  --search configs/search/search_smoke.json \
  --output /tmp/lenia-smoke
```

If `SPECTER_RUNTIME_ROOT` is set, explicit `/tmp/...` or `/private/tmp/...` outputs resolve under
`$SPECTER_RUNTIME_ROOT/lenia-swarm/...` instead of the system temp volume.

With frame export:

```bash
LeniaCLI discover local \
  --config configs/base/paper_base_1c_128.json \
  --search configs/search/search_smoke.json \
  --output /tmp/lenia-smoke \
  --frames \
  --frame-stride 5
```

## Required Inputs

- `--config`: base config JSON (`LeniaBaseConfig`).
- `--search`: search config JSON (`ParsedSearchConfig`).
- `--output`: output root; command writes `--output/<run_id>/`.

## Key Optional Flags

Simulation overrides:

- `--seed`: override `seed_start` from search config.
- `--count`: override `count` from search config.
- `--validate-only`: validate config pair and exit.

Frame export:

- `--frames`: write grayscale frames to `<run_dir>/frames`.
- `--frames-dir <path>`: override grayscale frame path.
- `--frames-color`: also emit colorized frames.
- `--frames-color-dir <path>`: override color frame path.
- `--frame-stride <n>`: capture every `n` steps (`n > 0`).
- `--include-warmup-frames`: include warmup steps in capture.
- `--sample-index <n>`: sample index when `batch_size > 1`.

Compendium indexing:

- `--compendium <path>`: explicit compendium DB path for auto-index.
- `--no-promotion`: disable auto-index, replay/export promotion, and warehouse refresh after run.

If `--compendium` is not provided, the command uses the dossier artifact compendium when one is
resolvable from the config path. Use `--compendium` for an explicit target.

Logging:

- `--run-id`, `--log-dir`, `--log-level`, and `--no-log-console` come from shared log options.
- Log destination stays local by default (`<output>/logs` when `--output` is set, otherwise `./logs`).

## Enforced Invariants

- `count > 0`.
- `batch_size > 0`.
- If any frame output is enabled: `count == 1`.
- If any frame output is enabled: `sample_index == 0`.
- If any frame output is enabled: `frame_stride > 0`.

The command fails with a validation error if any invariant is violated.

## Artifact Layout

Within `--output/<run_id>/`:

- `config.json`: copied base config.
- `search.json`: copied search config.
- `results.jsonl`: one line per simulation result.
- `top.json`: top-K passing results (omitted when no passing result exists).
- `summary.json`: run metadata, collection counts, and frame settings.
- `frames/` (optional): grayscale PNG frames.
- `frames_color/` (optional): colorized PNG frames.
- `library/index.jsonl` (optional): collected creatures when collection is enabled in search config.
- `exports/index.jsonl` (optional): replay-export bundles for collected creatures when `collection.export_enabled` is true.
- `exports/<slug>-<id>/base.json`, `search.json`, `meta.json` (optional): export bundle consumed by compendium indexing and later replay/publish stages.

Logs and metrics are written under `<log_dir>/<run_id>/` (for example `local.log.jsonl`, `local.metrics.jsonl`).

## Determinism Smoke

`dossiers/lenia-swarm/ops/deterministic-smoke.sh` runs two fixed-seed local runs and checks:

- `results.jsonl` byte equality.
- exported frame checksums.

Run from repo root:

```bash
./dossiers/lenia-swarm/ops/deterministic-smoke.sh
```
