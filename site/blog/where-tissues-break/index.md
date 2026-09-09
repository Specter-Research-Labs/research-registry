---
title: "Where Tissues Break"
release: "draft"
summary: We formalized a closed-loop morphogenesis model using polynomial functors and wiring diagrams, then used that compositional structure to predict which cuts do the most damage. Vulnerability is set by fragment viability, not connectivity alone, and the worst cut shifts abruptly as diffusion parameters change.
toc: true
---

# Where Tissues Break

## The Midpoint Is Not the Worst Cut

The worst cut in this tissue model is the one that strands a fragment below the size needed to sustain its reaction-diffusion pattern. It is not the midpoint, despite the midpoint maximizing the usual disconnected-pairs score. As the activator diffusion coefficient $D_a$ changes, the identity of the worst cut jumps.

The model comes from [Closing the loop on morphogenesis](https://doi.org/10.3389/fcell.2023.1087650) (Grodstein, McMillen, and Levin, 2023): a 1D chain forms a reaction-diffusion pattern, counts its peaks with a computation wave, and adjusts its parameters until the count matches a target. We recast its cells as polynomial functors and the tissue as a wiring diagram so that severing it produces explicit independent fragments.

---

## The model

### Turing patterns in one dimension

Consider a row of 100 cells. Each cell contains two chemicals: an **activator** that promotes its own production, and an **inhibitor** that suppresses it. Both diffuse to neighboring cells, but the inhibitor diffuses faster.

This is a [Turing system](https://en.wikipedia.org/wiki/Turing_pattern). The fast inhibitor creates local zones of suppression around each activator peak, and the chain settles into a striped pattern in one dimension. The spacing between peaks is set by the diffusion rates. Longer tissues support more peaks. Shorter tissues support fewer.

The key parameter is $D_a$, the activator diffusion coefficient. Increase $D_a$ and the peaks spread out. Decrease it and the peaks tighten. The tissue tends toward roughly $L / \lambda_{RD}$ peaks, where $L$ is tissue length and $\lambda_{RD}$ is the characteristic RD wavelength.

### Counting peaks with a wave

The Grodstein model does not assume an external observer. The tissue counts its own peaks. A chemical wave starts at the tail and propagates toward the head. As it passes each cell, the cell checks its local activator concentration. If the concentration crosses a threshold, the counter increments.

The counter uses Schmitt-trigger logic, with hysteresis, so noise does not create false counts. By the time the wave reaches the head cell, the head cell holds the total peak count.

### Closing the loop

The controller reads that count, compares it to a target $N$, and adjusts $D_a$:

- Too many peaks: increase $D_a$ so the wavelength broadens and the peak count drops.
- Too few peaks: decrease $D_a$ so the wavelength tightens and the peak count rises.
- Correct count: stop.

The cycle repeats until the tissue reaches the target count. That is the closed loop: build a pattern, measure it, correct it.

---

## The formalization

### Cutting the model

The hand-written coupled ODE system and the composed categorical system agree at machine precision. The diagram exposes what a cut does: it splits the tissue into independent pieces instead of mutating one state vector in place.

### Cells as polynomial functors

The formal definition is:

$$p(y) = \sum_{s \in S} y^{R(s)}$$

Polynomial functors encode systems whose interface depends on current state.

A cell in the Grodstein model fits that shape exactly:

- **RD mode:** the state is the local activator and inhibitor concentration, and the cell exchanges diffusion signals with its neighbors.
- **Wave mode:** the state includes the GRN counter, and the cell passes counting signals to the next cell.
- **Done mode:** the state includes the final peak count, and the cell exposes that count to the controller.

The ports change with the mode.

### The wiring diagram

A **wiring diagram** specifies which outputs feed which inputs. In the RD layer, cell $i$ sends activator and inhibitor signals to its immediate neighbors. In the wave layer, signals move left to right only.

We implement this in [Catlab.jl](https://github.com/AlgebraicJulia/Catlab.jl). For a 10-cell RD tissue, the wiring diagram looks like this:

![RD wiring diagram](../../addenda/poly-morphogenesis/docs/diagrams/rd_styled.svg)

The runtime uses these wires to route signals and build the composed dynamics.

### The tissue is the composition

The tissue is the composition of 100 cell components through that wiring diagram. The global state is the product of the local cell states, and the coupling is carried by the wires. We verified that this composed system matches the direct coupled ODE implementation at machine precision.

---

## Cutting the tissue

Cut the edge between cell $k$ and cell $k+1$.

In the categorical model, the wiring diagram decomposes into two independent subdiagrams: cells $1$ through $k$, and cells $k+1$ through $n$. Each fragment settles to its own attractor. That gives a simple prediction pipeline:

1. Factor the severed tissue into fragments.
2. Compute each fragment's settled pattern.
3. Concatenate the fragment phenotypes.
4. Compare the result to the intact tissue.

### The connectivity heuristic says "cut the midpoint"

A natural graph heuristic says the worst cut is the one that maximizes disruption. In a 1D chain, every cut removes one edge, so edge count does not distinguish positions. A slightly better connectivity score counts disconnected cell pairs:

$$d(k) = k(n-k)$$

That is maximized at the midpoint. If you reason only in terms of connectivity, the midpoint looks worst.

### Fragment viability

We rank cuts by a **severity functional** measuring phenotype shift between the intact tissue and the severed one:

$$S(k) = \frac{1}{3}\left(\hat{\Delta}_{\text{peak}}(k) + \hat{\Delta}_{\text{profile}}(k) + \hat{\Delta}_{\text{shape}}(k)\right)$$

The three terms are normalized to $[0,1]$:

- **Peak-count delta:** change in the number of peaks.
- **Profile distance:** mean absolute difference between concentration profiles.
- **Shape distance:** edit distance between coarse shape strings such as `"LH"` and `"LHLH"`.

On the 30-cell scan, the midpoint heuristic ranks cut 15 first at every parameter value. The severity functional does not. In that scan, the midpoint is never the worst cut.

The worst cut isolates a short fragment near one end of the chain: a fragment below the **minimum domain size** needed to sustain the RD pattern. That fragment collapses to a different attractor. The longer fragment stays close to what it was already doing.

By contrast, a midpoint cut usually creates two fragments that are both still large enough to sustain their patterns. It breaks more pairwise connectivity, but it produces a smaller phenotype shift.

---

## The vulnerability landscape has phase boundaries

We scanned 100 values of $D_a$ from 7.0 to 12.5 on a 30-cell chain. At each $D_a$, we scored every possible single cut and recorded the worst one.

The identity of the worst cut changes at two transition points:

| $D_a$ range | Worst cut | What it isolates | Margin |
|---|---|---|---|
| 7.0 -- 8.0 | Position 4 | 4-cell tail fragment | Large (~0.12) |
| 8.25 -- 9.25 | Position 25 | 5-cell head fragment | Small (collapsing) |
| 9.5 -- 12.5 | Position 24 | 6-cell head fragment | Medium (~0.006) |

This produces a phase diagram in $(D_a, \text{cut position})$ space. As $D_a$ changes, the identity of the worst cut jumps.

When the top-two gap is large, the tissue has one dominant weak point. When it collapses, many nearby cuts are almost equally bad.

### Why the transitions happen

Each transition tracks a fragment-size threshold.

At low $D_a$, the characteristic wavelength is short, so a 5-cell fragment can still support a peak but a 4-cell fragment cannot. The worst cut is therefore the one that isolates four cells.

As $D_a$ increases, the wavelength lengthens. Now a 5-cell fragment drops below viability, so the worst cut shifts. The jump is abrupt because the underlying event is abrupt: a fragment crosses from "large enough to support this attractor" to "too small."

Vulnerability is organized by **critical fragment size**, not symmetric graph partitioning.

### The effect survives simple extensions

We also checked two nearby cases.

In a structured 20-cell double-cut probe, the balanced-bipartition heuristic ranks cuts `[7, 14]` first, while the severity ranking places `[5, 15]` first. The reason is simple: `[5, 15]` creates two 5-cell fragments near the viability boundary, so the total phenotype shift is larger even though the raw connectivity score is smaller.

In a validated 100-cell subset `{50, 75, 80, 85, 90}`, connectivity ranks the midpoint cut `50` first, while the severity ranking places cut `80` first. That is still a probe, not a full sweep, but it points in the same direction. The mechanism is fragment viability, not midpoint symmetry.

---

## The prediction and the limits

### A concrete prediction

The literature already contains the ingredients: minimum domain size for Turing patterns ([Murray & Sperb, 1983](https://doi.org/10.1007/BF00280665)), mode selection on bounded domains ([Crampin et al., 2002](https://doi.org/10.1007/s002850100112)), gap junction disruption causing morphological change ([Nogi & Levin, 2005](https://doi.org/10.1016/j.ydbio.2005.09.002)), and critical fragment size for regeneration ([Shimizu et al., 1993](https://doi.org/10.1006/dbio.1993.1028)).

We rank vulnerability over parameter and cut-position space: factor the severed tissue, predict each fragment's attractor, and score the phenotype shift.

### The biological claim

Two lesions that break the same number of gap-junction links can have very different consequences. The variable is whether one of the resulting fragments falls below the size needed to sustain its attractor.

If that picture survives contact with richer models and experiments, then the most vulnerable anatomical location should depend on the tissue's bioelectric parameters and should reorganize abruptly as those parameters change.

That is testable. Spatially targeted gap-junction disruption, combined with voltage imaging, could look for position-dependent vulnerability in planaria or frog embryos.

### The formalization

You do not need category theory to see a cut 1D chain fall into two pieces. The formalization makes that factorization typed, checkable, and portable to less obvious topologies:

1. The cut is a typed decomposition of a wiring diagram, not an ad hoc splice of a vector.
2. The same language can carry to less trivial topologies, where the right factorization is not obvious by inspection.
3. Thinking compositionally is what made the vulnerability question legible in the first place.

### Open checks

- **RD-only ablation:** the current model includes a directional computation wave. We still need to show that the vulnerability asymmetry comes from fragment viability rather than wave direction.
- **Higher-dimensional tissues:** exact factorization is clean in 1D. In 2D and 3D, cuts create more complicated boundary geometry.
- **Experiment:** all current results are computational.

---

## Reproducibility

Code and documentation for this addendum are in the public repository:
[`Specter-Research-Labs/research-registry`](https://github.com/Specter-Research-Labs/research-registry), under [`addenda/poly-morphogenesis/`](https://github.com/Specter-Research-Labs/research-registry/tree/main/addenda/poly-morphogenesis).

From a fresh clone:

```bash
git clone https://github.com/Specter-Research-Labs/research-registry.git
cd research-registry/addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

Representative demo commands:

```bash
# Severity scan over D_a values
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "severity-scan", "--n-cells", "30", "--seed", "0", "--d-a-values", "7.5,8.5,9.849732675807608", "--top-k", "1"])'

# Cut sweep with exact fragment factorization
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "cut-sweep", "--n-cells", "30", "--seed", "0", "--cut-count", "1"])'

# Closed-loop convergence
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "closed-loop", "--n-cells", "100", "--target-peaks", "5", "--seed", "0"])'
```

---

*This article describes the documentation-only `poly-morphogenesis` draft in [`addenda/poly-morphogenesis/docs/`](../../addenda/poly-morphogenesis/docs/). A formal paper draft is at [`docs/paper/main.typ`](../../addenda/poly-morphogenesis/docs/paper/main.typ).*
