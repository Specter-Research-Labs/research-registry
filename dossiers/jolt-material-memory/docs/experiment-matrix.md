# Experiment Matrix

Campaign config: `configs/paper_track_v1.json`

## Factors
- Scenarios: `imprint`, `hysteresis`, `damage`
- Backends: `cpu`, `metal`
- Policies:
  - `blind` with `memory=off` (baseline)
  - `directed` with `memory=off` (control)
  - `directed` with `memory=on` (treatment)
  - `directed` with `memory=inertial_control` (damping-only control; no memory state)
- Seeds: contiguous range from `seed_start` for `seed_count`

## Total Runs
`num_runs = seed_count * 3 scenarios * 2 backends * 4 policy/memory conditions`

For default config (`seed_count=40`):
- `40 * 3 * 2 * 4 = 960` runs

## Provenance
Each campaign records:
- config path
- timestamp
- JJ change/commit IDs
- Jolt revision tag
- full command line per run
- stdout/stderr log paths
- return code per run

## Related Docs
- [Metric Spec](./metric-spec.md)
