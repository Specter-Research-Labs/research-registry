# Log Schemas: Run-Level

Run-level schema contract for corpus outputs under `logs/corpus-YYYY-MM-DD-HHMMSS/`.

## Directory Layout (Single Provider)

Typical top-level files:

- `run_status.json`
- `run_config.json`
- `summary.json.gz`
- `goal_cache.json.gz` (Lean-capable runs)
- `postprocess_metrics.json` (if postprocess executed)
- `root_goal_similarity.json` (if computed)
- `external_statement_similarity.json` (external backends)
- `failure_analysis.json` / `analysis_report.json` / `sheaf_analysis.json` (optional analyses)
- `all_ged_matrices.json`
- `report.md`

## Agent-Mode CLI Events

`wonton.py --agent` emits JSONL events.

Lean example:

```json
{"event":"start","backend":"lean","provider":"reprover","run_id":"corpus-YYYY-MM-DD-HHMMSS","log_dir":"..."}
{"event":"end","status":"completed","backend":"lean","run_id":"corpus-YYYY-MM-DD-HHMMSS","summary_path":".../summary.json.gz","errors":[]}
```

## `run_status.json`

Purpose: lifecycle and capability gating.

Example:

```json
{
  "status": "completed",
  "started_at": "2026-01-26T12:30:36",
  "completed_at": "2026-01-26T13:18:02",
  "goal_id_scheme": "checkpoint",
  "partial_results": false,
  "capabilities": {
    "has_proof_term": true,
    "has_proof_term_pretty": true,
    "has_assembly_trace": true,
    "has_process_trace": true,
    "has_proof_term_metrics": true
  }
}
```

Notes:

- `status`: `running | completed | failed`
- `goal_id_scheme` must be treated as part of comparability contract
- failed runs may include `error` and `traceback`

## `run_config.json`

Purpose: reproducibility snapshot for run inputs.

Minimal example:

```json
{
  "format_version": 2,
  "run_id": "corpus-2026-02-04-143736",
  "log_dir": "/.../dossiers/wonton-soup/logs/corpus-2026-02-04-143736",
  "created_at": "2026-02-04T14:37:36",
  "provider": "heuristic",
  "mode": "dev",
  "corpus": "easy"
}
```

Multi-provider runs include provider arrays/metadata and per-provider subrun configs.

## `summary.json.gz`

Purpose: main aggregate payload for the run.

Core shape:

```json
{
  "run_id": "corpus-2026-01-07-120200",
  "goal_sig_scheme": "ast",
  "theorems": [
    {
      "name": "or_left",
      "wild_type": {"solved": true, "iterations": 2, "k_search_efficiency": {}},
      "interventions": [
        {
          "name": "block_left",
          "solved": true,
          "ged_search_graph": {
            "value": 2.0,
            "normalized": 0.12,
            "valid": true,
            "validity_notes": [],
            "trace_source": "mcts",
            "trace_completeness": "full"
          }
        }
      ]
    }
  ],
  "aggregates": {"theorem_count": 40, "wild_type_solve_rate": 0.7}
}
```

GED-family payload contract (when present):

- `value`, optional `normalized`
- `valid`
- `validity_notes`
- `trace_source`
- `trace_completeness`

## `goal_cache.json.gz`

Purpose: signature map + per-signature outcome aggregation.

Core shape:

```json
{
  "sig_scheme": "ast",
  "mvar_to_sig": {"cp1:_uniq.560": "sig_abc123"},
  "entries": {
    "sig_abc123": {
      "occurrences": {
        "cp1:_uniq.560": {"outcomes": {"0": [true, false, true]}}
      }
    }
  }
}
```

Note: `mvar_id` values are checkpoint-scoped IDs in Lean runs.

## `postprocess_metrics.json`

Purpose: provenance record for heavy metric computation.

Core shape:

```json
{
  "schema_version": 1,
  "valid": true,
  "computed_at": "2026-02-07T02:31:56+00:00",
  "params": {"max_soft_ged_nodes": 60, "max_root_goal_theorems": 400},
  "inputs": {"summary_sha256": "...", "goal_cache_sha256": "..."},
  "runs": [{"run_dir": "...", "updated_interventions": 4}]
}
```

## Similarity and Optional Analysis Files

### `root_goal_similarity.json`

Cross-theorem root-goal TED matrix and clustering.

### `external_statement_similarity.json`

External-corpus statement TED matrix and clustering.

### `failure_analysis.json`

Failure pattern categorization across unsolved variants.

### `sheaf_analysis.json`

Sheaf-inspired consistency/residual metrics.

## Multi-Provider Extension

Top-level files for multi-provider runs:

- `providers_summary.json`
- `providers_theorem_summary.json`
- `providers_report.md`

Each provider subdirectory (`provider=<name>/`) contains full single-provider run layout.
