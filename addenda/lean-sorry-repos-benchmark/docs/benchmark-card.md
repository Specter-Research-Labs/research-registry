# Benchmark Card (Draft): `goal_to_tactic_proposal_v1`

## Identity
- Addendum: `addenda/lean-sorry-repos-benchmark`
- Entrypoint: `python -m lean_sorry_repos_benchmark`
- Schema version: `1`
- Task: given a Lean goal state, propose exactly one next tactic line.

## Scope
- Input unit: one row from `index.jsonl`.
- Output unit: one attempt record per `(item_id, sample_index)`.
- Adapters: `mock` (deterministic local baseline), `ollama` (local inference endpoint),
  `openai` (OpenAI-compatible chat completions endpoint).
- Verification modes: `none`, `synthetic`, `repo_replay`.

## Protocol
- Row loading validates required fields and fails on malformed rows.
- Selection is deterministic from `split_policy`, `goal_slice`, `seed`, and optional `max_items`.
- Multi-sample runs use deterministic per-attempt seeds from `(seed, item_id, sample_index)`.
- Verification only runs when generation had no error and tactic is non-empty and does not contain `sorry`/`admit`.
- `repo_replay` can load per-repo profile config (`schema_version: 1`) to override replay
  policy by `repo_remote` and/or `repo_lean_version`.

## Metrics And Outputs
- Proposal metrics (`summary.json`):
  - `valid_rate`, `nonempty_rate`, `contains_sorry_rate`
  - latency (`latency_ms_mean`, `latency_ms_p50`, `latency_ms_p95`)
  - generation error taxonomy (`generation_error_kinds`, `generation_error_domains`)
- Verification metrics (`summary.json`):
  - attempted/success/error rates and latency
  - `verification_pass_at_k_*` using item-level success aggregation
  - verification error taxonomy (`verification_error_kinds`, `verification_error_domains`)
- Output files:
  - `attempts.jsonl`
  - `summary.json`

## Reproducibility Invariants
- `selected_rows_hash` pins the selected item set.
- Optional deterministic sharding (`--shard-count`, `--shard-index`) partitions selected items by
  stable `item_id` hashing.
- Replay profile provenance is explicit in artifacts (`profile_config_path`, `profile_match_counts`,
  and per-attempt `repo_replay_profile_id`).
- Pass@k values are bounded to `samples_per_item`.
- Frozen split generation writes `split_manifest.json` and `contamination_report.json` with source index SHA-256 and split config.

## Known Limits
- Tactic extraction keeps only the first tactic line from model output.
- `synthetic` verification checks reconstructed scripts from `goal_text`; it is not equivalent to repo-context replay.
- `repo_replay` verifies patched-file Lean execution at `repo@commit`; it is first-pass and not full-project CI orchestration.
