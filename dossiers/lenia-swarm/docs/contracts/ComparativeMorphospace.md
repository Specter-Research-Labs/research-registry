# Comparative Morphospace Warehouse

## Purpose

The warehouse compares generated and observed forms without forcing every system into Lenia-native descriptors.

The comparison layer is:

- `morphospace_sources`: dataset or generator provenance.
- `specimens`: one observed or generated form, kept as the shared specimen registry.
- `observations`: one measured state of a specimen in a context.
- `feature_spaces`: a named coordinate system with an explicit sparse or dense storage mode.
- `feature_axes`: ordered axes inside a feature space.
- `sparse_feature_values`: physical long-form coordinates for source-native sparse spaces.
- `feature_values`: a logical row projection over sparse rows and active dense vectors.
- `source_receipts`: one content-addressed receipt per imported database or packet.
- `specimen_descriptors`: terminal and trajectory descriptors stored once, outside provenance.
- `feature_calibrations`: immutable normalization parameters and their balanced reference query.
- `specimen_feature_vectors`: the sole physical coordinates for calibrated fixed-axis spaces.

Warehouse schema v10 does not mirror source SQLite rows or duplicate fixed-axis coordinates. It keeps the full source hash and schema plus classified source tables, projected row counts, membership normalization, and nonfinite-coordinate quarantine in a receipt. Descriptor-derived axes, anatomical states, feature spaces, and topology are versioned products: the v8-to-v10 migration omits them, records explicit invalidations, and regenerates only specimens carrying the exact torus-aware v2 descriptor contract. Legacy v1 descriptors remain provenance; migration never relabels them as v2.

Migration is side by side. `lenia-swarm-analysis morphospace migrate-warehouse --source <v8> --destination <v10>` rejects a nonempty WAL on the source or any same-directory hardlink alias, opens the source read-only, projects specimens in bounded keyset batches, builds and verifies a temporary v10 database, rechecks source file identity and WAL state, and publishes the destination without clobbering an existing path. Unknown source tables or columns fail closed. Nonfinite source-native coordinates become `NULL`, deactivate calibration metadata, and invalidate their legacy feature space instead of entering an active metric. The writer refuses to open older schemas in place.

Migration recognizes compendium lineage explicitly and normalizes its mixed aggregate and run-scoped memberships into the canonical aggregate `compendium` study. Legacy study and artifact rows remain as provenance, their active memberships are retired, every normalized specimen receives one canonical membership, and unrelated cohort memberships remain unchanged. Regeneration uses `specimens.study_id` as the sole observation owner, so an unrelated membership cannot duplicate a feature vector. Default aggregate refresh uses the same stable study identity. A run-scoped deployment requires a separate warehouse seeded with every raw run membership, followed by one global calibration and derived-layer rebuild before incremental refresh begins.

Run `regenerate-derived` only after the required v2 descriptors are present. Full regeneration clears and exactly rebuilds derived axes, status, anatomy, terminal and common-morphology observations, dense vectors, and calibrations in one transaction. Dense spaces must have zero physical sparse values, one active frozen calibration, exact observation coverage, contiguous axes, finite arrays, and matching vector lengths. Invalid or building spaces are absent from the logical value projection. Regeneration also fails on count drift, duplicate observations, dangling references, incomplete anatomy, missing required external files, or an unbalanced calibration. Its readiness report distinguishes the structural warehouse gate from native-v2 and full-analysis gates; deleting an invalidation does not count as a rebuild.

For a final filename swap, first stop writers and verify that the WAL is absent. Create a no-clobber hardlink to the v8 inode and use that stable path as `--source`; otherwise a receipt that names the active path would point at the replacement after the rename. Migrate and verify the candidate, rebuild pending analyses, stop readers, checkpoint and close the candidate, atomically rename it over the active path, then reopen the active path read-only and recheck schema, receipt, counts, and inode. Keep the v8 hardlink for rollback.

## Comparison Layers

Use three feature layers.

Common morphology axes compare coarse point distributions across systems: elongation, anisotropy, compactness, polarity, bilateral symmetry, and radial symmetry. `common_morphology_v3_balanced_distribution` freezes robust center and scale from an equal-count, deterministic reference per source so adding a large corpus cannot silently move every existing coordinate. Component, coverage, boundary, and enclosure measurements are excluded because sparse landmarks and dense fingerprints do not define equivalent occupancy topology; those measurements belong in source-specific spaces.

Source-native axes preserve what each system knows best. Lenia keeps dynamics and stability descriptors. EmbryoMaker keeps developmental artifact descriptors. Biological landmark datasets keep GPA coordinates or other morphometric coordinates.

Assay axes record probes of a form under a context: perturbation, replay, resource field, continuation, recovery, or robustness. They attach behavior and robustness measurements to baseline forms without mixing those measurements into the baseline coordinate system.

`export-feature-matrix` emits `comparative_feature_matrix_v2`. JSON/stdout export is deterministically sampled inside DuckDB and hard-limited to 10,000 observations; the packet records the seed, source count, loaded count, and sample-plan hash. Complete archive-scale transfer requires a future streaming columnar export rather than increasing this JSON limit.

## Common Morphology Axes

These axes apply the same distributional formulas to every source. They remain sensitive to what each source samples, so balanced calibration controls scale and corpus size but does not by itself prove biological equivalence.

| Axis | Meaning | Example |
| --- | --- | --- |
| elongation | How stretched a form is along one main direction. | A needlefish-like body is high elongation; a round blob is low elongation. |
| anisotropy | How strongly the form prefers one direction over others. | A cigar shape is anisotropic; a circle is nearly isotropic. |
| compactness | How close sampled points or mass sit to the centroid rather than only on the rim. | A centrally concentrated form is more compact than a sparse peripheral ring. |
| polarity | Whether the form has a meaningful head-tail or inside-out direction. | A tadpole-like body is polar; a uniform disk has little polarity. |
| bilateral symmetry | How closely the point distribution matches reflection across its principal axis. | A left-right body scores higher than an irregular asymmetric form. |
| radial symmetry | How evenly sampled points or mass sit at similar radii from the centroid. | A round or star-like distribution scores higher than a one-sided form. |

## First Mathematical Pass

Start with metric geometry and TDA.

Each feature space declares which value column carries its metric. The initial Dryad fish import uses Euclidean distance over `normalized_value`, a per-PC z-score within the imported corpus.

The first analyses report:

- within-source persistent homology,
- coverage and nearest-neighbor distances across sources in a shared feature space,
- cluster and void stability under bootstrap resampling,
- Mapper or Reeb-style summaries when a scalar lens is meaningful.

This is enough to ask whether Lenia no-food, EmbryoMaker artifacts, and biological fish shapes occupy overlapping regions, separate islands, or differently connected supports.

## Sheaf Layer

Cellular sheaves enter once local charts exist.

Use a cover of each morphospace, with stalks carrying local feature summaries or local coordinate charts. Restriction maps compare overlapping neighborhoods. A successful gluing says local descriptions are compatible. A gluing failure is evidence that two systems look locally similar but cannot be globally aligned under the chosen descriptors.

Run sheaf analyses after the first TDA pass. TDA describes sampled supports; sheaves describe compatibility of local descriptions over those supports.
