# ADR: ProofGraphIR for Cross-Assistant Alignment

## Context

Cross-assistant alignment in wonton-soup compares theorem-level artifacts between Lean and Coq runs.

Before `ProofGraphIR`, graph distance directly mixed:

- Lean wild-type tactic-search traces (small, shallow, tactic-labeled)
- Coq proof-term DAGs (large, deep, structural-edge-labeled)

This produced a high risk of invalid structural conclusions because the compared graph families were
not semantically aligned.

## Research Findings (March 2, 2026)

From paired Lean↔Coq logic micro runs (`84` pairs):

- pre-IR alignment collapse:
  - `top1_unique_rate = 0.023810`
  - reciprocal top-1 rate `= 0.011905`
  - top-1 targets concentrated on two Coq theorems
- strong size confound:
  - correlation of pair rank with log Coq graph size `~0.918`
- graph-family mismatch:
  - Lean run classified as search traces
  - Coq run classified as proof-term DAGs

After first `ProofGraphIR` integration:

- retrieval quality improved:
  - `MRR: 0.122338 -> 0.321572`
  - `Recall@1: 0.023810 -> 0.226190`
  - `Recall@10: 0.309524 -> 0.500000`
- collapse reduced:
  - `top1_unique_rate: 0.023810 -> 0.392857`
  - reciprocal top-1 rate: `0.011905 -> 0.380952`
- size confound reduced:
  - rank/log-size correlation: `0.918 -> 0.084`

After enabling same-kind benchmark mode (`proof_term_graph` vs `proof_term_graph`, solved-only):

- same-kind support became explicit (`same_kind pairs = 36`, `cross_kind pairs = 0`)
- same-kind retrieval on this slice:
  - `MRR = 0.358735`
  - `Recall@1 = 0.25`
  - `Recall@10 = 0.583333`

The solved-only benchmark still missed gate at `Recall@10 = 0.277778` (threshold `0.30`), so this
is a major improvement but not final.

## Decision

Adopt `ProofGraphIR` as the required graph abstraction for cross-assistant alignment.

`ProofGraphIR` introduces:

- explicit graph kind (`search_trace`, `term_dag`, `unknown`)
- edge-role normalization
- shared operator-ontology profile (`apply`, `bind`, `branch`, ...)
- run-relative rank normalization by graph kind
- kind-aware graph distance and weighting
- report-time diagnostics:
  - `cross_kind_rate`
  - `kind_pair_distribution`
  - run-level graph-kind distributions

For cross-kind pairs, suppress role/shape channels and rely on normalized structural ranks plus
lexical/connective channels.

Paired benchmark now supports:

- deterministic name-obfuscated evaluation mode (`--name-obfuscation names`)
- `by_kind` summary and gate thresholds (`same_kind`, `cross_kind`)
- theorem-level proof aggregation modes (`single`, `best_of`, `consensus`)
- split gate axes (`coverage`, `quality`) with explicit cohort denominators

## Options Considered

1. Keep raw graph-size + family matching
2. Disable graph channel and use text-only matching
3. Add kind-aware IR with explicit comparability boundaries (chosen)

## Consequences

Positive:

- removes major size-driven artifacts from ranking
- makes comparability assumptions explicit in artifacts
- improves paired benchmark performance without hiding mismatch semantics

Costs and limits:

- cross-kind matching still depends heavily on statement/name lexical signal
- current runs are still mostly `search_trace -> term_dag` comparisons, not same-family structure
  comparisons
- cannot yet claim theorem-level proof-shape equivalence across assistants

## Claim Boundaries

Allowed:

- “We can compare cross-assistant theorem artifacts under explicit cross-kind semantics.”
- “Retrieval collapse from raw size mismatch is substantially reduced.”

Not allowed:

- “We are measuring identical proof shape across Lean and Coq.”
- “High retrieval alone implies proof-structure invariance.”

## Verification Requirements

Cross-assistant reports must include:

- graph-kind distributions for each run
- `cross_kind_rate`
- `kind_pair_distribution`
- paired retrieval metrics (`Recall@k`, `MRR`)

Any structural claim across assistants must report whether it is same-kind or cross-kind.

## Follow-On Decisions Needed

1. Expand operator-ontology v1 coverage for shared structural semantics.
2. Expand motif ontology coverage so cross-assistant action channels are not dominated by lexical
   spillover.
3. Build same-kind benchmark support (for example term-dag vs term-dag) so structural claims are
   not only cross-kind.

## References

- `analysis/proof_graph_ir.py`
- `analysis/cross_assistant_alignment.py`
- `analysis/cross_assistant_paired_benchmark.py`
- `$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_2026-03-02_v3_gated.json`
- `$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_paired_benchmark_2026-03-02_v3_ir1.json`
- `$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_alignment_diagnostic_2026-03-02_v3.json`
- `$SPECTER_SYNTHETIC_BUREAU_ROOT/cross_assistant_alignment_diagnostic_2026-03-02_v3_ir1.json`
- [Cross-Assistant Alignment (Diagnostic)](docs/ops/cross-assistant-alignment.md)
- [Cross-Assistant Paired Benchmark (Primary Gate)](docs/ops/cross-assistant-paired-benchmark.md)
