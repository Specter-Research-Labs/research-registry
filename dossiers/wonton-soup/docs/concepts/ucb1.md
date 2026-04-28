# UCB1 and Blind-Uniform Search in Wonton-Soup

Canonical semantics for centralized MCTS search policy and its basin-mode blind baselines.

## Policy Surface

Centralized `mcts_search` (`prover/mcts.py`) supports:

- `SearchPolicy.UCB1` (default)
- `SearchPolicy.BLIND_UNIFORM`

Policy affects two different decisions per iteration:

1. Which node to expand.
2. In what order to try suggested tactics at that node.

## UCB1 Definition and Implementation

For child node `i`:

```
score_i = exploitation_i + c * sqrt(ln(N_parent) / n_i)
```

Where:

- `n_i` is child visit count.
- `N_parent` is parent visit count.
- `c` is exploration constant (`sqrt(2)` default).

`MCTSNode.ucb1(...)` returns `+inf` for `n_i == 0`, forcing first-touch exploration.

Centralized selection path:

1. `MCTSTree.select(...)` walks down from root.
2. At each level, `best_child_by_ucb1(...)` chooses the highest-score live child.
3. If all candidates are dead/terminal, node is marked dead and backpropagates failure.

## Exploitation Term and Backprop Strategy

`backprop_strategy` changes exploitation:

- `UNIFORM`: `success_count / visit_count`
- `AND_MIN`: `and_min_value()` over tactic fanout (best tactic by worst subgoal)

`AND_MIN` is deliberately conservative on multi-subgoal expansions: one hard residual branch can keep tactic value low even when average outcomes look good.

## Tie-Breaking and Determinism

If several children have identical UCB score:

- with `tie_breaker`: custom chooser (must return a valid candidate)
- else with RNG: `rng.choice(candidates)`
- else: first candidate in iteration order

Determinism therefore depends on both seed wiring and whether tie-break hooks are active.

## Tactic Ordering Under UCB1

After a node is selected, centralized MCTS:

1. asks provider for `(tactic, prob)` pairs,
2. sorts descending by provider probability,
3. optionally applies `tactic_ranker` reordering.

Ranker contract is strict:

- same number of entries,
- same multiset of `(tactic, prob)` pairs,
- order may change only.

Violations raise `ValueError`.

## BLIND_UNIFORM Semantics

`SearchPolicy.BLIND_UNIFORM` is not just "low-c". It changes both stages:

1. Node selection uses `select_leaf_uniform(rng)`:
   - collect all non-terminal, non-dead leaves,
   - sample one uniformly.
2. Tactic order ignores provider probabilities:
   - keep provider tactic set,
   - shuffle tactic order with RNG.

So blind-uniform still depends on provider candidate generation, but not on provider probability ranking or UCB exploitation/exploration.

RNG is required for blind mode; missing RNG raises `ValueError`.

## Basin-Mode Relation (`--basin-blind`)

`--basin-blind` runs two policies per seed in basin analysis:

- agent policy: `UCB1`
- blind baseline: `BLIND_UNIFORM`

This is used to compute paper `K` summaries. Current guardrails:

- `--basin-blind` requires `--basin-seeds`.
- `--basin-blind` currently requires `--mcts-mode centralized`.

Distributed runs do not expose a blind-uniform policy toggle today.

## Interaction with Provider Filtering (`--allow-easy`)

By default, easy tactics are blocked via `FilteredTacticProvider`. Both UCB1 and blind-uniform operate on the filtered candidate set.

- Without `--allow-easy`: blocked tactics never enter policy ranking/shuffling.
- With `--allow-easy`: those tactics can dominate early if provider confidence or random order favors them.

When comparing policies, keep `--allow-easy` fixed across runs.

## Distributed Runner Note

Distributed MCTS (`experiments/distributed_mcts/core.py`) always uses UCB-style scoring for available-node reservation plus optional path/depth/virtual-loss adjustments. It does not implement a separate blind-uniform search policy.

## Worked Micro-Examples

Example A (UCB1):

- Parent visits `N=100`
- Child A: `n=50`, exploitation `0.80`
- Child B: `n=5`, exploitation `0.50`
- With `c=sqrt(2)`, B can still win early due to large exploration bonus.
- As `n_B` grows, B's exploration term shrinks and A usually dominates.

Example B (blind-uniform):

- Tree has 20 expandable leaves, 2 are promising under UCB.
- Blind-uniform samples each leaf with probability `1/20`, regardless of value.
- At the chosen leaf, tactic order is randomized, so high-prob provider suggestions lose priority.

## Reporting Checklist

Include all of the following in any claim about search quality:

- `search_policy` (`ucb1` or `blind_uniform`)
- `c`
- `backprop_strategy`
- tie-break and RNG/seed policy
- provider and ranker config
- `allow_easy` setting
- budget tiers and theorem set
