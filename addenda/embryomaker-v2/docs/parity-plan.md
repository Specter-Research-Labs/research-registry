# Parity Plan

The goal is not to port the legacy EmbryoMaker code line by line.

The goal is:

- preserve the core mathematics 1:1 where they define benchmark behavior,
- preserve the scheduler and event order when they matter,
- and make any intentional deviations explicit and benchmarked.

## Parity Principle

There are two different kinds of parity:

1. code parity
2. mathematical parity

We want mathematical parity.

This means:

- the same state variables,
- the same update equations,
- the same stepping order,
- the same event semantics,
- and the same benchmark outputs within declared tolerances.

It does not mean copying the same implementation style.

## Original Surfaces To Match First

The first parity program should cover the original developmental core:

- overdamped mechanics
- neighbor construction
- Euler, RK4, and adaptive RK stepping
- polarity-aware growth and division hooks
- diffusion / secretion surfaces that affect benchmark behavior
- event order in the main iteration loop

The original engine also includes many optional and accreted pathways. Those
should not all be treated as equally sacred.

## Parity Lanes

### Lane 0: mathematical transcription

For each selected benchmark surface:

- define the exact variables
- define the exact equations
- define the exact event ordering
- define the exact tolerances

This lane produces a parity ledger, not code first.

### Lane 1: state-space parity

Define the v2 state variables that correspond to the original model:

- node or cell state
- cell aggregates
- neighbor/contact state
- field state
- regulatory state

If a legacy variable has no explicit v2 image, that gap must be recorded.

### Lane 2: execution parity

Reproduce the original update order for the chosen benchmark lane:

- centroid updates if needed
- neighbor rebuild points
- force evaluation order
- field and regulation order
- event application order

This is where most accidental regressions happen.

### Lane 3: baseline execution

Run selected original benchmarks and save:

- config or input artifact
- raw output
- summary metrics
- selected snapshots
- toolchain provenance

### Lane 4: v2 comparison

Run the v2 transcription mode and compare:

- counts
- geometry metrics
- field totals
- selected trajectories
- event counts
- terminal morphology class

## First Benchmark Panel

Start with a small panel.

Recommended first cases from the original presets:

1. apoptosis
2. cell sorting
3. invagination
4. epithelial directed growth
5. mesenchymal directed growth
6. ECM secretion
7. migration

These are useful because they already exist as canonical legacy initial-condition
surfaces and exercise different mechanisms.

## Comparison Metrics

Do not compare images only.

Required metrics:

- node count or cell count over time
- centroid trajectories
- bounding-box or gyration metrics
- contact-count summaries
- selected state variable trajectories
- event counts
- terminal class

Optional if available:

- per-step force norms
- per-step displacement maxima
- species or gene concentration norms

## Tolerance Policy

Use three comparison bands:

- exact parity: identical up to deterministic serialization / float roundoff
- numerical parity: within declared floating tolerance, same event pattern
- behavioral parity: same morphology class and comparable summary trajectory

The first goal is exact or numerical parity on the smallest benchmark slice.

## Baseline Environment

The original code should be baselined in a controlled environment, not ad hoc on
whatever workstation is nearby.

Preferred baseline environment:

- Linux x86_64
- `gfortran`
- `freeglut`
- pinned compiler version
- pinned runtime libraries

Reason:

- the original compile scripts are old
- Apple-silicon parity is possible but not the cleanest initial baseline lane

Inference:
The cleanest first baseline path is likely a Linux container or Nix shell that
builds the original code in a repeatable way.

Current finding as of 2026-03-22:

- a headless baseline lane looks plausible through the legacy `aut=1` or
  `aut=5` path
- the cleaner first host is still Linux `x86_64`
- modern macOS `arm64` is the shakier first baseline target because the legacy
  scripts assume old Mac Fortran toolchains and OpenGL build conventions

## Cell Sorting v0

The first implemented transcription lane is the legacy cell-sorting preset.

Matched now:

- preset counts and scalar parameters
- legacy 27-box neighbor construction for the cell-sorting lane
- legacy neighbor ordering and Euclidean `dneigh` writes for the
  `neighbor_build -> iniboxes_p -> neighbor_build_simpleneigh` branch
- mesenchymal-only geometry construction
- one-hot adhesion classes with the original `kadh` matrix
- mesenchymal compact-support pair force law
- per-node positive-force cap at `maxad=50`
- fixed-delta RK4 stepping for the mechanics lane with a single neighbor build
  before the RK stages
- RK-stage distance refresh plus the legacy cutoff gate for stale mesenchymal
  neighbor pairs
- local mesenchymal energy evaluation for `energia(nodmo)` on the
  cell-sorting lane
- isotropic one-node Metropolis noise proposals with centroid bookkeeping
- fixed-delta noise batching with `c=nd*prop_noise`
- the original gfortran `random_number` stream behind both the preset
  initialization and the `nparti=1000` sphere table, including rewinding the
  saved frame-0 live seed words back to the pre-sphere state
- trajectory parity against the compiled legacy executable

Current comparison result as of 2026-03-22:

- the staged Linux baseline and the v2 trajectory comparator both run end to
  end on the cell-sorting lane
- the current 5% tolerance bundle passes on all 101 frames
- the staged comparison artifact is
  `tmp/legacy-cell-sorting-baseline/artifacts/cell_sorting_v2_comparison.json`
- the closing fixes were exact frame-0 RNG reconstruction and the RK-stage
  mesenchymal cutoff check

