# General Algebraic Tactic Calculus Spec

Companion to
[README.md](../README.md), [goals.md](../goals.md), and [research.md](../research.md).
Fixes the target of the stronger claim: a tactic representation that is executable,
effectful, law-bearing, round-trippable, and richer than strings.

It is not the current `wonton-soup` contract.

## Target

The calculus should support:

- executable interpretation into Lean
- explicit effects, continuation shape, and goal coupling
- composition and laws where side conditions justify them
- round-trippable serialization for replay and learning
- projection back into current step-level and graph-level repo artifacts

## Boundary

- this addendum owns the research question about richer tactic representation
- `wonton-soup` owns `TacticActionIR` and `ProofGraphIR`

Any future calculus must satisfy two obligations:

1. interpret into Lean
2. forget into current observational surfaces

If either fails, the calculus is not useful in this repo.

## Commitments

### Open core

Lean tactics are extensible. The calculus should therefore have:

- a small semantic core
- derived tactic families compiled into the core
- an explicit `foreign` node for extensions not yet reduced to the core

### Effectful semantics

The base semantic object is not a pure function `state -> state`. It must account for:

- elaboration
- unification
- typeclass search
- environment access
- backtracking
- normalization
- recursion and fuel

The right substrate is an effectful core language with handlers into Lean `MetaM` / `TermElabM` /
`TacticM`.

### Continuation-carrying steps

The semantic unit is not just "before/after goals". A step must return:

- changed state
- child obligations
- coupling structure
- a residual builder that closes the parent once child witnesses are supplied

This is where the research note's objection to naive bidirectionality lands.

### Coupled proof states

Subgoals are not assumed independent. The calculus must represent:

- shared metavariables
- dependency edges between obligations
- independence only when justified by the coupling object

### Proof terms are first-class

Partial proof terms and final witnesses are semantic data, not logging extras.

### Provenance is semantic

Toolchain, imports, options, trusted extensions, and replay-relevant settings are part of meaning.

### Failure is first-class

Failure, backtracking, and replay incompatibility must be explicit outcomes. No hidden fallback to
raw scripts or best-effort replay.

## Semantic Objects

### Proof state

```text
ProofState =
  < provenance,
    environment,
    active_obligations,
    focus,
    metavar_graph,
    constraint_store,
    partial_term,
    options >
```

- `provenance`: toolchain, imports, trusted extensions, elaboration and reduction settings
- `environment`: visible theorem/constant environment
- `active_obligations`: open proof obligations
- `focus`: currently selected obligation or obligation family
- `metavar_graph`: dependency structure induced by metavariables
- `constraint_store`: unresolved constraints relevant to elaboration
- `partial_term`: assembled witness with holes
- `options`: semantically relevant runtime settings

### Obligation

```text
Obligation =
  < obligation_id,
    local_context,
    target_type,
    local_assignments,
    visibility,
    provenance_ref >
```

### Coupling

```text
Coupling =
  < child_obligations,
    shared_metavars,
    dependency_edges,
    coupling_kind >
```

- `coupling_kind` may summarize to `none`, `independent`, `coupled`, or `unknown`
- the summary must project into current `TacticActionIR`
- the full object must retain richer dependency structure

### Step pack

```text
StepPack =
  < state_delta,
    child_interface,
    coupling,
    residual_builder,
    certificates >
```

```text
residual_builder : ChildWitnessFamily -> TacEff ParentWitness
```

`residual_builder` is not an inverse. It is the continuation that fills the parent hole after child
witnesses arrive.

## Core Language

### Layer 1: semantic core

```text
t, u ::=
    pure v
  | fail e
  | bind x <- t ; u
  | choice policy [t1, ..., tn]
  | scoped scope t
  | focus selector t
  | handle h t
  | fix f . t
  | op(args)
  | foreign symbol payload contract
```

Laws live here.

### Layer 2: derived tactic vocabulary

Named tactic families compile into the core. The initial fragment should cover at least:

- `intro`
- `apply`
- `exact`
- `cases`
- `simp`
- `rewrite`

These are derived programs, not the semantic foundation.

## Effect Signature

At minimum the core should expose:

### Inspection

- `ViewActiveObligations`
- `ReadObligation obligation_id`
- `ReadLocalContext obligation_id`
- `ReadMetavarGraph`
- `ReadConstraintStore`
- `ReadEnvironment query`

### Construction

- `FreshMetavar type`
- `SpawnObligations interface`
- `AssignMetavar hole witness`
- `RegisterResidualBuilder builder`

### Elaboration and kernel-facing effects

- `Elaborate syntax expected_type`
- `Normalize expr mode`
- `Unify lhs rhs`
- `Rewrite target rule location`
- `SynthesizeInstance class_goal`
- `CheckWitness witness obligation`

### Search and control

- `Checkpoint`
- `Rollback checkpoint_id`
- `Backtrack reason`
- `Cut label`
- `ConsumeFuel amount`

### Provenance

- `ReadProvenance`
- `RequireReplayCompatibility expected_provenance`

## Semantics

### One-step semantics

```text
[[step]] : (s, g) -> TacEff StepPack
```

The return value must expose:

- state change
- child interface
- coupling
- residual builder
- replay certificates

### Program semantics

