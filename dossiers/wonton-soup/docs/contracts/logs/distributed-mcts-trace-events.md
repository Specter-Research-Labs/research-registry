# Distributed MCTS Trace Event Dictionary

Field-level contract for distributed MCTS trace lines (`*_mcts_trace.jsonl`).

## Scope and Enablement

This dictionary applies when both are true:

- `--trace-mcts`
- `--mcts-mode distributed`

Typical files:

- `<theorem>/wild_type_mcts_trace.jsonl`
- `<theorem>/<intervention>_mcts_trace.jsonl`

## Mental Model

Distributed runner agents execute concurrently, but trace output is serialized by global iteration:

```text
                +----------------------------+
                | global iteration allocator |
                +-------------+--------------+
                              |
      +-----------------------+-----------------------+
      |                       |                       |
   agent 0                 agent 1                 agent 2
      |                       |                       |
      +---------- reserve / expand / backprop -------+
                              |
                    OrderedIterationWriter
                              |
                    *_mcts_trace.jsonl (JSONL)
```

Reservation and intervention flow per agent:

```text
select candidate node
      |
      v
blocked or delayed?
  |                |
 yes              no
  |                |
record reason=     reserve inflight
blocked|delayed    then expand
                   |
                   v
        reason=expanded|no_expansion|no_goal|dead_node|terminal_node
```

## Ordering and Stability Guarantees

- `iteration` is a global counter across all agents, not per-agent.
- Output lines are written in ascending `iteration` order.
- Agent-local scheduling step (`schedule_iteration`) is not logged.

## Event Kinds

Two top-level `event` values are emitted:

- `iteration`: primary per-iteration record
- `abort`: out-of-band abort marker emitted when progress callback aborts search

The distributed runner can emit both in the same global iteration:

- `{"event":"abort", ...}` (out-of-band marker)
- `{"event":"iteration","reason":"abort", ...}` (agent record)

## `event = "iteration"` Top-Level Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `event` | string | yes | Always `"iteration"` |
| `iteration` | int | yes | Global iteration id |
| `reason` | string | yes | Iteration outcome category |
| `agent_id` | int | yes (current impl) | Agent that produced the record |
| `selected_path` | `list[str]` | yes | Root-to-selected node mvar path |
| `node` | object | yes | Snapshot of selected node state |
| `tactics` | `list[object]` | yes | Candidate tactics in attempted order |
| `attempts` | `list[object]` | yes | Attempt results captured for this iteration |
| `expanded` | bool or null | yes | Whether any tactic expanded/committed |
| `terminal_reached` | bool | yes | Whether terminal state was reached |
| `backprop_success` | bool | yes | Whether this iteration backpropagated success |
| `tree` | object | yes | Tree-level snapshot after iteration handling |
| `block` | object | optional | Present on blocked records |
| `delay` | object | optional | Present on delayed records |
| `reroute` | `list[object]` | optional | Reroute trail before final node/decision |

Note: `trace_context` fields (currently `tier`, `budget`) are merged into each record by caller code.

## `reason` Values

| `reason` | When emitted |
|---|---|
| `expanded` | At least one tactic was committed and tree expanded (possibly terminal) |
| `no_expansion` | Candidate tactics existed but none produced novel expansion |
| `blocked` | Node selection was blocked by block schedule and not rerouted |
| `delayed` | Node selection was delayed by delay schedule and not rerouted |
| `terminal_node` | Selected node already terminal at reservation time |
| `dead_node` | Selected node already dead at reservation time |
| `no_goal` | Adapter returned no goal for selected node |
| `abort` | Progress callback requested abort (agent iteration record) |

## Nested Objects

### `node`

```json
{
  "mvar_id": "cp1:_uniq.560",
  "goal_type": "P -> Q",
  "goal_sig": "sig_abc123",
  "goal_sig_strict": "strict_def456",
  "visit_count": 12,
  "success_count": 5,
  "is_terminal": false,
  "is_dead": false,
  "depth": 3
}
```

### `tree`

```json
{
  "nodes": 41,
  "expansions": 19,
  "max_depth": 6,
  "solved": false,
  "aborted": false,
  "inflight": 2
}
```

### `attempts[]`

Serialized from `TacticAttempt`:

```json
{
  "tactic": "intro h",
  "outcome": "success",
  "child_mvar_ids": ["cp1:_uniq.561"],
  "timestamp_ms": 1730,
  "tactic_norm": "intro h",
  "goal_sig": "sig_abc123",
  "goal_sig_strict": "strict_def456",
  "goal_type": "P -> Q",
  "peg_id": null,
  "peg_kind": null,
  "block_reason": null,
  "provider_id": "deepseek"
}
```

`outcome` is one of:

- `success`
- `failure`
- `blocked`