## Explicit Non-Goals For Early Parity

- full parity with every historical feature flag
- full parity with GUI rendering
- full parity with every snapshot format revision
- immediate parity with all mutation / evolution surfaces

The first milestone is much smaller:

- one deterministic mechanics lane
- one diffusion or secretion lane
- one topology-changing lane

## Deliverables

The parity program should produce:

- a parity ledger per benchmark
- a baseline artifact bundle for the original
- a v2 comparison artifact bundle
- a pass or fail decision with an explicit reason

This makes "1:1 match" an auditable program instead of a slogan.

Current comparison scaffolding now includes:

- a staged legacy baseline runner for the cell-sorting preset
- a staged Apple-host `linux/amd64` Docker wrapper for that same baseline lane
- a stable-subset parser for legacy `.dat` snapshots on that lane
- a v2 outer-loop summary surface for the same lane
- a lane-specific comparator between parsed legacy snapshots and v2 summaries
- a lane-specific trajectory comparator over a whole legacy snapshot directory
- JSON comparison bundle emission with an explicit pass or fail reason

## Invagination Bootstrap

The next benchmark lane is invagination, and the staged legacy baseline now runs
for that preset too.

Current findings from the real legacy `0.dat` and later runtime snapshots as of
2026-03-22:

- frame 0 starts with `1274` epithelial nodes and `91` epithelial cells
- the epithelial sheet is exactly split into `637` apical and `637` basal nodes
- all epithelial nodes are paired through the legacy `%altre` relation
- the initial polarized expression patch covers `7` cells, with `49` basal
  gene-1-positive nodes and `49` apical gene-2-positive nodes
- exactly `98` nodes start with `pla=0` and `kvol=0`, matching the central
  contractile patch described in the preset source
- through the observed later snapshots at `getot=5802` and `getot=19367`
  (`rtime≈10` and `rtime≈30`), node count and cell count stay fixed at
  `1274` and `91`
- the kernel now exposes a dedicated invagination bootstrap state surface and
  summary executable, and the staged real `0.dat` passes that bootstrap
  comparison exactly via
  `baseline compare-invagination-bootstrap`
- the kernel now also exposes a first fixed-topology post-bootstrap compare
  surface via `baseline compare-invagination`, using the real staged `0.dat`
  as bootstrap input and `5802.dat` as the first target frame
- the full frame-0 bootstrap state now preserves the legacy `%marge`,
  `%talone`, and `%fix` flags in addition to the earlier epithelial mechanics
  fields
- by `5802.dat`, the v2 state also matches the legacy per-node
  `eqd/add/cod/grd/pld/vod/pla/kvol` surface exactly, so the remaining
  geometry drift is in force integration and position evolution rather than in
  the `nexe_gradual` contractile-patch update itself
- porting the legacy restored epithelial topology into the invagination kernel
  was the decisive structural fix:
  the compare now builds an ADD-range neighbor graph once per outer step,
  carries the saved epithelial `oneigh` topology from frame 0, reapplies the
  `restore_neighbors` recovery rule, and reuses that restored graph across the
  RK stages instead of rediscovering all contacts every force evaluation
- that port collapsed the `5802.dat` geometry miss from
  `max_position_error=0.18375603110506017`,
  `mean_position_error=0.04696190706123148`, and
  `rms_position_error=0.059864304491794515`
  down to
  `max_position_error=0.0023666159636699814`,
  `mean_position_error=0.0012363368648368742`, and
  `rms_position_error=0.0013635168956431473`
- the remaining miss is now a small, systematic inward `z` bias rather than a
  topology failure: summary parity still passes exactly, but the current
  geometry lane misses only the `0.001` absolute `max_position_error`
  threshold
- the new step-targeted compare confirms this is not just a stop-condition
  mismatch:
  running the v2 lane to the legacy snapshot `getot=5802` lands at
  `rtime=9.96814` with
  `max_position_error=0.015140400206941245`,
  which is materially worse than the current rtime-targeted compare; the
  remaining gap is therefore in per-step force magnitude or adaptive `delta`,
  not in how the runner decides to stop
- the new kernel step trace sharpens that diagnosis:
  at the same `getot`, the v2 lane is already behind legacy in accumulated
  `rtime` by `-0.040687847212914185` at step `2800`, with the largest sampled
  checkpoint miss at step `5600`
  (`legacy_rtime=9.619808487305749` versus `v2_rtime=9.577061519694343`);
  the biggest 100-step trough is `2700-2800`, where the legacy average
  `delta` is `0.00253450` but the v2 average is only `0.00214873`, so the next
  parity cut should instrument or port the force-scale logic that drives that
  adaptive-step dip
- a follow-up probe on restored-edge `ADDe/EQDe` values did not change the
  result, so the next diagnosis should focus on the last force-scale or
  stepping quirk rather than retrying saved-neighbor surface variants
- two additional neighbor-surface probes were reverted because they moved the
  real compare sharply in the wrong direction:
  treating the lane like the complex epithelial neighbor builder and porting
  the legacy `rv+1e-3` box scale both blew the geometry miss back out, so the
  current best-known state remains the simpler saved-neighbor port above
- the 2026-04-06 probe that rolled the saved epithelial ledger forward each
  outer step also blew parity up in the wrong direction:
  the rtime-targeted compare fell to `v2_getot=5518` with
  `max_position_error=0.2368792525368971`, and the step-targeted compare hit
  `v2_rtime=10.573` with `max_position_error=0.19579880608933528`, so the
  current best-known state still keeps the bootstrap-era restored-neighbor
  ledger for this lane
