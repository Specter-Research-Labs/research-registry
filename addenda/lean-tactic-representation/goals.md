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

Current executable slice:

- execute strict `exact` / `apply` / `constructor` program trees in Lean
- preserve each step as a typed action record with stable obligation paths
- make branching, continuation shape, coupling, residual builders, and dependencies explicit
- kernel-check the reassembled proof with captured replay provenance

Next evidence target:

- reproduce one shared-metavariable coupled branch in the real Lean bridge
- avoid claiming a general compositional calculus until the coupling and composition laws survive
