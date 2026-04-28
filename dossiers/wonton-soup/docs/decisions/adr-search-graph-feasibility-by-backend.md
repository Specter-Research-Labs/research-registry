# ADR: Search-Graph Feasibility by Backend

## Context

Metric families in wonton-soup distinguish true search-state structure from proof-object structure
and trace-derived proxies. Not all backends provide an interactive search API.

## Decision

Use family-specific GED by backend capability:

- true search graph available: `ged_search_graph`
- proof-object derivation only: `ged_proof_graph`
- trace-derived proxy only: `ged_trace_graph`

For proxy trace graphs, require explicit labeling (`trace_source`, `trace_completeness`).

## Options Considered

1. Build true interactive search REPLs for all backends immediately
2. Use trace/proof proxies for non-interactive backends
3. Hybrid family policy by backend capability (chosen)

## Capability Matrix (Current)

| Backend | True Search Graph | Proof Graph | Trace Proxy | Confidence |
|---|---|---|---|---|
| Lean | yes | optional | n/a | high |
| Coq | partial/experimental | yes | optional | medium |
| E prover | no | yes | yes | high |
| Vampire | no | yes | optional | medium |
| Z3 | no | yes | optional | medium |

## Promotion Criteria (Proxy -> True Search)

A backend can move from trace proxy to true search graph only when all are satisfied:

1. stepwise external control over search state transitions
2. stable node identity semantics across steps
3. complete edge/action provenance suitable for graph reconstruction
4. acceptable runtime overhead for corpus-scale experiments

## Consequences

- avoids mixing incomparable graph families under one metric label
- enables immediate cross-backend analysis with explicit validity boundaries
- keeps instrumentation-heavy true-search integrations as deliberate future work

## Verification Requirements

When emitting `ged_trace_graph` payloads:

- set `trace_source`
- set `trace_completeness`
- include `valid` and `validity_notes`

Analysis/reporting layers must not treat proxy and true-search GED as interchangeable.

## References

- [Log Schemas: Backend Artifact Mapping](docs/contracts/logs/log-schemas-backend-mapping.md)
- [Analysis Metrics Reference](docs/concepts/analysis-metrics.md)
- [Log File Schemas](docs/contracts/logs/log-file-schemas.md)
