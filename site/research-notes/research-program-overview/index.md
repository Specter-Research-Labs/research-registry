---
title: "Research Program Overview"
release: "draft"
provenance: "assistant-drafted"
toc: true
---

# Research Program Overview

<!-- release-target: 2026-04-29. -->

Can we make the idea of "pattern space" precise enough that we can actually run experiments on it?

Levin's work is one major reference point because bodies and bioelectric networks often do more than their default developmental script suggests. The thing we want to avoid is just admiring that from a distance. If "pattern space" is going to mean anything for us, it has to cash out in experiments.

## Why Research Notes

We are two people working on this on top of our jobs. We push the engineering and the research quality hard, but fully redacting a paper takes real time. Research Notes give us a place to publish smaller results, methods, and framing pieces without pretending every useful artifact is already a finished paper. A note can later become a stronger article, become part of a research paper, or remain a dead end we keep around because the dead end was informative.

## The Experimental Stack

We are coming at this through a few small worlds we can actually perturb.

[Wonton Soup](wonton-soup-follow-up/): damage proof search, block tactics, change the provider or budget, and ask what still survives.

[Lenia](geometry-of-a-synthetic-morphospace/): a visible synthetic morphospace. It is not biology, and that is partly the point—we can see more of the machinery and ask how persistent forms, parameter moves, and hidden-state transport relate.

[Material-memory](material-memory-without-a-controller/): a physical substrate with local history-dependent updates. Can it remember anything useful?

[Categorical morphogenesis](where-tissues-break/): cutting as a typed operation on a wiring diagram. The worst cut is not always the one that removes the most connectivity; sometimes it is the one that leaves a fragment too small to sustain its pattern.

Cross-dossier synthesis: does the same damage-response pattern show up in systems that otherwise have very little in common? The first test is lesion-rerouting with basin preservation—block a local channel, change the path, keep the macro-outcome. (See also [structural realism](from-structural-realism-to-platonic-space/).)

This is not just a lab conceit. Xenobots and Anthrobots already show that the same cellular material produces radically different behaviors depending on context—the default body hides part of the repertoire. Our probe worlds are smaller, more inspectable versions of that experiment.

A weird body or tiny proof world is only worth adding if it lets us ask a question the normal setup hides. If a later probe note has its own result, it can split out.

## The Tools

The formal tools have to do actual work, not just decorate the prose.

Polynomial functors model systems whose interface depends on state, while lenses model bidirectional observation and update. Sheaves help with local-to-global consistency, and fibrations give us a way to talk about implementation without pretending every level is the same thing.

The guiding mathematical overlap is:

```text
polynomial functor  ~=  dependent type  ~=  fiber of a bundle
```

This overlap is one reason the same words keep coming back in morphogenesis, proof search, and synthetic worlds.

## Computation Versus Convergence

The question I keep coming back to is whether a system is actually computing in a counterfactual sense, or merely converging.

Lots of things converge. A ball in a bowl converges, and so can a Boolean network, a tissue, or a proof search; convergence alone is cheap, so the question is what happens under intervention.

If the system recovers under perturbation, preserves a macro-family while changing micro-path, or exposes the same invariant across implementations, then there is more going on than falling downhill. If it does not, we should stop using pattern-space language for that case.

The specific patterns we look for across systems:

- Lesion-rerouting with basin preservation: block a local channel, change the path, keep the macro-outcome.
- Productive backtracking: get locally worse to do better globally.
- Basin-preserving degeneracy: many micro-trajectories land in the same functional family.

Any one of these in a single system is unremarkable. The same pattern appearing across proof search, morphogenesis, and a physical substrate starts to mean something.

## The Caution

Configuration spaces, model spaces, attractor landscapes, and the stronger pattern-space hypothesis are related, not interchangeable. Evidence about one does not automatically transfer to the others.

Recurring organization may be real in a structural-realist sense, and we can investigate it with formal tools and controlled systems. Platonic space is the bigger bet, not the thing we have already earned.
