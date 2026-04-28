# CLI And Reporting

The CLI now supports four compute-facing entry points:

- `compute`: validate one JSON request and emit one JSON result
- `sweep`: validate a batch of JSON/JSONL requests and emit summary rows
- `report`: render summary rows, or raw compute requests, as JSONL, CSV, or Markdown
- `benchmark`: run fixed reference demo cases and emit timings plus summary rows

## Compute Schema

Top-level keys:

- `trials`: required list of paired trial records
- `problem_space`: optional structured problem-space object
- `H`, `H_unit`, `w`, `w_unit`: legacy scalar inputs when `problem_space` is omitted
- `agent_policy`, `blind_policy`: optional policy names
- `agent_policy_spec`, `blind_policy_spec`: optional structured policy specs
- `bootstrap_samples`, `bootstrap_ci_level`, `bootstrap_seed`: optional uncertainty controls

`w` may be a scalar or an object:

```json
{
  "default": 1.0,
  "by_operator": {"move_b": 3.0},
  "description": "toy operator costs",
  "state_dependent": false,
  "unit": "joule"
}
```

## Batch Formats

`sweep --input` accepts:

- a single JSON object
- a JSON array of objects
- a JSON object with `cases: [...]`
- JSONL with one object per line

`report --input` accepts either summary rows or raw compute requests.

`benchmark` is intentionally narrow. It runs a small deterministic suite of
reference demos with fixed seeds so runtime changes and formatting regressions
are easy to spot in review.

Example:

```bash
uv run python -m paper_k benchmark --case sorting-small --case bitstring-small --format markdown
```

Benchmark rows include the same `K_restricted_mean_at_stop` and solve-rate
columns as sweep/report output, plus `mean_wall_sec`, `min_wall_sec`, and
`max_wall_sec`.

## Python Surface

If you need executable problem spaces or exact finite-horizon calculations, use
the Python API directly:

- `ProblemExecutor`
- `ExecutablePolicy`
- `compare_policies_in_problem_space(...)`
- `exact_finite_horizon_metrics(...)`

## Golden Report Guard

The CLI tests pin an exact Markdown rendering in
`tests/fixtures/report_markdown_golden.md`. When the report layout or numeric
formatting changes, update that fixture deliberately in the same patch so the
review surface stays explicit.
