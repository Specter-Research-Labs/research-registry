#import "../../../../addenda/typst-field-manual/specter-paper.typ": author, paper
#import "../../../../addenda/typst-field-manual/tokens.typ": tokens

#paper(
  title: "Compositional Vulnerability Maps for Severed Reaction-Diffusion Tissues",
  subtitle: "Exact factorization on disconnected graphs yields a 2D result beyond connectivity",
  note: "SPECTER LABS PREPRINT",
  authors: (
    author("Ludwig Pouey", affiliation: "Specter Labs"),
  ),
  date: "April 2026",
  keywords: ("morphogenesis", "reaction-diffusion", "wiring diagrams", "graph factorization", "tissue vulnerability"),
  abstract: [
    We study how lesion location affects pattern disruption in severed reaction-diffusion
    tissues. The 1D closed-loop model of Grodstein, McMillen & Levin (2023)
    @grodstein2023 provides the compositional starting point, but the main empirical
    result of this addendum is 2D. We extend exact severing factorization from the 1D
    chain to disconnected reaction-diffusion graphs and evaluate fixed-size rectangular
    patch lesions on a 4x6 grid. In this lesion family, every placement has the same
    connectivity loss, so a connectivity baseline cannot rank lesions at all. A
    compositional severity ranking derived from exact connected-component factorization
    does.

    Across 480 regimes (10 seeds, 4 patch sizes, 4 values of $D_a$, and 3 values of
    $D_i$), the connectivity tie span is positive in 480/480 cases under each of three
    severity metrics. Mean tie span is 0.751 for a balanced metric, 0.812 for a
    profile metric, and 0.856 for a structural metric. The top severity placement
    differs from the connectivity top placement in 97.5%, 90.6%, and 99.0% of regimes,
    respectively. Varying the active-mask threshold across 0.4, 0.5, and 0.6 leaves the
    effect intact across 4320 threshold-metric-regime cases. The 1D chain therefore
    remains useful as a compositional prototype, but the substantive result is 2D: in a
    setting where connectivity is exactly uninformative, compositional factorization
    recovers a stable vulnerability structure.
  ],
)[

= Introduction

The motivating biological question is simple: if a patterned tissue is severed, which
lesion location causes the largest phenotypic change? In 1D chains this question is
easy to ask but easy to misframe. A midpoint baseline is not serious competition for a
reaction-diffusion system with a minimum viable domain size @murray1983 @murray2003.
The more relevant test for a compositional formalization is whether it adds leverage in
a setting where connectivity alone cannot rank interventions.

That is the contribution of this addendum. We keep the Grodstein, McMillen & Levin
(2023) model @grodstein2023 as the conceptual starting point, and we keep the 1D chain
as the exact prototype where severing factorization is transparent. But the main result
is not a new 1D transition diagram. The main result is a 2D graph lesion setting in
which a connectivity baseline is flat by construction, while a compositional
severity ranking remains nontrivial and robust.

The paper makes three concrete claims:

- Severing factorization is exact for disconnected reaction-diffusion graphs, not just
  for 1D chains.
- In a fixed-size 2D rectangular-patch lesion family, connectivity loss is constant
  within each lesion family and therefore cannot rank placements.
- A compositional severity ranking remains structured under metric choice, seed choice,
  and active-mask threshold choice.

This is the point at which the categorical layer starts to matter. In 1D, factorization
is a clean restatement of removing two coupling terms. In 2D, lesions create irregular
connected components, and the ranking depends on the induced decomposition rather than
on a scalar connectivity score. The result is still computational and still limited to
the reaction-diffusion layer, but it is no longer decorative.

= Background <background>

== Morphogenetic context

Bioelectric morphogenesis provides the motivating experimental context. Gap-junction
state, voltage patterning, and regenerative outcome can dissociate from genotype, which
is why severing and rewiring questions are biologically interesting @nogi2005
@durant2017 @durant2019 @levin2022. This addendum does not model membrane voltage
directly. It studies reaction-diffusion severing as a formal and computational proxy
for location-dependent tissue vulnerability.

== Grodstein as the 1D scaffold

Grodstein, McMillen & Levin (2023) define a 1D closed-loop morphogenesis model with
three layers @grodstein2023:

+ a reaction-diffusion layer on a nearest-neighbor chain,
+ a directional wave that counts peaks, and
+ a controller that retunes the activator diffusion scale until the peak count matches a
  target.

That model is important here for two reasons. First, it gives a concrete 1D system in
which severing is meaningful. Second, it motivates a compositional representation of
cells and tissues via polynomial functors and wiring diagrams. The 2D result reported
in this paper does not yet extend the wave and controller. It extends the reaction-
diffusion severing problem to graph topologies where exact factorization remains
available.

== Reaction-diffusion and domain viability

For Turing-type systems, pattern existence depends on both the reaction law and the
domain geometry @turing1952 @murray1983 @murray2003. A fragment below the relevant
domain scale does not preserve the parent pattern. That minimum-domain-size intuition is
the 1D prototype. The 2D question is different: once lesion size is held fixed, does
placement still matter after the obvious size effect has been removed?

= Methods <methods>

== Graph factorization

#block(
  inset: (left: 12pt, y: 8pt),
  stroke: (left: 2pt + tokens.paper_colors.accent),
)[
*Proposition (Disconnected-graph factorization).* Let $G = (V, E)$ be a finite graph
with nearest-neighbor reaction-diffusion dynamics on each vertex, and let $F$ be a set
of severed edges. If removing $F$ disconnects the graph into connected components
$C_1, ..., C_m$, then the severed reaction-diffusion system factorizes into
$m$ independent subsystems, one on each $C_i$.

_Proof._ Each diffusion term uses only incident edges. After removing $F$, no state in
$C_i$ depends on any state in $C_j$ for $i != j$. The severed ODE system therefore
splits blockwise by connected component. $square$
]

