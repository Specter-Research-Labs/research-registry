---
summary: "Index of the Wonton Soup log schemas, the invariants across their files, and which search, proof and trace graph artifacts each proof backend produces."
---

# Log file schemas

Schema index for wonton-soup run artifacts.

## How to use this reference

- For field-level run metadata and top-level files: [Log schemas: run level](docs/contracts/logs/log-schemas-run-level.md)
- For per-theorem variant artifacts: [Log schemas: per-theorem artifacts](docs/contracts/logs/log-schemas-theorem-level.md)
- For backend capability/artifact-family mapping: [Backend artifact mapping](#backend-artifact-mapping) below
- For distributed trace JSONL event fields: [Distributed MCTS trace event dictionary](docs/contracts/logs/distributed-mcts-trace-events.md)

## Scope boundary

This index defines ownership and cross-file invariants. Detailed JSON examples live in the split
schema documents listed above.

## Cross-file invariants

- Lean goal IDs in logs are checkpoint-scoped IDs (`cp<checkpoint>:<lean_mvar_id>`).
- `run_status.json` capability flags govern optional artifact expectations.
- GED family fields are family-specific and must include validity metadata.
- Postprocess-enriched fields may be absent or placeholder-valued before postprocess runs.

## Postprocess ownership

`wonton.py postprocess` may update existing run artifacts in place (notably `summary.json.gz` and
`*_comparison.json`).

Postprocess-owned enrichments include:

- `ged_search_graph_soft`
- `goal_novelty`
- `solution_path_soft_distance`
- `k_search_efficiency`

## Multi-provider layout

Multi-provider runs place complete single-provider runs under `provider=<name>/` with top-level
provider aggregate files. See run-level schema doc for exact fields.

## Backend artifact mapping

Canonical mapping from backend capabilities to artifact families.

### Artifact families

- Search graph: interactive search-state transition structure
- Proof graph: derivation/proof-object structure
- Trace graph: proxy graph derived from protocol/log traces

### Backend mapping

| Backend | Search Graph | Proof Graph | Trace Graph | Notes |
|---|---|---|---|---|
| Lean | Yes (`*_graph.json`) | Optional derived proof subgraph | n/a | Interactive REPL + tactic-level search |
| Coq | No true search graph in external mode | Yes | Yes (`serapi_replay`) | Replay emits `*_process_trace.json.gz` plus `*_search_trace_graph.json` |
| E prover | No true interactive search graph | Yes | Optional | Trace/proof outputs are proxy surfaces for search behavior |
| Vampire | No true interactive search graph | Yes | Optional | Typically proof-object oriented |
| Z3 | No true interactive search graph | Yes | Optional | Proof/trace surfaces are solver-internal projections |

### GED family selection rules

- Use `ged_search_graph` only with true search graph artifacts.
- Use `ged_proof_graph` for proof-object families.
- Use `ged_trace_graph` when only trace-derived proxy graphs are available.

When using `ged_trace_graph`, payloads must include:

- `trace_source`
- `trace_completeness`
- explicit validity notes for comparability limits

### Reporting constraints

- Do not compare GED values across families without explicit normalization and rationale.
- Treat trace-family results as proxy evidence unless backend instrumentation provides true
  search-state transitions.

### Related ADR

- [ADR: search-graph feasibility by backend](docs/decisions/adr-search-graph-feasibility-by-backend.md)
