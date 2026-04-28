# Approach

## Task

Stage 1 asks for a plain-text cheatsheet, under `10 KB`, that helps an offline no-tools model
decide whether Equation 1 implies Equation 2 over all magmas.

That forces a split between two surfaces:

- the **teacher surface** used to discover and validate rules
- the **shipped evaluator** that must be small, literal, and executable from plain text

The teacher surface is stronger than the final artifact. The point of the addendum is to compress
that stronger surface into a finite decision procedure without pretending the compression is more
constructive than it is.

## Teacher Surface

The teacher surface is built from four pinned assets:

- public `normal.jsonl`
- public `hard.jsonl`
- `equations.txt`
- `graph.json`

The public benchmark maps exactly into the fixed `4694`-law implication graph, so the graph is the
offline teacher. The code uses it for three things:

1. validating headline results against the full law universe
2. mining theorem-backed always-TRUE source families
3. measuring how much of the public benchmark is already explained by small semantic bases and
   finite witness stacks

The teacher surface also supports experiments that are intentionally not shipped into the final
sheet, such as exact source-row semantics over the `2`-element theory classes.

## Shipped Evaluator

The final cheatsheet is narrower than the full analysis stack.

Its ordered procedure is:

1. normalize variable names by first appearance
2. apply theorem-backed always-TRUE source families
3. test a fixed `10`-table `2`-element separator basis
4. check direct substitution and one-hole context closure
5. apply an exact source-triggered kernel catalog
6. apply two exact commutativity repairs
7. use a tiny final FALSE tie-break only if everything earlier failed

The order matters:

- the theorem rules are globally strong and cheap
- the `10`-table separator is the strongest compact FALSE mechanism that easily fits in text
- substitution/context checks are exact and cheap
- the kernel catalog and commutativity repairs are only used where they are written explicitly

## TRUE Side

The strongest shipped TRUE rules come from two full-graph source families:

- **collapse**: `x = t` with `x` absent from `t`
- **mixed-self-reference with singleton**: `x = t`, every occurrence of `x` lies on a mixed
  left/right path, some other variable occurs exactly once, and the x-path set does not contain
  both exact `LR` and `RL`

These are the high-yield global rules because they are exact across the full implication graph, not
just the public split.

After those theorem rules, the teacher analysis still explains much more TRUE mass through exact
source-row semantics. That layer is not fully serialized into the shipped cheatsheet. It remains
analysis-side context, not a claim about what the final artifact can reconstruct offline.

## FALSE Side

The FALSE side works by explicit separation, not proof search.

The compact shipped mechanism is the fixed `10`-table `2`-element basis. If any one of those
representatives satisfies E1 but breaks E2, the implication is false.

The analysis stack goes further:

- greedy `2`-element witness battery
- exhaustive `3`-element search
- residual SAT search at sizes `4` and `5`

That larger witness stack is how the addendum measures the remaining false tail and where the
cheatsheet is still weaker than the internal analysis.

## Constructive Proof Layer

The last major design correction was to make the proof layer honest.

Earlier versions used graph-backed provenance to admit short kernels and then described that layer
as if the kernels were derived offline by simple source manipulations. That was not a valid
serialization.

The current proof layer is explicit and finite:

- `10` exact source-triggered kernel rules in `proof_catalog.py`
- `2` exact source-triggered commutativity repairs

Nothing is discovered online in that layer. Either E1 matches one of the cataloged normalized
source equations, or the rule does not fire.

That is the crucial distinction between the current artifact and the earlier review packets:

- the code now consumes the same finite catalog that the cheatsheet names
- the cheatsheet no longer claims to derive new kernels outside that catalog

## Why The Source-Row Work Still Matters

Exact source-row semantics is not fully shipped, but it still matters because it explains the
geometry of the benchmark:

- why the theorem rules leave a structured residual instead of random noise
- why raw fingerprint labels are too coarse
- why the center of gravity eventually moved toward the false residual once the proof layer became
  constructive

So the source-row work remains the main explanatory lens, but not the main user-facing procedure.

## Limitations

The current artifact is strongest on:

- theorem-backed TRUE cases
- FALSE cases with small explicit witnesses
- the tiny finite set of cataloged constructive TRUE repairs

It is weaker on:

- hidden cases that require stronger negative witnesses than the shipped `10`-table basis
- source laws whose teacher-side strength comes from exact source-row semantics that was not
  compressed into the sheet
- anything that would require open-ended proof search

That tradeoff is intentional. Stage 1 rewards a compact offline artifact, not the largest
internal analysis stack.
