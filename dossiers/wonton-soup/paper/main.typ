#import "../../../addenda/typst-field-manual/specter-paper.typ": author, paper
#import "../../../addenda/typst-field-manual/tokens.typ": tokens

#paper(
  title: "Proto-Cognitive Signatures in Distributed MCTS Theorem Proving",
  subtitle: "A TAME-style perturbation assay for same-goal, variable-means proof search",
  note: "SPECTER LABS PREPRINT",
  authors: (
    author("Ludwig Pouey", affiliation: "Specter Labs"),
  ),
  date: "April 2026",
  keywords: (
    "distributed theorem proving",
    "MCTS",
    "collective intelligence",
    "proto-cognition",
    "TAME",
    "proof graphs",
  ),
  abstract: [
    We study a distributed Monte Carlo tree search theorem prover in which multiple
    local controllers coordinate over a shared frontier, and ask whether targeted
    perturbations reveal bounded proto-cognitive signatures in proof search. Guided by
    Levin's Technological Approach to Mind Everywhere (TAME), we treat mentalistic
    language as an operational research stance rather than a metaphysical claim: the
    question is whether it improves prediction, intervention, and structural
    explanation @levin2022tame @levin2026mind2. We lesion solved proof trajectories by
    blocking tactic families and by perturbing scheduler decisions, then rerun under
    matched budgets with LLM tactic providers. The primary analysis conditions on
    baseline-solved theorem-runs, with a stricter null-stable subset to separate true
    lesion effects from provider stochasticity. We compare proof outcomes using
    proof-family labels, graph edit distance over goal- and tactic-labeled proof
    graphs, trajectory divergence and recovery metrics, and explicit basin analysis
    across repeated runs. The central claim is narrow: under perturbation, some
    theorem-runs preserve goal reachability by rerouting through structurally distinct
    proof families. Whether this resilience correlates with proof-basin width remains
    open. This makes distributed theorem proving a useful assay for intervention-defined
    proto-cognitive signatures in a non-biological search system.
  ],
)[

= Introduction

Formal theorem proving is a useful setting for perturbation science because the goal
state is explicit, the search trajectory is inspectable, and intervention points are
controllable. Unlike many open-ended agent benchmarks, proof search lets us ask a
precise question: when a successful trajectory is damaged, does the system fail
outright, reproduce the same proof family, or preserve competence by reaching the
same theorem through different means?

This paper studies that question in a distributed Monte Carlo tree search system in
which multiple local controllers coordinate over a shared frontier. The distributed
layer is not introduced as a generic performance booster. Instead, it is treated as a
collective-intelligence perturbation mechanism: by changing which local decisions can
be taken, when they can be taken, and how information is routed across the frontier,
we can probe how flexible the higher-level search process really is
@levin2024collective @levin2025chess.

The conceptual lens comes from Michael Levin's TAME program, which argues that
cognitive and teleological vocabulary should be evaluated by empirical leverage rather
than by metaphysical comfort. On that view, the relevant signature is not surface
resemblance to humans, but flexible navigation in a problem space: the ability to
reach a fixed goal by variable means under changing conditions
@levin2022tame @levin2025cognition @levin2026mind2.

Our claim is deliberately bounded. We do not argue that theorem provers are conscious,
sentient, or biologically equivalent. We ask instead whether intervention-response
signatures in this system support a limited proto-cognitive interpretation: that some
distributed proof-search processes maintain or regain goal-directed competence under
perturbation by shifting to alternative proof-graph pathways.

This paper makes three concrete contributions. First, it defines a lesion-based
framework for theorem proving that distinguishes `replicate`, `reroute`, and
`collapse` responses on baseline-solved theorem-runs. Second, it combines proof-graph
families, graph edit distance, trajectory divergence, and basin analysis into a single
structural assay for rerouting. Third, it uses that assay to test a TAME-style
hypothesis: theorem-runs with broader proof basins should be more likely to preserve
goal reachability after perturbation.

= TAME Framing And Research Questions

Levin's framing is useful here because it keeps the paper disciplined. TAME treats
agency language as a hypothesis about fruitful interaction protocols: if talking about
a system as goal-directed improves prediction, intervention, or synthetic control,
then that language has earned provisional scientific use @levin2022tame
@levin2026mind1 @levin2026mind2. The theorem-proving system gives us an unusually
clean environment in which to test that stance, because the objective is crisp and the
space of interventions is programmable.

For this paper, the key TAME motif is William James' formulation of intelligence as a
fixed goal pursued by variable means. In proof search, the theorem is the fixed goal,
while tactic choices, subtree expansions, controller allocations, and proof-graph
families provide the variable means. A lesion experiment becomes informative when it
forces the system to reveal whether the goal was reachable only through a narrow
channel or through a broader basin of alternatives.

The paper therefore revolves around four operational questions.

*Question 1.* When an intervention is applied to a solved theorem-run, how often does
the system replicate the original proof family, reroute to a distinct family, or
collapse?

*Question 2.* When reroutes occur, are they structurally real rather than superficial
label noise? The answer should show up in proof-graph edit distance, novel-goal
counts, and trajectory divergence.

*Question 3.* Does theorem-level basin structure predict lesion resilience? If broader
proof basins support rerouting, that is the strongest bridge from the data to a
proto-cognitive reading.

*Question 4.* Does perturbing the distributed scheduler measurably reshape controller
behavior even when theorem-level outcomes are buffered? This matters because the
distributed layer should count as a genuine intervention surface, not merely as a
different implementation detail.

These questions are falsifiable, and they also define the paper's limits. If lesions
mostly produce collapse, if reroutes fail to show structural divergence, or if basin
structure does not predict resilience, then the proto-cognitive interpretation should
be weakened accordingly.

= System And Perturbation Design

The experimental system is a distributed theorem prover built around Monte Carlo tree
search with LLM-backed tactic proposal. Multiple local controllers operate over a
shared frontier, so theorem proving unfolds as a coupled search process rather than as
a single monolithic rollout. Each node sees partial tree state; the collective
achieves proofs no single node could construct alone. This makes the system a useful
testbed for collective competence: local units can be individually limited while the
aggregate process exhibits higher-level structure.

The perturbation program has two main arms. The first arm performs *path lesions*:
once a control run solves a theorem, the system blocks a tactic or tactic family that
lies on the solved path and reruns under matched budgets. The second arm performs
*scheduler lesions*: block, delay, or reroute schedules alter which controller can act
or when an expansion can proceed. The two arms target different levels of the system.
Path lesions probe proof-space substitutability, while scheduler lesions probe the
coordination layer itself.

All comparisons in the main lesion analysis should be conditioned on theorem-runs that
the baseline solves. This is not a bookkeeping detail; it is part of the design.
Theorems that fail in both the control and intervention conditions do not inform the
question of lesion-induced rerouting, because they provide no evidence that the system
had usable goal reachability to begin with. For stochastic tactic providers, a
stricter null-stable subset should also be reported, requiring the matched
`control_null` rerun to solve. Rescue cases, where the intervention solves and the
baseline does not, are worth analyzing, but they belong in a separate bucket.

#figure(
  image("../docs/figures/out/fig2-protocol.pdf", width: 100%),
  caption: [
    Experimental protocol. Wild-type runs identify solved paths, intervention runs
    lesion specific tactics or matched controls under fixed budgets, and downstream
    analysis compares the resulting proof trajectories structurally.
  ],
)

