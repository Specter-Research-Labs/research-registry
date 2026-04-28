- Map Lean4 proof state representation (TacticM, metavariables, elaboration).
- Design a round-trippable, LLM-friendly serialization format.
- Survey existing tactic-learning systems and set baselines.
- Define evaluation criteria, corpora, and metrics.

- Investigate whether proof tactics can be represented as algebraic objects in a high-level
  language.
- When you apply a tactic, it transforms a proof state
- If that stronger representation turns out to be defensible, it could then be:
  1. Translated into Lean meta-programs
  2. Used to enable LLMs to automatically generate proof scripts through interactive sessions with the theorem prover

Current executable target:

- preserve one proof step as a typed action record
- make branching, continuation shape, coupling, and dependencies explicit
- avoid claiming a compositional calculus before we have evidence for it
