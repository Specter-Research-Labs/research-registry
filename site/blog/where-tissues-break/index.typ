#import "../../../addenda/typst-field-manual/specter-paper.typ": author, paper
#import "../../../addenda/typst-field-manual/tokens.typ": tokens

#paper(
  title: "Where Tissues Break",
  subtitle: "A compositional prediction of morphogenetic vulnerability",
  note: "SPECTER LABS BLOG POST",
  authors: (
    author("Ludwig Pouey", affiliation: "Specter Labs"),
  ),
  date: "April 2026",
  keywords: ("morphogenesis", "reaction-diffusion", "polynomial functors", "wiring diagrams", "Grodstein model", "bioelectricity"),
  abstract: [
    We formalized a closed-loop morphogenesis model using polynomial functors and wiring diagrams, then used that compositional structure to predict which cuts do the most damage. Vulnerability is set by fragment viability, not connectivity alone, and the worst cut shifts abruptly as diffusion parameters change. The categorical formalization makes tissue cutting a typed operation: sever the tissue, factor the wiring diagram, and compute the fragments separately.
  ],
)[

= Introduction

In 2023, Joel Grodstein, Patrick McMillen, and Michael Levin published "Closing the loop on morphogenesis." The model is small and crisp: a 1D chain of cells forms a reaction-diffusion pattern, counts its own peaks with a computation wave, and adjusts its parameters until the count matches a target.

We recast that model categorically: each cell as a polynomial functor, the tissue as a wiring diagram, and the feedback loop as a composition of phases connected by dependent lenses. That reformulation does not change the underlying dynamics. It does make one operation explicit: cut the tissue, factor the wiring diagram, and compute the fragments separately.

That yields a concrete prediction. The most damaging cut is not determined by connectivity alone, and in the regimes we scanned it is not the midpoint. It is determined by fragment viability: which cut isolates a fragment too small to sustain the pattern it had in the intact tissue. As the activator diffusion coefficient $D_a$ changes, the identity of the worst cut changes abruptly.

= The Model <model>

== Turing patterns in one dimension

Consider a row of 100 cells. Each cell contains two chemicals: an *activator* that promotes its own production, and an *inhibitor* that suppresses it. Both diffuse to neighboring cells, but the inhibitor diffuses faster.

This is a Turing system. The fast inhibitor creates local zones of suppression around each activator peak, and the chain settles into a striped pattern in one dimension. The spacing between peaks is set by the diffusion rates. Longer tissues support more peaks. Shorter tissues support fewer.

The key parameter is $D_a$, the activator diffusion coefficient. Increase $D_a$ and the peaks spread out. Decrease it and the peaks tighten. The tissue tends toward roughly $L slash lambda_"RD"$ peaks, where $L$ is tissue length and $lambda_"RD"$ is the characteristic RD wavelength.

== Counting peaks with a wave

The Grodstein model does not assume an external observer. The tissue counts its own peaks. A chemical wave starts at the tail and propagates toward the head. As it passes each cell, the cell checks its local activator concentration. If the concentration crosses a threshold, the counter increments.

The counter uses Schmitt-trigger logic, with hysteresis, so noise does not create false counts. By the time the wave reaches the head cell, the head cell holds the total peak count.

== Closing the loop

The controller reads that count, compares it to a target $N$, and adjusts $D_a$:

+ Too many peaks: increase $D_a$ so the wavelength broadens and the peak count drops.
+ Too few peaks: decrease $D_a$ so the wavelength tightens and the peak count rises.
+ Correct count: stop.

The cycle repeats until the tissue reaches the target count. That is the closed loop: build a pattern, measure it, correct it.

= The Formalization <formalization>

== Why formalize it categorically?

Not to make the ODEs "more correct." The hand-written coupled ODE system and the composed categorical system agree at machine precision.

The gain is compositional. When you sever the chain, the wiring diagram literally splits into independent pieces. That turns tissue cutting into a structured operation rather than an ad hoc edit to a state vector.

== Cells as polynomial functors

The one formal definition we need is:

$ p(y) = sum_(s in S) y^(R(s)) $

What matters here is not the notation but the use: polynomial functors encode systems whose interface depend on their current state.

A cell in the Grodstein model fits that shape exactly:

+ *RD mode:* the state is the local activator and inhibitor concentration, and the cell exchanges diffusion signals with its neighbors.
+ *Wave mode:* the state includes the GRN counter, and the cell passes counting signals to the next cell.
+ *Done mode:* the state includes the final peak count, and the cell exposes that count to the controller.

The ports change with the mode. That is the point.

== The wiring diagram

A *wiring diagram* specifies which outputs feed which inputs. In the RD layer, cell $i$ sends activator and inhibitor signals to its immediate neighbors. In the wave layer, signals move left to right only.

We implement this in Catlab.jl. For a 10-cell RD tissue, the wiring diagram represents the executable structure, not just illustration. The runtime uses these wires to route signals and build the composed dynamics.

== The tissue is the composition

The tissue is the composition of 100 cell components through that wiring diagram. The global state is the product of the local cell states, and the coupling is carried by the wires. We verified that this composed system matches the direct coupled ODE implementation at machine precision.

= Cutting the Tissue <cutting>

Cut the edge between cell $k$ and cell $k+1$.

In the categorical model, the wiring diagram decomposes into two independent subdiagrams: cells $1$ through $k$, and cells $k+1$ through $n$. Each fragment settles to its own attractor. That gives a simple prediction pipeline:

1. Factor the severed tissue into fragments.
2. Compute each fragment's settled pattern.
3. Concatenate the fragment phenotypes.
4. Compare the result to the intact tissue.

== The connectivity heuristic says "cut the midpoint"

A natural graph heuristic says the worst cut is the one that maximizes disruption. In a 1D chain, every cut removes one edge, so edge count does not distinguish positions. A slightly better connectivity score counts disconnected cell pairs:

$ d(k) = k(n-k) $

That is maximized at the midpoint. If you reason only in terms of connectivity, the midpoint looks worst.

== The stronger answer is fragment viability

We rank cuts by a *severity functional* measuring phenotype shift between the intact tissue and the severed one:

$ S(k) = 1/3 (hat(Delta)_"peak"(k) + hat(Delta)_"profile"(k) + hat(Delta)_"shape"(k)) $

The three terms are normalized to $[0,1]$:

+ *Peak-count delta:* change in the number of peaks.
+ *Profile distance:* mean absolute difference between concentration profiles.
+ *Shape distance:* edit distance between coarse shape strings such as "LH" and "LHLH".

On the 30-cell scan, the midpoint heuristic ranks cut 15 first at every parameter value. The severity functional does not. In that scan, the midpoint is never the worst cut.

The worst cut isolates a short fragment near one end of the chain: a fragment below the *minimum domain size* needed to sustain the RD pattern. That fragment collapses to a different attractor. The longer fragment stays close to what it was already doing.

By contrast, a midpoint cut usually creates two fragments that are both still large enough to sustain their patterns. It breaks more pairwise connectivity, but it produces a smaller phenotype shift.

= The Vulnerability Landscape Has Phase Boundaries <landscape>

We scanned 100 values of $D_a$ from 7.0 to 12.5 on a 30-cell chain. At each $D_a$, we scored every possible single cut and recorded the worst one.

The identity of the worst cut changes at two transition points:

#figure(
  table(
    columns: 4,
    stroke: tokens.paper_rules.thin + tokens.paper_colors.rule,
    inset: 8pt,
    table.header([*$D_a$ range*], [*Worst cut*], [*What it isolates*], [*Margin*]),
    [7.0 -- 8.0], [Position 4], [4-cell tail fragment], [Large (~0.12)],
    [8.25 -- 9.25], [Position 25], [5-cell head fragment], [Small (collapsing)],
    [9.5 -- 12.5], [Position 24], [6-cell head fragment], [Medium (~0.006)],
  ),
  caption: [Transition points in the vulnerability landscape. The worst cut shifts from position 4 (isolating a short tail fragment) to positions 25/24 (isolating short head fragments) as $D_a$ increases. The balanced-bipartition heuristic ranks cut 15 first at every $D_a$ value.],
) <transitions>

