# Analysis Lexicon (Wonton-Soup)

Canonical index for analysis terminology, artifact semantics, and metric families.

## Scope

Use this page to find the canonical definition source for a term. Detailed definitions live in:

- [Analysis Artifacts Reference](docs/contracts/analysis/analysis-artifacts.md)
- [Analysis Metrics Reference](docs/concepts/analysis-metrics.md)
- [Log File Schemas](docs/contracts/logs/log-file-schemas.md)

## Canonical References

- Log schemas: [Log File Schemas](docs/contracts/logs/log-file-schemas.md)
- Run inspection workflows: [Log Query Cookbook](docs/ops/log-query-cookbook.md)
- Cross-run lake operations: [Run Lake (Cross-Run DuckDB)](docs/ops/run-lake.md)
- Lake job materialization and references: [Lake Jobs (Materialized Datasets)](docs/ops/lake-jobs.md)

## Artifact Lexicon (Where/What)

Canonical artifact definitions and implementation pointers:

- `ExplorationHistory`, `MCTSTree`, search/proof/trace graph artifacts
- `ExprDAG` proof-term payloads and assembly traces
- `GoalCache` and signature mapping artifacts
- aggregate outputs (`summary.json.gz`, `analysis_report.json`, `failure_analysis.json`, etc.)

See: [Analysis Artifacts Reference](docs/contracts/analysis/analysis-artifacts.md).

## Metric Lexicon (Meaning/Validity)

Canonical metric families and validity boundaries:

- GED families (`ged_search_graph`, `ged_search_graph_soft`, `ged_proof_graph`, `ged_trace_graph`)
- goal-AST TED and soft distance metrics
- trajectory/detour/recovery metrics
- basin and K-style efficiency metrics
- novelty/sheaf/tactic-goal aggregate metrics

See: [Analysis Metrics Reference](docs/concepts/analysis-metrics.md).

## Naming and Comparison Invariants

- Do not compare metric families without explicit normalization and rationale.
- Treat `ged_trace_graph` as proxy-only unless a backend exposes true search state transitions.
- Treat `k_search_efficiency` as run-configuration dependent, not theorem-intrinsic.
- Keep goal-ID scheme and goal-signature scheme explicit in reports.

## Postprocess Ownership

Heavy metrics that are not computed in-run are owned by `wonton.py postprocess` and written into
`summary.json.gz` and per-variant `*_comparison.json` payloads.

Current postprocess-heavy fields include:

- `ged_search_graph_soft`
- `goal_novelty`
- `solution_path_soft_distance`
- `k_search_efficiency`

## Related Design Records

- Reference leakage guardrail: [ADR: Explicit Reference Selection for Lake Jobs](docs/decisions/adr-lake-reference-selection.md)
- Goal-ID scheme decision: [ADR: Checkpoint-Scoped Goal IDs](docs/decisions/adr-checkpoint-goal-ids.md)
- Backend trace/search feasibility: [ADR: Search-Graph Feasibility by Backend](docs/decisions/adr-search-graph-feasibility-by-backend.md)