- a matching 2026-04-06 probe that switched the simple invagination force lane
  to node-valued `add/eqd` cutoffs and `deqe` produced the same blown-up
  compares, so the present best-known parity slice still depends on the
  existing edge-valued restored-neighbor surface even though the non-polarized
  legacy source looks conceptually cleaner
- a same-day coefficient audit against the early `ic.mod.f90` preset blocks was
  a false lead for this staged lane: the active invagination preset still uses
  `rec=50` and `eqs=0.25` in the later block near line `2388`, not the
  unrelated `rec=30` / `eqs=0.15` values from the separate block near line
  `217`
- a 2026-04-07 provenance audit split the March oracle from the later April
  regression cleanly:
  the checked-in March binary at `kernel/build/em2_legacy_invagination_summary`
  still reproduces the recorded near-miss exactly
  (`v2_getot=5819`, `max_position_error=0.0023666159636699814` in rtime mode,
  and `v2_rtime=9.96814`, `max_position_error=0.015140400206941245` in
  step-targeted mode), and a clean workspace built from tracked commit
  `b511408679e6` reproduces the same signatures; the first bad tracked source
  is therefore `295c47cfbee6`, which already lands at
  `v2_getot=5651`, `max_position_error=0.026328661563438438`
- the same 2026-04-07 bisect also found that the first bad tracked commit is
  not failing because of the obvious topology probes inside that patch:
  re-testing the opposite-side epithelial admission, the per-step
  saved-neighbor roll-forward, and the bootstrap restored-ledger seeding did
  not move the bad `5651 / 0.0263` signature at all, so the real regression
  had to be a smaller arithmetic change inside the force loop
- the actual regression in `295c47cfbee6` is numerical rather than structural:
  the diagnostics refactor changed the final same-side torsion accumulation
  from the legacy arithmetic
  `(torsion + surface_torsion) * inverse_neighbor_count`
  into two separately scaled terms before summation; restoring the original
  total-force arithmetic while keeping the diagnostic surfaces in place
  snaps the live source back onto the March oracle lane at
  `v2_getot=5819`, `v2_rtime=10.0013`,
  `max_position_error=0.002367103895049276` in rtime mode, and
  `v2_rtime=9.96814`, `max_position_error=0.015142038183811221` in
  step-targeted mode, which is within `5e-7` of the old recorded geometry
  benchmark
- a later 2026-04-06 cut found and fixed one real early mechanics bug:
  the current neighborhood builder was wrongly skipping opposite-side
  epithelial pairs before force evaluation, while the legacy
  `forces_calculating_distances` lane does admit those contacts; removing that
  skip closes the old step-1 lateral drift and leaves the v2 state exact
  through steps `1`, `2`, `1000`, `2000`, `2200`, `2300`, `2350`, `2370`,
  `2375`, `2378`, and `2379`
- with that fix in place, the first visible geometry miss is now a single-step
  cliff:
  the staged v2 state at step `2379` still matches the March oracle to machine
  precision, but step `2380` is the first bad checkpoint, with the earliest
  visible drift concentrated in nodes `3`, `4`, `6`, and `7`
- the same-day restart probes rule out the stronger hidden-history story:
  starting from the oracle step-`2379` visible state, forcing the hidden
  `original` add/cod/grd baseline back to the real step-`0` bootstrap, and
  reusing the carried step-`2379` saved-neighbor ledger still reproduces the
  oracle step-`2380` state exactly; starting from the current step-`2379`
  visible state with that same saved-neighbor ledger reproduces the bad current
  step-`2380` state instead, so the remaining miss is in an epsilon-scale
  visible-state drift rather than in extra hidden restored-neighbor history
- the saved epithelial ledger dump still matters, but only as a narrowed input
  surface:
  at step `2379`, the carried full-run ledger and a fresh rebuild from the same
  visible geometry have the same neighbor sets and only differ in per-node
  ordering on `24` nodes, while the restored neighborhood reused through the RK
  stages is otherwise stable
- two extra 2026-04-06 “big swing” probes were also falsified and reverted:
  sorting the saved ledger per node, and re-canonicalizing the ledger from the
  live geometry at the start of each outer step, both left the step-`2380`
  miss unchanged at `max_position_error≈5.43514e-4`
- a later 2026-04-06 `k4` pairwise replay finally isolated the first actual
  branch flip:
  at step `2380`, `k1-k3` still match to roundoff, but the bad run activates
  the `twoep==1` torsion branch for the same-cell basal pairs `(2,5)` and
  `(3,6)` because their `vertical_projection` values land just above
  `kEpsilon`, while the oracle lands just below that threshold
- a follow-up 2026-04-07 pair-trace CLI cut tightened that bracket from
  “bad step `2380`” to the exact local replay surface:
  restarting from a fresh current step-`2378` checkpoint with the carried
  current saved-neighbor ledger reproduces the oracle step-`2379` state to
  roundoff (`max_position_error=2.5510982866352577e-15`), while restarting
  from the matching step-`2379` checkpoints blows up immediately at
  step `2380` (`max_position_error=0.00060321329784332131` at node `3`)
- on that same replay surface, the first dirty predicate is now explicit:
  the hot pairs `(2,5)` and `(3,6)` still match through `k1-k3`, and the
  first branch divergence is the `twoep==1` torsion gate
  `abs(vertical_projection) - angletor * distance > kEpsilon` inside `k4`;
  the bad replay reaches `vertical_projection=-2.5358575853425532e-15`
  and `-2.9893314946276901e-15`, while the oracle stays at
  `3.2965812233509731e-16` and `1.6059276797850305e-15`, so the next parity
  cut should stay inside step `2379` rather than reopening wide step-level
  bisection
