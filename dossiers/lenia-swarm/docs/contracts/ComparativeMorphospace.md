# Comparative Morphospace Warehouse

## Purpose

The warehouse compares generated and observed forms without forcing every system into Lenia-native descriptors.

The comparison layer is:

- `morphospace_sources`: dataset or generator provenance.
- `specimens`: one observed or generated form, kept as the shared specimen registry.
- `observations`: one measured state of a specimen in a context.
- `feature_spaces`: a named coordinate system with a stated metric policy.
- `feature_axes`: ordered axes inside a feature space.
- `feature_values`: long-form raw and normalized coordinates for observations.

Legacy Lenia tables such as `specimen_axes`, `development_sample_axes`, `anatomical_states`, and `context_trials` remain valid. They are source-specific projections over the same specimen and study registry, and existing exports continue to read them.

## Comparison Layers

Use three feature layers.

Common morphology axes compare visible form across systems: elongation, compactness, anisotropy, component count, boundary complexity, enclosure, coverage, symmetry, and polarity.

Source-native axes preserve what each system knows best. Lenia keeps dynamics and stability descriptors. EmbryoMaker keeps developmental artifact descriptors. Biological landmark datasets keep GPA coordinates or other morphometric coordinates.

Assay axes record probes of a form under a context: perturbation, replay, resource field, continuation, recovery, or robustness. They attach behavior and robustness measurements to baseline forms without mixing those measurements into the baseline coordinate system.

## Common Morphology Axes

These axes should be readable without knowing the generator.

| Axis | Meaning | Example |
| --- | --- | --- |
| elongation | How stretched a form is along one main direction. | A needlefish-like body is high elongation; a round blob is low elongation. |
| compactness | How tightly mass fills its footprint. | A solid disk is compact; a long sparse chain with the same area is less compact. |
| anisotropy | How strongly the form prefers one direction over others. | A cigar shape is anisotropic; a circle is nearly isotropic. |
| component count | How many disconnected pieces the form has. | One continuous organism has count 1; three separated islands have count 3. |
| boundary complexity | How irregular or folded the outer edge is. | A smooth oval has low boundary complexity; a ruffled or branched outline has high boundary complexity. |
| enclosure | Whether the form surrounds an interior space. | A ring, cup, or invaginated pocket has enclosure; a filled oval does not. |
| coverage | How much of the available field the form occupies. | A tiny centered animal has low coverage; a sheet spread across the frame has high coverage. |
| symmetry | How much the form matches itself under reflection or rotation. | A left-right fish silhouette has bilateral symmetry; a star has radial symmetry. |
| polarity | Whether the form has a meaningful head-tail or inside-out direction. | A tadpole-like body is polar; a uniform disk has little polarity. |

## First Mathematical Pass

Start with metric geometry and TDA.

Each feature space declares which value column carries its metric. The initial Dryad fish import uses Euclidean distance over `normalized_value`, a per-PC z-score within the imported corpus.

The first analyses should report:

- within-source persistent homology,
- coverage and nearest-neighbor distances across sources in a shared feature space,
- cluster and void stability under bootstrap resampling,
- Mapper or Reeb-style summaries when a scalar lens is meaningful.

This is enough to ask whether Lenia no-food, EmbryoMaker artifacts, and biological fish shapes occupy overlapping regions, separate islands, or differently connected supports.

## Sheaf Layer

Cellular sheaves become useful once local charts exist.

Use a cover of each morphospace, with stalks carrying local feature summaries or local coordinate charts. Restriction maps compare overlapping neighborhoods. A successful gluing says local descriptions are compatible. A gluing failure is evidence that two systems look locally similar but cannot be globally aligned under the chosen descriptors.

Run sheaf analyses after the first TDA pass. TDA describes sampled supports; sheaves describe compatibility of local descriptions over those supports.
