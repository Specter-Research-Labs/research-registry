# Wonton Soup Docs

Canonical documentation map for `dossiers/wonton-soup`.

## Mode Framing

`wonton-soup` is an intervention framework for studying proof-search structure. Centralized MCTS establishes the structural landscape: proof families, basin stability, recovery after lesion, and blind-relative efficiency (K). Distributed MCTS tests how collective control changes access to that landscape through multiple local controllers, coordination pressure, and scheduler lesions over a shared frontier.

The research stack is sequential. Centralized runs map the morphology and measure K as a single-controller baseline, comparable to the single-agent examples in Chis-Ciure and Levin (2025). Distributed runs then ask whether collective search creates efficiency that individual search does not access, and whether K decomposes across agents following the framework's compositionality property.

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

- Setup Lean + REPL environment: [Lean REPL Setup](ops/lean-repl-setup.md)
- Build/validate/sweep corpus artifacts: [Corpus Pipeline](ops/corpus-pipeline.md)
- Verification and representative command coverage: [Verification Matrix](ops/verification-matrix.md)
- Inspect run outputs with `jq` workflows: [Log Query Cookbook](ops/log-query-cookbook.md)
- Paired Lean↔Coq primary gate: [Cross-Assistant Paired Benchmark (Primary Gate)](ops/cross-assistant-paired-benchmark.md)
- Unpaired alignment diagnostic: [Cross-Assistant Alignment (Diagnostic)](ops/cross-assistant-alignment.md)
- Cross-run lake reconcile/export/sync: [Run Lake (Cross-Run DuckDB)](ops/run-lake.md)
- Lake jobs and reference selection: [Lake Jobs (Materialized Datasets)](ops/lake-jobs.md)
- Paper workflow runbook: [Paper Workflow Runbook](ops/paper-freeze.md)
- Follow-up run matrix and execution script: [Follow-Up Run Program (March 2026)](ops/followup-run-program.md)