- a same-day live-loop trace refactor confirmed that result without relying on
  a replay copy of the branch logic, and the richer raw geometry tightened the
  next target again:
  for both hot pairs, `pair_dz` stays exactly `0` at the first bad `k4`
  sample, `mc_norm` stays fixed at `1.156176482858579x`, and the whole
  `dotp` / `vertical_projection` flip comes from the tiny in-plane residual in
  `mc = cx + icx` / `cy + icy` rather than from a broader distance or norm
  drift; the dominant term is specifically `mcy * pair_dy`, not the pair
  vector itself
  (`(2,5)` shifts by about `-2.57859e-15` on the y-term versus
  `-7.34451e-16` on the x-term; `(3,6)` shifts by about `-3.86171e-15` on the
  y-term versus `-1.45122e-15` on the x-term), so the next parity cut should
  target the opposite-node y-coordinate cancellation for quartets
  `(2,5,9,12)` and `(3,6,10,13)` inside the step-`2379` `k4` input geometry
- a follow-up quartet-node blame cut made that split explicit:
  on the bad `k4` replay for `(2,5)`, node `12` contributes about `56.7%` of
  the `Δmcy` term and node `9` about `36.7%`, while nodes `2` and `5` stay
  near `1e-16`; for `(3,6)`, node `10` contributes about `51.0%` and node
  `13` about `44.9%`, so the first bad torsion gate is being fed almost
  entirely by the opposite epithelial nodes rather than by the hot pair
  endpoints themselves
- tracing all live pair rows touching nodes `9`, `10`, `12`, and `13` pushes
  the miss one RK stage earlier without reopening the hidden-history story:
  ordinary pairwise contact/torsion rows already explain about `96.1%`,
  `96.7%`, `98.3%`, and `97.8%` of the bad `k3y` on those nodes, so the
  upstream drift is already in the normal epithelial pair-force loop rather
  than in the saved-ledger rebuild
- the dominant `k3` contributors are a small symmetric ring of
  `same_posca_pos`, `twoep==1`, `torsion_active==1`, `restored_only==0`
  interactions centered on cell-`1` nodes:
  the biggest rows are `(7,13)`, `(7,10)`, `(7,12)`, `(10,26)`, `(10,11)`,
  `(13,65)`, `(12,50)`, `(8,13)`, `(7,9)`, and `(10,27)`, while node `7`
  itself carries the largest opposite-sign stage drift
  (`Δk3y≈-7.02768e-13`, versus `+5.96745e-13` on node `10`,
  `+5.22693e-13` on node `13`, `+3.93852e-13` on node `12`, and
  `+2.56462e-13` on node `9`), so the next invagination parity cut should
  target that local epithelial ring around node `7` and its immediate
  mirrored partners rather than reopening restored-neighbor mechanics
- tracing node `7` directly tightens that cut one more step:
  about `95.8%` of node `7`'s bad `k3y` already comes from the four same-cell
  torsion rows `(7,13)`, `(7,10)`, `(7,12)`, and `(7,9)`, with only
  `O(1e-14)` residual from the rest of its neighborhood, so the remaining
  invagination miss is now narrow enough to treat as a single local epithelial
  ring replay rather than as a distributed whole-sheet instability
- filtered component traces change the interpretation of that ring:
  for node `7`, the bad `k3y` is dominated by the ordinary pair-force buckets,
  not by the explicit torsion bucket
  (`Δcontact_rep_y≈-6.26166e-13`, `Δcontact_adh_raw_y≈-4.70735e-14`,
  `Δtorsion_y≈-3.89551e-14`, `Δsurface_torsion_y≈9.18560e-15`,
  `Δtotal_y≈-7.02768e-13`), and the opposite nodes `9`, `10`, `12`, and `13`
  show the same pattern with `contact_rep_y` carrying the bulk of their bad
  `k3y`
- that same node-`7` ring is stable across the whole RK interior, not just the
  first bad `k3` sample:
  the same four same-cell rows `(7,10)`, `(7,13)`, `(7,12)`, and `(7,9)`
  dominate node `7`'s pair-force deltas at `k1`, `k2`, and `k3`, with the
  sign simply flipping at `k2`, so the next parity cut should stay on the
  `same_posca_pos -> lateral_distance(fd) -> force_scalar` path instead of
  treating the later `k4` torsion gate as the primary source
- the per-pair scalar confirms that reading:
  on those four `k3` rows, `deqe` stays exact while the whole force mismatch is
  driven by `fd` drifting by only about `1e-15` to `2.5e-15`, which then
  amplifies through the repulsive same-cell force scalar into `O(1e-13)` `fy`
  deltas; the next local diagnostic should therefore compare the node-`7` ring
  geometry entering `k1` at step `2379`, not patch the torsion threshold
- two direct fixes for that gate were also falsified and reverted:
  widening the torsion deadband globally, and widening it only for same-cell
  pairs, both close the one-step `2379 -> 2380` replay to roundoff but destroy
  the real `5802.dat` lane instead
  (`rtime`-targeted compare falls to `v2_getot=5501` with
  `max_position_error=0.15848030635578406` on the global cut and to
  `v2_getot=5480` with `max_position_error=0.16296805755848237` on the
  same-cell cut; the step-targeted compare drifts to `v2_rtime=10.622` with
  `max_position_error=0.058395314657247614` on the global cut and to
  `v2_rtime=10.6897` with `max_position_error=0.060952049607490545` on the
  same-cell cut), so the next parity cut should stay on the current mechanics
  baseline and find the upstream source of the epsilon-scale drift that pushes
  those two torsion pairs over the threshold