= Metrics, Inclusion Rules, And Proof Families

The paper should define the denominator before it defines the effect sizes. The main
analysis population is the set of intervention rows for which `baseline_solved =
true`. A stricter robustness view additionally requires `control_null = solved` for
the same theorem-run so that provider stochasticity is not mistaken for lesion
collapse. Reporting both views side by side will keep the paper honest, especially if
null instability differs materially by provider.

Outcome labels are coarse but useful. `replicate` means the intervention reaches the
same proof-family label as the control. `reroute` means the intervention still solves
the theorem but lands in a distinct proof-family. `collapse` means the lesion destroys
goal reachability within the matched budget. Rescue cases should be reported
separately because they represent search regularization rather than damage.

The structural layer of the analysis should make reroutes earn their name. Proof
families are defined over proof graphs whose nodes are labeled by goal signatures and
tactic families. Graph edit distance provides a coarse family-distance measure,
trajectory divergence captures temporal separation from the control path, and recovery
metrics quantify whether the system converges back toward the control family or
stabilizes elsewhere. These measures allow the paper to distinguish a genuine
alternative route from superficial replay noise.

Basin analysis sits one level higher. Repeated control runs on the same theorem define
an empirical distribution over proof families, from which we can estimate support
counts, entropy, dominant-family mass, and other basin-width summaries. The guiding
hypothesis is simple: theorem-runs with wider basins should be more resilient to
lesion because they have more accessible structural alternatives.

