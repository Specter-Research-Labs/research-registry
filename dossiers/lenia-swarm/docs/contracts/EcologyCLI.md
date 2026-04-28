# Ecology Export

## Purpose

`LeniaCLI ecology` exports a deterministic parameter-space dataset from `compendium.sqlite` for downstream analysis and visualization.

It does not assign taxonomy or trait labels. It exports available values.

## Command Surface

Required:

- `--db` (`--db-path`): compendium SQLite path.

Optional:

- `--output` (default `outputs/ecology`): artifact directory.
- `--include-unstable`: include unstable creatures.
- `--limit <n>`: cap exported rows.
- `--plot`: write `mu-sigma` scatter PNG.
- `--plot-width`, `--plot-height`: plot dimensions.
- `--pca`: compute PCA(2) on genotype vectors.
- `--pca-max-rows`: cap rows used for PCA.

## Preconditions

The command fails if:

- `compendium_meta` or `creatures` table is missing,
- schema version differs from current `compendiumSchemaVersion`,
- `creatures` table is empty,
- PCA is requested with fewer than 2 usable rows,
- genotype vectors are inconsistent in length.

## Output Artifacts

Files are date-prefixed (`YYYY-MM-DD`):

- `<date>-ecology-embedding.jsonl`: one exported row per creature.
- `<date>-ecology-summary.json`: export metadata and output file paths.
- `<date>-ecology-pca2.jsonl` (optional): PCA coordinates when `--pca` is enabled.
- `<date>-ecology-mu-sigma.png` (optional): scatter plot when `--plot` is enabled.

## Embedding Row Schema

Each JSONL row contains:

- identity: `id`, `runId`, `isStable`, `score`.
- taxonomy passthrough: `taxonomyFamilyId`, `taxonomyGenusId`, `taxonomySpeciesId`.
- genotype summaries:
  - `kernelCount`,
  - `muSigma` (`[mean(m), mean(s)]`),
  - `betaSummary` (`rMean`, `bMean`, `bMax`, `wMean`, `wMax`, `aMean`, `aMax`, `R`),
  - `genotypeVector` (canonicalized flattened kernel vector + `R`).
- metrics subset: `massMean`, `gyration`, `centerVelocity`, `complexityMean`.

## Notes

- Taxonomy fields may be `null` because taxonomy assignment is not yet implemented in indexing.
- Plot rendering is intentionally simple and deterministic (histogram density overlay plus points, no KDE dependency).
