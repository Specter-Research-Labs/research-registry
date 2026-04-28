# Solvable-1000 Corpus Build Runbook

Target: ~1000 theorems solvable by both reprover and deepseek at ≥90% rate.

## Current state

- 128 confirmed both-provider
- 145 needs reprover screen (mostly mathlib)
- 341 needs deepseek screen (mostly crossatp)
- 614 total known-solvable by at least one provider

## Step 1: Screen needs-reprover (145 theorems, CPU, ~1 hour)

These are deepseek-solved theorems that need reprover confirmation.
All 145 are in `solvable-both-v1`. Run reprover at tier-0 then tier-1.

```bash
cd /shared/dev/specter-labs-wonton-abstract-runfix/dossiers/wonton-soup

# Tier-0 pass (quick budget = 10 iterations)
.venv/bin/python wonton.py lean run \
  -m research \
  -c lean:solvable-both-v1 \
  -p reprover \
  -b quick \
  --wild-only \
  --plain \
  --no-trace-mcts \
  --tactic-ranker none \
  --device cpu \
  --workers 4 \
  --run-id solvable-1000-screen/reprover-tier0 \
  --no-sync
```

Estimated: ~30 min. Expected solve rate: 30-50% (these are pre-filtered
to known-solvable theorems from related corpora).

## Step 2: Screen needs-deepseek (341 theorems, needs GPU, ~1-2 hours)

These are reprover-solved theorems that need deepseek confirmation.
277 are in `solvable-both-v1`, 64 are only in `coq-paired-expanded-v2`.

```bash
# Part A: 277 from solvable-both-v1
.venv/bin/python wonton.py lean run \
  -m research \
  -c lean:solvable-both-v1 \
  -p deepseek \
  -b quick \
  --wild-only \
  --plain \
  --no-trace-mcts \
  --tactic-ranker none \
  --deepseek-samples 10 \
  --workers 8 \
  --run-id solvable-1000-screen/deepseek-tier0-solvable \
  --no-sync

# Part B: 64 from coq-paired-expanded-v2
.venv/bin/python wonton.py lean run \
  -m research \
  -c lean:coq-paired-expanded-v2 \
  -p deepseek \
  -b quick \
  --wild-only \
  --plain \
  --no-trace-mcts \
  --tactic-ranker none \
  --deepseek-samples 10 \
  --workers 8 \
  --run-id solvable-1000-screen/deepseek-tier0-crossatp \
  --no-sync
```

Expected solve rate: 60-80% (deepseek is stronger, these are known-solvable).

**Note:** Steps 1 and 2A can run in parallel if GPU is free — reprover
on CPU, deepseek on GPU.

## Step 3: Tier-1 escalation on tier-0 failures (~30 min each)

After steps 1-2, collect the tier-0 failures. Re-run with `-b standard`
which gives tiers [10, 50, 200, 1000]. Many "near-miss" theorems that
need 20-50 MCTS iterations will be caught here.

```bash
# Collect tier-0 failures, then re-run with standard budget.
# Use --resume to only process unsolved theorems.
# (Exact commands depend on step 1-2 results — see assemble script)
```

## Step 4: Assemble and assess

```bash
.venv/bin/python scripts/build_solvable_corpus.py harvest   # re-harvest with new data
.venv/bin/python scripts/build_solvable_corpus.py assemble --target 1000
```

Expected yield after steps 1-3:
- 128 already confirmed
- ~50-70 from reprover screen (145 candidates)
- ~200-270 from deepseek screen (341 candidates)
- ~50-100 from tier-1 escalation
- Total: ~430-570 confirmed-both

## Step 5: If still under 1000 — mine deepseek-prover-v1

Only if steps 1-4 yield <800 theorems. Screen a 3000-theorem sample from
deepseek-prover-v1 with reprover on CPU, then validate reprover-solved
subset with deepseek.

```bash
.venv/bin/python wonton.py corpus build-lean-deepseek-prover-v1 \
  --revision main --no-sync

.venv/bin/python wonton.py lean run \
  -m research \
  -c lean:deepseek-prover-v1 \
  -p reprover \
  -b quick \
  -n 3000 --sample 3000 --seed 42 \
  --wild-only --plain --no-trace-mcts \
  --tactic-ranker none \
  --device cpu --workers 4 \
  --run-id solvable-1000-screen/dsp-reprover \
  --no-sync
```

## Step 6: Run the campaign

```bash
# 4 stages, each ~1-2 hours on 1000 theorems
for provider in reprover deepseek; do
  for mode in centralized distributed; do
    .venv/bin/python wonton.py lean run \
      -m research \
      -c lean:solvable-1000-v1 \
      -p $provider \
      --mcts-mode $mode \
      -b standard \
      --trace-mcts \
      --plain \
      --workers 8 \
      --run-id "2026-04-04-solvable-1000/provider=${provider}/mcts=${mode}" \
      --no-sync
  done
done
```

## Timeline (optimistic, single day)

| Time | Activity | Compute |
|---|---|---|
| 08:00 | Step 1: reprover screen (145 thms) | CPU ×4 |
| 08:00 | Step 2A: deepseek screen (277 thms) | GPU (parallel with step 1) |
| 09:30 | Step 2B: deepseek screen (64 thms) | GPU |
| 10:00 | Step 3: tier-1 escalation on failures | GPU |
| 11:00 | Step 4: assemble, assess | trivial |
| 11:30 | Step 5: mine deepseek-prover-v1 (if needed) | CPU ×4 |
| 14:00 | Step 6: campaign stage 1 (reprover centralized) | GPU |
| 15:30 | Step 6: campaign stage 2 (reprover distributed) | GPU |
| 17:00 | Step 6: campaign stage 3 (deepseek centralized) | GPU |
| 18:30 | Step 6: campaign stage 4 (deepseek distributed) | GPU |
| 20:00 | Done | |
