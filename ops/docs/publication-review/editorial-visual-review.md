# Editorial visual review

Local review, 10 September 2026. This is a visual and interface review of the current reading selection, not approval to publish or a fresh scientific audit of all archived records.

## Coverage

Inspected rendered pages at 1440 × 1000 and 390 × 1000, using actual browser screenshots, figure crops, and chart crops. The 21 routes below produced 42 desktop/phone captures. Full-page captures were supplemented by individual figures because shrinking a long page into one contact sheet does not establish label legibility.

- `/`
- `/blog/`
- `/addenda/`
- `/cabinet/`
- `/dossiers/`
- `/dossiers/lenia-swarm/`
- `/dossiers/wonton-soup/`
- `/dossiers/zang-levin-playground/`
- `/dossiers/lenia-swarm/morphospace/`
- `/dossiers/lenia-swarm/anatomical-compiler/`
- `/dossiers/lenia-swarm/morphospace/obstacle-response/`
- `/dossiers/lenia-swarm/fiber-theory/`
- `/dossiers/lenia-swarm/compendium/`
- `/dossiers/lenia-swarm/causal-emergence/`
- `/dossiers/lenia-swarm/causal-emergence/reports/synthesis-v7/`
- `/dossiers/lenia-swarm/causal-emergence/reports/fresh-phase-operator/`
- `/dossiers/lenia-swarm/causal-emergence/reports/initial-action-world/`
- `/dossiers/lenia-swarm/causal-emergence/reports/organism-birth-signal/`
- `/dossiers/lenia-swarm/causal-emergence/reports/organism-hardens-without-narrowing/`
- `/dossiers/lenia-swarm/causal-emergence/reports/preinjury-recovery-confirmation/`
- `/dossiers/lenia-swarm/causal-emergence/reports/spatial-scale-action-world/`

Automated companion checks found no page-level horizontal overflow, broken decoded images, or page JavaScript errors in these 42 captures. An initial image check ran before lazy images entered view; rechecking after decoding them removed all apparent failures. That initial result was not a broken-image finding.

## Findings and repairs

Changes are confined to shared CSS; report content, images, measurements, axes, and provenance were not altered by this visual pass.

- Restored light caption text on the retained black specimen panels in `fresh-phase-operator`. The original labels inherited the new paper-theme dark ink and were almost invisible.
- Restored light labels over the visible-matter / hidden-composition canvas pair in the current synthesis.
- Preserved readable mobile SVG dimensions in the selected imported data charts. The fresh-phase plots had compressed roughly 980-pixel figures to 271 pixels, including their type. The trajectory comparison and spatial-scale charts had similar problems. They now scroll inside their figure containers, with a visible instruction, rather than shrinking all labels.
- Extended the anatomical compiler's existing phone treatment to its inline SVG cost plot; its previous rule covered external SVG images only. Lightened the scrolling instruction on dark figure backgrounds.
- Restored the injected site-navigation and publication-navigation links where an original report's compact-navigation rule hid all anchor elements on phones.
- Applied the same bounded horizontal scrolling to the four technical Fiber Theory figures.
- Restored light axis text in the commitment report's deliberately dark data panels.

Imported report CSS is embedded by the verified projection path. Root rebuilt those reports and their transformation receipts after these changes; direct edits to their generated HTML were avoided.

## Figure and editorial observations

- Morphospace's native-body opening clearly distinguishes the two coherent movers from the fish-near specimens. Its caption correctly identifies unobstructed replays, fixed camera, playback duration, and nonphysical display size. The comparison fingerprints are deliberately coarse source measurements, not supposed high-resolution portraits of the opening creatures.
- The fish landmark illustration, rotatable point configuration, coordinate comparison, and PCA map show different representations of the same comparison. Map axis labels and the distinction between the two-dimensional projection and twelve-dimensional selection are present. The shared comparison scale is retained; no visual normalization changed the result.
- The obstacle chart provides sham-relative progress and separate heading difference. The caption explicitly says heading magnitude is not a measure of avoidance. The branch diagram shows initial direction, not a fabricated measured response.
- Anatomical compiler's paired bodies make the descriptor-match / anatomy mismatch visible. The target-field, recovered-rule, and later-time comparisons have explanatory captions that identify which frame was scored. Larger old technical charts remain scrollable rather than being replaced with invented cleaner data.
- Synthesis figures distinguish the two independent early-branching and forecasting comparisons. The zero line and negative whole-versus-split values remain visible. Frozen follow-up and recovery figures retain null and negative results. The source-specimen strips are illustrations, not a replacement for cohort plots.
- Wonton, sorting, and Addenda figures are integrated with their surrounding explanation; their visual identities remain distinct. Cabinet is a deliberately compact document list, not a report gallery.
- Sent the remaining Fiber Theory “fish outlines” wording and the causal-overview stale synthesis title to the content integration owner; they were handled outside this CSS pass.

