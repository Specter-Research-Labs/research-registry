# Data Card (Draft): Lean Sorry Benchmark Index

## Dataset Surface
- Primary input: `index.jsonl`
- Expected companion: `index.jsonl.manifest.json` (upstream provenance metadata)
- This addendum consumes index artifacts only; it does not crawl repositories directly.

## Required Row Fields
Each row must provide:
- `item_id`
- `repo_remote`
- `repo_commit`
- `repo_lean_version` (nullable)
- `location_path`
- `location_start_line`, `location_start_column`
- `location_end_line`, `location_end_column`
- `goal_sha256` (nullable)
- `goal_text`
- `source_url`

Rows fail fast on missing/invalid fields. Missing `goal_text` is a hard error.

## Derived Fields And Normalization
- `goal_bucket` is derived in-code:
  - `core_easy` when the goal text passes strict heuristic checks.
  - `full` otherwise.
- Rows are sorted by `item_id` before selection and hashing.

## Split And Contamination Controls
Frozen split generation (`split-artifacts` command on `lean_sorry_repos_benchmark`) uses:
- Repo holdout by deterministic hash of `(seed, repo_remote)`.
- Exact contamination check by `goal_sha256`.
- Near-duplicate contamination check by token Jaccard on normalized `goal_text`.
- Additional near-duplicate signal by character n-gram Jaccard.
- Automatic drop of contaminated heldout rows with explicit accounting:
  - `dropped_test_item_ids`
  - `leak_fraction`
  - overlap pair listings
- Release controls:
  - `license_policy`: `any` or `open_only`
  - `release_visibility`: `full` or `public`

## Release Pinning Requirements
For a releasable data/baseline bundle, pin:
- `public_dev.jsonl`
- `heldout_test.jsonl` (for `release_visibility=full` only)
- `heldout_test_commitments.json` (required for both `full` and `public`)
- `split_manifest.json`
- `contamination_report.json`
- `artifact_checksums.json`
- SHA-256 checksums for each pinned file
- annotated git tags for the split release and baseline run release

`split_manifest.json` and `contamination_report.json` must include:
- source `index_sha256`
- split config (`seed`, `repo_holdout_fraction`, `near_dup_jaccard_threshold`, `char_ngram_jaccard_threshold`, `license_policy`, `max_leak_fraction`)
- release visibility metadata (`full` vs `public`)

For public distribution, prefer `license_policy=open_only` and `release_visibility=public`.
