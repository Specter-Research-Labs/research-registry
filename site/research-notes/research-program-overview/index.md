---
title: "On The Point Of It All"
release: "draft"
provenance: "assistant-drafted"
toc: true
---

# Research Program Overview

Michael Levin's experimental work on basal cognition suggests that cognition is a graded, substrate-independent continuum rather than a binary property of brains. His experiments on planarian regeneration, ectopic eye induction, and synthetic organisms like Xenobots and Anthrobots show that physical systems—from ion channels to tissues to whole organisms—navigate attractor landscapes and correct against perturbations to reach their morphological goals. They do more than their default developmental script suggests.

Frameworks like the cognitive light cone—the spatiotemporal range over which a system can pursue goals—and TAME (Technological Approach to Mind Everywhere) propose that intelligence exists at every scale. Under this view, the formal tools used to describe neural computation can also describe goal-directed problem-solving in non-neural tissue. Instead of micromanaging individual cells, the goal becomes finding the right level of description to "prompt" or persuade the system toward a target morphology.

Levin provides the biological evidence and the conceptual framework: navigation in morphospace, polycomputing across nested scales, and the hypothesis that physical systems act as interfaces to a deeper space of patterns. The central question for this lab is whether that structure can be formalized. We want to provide the mathematical characterization of the spaces these systems navigate—what is the distance between two forms? What are the geodesics? Where are the barriers between attractor basins? We want to make the idea of "pattern space" precise enough that we can actually run experiments on it across different substrates.

We are a small, independent lab running this work on top of our day jobs. Because we do not have the time to manually redact every finding into a formal paper, we publish Research Notes—smaller results, methods, and framing pieces that we have LLMs help us draft from our discussions. This keeps the momentum going and lets us publish dead ends and intermediate steps without pretending every useful artifact is a finished paper.

## Morphospace Versus Platonic Space

A morphospace is a configuration space determined by a system's degrees of freedom. An attractor landscape is a dynamical object within that morphospace. Platonic space is a much stronger claim: the idea that there exists a structured space of substrate-independent patterns that physical systems interface with. Evidence about one does not automatically transfer to the others.

When a planarian regenerates its head or a Picasso tadpole corrects a scrambled face, they are moving through morphospace from a damaged configuration to a target attractor. But the geometry of these spaces is entirely unmapped. No computable morphospace currently exists where the topology, metric, and barrier structure are all formally known. This is the gap we are trying to close.

## The Experimental Stack

We are coming at this through a few small worlds we can actually perturb.

[Wonton Soup](wonton-soup-follow-up/): damage proof search, block tactics, change the provider or budget, and ask what still survives.

[Lenia](geometry-of-a-synthetic-morphospace/): a visible synthetic morphospace. It is not biology, and that is partly the point—we can see more of the machinery and ask how persistent forms, parameter moves, and hidden-state transport relate.

[Material-memory](material-memory-without-a-controller/): a physical substrate with local history-dependent updates. Can it remember anything useful?

[Categorical morphogenesis](where-tissues-break/): cutting as a typed operation on a wiring diagram. The worst cut is not always the one that removes the most connectivity; sometimes it is the one that leaves a fragment too small to sustain its pattern.

These probe worlds are smaller, inspectable versions of the Xenobot experiment. They let us see the machinery and ask how persistent forms, parameter moves, and hidden-state transport relate. We only add a new probe world if it lets us ask a question the normal setup hides.

Ultimately, we are asking if the same damage-response pattern shows up in systems that otherwise have very little in common. (See also [structural realism](from-structural-realism-to-platonic-space/).)

## The Tools

Polynomial functors model systems whose interface depends on state, while lenses model bidirectional observation and update. Sheaves help with local-to-global consistency, and fibrations give us a way to talk about implementation without pretending every level is the same thing.

The guiding mathematical overlap is:

```text
polynomial functor  ~=  dependent type  ~=  fiber of a bundle
```

This overlap is one reason the same words keep coming back in morphogenesis, proof search, and synthetic worlds.

## Computation Versus Convergence

Is a system actually computing in a counterfactual sense, or merely converging?

A ball in a bowl converges, just like a Boolean network, a tissue, or a proof search. Convergence alone is cheap; we care about what happens under intervention.

If the system recovers under perturbation, preserves a macro-family while changing micro-path, or exposes the same invariant across implementations, then there is more going on than falling downhill. If it does not, we should stop using pattern-space language for that case.

The specific patterns we look for across systems:

- Lesion-rerouting with basin preservation: block a local channel, change the path, keep the macro-outcome.
- Productive backtracking: get locally worse to do better globally.
- Basin-preserving degeneracy: many micro-trajectories land in the same functional family.

Any one of these in a single system could be a local quirk. The same pattern appearing across proof search, morphogenesis, and a physical substrate is the actual signal.
