# ProofGraphIR

`ProofGraphIR` is the cross-assistant graph abstraction used by
`analysis/cross_assistant_alignment.py`.

## Why It Exists

Raw graph artifacts from different assistants are not directly comparable:

- Lean wild-type graphs are small tactic-search traces.
- Coq extraction graphs are proof-term DAGs with structural edges (`fn`, `arg`, ...).

Without an IR layer, distance is dominated by raw scale mismatch (node/edge counts), which can
collapse nearest-neighbor retrieval.

## IR Fields

Per theorem graph, `ProofGraphIR` records:

- `graph_family`: `search_trace` | `proof_term_dag` | `external_proof` | `unknown`
- structural size: node/edge counts, max depth, root count
- topology ratios: leaf ratio, branching ratio, mean branch factor
- edge-role profile:
  - search traces: `fam:<tactic_family>`
  - term DAGs: structural roles (`fn`, `arg`, `binder_type`, `body`, `value`)
- assistant-agnostic operator profile (shared ontology), for example:
  - `apply`, `bind`, `branch`, `rewrite`, `normalize`, `close`, `automation`, `value`, `other`
- assistant-agnostic motif profile (action motifs), for example:
  - `motif:term_apply`, `motif:term_bind`, `motif:bind_open`, `motif:branch_split`,
    `motif:rewrite_step`, `motif:close_goal`
- action-layer summaries derived from `TacticActionIR`:
  - `action_kind_profile`
  - `effect_profile`
  - `continuation_profile`
  - `coupling_profile`
- Lean search traces can also carry explicit step dependencies and spawned-goal summaries through
  edge metadata and assembly-trace `actionMetadata`
- shape hash: WL hash over canonicalized graph

Run-relative rank features are derived separately at comparison time:

- `node_rank`, `edge_rank`, `depth_rank`, `leaf_rank`, `branching_rank`

These are computed per graph family within a run and are not intrinsic IR fields.

## Kind Inference

Inference combines:

- edge-role composition (term-edge fraction)
- ordered expansion edges (`order`) as a search-trace signal
- node `goal_type` hints for proof-term DAGs (`app`, `const`, `lam`, ...)
- backend hint from run config when available

Legacy Coq `proof_graph` artifacts are also repaired here when they are actually term-structural:
if an unversioned graph is dominated by structural term edges and node hints, the IR upgrades it to
`proof_term_dag` semantics instead of treating it as a generic external-proof trace.

When `proof_term_graph` is available, the Coq side can carry richer node metadata than
`wild_type_graph`, including constructor names and binder metadata. That metadata feeds the current
term-action enrichment for constructors such as `Case`, `Prod`, and `Cast`.

## Distance Contract

Graph distance is kind-aware:

- Same-kind:
  - rank-distance + operator-profile L1 + motif-profile L1 + edge-role L1
  - plus `action_kind`, `effect`, `continuation`, and `coupling` profile deltas
  - plus shape mismatch
- Cross-kind:
  - rank-distance + operator-profile L1 + motif-profile L1
  - plus action/effect/continuation/coupling profile deltas
  - plus a small fixed mismatch penalty
  - role/shape channels are still suppressed because their semantics are incompatible

Full pair distance then combines graph, lexical token Jaccard, and connective-profile distance,
with higher lexical/connective weight in cross-kind mode.

The aligner can now ablate lexical channels explicitly:

- `--lexical-ablation drop_tokens`: remove theorem/display/constant token overlap while keeping
  connective profiles
- `--lexical-ablation graph_only`: remove both lexical tokens and connective profiles

## What This Enables

- Explicit comparability semantics instead of implicit assumptions
- Diagnostics that separate structural mismatch from lexical mismatch
- Reduced retrieval collapse caused by absolute size bias
- Theorem-level inspection via `wonton.py inspect-proof-ir`, including action traces and
  pair-distance component breakdowns

## Current Limits

- Cross-kind matching still relies heavily on lexical/statement signals.
- Coq `proof_term_graph` is the richer surface for cross-kind diagnostics; older
  `wild_type_graph` logs can preserve the right topology while still dropping constructor metadata.
- Goal coupling is only as good as the producer path; some legacy or imported graphs still lack
  explicit coupling data.
- Current motif ontology is lightweight and requires expansion for richer proof-process semantics.

## Next Steps

- Expand `TacticActionIR` so Lean search traces can distinguish explicit continuation builders and
  real goal coupling.
- Add proof-state transition motifs (for search traces) and beta/eta-normalized motifs (for terms).
- Evaluate with translated theorem pairs where statements are intentionally obfuscated, so graph
  channels are stress-tested independently of theorem names. The new lexical ablation modes provide
  the first local benchmark lever for that stress test.
- Treat
  [TacticActionIR](tactic-action-ir.md)
  as the current step-level contract feeding this graph IR, while the addendum stays focused on the
  longer-term research question about richer tactic representation.

## External Research Anchors

- Lean expression-graph representation and retrieval context: <https://arxiv.org/abs/2403.11339>
- Graph-structured Coq tactic prediction: <https://arxiv.org/abs/2412.11099>
- Proof-format interoperability layer (Dedukti): <https://arxiv.org/abs/1409.1023>
- Multi-assistant formal-math translation setting (Logipedia direction): <https://arxiv.org/abs/2404.16100>
