# Cortical-Engagement Scoring Contract

This contract pins the experimental commitments of A-013, the lenia-swarm
TRIBE overlay addendum. Changes to it require an addendum-internal review.

## Frame
TRIBE-engagement is a relative score over Lenia creatures. We do not claim
absolute neural realism. The contract is about reproducibility of the
scoring procedure, not about cortex-as-ground-truth.

## Inputs
- A TRIBE v2 checkpoint identified by HuggingFace revision hash.
- A stimulus manifest. Each entry is content-addressed and carries a
  class label drawn from `{lenia, biomotion_positive, scrambled, noise,
  static, rigid_motion, grating}` plus stimulus-specific metadata.
- For lenia-class stimuli, a reference into the lenia-swarm compendium
  giving the source trajectory and the morphospace coordinates already
  computed there. We do not recompute morphospace features inside this
  addendum; we consume them.

## Outputs
For every (checkpoint, stimulus) pair:
- A vector of predicted per-voxel activations on `fsaverage5` (20484
  vertices, [left|right] hemispheres stacked per TRIBE's convention).
- A reduced vector of per-ROI mean activations for the registered ROI
  bundle (initial set: `sts`, `lateral_ot`, `v1_proxy`, defined via
  Destrieux atlas labels in `lenia_tribe_overlay.rois`).
- A provenance record (TRIBE revision, codebase commit, torch and CUDA
  versions, machine identifier).

For lenia-class stimuli with a manifest-supplied `specimen_id`, an overlay
report joins the ROI scores to the `lenia_terminal_v1` feature space in the
lenia-swarm morphospace warehouse and emits one row per linked specimen with
ROI scores and the 16 lenia descriptor axes (`normalized_value` per
`feature_values.axis_id`). Specimens whose `specimen_id` is not present in the
warehouse cause the overlay to fail loudly; the warehouse is the source of
truth for axis values.

Outputs are written under `$SPECTER_ARTIFACT_ROOT/lenia-tribe-overlay/` if
set, otherwise under `addenda/lenia-tribe-overlay/.artifacts/`.

## Redundancy verdict
For lenia-class stimuli with linked `specimen_id`s, `lenia-tribe-correlate`
computes Pearson r between every ROI score and every `lenia_terminal_v1`
axis. An ROI is tagged REDUNDANT if its top abs(r) crosses a threshold
(default 0.85), candidate-new otherwise. The threshold and the n_specimens
floor (currently 4) are part of the contract because they decide the
verdict; changing either requires reissuing prior verdicts.

## Sanity gate
A run of the experiment is invalid unless the sanity gate, defined in
`lenia_tribe_overlay.sanity`, has been executed against the same TRIBE
checkpoint within the last seven days and emitted a `pass` record with
the same checkpoint hash. The gate confirms only one thing:

1. Across-stimulus variance over a small OOD probe set exceeds
   `VARIANCE_FLOOR = 1e-4`. TRIBE must produce visibly differentiated
   whole-cortex predictions for visually distinct probes.

If (1) fails, the gate hard-errors with a diagnostic. Region-specific
claims (e.g. STS responds more to a creature than to noise) are not part
of the gate, because the bio-motion ROIs are ~1-2% of cortex and a
localized signal can be drowned out in any whole-cortex aggregate. Those
claims belong to the experiment proper.

## Determinism
- Stimulus tensors are precomputed and stored content-addressed; the
  same stimulus produces the same input tensor every run.
- TRIBE inference is run with deterministic kernels where supported.
  Where it is not, the non-determinism is recorded and the experiment
  reports the standard deviation across N replicate runs.

## What this contract does not promise
- We do not claim the predicted activations correspond to any particular
  individual human's response.
- We do not claim that elevated predicted activation in any ROI for a
  Lenia stimulus implies that humans perceive that stimulus a particular
  way. The model predicts a hemodynamic proxy.
- ROI masks are anatomical (Destrieux), not functional. `sts`,
  `lateral_ot`, and `v1_proxy` are loose proxies for STS, MT/EBA-lateral
  OTC, and V1 respectively; small-effect contrasts are not interpretable
  at this resolution.
- We do not commit to any specific clustering or significance test
  upfront. The analysis layer is allowed to evolve. The contract pins
  what is measured and recorded, not what is concluded.
