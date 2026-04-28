---
title: "A Primer on Lenia"
release: "draft"
summary: A technical primer on Lenia and Flow Lenia -- continuous cellular automata, quality-diversity search, and how Specter Labs uses them to build an atlas of artificial life.
toc: true
---

<link rel="stylesheet" href="lenia-explainer.css" />

# A Primer on Lenia

## What Game of Life would look like if physics were continuous

- Game of Life: discrete grid, binary states {0,1}, synchronous tick, neighbor-count lookup table
- Lenia (Bert Chan, 2018): generalize every axis to continuous
  - State per cell: real-valued concentration in [0, 1] instead of alive/dead
  - Time: fractional steps dt (typically 0.1--0.2) instead of integer ticks
  - Update rule: smooth kernel and growth functions instead of a lookup table
- Two mathematical functions define everything: a kernel K (sensing) and a growth function G (update rule)
- All complexity -- movement, morphology, replication -- is emergent from K and G. No explicit rules for any of it
- Bert Chan's original creatures: orbium (translating glider), geminium (self-replicator), scutium (armored walker)
- The field extended by: multi-channel Lenia (multiple interacting concentration fields), Flow Lenia (mass-conserving transport), sensorimotor Lenia (environmental coupling)

### The kernel -- convolution as neighborhood sensing

- Each cell computes a potential U = weighted average of surrounding concentrations
- The weights come from a kernel function K(r), depends only on distance r from center
- Shape: ring-shaped bump (donut profile) -- zero at center, peak at characteristic radius, decay to zero
- Parameterized by Gaussian mixtures stacked at different radial positions:
  - b[i] = amplitude of i-th Gaussian
  - a[i] = radial center of i-th Gaussian (where along the ring it peaks)
  - w[i] = width of i-th Gaussian (how sharp the peak)
  - R = base radius in grid cells, r = per-kernel fraction of R
  - Effective kernel radius in pixels: R * r
- Kernel is normalized (sum of all weights = 1), so U is a weighted average independent of kernel size
- Convolution equation: U(x,y) = sum over all (dx,dy) of K(dx,dy) * A(x+dx, y+dy)
  - A = state grid, K = pre-computed kernel weights
  - Only iterate within kRadius = ceil(R * max(r_k)) -- skip zero weights
- Kernel construction (`buildKernelBuffer` in our code):
  - For each kernel k at each grid offset (dx, dy):
    - dist = sqrt(dx^2 + dy^2)
    - D = dist / (R * r_k) -- normalized distance
    - K(dx,dy,k) = sum_g b[g] * exp(-(D - a[g])^2 / (2 * w[g]^2))
  - Normalize: K /= sum(K)
- Complexity: O(sx * sy * nbK * (2*kRadius+1)^2) per step
  - 128x128, 1 kernel, radius 7: ~3.7M multiply-adds
  - 128x128, 15 kernels, radius 12: ~150M multiply-adds (needs GPU)
- Multi-channel: c0_map[k] specifies which channel kernel k reads from
- Our MLX implementation uses FFT-based convolution (O(n^2 log n) instead of O(n^2 * k^2)) for large kernels
- Our WebGPU implementation uses direct spatial convolution (nested loop in compute shader) -- simpler, no FFT overhead for small grids

<div class="lenia-widget" data-widget="kernel" data-defaults='{"R":13,"r":0.5,"b":[1],"w":[0.2],"a":[0.5]}'>
<noscript><p>Interactive kernel visualizer requires JavaScript.</p></noscript>
</div>

### The growth function -- the local update rule

- G(U) maps the potential U to a rate of change for the cell
- Shape: shifted bell curve minus a baseline
- Equation: G(U) = (2 * exp(-(U - mu)^2 / (2 * sigma^2)) - 1) * h
  - U near mu: G positive (cell grows)
  - U far from mu: G negative (cell actively shrinks)
  - U very far: G approaches -h (maximum decay rate)
