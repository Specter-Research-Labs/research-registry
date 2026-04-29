# Approach

Stage 1 asks for a plain-text cheatsheet, under `10 KB`, that helps an offline
model decide whether Equation 1 implies Equation 2 over all magmas.

The full analysis can use the implication graph and residual witness search.
The submitted sheet cannot. The work here is to compress what the graph teaches
into a small, literal decision procedure.

## Inputs

The analysis uses four pinned assets:

- public `normal.jsonl`
- public `hard.jsonl`
- `equations.txt`
- `graph.json`

The public benchmark maps exactly into the fixed `4694`-law implication graph.
The code uses that graph to:

1. validate headline results against the full law universe,
2. mine theorem-backed always-TRUE source families,
3. measure how much of the public benchmark is explained by small semantic
   bases and finite witness stacks.

Some analysis remains internal to the code, including exact source-row semantics
over the `2`-element theory classes. The sheet only ships the finite pieces it
can state plainly.

## Submitted Procedure

The final cheatsheet is smaller than the analysis stack.

It runs this ordered procedure:

1. normalize variable names by first appearance,
2. apply theorem-backed always-TRUE source families,
3. test a fixed `10`-table `2`-element separator basis,
4. check direct substitution and one-hole context closure,
5. apply an exact source-triggered kernel catalog,
6. apply two exact commutativity repairs,
7. use a tiny final FALSE tie-break only if everything earlier failed.

The order is part of the result. The theorem rules are cheap and global. The
separator basis is the strongest compact FALSE test that fits comfortably in
plain text. The catalog rules only fire where they are written explicitly.

## TRUE Rules

The strongest shipped TRUE rules come from two full-graph source families:

- **collapse**: `x = t` with `x` absent from `t`
- **mixed self-reference with singleton**: `x = t`, every occurrence of `x`
  lies on a mixed left/right path, some other variable occurs exactly once, and
  the x-path set does not contain both exact `LR` and `RL`

These rules are exact across the full implication graph, not just the public
split.

The graph explains more TRUE cases through exact source-row semantics, but that
layer is not fully serialized into the sheet.

## FALSE Tests

FALSE decisions use explicit separation.

The shipped test is the fixed `10`-table `2`-element basis. If any table
satisfies E1 and breaks E2, the implication is false.

The larger analysis also uses:

- a greedy `2`-element witness battery,
- exhaustive `3`-element search,
- residual SAT search at sizes `4` and `5`.

Those searches measure the remaining false tail. They are not part of the
plain-text evaluator.

## Finite Proof Catalog

Earlier drafts used graph-backed provenance to admit short kernels, then
described that step as if the kernels were derived offline by simple source
manipulations. That was too strong.

The current proof layer is finite:

- `10` exact source-triggered kernel rules in `proof_catalog.py`
- `2` exact source-triggered commutativity repairs

Nothing is discovered online. Either E1 matches one of the cataloged normalized
source equations, or the rule does not fire.

## Limits

The sheet is strongest on theorem-backed TRUE cases, small explicit FALSE
witnesses, and the tiny finite set of cataloged TRUE repairs.

It is weaker on cases that need larger negative witnesses, source-row semantics
that were not compressed into the sheet, or open-ended proof search.

That is the trade: Stage 1 rewards a compact offline artifact, not the largest
analysis stack.
