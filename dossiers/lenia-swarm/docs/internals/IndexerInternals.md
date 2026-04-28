# Indexer Internals

## Scope

Implementation details for `LeniaCLI index` and compendium ingestion paths.

Primary source: `Sources/LeniaCLI/IndexCommand.swift`.

## Schema Lifecycle

- current schema constant lives in `Sources/LeniaCLI/CompendiumSchema.swift`.
- indexer checks `compendium_meta.schema_version`.
- migrations are explicit (`migrate1to2`, `migrate2to3`, `migrate3to4`, `migrate4to5`).

## Ingestion Model

- ingestion is incremental per source file via `ingest_state` (`offset`, `size`, `mtime`) and resets on in-place rewrites.
- each ingest pass is wrapped in explicit SQLite transactions (`BEGIN IMMEDIATE`).
- rows are inserted with `INSERT OR REPLACE` into canonical tables.

## Major Ingest Paths

- run metadata upsert into `runs`.
- campaign linkage upsert into run-scoped `campaigns`.
- library index ingestion into `creatures`.
- optional results ingestion into `results`.
- activity summary enrichment updates `morphometrics_json` for matching `run_id + init_seed (+ campaign_id)` rows.

## Derived Field Writes

- morphometrics are computed by `Morphometrics.from(...)` and stored with method/version metadata.
- taxonomy columns are currently reserved and written as null by default.

## Fail-Loud Behavior

- newer-than-supported schema versions cause immediate error.
- invalid UTF-8 or malformed JSON lines fail ingest for the active path.
- compendium sanity command enforces required tables and exact schema version.
