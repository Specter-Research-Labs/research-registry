---
title: "When an inert control refused to stay inert"
release: "published"
provenance: "assistant-drafted"
source_id: "D-002"
toc: true
---

# When an inert control refused to stay inert

_2 April 2026 · Experimental diagnosis. The resulting inference and seeding repair landed in the same release period._

We were trying to learn how a theorem prover’s search changes when one of its tactics is taken away. The control should have been uneventful: disable a tactic the prover never uses, rerun the theorem, and confirm that nothing changes. ReProver passed these control reruns consistently, whereas some DeepSeek theorems changed outcome even though the intervention was supposed to be inert.

That failure made the rest of the DeepSeek comparison impossible to interpret. If removing an unused tactic could change the result, then a changed result after removing an important tactic did not necessarily tell us anything about that tactic. The experiment was mixing up two causes: the intervention we intended to study and ordinary variation between calls to the local inference service.

The flag named `deterministic_inference` had made this easy to miss. It fixed the random seed used by Monte Carlo tree search, but the search still depended on stochastic samples from our DeepSeek server on the QuietBox, and repeated calls did not return identical tactics.

Difficult theorems made more model calls, giving small differences more chances to alter the search. Earlier DeepSeek campaigns had mostly run without paired controls, so there had been no clean baseline to expose this variation.

For Wonton, inference reproducibility therefore has to be tested as part of the experiment. In a system that combines a locally seeded search with a local model server, fixing the search seed is not enough. A tactic intervention can support a causal interpretation only after the supposedly inactive controls have been shown to remain inactive for that model and serving configuration.