- a follow-up 2026-04-07 node-focused replay from the exact step-`2378`
  checkpoints with the carried current saved-neighbor ledger moved that source
  one outer step earlier:
  the bad step-`2379` visible state is fed mainly by the step-`2378` `k4`
  contact ring around nodes `9`, `10`, `12`, and `13`, not by a fresh
  restored-neighbor divergence inside step `2379`
- on that replay surface, the dominant y-force deltas are all ordinary
  `same_posca_pos`, `twoep==1`, `torsion_active==1`, `restored_only==0`
  epithelial contacts rather than restored-only topology:
  the largest cumulative per-pair `fy` misses are `(7,10)`, `(7,13)`,
  `(12,50)`, `(10,11)`, `(10,26)`, `(7,12)`, `(13,65)`, `(10,27)`, and
  `(7,9)`, while the resulting step-`2378` `k4y` deltas on nodes
  `9/10/12/13` are about `-2.60403e-13`, `-9.65616e-13`, `-6.80400e-13`, and
  `-7.22034e-13` respectively; that means the next parity cut should target
  this symmetric non-restored contact ring before reopening saved-ledger
  porting or patching the later `(2,5)` / `(3,6)` torsion gate again
- the quartet trace also shows that this upstream ring is driven more by the
  pair-vector y offset than by a fresh `mc` cancellation:
  for the worst step-`2378` `k4` pairs, the shared source-side y shift on node
  `7` is about `-1.53932e-15`, while the paired targets `9/10/12/13` pick up
  positive offsets of about `5.55e-16`, `1.77636e-15`, `1.22125e-15`, and
  `1.33227e-15`, so the next narrow cut should follow the upstream y evolution
  of the `7/8/11` neighborhood rather than revisiting the restored-neighbor
  port itself
- filtered component traces rule out one more tempting explanation for that
  ring:
  `same_side_neighbor_count` matches exactly between the bad replay and the
  oracle, and the node-`7` / `9` / `10` / `12` / `13` `k3y` drift is carried
  mainly by the ordinary pair-force buckets, especially `contact_rep_y`,
  rather than by the averaged `torsion_y` or `surface_torsion_y` terms
- the hot node-`7` rows also localize the geometry blame more sharply than the
  earlier quartet note:
  on `(7,13)`, `(7,10)`, `(7,12)`, and `(7,9)`, the force mismatch is a pure
  `fd = lateral_distance` miss with a stable same-cell repulsive coefficient of
  `100` and exact `deqe`; substituting current coordinates into the oracle
  geometry shows that the `fd` drift comes entirely from the source/target
  coordinates, while the paired opposite-side nodes contribute effectively `0`
- one direct algebra probe for that surface was falsified and reverted:
  recomputing `fd` from the explicit perpendicular vector norm in the hot
  same-cell `same_posca_pos` lane changed the individual `(7,*)` row deltas
  slightly but left the exact step-`2379 -> 2380` replay frozen at
  `max_position_error=0.0006032132978433213`, so the remaining miss is not
  just the operation order of the lateral-distance square root
- the stage-state trace confirms that this ring is already offset at the step
  `2379` entry surface:
  node `7` reaches `k1` with `Δx≈-1.13e-15` and `Δy≈+1.50e-15`, while nodes
  `9/10/12/13` already carry the matching opposite-sign y offsets; the sign
  flips at `k2`, flips back at `k3`, and grows at `k4`, so the next strict
  parity cut should follow the step-`2378 -> 2379` visible-state generation
- rebuilding the carried current saved-neighbor ledger at step `2378` and
  replaying `2378 -> 2379` from the stored current/oracle checkpoints confirms
  that this earlier surface is still only a roundoff-scale seed rather than a
  macroscopic miss:
  the exact replay closes at `max_position_error≈1.79124e-15` (node `7`), so
  step `2379` is still effectively exact even though the node-`7` ring already
  carries a tiny signed offset
- on that exact replay, the node-`7` / `9` / `10` / `12` / `13` y updates are
  a pure RK cancellation story:
  `k1`, `k2`, and `k3` alternate sign, but `k4` is the largest single term on
  every hot node
  (for node `7`, the weighted contributions are about
  `k1=-5.30e-16`, `k2=+9.51e-16`, `k3=-7.67e-16`, `k4=+1.05e-15`, yielding a
  net `Δy≈+7.09e-16`; for node `10`, they are about
  `k1=+5.26e-16`, `k2=-8.18e-16`, `k3=+6.68e-16`, `k4=-8.50e-16`)
- the same component split still holds one outer step earlier:
  the bad `k4y` on that replay is dominated by `contact_rep_y`, not by the
  averaged torsion buckets
  (node `7`: `Δcontact_rep_y≈+9.13047e-13` versus
  `Δtorsion_y≈+5.98632e-14`; node `10`: `Δcontact_rep_y≈-7.36300e-13` versus
  `Δtorsion_y≈-5.09037e-14`), so the next narrow cut should target the
  step-`2378` node-`7` ring `k3 -> k4` stage-state geometry feeding the
  repulsive same-cell `fd` term rather than reopening saved-neighbor history
