# DeepSeek Provider Settings

Runtime settings and reproducibility constraints for `DeepSeekTacticProvider`.

## Model and Loading Contract

- Model ID: `l3lab/ntp-mathlib-context-deepseek-coder-1.3b`
- Runtime: local MLX (`mlx_lm`) by default, or local Transformers with
  `--deepseek-backend transformers`
- Expected converted model location (default):
  - `$SPECTER_ARTIFACT_ROOT/wonton-soup/models/ntp-mathlib-deepseek-1.3b-mlx-bf16`
- The MLX config must expose the rotary settings in the fields read by
  `mlx_lm`: `rope_theta: 100000` and
  `rope_scaling: {"type": "linear", "factor": 4.0}`.
- The tokenizer must match the upstream ByteLevel tokenizer from the model repo.
  Stale local snapshots with Metaspace tokenizer metadata produce literal
  byte-level artifacts such as `Ġ` and `Ċ`.

Implementation: `prover/providers/deepseek.py` (`_resolve_model_path`).

The Transformers backend should point `--deepseek-model-path` at the local
Hugging Face checkpoint directory. It loads `tokenizer.json` with
`PreTrainedTokenizerFast` and explicit DeepSeek BOS/EOS tokens because the
checkpoint metadata can otherwise select a slow Llama tokenizer that corrupts
space tokens.

## Current Decoding Settings

Current code path uses stochastic sampling:

- sampler: `make_sampler(temp=0.6, top_p=0.9)`
- `max_new_tokens = 64`
- per-request generation count: `min(n, self._num_samples)`
- default `num_samples = 10`
- MLX decoding uses `batch_generate(...)` over repeated prompt copies, not a
  Python-side serial loop
- Transformers decoding uses `AutoModelForCausalLM.generate(...)` on MPS/CUDA/CPU
  with the same sampling temperature/top-p defaults
- prompt tokens are truncated to the 2048-token window by keeping both the prefix
  and suffix when the assembled prompt is too long
- prompt encoding uses the raw `tokenizer.json` when available so ByteLevel
  newlines and spaces are preserved
- generated batch text is normalized from ByteLevel artifacts before tactic
  extraction

Implementation: `prover/providers/deepseek.py` (`_generate_tactics`).

## Prompt Contract

Provider prompt includes:

- system instruction block
- `[CTX]` theorem/import context plus recent proof steps from the current assembly trace
- `[STATE]` pretty goal state
- `[TAC]` model completion region

Tactic extraction prefers text before `[/TAC]`, then falls back to first non-empty line.

## Caching and Batching Behavior

- LRU-style in-memory prompt cache (`cache_size` default 100)
- batched request drain with `batch_max_size = 8`
- latency stats tracked (`last_latency_ms`, `avg_latency_ms`)

Caching improves throughput but can reduce effective stochastic variation for repeated prompts.

## Reproducibility Contract

This provider currently does **not** expose explicit seed control in its public interface.
Reproducibility is therefore bounded by:

- MLX sampling internals
- runtime environment
- prompt cache effects

Practical guidance:

- For strict reproducibility studies, use deterministic providers or run paired baselines.
- For basin-style variability studies, record full run config and disable assumptions of
  deterministic replay.

## Resource Envelope (Operational)

Expected cost drivers:

- model load latency
- prompt length and sample count
- local MLX backend/device performance

Primary knobs affecting cost/variance:

- `--deepseek-backend` (`mlx` or `transformers`)
- `--deepseek-model-path`
- `num_samples` (provider-level)
- caller `n`
- decoding params (`temp`, `top_p`, `max_new_tokens`)

## Failure Modes and Mitigations

- Model path missing:
  - Ensure `$SPECTER_ARTIFACT_ROOT` is set and converted MLX model exists.
- Stale or incompatible converted metadata:
  - Refresh local tokenizer/config files from
    `l3lab/ntp-mathlib-context-deepseek-coder-1.3b`.
  - The provider rejects configs that contain only Hugging Face
    `rope_parameters` without the MLX-readable `rope_theta`/`rope_scaling`
    fields.
- Low diversity despite sampling:
  - Check prompt cache hit rate and effective `num_samples`.
- Unstable outputs across runs:
  - Treat as stochastic behavior; compare aggregates rather than single-run anecdotes.

## Change-Control Checklist

When changing DeepSeek decoding/runtime behavior:

1. Update `prover/providers/deepseek.py`.
2. Update this document.
3. Update [Tactic Provider Options for Tactic Suggestion](docs/contracts/providers/tactic-provider-options.md) if selection guidance changes.
4. Note reproducibility impact in run/report metadata.

## Related Docs

- Provider selection rubric: [Tactic Provider Options for Tactic Suggestion](docs/contracts/providers/tactic-provider-options.md)
- Metric semantics consuming provider outputs: [Analysis Metrics Reference](docs/concepts/analysis-metrics.md)
- Artifact schemas and capability fields: [Log File Schemas](docs/contracts/logs/log-file-schemas.md)
