# Coherent-body pilot and HQ specimen review

The synthesis report's earlier collection orbiter becomes filamentary over a 3,600-step replay. Re-rendering it at 512 pixels improves presentation but does not solve specimen selection. The original developmental cohort also contains lattices and strands, including its most isotropic members.

The replacement is B26ADEF3, with FF41DAF6 and AE9700F0 available for review. All three preserve a compact leading body through independent 3,600-step native replays. They belong to the same family as the Morphospace movers: a more coherent selection, not new morphological diversity. The collection image remains explicitly separate from the original report's 64-organism developmental measurements.

## Selection and rendering

The existing 626-specimen long-horizon screen provided 135 persistent, localized candidates. An exploratory covariance-aspect screen retained 40 with maximum aspect below three and minimum reported coherence at least 0.95. Visual inspection exposed two limitations: diffuse matter can make a thin core look isotropic, and connected strands can pass a connected-component gate. Neither score alone qualifies an attractive coherent body.

Five visually selected candidates were re-rendered independently for 3,600 steps. Three were retained before their intervention outcomes were available:

| Replay campaign | Creature ID |
| --- | --- |
| 0574-flow-map-elite-19-b26adef3 | B26ADEF3-86EB-5F83-83C2-629C7E0490CD |
| 0531-flow-map-elite-0-ff41daf6 | FF41DAF6-3437-5AB3-90D4-E132FF4D8D7B |
| 0555-flow-map-elite-0-ae9700f0 | AE9700F0-230B-5C6D-8A51-8B87CF2BC721 |

The authoritative full IDs, input hashes, and renderer metadata are in `site/assets/causal-emergence/collection/coherent-bodies.json`. Each animation contains 300 transparent 512-pixel frames at 30 fps, generated from the original 256-cell simulation. The renderer reconstructs channel densities and uses one crop for the complete sequence. It does not increase simulation resolution or track the body frame by frame. Presentation sizes are independent across specimens.

Run `LeniaCLI publish media --input <one-campaign-root> --output <unique-output> --steps 3600 --frame-budget 300 --fps 30 --render-mode body`. The input root must contain `campaigns/<campaign>/` with its replay manifest, config, search, and one-entry library. Export `frames_color/frame_%06d.png` using ffmpeg's lossless `libwebp_anim` at 30 fps with a looping, BGRA output. Poster frames are native frame 25.

Use one output directory per candidate: this CLI version names media folders from the initial seed and creature name, which are not unique across campaigns. Early multi-candidate screening exports had naming collisions and are not used as scientific outputs. Source campaigns were not changed.

## Fixed intervention pilot

`ops/coherent_body_pilot.py` captures the selected bodies at steps 900 and 2,700 and reuses the existing native `local_coupled_cell_swap_v1` operator. Each checkpoint has one untouched continuation and three perturbed continuations, with seeds 17, 31, and 47, a 0.12 cell-swap command, and a 240-step horizon. The plan is saved before any intervention is run.

The pilot preserves each source genotype, initial patch, 256-cell grid, wall boundary, twenty kernels, two channels, and disabled parameter embedding. The ecology continuation requires `profile=experimental` to express an explicitly disabled beam mutation; the source Flow Lenia equation mode and physical parameters remain specified. Captured checkpoints retain all native Float32 channels. Native receipts verify identical starting-state hashes for matched arms and preserved cell inventories.

From the dossier directory, invoke:

```sh
uv run python ops/coherent_body_pilot.py \
  --runner "$LENIA_CLI" \
  --replay-root "$LONG_REPLAY_CAMPAIGNS" \
  --candidate 0574-flow-map-elite-19-b26adef3 \
  --candidate 0531-flow-map-elite-0-ff41daf6 \
  --candidate 0555-flow-map-elite-0-ae9700f0 \
  --output .codex/coherent-body-pilot-new
```

Use a runner supporting `discover local --terminal-state-patch` and ecology's static-genotype shooting continuation. The output must not already exist. The runner hash and source hashes are frozen in the plan. Actual completed run: `.codex/coherent-body-pilot-v1b/`. The preceding attempt stopped at validation because the ecology profile was not yet set; it produced no intervention outcome.

All 24 trials completed. The 18 perturbed runs match their controls' starting hashes and preserve matter, parameter, and occupancy inventories. Maximum relative mass discrepancy at intervention is 1.92e-7; accumulated continuation mass drift is below 1.11e-5. The largest eight-connected component above density 0.001 contains at least 82.06% of all matter throughout the sampled continuations, including diffuse matter in the denominator. Visual inspection of all 24 final fields shows a retained leading body.

This is a selected three-specimen pilot at later ages, not a replication of the original age-response result. Its exploratory field difference is L1 over independently centered, native-resolution Float16 total-matter fields, divided by control mass. Pixel recentering and residual displacement affect that quantity. The realized affected-matter fraction also varies despite a fixed cell command. These values must not be substituted for the original report estimator or used to assert developmental hardening. Dose matching and the original uncertainty analysis remain necessary before making a new developmental claim.

## Review and publication boundary

- `/review/coherent-bodies/` compares the three HQ replays, the previous clip, and all 24 final states. The site publisher excludes `review/`.
- The synthesis template uses B26ADEF3 as the explicitly separate collection illustration. Original numerical arrays and cohort snapshots remain intact.
- The original body's transparent HQ export and exploratory screen images remain local; the three accepted animations have durable public-asset provenance.
- No release, push, or commit is part of this pass.

## Flow-only selection

The three accepted bodies have similar silhouettes. The follow-up search must find distinct bodies under Flow Lenia dynamics. The named-family archive also contains `qd24_additive_v1` configurations despite its broad `flow_lenia` label; those candidates are excluded. Confirm the saved implementation mode before replaying any candidate. The additive review exports have been removed from the site.

Twelve additional candidates from the broader random, named-seed, and MAP-Elites runs received native 3,600-step replays (60 review frames each). Every saved config explicitly uses `flowlenia_2022_paper_equations`. Seven came from the broader 128-cell runs; five came from the persistence and biologically seeded searches at 128 or 256 cells. None was promoted: longer replays showed filament growth, diffusion, separated matter, or the already represented leading-edge form. Source/config hashes and candidate IDs are recorded locally in `.codex/flow-only-body-review/review.json`. This pass does not establish that the archive contains no suitable alternatives.

The next search should require long-run concentration of matter in a bounded connected body and retain diversity across shape descriptors, including compactness and elongation. Repeated diagonal structures in otherwise unrelated archived runs also warrant a reference-implementation comparison before a large new search; visual similarity alone does not establish a numerical bug. The original Flow Lenia examples at https://sites.google.com/view/flowlenia demonstrate a broader range of mass-conserving dynamics.
