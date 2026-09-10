---
title: "Proof search with a missing tactic"
release: "published"
summary: Intervention studies in proof search, with structural comparison across runs.
series: B-001
pdf: wonton-soup.pdf
---

# Proof search with a missing tactic

In one Wonton search, the prover found a proof using `contrapose!`. When we blocked that tactic, it still reached the theorem, this time through `intro` and `exact`. The result stayed the same while the route changed. That small detour is what we want to understand: when a familiar proof becomes unavailable, what alternatives can the prover actually find?

A theorem may have many valid proofs while a particular search depends heavily on one tactic. Even visibly different proof terms can share that dependency. Wonton records the attempted tactics and intermediate goals so we can compare the route as well as the final success or failure. Blocking a tactic turns a collection of observed proofs into a test of which alternatives remain usable under the same search budget.

This article follows the early experiments and the machinery built to make those comparisons. The later [controlled tactic-blocking study](/research-notes/2026-06-10-taking-away-one-move-revealed-proof-alternatives/) tests the question across a larger cohort. Along the way, an [unused-tactic control](/research-notes/2026-04-02-wonton-controls-exposed-a-reproducibility-problem/) exposed a problem with inference reproducibility that a fixed search seed had concealed.

![MCTS Proof Search Tree](../../assets/blog/wonton-soup/fig1-mcts-tree.png)

## 1. Following the route to a proof

At each unfinished goal, the prover proposes tactics and explores the proof states they produce. Some proposals fail immediately; others open new goals or complete the proof. Repeating the search can reveal routes that meet at the same intermediate state, reach the same theorem through different proof terms, or exhaust the budget without a solution.

We change one part of that process and compare the traces. A tactic block removes an action; changing a seed alters exploration; a scheduling intervention changes when workers examine parts of the search. Recording those differences lets us distinguish a local tactic substitution from a broader change of route. Recurring proof-graph clusters summarize the outcomes, though their recurrence alone does not establish dynamical attractors.

## 2. What an intervention can reveal

