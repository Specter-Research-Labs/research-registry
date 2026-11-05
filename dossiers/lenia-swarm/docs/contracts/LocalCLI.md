---
summary: "How to build LeniaCLI and run a local Flow Lenia sweep, what the run directory contains, what must be captured for a run to be reproduced later, and the stored field and specimen formats with the command that rewrites older artifacts."
---

# Running a local sweep

`LeniaCLI discover local` runs one local parameter sweep from a base config and a search config, writes a self-contained run directory, and optionally indexes the result into a compendium.

## Build

MLX Metal shaders are required. The checked-in metallib cache lets `swift build` and `swift test` reuse one compiled shader bundle instead of rebuilding it for each regenerated app or test bundle.

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

If `SPECTER_RUNTIME_ROOT` is set, explicit `/tmp/...` or `/private/tmp/...` outputs resolve under `$SPECTER_RUNTIME_ROOT/lenia-swarm/...` instead of the system temp volume.

With frame export:

```bash
LeniaCLI discover local \
  --config configs/base/paper_base_1c_128.json \
  --search configs/search/search_smoke.json \
  --output /tmp/lenia-smoke \
  --frames \
  --frame-stride 5
```

## Required inputs

- `--config`: base config JSON (`LeniaBaseConfig`).
- `--search`: search config JSON (`ParsedSearchConfig`).
- `--output`: output root; the command writes `--output/<run_id>/`.

The config families these come from are listed in the [config map](../configs/README.md).

## Optional flags

Simulation overrides:

- `--seed`: override `seed_start` from the search config.
- `--count`: override `count` from the search config.
- `--validate-only`: validate the config pair and exit.

Frame export:

- `--frames`: write grayscale frames to `<run_dir>/frames`.
- `--frames-dir <path>`: override the grayscale frame path.
- `--frames-color`: also emit colorized frames.
- `--frames-color-dir <path>`: override the color frame path.
- `--frame-stride <n>`: capture every `n` steps (`n > 0`).
- `--include-warmup-frames`: include warmup steps in capture.
- `--sample-index <n>`: sample index when `batch_size > 1`.

Compendium indexing:

- `--compendium <path>`: explicit compendium path for auto-indexing.
- `--no-promotion`: disable auto-indexing, replay and export promotion, and the warehouse refresh after the run.

Without `--compendium`, the command uses the dossier artifact compendium when one is resolvable from the config path.

Logging:

- `--run-id`, `--log-dir`, `--log-level`, and `--no-log-console` come from the shared log options.

## Enforced invariants

- `count > 0`.
- `batch_size > 0`.
- If any frame output is enabled: `count == 1`, `sample_index == 0`, and `frame_stride > 0`.

The command fails with a validation error if any invariant is violated.

## The run directory

Within `--output/<run_id>/`:

- `config.json`: copied base config.
- `search.json`: copied search config.
- `results.jsonl`: one line per simulation result.
- `summary.json`: run metadata, collection counts, and frame settings.
- `top.json`: top-K passing results (only when at least one result passes).
- `frames/` (optional): grayscale PNG frames.
- `frames_color/` (optional): colorized PNG frames.
- `library/index.jsonl` (optional): collected creatures, when collection is enabled in the search config.
- `exports/index.jsonl` (optional): replay-export bundles for collected creatures, when `collection.export_enabled` is true.
- `exports/<slug>-<id>/base.json`, `search.json`, `meta.json` (optional): export bundles consumed by compendium indexing and later replay and publish stages.
- `media/rank_XXX_seed_YYY/creature.gif`, `video.mp4`, and `frames/frame_XXXXXX.png` (optional): written later by `LeniaCLI publish media`.

Every run has its own `run_id` namespace, and the copied config and search files are the provenance snapshot used for reruns.

Logs and metrics go to `<log_base>/<run_id>/` (for example `local.log.jsonl`, `local.metrics.jsonl`), where the log base is `--log-dir` when given, otherwise `<output>/logs` when `--output` is set, otherwise `./logs`.

The indexer reads run-level `results.jsonl`, library index entries, export index entries, and activity summary JSONL files when present. Re-indexing the same artifacts is idempotent at row level.

## Reproducibility

A run can be reproduced later only if these are captured.

Inputs:

- base config JSON,
- search config JSON,
- explicit seed schedule (`seed_start`, `seed_stride`, `count`),
- implementation-affecting switches (for example compatibility modes).

Per run:

- copied `config.json` and `search.json` in the run directory,
- `summary.json` with the run id and execution counts,
- `results.jsonl` containing metrics and parameter payloads,
- log and metrics streams for the same run id.

