# Public Benchmark Notes

Current findings as of 2026-03-15 from the addendum pipeline.

Use `docs/approach.md` for the method overview. Serves as the detailed metric/reference companion.

## Public Labels Match The Graph

- Public set size: `1200`
- Public label agreement with `graph.json`: `1200/1200`
- Public statuses are proof-only: every public status byte is in `{2, 3, 6, 7}`
- Public status mix:
  - `explicit_proof_false`: `34`
  - `explicit_proof_true`: `1`
  - `implicit_proof_false`: `592`
  - `implicit_proof_true`: `573`

The public benchmark is not just adjacent to the Equational Theories implication graph. It is
exactly recoverable from that graph.

## Small Countermodels Explain Most FALSE Cases

Greedy cover over all `2`-element magmas covers `454/626` public false problems with six operations:

- `constant_0` (`0000`): `172`
- `right_projection` (`0101`): `126`
- `left_projection` (`0011`): `98`
- `xor` (`0110`): `45`
- `not_left` (`1100`): `8`
- `not_right` (`1010`): `5`

This is the strongest compact false-side signal.

If we shift from the old greedy witness battery to the full fixed `10`-theory `2`-element
pair-evaluator basis, false coverage improves to `467/626`. So the full representative basis adds
`13` public false decisions beyond the old six-table battery and is the better offline evaluator.

Brute-force search over all `19683` binary operations on the `3`-element carrier adds another
`84` false problems from the `172` missed by the `2`-element battery, leaving `88` still
unexplained.

Most frequent `3`-element witness tables so far:

- `000000001`: `10`
- `000002222`: `8`
- `000000010`: `6`
- `021210102`: `6`

An explicit SAT search for `4`-element countermodels, with a `1000 ms` timeout per residual
problem, adds another `51` false problems from the `88` missed after the `3`-element pass.
That leaves only `37` public false problems unexplained.

Unique-pair status split at size `4`:

- `20` `sat`
- `16` `unsat`
- `1` `unknown`

An explicit SAT search for `5`-element countermodels, again with a `1000 ms` timeout per
residual problem, adds another `16` false problems from the `37` missed after the `4`-element
pass. That leaves only `21` public false problems unexplained.

Unique-pair status split at size `5`:

- `7` `sat`
- `3` `unsat`
- `7` `unknown`

Combined false-side coverage:

- `2`-element battery: `454/626`
- `3`-element exhaustive search: `84/172` residual
- `4`-element SAT search: `51/88` residual
- `5`-element SAT search: `16/37` residual
- total explained false cases: `605/626` (`96.6%`)

Pushing the remaining `21` cases to a `3000 ms` timeout at size `5` did not add any new
witnesses, so the current bottleneck is not just per-instance timeout.

The expensive residual searches are now deduped by exact `(equation1_id, equation2_id)` pair:

- the `172` false cases missed by the `2`-element battery collapse to `100` unique pairs over
  `93` unique sources
- the `88` cases missed after the `3`-element pass collapse to `37` unique pairs over `33`
  unique sources
- the `37` cases missed after the `4`-element pass collapse to `17` unique pairs over `16`
  unique sources
- the final `21` residual false cases are only `10` unique pairs over `9` unique sources

Canonicalizing the `7` size-`5` `unknown` residual pairs to the smallest mutually implied source
and target laws already helps, but less than the earlier unstable rerun suggested:

- `1286 -> 2891` reduces to `1286 -> 2079`
- `2656 -> 2863` reduces to `2055 -> 2863`
- `2805 -> 3891` reduces to `1587 -> 3891`
- `2994 -> 2623` reduces to `2994 -> 242`
- rerunning size-`5` SAT on those canonical pairs changes `1` case from `unknown` to `unsat`
- the canonical followup status split is now `6 unknown / 1 unsat`

## Two Full-Graph Source Families Give The Main TRUE Rules

Across the full `4694`-law universe:

- laws of the form `x = t` where `x` is absent from `t`: `816/816` imply every target law
- laws of the form `x = t` where every occurrence of `x` is on a mixed path, some other
  variable appears exactly once in `t`, and the x-path set does not contain both exact `LR` and
  `RL`: `680/680` imply every target law
- laws of the form `x = t` where the leftmost leaf of `t` is still `x`: `0/816` imply every target law
- laws of the form `x = t` where `x` occurs exactly once and is not leftmost: `504/924` imply every target law

The first two lines are the cleanest true-side invariants in the current stack.

## Theorem Rules Cover Most Public TRUE Cases

The theorem-backed TRUE side carries most of the public TRUE cases:

- collapse rule: `243/574` public true problems
- mixed-self-reference-with-singleton rule: `188/574`
- direct substitution-instance rule: `5/574`
- one-hole context closure over substitution: `6/574`
- combined theorem-backed cover: `433/574` (`75.4%`)

The remaining theorem-uncovered true region is `141` public problems.

## Source-Row Semantics Explain Most Of The Remaining TRUE Mass

The main shift here is that the dominant middle is source-row semantics, not another
thin source feature family.

Over the `10` distinct `2`-element theory classes induced by the `16` binary operations:

- `2407/4694` source laws have a full implication row that is exactly the intersection of the
  `2`-element theories satisfying that source
- this is exact for `669/1200` public problems
- the exact public split is `558` true and `111` false
- among the `141` theorem-uncovered public true cases, the exact source-row classifier explains
  `126`

