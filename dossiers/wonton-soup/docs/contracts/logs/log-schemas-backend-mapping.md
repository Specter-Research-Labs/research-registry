# Log Schemas: Backend Artifact Mapping

Canonical mapping from backend capabilities to artifact families.

## Artifact Families

- Search graph: interactive search-state transition structure
- Proof graph: derivation/proof-object structure
- Trace graph: proxy graph derived from protocol/log traces

## Backend Mapping

| Backend | Search Graph | Proof Graph | Trace Graph | Notes |
|---|---|---|---|---|
| Lean | Yes (`*_graph.json`) | Optional derived proof subgraph | n/a | Interactive REPL + tactic-level search |
| Coq | No true search graph in external mode | Yes | Yes (`serapi_replay`) | Replay emits `*_process_trace.json.gz` plus `*_search_trace_graph.json` |
| E prover | No true interactive search graph | Yes | Optional | Trace/proof outputs are proxy surfaces for search behavior |
| Vampire | No true interactive search graph | Yes | Optional | Typically proof-object oriented |
| Z3 | No true interactive search graph | Yes | Optional | Proof/trace surfaces are solver-internal projections |

## GED Family Selection Rules

- Use `ged_search_graph` only with true search graph artifacts.
- Use `ged_proof_graph` for proof-object families.
- Use `ged_trace_graph` when only trace-derived proxy graphs are available.

When using `ged_trace_graph`, payloads must include:

- `trace_source`
- `trace_completeness`
- explicit validity notes for comparability limits

## Reporting Constraints

- Do not compare GED values across families without explicit normalization and rationale.
- Treat trace-family results as proxy evidence unless backend instrumentation provides true
  search-state transitions.

## Related ADR

- [ADR: Search-Graph Feasibility by Backend](docs/decisions/adr-search-graph-feasibility-by-backend.md)
