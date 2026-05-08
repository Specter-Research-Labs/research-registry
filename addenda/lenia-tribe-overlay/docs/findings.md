# Lenia TRIBE Overlay: Findings (Incubation)

Status as of 2026-05-04. The addendum is staged: pipeline is wired end-to-end
through correlation, sanity gate passes, but no real (non-fake) scoring batch
with warehouse-linked specimens has been run yet.

## What was built

- TRIBE v2 sanity gate (`lenia-tribe-sanity`). Passes on 6 OOD probes
  (variance > 1e-4 floor) for `facebook/tribev2`. Hard-errors on variance
  collapse with a diagnostic, no fallback path.
- ROI bundle on `fsaverage5` via Destrieux atlas labels: `sts`,
  `lateral_ot`, `v1_proxy`. Masks are anatomical proxies, not functional.
- ROI probe (`lenia-tribe-roi-probe`) caches per-vertex predictions for
  the OOD probe set under `.artifacts/predictions/` for control-row reuse.
- Corpus loader resamples arbitrary-length MP4s to TRIBE's 32-frame, 8-fps
  probe window via even-spaced linear sampling and PIL bilinear resize.
- Scoring CLI (`lenia-tribe-score`) accepts either `--corpus` (ad-hoc)
  or `--manifest` (warehouse-linkable). Manifest mode records `specimen_id`
  per row; corpus mode records `null` and is skipped by the overlay.
- Overlay CLI (`lenia-tribe-overlay`) joins a score report against the
  lenia-swarm `morphospace.duckdb` warehouse on `specimen_id`, fetches the
  16-axis `lenia_terminal_v1` descriptor per specimen, and emits one row
  per linked specimen with ROI scores plus descriptor coordinates.
- Correlation CLI (`lenia-tribe-correlate`) computes Pearson r for every
  (ROI, axis) pair, prints a matrix, and tags each ROI as REDUNDANT (any
  abs(r) >= threshold, default 0.85) or candidate-new.

## Framing pivot

First probe round used a synthetic point-light walker as a positive
bio-motion control. STS engagement went the wrong direction. Instead of
chasing a clean control (Vanrie & Verfaillie etc.), we rescoped: ROI
engagement is a relative score over Lenia creatures.

The question we keep is whether the TRIBE score is a duplicate of one of
the 16 `lenia_terminal_v1` axes or actually new. High correlation with an
existing axis means drop it. Low correlation with all 16 means keep it.
The score is not a "lifelikeness" measurement.

## Smoke run (fake client)

End-to-end pipeline verified through correlation: `lenia-tribe-score --fake`
on a 6-entry manifest, `lenia-tribe-overlay` against the real warehouse, then
`lenia-tribe-correlate` on the resulting overlay. Five rows linked, 16 axes
per row, 48-cell correlation matrix produced and verdict line emitted per
ROI. Numbers are not interpretable (fake client emits class-conditioned
constants plus tiny noise; n=5 is far below what would stabilize r).

## What blocks the first real comparative analysis

The lenia-swarm warehouse and the `renders/` MP4 tree are decoupled:
- 514 specimens have `lenia_terminal_v1` features and an `export_dir` of
  JSON manifests (`base.json`, `meta.json`, `search.json`); no MP4 alongside.
- MP4s in `renders/` are keyed on QD-cell labels and scene names, not
  specimen_ids. There is no automated linkage.

To produce a real warehouse-linked scoring batch we need to drive the
lenia-swarm replay and media pipelines from a curated specimen list:

1. Write an `index.jsonl` enumerating chosen `specimen_id`s and their
   `export_dir`s (read straight from `morphospace.duckdb`).
2. Run `swift run lenia-cli replay --input <index.jsonl> ...` to materialize
   replay-capable run dirs per specimen.
3. Run `swift run lenia-cli media --input <replay-dir> ...` to render MP4s
   labelled per specimen.
4. Build a manifest mapping `{name, mp4, specimen_id}` and feed it to
   `lenia-tribe-score --manifest`.

Until that pipeline is driven, the "TRIBE-engagement vs descriptor" plot is
not interpretable.

## Open questions for the first real batch

- How many specimens to render. ~30-50 covers the warehouse's family
  diversity without taking days on CPU TRIBE inference.
- Replay budget. TRIBE wants a 4-second probe window (32 frames at 8 fps).
  If `replay` produces shorter native trajectories we have to either pad or
  reject; the corpus loader already hard-errors on under-length sources.
- Whether to mix scene composites with single-creature renders.
  Single-creature is cleaner for the warehouse join (one specimen per MP4);
  composites are interesting but conflate ROI signals across specimens.

## Limitations carried forward

- TRIBE predicts fMRI, not perception; predicted activation is evidence of
  model-internal engagement, not conscious perception.
- Single observer: TRIBE averages 720 subjects into one mapping.
- OOD substrate: Lenia is far from TRIBE's training distribution. The
  sanity gate is necessary but not sufficient.
- ROI masks are anatomical (Destrieux), not functional. Small-effect
  contrasts within-ROI are not interpretable at this resolution.
- License: CC BY-NC; no commercial surface.