The 1D chain is the special case in which $G$ is a path graph and a single cut yields
two contiguous components. The 2D result in this paper uses the more general graph
statement directly.

== 2D lesion family

We study rectangular patch isolation on a 4x6 grid graph. A lesion is defined by a
patch size $(h, w)$ and a patch placement given by its top row and left column. The
intervention severs all
boundary edges between the patch and the rest of the grid, producing two disconnected
components: the isolated patch and the exterior remainder.

The evaluated patch sizes are:

- 1x1
- 1x2
- 2x2
- 2x3

For each patch size, every placement isolates the same number of cells and therefore
induces the same number of disconnected cell pairs. This makes the connectivity
baseline intentionally flat within each patch family.

== Baseline and severity policies

The connectivity baseline ranks lesions by the number of disconnected unordered cell
pairs:

$ d(F) = "number of disconnected unordered cell pairs after severing" $

For fixed-size rectangular patch isolation on a fixed grid, $d(F)$ is constant across
placements. Connectivity can compare lesion *families* of different sizes, but not
placements within a family.

We therefore evaluate three compositional severity policies, each normalized within a
regime by its componentwise maxima:

- *Balanced:* component-count shift, activator-profile L1 shift, active-mask Hamming
  fraction.
- *Structure:* component-count shift, active-cell-count shift, active-mask Hamming
  fraction.
- *Profile:* activator-profile L1 shift, activator-profile L2 RMS shift, active-mask
  Hamming fraction.

The active mask is defined by a thresholded activator field: cell $i$ is active when
$A_i >= theta times max_j A_j$.

with baseline threshold $theta = 0.5$. Threshold robustness is assessed at
$theta in {0.4, 0.5, 0.6}$.

== Evaluation protocol

For each regime we:

1. initialize the grid with a fixed seed,
2. settle the connected graph,
3. sever one rectangular patch boundary,
4. factorize the severed graph into connected components,
5. settle each component independently, and
6. compare the severed phenotype against the connected reference.

The primary summary statistics are:

- *Connectivity tie span:* the severity max-minus-min inside the largest connectivity
  tie class.
- *Top margin:* the severity difference between the top-ranked and second-ranked
  lesions.
- *Top disagreement rate:* the fraction of regimes in which the top severity placement
  differs from the top connectivity placement.

The main regime grid is:

- 10 seeds
- patch sizes {1x1, 1x2, 2x2, 2x3}
- $D_a in {0.8, 1.0, 1.2, 1.4}$
- $D_i in {20, 30, 40}$

This yields 480 regimes per metric. Crossing the same regimes with three active-mask
thresholds yields 4320 threshold-metric-regime cases.

= Results <results>

== Representative 2D regime