## Verification artifacts

Ephemeral local evidence is in `/tmp/editorial-visual/`:

- `results.json`: route status, image decoding, overflow, JavaScript errors, figure inventory.
- `{route-number}-{width}-full.png`: full rendered pages; the route numbering follows the list above starting at zero.
- `{route-number}-{width}-fig{figure-number}.png`: individual visible figure crops.
- `chart-{route-number}-{width}-{chart-number}.png`: selected causal SVG crops.
- `figsheet-*`, `chartsheet-*`, and `sheet-*`: inspection contact sheets assembled from the captures.
- `expanded-*.png`: additional captures with technical disclosures opened for selected reports.
- `final-caption.png`, `final-chart-scroll.png`, `final-fiber-phone.png`, `final-header-phone.png`, `final-patch-labels.png`, `final-hardens-phone.png`: targeted after-change verification.
- `final-validation.json`: the final navigation, container scrolling, and page-overflow checks.

Browser automation used a fresh Chrome context after the Helium headless process crashed. No user browser storage, saved reference choices, or live tabs were changed.

## Boundaries and remaining visual work

- The 74 causal records outside the seven-piece reading selection remain historical/supporting material, not newly certified publication-ready figures. Their shared CSS is repaired by projection, but a broad CSS correction is not a figure-by-figure scientific review of the archive.
- The unpublished Lenia primer has no built article at its public route. A later bounded follow-up built and checked its separate local review route; see the addendum below. It remains a draft.
- Poly-morphogenesis is linked from Addenda to its repository manuscript. There is no current local `/addenda/poly-morphogenesis/` report route. This review checked the Addenda presentation, not a nonexistent local report.
- Video posters and explanatory captions were inspected here; this pass did not re-export media or revalidate every replay's numerical trajectory. Earlier motion validation and source receipts remain separate evidence.
- Some original technical figures still use older accents and dense scientific labels. Scrolling makes those labels accessible; a later native HTML/SVG redesign can improve their presentation without changing their values.
- The restored fresh-phase global navigation wraps its final link onto a second phone row because a legacy margin survives. All four destinations are visible and usable; this is a nonblocking spacing refinement for the later visual pass.
- No approved homepage geometry was changed. No deployment, push, merge, or commit was performed by this review.


## Draft-preview follow-up

After the original pass, root built two local-only review routes using the shared article template:

- `/review/blog/lenia-explainer/`
- `/review/blog/research-program-overview/`

Both were visually inspected at 1440 and 390 pixels (four additional captures). Final fresh loads had no failed resources, page JavaScript errors, broken images, page overflow, or unresolved in-page citation anchors. Both show an automatically generated References heading and entries. Their draft markers remain visible; neither was promoted to a public article route.

All nine primer widgets were brought into view and initialized. Actual controls were tested, not just their presence:

