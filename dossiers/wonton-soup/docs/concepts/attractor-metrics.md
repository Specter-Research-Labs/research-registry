# Attractor Metrics for Proof Search

These metrics treat proofs as attractors in stochastic search and quantify
robustness, convergence, rerouting, and collapse under perturbed MCTS theorem
proving.

Centralized MCTS supplies the structural baseline: proof families, basin mass,
reroute versus collapse, and recovery after intervention. Distributed MCTS
produces compatible artifacts, but its role is different: test how collective
control changes access to that landscape.

## Core Concept: Algorithmic Basins

**Basin size is a property of the search algorithm, not the theorem.**

When we say "basins" here, we mean: the fraction of random seeds that converge to a given proof structure under a fixed configuration (provider, MCTS parameters, budget, intervention, signature scheme).

Unlike basins of attraction in dynamical systems, MCTS basins are distributions over outcomes in a stochastic search process. The metric quantifies:

- **Robustness**: How stable is the search policy under random perturbations?
- **Convergence**: Does the algorithm reliably find the same proof structure?
- **Sensitivity**: How much does the outcome depend on early random choices?

## When Basin Size Is Meaningful

Basin analysis is meaningful when:

1. **Real stochasticity exists.** If the provider is deterministic (beam search) and MCTS tie-breaking rarely triggers, basin size will be trivial (all seeds converge to the same outcome). Enable provider sampling when available (ReProver only) or ensure UCB ties occur frequently enough to matter.

2. **Budget and parameters are fixed.** Basin size is strongly budget-dependent in MCTS. A theorem can have basin size 0.3 at budget 100 and 0.9 at budget 1000 as the algorithm explores alternatives. Always report the configuration.

3. **Structure notion matches attractor definition.** We use AST-based `goal_signature` for nodes and `tactic_family` for edges when hashing proof structures.

## Limitations

Keep these caveats in mind when interpreting results:

| Limitation | Implication |
|------------|-------------|
| Algorithm-specific | Basin size changes if you swap providers, adjust UCB constants, or modify the MCTS tree policy. It's not an intrinsic property of the proof space. |
| Goal signature dedup | Semantically equivalent goals collapse to the same signature, which can shrink the apparent number of distinct basins. |
| Budget-dependent | Longer runs can converge to structures that shorter runs miss entirely. |
| Provider cache | If the provider caches suggestions, different seeds can receive identical tactics for repeated goal states. Cache clearing is best-effort: we clear between seeds only when the provider implements `clear_cache`. |

## Confounds in Cross-Prover Comparison

Similar proof structures across provers do not identify one cause. Main
confounds:

1. **Intrinsic structure** - something "platonic" about the theorem's proof space
2. **Training data overlap** - Mathlib is the dominant corpus; learned models inherit its statistical patterns
3. **Architectural similarity** - transformer-based models share inductive biases
4. **Tactic vocabulary constraints** - Lean's tactic language shapes the space of expressible proofs

To distinguish these explanations, compare provers that differ on multiple axes:

| Prover | Training Data | Architecture | Tactic Space |
|--------|---------------|--------------|--------------|
| ReProver | Mathlib | Transformer | Lean4 |
| DeepSeek | Mathlib + additional data (not specified here) | Transformer | Lean4 |
| Heuristic | None | Rule-based | Lean4 |

The **heuristic provider** (`--provider heuristic`) serves as a control: it has no learned statistics, only hard-coded rules. If it converges to structures similar to learned models, that's stronger evidence for intrinsic structure than two transformers trained on overlapping data agreeing with each other.

**Current status (March 2, 2026):**
- paired Lean/Coq benchmark gate over a curated 84-pair logic micro set
- unpaired cross-assistant alignment report

**Evidence needed for stronger claims:**
- provers trained on additional proof assistants beyond Lean/Coq, with translation controls
- fundamentally different architectures, including symbolic search and neurosymbolic hybrids
- human expert proofs as ground truth for "natural" structure

When reporting cross-prover comparisons, always note which confounds apply. Two Mathlib-trained transformers agreeing tells us less than a transformer and a rule-based system agreeing.

## The Four Metrics

### 1. Trajectory Comparison (Recovery Time)

Measures how intervention runs diverge from and reconverge to the wild-type solution path.

**Definitions:**
- **Wild-type solution path**: The sequence of `goal_sig` values on the solved wild-type path
- **Intervention trajectory**: The per-iteration selected goal signatures (`selected_path[-1]`)
- **Divergence**: First MCTS iteration where the intervention goal does not match the next expected wild goal
- **Reconvergence**: First iteration after divergence where the remaining intervention trajectory matches a suffix of the wild path
- **Recovery iterations**: `reconvergence - divergence` (MCTS iterations), or None if never reconverges

```
Wild-type path: [A, B, C, D]

Intervention:   [A, B, X, Y, C, D]
                      ^     ^
                      |     reconverges at C (rejoins suffix [C, D])
                      diverges (expected C, got X)

Recovery iterations: 2
```

This metric answers: "When we perturb the search (by blocking tactics), how quickly does it find its way back to equivalent proof states?"

### 2. Attractor Clustering

Groups proof variants by structural similarity using the GED matrix.

After running wild-type and intervention experiments, we have multiple proof graphs for the same theorem. Hierarchical clustering (average linkage) on the pairwise GED matrix identifies:

