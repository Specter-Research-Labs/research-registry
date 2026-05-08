# Run Lake (Cross-Run DuckDB)

The run lake is the cross-run analysis harness for wonton-soup. It reconciles run artifacts into
DuckDB and exports stable datasets for downstream dashboards and reports.

## Why It Exists

Single-run logs answer local debugging questions. The lake answers cross-run questions:

- how effects vary across providers/backends/interventions
- whether patterns persist across repeated seeds
- how metrics behave against explicitly selected references

## Storage Layout

Lake root resolves via `analysis.lake.db.resolve_lake_paths()` and
`runtime_paths.resolve_artifacts_root()`.

- If no machine-local override is configured:
  - active path: `dossiers/wonton-soup/artifacts/lake/`
  - checkouts under `research-registry-workspaces/` resolve this to the sibling main
    `research-registry/dossiers/wonton-soup/artifacts/lake/`
- If `SPCTR_LOCAL_ARTIFACT_ROOT` is set:
  - active path: `$SPCTR_LOCAL_ARTIFACT_ROOT/wonton-soup/artifacts/lake/`
- If `SPECTER_ARTIFACT_ROOT` is set:
  - active local staging path: `$SPECTER_RUNTIME_ROOT/wonton-soup/artifacts/lake/` when `SPECTER_RUNTIME_ROOT` is set, otherwise `tmp/runtime-artifacts/wonton-soup/artifacts/lake/`
  - remote target root: `$SPECTER_ARTIFACT_ROOT/wonton-soup/artifacts/lake/`

Inside active root:

- `lake.duckdb`
- `exports/`
- `jobs/`

## Stable IDs

Lake keys are deterministic:

- `root_id`: hash of resolved log-root path
- `run_key`: hash of resolved physical `run_dir`
- `rel_run_dir`: canonicalized against the shallowest enclosing known log root

This lets parent and child `--logs-dir` reconciles point at the same physical run without
double-indexing it in `runs` and downstream fact tables.

## Canonical Workflows

### Daily Incremental Update

```
uv run python wonton.py postprocess
uv run python wonton.py lake reconcile
```

Use when adding fresh runs locally.

### Backfill / Repair Missing Metrics

```
uv run python wonton.py postprocess
uv run python wonton.py lake reconcile
```

Use when old runs are missing postprocess-heavy fields.

### Paper Analysis Workflow

```
LAKE_DB_PATH=/path/to/shared/lake.duckdb \
uv run python dossiers/wonton-soup/paper/build_figures.py \
  --out-dir dossiers/wonton-soup/paper/artifacts
```

Use when rebuilding the paper figures from the shared runtime lake. `build_figures.py`
resolves `LAKE_DB_PATH` first, then falls back to the same shared-lake default used by the
marimo notebook.

Lake jobs remain useful as optional convenience slices when you want a narrow materialized cohort,
but they are not the paper's primary evidence surface.

There is no generic `lake export --format specter-viz` operator path anymore. Use explicit
lake jobs for optional snapshots, and `lake export-parquet` only for the site dashboard release.

### Site Dashboard Release (Hybrid Publish Path)

```
uv run python wonton.py lake export-parquet \
  --config dossiers/wonton-soup/analysis/lake/presets/72_site_dashboard_superset_v1.json
```

Use when publishing a reproducible compiled dashboard cohort to `site/dashboards/wonton-soup/data`.
Intentionally hybrid: release materialization is human-triggered, while CI validates and
publishes static site assets.

### Surface Preservation Path

Local runs write into the canonical local lake. `spctr surface sync` checkpoints
the raw logs/artifacts and promotes the current lake snapshot to the server.

```
spctr surface status wonton-lake
spctr surface sync wonton-lake
```

Use after local experiments to cold-store logs, non-lake artifacts, and the
current `lake.duckdb` snapshot.

On the server, the systemd timer runs:

```
spctr surface refresh wonton-lake --site-data-root /srv/www/site/data/wonton-soup
```

That refresh runs the native Wonton postprocess/reconcile path against the
server-visible durable roots and can rebuild `lake.duckdb` plus the dashboard
parquet export from the preserved raw roots.

## What Reconcile Extracts

High-level extracted surfaces:

- run registry and file registry
- theorem/intervention summaries from `summary.json.gz`
- theorem artifact index
- graph node/edge fact tables
- MCTS trace summaries
- basin tables from basin-only or summary-backed runs
- optional postprocess outputs
- goal-outcome aggregates
- optional reference-scored K outputs

Primary implementation modules:

- `analysis/lake/db.py`
- `analysis/lake/reconcile.py`
- `analysis/lake/extract_basin.py`

## Determinism and Repro Guarantees

- DB connections enforce single-thread mode for deterministic exports.
- Exports use explicit ordering and deterministic JSON encoding.
- Reference populations must be explicit for leakage-safe K scoring.

Reference-selection guardrail ADR:

- [ADR: Explicit Reference Selection for Lake Jobs](docs/decisions/adr-lake-reference-selection.md)

## Common Failure Modes

### Reconcile misses expected runs

Checks:

- confirm `--logs-dir` points at intended run root
- confirm runs have `run_status.json`
- check for partial/failed runs excluded by downstream filters

### Export output looks stale

Checks:

- rerun `postprocess` then `reconcile`
- confirm `lake.duckdb` under active artifact root is the one being queried

### Dashboard export aborts on selected runs

Checks:

- confirm the selected runs have `summary.json(.gz)` at the run root
- if the error says `basin-only run`, keep that run in the lake but exclude it from dashboard jobs
- do not rely on implicit skipping; mixed selections now fail loudly so site cohorts cannot shrink silently

### Durability drift persists

Checks:

- run `spctr surface status wonton-lake`
- inspect log/artifact roots from `runtime_paths`
- rerun `spctr surface sync wonton-lake` after resolving root mismatch

## Job-Based Materialization

For explicit dataset jobs, reference selection, and manifest provenance:

- [Lake Jobs (Materialized Datasets)](docs/ops/lake-jobs.md)
- [Paper Freeze Runbook](docs/ops/paper-freeze.md)
