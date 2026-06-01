# Paper

Workflow for rebuilding the Wonton paper figures and PDF.

## Dataset

The shared runtime lake is the dataset. Lake jobs are debug or release slices,
not alternate evidence.

Inputs:

- `LAKE_DB_PATH` or the shared-lake default resolved by `paper/build_figures.py`
- `dossiers/wonton-soup/paper/build_figures.py`
- `dossiers/wonton-soup/paper/main.typ`
- `dossiers/wonton-soup/paper/refs.bib`

Build output goes under `dossiers/wonton-soup/paper/artifacts/`.

## Build Figures

```bash
LAKE_DB_PATH=/path/to/shared/lake.duckdb \
uv run python dossiers/wonton-soup/paper/build_figures.py \
  --out-dir dossiers/wonton-soup/paper/artifacts
```

Expected artifacts:

- `paper/artifacts/fig17-followup-provider-splits.svg`
- `paper/artifacts/fig16-ged-bimodality.svg`
- `paper/artifacts/fig18-followup-basins.svg`

## Compile

```bash
typst compile \
  --root . \
  dossiers/wonton-soup/paper/main.typ \
  dossiers/wonton-soup/paper/artifacts/main.pdf \
  --font-path addenda/typst-field-manual/assets/fonts
```

## Optional Slices

Optional lake presets for debugging and release prep:

- `dossiers/wonton-soup/analysis/lake/presets/79_wonton_paper_closeout_v1.json`
- `dossiers/wonton-soup/analysis/lake/presets/80_wonton_paper_program_v1.json`

They do not replace the shared lake for paper analysis.

## Gates

Before publishing:

1. Claims and run counts match the shared runtime lake.
2. Scheduler/controller claims come from the same dataset as the figures.
3. Figures are refreshed after new runs or backfilled analyses enter the lake.
