# Analysis Artifacts Reference

Canonical definitions for raw and derived analysis artifacts.

## Core Raw Artifacts

### ExplorationHistory

Per-iteration search trace: selected paths, tactic attempts, outcomes, and terminal flags.

- Implementation: `prover/history.py` (produced by `prover/mcts.py`)
- Outputs: `*_history.json`

### MCTSTree

Serialized MCTS state with visit/value data and node topology.

- Implementation: `prover/mcts.py`
- Outputs: `*_mcts_tree.json`

### Search Graph (Lean)

Directed graph of explored goals and tactic expansions.

- Implementation: `prover/proof.py` (`ProofGraph`)
- Outputs: `*_graph.json` with `graph_kind=search_graph`

### Proof Graph (External Backends)

Backend-derived proof object graph (not interactive search graph).

- Implementation: `atp/proof_objects.py` + backend parsers
- Outputs: `*_graph.json` with `graph_kind=proof_graph`

### Search Trace Graph (Proxy)

Trace-derived graph when true interactive search graph is unavailable.

- Outputs: `*_search_trace_graph.json`
- Required metadata: `trace_source`, `trace_completeness`

### Proof Process Trace (Replay)

Backend-native step trace used to derive proxy trace graphs without collapsing everything into the
final proof term.

- Implementation: `atp/coq/process_trace.py`
- Outputs: `*_process_trace.json.gz`

### Proof Term DAG (ExprDAG)

Semantic proof-term representation for hashing, diffing, and complexity.

- Implementation: `prover/expr.py`, `prover/adapters/lean.py`
- Outputs: `*_proof_term.json.gz`

### Proof Assembly Trace

Stepwise tactic-to-term assembly log.

- Implementation: `prover/assembly.py`, `prover/adapters/lean.py`
- Outputs: `*_assembly.json.gz`

### GoalCache

Maps checkpoint-scoped `mvar_id` values to signatures and outcome features.

- Implementation: `prover/goal_cache.py`, `prover/goal_features.py`
- Outputs: `goal_cache.json.gz`

## Aggregate Run Artifacts

### Summary

Primary run aggregate payload.

- Output: `summary.json.gz`
- Includes theorem/intervention summaries, aggregates, optional postprocess enrichments

### Failure Analysis

Heuristic failure-mode categorization.

- Implementation: `analysis/failures.py`
- Output: `failure_analysis.json`

### Corpus Classification Report

Intervention classification over structural and term-level features.

- Implementation: `analysis/corpus.py`
- Output: `analysis_report.json`

### Root Goal Similarity

Cross-theorem root-goal TED matrix + clustering.

- Implementation: `analysis/root_goal_similarity.py`, `analysis/postprocess_metrics.py`
- Output: `root_goal_similarity.json`

### External Statement Similarity

Cross-problem statement TED matrix for external corpora.

- Implementation: `analysis/external_statement_similarity.py`, `analysis/postprocess_metrics.py`
- Output: `external_statement_similarity.json`

### GED Matrix Bundle

Pairwise variant distances per theorem and optional cross-theorem aggregations.

- Outputs: `ged_matrix.json`, `all_ged_matrices.json`

## Lake Extraction Surfaces

Cross-run lake extraction consumes run artifacts into normalized tables.

- Implementations: `analysis/lake/reconcile.py`, `analysis/lake/db.py`, `analysis/lake/extract_basin.py`
- See operational reference: [Lake](../../ops/lake.md)

## Artifact Integrity Invariants

- Artifact capability is gated by `run_status.json` capability flags.
- Goal IDs in Lean artifacts are checkpoint-scoped IDs, not raw Lean IDs.
- Backend-specific artifacts must set correct family metadata
  (`graph_family`, `graph_backend`, `graph_provenance`, legacy `graph_kind`,
  `trace_source`, `trace_completeness`).

For exact field-level JSON schemas, use [Log File Schemas](docs/contracts/logs/log-file-schemas.md).
