# ADR: Checkpoint-Scoped Goal IDs

## Context

Raw Lean metavariable IDs are not globally unique across rollback-heavy search. The search stack
rolls REPL state back to prior checkpoints, and Lean can reuse raw `mvar_id` values after rollback.

Collision risk surfaces:

- `MCTSTree.nodes_by_mvar`
- adapter state maps (`LeanAdapter.states`)
- run artifacts keyed by `mvar_id` (history/graph/goal-cache/assembly payloads)

Failure modes:

- hard failures (duplicate-key behavior)
- silent overwrite of logically distinct goal states

## Decision

Use checkpoint-scoped goal IDs in all Lean search bookkeeping and logs:

```
cp<checkpoint_id>:<lean_mvar_id>
```

Example:

- raw ID at one branch: `_uniq.560`
- same raw ID after rollback elsewhere: `_uniq.560`
- logged IDs: `cp4:_uniq.560` and `cp9:_uniq.560` (distinct)

## Options Considered

1. Path-specific opaque IDs
2. Checkpoint-scoped IDs (chosen)
3. Full state-graph merge by semantic signature
4. Hybrid (unique IDs + shared stats)

Chosen option preserves tree semantics while fixing rollback collisions.

## Behavioral Impact

- Search policy semantics: unchanged (tree of attempts remains tree-shaped)
- Node cardinality: may increase because raw-ID reuse no longer collapses states
- Structural metrics: absolute counts may shift; post-migration runs remain comparable under one scheme
- Goal-cache accounting: now counts checkpoint-scoped occurrences explicitly

## Schema and Migration Impact

Affected artifact fields:

- `*_history.json`: `mvar_id`, `selected_path[]`, `child_mvar_ids[]`
- `*_graph.json`: node identifiers
- `goal_cache.json.gz`: `mvar_to_sig` keys and occurrence IDs
- `*_assembly.json.gz`: step-level target IDs and opened/closed lists

Compatibility guidance:

- do not combine raw-ID and checkpoint-ID runs in one metric population without explicit migration logic
- rely on `run_status.json.goal_id_scheme` to gate mixed-run analyses

## Implementation Notes

- adapter identity generation and state keys: `prover/adapters/lean.py`
- MCTS node identity handling: `prover/mcts.py`
- artifact readers should treat `mvar_id` as opaque, scheme-tagged identity

## Consequences

Pros:

- collision safety under rollback
- explicit scheme visible in run metadata
- reproducible identity semantics for downstream analysis

Cons:

- larger ID strings
- historical comparability requires scheme awareness

## References

- `prover/adapters/lean.py` (`_state_id`, `preview_tactic`, `commit_tactic`)
- `prover/mcts.py` (`MCTSNode.mvar_id`, `nodes_by_mvar`)
- [Goal Identity, Deduplication, and Preview/Commit](docs/concepts/goal-deduplication-and-preview-commit.md)
- [Log File Schemas](docs/contracts/logs/log-file-schemas.md)
