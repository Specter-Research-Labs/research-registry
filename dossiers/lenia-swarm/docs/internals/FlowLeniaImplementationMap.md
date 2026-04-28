# FlowLenia.swift Parameter Mapping

Struct and function mapping from `Sources/LeniaCore/Core/FlowLenia.swift` to the Flow Lenia paper.

## Concept
Maps the public structs in `Sources/LeniaCore/Core/FlowLenia.swift` to the exact equations and line references in the Flow-Lenia paper ([arXiv:2212.07906](https://arxiv.org/abs/2212.07906)). It is a parameter-to-theory bridge for verifying the Swift implementation against the paper.

## Why it matters
The Flow Lenia update rule couples convolutional affinity (Lenia) with mass-conserving transport (reintegration tracking). The parameters below are the only user-level knobs that must align with the paper to ensure scientific fidelity, especially when running distributed parameter sweeps.

## System connections
- `Sources/LeniaCore/Core/FlowLenia.swift` (definitions of `CompiledKernels`, `BatchedConfig`, and use sites)
- `Sources/LeniaCore/Core/Configuration.swift` (runtime config fields that feed `BatchedConfig`)
- `configs/base/paper_base_1c_128.json` (paper-aligned defaults/ranges)

## Paper line references
(Line numbers refer to PDF text extraction; they are stable for this file but not canonical.)
- p.2 L100–134: Kernel definition Eq. (1), ring count k=3, growth function Eq. (2), and growth/affinity map Eq. (3).
- p.3 L40–69: Flow definition Eq. (5), alpha term with $\theta_A$ and $n$, and Sobel gradient note.
- p.4 L14–36: Reintegration update Eq. (6–7) and distribution $D(m, s)$ with width $s$.
- p.4 L70–78: Table 1 with hyperparameters/ranges (includes $R$, $dt$, $n$, and reintegration temperature $s$).
- p.6 L93–105: Chemotaxis channel $\Gamma$ definition used in the chemotaxis task.
- p.7 L35–55: Parameter embedding Eq. (8–10) and mixing rules.

Struct: CompiledKernels
These fields are compiled, runtime-ready versions of the paper’s kernel and growth definitions.

- fK
  - Meaning: FFT of the spatial kernels $K_i$ used in convolution to compute the affinity map $U_t$.
  - Paper mapping: Kernel definition Eq. (1) and the statement “K is a set of convolution kernels where $K_i : L \to [0,1]$” (p.2 L76). Eq. (3) uses $K_i * A^t$ inside $U_t$ (p.2 L125–134).
  - Controls: Spatial scale/shape of affinity sensing; derived from $(r_i, a_i, b_i, w_i, R)$.

- m
  - Meaning: Per-kernel growth centers $\mu_i$ for the growth function $G_i$.
  - Paper mapping: Growth function Eq. (2) with parameters $\mu_i$ and $\sigma_i$ (p.2 L114–122).
  - Controls: Preferred activation level at which growth is maximal.

- s
  - Meaning: Per-kernel growth widths $\sigma_i$ for the growth function $G_i$ (not reintegration temperature).
  - Paper mapping: Same as above (p.2 L114–122).
  - Controls: How sharply growth falls off around $\mu_i$.

- h
  - Meaning: Weight vector $h \in \mathbb{R}^{|K|}$ scaling each kernel–growth pair’s contribution to $U_t$.
  - Paper mapping: “Where $h \in \mathbb{R}^{|K|}$ is a vector weighting the importance of each pair $(K_i, G_i)$” (p.3 L08).
  - Controls: Relative influence of each kernel-growth pair.

- c0Idxs
  - Meaning: Source channel index per kernel; derived from connectivity matrix $M$.
  - Paper mapping: “Connectivity can be represented through a square adjacency matrix” with $m_{ij}$ kernels sensing channel $i$ and updating channel $j$ (p.2 L84).
  - Controls: Which channel each kernel reads from.

- c1Mask
  - Meaning: Target-channel mask for kernels; derived from the same connectivity matrix $M$.
  - Paper mapping: The indicator term in Eq. (3) ($[c_i^1 = j]$) specifies which channel a kernel updates (p.2 L125–134).
  - Controls: Which channel each kernel writes to.

Struct: BatchedConfig
These fields are runtime parameters used to execute the update equations.

- sx, sy
  - Meaning: Grid dimensions of the lattice $L$.
  - Paper mapping: Model defined on 2D grid $\mathbb{Z}^2$ with $A^t : L \to S^C$ (p.2).
  - Controls: Spatial extent and resolution.

- channels
  - Meaning: Number of channels $C$ (multi-field CA state).
  - Paper mapping: $A^t : L \to S^C$ with channel index $i$ (p.2).
  - Controls: Number of coupled fields; determines size of $M$.

- nbK
  - Meaning: Total number of kernels $|K|$, derived from connectivity matrix $M$.
  - Paper mapping: Same connectivity description (p.2 L84) and Eq. (3) summing over $|K|$ kernels (p.2 L125–134).
  - Controls: Number of kernel–growth pairs used to form $U_t$.

- dt
  - Meaning: Time step $dt$.
  - Paper mapping: Appears in standard Lenia update Eq. (4) (p.3 L17–21) and in flow transport target $p'' = p' + dt\cdot F^t(p')$ Eq. (7) (p.4 L27–29).
  - Controls: Integration step size; affects transport distance per step.

- dd
  - Meaning: Discrete window radius for reintegration summation (implementation detail).
  - Paper mapping: Not explicitly named; it approximates the integral in Eq. (6–7) by summing over nearby offsets (p.4 L14–36).
  - Controls: Reintegration accuracy vs. cost.

- sigma
  - Meaning: Reintegration distribution width $s$ in $D(m, s)$ (temperature).
  - Paper mapping: Eq. (7) and the definition “uniform square distribution with side length $2s$” (p.4 L31–36); Table 1 lists $s=0.65$ (p.4 L74).
  - Controls: Spatial dispersion of transported mass (diffusion-like smoothing).

- n
  - Meaning: Exponent in $\alpha(p) = \left[(A^t_\Sigma(p)/\theta_A)^n\right]_0^1$.
  - Paper mapping: Eq. (5) (p.3 L40–49) and “We typically use $n > 1$” (p.3 L68–69); Table 1 lists $n=2$ (p.4 L75).
  - Controls: How quickly mass-gradient dominance increases with mass.

- thetaA
  - Meaning: Critical mass $\theta_A$ for blending affinity and mass gradients.
  - Paper mapping: Eq. (5) and explanation of “critical mass $\theta_A$” (p.3 L61–65).
  - Controls: Mass scale at which diffusion begins to dominate.

- border
  - Meaning: Boundary condition for convolution/gradient operators.
  - Paper mapping: Not specified in the paper; FFT implementation assumes periodic (torus) boundaries.
  - Controls: Whether the implementation uses toroidal wrapping or not (implementation constraint).

- colabCompat
  - Meaning: Compatibility switch for the original Colab/JAX implementation (kernel gating/normalization differences).
  - Paper mapping: Not a paper parameter; implementation detail for parity.
  - Controls: Reproduces historical reference behavior.

- chemChannel
  - Meaning: Index of the chemotaxis channel $\Gamma$.
  - Paper mapping: Chemotaxis section introduces an external channel $\Gamma : L \to \mathbb{R}_{\ge 0}$ (p.6 L93–105).
  - Controls: Which channel is treated as the chemical field.

- chemIncludeInMass
  - Meaning: Whether $\Gamma$ contributes to total mass $A^t_\Sigma$.
  - Paper mapping: The paper treats $\Gamma$ as external to matter; this flag enforces that (implementation policy).
  - Controls: Prevents the chemotaxis field from affecting mass conservation.

Notes on parameter symbols
- Kernel parameters $(r_i, a_i, b_i, w_i, R)$ are defined in Eq. (1) (p.2 L100–112).
- Growth parameters $(\mu_i, \sigma_i)$ are defined in Eq. (2) (p.2 L114–122).
- Weight vector $h$ and channel routing are defined in Eq. (3) (p.2 L125–134; p.3 L08).

Functions and Classes (Flow Lenia Update Rule)
Maps the remaining functions in `FlowLenia.swift` to the paper's equations and described algorithmic steps.

- growth(U, m, s, h)
  - Meaning: Implements the growth function $G_i(x)$ and scales by $h_i$ per kernel-growth pair.
  - Paper mapping: Eq. (2) defines $G_i(x) = 2 \exp(-(\mu_i - x)^2 / (2 \sigma_i^2)) - 1$ (p.2 L114–121). Eq. (3) multiplies by $h_i$ in the construction of $U_t$ (p.2 L125–134; p.3 L08).
  - Controls: Shapes the affinity response around $\mu_i$ with width $\sigma_i$, then weights by $h_i$.

- sobelBatched / sobelBatchedPeriodic
  - Meaning: Approximates spatial gradients with Sobel filters, in either torus or zero-padded mode.
  - Paper mapping: "In practice, gradients are estimated through Sobel filtering." (p.3 L60).
  - Controls: Numerical gradient estimate for $\nabla U$ and $\nabla A_\Sigma$ in Eq. (5).

- computeFlow(A, ...)
  - Meaning: Computes affinity map $U_t$ (Lenia), then flow field $F_t$ combining affinity and mass gradients.
  - Paper mapping:
    - Eq. (3): $U_t$ from convolution $K_i * A^t$ and growth $G_i$, with channel routing and weights $h_i$ (p.2 L125–134).
    - Eq. (5): $F^t_i = (1 - \alpha^t)\nabla U^t_i - \alpha^t \nabla A^t_\Sigma$ with $\alpha^t(p) = [(A^t_\Sigma(p)/\theta_A)^n]_0^1$ (p.3 L40–49).
  - Controls: $\theta_A$ and $n$ govern the transition between affinity-driven and diffusion-like flow; Sobel provides gradient estimates.
  - Note: `massField` computes $A^t_\Sigma$ and can exclude the chemotaxis channel, consistent with treating $\Gamma$ as external.

- reintegrationBatched(X, F, ...)
  - Meaning: Mass-conserving advection via reintegration tracking using a square distribution $D(m, s)$ and overlap with cell domains.
  - Paper mapping:
    - Eq. (6): $A^{t+dt}_i(p) = \sum_{p' \in L} A^t_i(p') I_i(p', p)$ (p.4 L14–19).
    - Eq. (7): $I_i(p', p) = \int_{\Omega(p)} D(p''_i, s)$ with $p''_i = p' + dt \cdot F^t_i(p')$ and $D$ a uniform square of side $2s$ (p.4 L21–36).
  - Controls: `sigma` is the distribution width $s$ (temperature), `dt` scales transport distance, `dd` is a discrete window radius (implementation detail) used to approximate the integral.

- leniaStepBatched(A, ...)
  - Meaning: Full Flow Lenia step: compute $F_t$ then reintegrate $A$.
  - Paper mapping: Composition of Eq. (3) + Eq. (5) + Eq. (6–7).
  - Note: The additive Lenia update Eq. (4) is not used here because Flow Lenia replaces it with mass-conserving transport.

- FlowLeniaBatched, FlowLeniaSimple, leniaStepSingle
  - Meaning: Execution wrappers (batched vs. single) and compilation management; these mirror the paper's algorithm but add implementation constraints (FFT + loop compilation).
  - Paper mapping: No direct paper counterpart; they are runtime scaffolding.

Parameter Embedding (Flow Lenia with Local Parameters)
The paper extends Flow Lenia by embedding parameters as a spatial field $P : L \to \Theta$ and advecting/mixing them with mass.

- Parameter embedding in the update rule
  - Paper mapping: Eq. (8) defines a parameter-weighted affinity: $U^t_j(p) = \sum_{i,k} P^t_k(p) \cdot G_k(K_k * A^t_i)(p)$ (p.7 L35–39).
  - Code mapping: `computeFlowWithParams` replaces static $h$ with dynamic $P$ (per-cell per-kernel weights) before channel routing.

- Mixing rules for parameters
  - Paper mapping:
    - Eq. (9): Weighted average of incoming parameters (p.7 L46–49).
    - Eq. (10): Softmax sampling from incoming parameters (p.7 L50–55).
  - Code mapping:
    - `reintegrationParamsBatched` uses the same reintegration weights for $A$ and then computes $P^{t+dt}(p)$.
    - `mixMode = "avg"` implements Eq. (9).
    - `mixMode = "softmax"` implements Eq. (10) via categorical sampling; `mixMode = "stoch"` is the same sampling mechanism with explicit seeding.
    - `mixMode = "argmax"` is implementation-only (not in paper).
  - Controls: `mixSeed` and `mixStep` drive stochasticity; not specified in the paper but required for reproducibility in distributed runs.

- FlowLeniaParamsBatched and leniaStepParamsBatched
  - Meaning: Full update of $(A, P)$ using Eq. (8) for affinity and Eq. (6–7, 9–10) for transport and mixing.
  - Paper mapping: Combines parameter embedding (p.7 L35–55) with standard Flow Lenia flow/reintegration (p.3–4).
  - Note: `colabCompat` alters alpha computation and flow clipping for compatibility; this is not a paper parameter.

Pseudocode Mappings (Equation-by-Equation)
The blocks below are simplified, equation-aligned pseudocode for the main kernels. They follow the paper’s ordering and highlight how the Swift code corresponds to each equation.

1) Affinity / Growth (Eq. 1–3)
```text
# Inputs: A^t (state), params r,a,b,w,R, mu, sigma, h, connectivity
# Output: U_t (affinity map per channel)

for each kernel i:
  K_i(x) = sum_{j=1..k} b_{i,j} * exp( - ( (x / (r_i R)) - a_{i,j} )^2 / (2 w_{i,j}^2) )   # Eq. (1)

for each kernel i:
  G_i(x) = 2 * exp( - (mu_i - x)^2 / (2 sigma_i^2) ) - 1                                   # Eq. (2)

U_t,j = sum_{i=1..|K|} h_i * G_i( K_i * A^t_{c_i^0} ) * [c_i^1 = j]                         # Eq. (3)
```
Swift mapping:
- Kernel creation is in `compileKernels` (K_i); growth in `growth`; channel routing in `computeFlow` (`MLX.matmul(G, c1Mask.T)`).

2) Flow (Eq. 5)
```text
# Inputs: U_t, A^t, theta_A, n
# Output: F_t (flow field per channel)

A^t_Sigma(p) = sum_{i=1..C} A^t_i(p)
alpha(p) = clip( (A^t_Sigma(p) / theta_A)^n, 0, 1 )

F^t_i(p) = (1 - alpha(p)) * grad(U^t_i)(p) - alpha(p) * grad(A^t_Sigma)(p)                  # Eq. (5)
```
Swift mapping:
- `computeFlow` computes `U` then `nablaU` and `nablaA` via `sobelBatched`, and blends them via `alpha`.

3) Reintegration Tracking (Eq. 6–7)
```text
# Inputs: A^t, F^t, dt, s
# Output: A^{t+dt}

p''_i = p' + dt * F^t_i(p')                                                                  # Eq. (7)
I_i(p', p) = ∫_{Omega(p)} D(p''_i, s)                                                        # Eq. (7)
A^{t+dt}_i(p) = sum_{p' in L} A^t_i(p') * I_i(p', p)                                          # Eq. (6)
```
Swift mapping:
- `reintegrationBatched` approximates the integral by summing overlaps of the square distribution $D(m, s)$ with each cell. `sigma` is $s$; `dd` is the discrete window size used for approximation.

4) Full Flow Lenia Step (Eq. 3 + 5 + 6–7)
```text
U_t = affinity(A^t; K, G, h, connectivity)    # Eq. (3)
F_t = flow(U_t, A^t; theta_A, n)              # Eq. (5)
A^{t+dt} = reintegrate(A^t, F_t; dt, s)       # Eq. (6–7)
```
Swift mapping:
- `leniaStepBatched` calls `computeFlow` then `reintegrationBatched`.

