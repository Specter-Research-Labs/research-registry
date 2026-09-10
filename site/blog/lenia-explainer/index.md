---
title: "A Primer on Lenia"
release: "draft"
summary: A technical primer on Lenia and Flow Lenia -- continuous cellular automata, quality-diversity search, and how Specter Labs uses them to build an atlas of artificial life.
toc: true
bibliography: references.bib
link-citations: true
reference-section-title: References
---

<link rel="stylesheet" href="lenia-explainer.css" />

# A Primer on Lenia

A Lenia creature keeps its shape by continually remaking it. Each part responds to nearby activity, and those local changes can sustain a body that moves across the field. There is no separate instruction describing its outline or steering its path [@chan2019].

How can a rule about a neighbourhood produce something that behaves as a whole? We can investigate by changing that rule, watching the body reorganize, and searching for other forms the system can support. This primer develops the mechanics behind those experiments, from a single local update to an archive of discovered creatures.

<div class="lenia-widget" data-widget="creaturewall">
<noscript><p>Live Lenia gallery requires JavaScript.</p></noscript>
</div>

<details>
<summary>About this simulation</summary>
<p>This browser simulation applies Flow Lenia transport to an Orbium-derived rule. It is an adapted example; the original Orbium can be explored in <a href="https://chakazul.github.io/Lenia/JavaScript/Lenia.html">Chan’s catalogue</a>. The browser implementation has not been validated against the research CLI. The other demonstrations identify their algorithms and any illustrative data where they appear.</p>
</details>

## From a local rule to a moving body

Game of Life uses binary cells on a grid and a discrete update rule. Lenia replaces the binary state with concentrations between 0 and 1 and uses smooth functions to compute their change. The implementations here still sample space on a grid and advance time in finite steps. A kernel `K` weights the neighbourhood; a growth function `G` converts that weighted concentration into a local update [@chan2019].

In basic Lenia, the kernel and growth function specify the update rule. Movement and body shape are not programmed as separate behaviours, but the rule is not the complete creature: its initial field and numerical settings also matter. Chan's [interactive catalogue](https://chakazul.github.io/Lenia/JavaScript/Lenia.html) shows the variety of persistent patterns those choices can produce. Multi-channel versions couple several fields; Flow Lenia changes the update to conserve and transport matter.

Changing the rule lets us explore which interactions sustain a body and which break it apart. Saving the rule together with its initial field lets us return to the same experiment. Later, we will use that ability to search for many different bodies and compare how they behave.

### The kernel -- convolution as neighborhood sensing

Each cell first measures its neighbourhood. Convolution combines the state grid `A` with a kernel `K` to give a potential `U(x, y)`. Many Lenia kernels emphasize one or more rings around the cell, so concentration at a characteristic distance can matter more than concentration immediately beside it. Changing the ring widths and radii changes those interactions.

The ring is built as a mixture of Gaussians indexed by their position along the radius. For each Gaussian `g`, three parameters: an amplitude `b[g]`, a radial center `a[g]` saying where along the ring it peaks, and a width `w[g]` saying how sharp the peak is. A base radius `R` (in grid cells) and a per-kernel fraction `r` set the effective kernel size, so the actual reach in pixels is `R * r`. The kernel gets normalized so the weights sum to 1 and the potential `U` stays a weighted average that does not blow up with kernel size.

$$U(x, y) = \sum_{(dx, dy)} K(dx, dy)\, A(x + dx,\, y + dy)$$

Adding kernels and channels enlarges the rule space. Each kernel has its own radial profile, growth parameters and input/output connections. Direct convolution becomes expensive as the grid and neighbourhood grow; FFT-based convolution is one implementation strategy used to evaluate these interactions efficiently.

<div class="lenia-widget" data-widget="kernel" data-defaults='{"R":13,"r":0.5,"b":[1],"w":[0.2],"a":[0.5]}'>
<noscript><p>Interactive kernel visualizer requires JavaScript.</p></noscript>
</div>

### The growth function -- the local update rule

Once a cell has its potential `U`, the growth function `G(U)` turns that number into a signed rate of change. The shape is a shifted bell curve minus a baseline:

$$G(U) = \bigl(2\exp\!\bigl(-\tfrac{(U - \mu)^2}{2\sigma^2}\bigr) - 1\bigr) \cdot h$$

When `U` lands near the preferred neighbor density `mu`, growth is positive and the cell fills in. When `U` is far from `mu`, growth is negative and the cell actively shrinks, with the decay rate saturating at `-h` once it gets far enough away. So three numbers per kernel decide the cell's personality: `mu` (the sweet spot for how crowded its shell should be), `sigma` (how picky it is about hitting that target), and `h` (how aggressively it grows or decays once it has decided).

In basic Lenia, concentration can grow or decay according to this response. Whether a localized pattern persists depends on the entire evolving field: it must continually produce neighbourhood values that sustain it. A narrow growth window alone does not establish the geometry or dimension of the viable parameter set.

With multiple kernels and channels the bookkeeping is a connectivity matrix: each kernel reads from one channel and contributes to one or more output channels, and the per-cell update is the sum of contributions across kernels (with `dt` scaling and clamping to `[0, 1]`). The Aquarium creature, for instance, runs 15 kernels across 3 channels with cross-channel connections, so a single cell update has fifteen separate convolution reads and writes feeding into three output channels.

<div class="lenia-widget" data-widget="growth" data-defaults='{"m":0.15,"s":0.017,"h":0.1}'>
<noscript><p>Interactive growth function explorer requires JavaScript.</p></noscript>
</div>

