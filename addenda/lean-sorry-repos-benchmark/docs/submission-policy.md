# Submission Policy (Beta)

The benchmark is open and self-serve. Anyone can run and publish results if they follow the
protocol below.

## Required Submission Artifacts
- `suite_results.json`
- `suite_results.jsonl`
- `suite_summary.md`
- `suite_config.json` (or equivalent config used for the run)
- `split_manifest.json`
- `contamination_report.json`
- `heldout_test_commitments.json`
- `SHA256SUMS`

## Minimum Validity Conditions
- `suite_results.json` must report all runs with `status == "success"`.
- `contamination_report.json` must satisfy:
  - `fractions.leak_fraction <= config.max_leak_fraction`.
- `SHA256SUMS` must verify for all submitted files.
- Any profile-based replay submission must include profile config and strict mode evidence:
  - `verification.repo_replay.profile_config_path` present
  - `verification.repo_replay.profile_strict == true`

## Claim Levels
- Harness claim:
  - run is valid and reproducible as submitted.
- Clean baseline claim:
  - all harness claim conditions, and `model_error_run_count == 0`.

## Disclosure Requirements
- Model identifier(s) and endpoint provider.
- Inference parameters used in run config.
- Verification mode (`none`, `synthetic`, or `repo_replay`).
- If `repo_replay`, include runtime manifest and profile config.

## Disallowed
- Mixing results from different split manifests under one leaderboard row.
- Editing output artifacts after checksum generation.
- Reporting replay results without profile config when strict mode is expected.

## Maintainer Notes
- This policy is intentionally lightweight during beta.
- Public leaderboard governance can add stronger controls later (for example hosted submission
  verification or sealed heldout replay infrastructure).
