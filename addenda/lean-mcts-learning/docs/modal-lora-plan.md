# Modal LoRA Plan for Wonton-Soup Tactic Provider

This plan defines a reproducible path to train a new Lean tactic provider with Modal.

## Goal

Train a model that outputs `n` next-tactic candidates for MCTS expansion in `wonton-soup`.

Runtime contract:
- Input: current Lean goal state
- Output: ranked `(tactic, score)` candidates

## Constraints

- Current `export-learning` rows include `goal_type` and tactic outcomes, but not full
  per-node hypothesis strings.
- V1 training therefore uses `goal_type` as the state representation.
- V2 should add richer state logging (full hypotheses) if v1 is promising.

## Data Pipeline

1. Run `wonton.py export-learning` on one or more completed runs.
2. Convert exports to SFT JSONL rows in miniCTX-style prompt shape:
   - `[CTX]` theorem header up to `sorry`
   - `[STATE]` goal-only line: `⊢ <goal_type>`
   - target: `[TAC] <tactic> [/TAC]`
3. Train split and eval split are created in the Modal job.

Default label policy:
- `committed_success` (only successful tactics that were committed in the tree)

## Training Pipeline (Modal)

1. Upload dataset JSONL to Modal Volume.
2. Launch Unsloth LoRA training (default GPU: `L40S`, optional `A100-80GB`).
3. Save adapter checkpoints and run manifest to output Volume.
4. Resume from latest checkpoint when requested.

## Integration Path

1. Add provider that loads base model + adapter and returns ranked tactic candidates.
2. Add provider option to `orchestrator/lean.py` provider registry and CLI validation.
3. Benchmark against `reprover` and `deepseek` on identical corpus/budget/seeds.

## Acceptance Gates

- Primary: solve-rate delta on `research` corpus.
- Secondary:
  - tactic validity rate
  - per-call latency
  - candidate diversity

## Security / Secrets

- Do not hardcode tokens in code, files, or logs.
- Use Modal Secrets (for example `hf`) and read via environment variables at runtime.
- If a token has been pasted in chat/history, rotate it.