#table(
  columns: (1.3fr, 2.3fr),
  table.header([Element], [What this section must lock down]),
  [Main denominator], [Only theorem-runs with `baseline_solved = true` contribute to the main lesion story.],
  [Stricter subset], [Also report the null-stable slice where the matched `control_null` run solves.],
  [Rescue handling], [Track `baseline_fail / intervention_solve` as a separate regularization phenomenon.],
  [Structural metrics], [Define proof-family labels, GED, trajectory divergence, recovery, and basin-width measures.],
)

= Results

== Replicate, Reroute, And Collapse

The main denominator contains 5,161 intervention rows across 340 runs, restricted to
theorem-runs where the baseline solves. Of these, 1,754 preserve goal reachability
under lesion (34.0%) while 3,407 collapse. The distribution across providers is
uneven: DeepSeek contributes 536 solved and 969 collapsed (35.6% recovery), heuristic
25 solved and 28 collapsed (47.2%), and reprover 1,193 solved and 2,410 collapsed
(33.1%).

Provider-specific null instability is sharply asymmetric. DeepSeek solves 72.0% of
matched `control_null` reruns, while heuristic solves 100% and reprover 99.9%. This
asymmetry means the strict denominator---requiring both baseline and control-null to
solve---is substantially tighter for DeepSeek than for the other providers. Rescue
cases, where the intervention solves but the baseline does not, are excluded from the
main denominator and reported separately in Appendix C.

#figure(
  image("artifacts/fig17-followup-provider-splits.svg", width: 100%),
  caption: [
    Lesion outcomes from the shared lake across 340 runs. Right: the strict main-text
    denominator restricted to `baseline_solved = true` rows whose matched `control_null`
    rerun also solves. Left: rows excluded from that denominator, split into rescue
    cases and null-unstable spillover.
  ],
)

== Structural Reality Of Reroutes

In the strict denominator, 1,250 intervention rows solve after lesion while both
baseline and control-null also solve. Of these, 602 (48%) are explicit reroutes under
the hash-mismatch criterion---the intervention produces a structurally distinct proof
family from the control. Structural drift extends beyond that coarse label: 730 of the
1,250 solved strict-denominator rows (58%) have non-zero normalized search-graph edit
distance. The mean normalized GED is 0.405 and the maximum is 1.091. Structural
divergence is therefore the norm rather than the exception when goal reachability
survives.

Tactic-family heterogeneity produces a quantifiable hierarchy from redundant
scaffolding to irreplaceable chokepoints:

#figure(
  table(
    columns: (1.2fr, 0.8fr, 0.6fr, 1.4fr),
    table.header([Intervention], [Total], [Recovery], [Classification]),
    [`block_push_neg`], [61], [100.0%], [Redundant scaffolding],
    [`block_left`], [66], [93.9%], [Highly substitutable],
    [`block_intros`], [394], [61.2%], [Moderately recoverable],
    [`block_apply`], [73], [53.4%], [Mixed],
    [`block_intro`], [592], [27.0%], [Somewhat essential],
    [`block_rw`], [482], [22.4%], [Essential],
    [`block_linarith`], [380], [10.3%], [Critical],
    [`block_cases`], [136], [6.6%], [Chokepoint],
    [`block_dsimp`], [99], [2.0%], [Irreplaceable],
  ),
  caption: [
    Tactic family recovery rates from the main denominator. Blocking `push_neg` never
    collapses search; blocking `dsimp` almost always does. The hierarchy spans from
    redundant scaffolding (100% recovery) to irreplaceable chokepoints (2% recovery).
  ],
)

Entry tactics like `intro` and `intros` show divergent behavior: `intros` (plural,
handling multiple binders) recovers at 61.2%, while `intro` (singular) recovers at
only 27.0%. Terminal tactics and specialized closers (`dsimp`, `linarith`, `cases`)
cluster at the chokepoint end. The taxonomy matters because it predicts which lesions
will collapse search versus which merely force rerouting.

Reroutes explore genuinely novel territory. Compared to replicates, reroutes visit
more novel goals (0.48 vs 0.33 on average) and show higher solution-path distance from
the wild-type trajectory (0.198 vs 0.136). Despite this exploration, reroutes remain
efficient: 2.94 average iterations versus 3.08 for replicates. The system discovers
alternative paths through the proof space without additional search cost.

#figure(
  image("artifacts/fig16-ged-bimodality.svg", width: 100%),
  caption: [
    Normalized search-graph edit distance among solved strict-denominator rows. Of
    1,250 solved rows, 602 are explicit reroutes (hash mismatch) and 730 show non-zero
    structural drift.
  ],
)

== Basin Width And Lesion Resilience

The basin dataset contains 2,472 runs across 1,941 theorems, with unique-structure
counts ranging from 0 to 9. Joining this to the intervention data yields 78 theorems
with both basin and lesion outcomes. Preliminary stratification by basin width does not
show a clear positive correlation: theorems with unique-structure counts in the 0--1
range show 51.7% recovery (52 theorems), while those with counts above 3 show 27.7%
recovery (11 theorems). The remaining buckets fall between 13% and 20%.

// TODO(basin-width): The multibasin hypothesis is UNTESTED. Current slice has no
// variance (unique_structures clusters at 0-1). Experiment plan ready:
//
// Curated theorems: experiments/basin_width_curated_v1.json (306 theorems)
//   - 27 theorems with basin_width >= 2 in existing data
//   - Theorems with 80%+ reroute rate (known multi-proof)
//   - Theorems solved by 2+ providers
//   - Domains: AEMeasurable (avg 4.32), Action (4.29), AbsoluteValue (3.43)
//
// Run script: scripts/basin_width_experiment_v1.sh
//   Phase 1: Build corpus from curated theorems
//   Phase 2: 20-seed basin sweeps (measure unique_structures variance)
//   Phase 3: Lesion interventions on same theorems
//   Phase 4: Fit correlation basin_width vs recovery_rate
//
// Expected runtime: ~6 hours on quietbox (306 theorems x 20 seeds + interventions)

#block(fill: rgb("#fff3cd"), inset: 1em, radius: 4pt)[
  *DRAFT GAP: Basin-width hypothesis untested.* Current data clusters at
  unique-structure counts 0--1. Need targeted runs on theorems with known multi-proof
  structure before this section can make a claim.
]

#figure(
  image("artifacts/fig18-followup-basins.svg", width: 100%),
  caption: [
    Basin width vs. lesion recovery across 78 theorems. Data clusters at low
    unique-structure counts; hypothesis untested.
  ],
)

== Scheduler Perturbations And Controller-Level Effects