The [Diverse Intelligence](https://www.diverseintelligence.org/) programme asks how systems preserve or reach outcomes when their usual mechanisms are disturbed. Proof search gives us an unusually explicit target for that question: the theorem checker determines whether the result is valid, while the trace records how the prover reached it. We use efficiency, rerouting and recurring structure to examine different parts of the response.

### Search efficiency as a metric ($K$)
Following [Chis-Ciure and Levin (2025)](https://link.springer.com/article/10.1007/s11229-025-05319-6), we measure one proposed aspect of problem-solving performance: search efficiency relative to a specified blind policy. The score is the log-ratio between a random walk ($\tau_{blind}$) and our observed agent ($\tau_{agent}$):
$$K = \log_{10}(\tau_{blind} / \tau_{agent})$$
A positive $K$ quantifies how many orders of magnitude our policy saves over a brute-force baseline.

### Lesions and Rerouting
[Zhang et al. (2024)](https://arxiv.org/abs/2401.05375) demonstrate that decentralized systems, such as self-sorting arrays, can navigate around "damaged" components to reach a global goal, whereas our proof-search version blocks specific tactics or lemma families from a known solution path and measures whether the solver finds a different proof route or fails under the block.

### Pattern Invariance (TAME)
The TAME framework ([Levin, 2022](https://arxiv.org/abs/2201.10346)) argues that behavioral structures, not just low-level mechanisms, persist under perturbation, and in `wonton-soup` we use Graph Edit Distance (GED) and basin analysis to determine whether proof search repeatedly settles into the same proof-graph clusters across different seeds and interventions.

## 3. Making the rerun comparable

A failed rerun is informative only if we know what changed. We therefore save the theorem collection, selected items, search budget and intervention with each run. Repeating the corpus reference and seeded selection recovers the same theorem slice; matched controls test whether the inference and search process also behave comparably.

Before testing an intervention, we separate a malformed input from a theorem the prover cannot solve. The first check asks whether the backend can process the item. The second asks whether the provider can solve or meaningfully search it within the budget. The recorded configuration, status and summary preserve those distinctions for later analysis.

### What is fixed per comparison run

- Corpus reference plus build provenance (`manifest.json`, item ordering, hash identity).
- Selection procedure (`--sample`, `--seed`, `--offset`, `--limit`) and resulting theorem slice.
- Search budget and core execution knobs (mode, iteration budget, intervention declaration).
- Analysis inputs consumed by downstream tools (`run_config.json`, `run_status.json`, `summary.json.gz`, theorem subfiles).

## 4. Centralized and distributed Monte Carlo tree search

The order in which a prover explores alternatives may matter as much as the alternatives themselves. In centralized Monte Carlo tree search, one selection loop chooses which frontier state to expand next. That gives us a baseline with one expansion order.

Distributed search lets several workers explore the same frontier. Reservations reduce duplicated effort, while blocking or delaying workers changes which possibilities are examined first. The comparison asks whether a successful route remains accessible under a different schedule, or depended on the original order of exploration.

Both modes record compatible trees and traces. We can therefore compare the changed search directly, while keeping the theorem and budget fixed, instead of treating the parallel run as a different kind of result.

![Distributed Frontier](../../assets/blog/wonton-soup/fig9-distributed-frontier.png)

How to read the figure: each worker lane represents local agent activity against a shared frontier, with reservations and scheduler policy shaping contention and handoff, while dense synchronized bands suggest strong coupling and staggered bands indicate looser parallel exploration.

## 5. Comparing different provers

A route that is easy for one prover may be inaccessible to another. Comparing backends lets us ask how much of a recurring proof structure belongs to the theorem and how much depends on the solver. The comparison must account for what each solver records: a search graph, a completed proof and an execution trace are different objects.

`wonton-soup` currently supports five execution backends:

- `lean`
- `coq`
- `e`
- `vampire`
- `z3`

Run-level schemas are shared (`run_config.json`, `run_status.json`, `summary.json.gz`), and `run_status.json` flags plus file-presence checks say which outputs each backend can actually produce, so downstream analysis does not silently compare missing or incompatible files.

This matters for mixed analyses: `ged_search_graph` is meaningful only when a true search graph exists, whereas external solver traces may map to `ged_trace_graph` or proof-object comparisons instead, and capability flags plus validity metadata keep those distinctions visible.

### Backend Output Types (Typical)

| Backend | Search-graph output | Proof output | Trace output | Practical note |
| --- | --- | --- | --- | --- |
| `lean` | `ged_search_graph` | proof-term artifacts when enabled | MCTS traces | Full search-graph comparisons are strongest here. |
| `coq` | usually unavailable | proof object family (integration dependent) | backend trace varies | Treat proof/trace availability as capability-gated. |
| `e` | unavailable | proof object family | `ged_trace_graph` from TSTP-style traces | Mark trace completeness explicitly. |
| `vampire` | unavailable | proof object family | optional trace family | Proof-centric comparison is typical. |
| `z3` | unavailable | proof object family | optional trace family | Search-graph GED is not the primary comparison. |

Cross-backend comparisons are safest on shared run-level outcomes and explicitly labeled measurement types. Structure-level comparisons should be grouped by compatible output types, not collapsed into one undifferentiated score.

### Two views of the same experiment

Two views recur in the analysis: proof-structure clusters and search efficiency relative to a specified blind policy.

<div class="ws-focus-grid">
  <figure>
    <img src="../../assets/blog/wonton-soup/fig4-attractors.png" alt="Attractor analysis figure: GED matrix, clustering cut, and basin mass panels." />
    <figcaption>Proof-structure clusters and the fraction of sampled runs assigned to each. The figure uses historical “attractor” terminology; it measures recurring outcomes.</figcaption>
  </figure>
  <figure>
    <img src="../../assets/blog/wonton-soup/fig7-k-metric.png" alt="K metric visualization: blind-relative search efficiency calibration." />
    <figcaption>K view: efficiency over blind baseline for intervention comparisons.</figcaption>
  </figure>
</div>

## 6. Measuring the change

A solved/failed label tells us whether a route survived, but not whether it became longer or structurally different. The measurements below separate those changes:

- K-style search efficiency (`k_search_efficiency`) from trace-derived blind nulls.
- Paper-style paired blind baseline (`paper_k`) from basin runs with `--basin-blind`.
- GED measurement types (`ged_search_graph`, `ged_search_graph_soft`, `ged_proof_graph`, `ged_trace_graph`) with explicit validity metadata.
- Trajectory comparison (divergence, reconvergence, recovery iterations).
- Basin analysis (solve rate, structure hash diversity, dominant basin frequency).
- Sheaf analyses (equivalence consistency and tactic-transform residuals).
- Cross-run lake exports for reproducible, cross-experiment aggregation.

### Quick Metric Interpretation

| Metric | What changed in the intervention run | How to read it |
| --- | --- | --- |
| `k_search_efficiency` / `paper_k` | Attempted edge count before first solve ($\tau_{agent}$) vs blind baseline ($\tau_{blind}$) | Higher is better; $K > 0$ means fewer attempts than blind |
| `normalized GED_search` | Search-graph structure relative to wild-type | Near `0` means structurally similar search; larger values mean stronger reroute |
| shared prefix | Number of early wild-type steps replayed before divergence | High prefix means late divergence; low prefix means early policy/path change |
| divergence iteration/depth | First step where intervention path differs | Lower means early structural perturbation; higher means late perturbation |
| solve status under block | Whether constrained run still reaches terminal proof | Distinguishes a successful alternative from failure within the search budget |
| basin mass + attractor ID | Fraction of seeds ending in each clustered trajectory family | Concentrated mass means one frequent cluster; split mass means several observed clusters |

K is reported as:

$$K = \log_{10}\left( \frac{\tau_{blind}}{\tau_{agent}} \right)$$

Example calibration: $K=\log_{10}(120/9)=1.12$ (about $13\times$ fewer attempts than blind).

![K-Metric Visualization](../../assets/blog/wonton-soup/fig7-k-metric.png)

- **$\tau_{agent}$**: attempted tactic edges until first terminal solve in the observed search graph.
- **$\tau_{blind}$**: expected attempted edges for a matched blind null policy over the same available tactic choices.
- **$K$**: orders-of-magnitude efficiency over blind (`K > 0` is better than blind).

Two related outputs:

- `k_search_efficiency`: trace-derived null model from postprocess.
- `paper_k`: paired blind baseline from basin runs with `--basin-blind`.

## 7. Blocking a tactic and repeating the search

For each theorem, we first solve a wild-type run and extract the solution path $\pi = \{\tau_1, \dots, \tau_n\}$. We then run controlled lesions by blocking one tactic (or tactic family) from that path and rerun under the same budget and configuration.

This fixes the intended comparison: the same theorem and budget with one action constrained. An inert-control rerun is also needed to measure variation from the inference service or search execution; the shared seed alone does not supply that control.

![Canonical Loop](../../assets/blog/wonton-soup/fig6-canonical-loop.png)

### How to Read Attractor Analysis

![Attractor Analysis](../../assets/blog/wonton-soup/fig4-attractors.png)

- Panel A (GED matrix): pairwise structural distance between runs.
- Panel B (clustering + cut): where we place the cut determines attractor families.
- Panel C (basins): seed mass captured by each attractor family.

Low GED and a frequent shared cluster describe repeated structural similarity. Higher GED with several clusters describes a broader set of observed routes. A causal claim about rerouting also requires the matched controls; neither clustering nor GED establishes a dynamical attractor.

## 8. What rerouting looks like

The recorded examples below range from a changed proof strategy to a substituted final tactic. Step through them to compare what the prover attempted before and after the block.

<div class="ws-stepper ws-vignette-stepper" data-title="Log-derived vignette gallery" data-slides='[
  {
    "label":"contrapositive / block contrapose!",
    "metrics":"Solved | normalized GED_search 0.67 | structural reroute",
    "ged":0.6666666666666666,
    "attempts":{"blocked":1,"failure":1,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"¬P",
        "attempts":[
          {"tactic":"exact hnq","outcome":"failure"},
          {"tactic":"contrapose! hnq","outcome":"success"}
        ],
        "continuation":"exact h hnq"
      },
      "intervention":{
        "root":"¬P",
        "attempts":[
          {"tactic":"contrapose! hnq","outcome":"blocked"},
          {"tactic":"exact hnq","outcome":"failure"},
          {"tactic":"intro hP","outcome":"success"}
        ],
        "continuation":"exact hnq (h hP)"
      }
    },
    "wild_path":["contrapose! hnq","exact h hnq"],
    "intervention_path":["intro hP","exact hnq (h hP)"],
    "caption":"Blocking contrapose! forces a forward route (intro + exact), producing a clear structural shift.",
    "lightbox":false
  },
  {
    "label":"nat_succ_pred / block positivity",
    "metrics":"Solved | normalized GED_search 0.00 | local tactic swap",
    "ged":0.0,
    "attempts":{"blocked":0,"failure":0,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"n.pred.succ = n",
        "attempts":[
          {"tactic":"simp [Nat.succ_pred_eq_of_pos h]","outcome":"blocked"},
          {"tactic":"simp [Nat.succ_eq_add_one]","outcome":"blocked"},
          {"tactic":"rw [succ_pred]","outcome":"success"}
        ],
        "continuation":"positivity"
      },
      "intervention":{
        "root":"n.pred.succ = n",
        "attempts":[
          {"tactic":"rw [succ_pred]","outcome":"success"}
        ],
        "continuation":"exact Nat.ne_of_gt h"
      }
    },
    "wild_path":["rw [succ_pred]","positivity"],
    "intervention_path":["rw [succ_pred]","exact Nat.ne_of_gt h"],
    "caption":"Blocking positivity preserves structure and swaps in an explicit Nat.ne_of_gt proof step.",
    "lightbox":false
  },
  {
    "label":"iff_intro / block exact",
    "metrics":"Solved | normalized GED_search 0.00 | terminal discharge swap",
    "ged":0.0,
    "attempts":{"blocked":3,"failure":0,"success":1},
    "attempt_graph":{
      "wild":{
        "root":"P ↔ Q",
        "attempts":[
          {"tactic":"constructor","outcome":"success"}
        ],
        "continuation":"exact hpq"
      },
      "intervention":{
        "root":"P ↔ Q",
        "attempts":[
          {"tactic":"exact ⟨hpq, hqp⟩","outcome":"blocked"},
          {"tactic":"exact ⟨fun hp => hqp hp, ...⟩","outcome":"blocked"},
          {"tactic":"exact ⟨fun hp => hqp hp, fun hp => hqp hp⟩","outcome":"blocked"},
          {"tactic":"constructor","outcome":"success"}
        ],
        "continuation":"assumption"
      }
    },
    "wild_path":["constructor","exact hpq"],
    "intervention_path":["constructor","assumption"],
    "caption":"The terminal tactic changes from exact to assumption while the trajectory remains in-family.",
    "lightbox":false
  }
]'>
<div class="ws-stepper-fallback"><p>Interactive graph gallery requires JavaScript.</p></div>
</div>

### A. Alternate Tactic at Same Structure

From a recent February corpus sweep:

- `control_null`: solved, normalized GED `0.00`.
- `block_intros`: solved, normalized GED `0.45`.
- `block_split_ifs`: unsolved, normalized GED `0.57`.

Interpretation: one theorem shows both outcomes we care about, since some lesions reroute and recover whereas others collapse, and the split between `GED=0` replicate and `GED>0` reroute/collapse appears inside a single local intervention family.

### B. Different Theorems, Different Intervention Patterns

From **2026-02-04**:

- `contrapositive`: block `contrapose!` solved, normalized GED `0.67`. Blocking `contrapose!` forces a forward proof via `intro`, flipping the intermediate goal from $Q$ to $\mathsf{False}$ before discharge.
- `nat_succ_pred`: block `positivity` solved, normalized GED `0.00`. A local tactic swap: the proof keeps the same goal sequence but replaces an automated step with a direct lemma.
- `iff_intro`: block `exact` solved, normalized GED `0.00`. A shallow reroute: the structure is intact but the terminal discharge uses a different tactic.

## 9. What the early searches revealed

### Multistability in Proof Space
Proof search is not a single path: different seeds and interventions often converge to a small number of recurring proof shapes, suggesting that "the proof" is often a family of related trajectories rather than a single sequence of steps.

### Competency through Constraint
Targeted damage to search sometimes improves global outcomes, as in cases like `set_inter_self`, where blocking the highest-priority tactics forces the system into routes that the unconstrained policy does not reach within budget, while the relevant parallel to biological morphogenesis is concrete: a local disruption can change the route without preventing the target pattern.

### Search Efficiency
When $K > 0$, the observed search reaches a solve with fewer attempted tactic edges than its matched blind null, and the measurement is useful only after calibration to the available tactic choices: evidence that the policy is using useful structure in the action space, not a universal intelligence score.

### Recurring Proof Families
When wild-type, blocked-tactic, and seed-variation runs converge to the same low-GED proof shape, the narrow claim is that this policy/corpus slice has a stable cluster of related proofs, with recurrence as the evidence; stronger TAME-style claims require the same family to survive broader backends, encodings, and null calibrations.

Next steps: cross-backend basin agreement tests, calibrated $K$ estimation with matched null models, and wider corpus and provider coverage.

---

*This article records the early experimental framework. For the later controlled results, read [Which proofs survive a blocked tactic?](/research-notes/2026-06-10-taking-away-one-move-revealed-proof-alternatives/). Selected runs are available in the [Wonton Soup Dashboard](/dashboards/wonton-soup/).*
