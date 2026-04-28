# Log File Schemas

Schema index for wonton-soup run artifacts.

## How to Use This Reference

- For field-level run metadata and top-level files: [Log Schemas: Run-Level](docs/contracts/logs/log-schemas-run-level.md)
- For per-theorem variant artifacts: [Log Schemas: Per-Theorem Artifacts](docs/contracts/logs/log-schemas-theorem-level.md)
- For backend capability/artifact-family mapping: [Log Schemas: Backend Artifact Mapping](docs/contracts/logs/log-schemas-backend-mapping.md)
- For distributed trace JSONL event fields: [Distributed MCTS Trace Event Dictionary](docs/contracts/logs/distributed-mcts-trace-events.md)
- For operational inspection workflows: [Log Query Cookbook](docs/ops/log-query-cookbook.md)

## Scope Boundary

This index defines ownership and cross-file invariants. Detailed JSON examples live in the split
schema documents listed above.

## Cross-File Invariants

- Lean goal IDs in logs are checkpoint-scoped IDs (`cp<checkpoint>:<lean_mvar_id>`).
- `run_status.json` capability flags govern optional artifact expectations.
- GED family fields are family-specific and must include validity metadata.
- Postprocess-enriched fields may be absent or placeholder-valued before postprocess runs.

## Postprocess Ownership

`wonton.py postprocess` may update existing run artifacts in place (notably `summary.json.gz` and
`*_comparison.json`).

Postprocess-owned enrichments include:

- `ged_search_graph_soft`
- `goal_novelty`
- `solution_path_soft_distance`
- `k_search_efficiency`

## Multi-Provider Layout

Multi-provider runs place complete single-provider runs under `provider=<name>/` with top-level
provider aggregate files. See run-level schema doc for exact fields.