Scheduler lesions perturb the coordination layer rather than individual proof tactics.
The shared lake contains 14 scheduler-damage runs, primarily on reprover with
damage-block conditions at blocking fractions 0.1, 0.3, and 0.5. On the March 2026
scheduler matrix, recovery rates show a dose-response pattern: 14.0% at f=0.1 (7/50
interventions), 10.4% at f=0.3 (7/67), and 10.6% at f=0.5 (7/66). Higher blocking
fractions slightly reduce recovery, consistent with the intuition that more aggressive
scheduler damage leaves fewer coordination paths available.

Earlier February 2026 runs on a different corpus show higher recovery rates around 20%
for similar damage conditions. The corpus difference prevents direct comparison, but
both datasets confirm that the distributed scheduler is a genuine intervention surface.
Blocking or delaying controller actions changes theorem-level outcomes, not merely
internal coordination statistics. This supports the claim that the distributed layer
contributes meaningfully to collective competence rather than serving only as a
parallelization wrapper.

= Discussion, Limits, And TAME Interpretation

The central finding is that distributed proof search preserves goal reachability under
perturbation through structurally distinct paths. Across 340 runs, 34% of lesioned
theorem-runs still solve, and 48% of those solves are explicit reroutes with distinct
proof-family hashes. The remaining solved rows show non-zero structural drift in 58% of
cases. This is not superficial label noise: the system reaches the same theorem through
measurably different proof graphs when the original path is blocked.

Rerouting is efficient. Collapsed runs average 6.7 iterations with 1.7 backtracks and
2.9 unique goals visited; solved runs average 3.0 iterations with 0.1 backtracks and
2.1 unique goals. Collapsed search explores more broadly but fails. Among solved runs,
replicates and reroutes show nearly identical cost: 2.8 vs 2.9 iterations. The system
finds alternative paths without additional search overhead.

This pattern meets the threshold for a TAME-style proto-cognitive signature: flexible
goal pursuit under changing conditions @levin2022tame @levin2026mind2. The relevant
criterion is not resemblance to biological cognition but the ability to reach a fixed
goal by variable means. Distributed theorem proving exhibits this structure. The
proto-cognitive label names a bounded intervention-response pattern that improves
structural explanation.

The limits are equally clear. The basin-width hypothesis is untested (see Section 5.3).
Scheduler perturbations confirm the distributed layer as a genuine intervention
surface, though the dose-response effect is modest. Cross-assistant (Lean--Rocq)
results are incomplete.

What would weaken the claim? If broader corpora show that reroutes disappear under
tighter controls, if structural drift collapses to noise, or if scheduler damage
produces no theorem-level effects, then the proto-cognitive reading should be revised
downward. The paper stakes a narrow claim on intervention-defined flexibility; that
claim holds on the current data but remains falsifiable.

= Reproducibility

Every number in this paper traces to the shared runtime lake on `quietbox` at
`/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb` (6.9 GB, 340 runs,
21,044 intervention rows). The figure-generation script queries this lake directly and
produces the SVG figures embedded in the paper.

To regenerate figures and compile the paper:

```bash
# Sync the shared lake locally (optional, ~7 GB transfer)
rsync -avP quietbox:/shared/specter-runtime/wonton-soup/artifacts/lake/lake.duckdb \
  /local/path/to/lake.duckdb

# Generate figures from the synced lake
cd /path/to/research-registry/dossiers/wonton-soup
LAKE_DB_PATH=/local/path/to/lake.duckdb \
uv run python paper/build_figures.py --out-dir paper/artifacts

# Compile the paper
typst compile --root ../.. paper/main.typ paper/artifacts/main.pdf \
  --font-path ../../addenda/typst-field-manual/assets/fonts
```

The lake schema and extraction logic are documented in `docs/ops/run-lake.md` and
`analysis/lake/`. Raw run logs reside on `quietbox` under
`/shared/specter-runtime/wonton-soup/logs/`.

#pagebreak()

= Appendix

== Appendix A: Cohort Definitions