5) Parameter Embedding (Eq. 8–10)
```text
# Inputs: A^t, P^t (parameter map), K,G (static), connectivity, mixing rule
# Output: A^{t+dt}, P^{t+dt}

U^t_j(p) = sum_{i,k} P^t_k(p) * G_k( K_k * A^t_i )(p)                                         # Eq. (8)
F^t computed as in Eq. (5) using U^t and A^t

Mixing of P with incoming mass:
P^{t+dt}(p) =  [ sum_{p'} A^t(p') I(p',p) P^t(p') ] / [ sum_{p'} A^t(p') I(p',p) ]            # Eq. (9)
or
Pr[P^{t+dt}(p) = P^t(x)] ∝ exp( A^t(x) I(x,p) )                                               # Eq. (10)
```
Swift mapping:
- `computeFlowWithParams` uses per-cell $P$ as the weight vector (replacing static $h$) in Eq. (8).
- `reintegrationParamsBatched` implements Eq. (9) when `mixMode = "avg"`, and Eq. (10) when `mixMode = "softmax"` or `"stoch"`.
- `mixMode = "argmax"` is implementation-only (not in the paper).

Implementation Notes (Non-paper Details)
- `dd` is a discrete approximation window for reintegration; it is not an explicit paper parameter.
- `colabCompat` alters kernel gating, alpha computation, and flow clipping to match historical reference code; not in the paper.
- FFT-based convolution assumes periodic boundaries; the paper does not specify boundary conditions.
