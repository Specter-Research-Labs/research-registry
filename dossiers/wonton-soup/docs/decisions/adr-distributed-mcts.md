# ADR: Distributed (Cell-View) MCTS Runner

## Context

We need a distributed-control search mode (cell-view inspired) without destabilizing the canonical centralized MCTS path.

Research requirements:

- multiple local controllers (agents) over one shared tree
- scheduling interventions (block, delay, reroute)
- reproducible traces and run metadata
- no hidden fallback to centralized behavior

## Decision

Implement distributed MCTS as a separate runner (`experiments/distributed_mcts/core.py`) selected by `--mcts-mode distributed`.

Keep core centralized engine (`prover/mcts.py`) unchanged.

## Rationale

This isolates experimental control logic from the production baseline path. Distributed scheduling can evolve without mutating centralized semantics, centralized trace contracts, or core tree/node structures.

## Options Considered

1. Extend centralized `prover/mcts.py` with distributed branches.
2. Add a separate distributed runner and keep centralized path unchanged (chosen).
3. Build full concurrent adapter execution across agents.

Option 1 creates one mixed control path that is harder to reason about and test for regression.

Option 3 requires concurrency guarantees in Lean adapter state handling that we do not currently claim.

## Implementation Resources Used

Primary code surfaces used to realize this decision:

- distributed runner: `dossiers/wonton-soup/experiments/distributed_mcts/core.py`
- mode wiring and CLI validation: `dossiers/wonton-soup/orchestrator/lean.py`
- centralized baseline kept stable: `dossiers/wonton-soup/prover/mcts.py`

Primary documentation surfaces:

- distributed semantics: [Distributed MCTS Semantics](docs/concepts/distributed-mcts.md)
- distributed trace field dictionary: [Distributed MCTS Trace Event Dictionary](docs/contracts/logs/distributed-mcts-trace-events.md)

## Non-Goals

- no mutation of centralized `prover/mcts.py` semantics
- no concurrent Lean adapter execution
- no hidden fallback between modes

## Consequences

- Distributed iteration order diverges from centralized order by design.
- Intervention effects are expressed through scheduling and reservation, not core tree schema changes.
- The repo keeps one stable baseline path plus one isolated experimental path.

## References

- [Distributed MCTS Semantics](docs/concepts/distributed-mcts.md)
- `dossiers/wonton-soup/experiments/distributed_mcts/core.py`
- `dossiers/wonton-soup/orchestrator/lean.py`
- `dossiers/wonton-soup/prover/mcts.py`
- [Distributed MCTS Trace Event Dictionary](docs/contracts/logs/distributed-mcts-trace-events.md)
