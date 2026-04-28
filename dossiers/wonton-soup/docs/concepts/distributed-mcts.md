# Distributed MCTS

Active when `--mcts-mode distributed`. Centralized semantics remain in
[UCB1 and Blind-Uniform Search](ucb1.md).

Distributed mode is not a second proof-space model. It is the collective-control layer over the same
proof-space morphology studied in centralized runs. Centralized MCTS establishes the structural
landscape; distributed mode tests how coordination, contention, and scheduling change access to that
landscape.

## The Tree Is an AND/OR Search Over Proof Obligations

Each node in the MCTS tree is a single proof obligation (a Lean metavariable with a goal type). Each
edge is a tactic application. The tree has AND/OR semantics:

- **OR**: at any node, the search needs *any one* tactic to work.
- **AND**: if that tactic splits the goal into N subgoals, *all* N children must be solved.

```
  node: a /\ b                         (OR: pick any tactic)
    |
    +-- tactic "constructor"
    |     +-- child: a                  (AND: both must be solved)
    |     +-- child: b
    |
    +-- tactic "simp"
          +-- (closed, no children)     terminal success
```

`MCTSNode.children` is a `dict[str, list[MCTSNode]]` keyed by tactic string. An empty list means the
tactic closed the goal entirely. This encoding makes the AND/OR structure explicit in the data: each
key is an OR-branch, each value list is the AND-set.

`MCTSTree.is_solved()` walks this structure with iterative DFS: a node is solved if it is terminal,
or if at least one tactic edge has all its children solved. `extract_winning_tactics()` follows the
solved path to produce the final tactic sequence.

## Checkpoint-Based Branching Over a Sequential REPL

The Lean REPL is sequential -- one current proof state at a time. Tree search requires branching. The
adapter resolves this with checkpoint rollback.

Each committed tactic creates a `LeanEnvironmentCheckpoint`. When the search wants to try a different
tactic at the same node, the adapter rolls back to the parent checkpoint, restoring the REPL to the
pre-tactic state.

```
  Checkpoint 1             goal: a + b = b + a
       |
       +-- apply "ring"  --> Checkpoint 2  (closed, terminal)
       |
       +-- (rollback to CP1)
       |
       +-- apply "simp"  --> Checkpoint 3  (new subgoals)
```

Tactic evaluation is two-phase:

1. `adapter.preview_tactic(mvar_id, tactic)` rolls back, applies the tactic, returns a
   `TacticPreview` with child goals and a new checkpoint. Does not mutate adapter bookkeeping.
2. `adapter.commit_tactic(preview)` writes the state change into the adapter's maps.

This split lets the search test multiple tactics before committing. Preview is speculative; commit is
permanent. See [Goal Identity, Deduplication, and Preview/Commit](goal-deduplication-and-preview-commit.md)
for the identity and cycle-breaking contracts around this mechanism.

Node identity ties a goal to a specific checkpoint: `mvar_id = "cp{checkpoint_id}:{lean_mvar_id}"`.
This prevents collisions when the same raw Lean mvar ID appears at different points in the search.

## Shared State and Concurrency Model

Multiple async agents (typically 4--8) share one Python process, one `MCTSTree`, and one
`LeanAdapter`:

```
  +---------- shared state ----------+
  |  MCTSTree       tree_lock        |
  |  LeanAdapter    expansion_lock   |
  |  TacticProvider  inflight set    |
  |                  stop_event      |
  +---------+----+----+----+---------+
            |    |    |    |
         agent0  1    2    3
```

Two locks partition the work:

- `tree_lock` guards tree reads and writes (selection, backpropagation, node creation).
- `expansion_lock` serializes tactic evaluation against the single Lean REPL.

There is only one REPL subprocess. Agents do not evaluate tactics concurrently. The throughput gain
comes from overlapping the fast phases (selection, backpropagation, tactic suggestion) of one agent
with the slow phase (Lean tactic evaluation) of another.

## Agent Iteration Lifecycle

Each agent runs a loop: **reserve, expand, backpropagate, release**. One pass through this loop is
one iteration.

### 1. Reserve (under `tree_lock`)

The agent walks from root to a leaf using UCB-like scoring. At each level, it picks the
highest-scoring live child that is not already in the `inflight` set. If all live children at some
level are inflight, the agent backs off with a short sleep and retries.

On success, the selected node is added to `inflight` and the entire root-to-node path gets its
inflight counts incremented (used for virtual loss, see below).

### 2. Expand (under `expansion_lock`)

The agent retrieves the goal state from the adapter, asks the tactic provider for scored candidates,
and tries them in descending probability order:

- **Tactic fails**: skip, try the next candidate.
- **Tactic succeeds with zero children**: goal is closed. Commit, mark node terminal, break.
- **Tactic succeeds with N children**: check for cycles (see below), commit, create child nodes in
  the tree, break.

The agent commits the first successful tactic and stops. If all tactics fail, the node is marked
dead.

### 3. Backpropagate (under `tree_lock`)

Walk from the expanded node to root, incrementing `visit_count` at every ancestor.
If the expansion succeeded, also increment `success_count`.

After backpropagation, check `tree.is_solved()`. If the root is solved, set `stop_event` and all
agents exit their loops.

### 4. Release

Remove the node from `inflight`, decrement inflight counts along the path. Other agents can now
select this node or its neighbors without virtual-loss penalty.

### Timeline

```
Agent 0: [reserve root] [--- expand: ring(fail), simp(ok) ---] [backprop] [reserve child]...
Agent 1:   [reserve: root inflight, retry] [reserve root] [--- expand: omega ---] [backprop]...
Agent 2:      [reserve child_1] [--- expand ---] [backprop]...
Agent 3:         [reserve child_2] [--- expand ---]...
                                |
               expansion_lock serializes all Lean calls
```