- reading the stage input coordinates directly from that exact replay tightens
  the geometry target again:
  at the hot `k4` input, node `7` carries the largest single y shift
  (`Δy≈-1.65737e-15`), while the paired targets contribute smaller
  opposite-sign offsets
  (`node 9≈+8.88e-16`, `10≈+1.55431e-15`, `12≈+1.11022e-15`,
  `13≈+1.44329e-15`), and the resulting `pair_dy` drift on
  `(7,9)/(7,10)/(7,12)/(7,13)` is about
  `+2.44249e-15`, `+3.10862e-15`, `+2.66454e-15`, and `+2.99760e-15`
  respectively, while `Δmcy` stays smaller, so this surface is still driven
  mainly by the pair-vector y offset rather than by a fresh `mc`
  cancellation
- the source of that hot `k4` input offset is also now explicit:
  for node `7`, the step-`2378 -> 2379` `k4` input `Δy` is dominated by the
  full `k3` stage contribution (`≈-2.29959e-15`), with only partial
  cancellation from the carried visible-state seed and the half-step
  `k1/k2` terms
  (`Δy_in≈+8.05e-16`, `Δ(k1/2)≈-1.58912e-15`, `Δ(k2/2)≈+1.42587e-15`,
  `Δk3≈-2.29959e-15`); nodes `10`, `12`, and `13` show the same pattern with
  positive `k3` contributions dominating their `k4` input shifts, so the next
  strict parity cut should target the step-`2378` node-`7` ring `k3` pair
  forces that feed the `k4` repulsive `fd` miss
- that earlier `k3` surface is now narrow enough to treat exactly like the
  later node-`7` ring cut:
  on the exact `2378 -> 2379` replay, ordinary pair rows already explain about
  `95.5%` of node `7`'s bad `k3y`, `97.9%` of node `9`'s, `97.4%` of
  node `10`'s, `96.8%` of node `12`'s, and `97.1%` of node `13`'s, with the
  same same-cell rows `(7,10)`, `(7,13)`, `(7,12)`, and `(7,9)` still the
  dominant node-`7` contributors
  (`≈-1.09246e-13`, `-9.76996e-14`, `-7.63833e-14`, and `-6.57252e-14`
  respectively), so the next strict parity cut should target those four
  step-`2378` `k3` pair forces directly rather than reopening the wider ring
  or looking for a fresh intra-step branch
- rerunning that exact `2378 -> 2379` replay on the restored post-bisect
  benchmark branch confirms that the local seed did not move when the March
  invagination lane was restored:
  the replay still closes at `max_position_error=2.5510982866352577e-15`, and
  the upstream `7/8/11` neighborhood still shows alternating-sign RK y deltas
  dominated by `contact_rep_y` rather than by the averaged torsion buckets
  (node `8`: `Δk2y≈+2.14943e-13`, `Δk3y≈-7.99742e-14`,
  `Δk4y≈+2.18010e-13`; node `11`: `Δk2y≈+2.42195e-13`,
  `Δk3y≈-2.06835e-13`, `Δk4y≈+5.37979e-13`)
- that restored replay also shows node `8` is not merely echoing the old
  node-`7` same-cell quartet:
  at `k2/k3/k4`, the dominant source rows are `(8,13)`, `(8,96)`, `(8,9)`,
  and `(8,81)`, all ordinary `same_posca_pos`, `twoep==1`,
  `torsion_active==1` contacts; together they explain about `95.2%` of node
  `8`'s bad `k2 contact_rep_y`, about `80.0%` of its `k3`, and about `85.4%`
  of its `k4`, with the same-cell rows `(8,13)` and `(8,9)` overlapping the
  node-`7` ring and the cross-cell rows `(8,96)` and `(8,81)` extending that
  basin into adjacent cells `7` and `6`
- node `11` carries a second spoke on the same restored replay:
  `(11,51)` is the dominant pair row at `k2/k3/k4`,
  `(11,12)` is the leading same-cell companion row, and `(11,41)` / `(11,36)`
  are the next visible secondaries, again all in the ordinary
  `same_posca_pos`, `twoep==1`, `torsion_active==1` lane; that means the
  remaining epsilon-scale seed is better described as a coupled
  `7/8/11` neighborhood on cell `1` plus adjacent cells `4/6/7`, so the next
  strict parity cut should follow those exact rows alongside the older
  `(7,10)`, `(7,13)`, `(7,12)`, and `(7,9)` quartet rather than reopening the
  restored-neighbor port or patching the later torsion gate
- reading the legacy Fortran directly narrows the active mechanics path:
  the invagination preset takes `neighbor_build ->
  neighbor_build_simpleneigh_inter_other_side_epi -> restore_neighbors ->
  iterdiferencial -> forces (k1/delta) -> nexe_gradual -> rungekutta4 ->
  forces_calculating_distances (k2-k4)`, with `ffu(27)=0`, so the remaining
  miss is not hiding in adaptive stepping, the `*_pola` lane, or the
  `complexneigh` / `sqrt(2)` neighbor builder
- that also closes several grounded false leads:
  forcing live `add/eqd` cutoffs into `k2-k4` reproduces the old catastrophic
  `5518 / 10.0015 / 0.23688182500980381` full-lane signature while leaving the
  exact `2379 -> 2380` replay unchanged at
  `max_position_error=0.0006032132978433213`, so the remaining miss is not a
  plain "edge-valued versus live-valued cutoff" bug in the RK interior
