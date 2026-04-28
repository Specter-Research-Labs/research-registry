# Compendium SQLite Schema

## Purpose

The compendium is the indexed artifact database produced by `LeniaCLI index`.

## Producer and Consumers

Producer:

- `LeniaCLI index` ingests run artifacts and updates `compendium.sqlite`.

Consumers:

- `LeniaStudio` compendium views.
- `LeniaCLI analyze ecology` and warehouse derivation.
- `LeniaCLI publish compendium`, which materializes static site releases from indexed rows.
- ad hoc SQL analysis.

## Schema Version

Current schema version is `14` (see `Sources/LeniaCLI/CompendiumSchema.swift`).

The indexer enforces an exact match for read commands that depend on schema shape (`analyze ecology`, `compendium-sanity`, and canonical browse/warehouse surfaces).

## Tables

Core tables:

- `compendium_meta`: single-row schema metadata (`schema_version`).
- `runs`: indexed run roots and provenance (`run_id`, `run_dir`, host/output metadata, `config_hash`).
- `campaigns`: run-scoped campaign IDs linked to runs.
- `creatures`: browse/publish rows plus denormalized metrics, taxonomy slots, morphometrics, and a required canonical `canonical_specimen_id` link.
- `exports`: records for exported configs tied to creatures, keyed independently from the user-facing `export_dir`.
- `results`: optional per-seed records when indexing includes results.
- `specimens`: strict canonical specimen rows for replayable/warehouse-derived analysis.
- `ingest_state`: incremental ingestion cursor by source file (`offset`, `size`, `mtime`).

## Migration History

`v1 -> v2`:

- expands `runs` metadata (`run_name`, `host_id`, `output_root`, `indexed_at`),
- normalizes historical run IDs and run-dir metadata.

`v2 -> v3`:

- adds taxonomy fields on `creatures`:
  - `taxonomy_family_id`, `taxonomy_genus_id`, `taxonomy_species_id`,
  - `taxonomy_confidence`, `taxonomy_method`, `taxonomy_version`.
- adds morphometrics fields on `creatures`:
  - `morphometrics_json`, `morphometrics_method`, `morphometrics_version`.

`v3 -> v4`:

- adds `config_hash` to `creatures` and `runs`.

`v4 -> v5`:

- makes `campaigns` run-scoped via a composite `(run_id, campaign_id)` key,
- gives `exports` a stable synthetic primary key so identical relative export paths from different runs do not collide.

`v6 -> v14`:

- adds strict specimen tables and contracts,
- adds runtime family/capability projections,
- normalizes replay naming,
- adds `initial_condition_json` and canonical `creatures.canonical_specimen_id`,
- requires every canonical creature row to resolve to one strict specimen.

## Static Publish Contract

`LeniaCLI publish compendium` reads the indexed SQLite database and emits a
manifest-backed site release under `site/dossiers/lenia-swarm/compendium/data/`.

Publish semantics:

- creature detail payloads come from the indexed compendium row, not from atlas summaries,
- per-creature replay configs are computed from the indexed genotype, phenotype,
  sweep overrides, and the run's recorded search config,
- stage media can also be materialized during publish:
  - `poster.png`,
  - `field.png`,
  - `delta.png`,
  - `neighbor.png`,
  - `kernel.png`,
  - optional `replay.json` plus `frames.bin`,
- published detail and index payloads may carry `media` and `telemetry` objects when
  stage media is rendered,
- publish is fail-loud if the run snapshots needed to compute those replay configs
  are missing.

## Morphometrics Contract

`creatures.morphometrics_json` is computed during indexing.

Current method metadata:

- `morphometrics_method = "lenia-swarm:morphometrics"`
- `morphometrics_version = 1`

Inputs:

- always: `metrics_json` (`SimulationMetrics`),
- optional enrichment: activity summaries from `overall/activity.jsonl` or `campaigns/*/activity.jsonl`.

If activity summaries are absent, activity-derived morphometric fields remain `null`.

## Taxonomy Status

Taxonomy columns are present in schema but taxonomy assignment is not currently performed by the indexer. New rows are written with `NULL` taxonomy IDs/method/version until a taxonomy pass is implemented.

## Indexing Semantics

- Ingestion is incremental per file via `ingest_state`.
- Re-indexing upserts rows by primary key.
- Indexing is explicit and fail-loud on schema mismatch.
- Canonical browse and warehouse flows require `creatures.canonical_specimen_id` to resolve every creature row to a strict specimen row.
