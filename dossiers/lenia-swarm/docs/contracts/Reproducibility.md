# Reproducibility Contract

## Purpose

Defines what must be captured so a run can be reproduced later.

## Required Inputs

- base config JSON
- search config JSON
- explicit seed schedule (`seed_start`, `seed_stride`, `count`)
- implementation-affecting switches (for example compatibility modes)

## Required Captures per Run

- copied `config.json` and `search.json` in run directory
- `summary.json` with run id and execution counts
- `results.jsonl` containing metrics and parameter payloads
- log stream and metrics stream for the same run id

## Required Captures per Indexed Record

- `run_id`
- provenance fields in `runs` table
- `config_hash` when available
- method/version tags for derived fields (for example morphometrics)

## Determinism Checks

Current deterministic smoke harness validates repeated fixed-seed runs by comparing:

- `results.jsonl` byte identity
- exported frame checksums

## Non-Goals

Does not guarantee bitwise identity across different hardware, compiler versions, or MLX backend revisions unless explicitly pinned by the experiment protocol.
