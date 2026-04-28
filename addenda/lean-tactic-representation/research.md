# Algebraic Representations of Proof Tactics for Machine-Assisted Theorem Proving

This note evaluates whether Lean tactics can be represented as algebraic objects (rather than strings), identifies concrete resources, calls out flaws in the current argument, and sketches a minimal path to a proof-of-concept.

This is a research note, not a description of the current executable contract. The current
`TacticActionIR` work is narrower: it records typed step semantics without yet claiming an algebraic
or compositional tactic language.

## 1) What is solid and directly relevant

### Optics and dependent optics
- **Profunctor optics** give a unified categorical account of lenses, prisms, traversals, and related bidirectional accessors, with a representation theorem that supports modular composition. (Clarke et al., 2024)
- **Dependent optics** generalize optics to indexed categories and state explicit conditions under which coproducts exist; these conditions matter if we want branching tactics to be first-class. (Vertechi, 2022)
- **Fibre optics** unify lenses, optics, and dependent lenses via a fibrational construction, directly relevant because proof states naturally live over contexts. (Braithwaite et al., 2021)
- **Fibrational construction for optics and Dialectica** shows optics/lenses/Dialectica categories as instances of a single construction, clarifying where bidirectionality is shared and where it is not. (Capucci et al., 2024)

### Polynomial functors and dependent lenses (containers)
- Polynomial functors (containers) provide an algebraic model of branching structure. A polynomial functor has the form `P(X) = Σ_{i∈I} X^{A_i}`, where `I` are shapes and `A_i` are positions/directions. (Niu & Spivak, 2025)
- Morphisms between polynomials are **dependent lenses**; the category of polynomials supports composition products that align with sequential composition of interactive systems. (Niu & Spivak, 2025)

### Algebraic effects and free monads
- **Algebraic effects and handlers** provide a semantics where effect signatures generate free models (monads) and handlers interpret them. This is an appropriate semantic substrate for a tactic DSL. (Plotkin & Pretnar, 2013)
- **Interaction Trees (ITrees)** are coinductive free monads for potentially non-terminating effectful programs, with a rich equational theory; they are suitable for recursive tactics like `repeat`. (Xia et al., 2020)
- **Mtac2** shows that typed, monadic tactic languages can statically rule out classes of errors; it provides a practical precedent for typed tactic DSLs. (Kaiser & Ziliani, 2018)

### Lean 4 metaprogramming primitives
- Lean 4’s metaprogramming API is organized around `CoreM`, `MetaM`, `TermElabM`, and `TacticM`. `TacticM` is `ReaderT Context (StateRefT State TermElabM)`, and tactics act on the list of current goals. (Lean 4 metaprogramming book)
- Goals are **metavariables** (`MVarId`) with a local context and a target type; closing a goal corresponds to assigning a metavariable. (Lean 4 metaprogramming book)

## 2) Current systems and data relevant to tactics

- **LeanDojo + ReProver**: retrieval-augmented tactic generation from serialized proof states and premises; provides large benchmarks and interfaces for Lean interaction. The LeanDojo site notes the original release is deprecated in favor of LeanDojo-v2. (LeanDojo, NeurIPS 2023)
- **Pantograph**: a Lean 4 interface that extracts before/after goal states, supports proof-tree search, and explicitly handles metavariable coupling. (Pantograph, TACAS 2025)
- **COPRA**: an in-context proof agent for Lean/Coq that uses LLMs to drive tactic search and evaluation. (COPRA repo)
- **Ineq-Comp**: a benchmark exposing compositional reasoning gaps in current provers even when constituent proofs are provided. (Ineq-Comp, NeurIPS 2025)

## 3) Flaws and gaps in the current argument

1. **“Bidirectionality” is not automatic.** Lean tactics are not generally invertible; the “backward” direction is implemented by metavariable assignment and elaboration, not by an explicit inverse. An optic semantics must model this explicitly, likely as a *continuation* or *proof-term builder* rather than a true inverse.
2. **Subgoal independence is often false.** Lean subgoals can share metavariables, so a simple polynomial branching model (independent subgoals) is insufficient. The representation must track coupling between goals.
3. **Effects are pervasive.** Typeclass resolution, unification, backtracking, environment access, and elaboration effects are central to tactics. Any algebraic representation must account for these effects (e.g., via algebraic effects + handlers), or it will be semantically incomplete.
4. **Optic laws may not hold.** Standard lens laws rely on totality and determinism; tactic steps can be partial or nondeterministic. If we want law-like properties, we must state them in the appropriate effectful setting.
5. **No canonical dataset yet.** LeanDojo and Pantograph are string/trace oriented. There is no established pipeline that translates Lean proofs into algebraic tactic objects suitable for training or evaluation.