Use a free-effect or interaction-tree style semantics for the core language, then handle it into
Lean. Denotational and executable stories should share the same effect signature.

### Typing

```text
Delta ; I_in |- t : I_out ! Phi
```

This should guarantee at least:

- no out-of-scope hole or hypothesis references
- no residual builder expecting witnesses not spawned by the step
- no obligation-id collisions
- no dropped replay-critical provenance fields
- no branch law without justified coupling side conditions

### Observational equality

```text
t ~= u
```

Relative to a handler and compatible provenance, this should mean:

- same success or failure class
- equivalent output interface and coupling
- equivalent parent witness behavior once child witnesses are supplied
- same replay obligations

## Laws Worth Claiming

- `bind` associative up to observational equality
- `pure` left and right unit for `bind`
- `fail` left zero for sequencing
- `choice` laws only relative to explicit control policy
- focus/scope laws only when visibility and interface constraints are preserved
- branch permutation only under explicit coupling-disconnected and residual-equivariant side
  conditions
- fixpoint laws only under explicit fuel or termination discipline

## Laws Not to Claim Early

- ordinary lens laws for arbitrary tactics
- invertibility of tactic steps in general
- independence of child goals merely from branch count
- semantic equality from tactic-string equality
- closed syntax for all Lean tactics

## Open Extension Mechanism

```text
foreign symbol payload contract
```

`contract` must declare:

- effect footprint
- input/output interface boundary
- replay codec
- projection behavior
- whether a refinement into the core calculus is known

Two acceptable modes:

1. black-box execution contract
2. proven refinement into the core

Hidden raw-string fallback is not acceptable.

## Projection Obligations

### To `TacticActionIR`

Each successful `StepPack` must forget to at least:

- branch arity
- continuation kind
- coupling summary
- dependency summary
- effect flags
- proof-step count

### To assembly traces

Each successful `StepPack` must also forget to:

- parent and child obligation ids
- partial term before and after
- completed proof term when available

### To graph-level analysis

The calculus should admit a graph projection compatible with
[ProofGraphIR](../../../dossiers/wonton-soup/docs/concepts/proof-graph-ir.md),
but graph comparison is downstream and should not drive the semantics.

## Serialization

Round-trippable serialization requires:

- typed AST encoding
- schema versioning
- explicit provenance payload
- stable obligation and residual-builder ids
- explicit `foreign` nodes with declared contracts
- no hidden dependence on pretty-printed Lean state

Round-trip means:

1. parse serialized term
2. recover the same typed term and provenance witness
3. replay under Lean or reject with a precise incompatibility error

Silent repair is not round-trip.

## Theorem Program

Detailed judgments, side conditions, and the first lemma ladder are in
[theorem-agenda.md](theorem-agenda.md).

Minimum theorem set:

1. handler soundness
2. serialization round-trip
3. projection soundness
4. conditional branch independence
5. conservative extension

Ambitious theorem set:

1. adequacy to Lean execution for a core fragment
2. completeness of trace extraction for that fragment up to observational equality
3. optic or dependent-lens interpretation for the fragment where the laws actually hold
4. polynomial semantics for the provably independent fragment

## Evaluation Program

The calculus should be judged along four axes:

### Semantic fidelity

- replay validity against Lean
- witness equality or conservative equivalence
- child-interface fidelity
- coupling fidelity relative to the metavar graph

### Compositional adequacy

- laws hold where side conditions say they should
- laws fail or are unclaimable where side conditions do not hold

### Learning utility

- constrained-decoding validity
- sample efficiency versus string tactics
- generalization to held-out tactic compositions
- recoverability of structure from traces

### Search utility

- proof success under fixed budgets
- latency and branching efficiency
- compatibility with proof-progress signals
- robustness under provenance and replay stress

## State of the Art Anchors

- [Nazrin (arXiv:2602.18767, v2 March 2, 2026)](https://arxiv.org/abs/2602.18767):
  finite atomic basis plus `ExprGraph`
- [LeanTree (AI for Math Workshop 2025)](https://ufal.mff.cuni.cz/biblio/attachments/2025-kripner-p2251125924673771681.pdf):
  factorized states with explicit metavariable coupling
- [LeanDojo-v2 (2025)](https://leandojo.org/leandojo.html):
  current broad Lean 4 tracing and search surface
- [LeanProgress (arXiv:2502.17925, v3 January 18, 2026)](https://arxiv.org/abs/2502.17925):
  proof progress as a separate predictive signal
- [DeepSeek-Prover-V2 (arXiv:2504.21801, v2 July 18, 2025)](https://arxiv.org/abs/2504.21801)
  and [Goedel-Prover-V2 (arXiv:2508.03613, August 5, 2025)](https://arxiv.org/abs/2508.03613):
  decomposition and self-correction on the critical path

The pressure these systems put on the calculus is clear:

- atomic or near-atomic actions
- factorized but coupled states
- decomposition and repair
- progress-sensitive control
- provenance-sensitive replay

## Thesis

The most defensible target now is:

- a calculus of effectful proof-state interaction
- one-step semantics returning child obligations plus a residual builder
- explicit coupling in the semantic object
- laws indexed by side conditions, not claimed globally
- open extension points with explicit contracts

Anything weaker loses the point of the addendum. Anything stronger is not yet earned.
