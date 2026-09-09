---
title: "A Primer on Lenia"
release: "draft"
summary: A technical primer on Lenia and Flow Lenia -- continuous cellular automata, quality-diversity search, and how Specter Labs uses them to build an atlas of artificial life.
toc: true
---

<link rel="stylesheet" href="lenia-explainer.css" />

# A Primer on Lenia

<div class="lenia-widget" data-widget="creaturewall">
<noscript><p>Live Lenia gallery requires JavaScript.</p></noscript>
</div>

## What Game of Life would look like if physics were continuous

Game of Life is a discrete grid of dead-or-alive cells updated by a tiny lookup table, whereas Lenia (Bert Chan, 2018) turns every one of those knobs at once: cells hold concentrations in `[0, 1]`, time advances in fractional steps of roughly `0.1` to `0.2`, and two smooth functions replace the table. The kernel `K` reads a weighted neighborhood; the growth function `G` turns that reading into local growth or decay.

There are no movement rules, body plans, or replication instructions hidden elsewhere. Orbium translates, geminium splits, and scutium walks because the same update takes different numbers; [Chan's canonical demo](https://chakazul.github.io/Lenia/JavaScript/Lenia.html) showcases dozens of further examples under its deliberately silly taxonomy (Orbiformes, Scutiformes, Anuliformes). Multi-channel Lenia adds interacting concentration fields, Flow Lenia adds a velocity field so mass moves rather than appearing and disappearing, and sensorimotor Lenia couples those fields to an environment.

Most parameter settings still die or saturate. Persistent creatures occupy a thin, curved manifold inside that mostly dead space, and the simulation is here because you should watch the object before reading a page of equations about it. Once there are enough survivors, the work becomes less about finding one creature and more about mapping the manifold they share.

### The kernel -- convolution as neighborhood sensing

For every location, the engine convolves the state grid `A` with a radial kernel `K` and produces one potential value, `U(x, y)`. The kernel is a ring rather than a blob: it is zero at the center, peaks at a characteristic radius, then falls away again, so the update responds to a shell of nearby cells instead of the cell's immediate neighbors. That is what allows standing-wave patterns to lock into creatures instead of dissolving into diffusion.

The ring is built as a mixture of Gaussians indexed by their position along the radius. For each Gaussian `g`, three parameters: an amplitude `b[g]`, a radial center `a[g]` saying where along the ring it peaks, and a width `w[g]` saying how sharp the peak is. A base radius `R` (in grid cells) and a per-kernel fraction `r` set the effective kernel size, so the actual reach in pixels is `R * r`. The kernel gets normalized so the weights sum to 1 and the potential `U` stays a weighted average that does not blow up with kernel size.

$$U(x, y) = \sum_{(dx, dy)} K(dx, dy)\, A(x + dx,\, y + dy)$$

One channel and one Gaussian take roughly eight continuous parameters. Aquarium uses fifteen kernels across three channels, more than a hundred continuous values plus a small connectivity table. A direct 128x128 convolution with a radius-7 kernel costs about 3.7M multiply-adds per step; fifteen of them would cost roughly 55M before accounting for the larger grid and wider kernels Aquarium uses. The engine uses FFT convolution instead, turning that direct cost into an `N log N` one and making the large campaigns feasible on GPU.

<div class="lenia-widget" data-widget="kernel" data-defaults='{"R":13,"r":0.5,"b":[1],"w":[0.2],"a":[0.5]}'>
<noscript><p>Interactive kernel visualizer requires JavaScript.</p></noscript>
</div>

### The growth function -- the local update rule

Once a cell has its potential `U`, the growth function `G(U)` turns that number into a signed rate of change. The shape is a shifted bell curve minus a baseline:

$$G(U) = \bigl(2\exp\!\bigl(-\tfrac{(U - \mu)^2}{2\sigma^2}\bigr) - 1\bigr) \cdot h$$

Near the preferred neighbor density `mu`, `G(U)` is positive and the cell fills in; far away, it is negative and the cell shrinks, bottoming out at `-h`. `mu` sets the preferred crowding, `sigma` sets how narrow that preference is, and `h` sets the rate of growth or decay.

The bell curve leaves most of Lenia empty: outside a narrow concentration band, the update pulls values toward zero. A creature survives only by maintaining the right density at the right distance around its entire boundary.

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
<figcaption>Basic Lenia is four fields and three operations. The later sections either search over K and G or replace the final write with mass transport.</figcaption>
</figure>

### Flow Lenia -- mass-conserving transport (Plantec et al., 2023)

Basic Lenia does not conserve mass. `state += dt * G(U)` creates mass at the front of a moving creature and removes it at the back, which is enough for an orbium glider but falls apart as soon as creatures need to eat, exchange material, or collide.

Flow Lenia (Plantec et al., 2023) keeps the growth calculation but stops writing it directly into the state. It first turns it into a velocity field, then transports mass along that field, so each simulation step has two passes.

The first pass runs the usual kernel convolutions and growth functions, but instead of updating the state, it computes per-cell velocities. The velocity is a blend of two gradients: `nabla_U`, pointing toward where growth wants to happen (mass attracts itself toward growth maxima), and `nabla_A`, pointing toward where mass already is (mass repels itself via pressure). A mass-dependent factor `alpha = clamp((M / thetaA)^n, 0, 1)` decides the mix:

$$v(x, y, c) = (1 - \alpha)\,\nabla U \;-\; \alpha\,\nabla A$$

Low-density regions follow the growth gradient (the creature fills inward), high-density regions follow the pressure gradient (the creature pushes outward). Both gradients are computed with a Sobel filter on the relevant field.

The second pass does the actual transport. For each cell, look at every neighbor within distance `dd`, displace that neighbor's mass by `dt * v` (clamped so a step never moves more than one cell), and compute the overlap area between the neighbor's displaced square and the current cell. The accumulated overlapping mass, divided by the normalization `4 * sigma^2`, is the new state. The whole step is bilinear interpolation done by box intersection, which keeps total mass conserved to machine precision instead of by accident.

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
    <text x="338" y="229" fill="var(--doc-muted)" font-size="9">clamped &#8804; 1 cell</text>
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
<figcaption>One transport step for one cell. The growth function decided how much mass should exist; this step decides where it physically goes, by sliding each neighbor's square by dt&#183;v and counting how much of it lands inside the cell.</figcaption>
</figure>

A few parameters control how that all behaves. `dt` (around `0.1` to `0.2`) is the simulation timestep, `dd` (typically `5`) is how far each cell looks for incoming mass, and `sigma` (`0.65`) controls how soft the box overlap is. `n` and `thetaA` set where on the mass curve the velocity stops following growth and starts pushing outward, so a low `thetaA` makes creatures disperse quickly and a high one lets them clump. Border mode is `torus` for a world that wraps and `wall` for one that does not, and the difference is the difference between a creature drifting away forever and a creature bouncing off the edge of the world.

The two-pass structure also costs roughly double per step compared to basic Lenia, which is the price for actually owning your mass.

<div class="lenia-widget" data-widget="massconservation">
<noscript><p>Mass conservation comparison requires JavaScript.</p></noscript>
</div>

<div class="lenia-widget" data-widget="sandbox" data-creature="orbium">
<noscript><p>Live Lenia simulation requires JavaScript and WebGPU.</p></noscript>
</div>

## Finding creatures without guessing forever

A Lenia creature is two things bolted together: a genotype (the parameters of `K` and `G`) and a phenotype (the initial condition the simulation starts from). A single-channel single-kernel creature has about eight continuous genotype numbers, three-Gaussian kernels push that to a dozen, and the Aquarium-style multi-channel creatures land near 120 parameters plus a small integer connectivity table saying which channels read into which. The phenotype is much smaller: an integer PRNG seed, a few patch centers and radii, and the uniform range used to fill those patches. Grid size, `dt`, `dd`, `sigma`, `n`, `thetaA`, and border mode are run config and stay fixed across a campaign.

Most of this space is dead. Random settings either decay to zero within fifty steps or saturate into uniform soup, while structured creatures sit on a thin manifold that uniform sampling almost never hits. Our `flowlenia-ecology-2025` sweep narrows `r` to `[0.2, 1.0]`, `b` to `[0.001, 1.0]`, `w` to `[0.01, 0.5]`, `a` to `[0, 1]`, `mu` to `[0.05, 0.5]`, `sigma` to `[0.001, 0.18]`, `h` to `[0.01, 1.0]`, and `R` to `[2, 25]`; the dead/alive ratio is still brutal.

To say anything quantitative about what came out of a run, we measure each simulation with a fixed battery (the `SimulationMetrics` struct in the lenia-swarm code). Most of it is bookkeeping you never read directly, but it answers four questions:

| Question | Fields |
|---|---|
| Did anything survive? | `massMean`, `massStd`, `massMin`, `massMax` |
| How big, what shape? | `occupancyMean`, `varianceMean`, radius of gyration; plus Hu moments `hu1..hu7`, Flusser invariants `flusser1..flusser4` and `momentAnisotropy` for shape up to rotation and reflection |
| Moving or just shimmering? | `speedMean`, `pathLength`, `displacement`, `centerVelocity`, `headingRad` |
| One thing or many? | flood-fill `componentCount` and largest-component dominance; plus activity entropy, complexity decompositions, `isStable`, `survivalSteps` |

The default evaluation is 200 steps with 100 warmup, recording every 50, occupancy threshold 0.05, scoring `mass_mean: 1.0` with filters `mass_min: 0.01`, `gyration_min: 0.1`, `gyration_max: 180`. Almost every research question we ask is just a different choice of score weights and filters over this same battery, which is the entire reason it stays fixed.

### Three search strategies compared

Uniform random sampling establishes the problem and little else. Evolution Strategies climb from a seed toward one fitness peak, then stay there; Lenia has too many distinct kinds of creature for one peak to be an adequate answer. MAP-Elites keeps a grid of behavioral niches and fills them in parallel, producing a catalogue instead of one champion.

<div class="lenia-widget" data-widget="search" data-steps="200" data-auto-play="true">
<noscript><p>Interactive search comparison requires JavaScript.</p></noscript>
</div>

## MAP-Elites and Quality-Diversity

Quality-Diversity keeps the best creature found for each kind of behavior, rather than reducing the whole search to one fitness winner. The archive is indexed by descriptors such as speed, mass, gyration, symmetry, and mass oscillation, and selection is local: a merely adequate creature can survive in an empty niche. QD-score adds fitness over occupied niches, so 40 niches averaging 0.7 beat 60 averaging 0.3; a full archive of junk and one brilliant creature in an empty archive are both failures.

MAP-Elites (Mouret and Clune, 2015) is the canonical algorithm. The archive is an array of `K` cells, each storing the best `(genotype, fitness, descriptor)` it has seen, with `K` usually between 1024 and 16384. The four-step loop is select a random occupied cell, vary its genotype, evaluate the child in simulation, and place the child into the nearest niche if that niche is empty or if the child beats the incumbent. Coverage and per-cell fitness both go up monotonically, which is what makes the algorithm well-behaved to watch.

<p class="sl-skip">The next two sections, CVT and isoline variation, are implementation detail. You can skip them on a first read and lose nothing conceptual: they cover how the archive is partitioned and how children are mutated, not why any of it works.</p>

### CVT -- partitioning descriptor space

The naive way to partition descriptor space is a regular grid, but that costs `n^D` cells once you have more than two or three descriptors and most of those cells will never be reached. Centroidal Voronoi Tessellation gives you `K` cells regardless of how many descriptors you use. You sample a few thousand points from where the descriptors actually live, run Lloyd's algorithm (assign each sample to the nearest centroid, then move each centroid to the mean of its assigned samples, repeat), and after twenty or fifty iterations you have evenly-sized cells that hug the real distribution. Production runs pre-compute centroids once in Python with pyribs and reuse the same `centroids.npy` across campaigns.

<div class="lenia-widget" data-widget="cvt" data-centroids="64" data-samples="5000">
<noscript><p>Interactive CVT builder requires JavaScript.</p></noscript>
</div>

### The MAP-Elites loop

This widget replays that loop on a 64-niche CVT archive. Watch how quickly it fills and which niches stay empty.

<div class="lenia-widget" data-widget="mapelites" data-trace-src="me-trace.json" data-centroids="64">
<noscript><p>Interactive MAP-Elites step-through requires JavaScript.</p></noscript>
</div>

### Isoline variation (Vassiliades and Mouret, 2018)

Mutating a genotype with isotropic Gaussian noise is the obvious default, and also the wrong default for high-dimensional creature genotypes. Most isotropic perturbations go in directions that move the descriptor barely at all, so the search spends its budget jittering in place. Isoline variation fixes that by combining two noise sources:

$$\text{child} = A + \mathcal{N}(0, \sigma_{\text{iso}} I) + \mathcal{N}(0, \sigma_{\text{line}}) \cdot \widehat{(B - A)}$$

`A` is the parent and `B` is a second creature pulled from a different niche, and `widehat{(B - A)}` is the unit vector pointing from `A` toward `B`. The isotropic term (`sigma_iso` typically `0.005`) does fine-tuning within the parent's niche. The directional term (`sigma_line` typically `0.05`) jumps along the line between two creatures whose genotypes already differ in some behaviorally-meaningful way, so the search inherits a free hint about which directions actually move the descriptor. The slider widget below makes the effect of the two sigmas legible at a glance.

<div class="lenia-widget" data-widget="isoline" data-iso-sigma="0.03" data-line-sigma="0.12">
<noscript><p>Interactive isoline visualizer requires JavaScript.</p></noscript>
</div>

## After solitary creatures

Flow Lenia plus MAP-Elites gets us solitary creatures that move. Everything past that is about extending what a creature can do, what kind of world it lives in, and what we let the search figure out for itself.

### Sensorimotor Lenia

Flow Lenia creatures move, but they do not respond to anything outside themselves. Sensorimotor Lenia adds environmental input channels (food sources, chemical gradients, the presence of other creatures) and lets those inputs modulate the growth function directly. Once that loop is closed, behaviors like chemotaxis, avoidance, pursuit, and trail-following show up without anyone writing a controller for them. The creature is still pure `K` and `G`, the environment is just another set of fields it convolves against.

### Ecological search

Ecological search puts several species on the same grid and lets them share concentration fields, so they can compete, eat, form symbioses, or partition niches. Fitness becomes a property of the ecosystem: stability, diversity, and longevity. Our `flowlenia-ecology-2025` configuration runs 512x512 grids with three channels and 45 kernels (`[[5,5,5],[5,5,5],[5,5,5]]` connectivity).

### AURORA -- learned descriptors (Cully 2019)

MAP-Elites needs you to pick the descriptors up front, and the choice biases everything downstream. AURORA replaces hand-picked descriptors with learned ones: train an autoencoder on the behavioral observations from a run, use the latent space as the new descriptor space, run MAP-Elites for another batch of generations, retrain, and repeat. The behavioral axes that fall out are the ones the data actually has variation along, which is usually not the ones we would have chosen.

### The atlas

Every retained creature carries its genotype, phenotype, descriptor vector, ecology, campaign, replay, and anatomy panels (mass, components, moments). The `SavedCreature` record combines `ParamsPayload`, `InitConfig`, `SimulationMetrics`, score, weights, and `configHash`, so one record can appear in a SQLite query or on a creature page.

## Running it -- campaigns at scale

A single Flow Lenia evaluation takes about half a second to two seconds on GPU and ten to thirty on CPU. A real campaign needs 50k to 500k evaluations, which is hours to days, and the whole point of MAP-Elites is that those evaluations are independent. The archive is the only shared state, so you can have a host owning the archive (selecting parents, applying isoline variation, placing children) while a pool of workers chews through evaluation batches and reports back. Workers stay stateless: they get a `SimulationJob` with a seed range and a config, run the batch through their local engine, return the metrics, and never talk to each other.

A campaign goes through four phases. First a bootstrap of one to five thousand random genotypes to seed the archive. Then the long MAP-Elites loop with isoline variation, fifty to two hundred thousand generations of select-vary-evaluate-place. Then a refinement pass with `sigma_iso` cut to `0.001`, pure exploitation, polishing each occupied niche. Then a render pass with longer simulations (five thousand steps), full replays, detailed metrics, and export to the atlas SQLite. Determinism comes from a splitmix32 PRNG keyed on `phenotype.seed`, so the same `(genotype, seed, runConfig)` reproduces bit-for-bit within a backend and stays close across backends.

The two machines we run on are the M5 Max MacBook Pro (MLX Swift physics engine, Metal shaders) and quietbox (Tenstorrent backend over SSH, plus the heavy downstream work: distance matrices, UMAP, the analysis warehouse). Throughput depends entirely on the config. A 256-seed no-food scout at 200 steps clears in about 35 seconds on the M5 Max. A 512-seed ES batch at a 1200-step horizon drops to roughly 1.3 evals per second. The ecology configs (512x512 grids, 3 channels, 45 kernels, 500k steps per simulation) are an order of magnitude heavier again and run overnight rather than in an afternoon. For the implementation (Swift distributed actors, MLX Swift, Metal, the Tenstorrent backend, FFT-based convolution, checkpoint and resume), the [lenia-swarm dossier](../../dossiers/lenia-swarm/) has the receipts.

## What the atlas is for

The catalogue samples the manifold of viable creatures inside the mostly dead parameter space. MAP-Elites supplies the sample, descriptors give it coordinates, and the atlas preserves it in a form we can compute against.

With a few thousand genotypes, descriptors, and behaviors, the creatures stop being a list. Does the manifold break into body-plan components, or can one creature morph continuously into another? Does it contain holes around parameter regions no stable creature crosses? Those questions have measurable answers in Betti numbers and persistence; the [morphospace report](../lenia-morphospace-report/) works through them on the first 25,167 specimens.

<script src="lenia-gpu.js"></script>
<script src="lenia-explainer.js"></script>