The highest-yield exact source fingerprints on the public set are:

- `constant`: `92` public problems, `48` true, `47` from the current theorem-uncovered true tail
- `right_projection`: `39` public problems, `30` true, `30` from the current theorem-uncovered true tail
- `left_projection`: `36` public problems, `29` true, `29` from the current theorem-uncovered true tail
- `not_right + right_projection`: `32` public problems, `13` true, `13` from the current
  theorem-uncovered true tail
- `left_projection + not_left`: `18` public problems, `6` true, `6` from the current
  theorem-uncovered true tail
- empty fingerprint is real but not automatically TRUE; it only works when paired with a proved
  collapse theorem

## Raw Fingerprints Collide Too Much To Ship Directly

The raw `2`-element source fingerprint is helpful, but it is not close to a unique identifier for
the full implication row:

- there are `182` distinct fingerprint buckets over the full `4694`-law universe
- only `51` buckets have a single row signature
- `131` buckets are internally divergent
- only `51` laws live in single-row buckets; the other `4643` laws live in divergent buckets

The worst collisions are exactly where the current residual mass lives:

- empty fingerprint bucket: `1558` laws split across `1125` distinct rows
- `constant`: `671` laws split across `579` rows
- `left_projection`: `220` laws split across `199` rows
- `right_projection`: `220` laws split across `195` rows
- `xor_xnor`: `182` laws split across `179` rows

The lesson is straightforward:

- exact source-row semantics is real and high-yield
- raw fingerprint labels alone are too coarse to be the final evaluator
- the remaining Stage 1 work is mostly about the non-exact collision region

## The Proof Layer Is Now Explicit

The proof layer is now explicitly cataloged instead of graph-mined at review time.

After the exact public count `1164/1200`, the shipped constructive extension is:

1. an exact source-triggered kernel catalog with `10` explicit source patterns
2. two exact source-triggered commutativity repairs

The kernel catalog explains:

- `13/15` current residual public true problems
- `10/12` current residual unique true pairs

That raises the constructive candidate count from `1164/1200` to `1177/1200`, leaving only:

- `2` unresolved public true cases
- `21` unresolved public false cases

The two remaining true cases are closed by two explicit commutativity repairs:

- `711 -> 3567`:
  - source trigger: `x = y * (y * ((x * z) * z))`
  - base kernel: `x * y = y * ((x * z) * z)`
  - helper: `x * y = y * x`
  - one local flip yields `x * y = y * ((z * x) * z)`
- `2170 -> 4640`:
  - source trigger: `x = ((y * z) * x) * (z * y)`
  - base kernel: `x * (x * y) = (y * z) * z`
  - helper: `x * y = y * x`
  - one local flip yields `(x * y) * x = (y * z) * z`
- the commutativity repairs cover `2/2` residual true cases after the direct-kernel catalog
- the constructive candidate count therefore moves from `1177/1200` to `1179/1200`

So the public true-side residual is closed by a finite constructive catalog. The remaining public
tail is purely false-side.

## The Remaining Tail Is Small And Structured

After theorem-backed TRUE families, exact source rows, and the explicit false witness stack, the
exact public-decision tail is still `36` problems:

- `15` unresolved true
- `21` unresolved false

The unresolved true cases before the kernel proof layer were concentrated in a few source
fingerprints:

- `xor_xnor`: `7`
- `right_projection`: `3`
- `constant`: `3`
- `not_left_and_right_left_implies_right + right_projection`: `1`
- `left_projection + not_left`: `1`

The unresolved false cases are even more concentrated:

- empty fingerprint: `9`
- `xor_xnor`: `5`
- `right_projection`: `4`
- `left_projection`: `3`

By unique pair, the false tail is only `10` source-target pairs over `9` unique source laws.

## What The Full Stack Decides On The Public Set

If we stack:

- theorem-backed TRUE families
- exact `2`-element source-row semantics
- explicit false witnesses from the finite-model search stack

then the current public decision count is:

- `1164/1200` exact decisions
- `15` unresolved public true cases
- `21` unresolved public false cases

If we then add the current explicit source-triggered kernel catalog, the constructive count moves
to:

- `1177/1200` candidate decisions
- `2` unresolved public true cases
- `21` unresolved public false cases

If we add the two explicit commutativity repairs on top of that catalog, the constructive
candidate count moves again to:

- `1179/1200` candidate decisions
- `0` unresolved public true cases
- `21` unresolved public false cases

## Public-Only Candidate Rules Still Stay Hypotheses

These are public-set patterns only. They are useful for triage, but they are not theorem-backed
and remain hypotheses:

- non-collapse TRUE candidate: `source_more_vars + target_more_ops + target_two_vars` is `17/17`
- non-collapse FALSE candidate: `source_more_repetition + source_two_vars` is `0/116`
- non-collapse FALSE candidate: `same_operation_count + source_two_vars` is `0/115`

Full-graph validation says these public-perfect rules do not generalize cleanly:

- `source_more_vars + target_more_ops + target_two_vars` drops to `0.3999` true-rate on the full graph
- `source_more_repetition + source_two_vars` stays extremely false-biased at `0.0026` true-rate
- `same_operation_count + source_two_vars` stays extremely false-biased at `0.0033` true-rate

## Frozen Submission Artifact

See [cheatsheet-v0.txt](cheatsheet-v0.txt).
