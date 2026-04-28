# lean-sorry-dataset

Ingests Lean `sorry` data for benchmarking.

Consumes SorryDB-compatible snapshots (e.g., `sorry_database.json` or `deduplicated_sorries.json`)
and materializes a deterministic benchmark index for downstream use in
`addenda/lean-sorry-repos-benchmark`.

## Scope
- Ingest pinned JSON snapshots from local path or URL.
- Normalize records into one explicit JSONL schema.
- Emit deterministic IDs, plus reproducibility manifest and summary counts.
- Optionally resolve GitHub license metadata and filter to open-license repos.

## Install / Check
```bash
cd addenda/lean-sorry-dataset
nix develop
uv run ruff check .
uv run ty check
uv run python -m pytest
```

If you use direnv, `direnv allow` from `addenda/lean-sorry-dataset/` is equivalent. The shell
auto-runs `uv sync`.

## Build Benchmark Index
Example using the public SorryDB deduplicated snapshot:

```bash
cd addenda/lean-sorry-dataset
uv run python -m lean_sorry_dataset build-index \
  --snapshot https://raw.githubusercontent.com/SorryDB/sorrydb-data/master/deduplicated_sorries.json \
  --out ../../tmp/lean-sorry/index.jsonl \
  --resolve-github-license \
  --require-open-license
```

The command writes:
- `index.jsonl`: normalized benchmark rows.
- `index.jsonl.manifest.json`: provenance, config, and summary stats.

## Backfill License Metadata On Existing Index
When you already have an `index.jsonl` (for example with `repo_license_*` fields unresolved),
run targeted backfill without rebuilding from snapshot:

```bash
cd addenda/lean-sorry-dataset
uv run python -m lean_sorry_dataset license-backfill \
  --index ../../tmp/lean-sorry-with-goals/index.jsonl \
  --out ../../tmp/lean-sorry-with-goals/index.licensed.jsonl
```

Optional strict filtering:

```bash
uv run python -m lean_sorry_dataset license-backfill \
  --index ../../tmp/lean-sorry-with-goals/index.jsonl \
  --out ../../tmp/lean-sorry-with-goals/index.open-only.jsonl \
  --require-open-license
```

The backfill command writes:
- backfilled index JSONL.
- backfill manifest (`<out>.manifest.json`) with lookup/error stats.

## Row Contract (v1)
Each row includes:
- `item_id`: deterministic SHA-256 over `(repo, commit, file path, location span)`.
- Repository provenance (`repo_remote`, `repo_branch`, `repo_commit`, `repo_lean_version`).
- Location provenance (`location_*` fields, `source_url`).
- Goal traceability (`goal_sha256`, optional `goal_text`).
- Optional license metadata (`repo_license_spdx`, `repo_license_open`).

## Integration Contract (Benchmark Addendum)
`addenda/lean-sorry-repos-benchmark` should treat `index.jsonl` + manifest as its canonical input.
That keeps dataset ingestion and benchmark policy as separate surfaces.
