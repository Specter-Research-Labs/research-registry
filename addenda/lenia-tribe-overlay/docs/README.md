# Lenia TRIBE Overlay

## Question
`lenia-swarm` already gives each creature 16 shape-and-motion numbers
(`lenia_terminal_v1`: spread, compactness, boundary complexity, symmetry,
displacement, etc.). This addendum computes a 17th number by a separate
route: feed the video to TRIBE v2 and average the predicted
cortical activation in a few regions.

Is the 17th number redundant with the existing 16-axis descriptor space? If
it correlates near `0.9` with `boundary_complexity` or another axis, drop it.
If it stays decorrelated from all 16 axes, keep it as a new sorting
coordinate.

We do not claim Lenia creatures are alive because the cortex says so, and
the score is not a "lifelikeness" measurement.

## Tool
[TRIBE v2](https://github.com/facebookresearch/tribev2) is a multimodal
transformer (LLaMA 3.2 + V-JEPA2 + Wav2Vec-BERT) trained on >1000 hours
of fMRI from 720 subjects to predict cortical responses to video, audio,
and language. We use only the video pathway; audio and text are stubbed
to silence and empty string. The model emits per-voxel predictions on
`fsaverage5` (20484 vertices, [left|right] hemispheres stacked).

## Pipeline
1. **Sanity gate.** Push a small set of OOD-but-controlled probes through
   TRIBE and confirm whole-cortex predictions vary across them. Hard-error
   on variance collapse.
2. **ROI bundle.** Build named anatomical-proxy masks on `fsaverage5` via
   the Destrieux atlas: an STS region, a lateral-occipitotemporal region
   (proxy for MT / EBA), and a V1 region as control.
3. **Lenia corpus loading.** Existing lenia-swarm MP4 renders are
   re-timed to TRIBE's 32-frame, 8-fps, 4-second probe window — the brain
   does not know what one Lenia timestep means in seconds, so the entire
   source clip is compressed into the probe window.
4. **Inference.** Forward pass per stimulus through TRIBE. Per-vertex
   predictions persist to `.artifacts/predictions/`. ROI summaries
   persist alongside under `.artifacts/lenia-scores/`.
5. **Warehouse overlay.** When a scoring run supplies a manifest with
   `specimen_id` per Lenia clip, `lenia-tribe-overlay` joins the ROI
   scores against the `lenia_terminal_v1` feature space in the lenia-swarm
   morphospace warehouse and emits one row per linked specimen with ROI
   scores plus the 16 descriptor axes. Manifest entries without
   `specimen_id` are scored and recorded but skipped by the overlay.
6. **Comparative analysis.** `lenia-tribe-correlate` computes Pearson r
   between each ROI score and each of the 16 `lenia_terminal_v1` axes,
   prints the matrix, and tags each ROI as REDUNDANT (any abs(r) >=
   threshold, default 0.85) or candidate-new.

## Determinism and provenance
Every inference run records: TRIBE weight hash, codebase commit, stimulus
manifest derived from content-addressed MP4s, torch and CUDA versions,
seed for any preprocessing randomness. Reports are timestamped under
`.artifacts/`.

## Limits
- TRIBE predicts fMRI, not perception. A predicted activation in any ROI
  is evidence of model-internal engagement, not of conscious perception.
- Single observer. TRIBE averages 720 subjects into a learned mapping;
  individual and cultural differences are absent.
- OOD substrate. Lenia is far from TRIBE's training distribution. The
  sanity gate is necessary but not sufficient guard against garbage.
- ROI masks are anatomical (Destrieux), not functional. `sts`,
  `lateral_ot`, and `v1_proxy` are loose proxies; small-effect contrasts
  at this resolution are not interpretable.
- License. CC BY-NC. No commercial use.
