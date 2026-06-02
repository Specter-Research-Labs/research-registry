# Partial Proof Terms, Assembly Tracking, and Sequential Replay

In multi-step Lean proofs, the kernel assembles a term incrementally. This is
the `wonton-soup` proof-term tracking model and the no-branching replay path
for final proof-term reconstruction.

## Problem 1: Partial Term Visibility During Search

Consider proving `True ∧ True`:

```lean
theorem example : True ∧ True := by
  constructor
  · trivial
  · trivial
```

After `constructor`, Lean has a partial term with holes:

```
And.intro ?mvar_1 ?mvar_2
```

After solving one branch:

```
And.intro True.intro ?mvar_2
```

After solving both:

```
And.intro True.intro True.intro
```

If we only serialize the final term, we lose when and how subterms were committed. We track
partial terms per tactic so that divergence points are inspectable.

## Problem 2: `sorry` Contamination from Branch Partitioning

`leantree`'s branching tactic API partitions independent goals and masks non-target goals with
`sorry`. That is acceptable for search bookkeeping, but unsafe for final proof-term extraction.

When one branch is solved with another branch masked, the produced term still contains `sorry`.
The Lean REPL proof-term extraction path rejects such terms.

## Why Track Assembly + Replay Sequentially

- Assembly trace explains *when* proof structures diverge.
- Partial terms expose intermediate commitments and open holes.
- Sequential replay produces one proof state with all goals visible and no masking artifacts.

## Lean-Side Extraction Model

The pinned Specter `leantree` fork exposes partial-term extraction via metavariable
assignment expansion.

Core behavior:

- inline assigned metavariables recursively
- keep unassigned metavariables as holes
- serialize both the expression DAG and open-hole metadata

The returned payload includes:

- `proofTerm`: partial or complete `ExprDAG`
- `openMvars`: remaining holes (`mvarId`, `type`)
- `isComplete`: whether all holes are closed

## Python Data Model

`prover/expr.py`:

- `MvarHole`
- `PartialProofTerm`

`prover/assembly.py`:

- `AssemblyStep`
- `ProofAssemblyTrace`

`ProofAssemblyTrace` is the canonical step-by-step audit artifact for proof assembly.

## Adapter Integration (Preview/Commit)

`prover/adapters/lean.py` records assembly information on `commit_tactic` using preview data
captured by `preview_tactic`.

At commit time the adapter records:

- target goal (`mvar_id`)
- partial term before/after
- goals opened/closed
- terminal proof term when complete

This produces `*_assembly.json.gz` for each variant.

## Sequential No-Branching Replay API

To reconstruct a final proof term without branch masking, replay uses the no-branching API in
`leantree/leantree/repl_adapter/interaction.py`:

- `apply_tactic_no_branching_async(...)`
- `try_apply_tactic_no_branching_async(...)`

Differences from branching API:

- returns a single branch with all resulting goals visible
- does not partition independent goals into masked branches
- preserves one coherent proof state for final extraction

## Reconstruction Flow

`prover/adapters/lean.py` (`reconstruct_proof_term`):

1. Create a fresh theorem state.
2. Replay `assembly_trace.steps` with no-branching tactic application.
3. Abort if any replay step fails.
4. Extract the final proof term once the branch is solved.

This replay path is used as the fallback when direct in-run extraction cannot return a usable term.

## Output Artifacts

Per theorem variant (under `logs/corpus-.../<theorem>/`):

- `*_assembly.json.gz`: assembly trace with partial terms per step
- `*_proof_term.json.gz`: final term only

## Relation to Goal Identity

Assembly events are keyed by checkpoint-scoped goal IDs (`cp<checkpoint>:<lean_mvar_id>`).
Conceptual background and cycle-breaking behavior are documented in
[Goal Identity, Deduplication, and Preview/Commit](docs/concepts/goal-deduplication-and-preview-commit.md).

## Implementation Files

| File | Purpose |
|------|---------|
| `leantree/lean-repl/REPL/JSON.lean` | JSON structures for mvars and partial proof terms |
| `leantree/lean-repl/REPL/Main.lean` | partial proof-term extraction |
| `leantree/leantree/repl_adapter/interaction.py` | no-branching tactic replay API |
| `prover/expr.py` | `MvarHole`, `PartialProofTerm` |
| `prover/assembly.py` | `AssemblyStep`, `ProofAssemblyTrace` |
| `prover/adapters/lean.py` | preview/commit integration and sequential reconstruction |
