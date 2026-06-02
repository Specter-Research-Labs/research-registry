# Wonton Soup Docs

Documentation map for `dossiers/wonton-soup`.

## Mode Framing

`wonton-soup` perturbs MCTS proof search and measures what survives. Centralized runs map proof families, basin stability, rerouting, collapse, and blind-relative efficiency (K). Distributed runs test whether coordinated controllers change access to the same landscape.

## Concepts

- Analysis terminology index: [Analysis Lexicon](concepts/analysis-lexicon.md)
- Metric-family definitions: [Analysis Metrics Reference](concepts/analysis-metrics.md)
- Attractor/basin metrics deep dive: [Attractor Metrics for Proof Search](concepts/attractor-metrics.md)
- Distributed MCTS scheduling and control semantics: [Distributed MCTS Semantics](concepts/distributed-mcts.md)
- Goal identity, deduplication, and preview/commit: [Goal Identity, Deduplication, and Preview/Commit](concepts/goal-deduplication-and-preview-commit.md)
- Cross-assistant proof graph abstraction: [ProofGraphIR](concepts/proof-graph-ir.md)
- UCB1 behavior and tuning in this repo: [UCB1 and Blind-Uniform Search in Wonton-Soup](concepts/ucb1.md)

## Contracts

- Artifact definitions: [Analysis Artifacts Reference](contracts/analysis/analysis-artifacts.md)
- Log schema index: [Log File Schemas](contracts/logs/log-file-schemas.md)
- Run-level schema details: [Log Schemas: Run-Level](contracts/logs/log-schemas-run-level.md)
- Per-theorem schema details: [Log Schemas: Per-Theorem Artifacts](contracts/logs/log-schemas-theorem-level.md)
- Backend artifact-family mapping: [Log Schemas: Backend Artifact Mapping](contracts/logs/log-schemas-backend-mapping.md)
- Distributed MCTS trace event dictionary: [Distributed MCTS Trace Event Dictionary](contracts/logs/distributed-mcts-trace-events.md)
- Partial proof-term extraction + sequential replay: [Partial Proof-Terms and Sequential Replay](contracts/backends/partial-proof-terms.md)
- Provider options and selection rubric: [Tactic Provider Options for Tactic Suggestion](contracts/providers/tactic-provider-options.md)
- DeepSeek runtime settings and reproducibility notes: [DeepSeek Provider Settings](contracts/providers/deepseek-provider-settings.md)

## Decisions

- ADR index: [ADR Index](decisions/README.md)

## Operations

- Setup: [Setup](ops/setup.md)
- Corpus artifacts: [Corpus](ops/corpus.md)
- Lake, jobs, exports, and preservation: [Lake](ops/lake.md)
- Verification, cross-assistant gates, and run inspection: [Verification](ops/verification.md)
- Paper rebuild workflow: [Paper](ops/paper.md)