## Virtual Loss Prevents Redundant Selection

Without virtual loss, all agents would select the same most-promising node. Virtual loss applies a
temporary pessimistic bias to nodes currently being worked on:

```
visits_eff  = visit_count + inflight_count * virtual_loss
success_eff = success_count - inflight_count * virtual_loss
```

When `inflight_count >= 1` and `virtual_loss > 0`, the node's UCB score drops sharply. Other agents
prefer different nodes.

The penalty applies to the **entire selected path**, not just the leaf. If agent 0 is working deep
in the left subtree, agent 1 is nudged toward the right subtree because every ancestor on agent 0's
path also has elevated inflight counts.

When agent 0 finishes and releases, inflight counts drop back and scores return to their true values.

Effective parent visits for the exploration term:

```
parent_visit_eff = parent.visit_count + inflight(parent) * virtual_loss
```

Optional additive score modifiers:

- `depth_bias * node.depth`
- `path_bias` when node lies on the agent's previous selected path

Unvisited and non-inflight nodes keep first-touch priority (`+inf`).

When `virtual_loss = 0`, agents can collide on the same node. The `expansion_lock` serializes them,
and the second agent skips tactics already in `node.children`.

## Cycle Prevention via Goal Signatures

A tactic can transform a goal into a semantically equivalent form (e.g. `rw [add_comm]` turning
`a + b` into `b + a`, which a later rewrite could reverse). Without cycle detection, the search
enters infinite loops.

Before expanding a node, the search collects goal signatures of all ancestors from root to the
current node. Any child whose signature matches an ancestor is skipped.

Goal signatures are 12-hex hashes of the canonicalized goal AST, with commutative normalization
applied to selected connectives. A strict variant (`goal_sig_strict`) without commutative
normalization is recorded separately for analysis.

See [Goal Identity, Deduplication, and Preview/Commit](goal-deduplication-and-preview-commit.md)
for signature computation details and the dead-node cascading contract.

## Intervention Schedules

Blocking, delay, and reroute schedules are research tools for studying how the search degrades and
recovers under damage. They do not affect Lean tactic correctness.

Blocking (`BlockSchedule`):

- probabilistic first-touch blocking by node
- finite duration and permanent blocks (`duration < 0`)
- optional immovable subset and unfreeze controls

Delay (`DelaySchedule`):

- probabilistically delays selected nodes for fixed windows

Reroute:

- when blocked or delayed, selection can retry alternate nodes up to `max_attempts`
- reroute trail is recorded in trace payloads

## CLI Contract

| Flag(s) | Requirement | Validation |
|---|---|---|
| `--mcts-agents`, `--mcts-inflight` | required in distributed mode | both must be provided |
| distributed options in centralized mode | forbidden | parser error |
| `--mcts-block-fraction` | enables block schedule | must be in `(0,1)` |
| `--mcts-block-duration` with block fraction | required | must be non-zero |
| `--mcts-block-seed` with block fraction | required | must be provided |
| `--mcts-block-immovable-fraction` | optional with block schedule | must be in `[0,1]`; requires positive duration |
| `--mcts-unfreeze-after` | optional with block schedule | must be `>= 1` |
| `--mcts-unfreeze-prob` | optional with block schedule | must be in `(0,1]` |
| `--mcts-reroute-blocked` + `--mcts-reroute-max` | paired | max required when reroute enabled; max `>= 1` |
| delay triplet (`--mcts-delay-prob`, `--mcts-delay-duration`, `--mcts-delay-seed`) | all-or-none | prob in `(0,1)`, duration `>= 1`, seed `>= 0` |
| `--mcts-virtual-loss` | optional | `>= 0` |
| `--mcts-depth-bias`, `--mcts-path-bias` | optional | each `>= 0` |
| `--mcts-history-cache` | optional | boolean switch |

Cross-mode constraints:

- `--basin-blind` requires `--basin-seeds`.
- `--basin-blind` currently requires centralized mode.
- Multi-provider runs do not support `--basin-seeds`.

## Provider and Ranker Compatibility

Distributed mode uses the same provider stack as centralized mode. Provider output is
probability-sorted before ranker application. The ranker is reorder-only and must preserve count and
tactic multiset. Violations fail fast.

## Provenance

Run metadata captures distributed settings (`distributed_mcts`) and policy choices. Trace payloads
capture per-iteration distributed context: `agent_id`, inflight state, and block/delay/reroute
snapshots. These fields allow post-hoc reconstruction without relying on CLI history.

## Implementation Surface

| File | Responsibility |
|------|----------------|
| `experiments/distributed_mcts/core.py` | `distributed_mcts_search`, agent loop, virtual loss, intervention schedules |
| `prover/mcts.py` | `MCTSNode`, `MCTSTree`, AND/OR solving, centralized baseline |
| `prover/adapters/lean.py` | `LeanAdapter`, checkpoint rollback, preview/commit |
| `prover/goal_signature.py` | goal signature hashing with commutative normalization |
| `prover/providers/base.py` | `TacticProvider`, `GoalAwareTacticProvider` |
| `orchestrator/lean.py` | `run_corpus`, `run_theorem`, distributed config wiring |

## Related Docs

- [ADR: Distributed (Cell-View) MCTS Runner](../decisions/adr-distributed-mcts.md)
- [Distributed MCTS Trace Event Dictionary](../contracts/logs/distributed-mcts-trace-events.md)
- [UCB1 and Blind-Uniform Search](ucb1.md)
- [Goal Identity, Deduplication, and Preview/Commit](goal-deduplication-and-preview-commit.md)
