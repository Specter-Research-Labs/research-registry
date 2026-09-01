---
title: "One theorem, several proofs"
release: "published"
provenance: "assistant-drafted"
source_id: "D-002"
toc: true
---

# One theorem, several proofs

_25 May 2026 · Retrospective analysis of existing Wonton runs; no new theorem campaign was needed._

A theorem prover can arrive at the same correct answer by more than one route. We wanted to know how often that actually happened in Wonton, and whether the variation resembled a familiar idea from biology: different developmental histories producing the same visible outcome.

There are two distinct versions of that question. Search paths might separate and later meet at the same unfinished proof state, after which they share the rest of the journey. Or they might never meet at all, yet still finish with different proof terms for the same theorem. The first kind of convergence turned out to be rare—about one per cent of the trees we inspected. These searches were generally short enough that diverging branches had little opportunity to meet again before the theorem was solved.

The second kind was much more common. Among repeated successful searches, between 12 and 33 per cent produced a structurally different final proof, depending on how much of the search setup had been allowed to vary. Each run established the same theorem, but the prover did so by constructing a different proof term.

That distinction also sets a precise limit on the biological analogy. The theorem is the shared outcome; each proof term is one concrete way of reaching it. We did not show that every intermediate state has a rich collection of interchangeable routes, and the 12 per cent result under fixed conditions still includes residual sampling variation. What we can say is that agreement on the theorem concealed substantial diversity in the proofs that produced it.

