---
title: "Taking away one move revealed which proofs had alternatives"
release: "published"
provenance: "assistant-drafted"
source_id: "D-002"
toc: true
---

# Taking away one move revealed which proofs had alternatives

_21 May–10 June 2026 · Retrospective intervention analysis of completed Wonton runs._

Repeated proof searches had already shown that one theorem could have several valid proofs. The harder question was whether those alternatives were actually available when the familiar route was damaged. We tested that by taking a tactic used in a successful Lean proof, blocking it, and giving the prover the same budget to find another way through.

Across the completed cohort, the unperturbed prover had solved 1,064 theorem-runs. Once a tactic was blocked, 367 still solved and 697 failed. Those totals alone were not enough, because a difficult theorem might also fail when nothing meaningful had changed. The main comparison therefore required both the original run and a matched inert-control rerun to solve before treating the tactic block as causal evidence.

Within that stricter comparison, 330 blocked runs still reached the theorem. Ninety-six of them—29.1 per cent—finished in a different proof family from the control. Search traces detected a non-zero structural difference in 187 cases, so even some proofs with the same final family had travelled through different intermediate states. These were genuine detours rather than simple repetitions.

The tactic being removed mattered enormously. Blocking `simp`, `apply` or `intros` often left another route available. Blocking rewriting or arithmetic tactics such as `rw`, `linarith` and `norm_num` usually did not. One arithmetic theorem made the contrast especially clear: ReProver solved all sixteen unblocked seeds and none of the sixteen runs in which `linarith` was forbidden. DeepSeek showed the same collapse in the smaller set of runs for which control and intervention results could be compared directly. In this theorem, `linarith` was carrying essential proof work: neither prover found a substitute within the budget.

Other dependencies belonged to the prover rather than the theorem. Blocking `cases` destroyed every ReProver attempt on one list theorem, while the heuristic prover solved all sixteen corresponding runs. The experiment could therefore distinguish a generally load-bearing proof resource from a habit peculiar to one search system.

We had expected theorems with many observed proof shapes to survive damage more easily. That prediction failed. Among the theorem-provider groups that supported the controlled comparison, the correlation between the number of observed proof structures and recovery was 0.03. A theorem can have many superficial variants that all depend on the same indispensable tactic, while a theorem with only a few known proofs may have routes that use genuinely different resources.

The intervention changed the question from “How many proofs have we seen?” to “What does each proof depend on?” Diversity in the final proof term is not the same thing as resilience. A proof search becomes robust only when its alternatives remain alternatives after one of its usual tools has been taken away.
