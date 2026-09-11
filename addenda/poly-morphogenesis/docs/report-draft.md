# Same-sized cuts, different patterns

*Editorial draft · September 2026. Based on the existing paper and an inspection of the implementation. Numerical sweep results below are inherited from the paper, not newly reproduced.*

Imagine a small sheet of cells exchanging two chemicals. One chemical promotes activity; the other suppresses it. Their reactions and movement between neighboring cells can produce a spatial pattern. Now isolate a rectangular patch by cutting its connections to the surrounding sheet. Keep the cells, their initial concentrations, and the reaction laws. Change only which cells can exchange chemicals.

Does moving the cut change the pattern, even when the isolated patch stays the same size?

Our Julia implementation gives us a way to make this comparison precisely. On a four-by-six grid, a two-by-two patch has fifteen possible placements. Each placement separates four cells from the other twenty. In every case, eighty pairs of cells lose their connecting path: four times twenty. That count cannot distinguish one placement from another. The reaction–diffusion dynamics can still differ because the shapes of the remaining domains and the initial concentrations inside them differ.

## From counting peaks to changing connections

The project began with a one-dimensional controller that alternates between forming a pattern and counting its peaks. A reaction–diffusion phase changes the chemical field. A gene-network phase counts the peaks, and feedback adjusts the diffusion scale for the next iteration. The implementation separates those phases and makes their state transfers explicit.

Catlab wiring diagrams and polynomial interfaces help express the composition: which state a phase receives, what it produces, and how that output becomes another phase's input. The two-dimensional experiment takes a narrower part of this system—the reaction–diffusion field—and changes its wiring. It does not yet implement the peak-counting wave or feedback controller in two dimensions.

This separation matters. A result about two-dimensional pattern formation is not yet a result about two-dimensional repair or goal-directed control.

## Fifteen placements of the same patch

For each placement, we compare two simulations starting from the same initial concentration field. One develops with all grid connections intact. The other develops with the patch boundary disconnected from the outset. Cells inside the patch continue to exchange chemicals with one another, as do cells in the exterior.

The existing draft describes this partly as severing a settled pattern. The current code instead starts each disconnected simulation from the original initial state. It measures how altered wiring changes development. Applying a cut to an already formed pattern would be a different experiment.

Once disconnected, the patch and exterior cannot influence each other. Their equations can be solved separately and the resulting fields assembled back onto the grid. This factorization is exact at the level of the differential equations: there are no remaining coupling terms between the components. Numerical integration still requires a check against solving the entire disconnected system together, with matching tolerances and stopping rules.

**Figure to build from reproduced data:** a selectable four-by-six grid with all fifteen patch placements. Beside it, show the intact final field, the disconnected final field, and their difference using shared color scales. The selected patch should remain outlined in each view. Keep the initial field visible so the reader can see what was held fixed.

## Comparing the resulting patterns

We compare the final activator fields directly and also turn each field into an active-cell mask. A cell is active when its concentration exceeds a chosen fraction of that field's maximum. This lets us ask several related questions: how much did concentrations change, which cells changed activity, and how many connected regions of activity remain?

The original analysis combines three measurements into each of three scores. Each measurement is divided by its largest value across the placements in that regime, then the three normalized measurements are averaged. A score is therefore relative to the other placements tested under the same conditions. It is not an absolute amount of damage, and equal scores in different regimes need not describe equal physical changes.

The paper reports variation between placements across 480 regimes: ten initial seeds, four patch sizes, four activator diffusion values, and three inhibitor diffusion values. At the default activity threshold, its reported mean difference between the highest and lowest scores is 0.751 for the balanced score, 0.812 for the profile score, and 0.856 for the structure score. These values need to be regenerated from saved per-placement outputs before they become publication claims.

If reproduced, the useful finding is that a count of disconnected cell pairs discards information relevant to the resulting pattern. It does not establish that one composite score captures all meaningful changes, or that different scores agree on the worst placement.

**Figure to build from reproduced data:** show all fifteen placements as a small severity map for one regime, followed by the distribution of within-regime score ranges across seeds and parameters. Include raw concentration differences alongside the normalized scores. Allow switching between scores and activity thresholds without changing the grid or color-scale conventions silently.

## What the ranking tells us

The current severity ranking uses the simulated outcome of every placement. Its normalization also depends on the complete set of outcomes. It describes the sweep after it has run; it does not predict the worst placement without running that sweep.

Nor is disagreement with the connectivity ranking an informative accuracy measure here. Connectivity assigns every placement the same value, and the code resolves those ties by row and column. A severity winner appearing elsewhere mostly tells us that it differs from an arbitrary first entry.

The compositional representation supplies a transparent way to construct and solve disconnected systems. The present experiment does not show that this representation predicts outcomes better than an ordinary graph-based reaction–diffusion solver. To establish a practical advantage, we would need to measure something additional: reusable component solutions, reduced computation, or a ranking chosen before evaluating the held-out outcomes.

## The next comparison

A useful extension would begin with a formed pattern, save its full chemical state, and apply each cut to that same state. We could then follow the response through time instead of comparing only final fields. Some placements might cause a large transient change and recover; others might settle into a different pattern. Restoring the severed edges would introduce a further question: does reconnecting the same cells restore the original organization?

That experiment would connect the project's two strands more directly: explicit composition of a controller, and the changing patterns of the system it controls. For now, the first report should make the simpler comparison visible and reproducible: identical patch sizes, different placements, and the patterns those connections permit.

## Sources and reproduction status

- Original draft: [Compositional Vulnerability Maps for Severed Reaction-Diffusion Tissues](paper/main.typ).
- Experiment implementation: `src/grid_lesions.jl`, especially `grid_patch_isolation_demo`, `_factorized_graph_snapshot`, and `_calibrate_severity!`.
- Integration and stopping: `src/rd_graph.jl`, especially `settle_rd_graph!`.
- Existing structural and numerical checks: `test/test_grid_lesions.jl` and `test/test_rd_graph.jl`.
- The original draft attributes the one-dimensional controller to Grodstein, McMillen and Levin (2023); its bibliography is in `docs/paper/refs.bib`.

The original paper contains aggregate tables and reproduction commands. The saved sweep outputs were not found in the two inspected local checkouts. No simulations were rerun for this editorial draft. Keep this document as a draft until the per-placement evidence and figures have been regenerated and checked.