### `block`

```json
{
  "until": 140,
  "remaining": 6,
  "duration": 20,
  "immovable": false
}
```

### `delay`

```json
{
  "until": 92,
  "remaining": 3,
  "duration": 5
}
```

### `reroute[]`

Each entry is a skip decision before final handling:

```json
{
  "mvar_id": "cp1:_uniq.574",
  "reason": "blocked",
  "block": {"until": 140, "remaining": 6, "duration": 20, "immovable": false}
}
```

or:

```json
{
  "mvar_id": "cp1:_uniq.601",
  "reason": "delayed",
  "delay": {"until": 92, "remaining": 3, "duration": 5}
}
```

## `event = "abort"` Shape

Out-of-band abort marker:

```json
{
  "event": "abort",
  "iteration": 312,
  "tier": 2,
  "budget": 200,
  "tree": {
    "nodes": 141,
    "expansions": 77,
    "max_depth": 11,
    "solved": false,
    "aborted": true,
    "inflight": 4
  }
}
```

Does not include `agent_id`, `reason`, `attempts`, or `node`.

## Worked Record Examples

### Expanded Iteration with Prior Reroutes

```json
{
  "event": "iteration",
  "iteration": 85,
  "reason": "expanded",
  "agent_id": 2,
  "tier": 1,
  "budget": 50,
  "selected_path": ["cp1:_uniq.560", "cp1:_uniq.568"],
  "node": {
    "mvar_id": "cp1:_uniq.568",
    "goal_type": "A -> B",
    "goal_sig": "sig_f08f",
    "goal_sig_strict": "strict_817f",
    "visit_count": 4,
    "success_count": 2,
    "is_terminal": false,
    "is_dead": false,
    "depth": 1
  },
  "tactics": [
    {"tactic": "intro h", "score": 0.61},
    {"tactic": "simp", "score": 0.23}
  ],
  "attempts": [
    {
      "tactic": "intro h",
      "outcome": "success",
      "child_mvar_ids": ["cp1:_uniq.602"],
      "timestamp_ms": 519,
      "tactic_norm": "intro h",
      "goal_sig": "sig_f08f",
      "goal_sig_strict": "strict_817f",
      "goal_type": "A -> B",
      "peg_id": null,
      "peg_kind": null,
      "block_reason": null,
      "provider_id": "reprover"
    }
  ],
  "expanded": true,
  "terminal_reached": false,
  "backprop_success": true,
  "tree": {
    "nodes": 33,
    "expansions": 14,
    "max_depth": 6,
    "solved": false,
    "aborted": false,
    "inflight": 3
  },
  "reroute": [
    {
      "mvar_id": "cp1:_uniq.574",
      "reason": "blocked",
      "block": {"until": 93, "remaining": 8, "duration": 20, "immovable": false}
    }
  ]
}
```

### Blocked Iteration (No Reservation)

```json
{
  "event": "iteration",
  "iteration": 86,
  "reason": "blocked",
  "agent_id": 1,
  "selected_path": ["cp1:_uniq.560", "cp1:_uniq.574"],
  "node": {
    "mvar_id": "cp1:_uniq.574",
    "goal_type": "A -> B",
    "goal_sig": "sig_f08f",
    "goal_sig_strict": "strict_817f",
    "visit_count": 3,
    "success_count": 1,
    "is_terminal": false,
    "is_dead": false,
    "depth": 1
  },
  "tactics": [],
  "attempts": [],
  "expanded": null,
  "terminal_reached": false,
  "backprop_success": false,
  "tree": {
    "nodes": 33,
    "expansions": 14,
    "max_depth": 6,
    "solved": false,
    "aborted": false,
    "inflight": 2
  },
  "block": {
    "until": 93,
    "remaining": 7,
    "duration": 20,
    "immovable": false
  }
}
```

## Quick Query Patterns

Top `reason` frequencies:

```bash
jq -r 'select(.event=="iteration") | .reason' theorem/wild_type_mcts_trace.jsonl | sort | uniq -c
```

Average inflight by reason:

```bash
jq -s '
  map(select(.event=="iteration" and .tree.inflight != null))
  | group_by(.reason)
  | map({reason: .[0].reason, avg_inflight: ((map(.tree.inflight)|add)/length)})
' theorem/wild_type_mcts_trace.jsonl
```

## Related Docs

- [Distributed MCTS Semantics](docs/concepts/distributed-mcts.md)
- [ADR: Distributed (Cell-View) MCTS Runner](docs/decisions/adr-distributed-mcts.md)
- [Log Schemas: Per-Theorem Artifacts](docs/contracts/logs/log-schemas-theorem-level.md)
- [UCB1 and Blind-Uniform Search in Wonton-Soup](docs/concepts/ucb1.md)
