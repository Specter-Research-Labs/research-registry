# Lean Tactic Representation

Research agenda and toy interpreter for structured Lean tactic representations.

The question is whether proof tactics can be represented as compositional
objects instead of strings, with executable semantics and a testable evaluation protocol.

Start with `docs/general-algebraic-tactic-calculus-spec.md` for the technical
target.

The runnable code is a toy interpreter and visualizer for calculus fragments.

## Check

```bash
cd addenda/lean-tactic-representation
nix develop
uv run ruff check .
uv run ty check .
uv run python -m pytest
```

## Related

This addendum asks the representation question. The concrete IR docs live in
`wonton-soup`:

- [TacticActionIR](../../dossiers/wonton-soup/docs/concepts/tactic-action-ir.md):
  a pragmatic typed summary of what one observed proof step did
- [ProofGraphIR](../../dossiers/wonton-soup/docs/concepts/proof-graph-ir.md):
  the downstream graph-level abstraction used for cross-assistant comparison
