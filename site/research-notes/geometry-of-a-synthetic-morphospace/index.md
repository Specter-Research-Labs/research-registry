---
title: "The Geometry of a Synthetic Morphospace"
release: "draft"
provenance: "assistant-drafted"
source_id: "D-003"
toc: true
---

# The Geometry of a Synthetic Morphospace

We use Flow Lenia to study the structure of a synthetic morphospace — fiber-bundle geometry, non-trivial topology, and measurable holonomy — rather than to catalog creatures.

## Setup

[Morozova and Shubin (2012)](https://arxiv.org/pdf/1205.1158) formalized the morphogenetic field as a fiber bundle: the base space is cell states across developmental time, the fiber at each cell is possible cell events, and the morphogenetic field selects one event per cell. Development, in this picture, is minimization of discrepancy between actual and coded target trees.

In Lenia, the genotype-to-phenotype map $\pi$ gives the same structure directly:

- **Base space $B$:** phenotype space of observable creature morphologies (velocity, spatial extent, moment invariants).
- **Total space $E$:** genotype space of parameter vectors (kernel radii $R$, inner fractions $r_k$, growth midpoints $m_k$, weight matrix $w_{ij}$).
- **Projection $\pi: E \to B$:** simulate the genotype, measure the phenotype.
- **Fiber $F_b$:** all genotypes that produce phenotype $b$.

If the fiber bundle is non-trivial — sections tear, transport has holonomy, fibers are thick — the space has geometric structure that a shape catalog or connectivity score misses.

## What we measured

### Persistent homology

We computed persistent homology on pairwise genotype distances in a 96-creature cohort.

- **$H_0$ (components):** two topologically separated families across a wide parameter range — the "drifter-triplet" and "eddy-triplet" families. These are distinct islands in morphospace, not a continuous cloud.
- **$H_1$ (cycles):** non-contractible loops — closed paths through morphospace that enclose regions of non-viability. The cycle-lift pipeline maps these back to concrete specimen pairs.

![Persistence barcodes showing H0 and H1 features](../../assets/blog/lenia-morphospace-report/fig-persistence.svg)

### Holonomy

We measured parallel transport around a square loop in parameter space, varying the growth midpoint $m$ and height $h$. A control traversed a single axis and returned.

Both return to the starting phenotype. But the loop produced an endpoint state closure of **0.500** versus the control's **0.250**. The 0.250 surplus is the holonomy signal — curvature of the bundle integrated over the loop area.

Concretely: transporting *serene-dancer* through a loop of other phenotypes and back returns the same shape, but its internal parameters drift (radius $R$ shifts from 10.57 to 10.61). The form is preserved; the implementation has changed.

![Holonomy experiment showing 0.250 surplus in state closure](../../assets/blog/lenia-morphospace-report/fig-holonomy.svg)

### Substrate independence

Thick fibers mean different genotypes produce the same phenotype. *crystal-walker* and *mystic-pattern* have nearly identical velocities and spatial extents:

| Metric | crystal-walker | mystic-pattern |
|---|---|---|
| Velocity | 0.0101 | 0.0101 |
| Arrangement | Cross-coupled | Balanced |

Phenotype distance: **0.218**. Interface distance (normalized genotype delta): **1.106** — 5× larger. Two fundamentally different internal architectures achieve the same morphological outcome.

### Bridge studies

Linear interpolation between two creature genotypes tests whether the section tears: intermediate genotypes between seed 196 and seed 241 collapsed into non-viable regions instead of producing viable intermediates. These barriers are topological obstructions in the bundle.

![Fiber bundle schematic](../../assets/blog/lenia-morphospace-report/fig-fiber-bundle.svg)

![Two sections through the fiber bundle](../../assets/blog/lenia-morphospace-report/fig-sections.svg)

![Bridge study showing a failure band](../../assets/blog/lenia-morphospace-report/fig-transport.svg)

## Polynomial functors and arrangement

[Spivak (2022)](https://topos.institute/people/david-spivak/Levin20220607.pdf) gives the algebraic counterpart. A polynomial functor $p = \sum_{i \in P} y^{F[i]}$ encodes an interface: $P$ is what the system can output, $F[i]$ is what it can sense. In Lenia, each kernel is an interface — narrow steepness ($s = 0.058$) gives a limited sensorium, broad steepness ($s = 0.173$) responds to a wider neighbor-density range.

The weight matrix $w_{ij}$ is the **arrangement**: the wiring diagram coupling kernel interfaces. This decomposes the Lenia genotype into interface parameters (per-kernel $r, m, s, h$) and arrangement parameters (the matrix $w$). A bridge-study failure can then be diagnosed as interface obstruction (the sensors became non-functional) or arrangement obstruction (the wiring became incoherent).

![Three weight matrices with nearly identical phenotypes but distinct arrangements](../../assets/blog/lenia-morphospace-report/fig-weight-matrices.svg)

## What this connects to

The fiber-bundle picture maps onto Levin's questions:

- **Attractor discreteness** maps to $H_0$ components in persistent homology. If these persist across different Lenia rule families, discreteness is a topological property of the space, not a quirk of one physics.
- **Navigation hierarchy** maps to geodesics in the fiber bundle with a metric. Greedy navigators versus topology-aware ones become well-defined comparison classes.
- **Anatomical compilers** become section-finding problems. The Poly decomposition splits this into identifying a viable arrangement class, then optimizing interfaces within it.

The Poly decomposition splits the genotype into arrangement class and interface parameters. A higher level chooses which wiring diagram to use; a lower level tunes the kernel parameters inside it. This maps onto Levin's competency hierarchy — a "surgeon" sets the broad architecture, a "cell" optimizes within it — but here the levels are operationalized as separable parts of a parameter vector.

## Next

- Physics invariance: do $H_0 / H_1$ structures persist across different Lenia rule families and kernel types?
- Agda formalization: turning the fiber-bundle observations into verified theorems.
- The inverse problem: finding sections for arbitrary target phenotypes — a first anatomical compiler for Lenia.
