# Theorem Agenda for the General Algebraic Tactic Calculus

Companion to
[general-algebraic-tactic-calculus-spec.md](general-algebraic-tactic-calculus-spec.md).
Fixes the judgments, side conditions, theorem families, and first lemmas. It exists
to keep the calculus from collapsing into metaphor.

## Scope

Assume the stance already fixed in the spec:

- open core
- explicit effects
- explicit coupling
- continuation-carrying step packs
- provenance-sensitive replay

Do not assume:

- closed syntax for all Lean tactics
- global subgoal independence
- ordinary lens laws for arbitrary tactics
- full algebraic reduction of every foreign metaprogram

## Core Judgments

These should be treated as the canonical judgment forms.

### Provenance well-formedness

```text
|- Pi wf
```

`Pi` contains a coherent toolchain, imports, options, trusted extensions, and handler boundary.

### Replay compatibility

```text
Pi ~=prov Pi'
```

Replay under `Pi'` is semantically admitted for terms authored under `Pi`.

### Interface well-formedness

```text
Delta ; Pi |- I wf
```

`I` is scoped, identifier-consistent, and provenance-valid under `Delta` and `Pi`.

### Proof-state well-formedness

```text
Delta ; Pi |- s wf
```

The active obligations, focus, constraint store, metavar graph, and partial term are coherent.

### Typing and effects

```text
Delta ; I_in |- t : I_out ! Phi
```

`t` maps input interface `I_in` to output interface `I_out` with effect footprint `Phi`.

### Primitive step execution

```text
Pi ; H |- step @ (s, g) ==> R
```

`R` ranges over at least:

- `success pack`
- `failure err`
- `backtrack reason`

### Residual-builder admissibility

```text
Delta ; Pi |- rho : CW(C) => PW(g)
```

`rho` consumes child witnesses matching coupling object `C` and yields a parent witness for `g`.

### Observational equivalence

```text
Delta ; I |- t ~=obs u : I' [Pi, H]
```

`t` and `u` agree on success or failure class, output interface, coupling behavior, witness
behavior, and replay obligations under `Pi` and `H`.

### Projection

```text
Pi |- pack ==>action a
Pi |- pack ==>assembly m
```

`pack` forgets to current action-level and assembly-level repo surfaces.

### Serialization round-trip

```text
Delta ; I_in |- t : I_out ! Phi
parse(serialize(t)) = t'
```

Required conclusion:

```text
Delta ; I_in |- t' : I_out ! Phi
and
t ~=obs t' : I_out [Pi, H]
```

## Side Conditions

Use these names in theorem statements.

### `ReplayCompat(Pi, Pi')`

Replay under `Pi'` is admitted for artifacts authored under `Pi`.

### `ScopeClosed(Delta, x)`

Every hypothesis, hole, obligation id, and environment reference in `x` is in scope.

### `IfaceMatch(I, J)`

`I` and `J` agree on shape, id discipline, and witness boundary.

### `CouplingDisconnected(C)`

The relevant branch families in `C` have no dependency path.

### `ResidualEquivariant(rho, sigma, C)`

Permuting independent child witnesses by `sigma` commutes with `rho`.

### `EffectContained(Phi, H)`

Handler `H` implements the effects in `Phi` with the guarantees the theorem requires.

### `FuelAdequate(k, t)`

Fuel bound `k` is sufficient for the theorem slice of `t`.

### `ForeignContractWellFormed(c)`

Foreign contract `c` declares interface boundary, effect footprint, replay codec, projection
behavior, and refinement status.

### `KernelChecked(w, g, Pi)`

Witness `w` closes obligation `g` under provenance `Pi` by Lean's kernel check.

## Theorem Families

### Family A: Static well-formedness

- weakening of unused scope preserves typing
- interface composition preserves well-formedness
- effect footprints compose monotonically under sequencing
- malformed `foreign` contracts are rejected

### Family B: Primitive operational soundness

- a well-typed primitive step returns typed failure, typed backtrack, or a well-formed `StepPack`
- successful primitive steps preserve proof-state well-formedness
- successful primitive steps produce admissible residual builders for their exact child interface

### Family C: Handler and replay soundness

- successful handled execution yields kernel-checked witnesses
- replay under compatible provenance preserves observational behavior
- replay under incompatible provenance is rejected, not silently repaired