<figure class="sl-diagram" aria-label="The basic Lenia update step as a dataflow pipeline">
<svg viewBox="0 0 760 230" xmlns="http://www.w3.org/2000/svg" role="img" font-family="var(--sl-font-mono)">
  <defs>
    <marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--doc-ink)"/></marker>
    <marker id="ahA" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--doc-accent)"/></marker>
  </defs>
  <g fill="var(--doc-paper)" stroke="var(--doc-ink)" stroke-width="1.5">
    <rect x="5"   y="55" width="120" height="78"/>
    <rect x="215" y="55" width="120" height="78"/>
    <rect x="425" y="55" width="120" height="78"/>
    <rect x="635" y="55" width="120" height="78"/>
  </g>
  <g text-anchor="middle" fill="var(--doc-ink)">
    <text x="65"  y="90"  font-size="26">A</text>
    <text x="275" y="90"  font-size="26">U</text>
    <text x="485" y="90"  font-size="24">&#916;A</text>
    <text x="695" y="90"  font-size="26">A&#8242;</text>
  </g>
  <g text-anchor="middle" fill="var(--doc-muted)" font-size="9.5" letter-spacing="1">
    <text x="65"  y="116" text-transform="uppercase">STATE &#183; t</text>
    <text x="275" y="116" text-transform="uppercase">POTENTIAL</text>
    <text x="485" y="116" text-transform="uppercase">GROWTH RATE</text>
    <text x="695" y="116" text-transform="uppercase">STATE &#183; t+dt</text>
  </g>
  <g stroke="var(--doc-ink)" stroke-width="1.5" fill="none">
    <line x1="125" y1="94" x2="213" y2="94" marker-end="url(#ah)"/>
    <line x1="335" y1="94" x2="423" y2="94" marker-end="url(#ah)"/>
  </g>
  <line x1="545" y1="94" x2="633" y2="94" stroke="var(--doc-accent)" stroke-width="2" fill="none" marker-end="url(#ahA)"/>
  <g text-anchor="middle" font-size="12" fill="var(--doc-ink)">
    <text x="169" y="80">&#8859; K</text>
    <text x="379" y="80">G( &#183; )</text>
    <text x="589" y="80" fill="var(--doc-accent)">&#183; dt, clamp</text>
  </g>
  <g text-anchor="middle" font-size="9" fill="var(--doc-muted)" letter-spacing="0.6">
    <text x="169" y="111" text-transform="uppercase">CONVOLVE / RING</text>
    <text x="379" y="111" text-transform="uppercase">BELL CURVE</text>
    <text x="589" y="111" text-transform="uppercase">[0, 1]</text>
  </g>
  <path d="M695 133 V178 H65 V133" stroke="var(--doc-ink)" stroke-width="1.2" fill="none"
        stroke-dasharray="4 3" marker-end="url(#ah)"/>
  <text x="380" y="172" text-anchor="middle" font-size="9.5" fill="var(--doc-muted)"
        letter-spacing="1" text-transform="uppercase">NEXT STEP</text>
  <text x="380" y="210" text-anchor="middle" font-size="11" fill="var(--doc-muted)">
    basic Lenia writes growth straight into the state along the orange arrow;
  </text>
  <text x="380" y="225" text-anchor="middle" font-size="11" fill="var(--doc-muted)">
    Flow Lenia keeps A &#8594; U &#8594; &#916;A and replaces that one arrow with mass transport.
  </text>
</svg>
<figcaption>The whole basic update is four fields and three operations. K and G specify the basic local rule. The initial field and numerical settings determine the rollout on which we observe a body.</figcaption>
</figure>

### Flow Lenia -- mass-conserving transport (Plantec et al., 2023)

Basic Lenia does not conserve mass. The update `state += dt * G(U)` can create concentration at the front of a moving pattern and remove it at the back. Flow Lenia instead redistributes existing matter [@plantec2023]. This makes material exchange and the movement of a persistent pattern distinct quantities that can be followed through the simulation.

Flow Lenia (Plantec et al., 2023) fixes this by separating *what should grow* from *where the mass actually goes*. The growth function still produces a desired rate, but instead of writing that rate straight into the state, we use it to build a velocity field, then transport mass along that field with an explicit redistribution step. One simulation step becomes two passes.

The first pass runs kernel convolutions and growth functions to form a growth-affinity field, written here as `H`. Unlike the earlier convolution potential `U`, `H` already includes the growth response. Its gradient attracts matter toward higher affinity. A density-dependent pressure term opposes crowding. Schematically, with total density `M` and a density-dependent weight `alpha`, the velocity combines these contributions:

$$v(x, y, c) = (1 - \alpha)\,\nabla H_c \;-\; \alpha\,\nabla M$$

At low density the affinity contribution dominates; at high density the negative density gradient pushes matter away from crowded regions. The exact discretization and pressure parameters belong to the implementation, not to a universal numerical constant of Lenia.

The second pass redistributes matter along the velocity field. In the illustrated box-overlap scheme, each source cell contributes to destination cells in proportion to the overlap of its displaced box with theirs. The contributions partition the source mass. Conservation follows from that partition when the search neighbourhood and boundary handling include all destinations; floating-point arithmetic still introduces numerical error.

<figure class="sl-diagram" aria-label="Flow Lenia mass transport by box overlap">
<svg viewBox="0 0 700 366" xmlns="http://www.w3.org/2000/svg" role="img" font-family="var(--sl-font-mono)">
  <defs>
    <marker id="ov" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0 0L10 5L0 10z" fill="var(--doc-accent)"/></marker>
  </defs>
  <g stroke="var(--doc-rule)" stroke-width="1" fill="none">
    <rect x="120" y="60"  width="80" height="80"/>
    <rect x="200" y="60"  width="80" height="80"/>
    <rect x="280" y="60"  width="80" height="80"/>
    <rect x="120" y="140" width="80" height="80"/>
    <rect x="280" y="140" width="80" height="80"/>
    <rect x="120" y="220" width="80" height="80"/>
    <rect x="200" y="220" width="80" height="80"/>
    <rect x="280" y="220" width="80" height="80"/>
  </g>
  <rect x="200" y="140" width="80" height="80" fill="var(--doc-overlay-soft)" stroke="var(--doc-ink)" stroke-width="2"/>
  <rect x="280" y="220" width="80" height="80" fill="none" stroke="var(--doc-ink)" stroke-width="1.6"/>
  <rect x="185" y="125" width="80" height="80" fill="none" stroke="var(--doc-accent)" stroke-width="1.6" stroke-dasharray="5 3"/>
  <rect x="200" y="140" width="65" height="65" fill="var(--doc-accent)" fill-opacity="0.22" stroke="none"/>
  <line x1="320" y1="260" x2="232" y2="172" stroke="var(--doc-accent)" stroke-width="2" marker-end="url(#ov)"/>
  <g font-size="11" fill="var(--doc-ink)">
    <text x="240" y="135" text-anchor="middle" fill="var(--doc-muted)" font-size="9.5" letter-spacing="1" text-transform="uppercase">TARGET CELL</text>
    <text x="300" y="316" text-anchor="middle" fill="var(--doc-muted)" font-size="9.5" letter-spacing="0.6" text-transform="uppercase">NEIGHBOR MASS, CURRENT POSITION</text>
    <text x="338" y="214" fill="var(--doc-accent)" font-size="11.5">dt &#183; v</text>
    <text x="338" y="229" fill="var(--doc-muted)" font-size="9">bounded transport step</text>
  </g>
  <line x1="232" y1="172" x2="470" y2="120" stroke="var(--doc-rule-strong)" stroke-width="1"/>
  <text x="476" y="118" font-size="11" fill="var(--doc-ink)">overlap area = mass this</text>
  <text x="476" y="134" font-size="11" fill="var(--doc-ink)">neighbor delivers here</text>
  <text x="350" y="344" text-anchor="middle" font-size="10.5" fill="var(--doc-muted)">
    sum the overlaps from every neighbor within dd, divide by 4&#963;&#178;,
  </text>
  <text x="350" y="359" text-anchor="middle" font-size="10.5" fill="var(--doc-muted)">
    and that sum is the new state. mass is conserved by construction.
  </text>
</svg>
<figcaption>One transport step for one cell. The growth-affinity field helps determine velocity. This step redistributes existing matter by sliding each source box by dt&#183;v and counting how much lands inside the destination cell.</figcaption>
</figure>

Transport depends on the timestep, the redistribution kernel, the neighbourhood used to collect incoming mass, and the density at which pressure becomes dominant. These must be recorded with a replay. Periodic boundaries wrap matter across opposite edges; a wall requires its own boundary rule and does not guarantee that a creature will bounce or recover.

The extra transport work changes runtime as well as behaviour. Its cost depends on grid size, channel count, neighbourhood and hardware; two conceptual passes do not imply a fixed twofold slowdown.

The next widget contrasts additive growth with a deliberately simpler control: rescale the whole field to its previous total after each update. This illustrates why a fixed mass total alone does not implement Flow Lenia. It lacks the local velocity field and transport law described above.

<div class="lenia-widget" data-widget="massconservation">
<noscript><p>Mass conservation comparison requires JavaScript.</p></noscript>
</div>

<div class="lenia-widget" data-widget="sandbox" data-creature="orbium">
<noscript><p>Live Lenia simulation requires JavaScript and WebGPU.</p></noscript>
</div>

## The search problem -- parameter space and fitness

A reproducible Lenia experiment needs an update rule, an initial field and numerical settings. We call the rule parameters the **genotype** by analogy with biology. The **phenotype** is the form or behaviour that emerges, not the initial condition. A seed and an initialization recipe can specify the initial field compactly, while the grid, timestep and boundary rules remain part of the run configuration.

Uniform sampling provides a useful baseline, but it can spend much of its budget on outcomes outside the behaviour we want to study. In basic Lenia these may disappear or saturate. In a mass-conserving Flow Lenia run, losing a coherent body does not mean losing the total matter: it may disperse or break into fragments. Search therefore needs an explicit definition of the outcome worth retaining, rather than treating nonzero mass as life.

To say anything quantitative about what came out of a run, we measure each simulation with a fixed battery (the `SimulationMetrics` struct in the lenia-swarm code). Most of it is bookkeeping you never read directly, but it answers four questions:

| Question | Fields |
|---|---|
| Did anything survive? | `massMean`, `massStd`, `massMin`, `massMax` |
| How big, what shape? | `occupancyMean`, `varianceMean`, radius of gyration; plus Hu moments `hu1..hu7`, Flusser invariants `flusser1..flusser4` and `momentAnisotropy` for shape up to rotation and reflection |
| Moving or just shimmering? | `speedMean`, `pathLength`, `displacement`, `centerVelocity`, `headingRad` |
| One thing or many? | flood-fill `componentCount` and largest-component dominance; plus activity entropy, complexity decompositions, `isStable`, `survivalSteps` |

Evaluation settings—including warm-up, recording interval and thresholds—are part of the measurement. A candidate that persists for a short scout run may fail during a longer replay. Report those horizons with the result rather than treating one default evaluation as a universal survival test.

### Three search strategies illustrated

Uniform random sampling tells us what the chosen parameter distribution produces. Evolution Strategies use batches of nearby candidates to improve an objective, but an objective alone need not reward a diverse collection. MAP-Elites retains good candidates in many behavioural niches, allowing a catalogue of different outcomes rather than only the highest-scoring specimen.

The demonstration uses a synthetic two-dimensional fitness landscape. It compares uniform sampling, a simple local hill climber, and archive-based variation with one new fitness evaluation per step. The hill climber is not a full Evolution Strategy, and this example does not benchmark the algorithms on Lenia.

<div class="lenia-widget" data-widget="search" data-steps="200" data-auto-play="true">
<noscript><p>Interactive search comparison requires JavaScript.</p></noscript>
</div>

## MAP-Elites and Quality-Diversity

Quality-Diversity flips the usual optimization question. Instead of asking "which parameter setting maximizes fitness?", it asks "what is the best creature we can find *for each kind of behavior*?". The archive is structured by behavioral descriptors (speed, mass, gyration, symmetry, the oscillation frequency of the mass over time, and so on), and competition is local within a niche, so an eligible candidate in an empty niche can be retained even if other niches contain higher-scoring candidates. The QD-score is the total fitness summed over all niches, which rewards quality and diversity at the same time. A run that fills 40 of 64 niches with average fitness 0.7 scores higher than a run that fills 60 of 64 with average 0.3, even though it covers less ground. Coverage with nothing good in it is not the goal, and one brilliant creature in an empty archive is not either.

MAP-Elites is one widely used algorithm for this purpose [@mouret2015]. The archive is an array of `K` cells, each storing the best `(genotype, fitness, descriptor)` it has seen, with `K` usually between 1024 and 16384. The four-step loop is select a random occupied cell, vary its genotype, evaluate the child in simulation, and place the child into the nearest niche if that niche is empty or if the child beats the incumbent. For a fixed archive and stored evaluations, replacement only improves the recorded incumbent in each cell. Re-evaluation, noisy fitness or changed descriptors require separate handling.

<p class="sl-skip">The next two sections, CVT and isoline variation, are implementation detail. You can skip them on a first read and lose nothing conceptual: they cover how the archive is partitioned and how children are mutated, not why any of it works.</p>

### CVT -- partitioning descriptor space

The naive way to partition descriptor space is a regular grid, but that costs `n^D` cells once you have more than two or three descriptors and most of those cells will never be reached. A centroidal Voronoi tessellation gives you `K` cells regardless of how many descriptors you use [@vassiliades2016]. You sample a few thousand points from where the descriptors actually live, run Lloyd's algorithm (assign each sample to the nearest centroid, then move each centroid to the mean of its assigned samples, repeat), and the centroids partition the sampled distribution; the cells need not have equal volume or equal probability. Production runs pre-compute centroids once in Python with pyribs and reuse the same `centroids.npy` across campaigns.

This two-dimensional widget approximates uniform-area Lloyd updates on a fixed 128 × 128 sample grid. It illustrates centroid relaxation rather than reproducing the production descriptor distribution.

<div class="lenia-widget" data-widget="cvt" data-centroids="64" data-samples="5000">
<noscript><p>Interactive CVT builder requires JavaScript.</p></noscript>
</div>

### The MAP-Elites loop

The widget below generates a synthetic teaching sequence on 64 Voronoi cells. Its scores and descriptors are illustrative, not measurements from Lenia creatures; placements follow the nearest-cell and elite-replacement rules. Watch which niches receive candidates, when an incumbent is replaced, and where the map remains empty. An empty niche is an absence from this search, not proof that its behaviour is impossible.

<div class="lenia-widget" data-widget="mapelites" data-centroids="64">
<noscript><p>Interactive MAP-Elites step-through requires JavaScript.</p></noscript>
</div>

### Isoline variation (Vassiliades and Mouret, 2018)

Isoline variation combines an isotropic perturbation with a displacement along the line joining two archived candidates [@vassiliades2018]. The line term uses relationships already present in the archive. Whether that helps depends on how those relationships align with useful changes in behaviour; it is a search operator to compare, not a guarantee of better offspring.

$$\text{child} = A + \mathcal{N}(0, \sigma_{\text{iso}}^2 I) + \mathcal{N}(0, \sigma_{\text{line}}^2) \cdot \widehat{(B - A)}$$

This widget uses a normalized-direction variant: the standard line operator uses the unnormalized difference `B - A`. Here `A` is the parent and `B` is a second creature pulled from a different niche, and `widehat{(B - A)}` is the unit vector pointing from `A` toward `B`. The isotropic term (`sigma_iso` typically `0.005`) does fine-tuning within the parent's niche. The directional term (`sigma_line` typically `0.05`) jumps along the line between two creatures whose genotypes already differ in some behaviorally-meaningful way, which provides a candidate direction to test. A difference between archived genotypes need not change every measured behaviour. The slider widget below makes the effect of the two sigmas legible at a glance.

<div class="lenia-widget" data-widget="isoline" data-iso-sigma="0.03" data-line-sigma="0.12">
<noscript><p>Interactive isoline visualizer requires JavaScript.</p></noscript>
</div>

## The research ladder

Flow Lenia plus MAP-Elites gets us solitary creatures that move. Everything past that is about extending what a creature can do, what kind of world it lives in, and what we let the search figure out for itself.

### Sensorimotor Lenia

A moving Flow Lenia pattern can already interact with other matter or an imposed boundary. Sensorimotor variants make particular environmental signals available to the update rule and search for responses to them. Food seeking, obstacle avoidance and other tasks require defined environments and evaluation protocols; none follows merely from adding an input channel.

### Ecological search

An ecological experiment places multiple interacting patterns in a shared world. Localized rule parameters allow different rule identities to coexist within Flow Lenia. Competition, material exchange or sustained coexistence must then be measured from the dynamics. Several channels or many kernels do not by themselves establish distinct species or symbiosis.

### AURORA -- learned descriptors

MAP-Elites needs you to pick the descriptors up front, and the choice biases everything downstream. AURORA replaces hand-picked descriptors with learned ones: train a dimensionality-reduction model, such as an autoencoder, on the behavioural observations from a run, use the learned coordinates as descriptors, continue quality-diversity search, retrain, and repeat [@cully2019]. The learned coordinates depend on the observations, training objective and model; they remain a choice of representation that needs validation.

### The atlas

The atlas is where all of this ends up. Every creature we keep gets stored with its genotype, phenotype, full descriptor vector, the ecology it came from, the campaign that produced it, a replay you can scrub, and the anatomy panels (mass, components, moments) that summarize what it does. The format (`SavedCreature` with `ParamsPayload`, `InitConfig`, `SimulationMetrics`, score, weights, `configHash`) is meant to be both a scientific dataset and an interactive catalog, so the same record renders as a row in a SQLite query and as a card on a creature page.

## Running it -- campaigns at scale

Campaigns separate discovery from verification. Short evaluations can rank large numbers of candidates; longer replays then check whether selected bodies persist and whether their saved records reproduce the observations. Parallel workers accelerate the evaluations, while the archive records the candidates selected under a particular descriptor and scoring scheme.

Reproducibility requires more than a fixed seed. The rule, initial condition, run configuration and backend must all be recorded, and replay agreement must be tested. The [Lenia dossier](/dossiers/lenia-swarm/) links the current experiments and their evidence.

## What the atlas is for

The archive lets us compare observed forms with the rules and histories that produced them. Do neighbouring rules make neighbouring bodies? Can similar-looking bodies respond differently to the same obstacle? Can we find a rule that produces and maintains a requested shape?

A sampled map can suggest connected regions or persistent gaps, but those features depend on sampling, descriptors and distance. It does not establish a smooth manifold of all viable creatures, or prove that unobserved forms cannot exist. The [current morphospace report](/dossiers/lenia-swarm/morphospace/) examines that distinction using 25,167 Flow Lenia observations and two external shape collections.


<script src="lenia-gpu.js"></script>
<script src="lenia-explainer.js"></script>
