# Species Knobs for Glider Search

Flow Lenia system, not a classical Lenia implementation. When we say "Orbium-like" below, we mean "a constrained single-kernel Flow Lenia family chosen to stay visually and structurally close to classical Orbium-style gliders", not an exact recreation of Chakazul's preset browser.

## Why this distinction matters

- Classical Lenia gliders like `O2 Orbium unicaudatus` are curated organisms inside a narrow rule family with fixed update semantics and a fixed kernel/growth family.
- This repo searches Flow Lenia, which changes the update rule from additive Lenia to flow plus reintegration. That is a different universe, even when some knob names overlap.
- Broad random sweeps over Flow Lenia rule space will happily find movers, translators, and distributed field patterns that are not canonical gliders.

The practical consequence is simple: if the goal is "find something like Orbium", we must freeze almost all rule-defining knobs and search mostly over initial conditions.

## What counts as species-defining in this repo

These knobs change the governing rule family or body-plan manifold. Do not randomize them when trying to recreate a known creature class.

| Knob group | Repo fields | What it tends to change |
| --- | --- | --- |
| Update family | `profile`, `implementation.mode`, `flow.dt`, `flow.n`, `flow.theta_A`, `reintegration.dd`, `reintegration.sigma`, `reintegration.border` | Transport physics, stability bands, tempo, whether a mover exists at all |
| Channel topology | `channels`, `connectivity` | Number of interacting fields and number of kernels; often changes body plan qualitatively |
| Kernel geometry | `params.r`, `params.b`, `params.w`, `params.a` | Ring placement, segmentation, appendage count, shell thickness, internal banding |
| Growth law | `params.m`, `params.s`, `params.h` | Preferred activation, sharpness, aggressiveness, persistence, locomotion regime |
| Absolute scale | `params.R` | Creature scale, interaction radius, motion tempo, stability window |
| Local rule heterogeneity | `parameter_embedding.*` | Multispecies or locally mixed rules; coherent single-species morphology is no longer guaranteed |
| Environmental scaffolding | `environment.*`, `walls.*`, `food.*`, `chemotaxis.*` | Obstacle-following, ecology-scale patterning, field-wide motifs rather than isolated solitons |
| Rule mutation operators | `beam_mutation.*`, `interventions.*` | In-run rule drift and hybridization, which breaks species reconstruction |

## What is usually safe to vary first

These knobs explore individuals within a fixed rule family instead of redefining the family.

| Safer search knob | Repo fields | Typical use |
| --- | --- | --- |
| Initial-condition seed | `init.seed` via `seed_start` and `init_seed_offset` | Primary search knob for fixed-rule glider hunting |
| Patch randomness | `init.a_uniform` | Vary the realized starting mass while keeping the same rule |
| Run length and observation | `run.steps`, search `warmup_steps`, `record_interval` | Reveal longer periods or translational recurrence without changing the creature |
| Very small local rule nudges | narrow curated changes in `R`, then `m/s`, then `h` | Explore nearby members of the same hand-chosen family after a hit exists |

For this repository, the correct order is:

1. Freeze the rule family.
2. Sweep seeds.
3. Only after finding a good mover, do tiny local nudges in `R`.
4. Then consider tiny `m/s` shifts.
5. Touch `b/w/a/r` only if you intentionally want a different species family.

## What each rule knob tends to do

### `R`

- Primary scale knob.
- Larger `R` usually makes a creature larger and often slower.
- Smaller `R` usually makes motion tighter and can destabilize a pattern if internal structures collapse.

### `m`

- Growth-center knob.
- Moves the preferred activation level up or down.
- Small changes can flip a rule from inert to active, or from smooth translation to pulsing or fragmentation.

### `s`

- Growth-width knob.
- Smaller `s` sharpens selection and can create crisp but fragile movers.
- Larger `s` broadens response and often yields blurrier, more robust but less characterful structures.

### `h`

- Kernel contribution strength.
- Raising `h` usually makes the rule more forceful; too much can inflate or destabilize a pattern.
- Lowering `h` can quiet a rule into near-static behavior.

### `r`

- Relative kernel-radius knob.
- Changes where the kernel senses structure relative to `R`.
- In practice this often changes whether the body forms one lobe, multiple lobes, or extended arms.

