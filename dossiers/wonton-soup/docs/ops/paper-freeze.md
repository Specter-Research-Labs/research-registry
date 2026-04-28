# Paper Workflow Runbook

This is the operator path for the current `wonton-soup` paper workflow.

## Decision

The shared runtime lake is the dataset.

Do not treat small lake-job slices as alternate sources of truth. They may exist as optional
convenience surfaces, but the paper should be analyzed against the shared lake.

## Inputs

- lake DB: `LAKE_DB_PATH` or the shared-lake default resolved by `build_figures.py`
- figure builder: `dossiers/wonton-soup/paper/build_figures.py`
- manuscript: `dossiers/wonton-soup/paper/main.typ`

## Steps

### 1. Refresh the contributing lake roots if needed

Run `postprocess` + `lake reconcile` for any root whose runs should feed the shared lake analysis.
Iterate on data collection until the lake contains the evidence the paper needs.

### 2. Build figures directly from the shared lake

`build_figures.py` reads the shared lake and then applies the paper's internal cell filter:
March `p2-paired` for lesion / structural figures, and March `p4-basin-deep` for the basin panel.


```bash
LAKE_DB_PATH=/path/to/shared/lake.duckdb \
uv run python dossiers/wonton-soup/paper/build_figures.py \
  --out-dir dossiers/wonton-soup/paper/artifacts
```

Expected artifacts:

- `paper/artifacts/fig17-followup-provider-splits.svg`
- `paper/artifacts/fig16-ged-bimodality.svg`
- `paper/artifacts/fig18-followup-basins.svg`

### 3. Compile the paper

```bash
typst compile \
  --root . \
  dossiers/wonton-soup/paper/main.typ \
  dossiers/wonton-soup/paper/artifacts/main.pdf \
  --font-path addenda/typst-field-manual/assets/fonts
```

## Optional convenience slices

If a narrow materialized cohort is useful for debugging or release prep, these optional presets exist:

- `dossiers/wonton-soup/analysis/lake/presets/79_wonton_paper_closeout_v1.json`
- `dossiers/wonton-soup/analysis/lake/presets/80_wonton_paper_program_v1.json`

They are convenience slices, not the dataset.