- **Clusters**: Groups of proofs with similar structure
- **Representatives**: The most central member of each cluster (minimizes total distance to other members)
- **Inter-cluster distances**: How different the proof "families" are from each other

A theorem with one dominant cluster suggests a robust proof structure. Multiple well-separated clusters indicate genuinely different proof strategies.

### 3. Basin Analysis (Multi-Seed)

Runs the same theorem N times with different random seeds to measure convergence.

For each seed:
1. Clear provider cache if the provider implements `clear_cache`
2. Call provider `set_seed` if available (affects sampling-based providers)
3. Create per-seed MCTS RNG (affects UCB tie-breaking)
4. Run full MCTS search
5. Hash the resulting proof structure (nodes + tactic families)

**Output metrics:**
- `solve_rate`: Fraction of seeds that found a proof
- `unique_structures`: Number of distinct proof hashes
- `dominant_structure_frequency`: Fraction of solved seeds converging to the most common structure
- `structure_distribution`: Hash → count mapping

**Interpretation:**
- `dominant_structure_frequency = 1.0`: Single basin, completely deterministic outcome under this config
- `dominant_structure_frequency = 0.5` with 2 structures: Two equally likely attractors
- Many structures with low frequencies: High sensitivity to initial conditions

### 4. K-Style Search Efficiency 

Estimates how much work this solver saved relative to a simple "blind" null model, using
the MCTS trace as the reference set of choices available at each committed solution step.

We log and report:
- `tau_agent`: actual search cost, measured in `tactic_attempt`s (currently `detour.total_attempts`)
- `tau_blind`: expected blind cost under a null model
- `K = log10(tau_blind / tau_agent)` (orders-of-magnitude efficiency over blind)

**Interpretation:**
- `K > 0`: the solver is more search-efficient than blind selection (under this null model).
- `K = 0.301`: about a `2x` efficiency gain (`10^0.301 ≈ 2`).
- `K < 0`: the solver spent more attempts than blind would expect (often a smell of thrashing).

**Null models (current implementation):**
- `blind_uniform_candidate` (primary): at each solution step, pick uniformly from the trace-captured
  candidate tactic set at the iteration where that step was committed.
- `blind_uniform_family` (fallback): pick a tactic *family* uniformly; estimate success probability
  from `goal_cache` outcomes for that goal signature (weaker, used when traces are missing/incomplete).

**What this does NOT justify:**
- "Intrinsic basin size": `tau_agent` and the candidate set are algorithm/config-dependent.
- "Semantic identity": this metric does not compare proof terms; it only scores search efficiency.

**Where it lives:**
- Full payload (per intervention): `*_comparison.json` → `k_search_efficiency`
- Compact summary (wild + interventions): `summary.json.gz` → `theorems[].wild_type.k_search_efficiency`
  and `theorems[].interventions[].k_search_efficiency`
- Computation: `analysis/postprocess_metrics.py` (`compute_k_search_efficiency_from_logs`)

## Structure Hashing

Proof structures are hashed for comparison using:

```python
canonical = graph.to_canonical()
for u, v, data in canonical.edges(data=True):
    data["tactic_family"] = tactic_family(data.get("tactic_norm", ""))
structure_hash = nx.weisfeiler_lehman_graph_hash(
    canonical,
    node_attr="goal_sig",
    edge_attr="tactic_family",
)[:16]
```

This includes both the graph topology (which goals connect to which) and the tactic families used. Two proofs with identical goal structures but different tactics (e.g., `simp` vs `ring`) receive different hashes. The WL hash is a stable, fast proxy for labeled graph isomorphism. The goal signature scheme is recorded in `summary.json.gz`.

## Implementation Files

| File | Purpose |
|------|---------|
| `analysis/trajectory.py` | `TrajectoryComparison`, `compare_trajectories()`, `extract_solution_goal_sigs()` |
| `analysis/attractors.py` | `AttractorCluster`, `AttractorAnalysis`, `cluster_proof_structures()` |
| `prover/history.py` | `ExplorationHistory.iterations` with `selected_path` |
| `prover/mcts.py` | `rng` parameter for seeded tie-breaking |
| `prover/providers/reprover.py` | `set_seed()`, `clear_cache()` for independent runs (ReProver only) |
| `orchestrator/lean.py` | `run_basin_analysis()`, `BasinAnalysis` dataclass, CLI `lean basin --seeds` (and optional `--blind` for paper K) |

## Output Files

Per-theorem outputs in `logs/corpus-.../theorem_name/`:

```
wild_type_metrics.json      # includes solution_path for trajectory comparison
block_simp_comparison.json  # includes trajectory_comparison
attractor_clusters.json     # hierarchical clustering results
basin_analysis.json         # multi-seed convergence data (if using `lean basin --seeds`)
```

## Example Usage

```bash
# Standard run with trajectory + attractor metrics
uv run python wonton.py lean run -m research

# Basin analysis with 20 seeds per theorem
uv run python wonton.py lean basin -m dev --seeds 20 --sampling

# Basin analysis + blind baseline (adds paper K to basin_analysis.json)
uv run python wonton.py lean basin -m dev --seeds 20 --blind

# Single theorem deep analysis
uv run python wonton.py lean basin -t nat_add_comm --seeds 50 --sampling -b deep
```

The `--sampling` flag enables temperature sampling for ReProver only. DeepSeek and the
heuristic provider ignore it; in those cases, randomness mainly comes from UCB
tie-breaking. Sampling is recommended (not required) for meaningful basin analysis.
