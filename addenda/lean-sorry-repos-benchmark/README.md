# lean-sorry-repos-benchmark

Benchmark harness for Lean `sorry` tasks.

Consumes benchmark index outputs from `../lean-sorry-dataset` and handles
split policy, scoring, and baseline runs. 

## Input Contract
- `index.jsonl`: canonical benchmark rows.
- `index.jsonl.manifest.json`: provenance and reproducibility metadata.

## Current Benchmark
`goal_to_tactic_proposal_v1`:
- Task: model proposes one next Lean tactic from a goal state.
- Adapter support:
  - `mock` (deterministic test adapter)
  - `ollama` (local model server)
  - `openai` (OpenAI-compatible chat completions endpoint)
- Goal slicing: `--goal-slice all|core_easy|non_core_easy`.
- Multi-sample protocol: `--samples-per-item` with `--pass-at-k` reporting.
- Metrics:
  - Proposal-level proxies (`valid_rate`, `nonempty_rate`, `contains_sorry_rate`, latency stats).
  - Verification metrics (attempted/success/error rates, latency, `verification_pass_at_k_*`).
  - Bootstrap confidence intervals for verification rates:
    - `verification_success_rate_total_ci`
    - `verification_success_rate_attempted_ci`
    - `verification_pass_at_k_success_rate_ci`
  - Error taxonomy and domains in `summary.json`:
    - generation: `generation_error_kinds`, `generation_error_domains`
    - verification: `verification_error_kinds`, `verification_error_domains`

## Validate
```bash
cd addenda/lean-sorry-repos-benchmark
uv run ruff check .
uv run ty check
uv run python -m pytest
```

## Release Smoke
```bash
cd addenda/lean-sorry-repos-benchmark
./scripts/release_smoke.sh
```

## Containerized Validation
Build and run the pinned runtime:
```bash
cd addenda/lean-sorry-repos-benchmark
docker build -t lean-sorry-repos-benchmark:local .
docker run --rm lean-sorry-repos-benchmark:local sh -lc '
  uv run ruff check . --no-cache &&
  uv run ty check &&
  uv run python -m pytest -q
'
```

Build replay-specific runtime (Lean + Lake + Elan pinned):
```bash
cd addenda/lean-sorry-repos-benchmark
./scripts/build_replay_runtime.sh \
  lean-sorry-repos-benchmark-replay:local \
  artifacts/replay-runtime
```

## Run (Mock)
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-smoke/index.jsonl \
  --adapter mock \
  --model mock-v1 \
  --max-items 100
```

## Run (Local Ollama Model)
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-with-goals/index.jsonl \
  --adapter ollama \
  --model qwen2.5-coder:7b \
  --max-items 100 \
  --split-policy repo_holdout \
  --repo-holdout-fraction 0.2
```

## Run (OpenAI-Compatible Hosted Model)
```bash
cd addenda/lean-sorry-repos-benchmark
export OPENAI_API_KEY=...
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-with-goals/index.licensed.jsonl \
  --adapter openai \
  --model gpt-5.2 \
  --openai-endpoint https://api.openai.com/v1/chat/completions \
  --openai-timeout-seconds 60 \
  --openai-max-tokens 64 \
  --max-items 100 \
  --split-policy repo_holdout \
  --repo-holdout-fraction 0.2
```

OpenRouter example:
```bash
cd addenda/lean-sorry-repos-benchmark
export OPENAI_API_KEY=...
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-with-goals/index.licensed.jsonl \
  --adapter openai \
  --model moonshotai/kimi-k2 \
  --openai-endpoint https://openrouter.ai/api/v1/chat/completions \
  --openai-timeout-seconds 60 \
  --openai-max-tokens 64 \
  --max-items 100
```

## Generate Frozen Benchmark Split Artifacts
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark split-artifacts \
  --index ../../tmp/lean-sorry-with-goals/index.jsonl \
  --out-dir ../../tmp/lean-sorry-frozen-split-v1 \
  --seed 7 \
  --repo-holdout-fraction 0.2 \
  --near-dup-jaccard-threshold 0.9 \
  --max-leak-fraction 0.0