So the right object is not a single "most vulnerable location" full stop. It is a phase diagram in $(D_a, text("cut position"))$ space. As $D_a$ changes, the identity of the worst cut jumps.

The top-2 gap matters too. When the gap is large, the tissue has one clearly dominant weak point. When the gap collapses, the tissue is broadly fragile: many nearby cuts are almost equally bad. That is a different failure regime.

== Why the transitions happen

Each transition tracks a fragment-size threshold.

At low $D_a$, the characteristic wavelength is short, so a 5-cell fragment can still support a peak but a 4-cell fragment cannot. The worst cut is therefore the one that isolates four cells.

As $D_a$ increases, the wavelength lengthens. Now a 5-cell fragment drops below viability, so the worst cut shifts. The jump is abrupt because the underlying event is abrupt: a fragment crosses from "large enough to support this attractor" to "too small."

This is the core picture: vulnerability is organized by *critical fragment size*, not by symmetric graph partitioning.

== The effect survives simple extensions

We also checked two nearby cases.

In a structured 20-cell double-cut probe, the balanced-bipartition heuristic ranks cuts [7, 14] first, while the severity ranking places [5, 15] first. The reason is simple: [5, 15] creates two 5-cell fragments near the viability boundary, so the total phenotype shift is larger even though the raw connectivity score is smaller.