- the literal `complexneigh`-style epithelial reach is also a dead end in the
  current basin:
  widening the current builder toward the legacy `sqrt(2)` neighborhood
  surface drops the exact replay delta to `0.001` immediately and blows the
  exact `2378 -> 2379` replay out to `max_position_error≈8.76133e-3`, so the
  near-oracle branch is not missing that wider same-face interaction surface
- the simpler boxing fudge from the real
  `neighbor_build_simpleneigh_inter_other_side_epi` path,
  `urv = 1 / (rv + 1e-3)`, is effectively neutral on the exact replay:
  `2378 -> 2379` still closes at `2.5510982866352577e-15`, and
  `2379 -> 2380` stays at `0.0006032132978433213`
- with the hot `twoep==1` / torsion formulas now line-by-line checked against
  `biomechanic.mod.f90`, the strongest remaining suspect is upstream
  geometry/order feeding those rows inside step `2378` `k2-k4`, not the local
  pair-force algebra itself; the next strict cut should stay on the
  `7/8/11` ring input state and neighborhood enumeration surface
- replaying the exact nested Fortran `restore_neighbors` loops against the hot
  step-`2379` state does not reveal a hidden semantic gap in the current port:
  the literal `neighboring.mod.f90` recovery algorithm and the current
  `should_skip_restored_neighbor` port produce identical restored neighbor
  lists and identical order for every node on that step, including the hot
  `7/8/11` basin
- the first bad `2379 -> 2380` step is also no longer a live-neighborhood
  topology problem:
  rebuilding the current-neighbor lists from the exact step-`2379` current and
  oracle states yields identical neighbor sets and identical order globally,
  not just on nodes `7`, `8`, and `11`; combined with the exact
  `2378 -> 2379` replay, that means the remaining cliff is now best described
  as pure intra-step stage-state geometry drift through the same topology and
  the same pair iteration order, not a hidden restore-neighbor or box-order
  mismatch at the first bad step
- replaying the exact step-`2379` restart with the alternate
  `invagination_v2_saved_neighbors_restart_from2379.txt` ledger closes the
  last order-only restore branch on that cliff:
  the one-step miss stays exactly at
  `max_position_error=0.0006032132978433213`, with only roundoff-scale drift
  from `invagination_v2_state_current_step2380_fresh.txt`, so the hidden
  saved-ledger order at step `2379` is not the live driver either
- the remaining hot `7/8/11` ring is not a restore-payload bug:
  filtered pair traces on the exact step-`2378` replay show every dominant
  row in that basin has `restored_only=0`, with live
  `edge_add=reverse_edge_add=0.55` and
  `edge_eqd=reverse_edge_eqd=0.35`; the bad rows are ordinary current-build
  `same_posca_pos`, `twoep==1`, `torsion_active==1` contacts, not zero-payload
  restored edges
- I added per-pair raw torsion diagnostics to the live trace surface
  (`source_torsion_y_raw`, `target_torsion_y_raw`,
  `source_surface_torsion_y_raw`, `target_surface_torsion_y_raw`) so the hot
  pair rows can now be bridged directly back into the node-level averaged
  `torsion_y` buckets without changing mechanics
- that new bridge confirms the exact step-`2379` `k4` miss on node `7` is
  still dominated by direct pair repulsion, not by torsion:
  `Δtotal_y≈-1.90934e-12`,
  `Δcontact_rep_y≈-1.68665e-12`,
  `Δtorsion_y≈-1.12281e-13`, and
  `Δsurface_torsion_y≈+2.43185e-14`, while the four same-cell rows
  `(7,10)`, `(7,13)`, `(7,12)`, and `(7,9)` alone contribute
  `ΣΔfy≈-1.77902e-12`; their averaged raw torsion contribution is only
  `ΣΔsource_torsion_y_raw / 12 ≈ -4.44459e-14`
- the worst single row on that exact step-`2379` replay is still `k4 (7,10)`,
  and the new trace narrows its mechanism further:
  `Δfy≈-5.46230e-13` is almost entirely a scalar drift
  (`Δforce_scalar≈-6.76792e-13`, projected contribution
  `≈-5.53402e-13`), not a direction drift
  (`Δuvy≈-8.88178e-16`, contribution `≈+7.25426e-15`);
  the underlying geometry change is only
  `Δfd≈-6.77236e-15`, so the live search space is now the
  same-cell `fd/lateral_distance` path for those hot rows rather than the
  torsion or `uvy` branches
- reconstructing the cumulative RK stage state for step `2379` tightens the
  source of that `fd` drift:
  node `7`'s bad `k4` state carries `Δy≈+3.27382e-15`, node `10` carries
  `Δy≈-2.69041e-15`, and the shared opposite node `0` only moves by
  `≈-2.58917e-16`; for node `7`, that `k4` state offset is dominated by the
  carried `δ * Δk3y≈+4.41793e-15` term after partial cancellation from
  `0.5δ * Δk1y≈+2.83048e-15` and
  `0.5δ * Δk2y≈-2.47765e-15`
- stepping one layer earlier shows the same mechanism is already live on the
  exact `2378 -> 2379` replay:
  node `7`'s `k3` bucket mismatch is
  `Δtotal_y≈+3.98219e-13`, with
  `Δcontact_rep_y≈+3.49054e-13`,
  `Δtorsion_y≈+2.71635e-14`, and
  `Δsurface_torsion_y≈-7.39917e-15`; the same four-row quartet contributes
  `ΣΔfy≈+3.72147e-13`, while its averaged raw torsion contribution is only
  `≈+1.10652e-14`