The simplest concrete example already defeats the connectivity baseline. For a 2x2
isolated patch on the 4x6 grid at seed 33, $D_a = 1.0$, and $D_i = 30.0$, every one of
the 15 patch placements has the same connectivity loss:

$ d = 80 $

Connectivity is therefore indifferent. The balanced severity metric is not.

#figure(
  table(
    columns: 4,
    stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
    inset: 8pt,
    table.header([Placement], [Connectivity], [Balanced severity], [Rank]),
    [(1, 3)], [80], [0.919], [1],
    [(2, 3)], [80], [0.879], [2],
    [(3, 4)], [80], [0.863], [3],
    [(1, 1)], [80], [0.833], [4],
    [(3, 2)], [80], [0.828], [5],
  ),
  caption: [Representative 2D regime for 2x2 isolated patches on a 4x6 grid
    (seed 33, $D_a = 1.0$, $D_i = 30.0$). Connectivity is constant across all
    placements, but the compositional severity ranking is not.],
) <representative-2d>

This is the empirical setting the paper needs. The connectivity baseline does not fail
by being weakly correlated with severity. It fails by carrying no information at all.

== Multi-seed metric robustness

We ran the full 2D sweep over 10 seeds, 4 patch sizes, 4 values of $D_a$, and 3 values
of $D_i$. For each of the resulting 480 regimes, connectivity is flat within the fixed-
size lesion family. Table @metric-robustness summarizes the three severity policies.

#figure(
  table(
    columns: 6,
    stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
    inset: 8pt,
    table.header(
      [Metric],
      [Regimes],
      [Mean tie span],
      [Min tie span],
      [Frac. tie span > 0.5],
      [Top disagrees with connectivity],
    ),
    [Balanced], [480], [0.751], [0.286], [0.942], [0.975],
    [Profile], [480], [0.812], [0.332], [0.981], [0.906],
    [Structure], [480], [0.856], [0.267], [0.985], [0.990],
  ),
  caption: [Metric robustness for the 2D lesion family. Every regime has flat
    connectivity within the lesion family. Every regime also has positive tie span under
    every severity policy.],
) <metric-robustness>

Three points matter:

- The tie span is positive in 480/480 regimes for every metric.
- The mean tie span is large under all three metrics, not just under the original
  balanced score.
- The top severity placement almost always differs from the connectivity top placement.

The effect is therefore not an artifact of one hand-picked severity policy. The exact
winner can change with the metric, but the existence of nontrivial structure inside the
connectivity tie survives.

== Threshold robustness

The active mask appears explicitly in all three metrics, so threshold choice is a real
possible failure mode. We therefore repeated the full sweep at active fractions 0.4,
0.5, and 0.6, yielding 4320 threshold-metric-regime cases.

#figure(
  table(
    columns: 5,
    stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
    inset: 8pt,
    table.header(
      [Metric],
      [Active fraction],
      [Mean tie span],
      [Min tie span],
      [Top disagrees with connectivity],
    ),
    [Balanced], [0.4], [0.754], [0.292], [0.983],
    [Balanced], [0.5], [0.751], [0.286], [0.975],
    [Balanced], [0.6], [0.786], [0.290], [0.971],
    [Profile], [0.4], [0.806], [0.310], [0.948],
    [Profile], [0.5], [0.812], [0.332], [0.906],
    [Profile], [0.6], [0.804], [0.251], [0.854],
    [Structure], [0.4], [0.855], [0.417], [0.985],
    [Structure], [0.5], [0.856], [0.267], [0.990],
    [Structure], [0.6], [0.892], [0.267], [0.977],
  ),
  caption: [Threshold robustness for the 2D lesion family. The separation survives
    threshold changes across all tested metrics.],
) <threshold-robustness>

Again, the key point is not that every threshold gives the same ranking. It does not.
The key point is that the separation remains nontrivial after threshold changes. The
weakest corner is the profile metric on 2x3 patches at threshold 0.6, where the top
disagreement rate falls to 0.725, but the mean tie span in that slice remains 0.598 and
the minimum tie span remains positive at 0.251.

== What the 1D chain still contributes

The 1D chain remains useful in two narrower ways:

- It provides the exact motivating special case for severing factorization.
- It keeps the addendum anchored to the Grodstein closed-loop model, which remains 1D.

What it does *not* provide is the main empirical claim of this paper. The 1D result is
best read as a prototype and continuity argument. The 2D grid result is where the
compositional layer starts doing work that a connectivity score cannot do.

