# Report layout maintenance

The publication styles are shared by the report family. Change the owning rule rather than appending a dated override or adding a second stylesheet for a visual revision.

## Where changes belong

| Source | Responsibility |
| --- | --- |
| `site/assets/publication-layout.css` | Site shell, navigation, publication fonts, shared report conventions and spacing tokens. |
| `site/assets/report.css` | Report components, Morphospace compositions and Fiber Theory layout. |
| `site/assets/publication-formats.css` | Publication-format treatments: home, dossier, note and method report. |
| `site/dossiers/lenia-swarm/anatomical-compiler/index.html` | Anatomy markup and its scoped page styles, including its chapter and specimen layouts. |
| `site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-publication.css` | Development report treatment. This is embedded by the Rust release renderer. |
| `site/dossiers/lenia-swarm/causal-emergence/report-polish.css` | Shared rendering of imported causal reports and their instruments; do not put Anatomy layout overrides here. |

Keep responsive declarations with the owning stylesheet, after the base rules. Each media condition has one block. Preserve meaningful layout variation: reading columns, paired introductions and figures wider than the prose serve different purposes.

## Spacing

`publication-layout.css` defines the single spacing scale:

| Token | Desktop | Up to 700px | Use |
| --- | ---: | ---: | --- |
| `--publication-space-prose` | 16px | 16px | Related paragraphs and disclosures |
| `--publication-space-block` | 32px | 24px | Elements within an explanation |
| `--publication-space-topic` | 64px | 48px | New topics and substantial figures |
| `--publication-space-section` | 96px | 72px | Chapter boundaries |

Give each transition one spacing owner. Account for a parent's grid gap before adding a child's margin. A heading stays closer to the material it introduces than to the preceding topic. Captions stay attached to their figures. Use the shared tokens directly rather than making page-local aliases for the same values.

The report shell is capped at 1440px; the other publication pages retain the shared site shell. Morphospace's reading and figure widths are separate component dimensions in `report.css`.

## Build and review

For stylesheet-only changes, run `ops/spctr/target/debug/spctr site build` and compare the affected pages at desktop and phone widths. Include a neighboring page that uses the same stylesheet. Inspect computed margins, padding, fonts and widths as well as actual screenshots; exercise any affected disclosure, replay or chart control. Use an uncached local preview.

For the Development template, first rebuild `spctr` with `cargo build --manifest-path ops/spctr/Cargo.toml --bin spctr`: its stylesheet is included at compile time. Run `spctr site stage-lenia-causal-reports --input-root <verified-input-root> --output <new-staging-directory> --id synthesis-v7`. Copy the staged report and its receipt together, and replace only the matching entry in the site's report manifest. Do not edit generated report HTML or hashes by hand. Run `cargo test --manifest-path ops/spctr/Cargo.toml --lib site::causal_emergence_release` after regeneration.

Keep temporary snapshots and comparison servers outside the tracked site. Checkpoint an approved design before refactoring, preserve its geometry and content during cleanup, and report local validation separately from deployment.

## Homepage replays

The homepage selects one creature on each load, avoiding the previous selection within the browser tab. The small curated list lives in `site/templates/index.html`; changing it requires `spctr site build --write`. Only the selected hero video loads. Keep pause controls on the shared `.publication-motion` component.

Native replay exports live in `site/assets/home-creatures/`, with a poster and JSON provenance beside each MP4. Use the existing renderer to package another candidate:

```sh
LeniaCLI publish media --input <single-specimen-replay-root> --output <media-root> \
  --steps 120 --frame-budget 120 --fps 15 --render-mode body
uv run --with numpy --with scipy --with pillow python \
  dossiers/lenia-swarm/ops/render_homepage_creature.py \
  --media-root <media-root> --campaign <source-campaign> --steps 120 \
  --output site/assets/home-creatures/<slug> --title '<accurate specimen label>'
```

Use the current native CLI: media capture disables the additive search engine's automatic recentering so locomotion remains visible. Search itself retains its existing behavior. An unchanged crop alone does not guarantee world-coordinate footage when an older capture engine centers the simulation.

The packager uses one fixed crop across the recording and preserves its playback rate. It checks connected mass, clipping, and centroid travel of at least 12% of the crop width. Inspect the playback as well: displacement alone does not establish an interesting or persistent body. Choose a segment that ends before a torus-edge crossing; a wrap can split the visible creature. `--steps` must match the native capture command. Spatial interpolation improves presentation, not simulation resolution.

The homepage mixes the original Quadrium study with Geminidae-derived `4F18F1D6` and Pterifera-derived `46E696E5`, from the preserved family replay collection. The latter two are eight-second, 1024-square recordings of 120 native steps at 15 fps. Their receipts record source configurations, capture timing, connected mass, displacement, and file hashes. The original Quadrium study uses its separately documented simulation-grid refinement. All three are additive Lenia; do not label them Flow Lenia. Keep candidate exports and contact sheets outside the published tree.

## Wonton dossier evidence

Refresh the dossier counts with `uv run --with duckdb python dossiers/wonton-soup/paper/export_dossier_evidence.py --db <preserved-lake.duckdb>`, then run `spctr site build --write`. The exporter reuses the paper's completed-run selection, writes `site/assets/wonton-soup/dossier-evidence.json`, and replaces the marked evidence region in the dossier template. Do not edit those generated counts by hand.

Repeated-seed trial counts, guided/blind tactic-attempt totals, and intervention survival have different denominators. Keep their labels attached. The featured `encode_inl` reroute is checked against original history hashes and recorded proof closure; its unchanged control blocks `decide`, already excluded by the baseline provider. The older full showcase and preprint retain their frozen figures; they are separate snapshots, not sources for a current-lake headline.

## Addenda emblems

`site/assets/addenda-symbols.svg` contains the original editorial emblems; symbol IDs match addendum slugs. Add a corresponding symbol when adding an addendum. These are schematic illustrations of the subjects, not measured results. Their engraved linework takes its visual cue from the recursive book illustration in the [SPECTER reference board](https://www.are.na/block/49421548).

The index renderer places each emblem beside its entry using the shared layout in `site/assets/addenda.css`. Keep the SVG sprite as the artwork source, use the existing 160-unit viewBox, and check both the 144px desktop and 80px phone treatments. No drawing library or client-side generation is required.