- that means the remaining invagination miss is no longer best framed as a
  vague "torsion epsilon" problem:
  it is a persistent same-cell quartet `fd -> force_scalar -> contact_rep_y`
  drift on the `7/8/11` ring, seeded one step earlier in `k3` and amplified
  on step `2379` `k4` through node-`7` and target-node stage-state y
  cancellation
- the legacy Fortran `rungekutta4` implementation is now checked directly
  against the C++ port, and it does use the same cumulative stage-state
  sequence (`x += 0.5d*k1`, then `+= 0.5d*k2`, then `+= d*k3`) before the
  final `1/6 * (k1 + 2k2 + 2k3 + k4)` update, so the remaining stage-state
  drift is not coming from a hidden "standard RK4 versus cumulative RK4"
  mismatch
- a strict floating-point build is also a dead end at the first bad step:
  rebuilding `em2_legacy_invagination_summary` with `-ffp-contract=off`
  leaves the exact `2379 -> 2380` replay unchanged at
  `max_position_error=0.0006032132978433672`, effectively identical to the
  current `0.0006032132978433213`, so fused contraction is not the missing
  lever either
- a disposable legacy-Fortran trace run under
  `/tmp/em2-legacy-trace/EmbryoMaker` finally exposed the live benchmark path
  directly:
  logging every force row for `getot in {2378,2379,2380}` produced
  `50148` rows in `debug_pairs_2379.txt`, no `_pola` dump at all, and equal
  stage buckets `0/2/3/4` (`12537` rows each), so this preset is definitely on
  plain `biomechanic.mod.f90`, not the polarity branch, and it does execute
  the same `k1 + RK(k2-k4)` force surfaces we have been assuming
- joining those legacy rows against the v2 pair traces confirms the hot-pair
  force algebra is already close:
  on the exact legacy `2379/k4` hot rows the v2 current/oracle traces differ
  from the legacy full-run rows mainly through small geometry drifts
  (`Δdistance≈2.4e-5`, `Δfd≈2.4e-5`, `Δforce_scalar≈2.4e-3` on node-`7`
  quartet rows), while the midpoint geometry terms stay tight
  (`Δposca≈1.5e-5`, `Δdotp≈1.9e-5`), so the bridge back to legacy again points
  at upstream stage-state generation rather than a bad local force formula
- that same legacy dump also reopens the pair-order branch, but now against
  real legacy data rather than restart-to-restart comparisons:
  after filtering the v2 full-node traces down to `interacts==1`, the current
  source still rebuilds the hot source-node interaction order differently from
  legacy on the first bad step
  `2379/k4`:
  legacy node `8`
  `[52,67,13,37,12,14,11,82,9,28,10,97]`
  versus v2
  `[52,13,67,12,37,11,14,9,82,10,28,97]`;
  legacy node `9`
  `[66,81,78,96,98,13,14,11,82,10,97]`
  versus v2
  `[66,78,81,96,98,13,11,14,82,10,97]`;
  legacy node `12`
  `[53,51,42,36,27,52,13,37,14]`
  versus v2
  `[53,51,36,42,27,52,13,37,14]`
- the seed is already visible one step earlier on the hot quartet:
  for legacy node `8` on `2378/k3`, the interacting hot-subset order is
  `[13,14,11,10]`, while both current and oracle v2 restarts still use
  `[13,11,14,10]`
- the concrete source-level reason is now clear from `neighboring.mod.f90`:
  legacy `iniboxes_p` inserts each node at the head of a per-box linked list
  (`list(i)=boxes(ii,jj,kk); boxes(ii,jj,kk)=i`), so scanning `ie=list(ie)`
  visits nodes within each box in reverse insertion order; the current C++
  builder stores per-box vectors in insertion order and walks them forward
- a direct reverse-per-box C++ experiment proves that this order surface is
  real but not sufficient on its own:
  reversing each per-box traversal makes the v2 interacting order match the
  legacy dump exactly on hot nodes `8/9/12`, and it improves the exact
  `2379 -> 2380` replay from
  `max_position_error≈0.0006032133`
  down to
  `0.0005435141902303542`,
  but it destroys the real benchmark lane, collapsing the full compare to
  `v2_getot=5372`, `v2_rtime=10.0015`,
  `max_position_error=0.2142715406859064`; that blunt patch was reverted
- forcing a clean rebuild of the repo-local `kernel/build` directory also
  uncovered a bigger problem:
  the historical near-miss
  (`v2_getot=5819`, `max_position_error≈0.0023666`)
  had been coming from the stale cached March binary under the old workspace
  path, not from a fresh build of the checked-in current source;
  after recreating `kernel/build` from the live repo path, the clean-source
  benchmark lane now reproduces much worse at
  `v2_getot=5521`, `v2_rtime=10.0016`,
  `max_position_error=0.23723760444924083`,
  even though the exact `2379 -> 2380` replay on that same clean rebuild stays
  at `0.0005435141902303542`
- that means the next invagination task is now bifurcated:
  first, recover the clean-source regression window between the stale March
  binary and the checked-in current source; second, once the benchmark lane is
  back in the old `≈0.00237` basin, continue the legacy-guided pair-order work
  on the hot `8/9/12` neighborhood instead of the torsion algebra

That means the first v2 invagination slice should target epithelial mechanics
and polarity on a fixed-topology sheet before division, death, or ECM surfaces.