- Creature wall: WebGPU rendered a live adapted preset. Explicit Play changed its pixels and Pause froze it.
- Kernel: changing R changed the two-dimensional weights; changing a changed the radial profile. The normalized radial profile appropriately does not change merely when R changes.
- Growth: changing μ changed the function graph; explicit Play advanced its preview and Pause froze it.
- Mass comparison: Play advanced both toy panels, Pause stopped updates, and Reset was exercised. This is labelled a global-rescaling control, not the Flow Lenia transport algorithm.
- Sandbox: actual GPU stepping advanced from 0 to 88 at the tested speed; Pause froze pixels and the step counter; Reset returned the counter to 0; selecting Geminium loaded its different preset at step 0.
- Search: scrubbing changed the synthetic history and scores; Play advanced it; a separate pause check held the step at 15; Reset returned to 0.
- CVT: Play advanced the partition; Pause held it; Step advanced the iteration by one; Reset returned to iteration 0.
- MAP-Elites: generation scrub changed coverage and scores; Play advanced; Pause held; Reset cleared generation and archive metrics. It is labelled synthetic teaching data.
- Isoline variation: both slider changes and dragging an endpoint changed the displayed distribution.

All nine were visually stable on initial load under `prefers-reduced-motion: reduce`; explicit playback still operated. A separate browser context with WebGPU removed displayed the sandbox's visible unsupported explanation and disabled its Play/Reset buttons, while the article remained readable.

Two CSS fixes were made in the primer's own stylesheet: stack title/subtitle on narrow phones so long widget titles are not split midword, and preserve mathematical slider-label case. Previously text-transform made distinct R/r controls both look like R and changed μ/σ into uppercase glyphs.

Evidence: `draft-qa.json`, `primer-functional.json`, `draft-{article}-{width}.png`, `primer-{width}-canvas{n}.png`, `primer-control-*.png`, `primer-gpu-geminium.png`, and `primer-fallback.png` under the same temporary evidence directory. These interaction checks do not establish scientific equivalence between an adapted browser preset and a canonical native Lenia replay.

## Release narrative recheck

Rechecked five release-bound routes after the latest narrative changes at 1440 and 390 pixels: Writing, Morphospace, Anatomical Compiler, Synthesis v7, and Wonton Soup (ten viewport checks). Visually inspected their top sections and 24 captured section-transition views across the four section-based routes. Wonton Soup uses article headings rather than section wrappers; its opening was inspected at both widths.

The first desktop capture caught Morphospace's second introductory paragraph flowing into the narrow margin column. Root grouped the two paragraphs in one `.report-hero-dek` element. Fresh desktop and phone screenshots confirm both paragraphs now share the text column and the distance-to-fish note occupies its intended margin; no overlap remains. The Synthesis opening and first section have distinct headings with no duplicates, and the prose-to-diagram transition remains intact. Existing phone figure scrolling remains intentional.

All ten final loads reported no page overflow, JavaScript errors, failed HTTP resources, or unresolved in-page anchors. Video source/poster URLs remain populated without media errors. This is a targeted narrative-regression check, not a new certification of every interaction or every report. Draft previews were excluded from this pass. No CSS or layout experiment was introduced.

Evidence: `/tmp/editorial-visual/release-narrative.json`, `release-{0..4}-{1440|390}-top.png`, `release-*-section*.png`, and `release-transitions-*.png`.

### Morphospace annotation follow-up

- Recast the fish comparison around the reversal in measured proximity and its interpretation. The selected cohort, distances, and comparison data are unchanged.
- Replaced the enlarged 32 × 32 fingerprint with the same specimen’s original 128 × 128 replay, retaining the fingerprint in expandable measurement details. All six published fish-near poster images were inspected; they contain similar elongated structures. This does not establish that no stronger specimen exists elsewhere in the archive.
- Replaced the transport scorecards with an interpretation in the main text and the full 109/4,802, 1/5, 0/5 counts in expandable methods. The negative result remains explicit. The closing panel states a testable prediction about turning and recovery.
- Applied shared publication typography and navigation to the obstacle report on the existing panel-paper token; removed raised shadows. Homepage styling unchanged.
- Checked both routes at 1440 and 390 pixels: no page overflow, failed resources, missing local anchors, or JavaScript errors. The replacement replay plays at both widths. Expanded the transport methods and verified all three counts; confirmed the schematic loads at its original dimensions. These are local checks, with no release action.

### Synthesis publication treatment