- Three parameters per kernel:
  - mu: preferred neighbor density (the sweet spot)
  - sigma: tolerance width (narrow = sensitive, wide = tolerant)
  - h: amplitude (metabolic rate -- how fast growth/decay happens)
- This creates a narrow "habitable zone" in concentration space: only configurations maintaining the right local density at the right distance survive. Everything else decays
- Growth params stored as Float32Array with stride 4: [m_0, s_0, h_0, pad, m_1, s_1, h_1, pad, ...]
- Multi-channel accumulation via connectivity matrix:
  - c1_mask[ch][k] = 1.0 if kernel k writes to channel ch, 0.0 otherwise
  - Per channel: delta_ch = sum_k (G_k * c1_mask[ch][k])
  - Example: the Aquarium creature has 15 kernels across 3 channels with cross-channel connections (kernel reads ch0, writes ch1)
- Basic Lenia update (without flow): A_new(x,y,ch) = clamp(A(x,y,ch) + dt * delta_ch, 0, 1)
- All of Lenia's complexity emerges from just K and G. No explicit morphology, movement, or replication rules

$$G(U) = \bigl(2\exp\!\bigl(-\tfrac{(U - \mu)^2}{2\sigma^2}\bigr) - 1\bigr) \cdot h$$

<div class="lenia-widget" data-widget="growth" data-defaults='{"m":0.15,"s":0.017,"h":0.1}'>
<noscript><p>Interactive growth function explorer requires JavaScript.</p></noscript>
</div>

### Flow Lenia -- mass-conserving transport (Plantec et al., 2023)

- Problem with basic Lenia: mass is not conserved. `state += dt * G(U)` creates and destroys mass freely
  - Creatures evaporate, explode, or fragment without a physical conserved quantity
  - Movement is illusory: cells at the front grow while cells at the back shrink—a wave, not an object
- Flow Lenia adds a velocity field and mass redistribution step after growth
- Two-pass compute pipeline per simulation step:
- **Pass 1 -- compute_flow (growth + velocity field):**
  - For each cell (x,y):
    - Compute U_k for all kernels (convolution)
    - Compute G_k for all kernels (growth function)
    - Accumulate growth into state_out per channel via c1_mask
    - Compute total mass: M(x,y) = sum over all channels of A(x,y,ch)
    - Compute alpha = clamp((M / thetaA)^n, 0, 1) -- mass-dependent blending factor
      - Low mass: alpha near 0, creature follows growth gradient
      - High mass: alpha near 1, creature follows pressure gradient (dispersal)
    - Compute growth gradient: nabla_U = Sobel filter on growth field (per channel)
    - Compute mass gradient: nabla_A = Sobel filter on total mass field
    - Velocity: v(x,y,ch) = (1 - alpha) * nabla_U - alpha * nabla_A
    - Write velocity to flow_field buffer, zero out state_out
  - Sobel operator (3x3): gx = (a00 + 2*a10 + a20) - (a02 + 2*a12 + a22), gy similarly
- **Pass 2 -- reintegrate (mass redistribution along velocity field):**
  - For each cell (x,y), for each neighbor (dx,dy) within dd distance:
    - Read neighbor's state A_r and flow vector (fx, fy)
    - Compute where neighbor's mass lands: mur = neighbor_pos + clamp(dt * flow, -ma, ma)
    - Compute overlap area with current cell (box intersection):
      - szX = clamp(0.5 - |posX - murX| + sigma, 0, clipMax)
      - szY = clamp(0.5 - |posY - murY| + sigma, 0, clipMax)
      - area = szX * szY
    - Accumulate: accum += A_r * area
  - Final: state_out(x,y,ch) = accum / (4 * sigma^2)
  - After both passes: copy stateBufferB -> stateBufferA (ping-pong)