Per indexed record:

- `run_id`,
- provenance fields in the `runs` table,
- `config_hash` when available,
- method and version tags for derived fields such as morphometrics and taxonomy.

Results are not guaranteed bitwise identical across different hardware, compiler versions, or MLX backend revisions unless the experiment protocol pins them.

## Storage compaction

### Field patches

Every stored float field (`init.state_patch`, `init.p_state_patch`, `terminal-state.json`, `terminal-params.json`, and the same patches inside creatures, export bundles and Studio organisms) has one encoding:

```json
{"center": [x, y], "width": W, "height": H, "channels": C,
 "encoding": "f32le-shuffle-zlib", "data": "<base64>"}
```

`data` is base64 of a zlib stream (RFC 1950, level 9) of the `W*H*C` little-endian float32 values after a byte-plane shuffle: byte 0 of every value, then byte 1 of every value, then bytes 2 and 3, in the value order the patch has always used. The inflated stream must be exactly `4*W*H*C` bytes. The shuffle groups the near-constant exponent bytes, which is where most of the saving comes from. `FieldCodec` (Swift) and `lenia_swarm_analysis.trace_codec` (Python) share the fixture `Tests/LeniaCoreTests/Fixtures/field-codec.json`, and the codec is lossless to the bit, including NaN payloads and signed zeros.

Decoders accept only `f32le-shuffle-zlib`. The retired raw `f32le` encoding fails with a message naming the compaction command, and any other encoding fails as unknown.

### One copy per specimen

The genotype, initial condition, metrics and descriptor bundle live on the creature (or on the row columns of a result) beside its specimen manifest, and nowhere else. `snapshots` in a specimen manifest holds only `morphometrics`, which has no other home.

Library rows (`library/index.jsonl`) require `runtime_family`, `runtime_capabilities` and `specimen_manifest`. Export `meta.json` requires `bundleKind`, `reason`, `runtimeFamily` and `runtimeCapabilities`. Creatures store their initial condition under `initialCondition`. The retired `phenotype` key, the `qd-2024` runtime family (now `qd24_paper`) and the capability names `native-replay`, `native-intervention` and `phenotype-queryable` are no longer read. The `phenotype` key in compendium release details is the published site format and is unaffected.

### Rewriting an artifact store

Files written before these formats are rewritten in place by:

```bash
cd dossiers/lenia-swarm
uv run lenia-swarm-analysis compact <root> --dry-run
uv run lenia-swarm-analysis compact <root> [--jobs N]
```

The command walks every `*.json` and `*.jsonl` under `<root>`, skipping symlinks, and rewrites only documents that need it. It keeps each file's JSON style (indent, separators, `\/` escaping), leaves unchanged JSONL lines byte-identical, writes numbers in their shortest round-trip form (`0.20000000000000001` becomes `0.2`, the same double), and replaces each file atomically. Before it writes a file it checks that the rewritten text reparses to the same raw float bytes, compared by SHA-256, for every patch.

It fails a file, and leaves it untouched, when:

- a patch has an unknown encoding or a byte count that does not match its shape;
- a snapshot it would drop differs from, or cannot be checked against, the creature it supposedly duplicates;
- a creature lacks a required saved-creature field;
- a retired record has no unambiguous current form, such as an export bundle missing from its `exports/index.jsonl`.

Errors go to stderr and the exit status is 1. Resolve the named files and rerun; the command is idempotent.

A run writes `<root>/compaction-receipts/<UTC>.jsonl`. It holds a header, then one line per rewritten file with byte counts, the file SHA-256 before and after, the raw-float SHA-256 of every converted patch, and the counts of snapshots dropped and manifests written. `--dry-run` prints the projected per-directory table and writes nothing.

Compaction preserves the simulation input exactly: the same LeniaCLI build produces byte-identical `results.jsonl` and `top.json` from a config before and after compaction. A run recorded before a physics change will not reproduce under the current build either way. Compaction does change file bytes and therefore anything hashed over encoded configs. A `config_hash` recorded before compaction is not what LeniaCLI computes from the compacted config, because the hash covers the encoded patch text, and `discover local` refuses to resume a pre-compaction `checkpoint.json` because its `inputHash` covers the config file bytes. SQLite and DuckDB files are not rewritten; reindex from the compacted JSON.

## Determinism smoke test

`dossiers/lenia-swarm/ops/deterministic-smoke.sh` runs two fixed-seed local runs and checks that `results.jsonl` is byte-identical and that exported frame checksums match. Run it from the repo root:

```bash
./dossiers/lenia-swarm/ops/deterministic-smoke.sh
```