In a validated 100-cell subset {50, 75, 80, 85, 90}, connectivity ranks the midpoint cut 50 first, while the severity ranking places cut 80 first. That is still a probe, not a full sweep, but it points in the same direction. The mechanism is fragment viability, not midpoint symmetry.

= The Prediction and the Limits <prediction>

== A concrete prediction

The literature already contains the ingredients: minimum domain size for Turing patterns, mode selection on bounded domains, gap junction disruption causing morphological change, and critical fragment size for regeneration.

What this addendum contributes is the combination: a vulnerability ranking over parameter and cut-position space. The compositional formalization makes that combination natural. Factor the severed tissue, predict each fragment's attractor, and score the result.

== The biological claim

Taken as a model claim, the prediction is straightforward: two lesions that break the same number of gap-junction links can have very different consequences, because the important variable is not just connectivity loss. It is whether one of the resulting fragments falls below the size needed to sustain its attractor.

If that picture survives contact with richer models and experiments, then the most vulnerable anatomical location should depend on the tissue's bioelectric parameters and should reorganize abruptly as those parameters change.

That is testable. Spatially targeted gap-junction disruption, combined with voltage imaging, could look for position-dependent vulnerability in planaria or frog embryos.

== What the formalization adds

You do not need category theory to notice that a cut 1D chain falls into two pieces. The value here is not that the chain itself becomes possible. The value is that the factorization becomes typed, checkable, and extensible.

It buys three things:

1. The cut is a typed decomposition of a wiring diagram, not an ad hoc splice of a vector.
2. The same language can carry to less trivial topologies, where the right factorization is not obvious by inspection.
3. Thinking compositionally is what made the vulnerability question legible in the first place.

== Open checks

+ *RD-only ablation:* the current model includes a directional computation wave. We still need to show that the vulnerability asymmetry comes from fragment viability rather than wave direction.
+ *Higher-dimensional tissues:* exact factorization is clean in 1D. In 2D and 3D, cuts create more complicated boundary geometry.
+ *Experiment:* all current results are computational.

= Reproducibility

Code and documentation for this addendum are in the public repository `https://github.com/Specter-Research-Labs/research-registry`, under `addenda/poly-morphogenesis/`.

From a fresh clone:

```bash
git clone https://github.com/Specter-Research-Labs/research-registry.git
cd research-registry/addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

Representative demo commands:

```bash
# Severity scan over multiple D_a values
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "severity-scan", "--n-cells", "30", "--seed", "0", "--d-a-values", "7.5,8.5,9.849732675807608", "--top-k", "1"])'

# Cut sweep with factorization
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "cut-sweep", "--n-cells", "30", "--seed", "0", "--cut-count", "1"])'

# Closed-loop convergence
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "closed-loop", "--n-cells", "100", "--target-peaks", "5", "--seed", "0"])'
```

The implementation includes:

- Source code in `src/` (RD layer, wave counting, controller, Poly layer, compilation, wiring)
- Comprehensive test suite in `test/`
- Documentation in `docs/` including diagrams and the formal paper draft

This article describes the `poly-morphogenesis` work in `addenda/poly-morphogenesis/docs/`. A formal paper draft is at `docs/paper/main.typ`.

]
