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
