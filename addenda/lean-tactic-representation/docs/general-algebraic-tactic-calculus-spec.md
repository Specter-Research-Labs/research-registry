# Algebraic Tactic Calculus

Research target for a tactic representation richer than strings.

This is not the current `wonton-soup` contract. It is the strongest defensible
version of the idea: executable in Lean, explicit about effects, able to carry
proof-state coupling, and able to project back into the artifacts the repo
already uses.

Companion files:

- [README.md](../README.md)
- [theorem-agenda.md](theorem-agenda.md)

## Boundary

This addendum owns the research question. `wonton-soup` owns `TacticActionIR`
and `ProofGraphIR`.

Any calculus in this repo must do two things:

1. interpret into Lean,
2. project into the current step-level and graph-level artifacts.

If either fails, reject the representation.

## Minimum Target

The calculus needs:

- executable interpretation into Lean,
- explicit effects,
- explicit continuation shape,
- explicit goal coupling,
- composition laws with side conditions,
- round-trippable serialization,
- projection into existing trace artifacts.

It does not need to encode every Lean tactic in a closed syntax. Lean tactics
are extensible, so the core needs an explicit extension node.

## State Objects

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

`provenance` includes toolchain, imports, options, trusted extensions, and
replay-relevant elaboration settings.

```text
Obligation =
  < obligation_id,
    local_context,
    target_type,
    local_assignments,
    visibility,
    provenance_ref >
```

```text
Coupling =
  < child_obligations,
    shared_metavars,
    dependency_edges,
    coupling_kind >
```

`coupling_kind` summarizes to `none`, `independent`, `coupled`, or
`unknown`.

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

The residual builder is not an inverse. It is the continuation that fills the
parent hole after child witnesses arrive.

## Core Language

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

Named tactic families such as `intro`, `apply`, `exact`, `cases`, `simp`, and
`rewrite` compile into this core. They are not the foundation.

## Effects

Inspection:

- `ViewActiveObligations`
- `ReadObligation obligation_id`
- `ReadLocalContext obligation_id`
- `ReadMetavarGraph`
- `ReadConstraintStore`
- `ReadEnvironment query`

Construction:

- `FreshMetavar type`
- `SpawnObligations interface`
- `AssignMetavar hole witness`
- `RegisterResidualBuilder builder`

Elaboration and kernel-facing effects:

- `Elaborate syntax expected_type`
- `Normalize expr mode`
- `Unify lhs rhs`
- `Rewrite target rule location`
- `SynthesizeInstance class_goal`
- `CheckWitness witness obligation`

Search and control:

- `Checkpoint`
- `Rollback checkpoint_id`
- `Backtrack reason`
- `Cut label`
- `ConsumeFuel amount`

Provenance:

- `ReadProvenance`
- `RequireReplayCompatibility expected_provenance`

## Semantics

One step:

```text
[[step]] : (s, g) -> TacEff StepPack
```

The return value exposes state change, child interface, coupling, residual
builder, and replay certificates.

Typing:

```text
Delta ; I_in |- t : I_out ! Phi
```

Typing rules must rule out:

- out-of-scope holes or hypotheses,
- residual builders expecting witnesses that were not spawned,
- obligation-id collisions,
- dropped replay-critical provenance,
- branch laws without coupling side conditions.

Observational equality:

```text
t ~= u
```

Relative to a handler and compatible provenance, equality means:

- same success or failure class,
- equivalent output interface and coupling,
- equivalent parent witness behavior once child witnesses are supplied,
- same replay obligations.

## Laws

Worth claiming:

- `bind` associativity up to observational equality,
- `pure` left and right unit for `bind`,
- `fail` left zero for sequencing,
- `choice` laws relative to explicit control policy,
- focus and scope laws when visibility and interface constraints are preserved,
- branch permutation under coupling-disconnected and residual-equivariant side
  conditions,
- fixpoint laws under explicit fuel or termination discipline.

Not worth claiming early:

- ordinary lens laws for arbitrary tactics,
- tactic-step invertibility,
- child-goal independence from branch count alone,
- semantic equality from tactic-string equality,
- closed syntax for all Lean tactics.

## Foreign Tactics

```text
foreign symbol payload contract
```

The contract declares:

- effect footprint,
- input and output interface boundary,
- replay codec,
- projection behavior,
- known refinement into the core, if any.

Two modes are allowed:

1. black-box execution contract,
2. proven refinement into the core.

Hidden raw-string fallback is not allowed.

## Projection

A successful `StepPack` must project to `TacticActionIR` fields for branch
arity, continuation kind, coupling summary, dependency summary, effect flags,
and proof-step count.

It must also project to assembly traces with parent and child obligation ids,
partial term before and after, and completed proof term when available.

Graph comparison remains downstream. It does not drive the semantics.

## Serialization

Round-trippable serialization requires:

- typed AST encoding,
- schema versioning,
- explicit provenance payload,
- stable obligation and residual-builder ids,
- explicit `foreign` nodes with declared contracts,
- no hidden dependence on pretty-printed Lean state.

Round-trip means:

1. parse serialized term,
2. recover the same typed term and provenance witness,
3. replay under Lean or reject with a precise incompatibility error.

Silent repair is not round-trip.

## Theorem Program

The minimum theorem set:

1. handler soundness,
2. serialization round-trip,
3. projection soundness,
4. conditional branch independence,
5. conservative extension.

The ambitious set:

1. adequacy to Lean execution for a core fragment,
2. completeness of trace extraction for that fragment up to observational
   equality,
3. optic or dependent-lens interpretation where the laws hold,
4. polynomial semantics for the provably independent fragment.

Detailed judgments and first lemmas are in
[theorem-agenda.md](theorem-agenda.md).

## Evaluation

Judge the calculus on:

- replay validity against Lean,
- witness equality or conservative equivalence,
- child-interface fidelity,
- coupling fidelity against the metavar graph,
- laws holding exactly where side conditions allow them,
- constrained-decoding validity,
- sample efficiency versus string tactics,
- proof success under fixed budgets,
- provenance-sensitive replay.

## Anchors

- [Nazrin (arXiv:2602.18767, v2 March 2, 2026)](https://arxiv.org/abs/2602.18767):
  finite atomic basis plus `ExprGraph`.
- [LeanTree (AI for Math Workshop 2025)](https://ufal.mff.cuni.cz/biblio/attachments/2025-kripner-p2251125924673771681.pdf):
  factorized states with explicit metavariable coupling.
- [LeanDojo-v2 (2025)](https://leandojo.org/leandojo.html):
  broad Lean 4 tracing and search.
- [LeanProgress (arXiv:2502.17925, v3 January 18, 2026)](https://arxiv.org/abs/2502.17925):
  proof progress as a separate predictive signal.
- [DeepSeek-Prover-V2 (arXiv:2504.21801, v2 July 18, 2025)](https://arxiv.org/abs/2504.21801)
  and [Goedel-Prover-V2 (arXiv:2508.03613, August 5, 2025)](https://arxiv.org/abs/2508.03613):
  decomposition and self-correction on the critical path.

The pressure from these systems is concrete: atomic actions, coupled proof
states, decomposition, repair, progress-sensitive control, and replay.
