---
summary: "Map of the Wonton Soup documentation on perturbed proof search: where to start, the measures, the run artifacts, the search machinery and the decision records."
---

# Wonton Soup docs

Wonton Soup runs Monte Carlo tree search (MCTS) over proofs, perturbs the search, and measures what survives. Centralized runs map which proof families the search finds, how stable its basins are, how it reroutes or collapses, and how much faster it is than blind search (K). Distributed runs test whether coordinated controllers change access to the same landscape.

## Start here

- [Analysis lexicon](concepts/analysis-lexicon.md): the terms used across the analysis and reports.
- [Analysis metrics reference](concepts/analysis-metrics.md): what each metric family measures.
- [Log file schemas](contracts/logs/log-file-schemas.md): what a run writes, and which graphs each proof backend can produce.

## Measures

- [Attractor metrics for proof search](concepts/attractor-metrics.md): basins of attraction in proof search, and when their size means something.
- [UCB1 and blind-uniform search](concepts/ucb1.md): how centralized search picks nodes and orders tactics, and the blind-uniform baseline.

## Run artifacts

- [Analysis artifacts reference](contracts/analysis/analysis-artifacts.md)
- [Log schemas: run level](contracts/logs/log-schemas-run-level.md)
- [Log schemas: per-theorem artifacts](contracts/logs/log-schemas-theorem-level.md)
- [Distributed MCTS trace event dictionary](contracts/logs/distributed-mcts-trace-events.md)

## Search machinery

- [Distributed MCTS](concepts/distributed-mcts.md): scheduling and control in distributed runs.
- [Goal identity, deduplication, and preview/commit](concepts/goal-deduplication-and-preview-commit.md)
- [ProofGraphIR](concepts/proof-graph-ir.md): the proof graph shared across proof assistants.
- [TacticActionIR](concepts/tactic-action-ir.md): a typed summary of what each proof step did.
- [Partial proof terms, assembly tracking, and sequential replay](contracts/backends/partial-proof-terms.md)
- [Tactic provider options for tactic suggestion](contracts/providers/tactic-provider-options.md)
- [DeepSeek provider settings](contracts/providers/deepseek-provider-settings.md)

## Decision records

- [ADR: checkpoint-scoped goal IDs](decisions/adr-checkpoint-goal-ids.md)
- [ADR: distributed (cell-view) MCTS runner](decisions/adr-distributed-mcts.md)
- [ADR: explicit reference selection for lake jobs](decisions/adr-lake-reference-selection.md)
- [ADR: ProofGraphIR for cross-assistant alignment](decisions/adr-proof-graph-ir-cross-assistant.md)
- [ADR: search-graph feasibility by backend](decisions/adr-search-graph-feasibility-by-backend.md)
