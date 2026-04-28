# Log Schemas: Per-Theorem Artifacts

Per-theorem schema contract for files under `logs/corpus-.../<theorem_name>/`.

## Graph Artifacts

### `*_graph.json`

Graph payload for a theorem variant.

- Lean: search graph (`graph_kind=search_graph`)
- External backends: proof graph (`graph_kind=proof_graph`)
- Canonical family metadata:
  - `graph_family`
  - `graph_backend`
  - `graph_provenance`
  - `graph_schema_version`

Example:

```json
{
  "graph_family": "search_trace",
  "graph_backend": "lean",
  "graph_provenance": "mcts",
  "graph_schema_version": 1,
  "graph_kind": "search_graph",
  "nodes": [{"id": "cp1:_uniq.560", "type": "P -> Q", "solved": true}],
  "edges": [{"source": "cp1:_uniq.560", "target": "cp1:_uniq.561", "tactic": "intro h"}],
  "root": "cp1:_uniq.560"
}
```

### `*_search_trace_graph.json`

Trace-derived proxy graph when true search graph is unavailable.

Coq replay traces also land here, with `trace_source=serapi_replay` and
`trace_completeness=script|partial`.

Required metadata:

- `trace_source`
- `trace_completeness`
- `valid`
- `validity_notes`

Example:

```json
{
  "graph_family": "search_trace",
  "graph_backend": "unknown",
  "graph_provenance": "proxy",
  "graph_schema_version": 1,
  "graph_kind": "trace_graph",
  "trace_source": "tstp",
  "trace_completeness": "proxy",
  "valid": true,
  "validity_notes": [],
  "nodes": [{"id": "c1", "goal_sig": "sig_abc123", "node_kind": "clause"}],
  "edges": [{"src": "c1", "dst": "c2", "action_family": "Resolution"}]
}
```

## Search and Assembly Traces

### `*_history.json`

Iteration-level search trace for one variant.

Example:

```json
{
  "iteration_count": 1,
  "solution_path": [{"goal": "P -> Q", "tactic": "intro h", "mvar_id": "cp1:_uniq.560"}],
  "iterations": [
    {
      "iteration": 0,
      "selected_path": ["cp1:_uniq.560"],
      "attempts": [{"tactic": "intro h", "outcome": "success", "child_mvar_ids": ["cp1:_uniq.561"]}],
      "terminal_reached": false
    }
  ]
}
```

### `*_assembly.json.gz`

Stepwise proof assembly trace.

Example:

```json
{
  "rootMvarId": "cp1:_uniq.560",
  "steps": [
    {
      "tactic": "intro h",
      "mvarId": "cp1:_uniq.560",
      "partialTermBefore": null,
      "partialTermAfter": {"proofTerm": {}},
      "goalsClosed": [],
      "goalsOpened": ["cp1:_uniq.561"],
      "actionMetadata": {
        "continuation_kind": "chain",
        "goal_coupling": "none",
        "effect_flags": ["opens_binder", "uses_hypotheses"],
        "depends_on_count": 1
      }
    }
  ],
  "finalTerm": {"rootId": "n0", "nodes": []}
}
```

### `*_process_trace.json.gz`

Backend replay/process trace when a backend can step through a proof script but does not expose a
true interactive search tree.

Current producer:

- Coq external extraction via SerAPI replay

Example skeleton:

```json
{
  "theorem": "and_assoc",
  "sourcePath": "/abs/path/to/Logic.v",
  "traceSource": "serapi_replay",
  "traceCompleteness": "script",
  "steps": [
    {
      "index": 1,
      "sentence": "split.",
      "commandKind": "tactic",
      "commandNorm": "split",
      "goalsBefore": {"focused": [{"goalId": "1", "goalType": "(Const goal_demo)"}]},
      "goalsAfter": {"focused": [{"goalId": "2"}, {"goalId": "3"}]},
      "proofTermBefore": "?demo",
      "proofTermAfter": "conj ?left ?right",
      "actionMetadata": {
        "tactic_family": "split",
        "branch_arity": 2,
        "continuation_kind": "branch"
      }
    }
  ]
}
```

### `*_proof_term.json.gz`

Final proof term only (`ExprDAG` payload):

```json
{"rootId": "n0", "nodes": [["n0", {"kind": "lam"}]]}
```

## Variant Metrics and Comparisons

### `*_metrics.json`

Per-variant metric summary.

Typical fields:

- `trajectory`
- `detour`
- `proof_term`
- `solution_path`
- optional pretty-print and fingerprint fields

### `*_comparison.json`

Intervention-vs-wild comparison payload.

Typical fields:

- intervention status
- hash and axiom deltas
- GED family payloads
- trajectory and novelty comparisons
- optional postprocess-heavy enrichments

Example skeleton:

```json
{
  "name": "block_simp",
  "solved": true,
  "ged_search_graph": {
    "value": 4.0,
    "normalized": 0.1,
    "valid": true,
    "validity_notes": [],
    "trace_source": "mcts",
    "trace_completeness": "full"
  },
  "ged_proof_graph": null,
  "ged_trace_graph": null,
  "goal_novelty": {"valid": true},
  "solution_path_soft_distance": {"valid": true}
}
```

Postprocess-owned sections may be placeholders before postprocess runs.

## Distance Matrix and Clustering

### `ged_matrix.json`

Pairwise variant distance matrix for one theorem.

### `attractor_clusters.json`

Clustering result over theorem variant distance matrix (when enough variants exist).

### `basin_analysis.json`

Multi-seed convergence summary (basin mode).

## Trace and Tree Optional Artifacts

- `*_mcts_tree.json`
- `*_mcts_trace.jsonl` (with tracing enabled)

Presence depends on run mode and flags.

Distributed trace field dictionary and examples:

- [Distributed MCTS Trace Event Dictionary](docs/contracts/logs/distributed-mcts-trace-events.md)
