# Lake Jobs (Materialized Datasets)

Lake jobs are a thin, explicit way to:

- select a set of runs from the lake registry,
- optionally build or attach a reference model,
- materialize one or more SQL datasets into files (JSONL or Parquet),
- write a manifest capturing selection + reference provenance.

They are intended as the stable bridge from "raw lake tables" to downstream reporting/viz (for
example, `addenda/specter-viz`).

Implementation: `dossiers/wonton-soup/analysis/lake/job.py`.

## Presets

Preset job configs live in `dossiers/wonton-soup/analysis/lake/presets/*.json`.

List them:

```bash
uv run python wonton.py lake job presets
```

Run one:

```bash
uv run python wonton.py lake job run --config dossiers/wonton-soup/analysis/lake/presets/01_runs_overview.json --logs-dir logs
```

Optional paper/debug convenience slice:

```bash
uv run python wonton.py lake job run \
  --config dossiers/wonton-soup/analysis/lake/presets/79_wonton_paper_closeout_v1.json
```

This preset materializes a narrow closeout cohort. It is useful for debugging or release prep,
but it is not the paper's source-of-truth dataset.

Release a compiled site dashboard cohort (quality-gated superset):

```bash
uv run python wonton.py lake export-parquet \
  --config dossiers/wonton-soup/analysis/lake/presets/72_site_dashboard_superset_v1.json \
  --logs-dir logs
```

This command:

- materializes dashboard payloads with an explicit selection preset,
- writes a versioned snapshot under `site/dashboards/wonton-soup/data/releases/<release_id>/`,
- promotes the release into active site data at `site/dashboards/wonton-soup/data/dashboard_manifest.json`.

Use `--no-promote` to stage a release snapshot without switching active site data.

## Job Config Schema (v2)

Job configs are JSON objects with `schema_version: 2`:

```json
{
  "schema_version": 2,
  "name": "runs_overview",
  "selection": {
    "provider": ["reprover", "deepseek"],
    "backend": "lean",
    "mode": ["dev", "research"]
  },
  "reference": null,
  "datasets": [
    {
      "name": "runs",
      "query": "SELECT * FROM runs WHERE run_key IN (SELECT run_key FROM selected_runs)",
      "format": "jsonl"
    }
  ]
}
```

### selection

`selection` filters the `runs` table. Supported keys:

- `root_id` (string)
- `provider`, `backend`, `mode`, `corpus`, `goal_sig_scheme` (string or list of strings)

When you pass `--logs-dir` to `wonton.py lake job run`, the job will set `selection.root_id` to that
directory's `root_id` unless you already provided one.

The selection is applied as an AND across fields.

### datasets

Each dataset is:

- `name` (string, required)
- `query` (SQL string, required)
- `format` (`jsonl` or `parquet`, default `jsonl`)
- `file` (optional base name; no directories)

Jobs create a temporary `selected_runs(run_key)` table that dataset SQL can use.

### reference

`reference` controls reference building and optional K scoring.

Supported patterns:

1) Attach an existing reference by id:
```json
{"ref_id": "abc123", "score_k": true}
```

2) Build a new goal-outcomes reference (from goal_cache aggregates), with an explicit run selection:
```json
{
  "build_outcomes": {"alpha": 1.0, "meta": {"note": "baseline reference"}},
  "selection": {"provider": "reprover", "backend": "lean"},
  "score_k": true
}
```

Important invariant:

- If `reference.build_outcomes` is present, `reference.selection` must be a **non-empty** object.
  Enforced in `analysis.lake.job.load_job_config()` to prevent accidental in-sample leakage.
- Rationale for this guardrail: [ADR: Explicit Reference Selection for Lake Jobs](docs/decisions/adr-lake-reference-selection.md).

If `score_k` is true, `--logs-dir` must be provided so the scorer can locate per-run directories and
read MCTS traces.

## Output Contract

Each job run writes:

- `manifest.json`: resolved selection + resolved reference (including ref id and reference members)
- `job_config.json`: the original config snapshot (schema v2)
- `inputs.json`: the selected run keys
- one file per dataset

Jobs also record a row in the `lake_job_runs` table (for cross-run provenance).

## SQL Convenience: job_context(ref_id)

Jobs create a temporary `job_context(ref_id)` table:

- If a reference is present, it contains a single row with that `ref_id`.
- If no reference is present, the table exists but is empty.

This lets dataset SQL bind deterministically to the job's chosen reference, e.g.:

```sql
SELECT *
FROM k_reference_score
WHERE ref_id IN (SELECT ref_id FROM job_context)
```