```

Outputs:
- `public_dev.jsonl`
- `heldout_test.jsonl`
- `split_manifest.json`
- `contamination_report.json`

## Run (With Synthetic Lean Verification)
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-frozen-split-v1/public_dev.jsonl \
  --adapter ollama \
  --model qwen2.5:0.5b \
  --max-items 50 \
  --samples-per-item 5 \
  --pass-at-k 1 5 \
  --bootstrap-iters 2000 \
  --bootstrap-confidence-level 0.95 \
  --bootstrap-seed 7 \
  --verification-mode synthetic \
  --lean-cmd "lean" \
  --lean-timeout-seconds 20
```

You can repeat `--lean-import` to add module imports in synthetic scripts when your Lean
environment supports them.

## Run (With Repo Replay Verification)
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-frozen-split-v1/heldout_test.jsonl \
  --adapter mock \
  --model mock-v1 \
  --max-items 10 \
  --samples-per-item 3 \
  --pass-at-k 1 3 \
  --goal-slice core_easy \
  --verification-mode repo_replay \
  --repo-replay-lean-cmd "lake env lean" \
  --repo-replay-timeout-seconds 60 \
  --repo-replay-cold-start-timeout-seconds 120 \
  --repo-replay-prepare-cmd ""
```

`repo_replay` clones/fetches each repo into a cache, checks out `repo@commit`, patches the source
span at the target location, runs Lean, and restores the file after each attempt. It also caches
successful repo setup and failed setup states per `repo@commit`.

`repo_replay` now runs a preflight setup phase for all selected `repo@commit` targets before
inference starts and fails loud if setup cannot be prepared.

You can provide per-repository replay profiles to override replay policy by `repo_remote` and/or
`repo_lean_version`:
```bash
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-frozen-split-v1/heldout_test.jsonl \
  --adapter mock \
  --model mock-v1 \
  --verification-mode repo_replay \
  --repo-replay-profile-config configs/repo-replay-profiles.example.json \
  --repo-replay-profile-strict
```

`--repo-replay-profile-strict` fails fast if any selected row does not match exactly one profile.

Example profile config:
```json
{
  "schema_version": 1,
  "profiles": [
    {
      "id": "mathlib4",
      "match": {
        "repo_remote_prefix": "https://github.com/leanprover-community/mathlib4"
      },
      "overrides": {
        "lean_cmd": "lake env lean",
        "prepare_cmd": "lake build",
        "prepare_timeout_seconds": 1800,
        "timeout_seconds": 120,
        "cold_start_timeout_seconds": 240
      }
    }
  ]
}
```

Generate a real profile config from heldout rows:
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python scripts/generate_repo_replay_profiles.py \
  --index ../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/split-full/heldout_test.jsonl \
  --out ../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/repo-replay-profiles-heldout.json
```

Check strict profile coverage, then run strict replay preflight smoke:
```bash
cd addenda/lean-sorry-repos-benchmark
./scripts/repo_replay_strict_preflight.sh \
  ../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/split-full/heldout_test.jsonl \
  ../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/repo-replay-profiles-heldout.json \
  ../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/replay-preflight \
  25
```

Use deterministic sharding for distributed execution:
```bash
uv run python -m lean_sorry_repos_benchmark run \
  --index ../../tmp/lean-sorry-frozen-split-v1/heldout_test.jsonl \
  --adapter mock \
  --model mock-v1 \
  --verification-mode repo_replay \
  --shard-count 4 \
  --shard-index 0
```

## Run Benchmark Suite (Multiple Models, Shared Budget)
Create a suite config JSON:
```json
{
  "schema_version": 1,
  "common_args": [
    "--index",
    "../../tmp/lean-sorry-with-goals/index.jsonl",
    "--max-items",
    "100",
    "--split-policy",
    "repo_holdout",
    "--repo-holdout-fraction",
    "0.2",
    "--seed",
    "0",
    "--verification-mode",
    "none"
  ],
  "runs": [
    {"name": "mock-v1", "adapter": "mock", "model": "mock-v1"},
    {"name": "qwen-0.5b", "adapter": "ollama", "model": "qwen2.5:0.5b"}
  ]
}
```

Run the suite:
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark.suite_runner \
  --config ../../tmp/lean-suite.json \
  --out-dir ../../tmp/lean-suite-run \
  --max-parallel-runs 2