= Discussion <discussion>

== What is new here

The strongest claim supported by the current draft is no longer "the midpoint is not
the worst cut." That claim is true but not especially informative. The stronger claim
is:

In a 2D lesion family where connectivity is exactly flat, compositional factorization
produces a stable vulnerability ordering across seeds, metrics, and active-mask
thresholds.

That is the point at which the applied-category-theory layer stops being a reformulation
exercise. The lesion creates disconnected graph components. The factorization is exact on
those components. The severity ranking is computed on the induced decomposition. And the
baseline connectivity score has nothing to say because it is constant.

== Relationship to existing work

The 1D prototype still aligns with the classical minimum-domain-size literature for
Turing systems @murray1983 @murray2003. The 2D result is closer in spirit to
fragmentation studies such as Bassett & Van Gorder (2022) @bassett2022, where pattern
existence depends on patch geometry and diffusion scale. Our question is different.
We do not ask whether a fragmented landscape admits any pattern. We ask whether lesions
with identical connectivity loss differ systematically in phenotypic severity.

Within the bioelectric morphogenesis program, the present result should be read as an
RD-layer addendum, not as a full 2D bioelectric controller model. It is motivated by
the Grodstein framework and by lesion-location questions in morphogenesis, but it does
not yet implement a 2D wave or a 2D controller.

== Why the categorical layer matters here

For 1D chains, the categorical machinery is clean but not load-bearing. For disconnected
2D graphs, it is closer to load-bearing because:

- the lesion is defined structurally, by severed graph edges rather than by an interval
  index;
- the factorization follows the connected-component decomposition directly; and
- the ranking problem remains nontrivial even when connectivity is flat.

This is the right direction for the addendum. It is still modest. It is not yet a full
2D closed-loop morphogenesis paper. But it is a setting where the compositional layer
changes what can be computed and compared.

= Limitations

- *RD-only in 2D.* The reported 2D result studies the reaction-diffusion layer alone.
  The 2D wave and 2D controller are not yet defined.
- *Restricted lesion family.* We study rectangular patch isolation on a regular 4x6
  grid. This is a disciplined test family, not a full lesion taxonomy.
- *No experimental validation.* All results are computational.
- *Severity is still designed, not discovered.* Metric and threshold robustness are now
  measured rather than deferred, but they are not exhaustive over all possible
  phenotype distances.
- *No full 2D geometry sweep.* We vary patch size, diffusion parameters, seed, metric,
  and threshold, but not grid aspect ratio or alternative graph topologies.
- *Bioelectric interpretation is indirect.* The model is motivated by bioelectric
  morphogenesis but operates on reaction-diffusion concentrations, not membrane voltage.

= Reproducibility

Code and documentation for this addendum are in the public repository
`https://github.com/Specter-Research-Labs/research-registry`, under
`addenda/poly-morphogenesis/`.

From a fresh clone:

```bash
git clone https://github.com/Specter-Research-Labs/research-registry.git
cd research-registry/addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

Core paper commands:

```bash
# Representative 2D patch sweep
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "grid-patch-sweep", "--rows", "4", "--cols", "6", "--patch-sizes", "1x1,1x2,2x2,2x3", "--seed", "33", "--d-a-values", "0.8,1.0,1.2,1.4", "--d-i-values", "20.0,30.0,40.0"])'

# Metric sensitivity for one regime
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "grid-patch-sensitivity", "--rows", "4", "--cols", "6", "--patch-rows", "2", "--patch-cols", "2", "--seed", "33", "--d-a", "1.0", "--d-i", "30.0", "--metrics", "balanced,structure,profile"])'

# Threshold sensitivity for one regime
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "grid-patch-threshold-sensitivity", "--rows", "4", "--cols", "6", "--patch-rows", "2", "--patch-cols", "2", "--seed", "33", "--d-a", "1.0", "--d-i", "30.0", "--active-fractions", "0.4,0.5,0.6", "--metrics", "balanced,structure,profile"])'
```

The aggregate numbers reported in @metric-robustness and @threshold-robustness were
generated by looping these commands over seeds 0 through 9, patch sizes
{1x1, 1x2, 2x2, 2x3}, $D_a in {0.8, 1.0, 1.2, 1.4}$, and $D_i in {20, 30, 40}$.

#bibliography("refs.bib", style: "springer-mathphys")
]
