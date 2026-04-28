# K Equations From CATWD 2.0

Explains the `P` and `K` equations used in this addendum, grounded in
Robert Chis-Ciure and Michael Levin, *Cognition all the way down 2.0:
neuroscience beyond neurons in the diverse intelligence era* (Synthese, 2025),
<https://doi.org/10.1007/s11229-025-05319-6>.

The paper’s core move is to treat intelligence as search efficiency in a shared
problem space, not as a vague label for “complex behavior”. The addendum here
implements that claim as a small reference calculus and a set of runnable toy
domains.

## The Two Equations

The paper defines search efficiency with:

```text
K = log10(tau_blind / tau_agent)
```

The article describes this as “the decimal logarithm of the ratio” between the
cost of a blind walk and the cost of an agentic policy. In plain terms:

- `tau_blind` is the expected cumulative cost of an unbiased or maximal-entropy
  search policy over the same admissible moves.
- `tau_agent` is the expected cumulative cost of the agent policy over that same
  search problem.
- `K` is measured in orders of magnitude.

That last point matters. `K = 1` means the agent is about `10x` more efficient
than blind search. `K = 2` means about `100x`. `K = 0` means no gain. Negative
`K` would mean the supposed agent is worse than the blind baseline.

The paper’s second important equation is not a scalar but a structured object:

```text
P = <S, O, C, E, H>
```

The paper calls this a “scale-agnostic quintuple”. It is the thing that defines
the search problem whose efficiency is being measured.

## What Each Part Means

- `S`: the state space. What configurations count as reachable states?
- `O`: the operator alphabet. What elementary moves are allowed?
- `C`: constraints. Which state-operator combinations are disallowed or
  impossible?
- `E`: the evaluation functional. What makes a state or trajectory good, bad, or
  goal-satisfying?
- `H`: the predictive horizon or budget. How far is the comparison allowed to
  search?

The addendum also tracks:

- `w`: the operator cost function, because different operators can have
  different costs even inside the same `O`.
- `H_unit` and `w_unit`: because the paper’s insistence on commensurate units is
  not bookkeeping trivia; it is what keeps the ratio meaningful.

## What The Metric Actually Measures

The paper says `K` records how much an agent “prunes the futile branches” of a
problem space relative to a maximal-entropy walk. That is the right intuition.

`K` is not:

- raw success rate by itself
- raw speed by itself
- a generic intelligence score detached from a modeling choice

`K` is:

- a comparison between two policies
- inside one explicitly modeled problem space
- under one explicit cost currency
- under one explicit horizon

So the real object being measured is not “the organism” or “the algorithm” in
the abstract. It is the efficiency gain of one policy over another once you
commit to a particular search model.

## Why The Shared Problem Space Matters

This is the most important modeling discipline in the whole paper and in this
repository.

If `tau_agent` and `tau_blind` are computed in different spaces, with different
operators, different constraints, or different cost units, then the ratio is no
longer interpretable. The paper explicitly warns that choices about `O`, `C`,
and `w` shift the result.

That is why this addendum keeps agent and blind policies inside one
`ProblemSpace` and, when available, records shared operator semantics in
`PolicySpec`. The policy may change; the problem definition may not.

## How This Addendum Maps The Paper To Code

The main reference surface is [`core.py`](../core.py).

The core datatypes line up with the paper like this:

- `ProblemSpace`: the implementation of `P = <S, O, C, E, H>` plus units and
  optional `S_init` / `S_goal` descriptors for reporting.
- `PolicySpec`: an explicit record of what the policy means operationally.
- `PairedTrial`: one paired observation of agent cost and blind cost under the
  same setup.
- `paper_k_from_paired_trials(...)`: compute `K` from trial data.
- `paper_k_from_expectations(...)`: compute `K` when expected costs are already
  known.

The demos in [`demos/`](../demos/)
instantiate that calculus with small spaces where the modeling choices are easy
to inspect:

- sorting: adjacent swaps
- grid: four-neighbor motion
- bitstring repair: single-bit flips
- synthesis: bounded RPN program construction
- chemotaxis, Hanoi, GRN, and compositional variants
- two paper-facing examples for amoeboid chemotaxis and planarian regeneration

## How To Read A Reported K Value

When you see a result from this addendum, ask these questions in order:

1. What exactly is `S`?
2. What exactly counts as one operator in `O`?
3. What is the cost function `w`?
4. What is the horizon `H`, and what happens when a trial fails within it?
5. Is the blind baseline truly operating over the same admissible graph?

If those answers are crisp, then `K` is meaningful. If they are fuzzy, `K` is
mostly a placeholder for hidden assumptions.

## What The Metric Gives You

When modeled carefully, `K` gives a compact answer to a hard question:

How much better than blind search is this policy, measured in the natural cost
currency of the task?

That is why the paper uses it as a bridge concept across very different
substrates. The value is not that all systems reduce to one scalar. The value is
that the scalar forces the modeler to expose the search space, the move set, the
constraints, the cost measure, and the comparison policy.

That is also the point of this addendum. It is not a benchmark leaderboard. It
is a reference implementation for making the paper’s commitments explicit,
runnable, and inspectable.