```

Output files:
- `attempts.jsonl`: per-item model outputs and validity flags.
- `summary.json`: run config, selection hash, aggregate metrics.
- `suite_results.jsonl`: one machine-readable suite row per run.
- `suite_results.json`: aggregate suite metadata + all run records.
- `suite_summary.md`: human-readable leaderboard table.

OpenRouter throttling reference run:
```bash
cd addenda/lean-sorry-repos-benchmark
uv run python -m lean_sorry_repos_benchmark.suite_runner \
  --config configs/openrouter-throttled-v3.json \
  --out-dir ../../tmp/lean-suite-openrouter-throttled-v3
```

Notes and interpretation are in `docs/openrouter-throttling-2026-03-01.md`.

## Release Docs
- Benchmark card: `docs/benchmark-card.md`
- Data card: `docs/data-card.md`
- Equivalents and gap analysis: `docs/release-equivalents.md`
- Replay runtime pinning: `docs/replay-runtime.md`
- Submission policy (beta): `docs/submission-policy.md`
- Release notes template: `docs/release-notes-template.md`

## Release Checklist
1. Run quality gates:
   - `uv run ruff check .`
   - `uv run ty check`
   - `uv run python -m pytest`
2. Build replay runtime and write runtime manifest:
   - `./scripts/build_replay_runtime.sh lean-sorry-repos-benchmark-replay:local artifacts/replay-runtime`
3. Generate replay profile config from heldout index and validate strict coverage:
   - `uv run python scripts/generate_repo_replay_profiles.py --index "$HELDOUT_INDEX" --out "$REPLAY_PROFILE_CONFIG"`
   - `uv run python scripts/check_repo_replay_profile_coverage.py --index "$HELDOUT_INDEX" --profile-config "$REPLAY_PROFILE_CONFIG"`
4. Generate pinned split artifacts with explicit split params:
   - `uv run python -m lean_sorry_repos_benchmark split-artifacts --index "$INDEX" --out-dir "$SPLIT_OUT" --seed "$SEED" --repo-holdout-fraction "$REPO_HOLDOUT_FRACTION" --near-dup-jaccard-threshold "$NEAR_DUP_JACCARD_THRESHOLD" --char-ngram-jaccard-threshold "$CHAR_NGRAM_JACCARD_THRESHOLD" --max-leak-fraction "$MAX_LEAK_FRACTION" --license-policy "$LICENSE_POLICY" --release-visibility "$RELEASE_VISIBILITY"`
5. Run pinned suite config against the pinned corpus/split:
   - `uv run python -m lean_sorry_repos_benchmark.suite_runner --config "$SUITE_CONFIG" --out-dir "$SUITE_OUT"`
6. Build the baseline bundle and write checksums (see next section).
7. Create annotated tags for data split and baseline run bundle.

## Failure Policy
- Release is blocked if any quality gate command exits non-zero.
- Release is blocked if split generation exits non-zero (including leak-threshold failures).
- Release is blocked if `contamination_report.json` shows `fractions.leak_fraction > config.max_leak_fraction`.
- Release is blocked if suite runner exits non-zero.
  - Exit code `2` means at least one infra failure in suite runs.
- Release is blocked if `suite_results.json` reports any run with `status != "success"`.
- Release is blocked if required baseline-bundle files are missing or checksum verification fails.
- `model_error_run_count > 0` is a baseline-claim blocker (you may ship harness changes, but not claim a clean baseline leaderboard run).

## Baseline Bundle (Pinned Outputs + Checksums + Tags)
Set release variables:
```bash
cd addenda/lean-sorry-repos-benchmark
export INDEX=../../tmp/lean-sorry-with-goals/index.jsonl
export HELDOUT_INDEX=../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/split-full/heldout_test.jsonl
export REPLAY_PROFILE_CONFIG=../../tmp/lean-sorry-release-v1-beta-open-only-ci-refresh-20260301/repo-replay-profiles-heldout.json
export SUITE_CONFIG=../../tmp/lean-suite.json
export RELEASE_ROOT=../../tmp/lean-sorry-release-v1
export SPLIT_OUT="$RELEASE_ROOT/split"
export SUITE_OUT="$RELEASE_ROOT/suite"
export BUNDLE_OUT="$RELEASE_ROOT/baseline-bundle"
export SEED=7
export REPO_HOLDOUT_FRACTION=0.2
export NEAR_DUP_JACCARD_THRESHOLD=0.9
export CHAR_NGRAM_JACCARD_THRESHOLD=0.85
export MAX_LEAK_FRACTION=0.0
export LICENSE_POLICY=open_only
export RELEASE_VISIBILITY=public
export DATA_TAG=lean-sorry-split-v1
export BASELINE_TAG=lean-sorry-baseline-v1
```

One-shot release-candidate runner:
```bash
INDEX="$INDEX" \
SUITE_CONFIG="$SUITE_CONFIG" \
RELEASE_ROOT="$RELEASE_ROOT" \
SPLIT_OUT="$SPLIT_OUT" \
SUITE_OUT="$SUITE_OUT" \
BUNDLE_OUT="$BUNDLE_OUT" \
SEED="$SEED" \
REPO_HOLDOUT_FRACTION="$REPO_HOLDOUT_FRACTION" \
NEAR_DUP_JACCARD_THRESHOLD="$NEAR_DUP_JACCARD_THRESHOLD" \
CHAR_NGRAM_JACCARD_THRESHOLD="$CHAR_NGRAM_JACCARD_THRESHOLD" \
MAX_LEAK_FRACTION="$MAX_LEAK_FRACTION" \
LICENSE_POLICY="$LICENSE_POLICY" \
RELEASE_VISIBILITY="$RELEASE_VISIBILITY" \
CREATE_TAGS=0 \
./scripts/run_release_candidate.sh
```

Create pinned outputs:
```bash
uv run python -m lean_sorry_repos_benchmark split-artifacts \
  --index "$INDEX" \
  --out-dir "$SPLIT_OUT" \
  --seed "$SEED" \
  --repo-holdout-fraction "$REPO_HOLDOUT_FRACTION" \
  --near-dup-jaccard-threshold "$NEAR_DUP_JACCARD_THRESHOLD" \
  --char-ngram-jaccard-threshold "$CHAR_NGRAM_JACCARD_THRESHOLD" \
  --max-leak-fraction "$MAX_LEAK_FRACTION" \
  --license-policy "$LICENSE_POLICY" \
  --release-visibility "$RELEASE_VISIBILITY"

