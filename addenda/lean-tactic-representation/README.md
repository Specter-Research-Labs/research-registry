# Lean Tactic Representation

Tracks the research agenda for richer tactic representation in Lean.

Asks whether proof tactics admit a representation that is structurally richer than strings, possibly algebraic or compositional, with an explicit execution story and evaluation plan.

## What Lives Here

- [research.md](research.md):
  survey, objections, and a plausible path to a proof-of-concept
- [goals.md](goals.md):
  research scope and concrete success criteria
- [docs/general-algebraic-tactic-calculus-spec.md](docs/general-algebraic-tactic-calculus-spec.md):
  research-level semantic spec for a fully general algebraic tactic calculus
- [docs/theorem-agenda.md](docs/theorem-agenda.md):
  companion theorem program with fixed judgments, side conditions, and the first lemmas to attempt
- `core/`, `examples/`, `render.py`, and `cli.py`:
  toy interpreter and CLI visualizer for calculus fragments, examples, and invariant checks

## What Does Not Live Here

- `TacticActionIR` lives in `wonton-soup`.
- `ProofGraphIR` lives in `wonton-soup`.

Those are dossier concerns because they are artifact contracts and analysis surfaces, not the
research program itself.

## Related Dossier Surfaces

The nearest concrete implementation work is documented in:

- [TacticActionIR](../../dossiers/wonton-soup/docs/concepts/tactic-action-ir.md):
  a pragmatic typed summary of what one observed proof step did
- [ProofGraphIR](../../dossiers/wonton-soup/docs/concepts/proof-graph-ir.md):
  the downstream graph-level abstraction used for cross-assistant comparison

Those surfaces inform this addendum, but they are not the addendum itself.

## Boundary

The clean split is:

- this addendum owns the research question about richer tactic representation
- `wonton-soup` owns the step-level and graph-level IR surfaces

That split keeps the research agenda separate from the dossier’s working artifact contracts.