*Main denominator.* A theorem-intervention row belongs to the main denominator if
`baseline_solved = true`. This restricts analysis to cases where the unperturbed system
solves the theorem, ensuring that collapse or reroute reflects lesion effects rather
than baseline failure.

*Strict denominator.* A subset of the main denominator additionally requires that the
matched `control_null` rerun solves. This filters out provider stochasticity: if the
system cannot reliably solve the theorem even without lesion, observed failures may
reflect noise rather than damage.

*Rescue bucket.* Rows where `baseline_solved = false` and `intervention_solved = true`
represent regularization effects---the lesion improves search rather than damaging it.
These are excluded from the main analysis and reported separately.

*Provider filters.* The main analysis includes DeepSeek, heuristic, and reprover
providers on the Lean backend in research mode. Coq and other backends are excluded.
Runs with partial results or incomplete status are filtered out.

== Appendix B: Lesion Taxonomy

*Entry tactics:* `intro`, `intros` --- appear at proof openings; blocking forces
alternative entry points.

*Terminal tactics:* `rfl`, `trivial`, `decide` --- appear at proof leaves; blocking
tends to collapse search unless equivalent terminals exist.

*Rewriting tactics:* `rw`, `simp`, `simp_all`, `simpa` --- occupy middle positions;
show intermediate recoverability.

*Numeric tactics:* `norm_num`, `omega`, `linarith`, `ring` --- domain-specific
closers; blocking collapses search for numeric goals.

*Control flow:* `constructor`, `exfalso`, `contradiction`, `assumption`, `cases`,
`apply`, `exact`, `ext` --- structural tactics with varied recoverability.

*Scheduler perturbations:* `damage-block-f{0.1,0.3,0.5}` --- block a fraction of
scheduler actions; `damage-delay` --- introduce random delays in controller
coordination.

== Appendix C: Rescue Cases And Search Regularization

Rescue cases---where the baseline fails but the intervention solves---total 785 rows
across all intervention types. This is not noise: blocking certain tactics reliably
improves search by pruning unproductive branches.

#figure(
  table(
    columns: (1.5fr, 1fr, 2fr),
    table.header([Intervention], [Rescues], [Interpretation]),
    [`block_intros`], [256], [Plural intro over-commits early],
    [`block_simp`], [125], [Simplification loops avoided],
    [`block_rw`], [90], [Rewrite chains pruned],
    [`block_exact`], [60], [Forces alternative closers],
    [`block_apply`], [52], [Reduces blind application],
    [`block_have`], [43], [Lemma introduction pruned],
    [`block_rfl`], [38], [Forces non-trivial paths],
  ),
  caption: [
    Top rescue interventions. Blocking `intros` produces the most rescues (256),
    suggesting the baseline over-explores multi-binder introductions. These are cases
    where lesion regularizes search rather than damaging it.
  ],
)

The rescue phenomenon inverts the usual lesion interpretation: the "damaged" system
outperforms the intact one. This occurs when the baseline search wastes budget on
unproductive branches that the lesion prunes. Among failed baselines, blocking certain
tactics produces reliably higher rescue rates: `block_apply` (16.0%), `block_intros`
(15.6%), `block_have` (13.9%), and `block_decide` (13.5%) rescue far more often than
`block_intro` (2.0%) or `block_rfl` (3.3%). The pattern suggests that tactics
involving multi-step commitment (`intros`, `apply`, `have`) sometimes lock the prover
into suboptimal search branches, while atomic closers (`intro`, `rfl`) rarely cause
such over-commitment.

Some theorems exhibit 100% rescue rates: every baseline fails, but every lesioned
variant solves. These include `hf_deepseek_prover_v1_train_01679` (128 rescues) and
`add_eq_of_eq_neg_add` (134 rescues). For these theorems, the baseline proof strategy
is strictly dominated by the lesioned alternatives.

#bibliography("refs.bib", style: "springer-mathphys")
]