## 4) A minimal, testable path to a proof-of-concept

**Goal:** show that a small algebraic tactic DSL can (a) execute against Lean 4, and (b) improve compositional generalization vs. string tactics on a controlled benchmark.

1. **Define a minimal core DSL.**
   - Primitives: `intro`, `apply`, `exact`, `cases`, `simp`, `rewrite`.
   - Representation: a tree with explicit branching, plus a *continuation* that assembles proof terms once subgoals are solved.

2. **Make dependencies explicit.**
   - Represent goal coupling by attaching metavariable dependency info to branches.
   - Use a dependent-lens style representation to ensure that backward steps depend on forward decomposition.

3. **Provide a Lean 4 interpreter.**
   - A handler from the DSL into `MetaM`/`TacticM` that executes a step, returns new goals, and stores the proof-term builder.
   - Fail loudly on mismatched contexts or unresolved metavariable dependencies (no hidden fallbacks).

4. **Extract data and validate equivalence.**
   - Use Pantograph/LeanDojo traces to build a translator from Lean tactics to DSL trees.
   - Validate on a small corpus: re-run the DSL against Lean and check it yields the same proof terms.

5. **LLM integration and evaluation.**
   - Serialize the DSL as a typed AST; use constrained decoding or grammar-based generation.
   - Evaluate on LeanDojo splits and on Ineq-Comp to test compositional generalization.

## 5) Resources (primary)

### Optics and dependent optics
- Clarke et al., *Profunctor Optics: A Categorical Update*, Compositionality 2024. https://compositionality.episciences.org/13530
- Vertechi, *Dependent Optics*, arXiv 2022. https://arxiv.org/abs/2204.09547
- Braithwaite et al., *Fibre Optics*, arXiv 2021. https://arxiv.org/abs/2112.11145
- Capucci et al., *On a fibrational construction for optics, lenses, and Dialectica categories*, ENTICS 2024. https://entics.episciences.org/14638

### Polynomial functors
- Niu & Spivak, *Polynomial Functors: A Mathematical Theory of Interaction*, Cambridge University Press, 2025. https://www.cambridge.org/core/books/polynomial-functors/5A57527AE303503CDCC9B71D3799231F

### Algebraic effects and tactics
- Plotkin & Pretnar, *Handling Algebraic Effects*, LMCS 2013. https://lmcs.episciences.org/705
- Xia et al., *Interaction Trees: Representing Recursive and Impure Programs in Coq*, POPL 2020. https://doi.org/10.1145/3371119
- Kaiser & Ziliani, *Mtac2: Typed Tactics for Backward Reasoning in Coq*, ICFP 2018. https://doi.org/10.1145/3236773

### Lean 4 metaprogramming
- *Metaprogramming in Lean 4* (community book): `MetaM` and `TacticM` chapters.
  - https://leanprover-community.github.io/lean4-metaprogramming-book/main/04_metam.html
  - https://leanprover-community.github.io/lean4-metaprogramming-book/main/09_tactics.html

### Tooling and benchmarks
- LeanDojo paper (NeurIPS 2023). https://proceedings.neurips.cc/paper_files/paper/2023/hash/4441469427094f8873d0fecb0c4e1cee-Abstract-Datasets_and_Benchmarks.html
- LeanDojo site (v2 recommended). https://leandojo.org/leandojo
- Pantograph (TACAS 2025). https://link.springer.com/chapter/10.1007/978-3-031-90643-5_6
- COPRA repo. https://github.com/trishullab/copra
- Ineq-Comp benchmark (NeurIPS 2025 poster). https://neurips.cc/virtual/2025/poster/121821
- Ineq-Comp dataset/code repo. https://github.com/haoyuzhao123/LeanIneqComp

### Related funded efforts (context)
- Renaissance Philanthropy: *A Structured Representation of Tactics for Machine-Assisted Theorem Proving* (project page). https://www.renaissancephilanthropy.org/a-structured-representation-of-tactics-for-machine-assisted-theorem-proving
- ARIA Safeguarded AI (TA1.1 theory call for proposals). https://www.aria.org.uk/wp-content/uploads/2024/04/ARIA-Safeguarded-AI-TA1.1-Theory-Call-for-proposals.pdf
