# Lake

The Wonton lake reconciles run artifacts into DuckDB and exports stable
datasets for reports, dashboards, and release snapshots.

Single-run logs answer local debugging questions. The lake answers cross-run
questions: provider effects, intervention effects, repeated-seed stability, and
reference-scored efficiency.

## Storage

Lake paths resolve through `analysis.lake.db.resolve_lake_paths()` and
`runtime_paths.resolve_artifacts_root()`.

- default: `dossiers/wonton-soup/artifacts/lake/`
- `SPCTR_LOCAL_ARTIFACT_ROOT`: `$SPCTR_LOCAL_ARTIFACT_ROOT/wonton-soup/artifacts/lake/`
- `SPECTER_ARTIFACT_ROOT`: staged under `SPECTER_RUNTIME_ROOT` or
  `tmp/runtime-artifacts/wonton-soup/artifacts/lake/`, then synced to
  `$SPECTER_ARTIFACT_ROOT/wonton-soup/artifacts/lake/`

Inside the root:

- `lake.duckdb`
- `exports/`
- `jobs/`

## Stable IDs

- `root_id`: hash of resolved log-root path
- `run_key`: hash of resolved physical run directory
- `rel_run_dir`: run path canonicalized against the shallowest known log root

These keys keep parent and child `--logs-dir` reconciles from double-indexing
the same physical run.

## Standard Update

```bash
uv run python wonton.py postprocess
uv run python wonton.py lake reconcile
```

Use the same sequence for fresh runs and for backfilling old runs after
postprocess logic changes.

## Paper Figures

The paper uses the shared runtime lake as the dataset.

```bash
LAKE_DB_PATH=/path/to/shared/lake.duckdb \
uv run python dossiers/wonton-soup/paper/build_figures.py \
  --out-dir dossiers/wonton-soup/paper/artifacts
```

`build_figures.py` checks `LAKE_DB_PATH` first, then falls back to the shared
lake default used by the notebook.

## Site Dashboard

```bash
uv run python wonton.py lake export-parquet \
  --config dossiers/wonton-soup/analysis/lake/presets/72_site_dashboard_superset_v1.json
```

This writes a versioned release under
`site/dashboards/wonton-soup/data/releases/<release_id>/` and promotes it to the
active dashboard manifest. Use `--no-promote` to stage without switching active
site data.

## Jobs

Lake jobs are optional materialized slices. They are not the paper dataset.

```bash
uv run python wonton.py lake job presets

uv run python wonton.py lake job run \
  --config dossiers/wonton-soup/analysis/lake/presets/01_runs_overview.json \
  --logs-dir logs
```

Job configs use `schema_version: 2` and contain:

- `selection`: filters on `runs`
- `datasets`: SQL queries emitted as JSONL or Parquet
- `reference`: optional explicit reference model for K scoring

If a job builds a reference from goal outcomes, `reference.selection` must be a
non-empty object. The guardrail is recorded in
[ADR: Explicit Reference Selection for Lake Jobs](../decisions/adr-lake-reference-selection.md).

## Preservation

```bash
spctr surface status wonton-lake
spctr surface sync wonton-lake
```

Server refresh:

```bash
spctr surface refresh wonton-lake --site-data-root /srv/www/site/data/wonton-soup
```

This refreshes raw roots, rebuilds `lake.duckdb`, and can regenerate dashboard
Parquet from preserved logs.

## Failure Checks

- Missing runs: confirm `--logs-dir`, `run_status.json`, and completed status.
- Stale export: rerun `postprocess`, then `lake reconcile`, against the intended
  `lake.duckdb`.
- Dashboard abort: selected runs must have `summary.json` or `summary.json.gz`;
  basin-only runs stay in the lake but must be excluded from dashboard cohorts.
- Durability drift: run `spctr surface status wonton-lake`, fix roots, then
  sync again.
