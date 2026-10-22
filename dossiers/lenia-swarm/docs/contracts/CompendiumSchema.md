---
summary: "The Lenia compendium: its SQLite schema and migrations, how the indexer writes it, how Studio and the CLI read it, and why readers require an exact version."
---

# The compendium

The compendium is the SQLite database of indexed run artifacts, `compendium.sqlite`, produced by `LeniaCLI index` (whose default subcommand is `index ingest`).

## Producer and consumers

Producer:

- `LeniaCLI index` ingests run artifacts and updates `compendium.sqlite`.
- `LeniaCLI discover local` indexes its own run when auto-indexing is enabled.
- `LeniaCLI analyze taxonomy` fills the taxonomy columns afterwards (see [Taxonomy](../universe/Taxonomy.md)).

Consumers:

- `LeniaStudio` compendium views.
- `LeniaCLI analyze ecology` and warehouse derivation.
- `LeniaCLI publish compendium`, which materializes static site releases from indexed rows.
- ad hoc SQL analysis.

## Schema version

The current schema version is `15`, set by `compendiumSchemaVersion` in `Sources/LeniaCLI/Compendium/Schema.swift`.

Commands that depend on schema shape require an exact match: `analyze ecology`, `analyze taxonomy`, `index sanity`, and the canonical browse and warehouse surfaces.

## Tables

- `compendium_meta`: single-row schema metadata (`schema_version`).
- `runs`: indexed run roots and provenance (`run_id`, `run_dir`, host and output metadata, `config_hash`).
- `campaigns`: run-scoped campaign IDs linked to runs.
- `creatures`: browse and publish rows with denormalized metrics, taxonomy, morphometrics, and a required `canonical_specimen_id` link.
- `creature_qc_events`: append-only catalog QC status changes for audit and review.
- `exports`: records for exported configs tied to creatures, keyed independently from the user-facing `export_dir`.
- `results`: optional per-seed records when indexing includes results.
- `specimens`: strict canonical specimen rows for replayable and warehouse-derived analysis.
- `ingest_state`: incremental ingestion cursor by source file (`offset`, `size`, `mtime`).

## Migration history

Migrations are explicit functions in `Sources/LeniaCLI/IndexCommand.swift`, `migrate1to2` through `migrate14to15`.

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

`v5 -> v6`:

- adds `velocity_x`, `velocity_y` and `heading_rad` to `creatures`.

`v6 -> v14`:

- adds strict specimen tables and contracts,
- adds runtime family and capability projections,
- normalizes replay naming,
- adds `initial_condition_json` and canonical `creatures.canonical_specimen_id`,
- requires every canonical creature row to resolve to one strict specimen.

`v14 -> v15`:

- adds catalog QC fields on `creatures`:
  - `catalog_status` (`active`, `protected`, `quarantine`, `rejected`),
  - `quality_flags_json`.
- adds `creature_qc_events` for reversible curation audit trails.
- normal browse and warehouse ingest surfaces default to `active` plus `protected`.

## How the indexer writes

Primary source: `Sources/LeniaCLI/IndexCommand.swift`.

- Ingestion is incremental per source file via `ingest_state` and resets when a file is rewritten in place.
- Each ingest pass runs in an explicit SQLite transaction (`BEGIN IMMEDIATE`).
- Rows are upserted by primary key, so re-indexing the same artifacts is idempotent.
- Ingest paths: run metadata into `runs`, campaign linkage into run-scoped `campaigns`, library index entries into `creatures`, optional results into `results`, and activity summaries that update `morphometrics_json` for matching `run_id + init_seed (+ campaign_id)` rows.
- Morphometrics are computed by `Morphometrics.from(...)` from `metrics_json`, enriched by activity summaries from `overall/activity.jsonl` or `campaigns/*/activity.jsonl` when present, and stored with `morphometrics_method = "lenia-swarm:morphometrics"`, `morphometrics_version = 1`. Without activity summaries the activity-derived fields stay `null`. Field definitions are in [Morphology and morphometrics](../universe/Morphology.md).
- Taxonomy columns are written as `NULL` on insert and left untouched on re-index, so assignments made by `analyze taxonomy` survive.
- Canonical browse and warehouse flows require `creatures.canonical_specimen_id` to resolve every creature row to a strict specimen row.

Fail-loud behavior:

- schema versions newer than the binary supports cause an immediate error,
- invalid UTF-8 or malformed JSON lines fail ingest for the active path,
- `LeniaCLI index sanity` checks required tables, the exact schema version, and per-run completeness (missing taxonomy, provenance, morphometrics and trait labels).

## Static publish

`LeniaCLI publish compendium` reads the indexed database and emits a manifest-backed site release under `site/dossiers/lenia-swarm/compendium/data/`.

- Creature detail payloads come from the indexed compendium row, not from atlas summaries.
- Per-creature replay configs are computed from the indexed genotype, phenotype, sweep overrides, and the run's recorded search config.
- Stage media can be materialized during publish: `poster.png`, `field.png`, `delta.png`, `neighbor.png`, `kernel.png`, and optionally `replay.json` plus `frames.bin`.
- Published detail and index payloads may carry `media` and `telemetry` objects when stage media is rendered.
- Publish fails loudly if the run snapshots needed for replay configs are missing.

## How Studio reads it

LeniaStudio views consume indexed creature rows and metadata; CLI indexing remains the writer of record. Studio depends on:

- the exact schema version the CLI expects,
- the core tables (`compendium_meta`, `runs`, `campaigns`, `creatures`, `exports`, `results`),
- stable column names for taxonomy and morphometrics fields.

Null taxonomy fields are valid data, meaning taxonomy has not been assigned yet, and must not be treated as ingest corruption. Derived fields carry method and version tags so UI logic can branch on them explicitly.

When changing compendium-facing columns:

1. update the schema and its migration,
2. update CLI validations,
3. update Studio readers and views,
4. update this page.

## ADR-002: exact schema version enforcement

Status: accepted.

Read commands and UI surfaces depend on fixed table and column layouts, and a silent compatibility fallback risks incorrect analysis. So the compendium uses explicit schema versioning with exact-match enforcement for every command that reads structured compendium data.

- Failing loudly prevents silent misreads.
- Migration steps make evolution explicit and reviewable.
- A version-locked schema makes deterministic reproduction easier.

Consequences: schema bumps require migration code and doc updates, older databases must be migrated before some commands run, and older binaries reject newer databases instead of reading them partially.
