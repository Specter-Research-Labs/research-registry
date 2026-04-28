# Artifact Layout Contract

## Purpose

Defines canonical on-disk outputs for local runs and indexing inputs.

## Local Run Root

`LeniaCLI discover local --output <root>` creates:

- `<root>/<run_id>/config.json`
- `<root>/<run_id>/search.json`
- `<root>/<run_id>/results.jsonl`
- `<root>/<run_id>/summary.json`
- `<root>/<run_id>/top.json` (only when at least one passing result exists)
- `<root>/<run_id>/frames/` (optional)
- `<root>/<run_id>/frames_color/` (optional)
- `<root>/<run_id>/media/rank_XXX_seed_YYY/creature.gif` (optional `publish media` output)
- `<root>/<run_id>/media/rank_XXX_seed_YYY/video.mp4` (optional `publish media` output)
- `<root>/<run_id>/media/rank_XXX_seed_YYY/frames/frame_XXXXXX.png` (optional per-frame media output)
- `<root>/<run_id>/library/index.jsonl` (optional when collection enabled)

## Logs and Metrics

Log base resolution:

1. explicit `--log-dir` when provided,
2. otherwise `<output>/logs` when `--output` is set,
3. otherwise local `./logs`.

Run logs then live under `<log_base>/<run_id>/`.

## Indexing Inputs

Indexer ingests run artifacts and may also ingest activity summaries when present.

Expected ingestable sources include:

- run-level `results.jsonl`,
- library index entries,
- export index entries,
- activity summary JSONL files.

## Invariants

- Every run has a unique `run_id` namespace in artifact paths.
- Copied config/search files inside run dir are the provenance snapshot used for reruns.
- Reindexing the same artifact set must be idempotent at row level (upsert semantics).