- **Flow parameters:** dt (0.1--0.2), dd (5), sigma (0.65), n (2), thetaA (2.0), border ("torus" or "wall")
- **GPU buffer layout (WebGPU):**
  - configBuffer (48 bytes, uniform): sx, sy, channels, nbK, dt, dd, sigma, n, thetaA, border, kernelRadius, pad
  - stateBufferA/B (sx*sy*channels*4 bytes): ping-pong state
  - flowBuffer (sx*sy*channels*2*4 bytes): velocity field
  - kernelBuffer (sx*sy*nbK*4 bytes): pre-computed kernel weights
  - growthBuffer (nbK*4*4 bytes): growth params
  - c0Buffer (nbK*4 bytes): source channel indices
  - c1Buffer (channels*nbK*4 bytes): target channel mask
  - Workgroup: 8x8, dispatch ceil(sx/8) x ceil(sy/8)
- **Our MLX/Metal implementation (dossiers/lenia-swarm):**
  - Two compute backends: `mlx` (pure MLX reference path) and `metal-full` (all-Metal shaders)
  - MLX backend: FFT-based convolution via MLX arrays. CompiledKernels stores frequency-domain kernels (fK: MLXArray)
  - Metal backend: separate shader stages -- FFT, spectrum gather, growth reduce, wall potential, flow, reintegrate
  - MetalPipeline.swift (~80KB) manages buffer allocation, encoder setup, synchronization
  - Backend auto-detection: checks MTLCreateSystemDefaultDevice(), prefers metal-full when Metal is available
  - BatchedConfig groups all simulation parameters for efficient dispatch

<div class="lenia-widget" data-widget="sandbox" data-creature="orbium">
<noscript><p>Live Lenia simulation requires JavaScript and WebGPU.</p></noscript>
</div>

## The search problem -- parameter space and fitness

- A Lenia creature = genotype (parameter values) + phenotype (initial condition)
- Single-channel, single-kernel genotype: [R, r, b_0..b_G, w_0..w_G, a_0..a_G, mu, sigma, h]
  - G=1 (one Gaussian): ~8 continuous parameters
  - G=3: ~12 parameters
- Multi-channel genotype (Aquarium: 3 channels, 15 kernels): ~120 continuous parameters
  - Plus connectivity: c0[k] (source channel), c1[k] (target channels)
- Phenotype: seed (integer for PRNG), patch centers (cx, cy), patch radii, a_uniform [low, high]
- Run config (fixed per campaign): grid size, dt, dd, sigma, n, thetaA, border
- Parameter space is overwhelmingly boring:
  - Most combinations: decay to zero within 50 steps
  - Second: saturate to 1.0 (uniform soup)
  - Persistent structured creatures: vanishingly thin manifold
- Real parameter ranges from our configs (flowlenia-ecology-2025):
  - r: [0.2, 1.0], b: [0.001, 1.0], w: [0.01, 0.5], a: [0.0, 1.0]
  - m: [0.05, 0.5], s: [0.001, 0.18], h: [0.01, 1.0], R: [2.0, 25.0]
