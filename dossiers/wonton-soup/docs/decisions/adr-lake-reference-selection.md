---
summary: "Decision record: lake jobs that build reference outcomes must select the reference population explicitly, to avoid in-sample leakage."
---

# ADR: explicit reference selection for lake jobs

## Context

Reference-based scoring (notably K-style goal-outcome scoring) can leak in-sample information when
reference populations are implicitly derived from evaluation populations.

If a job evaluates runs and also builds reference outcomes from those same runs by default,
comparison looks cleaner than justified.

## Decision

When `reference.build_outcomes` is set in a lake job config, `reference.selection` must be a
non-empty object.

Enforced when the config is loaded, in `analysis.lake.job_config.load_job_config()`, and again in
`analysis.lake.job.run_job()`.

## Problem Statement

Lake jobs need to support:

- selecting evaluation runs (`job.selection`)
- selecting reference-member runs (`reference.selection`)
- optionally scoring against the built/attached reference

Implicitly reusing `job.selection` for reference membership is too error-prone.

## Options Considered

1. Implicit reference selection from `job.selection`
2. Explicit reference selection (chosen)
3. Disallow reference building inside jobs

## Examples

### Invalid (rejected)

```json
{
  "schema_version": 2,
  "name": "k_scores",
  "selection": {"provider": "reprover"},
  "reference": {"build_outcomes": {"alpha": 1.0}, "score_k": true},
  "datasets": [{"name": "runs", "query": "SELECT * FROM selected_runs ORDER BY run_key"}]
}
```

Reason: `reference.selection` missing.

### Valid (explicit in-sample)

```json
{
  "schema_version": 2,
  "name": "k_scores",
  "selection": {"provider": "reprover"},
  "reference": {
    "build_outcomes": {"alpha": 1.0},
    "selection": {"provider": "reprover"},
    "score_k": true
  },
  "datasets": [{"name": "runs", "query": "SELECT * FROM selected_runs ORDER BY run_key"}]
}
```

### Valid (explicit out-of-sample)

```json
{
  "schema_version": 2,
  "name": "k_scores",
  "selection": {"provider": "deepseek"},
  "reference": {
    "build_outcomes": {"alpha": 1.0},
    "selection": {"provider": "reprover"},
    "score_k": true
  },
  "datasets": [{"name": "runs", "query": "SELECT * FROM selected_runs ORDER BY run_key"}]
}
```

## Consequences

- provenance is explicit in `manifest.json`
- leakage-prone defaults are blocked at config-load time
- in-sample references remain available, but only by explicit declaration

## Reporting Checklist

When publishing K-style results from lake jobs, report:

- evaluation selection filters
- reference selection filters
- whether reference is in-sample or out-of-sample
- reference `ref_id`

## References

- `analysis/lake/job_config.py`
- `analysis/lake/job.py`