- Replaced the synthesis opening with the accepted serif publication title, ultramarine/apricot palette, and a channel-field instrument. Its host, near-donor, far-donor, and scrambled-donor views use the four original encoded Float32 fields. Fixed the upstream renderer, which had indexed the Base64 string as numeric field data.
- Added an age instrument coupling five recorded s01 snapshots to the 133 cohort means already present in the report heatmap. The seven horizon choices and five checkpoint positions update the chart and readout. Playback advances through saved checkpoints; there is no interpolated creature motion. Native portraits and cohort measurements remain explicitly distinguished.
- Replaced the boxed forecasting schematic with open wiring diagrams and a typographic statement of the subtraction. Restyled the report’s sections, methods, and comparisons; removed a sticky callout that overlapped the corrected field figures.
- The canonical projection now installs and refreshes the treatment while preserving source provenance. All 15 embedded PNGs, four encoded channel fields, and 133 fixed-command age/horizon means are unchanged from the prior report. All 81 installed report/context/receipt hashes verify.
- Nine causal publication tests passed, including a new re-import check for preservation of source evidence and non-duplication of instruments. At 1440 and 390 pixels, the channel view changes with donor choice while visible-matter renders remain identical. All eight original channel canvases contain nonuniform rendered data. The age/horizon controls and start/pause playback work. No missing section anchors, failed resources, page overflow, or JavaScript errors were observed. Local only; no deployment.

### Synthesis annotation corrections

- Restored ink-only headline emphasis and repaired text contrast in the former dark sections, including their synthesis and boundary cards. Replaced the two oversized metaphor blocks with ordinary result headings and prose. Removed the redundant forecasting subtraction banner and footer recap.
- Donor selection now opens on a signed channel-fraction difference map, with the same ±25 percentage-point color scale for every donor (explicitly saturated beyond its ends). An unclipped, mass-weighted absolute difference readout distinguishes the host (0.0 pp), nearby donor (16.3), distant donor (10.5), and scrambled nearby donor (22.4). The visible-matter view deliberately remains identical, with this stated in its live feedback.
- Visually inspected the saved organism-observation sheet, four coherent-scout renders, and six orbiter/shape-preserving renders. Added a recorded orbiter, specimen 5682, from the broader collection; its source run, original video hash, and display crop are recorded beside the assets. It is explicitly separate from the age cohort. Moved the five s01 checkpoints into an expandable inspection panel, retaining their age synchronization and the original evidence images.
- At 1440 and 390 pixels: four distinct donor difference renders, identical visible-matter renders, working video playback, passage-780 snapshot selection, no page overflow, failed resources, missing anchors, or JavaScript errors. All 47 visible headings at each width exceeded 4.5:1 contrast against their computed surfaces. Visually inspected the opening, age instrument, forecasting section, both revised result blocks, and formerly unreadable sections at both widths. Nine projection tests passed. The 15 embedded PNGs, four source channel arrays, and 133 recorded means are unchanged.
- Local review only. These corrections supersede the earlier claim that visual inspection of the top and a few interactions was sufficient to verify the full report.

## Coherent-body replacements and native HQ exports

The synthesis collection illustration now uses B26ADEF3, re-rendered from its original 256-cell configuration into 300 transparent 512-pixel frames over 3,600 simulation steps. FF41DAF6 and AE9700F0 have the same export treatment. `/review/coherent-bodies/` provides all three replays, the previous clip, and the independent pilot outputs. The review route is excluded from publication.

A fixed pilot on these three specimens completed 24 native cell-swap/control continuations at two later ages. Matched starting-state hashes and inventory preservation were checked for every arm. The analysis and limits are recorded in [coherent-body-pilot.md](coherent-body-pilot.md); this selected cohort does not replace the report's original developmental results.

The hero's saved channel fields now reconstruct density at 512 presentation pixels with a shared crop, while differences remain calculated from the original arrays. All 15 embedded source images and four Float32 payloads remain byte-identical to the preceding staged report. Donor readouts remain 0.0, 16.3, 10.5, and 22.4 percentage points.

Desktop (1440px) and phone (390px) browser checks found visible frame-to-frame animation, working play/pause, no overflow, no failed resources, and no JavaScript errors. Reduced-motion starts with still images. Screenshots of both report and review were inspected. All nine causal-publication tests pass, and all 81 report/context/receipt hashes verify after installing only the synthesis projection. No deployment or commit was made.
