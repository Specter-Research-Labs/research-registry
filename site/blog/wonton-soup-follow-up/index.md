---
release: "draft"
---

# Wonton Soup Follow-Up

Blocking a tactic does not split proof search into “damage” and “help.” Sometimes the prover reroutes through a different successful proof, sometimes it loses the route entirely, and sometimes it changes tactics while staying in the same proof family. That third case is why solved/failed is too crude a summary.

The follow-up compares providers, blocked-tactic responses, and distributed-MCTS schedules over the same intervention machinery. The detailed run counts and tables are in the [research note](../../research-notes/wonton-soup-follow-up/): most apparent provider convergence came from trivial one-step proofs; the multi-step cases show the structural differences.

![Paired-panel intervention taxonomy](../../assets/blog/wonton-soup-follow-up/fig16-followup-taxonomy.png)

In the distributed sweep, blocking `simp` or `rw` killed every observed proof, while blocking `left`, `push_neg`, or `contrapose!` was fully survivable. The reroute separates indispensable local channels from bypassable ones, and distinguishes a genuinely different route from a text-level variation.

![Provider-specific intervention outcomes on the paired panel](../../assets/blog/wonton-soup-follow-up/fig17-followup-provider-splits.png)

The current comparison is still narrow. `reprover` and `deepseek` have similar solve rates on the measured slice, but DeepSeek interventions move the proof graph more often. That is a lead for targeted multi-step comparisons, not a general statement about either provider.

![Basin multistability versus blind-relative gain](../../assets/blog/wonton-soup-follow-up/fig18-followup-basins.png)

For the underlying measurements and corpus boundaries, see [Wonton Soup: Proof Structures Under Interventions](../wonton-soup/) and the [follow-up receipt](../../research-notes/wonton-soup-follow-up/).
