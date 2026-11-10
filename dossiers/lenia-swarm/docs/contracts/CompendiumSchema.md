---
summary: "The Lenia compendium: its SQLite schema, how the indexer writes it, how Studio and the CLI read it, and why readers require an exact version."
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

The current schema version is `15`, set by `compendiumSchemaVersion` in `Sources/LeniaArchive/CompendiumSchemaVersion.swift`.

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

## No migrations

The compendium is derived data. `LeniaCLI index` creates the current schema in a new database and refuses a database at any other version; rebuild such a database from its run directories with `--rebuild`. A schema change bumps `compendiumSchemaVersion` and edits `createSchema()` in `Sources/LeniaCLI/IndexCommand.swift`; it does not add migration code.

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

- a schema version other than the current one causes an immediate error,
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

1. update the schema and bump its version,
2. update CLI validations,
3. update Studio readers and views,
4. update this page.

## ADR-002: exact schema version enforcement

Status: accepted.

Read commands and UI surfaces depend on fixed table and column layouts, and a silent compatibility fallback risks incorrect analysis. So the compendium uses explicit schema versioning with exact-match enforcement for every command that reads structured compendium data.

- Failing loudly prevents silent misreads.
- Rebuilding from run directories keeps every database on one reviewed schema.
- A version-locked schema makes deterministic reproduction easier.

Consequences: schema bumps require doc updates and a rebuild of existing databases, and binaries reject databases at any other version instead of reading them partially.
