# Lean MCTS Learning (Addendum)

Trains small value, policy, and reranking models from wonton-soup logs.

Scope:
- Offline training loops
- Consumes exported data from wonton-soup (`wonton.py export-learning`)
- Modal-based LoRA/SFT experiments for tactic prediction

## Modal Tactic SFT

V1 target is next-tactic SFT from `wonton-soup` traces using miniCTX-style prompt shape.

The canonical package CLI for the non-Modal tools is `lean-mcts-learning`.

### 1) Export learning rows from wonton-soup

```bash
uv --project dossiers/wonton-soup run python dossiers/wonton-soup/wonton.py export-learning \
  --run-dir dossiers/wonton-soup/logs/<run_id> \
  --out-dir ./tmp/learning
```

### 2) Build SFT dataset JSONL

```bash
uv run lean-mcts-learning build-tactic-sft-dataset \
  --run-dir dossiers/wonton-soup/logs/<run_id_a> \
  --run-dir dossiers/wonton-soup/logs/<run_id_b> \
  --variants wild_type \
  --label-policy committed_success \
  --skip-unloadable-runs \
  --out tmp/tactic_sft.jsonl
```

Notes:
- Repeat `--run-dir` to merge many runs into one dataset.
- Use `--provider <name>` only when a run dir is a multi-provider root.
- Use `--skip-unloadable-runs` when some run corpora are unavailable in the current environment.
- This script imports `wonton-soup` modules, so run it with `--project dossiers/wonton-soup`.

### 3) Create Modal secrets and run training

```bash
modal secret create hf HF_TOKEN=$HF_TOKEN
uv --project addenda/lean-mcts-learning run modal run addenda/lean-mcts-learning/modal_jobs/tactic_sft.py \
  --dataset-path tmp/tactic_sft.jsonl \
  --dataset-relpath data/tactic_sft.jsonl \
  --output-subdir runs/tactic-v1 \
  --gpu l40s \
  --max-steps 1000
```

Notes:
- The training script expects Modal secret `hf` for Hugging Face model access.
- V1 uses `goal_type`-only state because current exports do not include full hypotheses.

## Family-Prior Replay Evaluation

Use replay evaluation to estimate whether a learned ranker is helping before rerunning full corpora.

### 1) Train ranker from a completed run

```bash
uv --project dossiers/wonton-soup run python dossiers/wonton-soup/wonton.py train-family-prior \
  --run-dir dossiers/wonton-soup/logs/<run_id> \
  --out-dir tmp/learning
```

### 2) Replay-evaluate alpha sweep on traces

```bash
uv run lean-mcts-learning eval-family-prior-replay \
  --run-dir dossiers/wonton-soup/logs/<run_id> \
  --model tmp/learning/<run_id>/family_prior.json \
  --alphas 0,0.1,0.25,0.5,0.75,1.0 \
  --out tmp/learning/<run_id>/family_prior_replay_eval.json
```

Notes:
- Run this script with the `dossiers/wonton-soup` project because it imports runtime modules.
- `alpha=0` is provider ordering baseline; compare higher alphas against it before enabling ranker in runtime.

## Batch Evaluation Across Many Runs

To rank model usefulness across a set of runs, use the batch runner. It trains one model per run,
replay-evaluates each run, and writes one leaderboard JSON.

```bash
uv run lean-mcts-learning batch-family-prior-eval \
  --run-dir dossiers/wonton-soup/logs/<run_id_a> \
  --run-dir dossiers/wonton-soup/logs/<run_id_b> \
  --out-root tmp/learning-batch \
  --alphas 0,0.1,0.25,0.5,0.75,1.0 \
  --overwrite
```

Output:
- `tmp/learning-batch/family_prior_batch_eval.json` with:
  - weighted aggregate metrics by alpha,
  - per-run baseline (`alpha=0`) vs best nonzero alpha,
  - a conservative per-run alpha recommendation.

Optional run list file:

```bash
uv run lean-mcts-learning batch-family-prior-eval \
  --run-list tmp/run_dirs.txt \
  --out-root tmp/learning-batch \
  --overwrite
```

### Value Model

```bash
uv run lean-mcts-learning train-value \
  --dataset tmp/node_dataset.jsonl.gz \
  --out tmp/value_model.json
```
