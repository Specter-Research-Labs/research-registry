# Goal Identity, Deduplication, and Preview/Commit

Canonical reference for:

- checkpoint-scoped goal identity in logs and MCTS
- semantic cycle-breaking via goal signatures
- preview/commit tactic application in the Lean adapter

## Goal Identity in This Repo

Lean metavariable IDs (`mvar_id`) are stable only within a given proof state. With checkpoint
rollback, raw IDs can be reused.

To prevent collisions, wonton-soup logs and tree nodes use checkpoint-scoped IDs:

```
cp<checkpoint_id>:<lean_mvar_id>
```

Example:

```
cp12:_uniq.100099.72
```

Implications:

- `MCTSTree.nodes_by_mvar` keys by checkpoint-scoped goal ID.
- adapter state maps (`LeanAdapter.states`) key by checkpoint-scoped goal ID.
- history/graph/assembly artifacts record checkpoint-scoped IDs in `mvar_id` fields.

## Why Identity Alone Is Not Enough

Checkpoint-scoped IDs prevent collisions, but they do not merge semantically equivalent goals.
Equivalent goals reached by different rewrites still produce distinct IDs.

That caused an observed failure mode: repeated rewrites cycling equivalent goals indefinitely
(e.g., `mul_add_distrib` repeatedly rewriting commutative forms).

## Goal Signatures for Cycle Breaking

Search uses an AST-based coarse goal signature for branch-local cycle breaking.

Input surface:

- goal type AST
- hypothesis ASTs

Normalization intentionally removes distinctions that are noisy for cycle detection:

- binder/fvar/mvar identity
- hypothesis ordering
- commutative surface forms for selected connectives

Tradeoff:

- prevents infinite equivalent-goal cycles
- may occasionally over-merge distinct states

A strict signature variant is also recorded for analysis payloads (`goal_sig_strict`) to preserve
full structural distinctions for diagnostics.

## Preview/Commit Tactic Application

The adapter API (`prover/adapters/lean.py`) separates speculative execution from state mutation.

- `preview_tactic(mvar_id, tactic) -> TacticPreview | None`
  - rolls back to the parent checkpoint
  - applies tactic
  - returns child goals/terms/checkpoint info without mutating adapter maps
- `commit_tactic(preview) -> list[str]`
  - mutates adapter bookkeeping (state map, partial term, assembly trace)
  - creates child states and returns child checkpoint-scoped IDs

This split allows MCTS to test multiple tactics before committing to one.

## MCTS Expansion Contract

At expansion time (`prover/mcts.py`), tactics are evaluated in order:

1. preview tactic
2. compute goal signatures for child goals
3. discard children whose signatures already appear on the current root-to-node path or
   earlier siblings from the same preview
4. commit only the first tactic that yields novel children
5. mark node dead only when all tactics are exhausted

This avoids the earlier failure where the first duplicate-producing tactic prematurely killed a
node, while also avoiding global pruning based on a deliberately lossy equivalence class.

## Dead-Node Cascading

When no tactic can yield novel children on the current branch:

1. node is marked dead
2. dead children are skipped by selection
3. parents become dead when all descendants are dead
4. search stops when root is dead

This ensures iteration budget is not spent on branch-local cycles. Coarse signatures are not used
to prove that the same semantic shape is globally dead across unrelated branches.

## Behavioral Impact

- Search distribution: tree semantics preserved (no state-graph merge).
- Stability: collisions from rollback reuse are eliminated.
- Metrics/logging: node counts may shift upward because reused raw IDs no longer collapse.
- Comparability: goal-ID scheme is explicit (`checkpoint`) in run metadata.

## Why Not Full State-Graph Merging?

Alternatives considered:

- path-specific opaque IDs only
- full state-graph merge by goal signature
- hybrid shared statistics by signature

Current design keeps tree semantics while adding bounded semantic deduplication for cycle safety on
the active branch. This minimizes search-policy drift while fixing concrete failure modes without
making the search incomplete through global coarse-signature pruning.

## Relation to Proof Artifacts

Goal identity and dedup semantics directly influence:

- `*_history.json` selected paths and attempts
- `*_graph.json` node identity
- `*_assembly.json.gz` step target IDs
- GED and trajectory-derived analyses that consume those artifacts

## Implementation Surface

| File | Responsibility |
|------|----------------|
| `prover/adapters/lean.py` | checkpoint-scoped state IDs, preview/commit, reconstruction |
| `prover/mcts.py` | signature-aware expansion, dead-node handling, tree bookkeeping |
| `prover/goal_signature.py` | goal signature computation schemes |
| `prover/goal_cache.py` | signature mapping and per-signature outcome aggregation |
| [Log File Schemas](docs/contracts/logs/log-file-schemas.md) | artifact fields affected by goal-ID scheme |
| [ADR: Checkpoint-Scoped Goal IDs](docs/decisions/adr-checkpoint-goal-ids.md) | design decision record |
