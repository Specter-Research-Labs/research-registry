---
title: "Critical Fragment Size and Morphogenetic Vulnerability"
release: "draft"
source_id: "A-013"
toc: true
---

# Critical Fragment Size and Morphogenetic Vulnerability

If a patterned tissue is severed, which cut causes the largest phenotype change?

The natural graph heuristic says: maximize disconnected cell pairs. In a 1D chain of
length $n$, that score is $d(k) = k(n-k)$, maximized at the midpoint. But the midpoint
is not the worst cut in the regimes we scanned. The worst cut isolates a fragment below
the minimum domain size needed to sustain the reaction-diffusion pattern.

---

## Setup

Grodstein, McMillen & Levin (2023) define a 1D closed-loop morphogenesis model: a chain
of cells forms a Turing pattern, counts its own peaks with a computation wave, and
retunes the activator diffusion coefficient $D_a$ until the peak count matches a target.
We recast each cell as a polynomial functor and the tissue as a wiring diagram in
Catlab.jl, so severing the chain becomes factorization of the wiring diagram.

The one formal piece:

> **Disconnected-graph factorization.** Let $G = (V, E)$ be a finite graph with
> nearest-neighbor reaction-diffusion dynamics on each vertex, and let $F$ be a set of
> severed edges. If removing $F$ disconnects $G$ into connected components
> $C_1, \ldots, C_m$, then the severed system factorizes into $m$ independent
> subsystems, one on each $C_i$. The severed ODE system splits blockwise by connected
> component.

The 1D chain is the special case where $G$ is a path graph and a single cut yields two
contiguous fragments. The stronger result is 2D.

---

## 1D: Fragment viability beats the midpoint

We rank cuts by a severity functional measuring phenotype shift:

$$S(k) = \frac{1}{3}\left(\hat{\Delta}_{\text{peak}}(k) + \hat{\Delta}_{\text{profile}}(k) + \hat{\Delta}_{\text{shape}}(k)\right)$$

Each term normalized to $[0,1]$:

- **Peak-count delta:** change in number of pattern peaks.
- **Profile distance:** mean absolute difference between concentration profiles.
- **Shape distance:** edit distance between coarse shape strings.

On a 30-cell chain scanned over 100 values of $D_a \in [7.0, 12.5]$, the midpoint
heuristic ranks cut 15 first at every value. The severity functional never ranks the
midpoint as the worst cut.

| $D_a$ range | Worst cut | What it isolates | Margin |
|---|---|---|---|
| 7.0--8.0 | Position 4 | 4-cell tail fragment | Large (~0.12) |
| 8.25--9.25 | Position 25 | 5-cell head fragment | Small (collapsing) |
| 9.5--12.5 | Position 24 | 6-cell head fragment | Medium (~0.006) |

Each transition tracks a fragment-size threshold. At low $D_a$, wavelength is short
and a 5-cell fragment supports a peak but a 4-cell fragment cannot. As $D_a$
increases, the wavelength lengthens and a 5-cell fragment drops below viability,
shifting the worst cut. The transition is abrupt because the underlying event is
abrupt: a fragment crosses from viable to too small.

Extensions held: a 20-cell double-cut probe ranks `[5, 15]` ahead of the balanced
bipartition `[7, 14]`, and a validated 100-cell subset puts cut 80 ahead of cut 50.

The 1D chain is a prototype. The 2D grid result is where the compositional layer
starts doing work a connectivity score cannot do.

---

## 2D: Connectivity is flat, severity is not

For a 4x6 grid graph, we study rectangular patch isolation. A lesion severs all
boundary edges between a patch of size $(h, w)$ and the rest of the grid. Every
placement of a fixed-size patch isolates the same number of cells, so the connectivity
baseline is exactly constant within each lesion family. Connectivity can compare
lesion sizes, but not placements.

The severity functional generalizes to 2D via three policies:

- **Balanced:** component-count shift, activator-profile L1 shift, active-mask Hamming fraction.
- **Structure:** component-count shift, active-cell-count shift, active-mask Hamming fraction.
- **Profile:** activator-profile L1 shift, activator-profile L2 RMS shift, active-mask Hamming fraction.

The active mask thresholds the activator: cell $i$ is active when $A_i \geq \theta \cdot \max_j A_j$, with $\theta = 0.5$.

We ran 480 regimes (10 seeds, 4 patch sizes, 4 values of $D_a$, 3 values of $D_i$):

| Metric | Mean tie span | Min tie span | Frac. tie span > 0.5 | Top ≠ connectivity |
|---|---|---|---|---|
| Balanced | 0.751 | 0.286 | 0.942 | 97.5% |
| Profile | 0.812 | 0.332 | 0.981 | 90.6% |
| Structure | 0.856 | 0.267 | 0.985 | 99.0% |

The tie span is positive in 480/480 regimes for every metric. Varying the active-mask
threshold across $\theta \in \{0.4, 0.5, 0.6\}$ (4320 threshold-metric-regime cases)
preserves the effect.

---

## Prediction

Two lesions that break the same number of gap-junction links can have very different
consequences. The important variable is not connectivity loss; it is whether a
resulting fragment falls below the minimum domain size for its attractor.

If this holds in richer models, the most vulnerable anatomical location should depend
on the tissue's bioelectric parameters and should reorganize abruptly as those
parameters change. Spatially targeted gap-junction disruption combined with voltage
imaging could test that directly.

---

## Reproducibility

From a fresh clone:

```bash
git clone https://github.com/Specter-Research-Labs/research-registry.git
cd research-registry/addenda/poly-morphogenesis
julia --project=. -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
```

Severity scan demo:

```bash
julia --project=. -e 'using PolyMorphogenesis; main(["demo", "severity-scan", "--n-cells", "30", "--seed", "0"])'
```