### Family D: Projection soundness

- `StepPack` projection preserves continuation, coupling, dependency, and effect summaries
- assembly projection preserves obligation linkage and partial-term transitions
- graph projection preserves the structural signal current analysis depends on

### Family E: Conditional algebraic laws

- sequencing laws
- focus and scope laws
- branch permutation or parallel-evaluation laws under explicit independence side conditions
- control laws for `choice`, `try`, and `fix` under handler and fuel side conditions

### Family F: Conservative extensibility

- well-contracted `foreign` nodes do not invalidate core soundness theorems
- refined `foreign` nodes are observationally equivalent to their core refinement
- black-box `foreign` nodes can still be replay-checked and projected without fake internal laws

## First Lemmas to Attempt

### Lemma 1: Primitive step preserves well-formedness

```text
If
  Delta ; Pi |- s wf
  and Delta ; I |- step : I' ! Phi
  and Pi ; H |- step @ (s, g) ==> success pack
then
  Delta ; Pi |- apply(pack, s) wf
```

Role:

- establishes that `ProofState`, `StepPack`, and state application are coherent

### Lemma 2: Residual-builder domain exactness

```text
If
  Pi ; H |- step @ (s, g) ==> success pack
then
  pack.residual_builder is admissible exactly for the child interface returned by pack
```

Role:

- makes continuation semantics precise
- blocks fake branch laws based on under-specified witness families

### Lemma 3: Handler success yields kernel-checked witness

```text
If
  Delta ; I_in |- t : I_out ! Phi
  and Delta ; Pi |- s wf
  and EffectContained(Phi, H)
  and Pi ; H |- t @ s ==> success w
then
  KernelChecked(w, target(s), Pi)
```

Role:

- connects the calculus to Lean in the only way that finally matters

### Lemma 4: Projection preserves action-level summaries

```text
If
  Pi ; H |- step @ (s, g) ==> success pack
  and Pi |- pack ==>action a
then
  a correctly summarizes branch arity, continuation, coupling, dependencies, and effects
```

Role:

- keeps the calculus connected to `TacticActionIR`

### Lemma 5: Branch permutation under explicit independence

```text
If
  CouplingDisconnected(C)
  and ResidualEquivariant(rho, sigma, C)
then
  the relevant branch orders are observationally equivalent
```

Role:

- first genuinely algebraic law
- precise replacement for the overclaim that "multiple subgoals are independent"

## Theorems to Delay

- global completeness for all Lean tactics
- ordinary optic laws for the full calculus
- global confluence or normalization
- full trace completeness against arbitrary extracted scripts

## Mechanization Order

### Stage 0: paper semantics

Fix syntax, judgments, side conditions, and theorem statements.

Exit:

- the first five lemmas have stable statements with no undefined objects

### Stage 1: core mechanization without `foreign`

Mechanize:

- interface well-formedness
- primitive step typing
- typed success or failure results
- residual-builder admissibility
- sequencing laws

Exit:

- Lemmas 1 and 2 mechanized for a small core fragment

### Stage 2: handler bridge

Connect the abstract handler to a Lean-side interpreter for a small primitive fragment.

Exit:

- Lemma 3 for a nontrivial executable fragment

### Stage 3: projection bridge

Prove forgetful projection into current repo artifacts.

Exit:

- Lemma 4 for the same fragment

### Stage 4: conditional algebraic laws

Add independence and permutation laws once the operational bridge is stable.

Exit:

- Lemma 5 for the explicit independence fragment

### Stage 5: foreign conservativity

Reintroduce the open extension mechanism into the mechanized story.

Exit:

- conservative extension theorem for well-contracted `foreign` nodes

## Proof Risks

- provenance may be underspecified for stable replay
- witness-family typing may be too weak for residual-builder theorems
- coupling may not be captured by shared metavariables alone
- weak `foreign` contracts can collapse the theory into a hidden escape hatch
- the handler trust boundary can become implicit if we are careless

## Success Criteria

The agenda is working if it makes two failures hard:

- stating a law without naming the side conditions that justify it
- claiming semantic richness without showing the executable and observational projections

If the agenda works, the next step is not more prose. It is a fragment spec with concrete syntax,
typing rules, and a first proof in earnest.
