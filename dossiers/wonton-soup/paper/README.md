# Wonton Soup Paper Draft

Typst manuscript scaffold for the `wonton-soup` paper, built on the shared Specter
paper surface in `research-registry/addenda/typst-field-manual/`.

## Files

- `main.typ`: manuscript skeleton with section structure, placeholder figures, and a
  seeded argument.
- `refs.bib`: initial bibliography seed for the Levin / TAME framing.
- `artifacts/`: local build output (gitignored inside this folder).

## Source Of Truth Dataset

The paper should be analyzed against the shared runtime lake.

This is the same broad surface that the marimo notebook targets. Small lake-job slices may exist as
operator conveniences, but they are not the dataset. The paper figure builder then narrows that lake
to the intended March `p2-paired` lesion cells and March `p4-basin-deep` basin cells.

## Optional Convenience Slices

If a narrower or explicitly materialized cohort is useful for debugging or release prep, these
presets exist:

- tight closeout slice: `dossiers/wonton-soup/analysis/lake/presets/79_wonton_paper_closeout_v1.json`
- broad shared-lake program slice: `dossiers/wonton-soup/analysis/lake/presets/80_wonton_paper_program_v1.json`

They are optional conveniences, not alternate sources of truth.

## Build

From `research-registry/`:

```bash
LAKE_DB_PATH=/path/to/shared/lake.duckdb \
uv run python dossiers/wonton-soup/paper/build_figures.py \
  --out-dir dossiers/wonton-soup/paper/artifacts

typst compile \
  --root . \
  dossiers/wonton-soup/paper/main.typ \
  dossiers/wonton-soup/paper/artifacts/main.pdf \
  --font-path addenda/typst-field-manual/assets/fonts
```

Generated figure assets currently used by `main.typ`:

- `paper/artifacts/fig17-followup-provider-splits.svg`
- `paper/artifacts/fig16-ged-bimodality.svg`
- `paper/artifacts/fig18-followup-basins.svg`

## Current Closeout Tasks

1. Replace the placeholder author block and title if needed.
2. Tighten the remaining claims and exact run counts against the shared runtime lake.
3. Expand the scheduler/controller section from the same dataset if it is promoted into the main story.
4. Refresh the figures whenever the shared lake gains new runs or backfilled analyses.