### `a`

- Ring-center placement.
- Moves the locations of the Gaussian kernel bands.
- This is highly species-defining because it changes which spatial offsets are reinforced.

### `w`

- Ring-width knob.
- Narrower widths make crisper, more selective bands.
- Wider widths make blurrier, more blended sensing.

### `b`

- Ring-amplitude knob.
- Controls which kernel lobes matter and by how much.
- In this repo's random sampler, `b` is sampled independently for three lobes, so broad random search here quickly stops being "unimodal Orbium-like" and becomes a different kernel family.

## Why parameter embedding and cross-map search are wrong for Orbium-like reconstruction

- `parameter_embedding.enabled` turns the local rule into a spatially varying field of parameters. That is useful for multispecies ecology, not for recreating a single canonical glider family.
- `environment.type = "cross_map"` adds structured obstacles/passages. That is useful for navigation and mover discovery, but it promotes repeated field motifs and distributed patterns.
- `beam_mutation` and in-run interventions explicitly mutate the rule during the simulation. That is the opposite of fixed-species reconstruction.

If the target is "something like the Chakazul glider", those features must stay off.

## Current repo limitation that affects glider search

`params.mode = "random"` samples `b`, `w`, and `a` independently across all three stored lobes. That means random mode cannot express a clean "single dominant lobe plus two suppressed lobes" family except by luck.

That is why the glider search now uses explicit fixed-rule configs in `configs/orbium_like_*.json` and searches seeds, not broad random rules.

## Recommended glider-search policy

Use:

- `configs/glider_sweeps.json`
- `configs/search_orbium_glider.json`
- one of the explicit single-kernel configs in `configs/orbium_like_*.json` or the explicit seed-search families in `configs/glider_family_*.json`

Command:

```bash
./dossiers/lenia-swarm/ops/sweep.sh \
  --manifest dossiers/lenia-swarm/configs/glider_sweeps.json \
  --output dossiers/lenia-swarm/artifacts/orbium-like-sweep \
  --target-creatures 32
```

Interpretation:

- `orbium_like_classic_1c_128.json` is the closest classical anchor in this repo.
- `orbium_like_relaxed_1c_128.json` broadens the classical growth width slightly because Flow Lenia usually needs a wider basin than classical additive Lenia.
- `glider_family_luminous_spiral_4134_1c_128.json` is a local seed-search anchor copied from a real no-embedding compact mover hit already found in this corpus.
- The manifest mixes two classical anchors with one local-hit family because Flow Lenia is not classical Lenia, so the reliable workflow is "anchor near the classical family, then exploit real fixed-rule hits that survive without parameter embedding."

## Literature notes

These references do help decide which knobs not to touch, but only if read with the model boundary in mind.

- Chakazul's JavaScript demo and preset file show that the famous gliders are curated presets inside a narrow classical Lenia family, not the output of a broad random search.
- The original Lenia paper argues that lifeforms occupy structured regions of parameter space, which supports freezing a family and searching locally rather than treating all parameters as free.
- "Lenia and Expanded Universe" is directly relevant because it treats multiple kernels and multiple channels as an expanded universe, not a small perturbation. That means those are family-defining knobs.
- Flow-Lenia is directly relevant because it says localized update-rule parameters define creature properties and can be mixed locally. That is exactly why parameter embedding is not a harmless local search knob when the goal is a single species.
- The step-size paper is directly relevant because it shows step size changes stability and qualitative behavior. In this repo, `flow.dt` belongs in the "do not casually randomize" bucket.

## References

- Chakazul demo: <https://chakazul.github.io/Lenia/JavaScript/Lenia.html>
- Chakazul preset library: <https://chakazul.github.io/Lenia/JavaScript/Lenia-LifeForms.js>
- Lenia: Biology of Artificial Life: <https://arxiv.org/abs/1812.05433>
- Lenia and Expanded Universe: <https://direct.mit.edu/isal/article/doi/10.1162/isal_a_00297/98400/Lenia-and-Expanded-Universe>
- Flow-Lenia: Towards open-ended evolution in cellular automata through mass conservation and parameter localization: <https://arxiv.org/abs/2212.07906>
- Step Size is a Consequential Parameter in Continuous Cellular Automata: <https://arxiv.org/abs/2205.12728>