- **Fitness and behavioral descriptors (SimulationMetrics in our code):**
  - Core morphometrics: massMean, massStd, massMin, massMax
  - Spatial: occupancyMean, varianceMean, gyration (radius of gyration)
  - Movement: speedMean, pathLength, displacement, centerVelocity, headingRad
  - Shape (moment invariants): hu1--hu7 (Hu's moments), flusser1--flusser4, momentAnisotropy
  - Components: componentCount (flood-fill), largestComponentFraction, largestComponentAnisotropy
  - Activity: activityEacMean, activityDiversityMean (Shannon entropy)
  - Stability: isStable, survivalSteps
  - Complexity: complexityMean, complexityScales (per-scale decomposition)
  - Scoring: weighted sum of metrics, configurable. Default: score_weights: {"mass_mean": 1.0}
  - Filters: mass_min: 0.01, gyration_min: 0.1, gyration_max: 180.0
  - Default eval: 200 steps, record every 50, warmup 100, occupancy_threshold 0.05

### Three search strategies compared

- **Random search:** uniform sampling, no learning. Almost all evaluations produce dead grids
- **ES:** follows fitness gradient from one point. Finds one peak, converges, stops. Landscape is multimodal
- **MAP-Elites:** maintains a grid of behavioral niches, fills all simultaneously. Values diversity alongside fitness

<div class="lenia-widget" data-widget="search" data-steps="200" data-auto-play="true">
<noscript><p>Interactive search comparison requires JavaScript.</p></noscript>
</div>

## MAP-Elites and Quality-Diversity

- QD: structured archive indexed by behavioral descriptors. Each cell stores best individual for that niche
- QD-score = sum of all fitnesses across all cells. Requires both quality and diversity
- MAP-Elites (Mouret & Clune 2015): the canonical QD algorithm
- Competition is local (within CVT cell). Mediocre creature in empty niche always gets kept
- Archive: array of K cells (K = CVT centroids, typically 1024--16384)
  - Each cell: { genotype, fitness, descriptor, occupied }
- Our descriptor functions: speed, mass, gyration, symmetry, oscillation (FFT of mass time series)

### CVT -- partitioning descriptor space

- Centroidal Voronoi Tessellation: evenly partition descriptor space into K cells
- Lloyd's algorithm: start K random centroids, iterate assign-to-nearest/recompute-mean until convergence
- Converges in ~20--50 iterations for K=64, N=5000
- Regular grid: K = n^D cells (exponential). CVT: K cells regardless of D
- Production: pre-compute in Python (pyribs), export as centroids.npy

<div class="lenia-widget" data-widget="cvt" data-centroids="64" data-samples="5000">
<noscript><p>Interactive CVT builder requires JavaScript.</p></noscript>
</div>

### The MAP-Elites loop

1. **Select** -- random occupied cell (uniform over filled cells)
2. **Vary** -- mutate genotype: child = parent + noise (Gaussian or isoline)
3. **Evaluate** -- simulate N steps, measure fitness + descriptors
4. **Place** -- nearest CVT cell; child enters if empty or beats incumbent

- Coverage and per-cell fitness are both monotonically non-decreasing
- QD-score example: 40/64 cells * avg 0.7 fitness = QD 28 > 60/64 * avg 0.3 = QD 18

<div class="lenia-widget" data-widget="mapelites" data-trace-src="me-trace.json" data-centroids="64">
<noscript><p>Interactive MAP-Elites step-through requires JavaScript.</p></noscript>
</div>

### Isoline variation (Vassiliades & Mouret 2018)

- Standard mutation: isotropic Gaussian in all directions
- Isoline: decompose into two components:
  - **Isotropic:** N(0, sigma_iso * I), sigma_iso typically 0.005 -- fine-tuning within niche
  - **Directional:** N(0, sigma_line) * unit_vector(A->B), sigma_line typically 0.05 -- explores descriptor space
- Formula: child = A + N(0, sigma_iso * I) + N(0, sigma_line) * normalize(B - A)
- A and B from different niches. Their genotypic difference encodes "what changes produce behavioral changes"
- Code: `direction = (partner - parent) / (norm + 1e-8); child = parent + randn(d)*sig_iso + randn()*sig_line*direction`

<div class="lenia-widget" data-widget="isoline" data-iso-sigma="0.03" data-line-sigma="0.12">
<noscript><p>Interactive isoline visualizer requires JavaScript.</p></noscript>
</div>

## The research ladder

### Sensorimotor Lenia

- Flow Lenia: creatures move but don't respond to environment
- Sensorimotor: add environmental input channels (food, chemicals, other creatures)
- Inputs modulate growth function -- closes perception-action loop
- Emergent behaviors: chemotaxis, avoidance, pursuit, trail following

### Ecological search

- Previous: each creature in isolation
- Ecological: multiple species on same grid, interacting via shared concentration fields
- Emergent: predation, symbiosis, competition, niche partitioning
- Fitness: ecosystem stability and diversity, not individual survival
- Our configs: flowlenia-ecology-2025, 512x512 grid, 3 channels, 45 kernels (connectivity [[5,5,5],[5,5,5],[5,5,5]])

### AURORA -- learned descriptors (Cully 2019)

- MAP-Elites needs hand-picked descriptors. AURORA: learn them from data
- Autoencoder on behavioral observations -> latent space becomes descriptor space
- Co-evolution: run MAP-Elites N generations, retrain autoencoder, update descriptors, repeat
- Discovers behavioral axes humans wouldn't have chosen

### The atlas

- Comprehensive catalog: genotype, phenotype, descriptors, ecological context, provenance, replays, anatomy panels
- Scientific dataset (reproducible, citable) + interactive exploration tool
- SavedCreature format: { id, name, timestamp, ownerId, genotype (ParamsPayload), phenotype (InitConfig), metrics (SimulationMetrics), score, scoreWeights, configHash }

## Distributed search -- workers, campaigns, and infrastructure

- **Why distribute:**
  - Single eval: ~0.5--2s on GPU (MLX/Metal), ~10--30s on CPU
  - Campaign: 50k--500k evaluations -> hours to days
  - MAP-Elites is embarrassingly parallel: each evaluation independent, archive is only shared state

- **Architecture (Swift distributed actors in lenia-swarm):**
  - Controller (host): owns archive, runs select/vary, dispatches SimulationJob, runs placement
  - Worker (distributed actor): receives SimulationJob, runs simulation via SearchEngine.runBatch(), returns SimulationResult
    - Stateless, no archive knowledge, no inter-worker communication
    - Auto-detects backend: MTLCreateSystemDefaultDevice() -> prefers metal-full, falls back to mlx
    - WorkerBackendCapabilities: lists available backends per worker

- **SimulationJob data flow:**
  - Job: { seedStart, count, stride, baseConfig (LeniaBaseConfig), searchConfig (ParsedSearchConfig) }
  - Worker computes seeds, splits into batches of batch_size, runs each through engine
  - Per eval: simulate, measure SimulationMetrics (40+ fields), score via weighted sum, apply filters
  - Returns: array of SimulationResultData (seed, backend, score, metrics, params, filtersPassed)

- **Campaign structure (LeniaCampaignJob):**
  - campaignID, runID, preset ("discovery", "food-discovery", "seeded-ecology", "intervention-battery")
  - executor: "search" or "ecology-2025"
  - executionMode: "local" or "distributed"
  - Results: LeniaCampaignRunRecord[], LeniaCampaignMetricRecord[], LeniaCampaignEventRecord[], LeniaCampaignExportCandidate[]

- **Campaign phases:**
  1. Bootstrap: N random genotypes (1000--5000), evaluate all, seed archive
  2. Isoline MAP-Elites: select + vary + evaluate + place, 50k--200k generations
  3. Refinement: small perturbations per cell, sigma_iso 0.001, pure exploitation
  4. Render + publish: longer sim (5000 steps), record replays, compute detailed metrics, export to atlas SQLite

- **Batch scheduling:**
  - Batches of 64--128 evaluations dispatched in parallel
  - Tradeoff: larger batches = better GPU utilization, staler archive
  - Sweet spot: batch_size = 2--4x worker count

- **Fault tolerance:**
  - Timeout: 60s per evaluation (divergent sims killed)
  - Validation: fitness finite, descriptors in bounds, mass positive
  - Checkpoint every N generations, resume from checkpoint
  - Workers stateless -- relaunch on crash

- **Hardware:**
  - GPU memory: 128x128 * 3ch = ~200KB state, 15-kernel buffer = ~12MB
  - Apple Silicon: Metal compute shaders, ~1s/eval on M1 Pro
  - Our setup: Mac Studio M1 Ultra, 4 MLX workers, ~200 evals/min -> 100k evals in ~8 hours
  - Ecology configs: 512x512 grid, 3 channels, 45 kernels, 500k steps per sim

- **Reproducibility:**
  - Seeded: splitmix32 PRNG with phenotype.seed
  - Same genotype + seed + runConfig = deterministic (within one backend)
  - Archive snapshots include full genotype + phenotype + runConfig per creature
  - Campaign config logged: generation count, sigmas, CVT centroids, fitness function, filters

<script src="lenia-gpu.js"></script>
<script src="lenia-explainer.js"></script>