uv run python -m lean_sorry_repos_benchmark.suite_runner \
  --config "$SUITE_CONFIG" \
  --out-dir "$SUITE_OUT"
```

Bundle required files and pin checksums:
```bash
mkdir -p "$BUNDLE_OUT"
cp "$SPLIT_OUT"/public_dev.jsonl "$BUNDLE_OUT"/
if [ -f "$SPLIT_OUT"/heldout_test.jsonl ]; then
  cp "$SPLIT_OUT"/heldout_test.jsonl "$BUNDLE_OUT"/
fi
cp "$SPLIT_OUT"/heldout_test_commitments.json "$BUNDLE_OUT"/
cp "$SPLIT_OUT"/split_manifest.json "$BUNDLE_OUT"/
cp "$SPLIT_OUT"/contamination_report.json "$BUNDLE_OUT"/
cp "$SPLIT_OUT"/artifact_checksums.json "$BUNDLE_OUT"/
cp "$SUITE_OUT"/suite_results.json "$BUNDLE_OUT"/
cp "$SUITE_OUT"/suite_results.jsonl "$BUNDLE_OUT"/
cp "$SUITE_OUT"/suite_summary.md "$BUNDLE_OUT"/
cp "$SUITE_CONFIG" "$BUNDLE_OUT"/suite_config.json

(
  cd "$BUNDLE_OUT"
  FILES=(
    public_dev.jsonl
    heldout_test_commitments.json
    split_manifest.json
    contamination_report.json
    artifact_checksums.json
    suite_results.json
    suite_results.jsonl
    suite_summary.md
    suite_config.json
  )
  if [ -f heldout_test.jsonl ]; then
    FILES+=(heldout_test.jsonl)
  fi
  shasum -a 256 "${FILES[@]}" > SHA256SUMS
  shasum -a 256 -c SHA256SUMS
)
```

Create tags after checksum verification:
```bash
git tag -a "$DATA_TAG" -m "lean sorry split release: $DATA_TAG"
git tag -a "$BASELINE_TAG" -m "lean sorry baseline release: $BASELINE_TAG"
git push origin "$DATA_TAG" "$BASELINE_TAG"
```

## Important Limitation
- `synthetic` verification is reconstructed from `goal_text`; it is stricter than text-only
  metrics but not equivalent to repository replay.
- `repo_replay` is still first-pass: it checks patched-file replay in repo context but does not yet
  implement full-project CI orchestration (for example, per-repository custom end-to-end pipelines
  and fleet-level distributed worker management for large public leaderboards).
