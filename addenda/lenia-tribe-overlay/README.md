# Lenia TRIBE Overlay (A-013)

Status: experimental. Addendum to `dossiers/lenia-swarm/`.

`lenia-swarm` already gives each creature 16 shape-and-motion numbers
(`lenia_terminal_v1`). This addendum computes a 17th number by a separate
route: render the Lenia run as video, push it through Meta's TRIBE
v2 ([weights](https://huggingface.co/facebook/tribev2),
[code](https://github.com/facebookresearch/tribev2)) to predict per-voxel
fMRI activation on `fsaverage5`, and average that activation inside three
anatomical ROIs (STS, lateral occipitotemporal, V1 as control).

The question is whether that 17th number is redundant with the existing
descriptor space. If a ROI score correlates near `0.9` with
`boundary_complexity` or any other axis, drop it. If it stays decorrelated
from all 16 axes, keep it as a new sorting coordinate. The score is not a
"lifelikeness" measurement.

## Failure Modes
TRIBE was trained on naturalistic video; Lenia is far outside that
distribution. The sanity gate (`lenia-tribe-sanity`) only checks
model-level health: that whole-cortex predictions vary across visually
distinct OOD probes. It hard-errors on variance collapse, no fallback.

ROI masks are anatomical proxies via the Destrieux atlas, not functional ROIs.
Small within-ROI effects are not interpretable.

## License
TRIBE v2 weights are CC BY-NC. This addendum is research and
non-commercial only; `spctr.toml` reflects that.

## Layout
- `lenia_tribe_overlay/` Python source.
- `docs/contracts/BiomotionExperiment.md` formal experimental contract.
- `docs/README.md` design overview.
- `docs/findings.md` incubation status and what blocks the first real
  warehouse-linked batch.
- `tmp/lenia-corpus-batch1/` curated symlinked corpus for the first
  scoring run.

## How to run
```sh
cd addenda/lenia-tribe-overlay
uv sync
uv run lenia-tribe-sanity --device cpu
uv run lenia-tribe-roi-probe --device cpu
uv run lenia-tribe-score --manifest tmp/smoke-manifest.json --device cpu
uv run lenia-tribe-overlay \
  --score-report .artifacts/lenia-scores/<report>.json \
  --warehouse ../../dossiers/lenia-swarm/artifacts/morphospace.duckdb
uv run lenia-tribe-correlate \
  --overlay-report .artifacts/overlays/<overlay>.json
```

The sanity gate must pass before any later stage runs. Reports land under
`.artifacts/`.

## Manifest format
`lenia-tribe-score` accepts either a `--corpus` directory of MP4s for
ad-hoc scoring, or a `--manifest` JSON array for runs that need to be
joined back to the lenia-swarm warehouse:

```json
[
  {"name": "creature-a", "mp4": "renders/a.mp4", "specimen_id": "result:..."},
  {"name": "showcase",   "mp4": "renders/x.mp4", "notes": "no warehouse linkage"}
]
```

`specimen_id` is the only field that connects a scored creature to the
lenia-swarm warehouse. Rows without it are scored and recorded but skipped
by the overlay. `lenia-tribe-overlay` joins on `specimen_id` against the
`lenia_terminal_v1` feature space and emits one row per linked specimen
with ROI scores and 16 descriptor axes. `lenia-tribe-correlate` then
computes a Pearson correlation between each ROI score and each descriptor
axis to answer the redundancy question.
