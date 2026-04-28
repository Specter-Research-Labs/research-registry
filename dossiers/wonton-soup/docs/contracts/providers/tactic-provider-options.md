# Tactic Provider Options for Tactic Suggestion

Reference for the Lean tactic-provider surface used by MCTS and distributed MCTS.

## Provider Interface

```python
class TacticProvider(ABC):
    @abstractmethod
    async def suggest_tactics_with_probs_async(
        self, goal: LeanGoal, mvar_id: str, adapter: LeanAdapter, n: int = 10
    ) -> list[tuple[str, float]]:
        """Return up to n (tactic, probability) pairs."""
```

Serves as the compatibility boundary: search code consumes `(tactic, probability)` pairs and does not need provider-specific branching.

## Provider Registry and Exposure

CLI-exposed providers (`orchestrator/lean_inputs.py`, `PROVIDER_CHOICES`):

- `reprover`
- `deepseek`
- `bfs`
- `internlm`
- `heuristic`

Internal-only provider (implemented but not exposed via `--provider`):

- `AesopTacticProvider` (`prover/providers/base.py`)
  - Used as a programmatic helper, not a named CLI provider.
  - Wraps `adapter.get_tactic_suggestions(..., search_tactic="aesop?")` and returns uniform weights over suggestions.

## Construction Path and Easy-Tactic Gate

Provider construction happens in `create_provider(...)` (`orchestrator/lean_inputs.py`):

1. Build the base provider from `provider_name`.
2. If `block_easy=True`, wrap with `FilteredTacticProvider(blocked=EASY_TACTICS)`.

`wonton.py lean run` sets `block_easy = not --allow-easy`, so easy tactics are blocked by default unless `--allow-easy` is passed.

Default easy block set:

- `simp`
- `simp_all`
- `omega`
- `decide`
- `native_decide`
- `rfl`

## Provider Selection Semantics

Resolution order in CLI parsing (`main()`):

1. If `--all-providers`, use the full provider list in fixed order.
2. Else choose `raw = --providers` if present, otherwise `--provider`.
3. Parse comma list, trim, dedupe while preserving order.
4. Validate each name against `PROVIDER_CHOICES`.

Important parser constraints:

- `--all-providers` and `--providers` are mutually exclusive.
- `--provider all` is allowed and maps to all providers.
- Unknown provider names fail fast with the valid-provider list in the error.

## Single vs Multi-Provider Execution

Single provider:

- One `run_corpus(...)` invocation.
- One provider configuration in run metadata.

Multi-provider (`--all-providers` or multi-entry `--providers`):

- Sequential execution (not interleaved).
- One sub-run per provider, with provider-specific directories/metadata.
- `--basin-seeds` is forbidden in multi-provider mode.
  - Parser error: `"Multi-provider runs do not support --basin-seeds"`.

## Provider-Specific Runtime Knobs

Flags that override provider constructor sample counts:

- `--deepseek-samples` -> `DeepSeekTacticProvider(num_samples=...)`
- `--bfs-samples` -> `BFSProverTacticProvider(num_samples=...)`
- `--internlm-samples` -> `InternLMStepProverTacticProvider(num_samples=...)`

Validation:

- Each must be `>= 1` when provided.
- Values are passed through unchanged for matching providers.
- Non-matching providers ignore the unrelated sample flag.

Example:

```bash
uv run python wonton.py lean \
  --provider deepseek \
  --deepseek-samples 32 \
  --bfs-samples 8
```

This run only applies `--deepseek-samples`; BFS is not instantiated.

## Tactic Ranker Compatibility

Rankers are provider-agnostic reorderers:

- `--tactic-ranker family_prior` with `--tactic-ranker-model PATH`
- optional blend knob `--tactic-ranker-alpha` in `[0, 1]`

Runtime contracts enforced in search code (`prover/mcts.py` and `experiments/distributed_mcts/core.py`):

- ranker output must have the same length as input
- ranker output must contain the same tactic-probability pairs (reordering only)

Violations raise `ValueError` immediately.

## Available Runtime Providers

### ReProver (`reprover`)

- Model: `kaiyuy/leandojo-lean4-tacgen-byt5-small`
- Strengths: lightweight baseline, comparability with LeanDojo-style work
- Limitations: may emit some Mathlib3-style tactics
- Default provider for `wonton.py lean run`

### DeepSeek (`deepseek`)

- Model: `l3lab/ntp-mathlib-context-deepseek-coder-1.3b`
- Runtime: local MLX inference (`mlx_lm`)
- Decoding: sampling-first in this integration
- Strengths: Lean4 syntax quality and candidate diversity
- Limitations: larger footprint, stochastic outputs

### BFS-Prover (`bfs`)

- Model: `ByteDance-Seed/BFS-Prover-V1-7B`
- Runtime: local HuggingFace transformers
- Prompt shape: proof-state text + `:::`, continuation parsed as tactic
- Strengths: larger-model breadth
- Limitations: higher resource cost

### InternLM Step Prover (`internlm`)

- Model: `internlm/internlm2_5-step-prover`
- Runtime: local HuggingFace transformers
- Prompt shape: `NAME / PROOF_BEFORE / STATE_BEFORE / TACTIC`
- Strengths: step-structured generation
- Limitations: model-card license marked `other` (opt-in usage)

### Heuristic (`heuristic`)

- Implementation: `GoalAwareTacticProvider`
- Strengths: deterministic, no model weights
- Limitations: narrower tactic surface than model-backed providers

## Adding Another Lean Provider

If you add a new provider, keep one path:

1. Implement `TacticProvider` in `prover/providers/`.
2. Wire it in `create_provider(...)` in `orchestrator/lean_inputs.py`.
3. Add its name to `PROVIDER_CHOICES`.
4. Extend CLI help text and validation docs here.
5. Capture provider config in `_provider_config(...)` so logs remain reproducible.

Avoid adding a second provider-selection stack outside `create_provider(...)`.

## Related Notes

- DeepSeek decoding/config details: [DeepSeek Provider Settings](docs/contracts/providers/deepseek-provider-settings.md)
- Search-side metric semantics consuming provider outputs: [Analysis Metrics Reference](docs/concepts/analysis-metrics.md)
- Search policies and UCB/blind behavior: [UCB1 and Blind-Uniform Search in Wonton-Soup](docs/concepts/ucb1.md)
- Distributed scheduling and constraints: [Distributed MCTS Semantics](docs/concepts/distributed-mcts.md)
- Distributed runner isolation rationale: [ADR: Distributed (Cell-View) MCTS Runner](docs/decisions/adr-distributed-mcts.md)
