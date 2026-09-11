---
title: "What survives a change of system?"
release: "draft"
summary: A research programme for comparing how different systems preserve, lose, and recover organization under intervention.
toc: true
bibliography: references.bib
link-citations: true
reference-section-title: References
---

# What survives a change of system?

Cells taken from a frog embryo can assemble into a swimming body that no frog ever develops. The genome has not been rewritten; the cells have been given a different setting in which to organize. Such experiments make the familiar body of an animal look less like the inevitable consequence of its genes, and more like one possibility among many [@levin2026].

Michael Levin uses these unfamiliar bodies to ask where new forms and abilities come from. In *Ingressing Minds*, he proposes that evolution and engineering give physical expression to patterns whose possibilities extend beyond any one organism. His account reaches from mathematical regularities to behavior and mind: what we build may make an existing possibility accessible, much as a mathematical construction reveals properties we did not choose [@levin2026].

For SPECTER, the attraction is that discovery need not end with another surprising example. We can search systematically for forms, change the conditions that sustain them, and ask which relationships keep reappearing. The ambition is to learn enough about those relationships to predict a body's behavior, recover a rule from a desired form, or recognize the same capacity in an unfamiliar implementation.

## Exploring what a system can become

Levin's work on diverse intelligence suggests a practical way to begin: investigate what a system can accomplish and how it responds when its usual way of accomplishing it is disrupted [@levin2022]. In biology, this brings development and regeneration into the study of intelligence. It also gives us questions to ask of systems whose possibilities are much less familiar.

Our computational experiments let us change the conditions of an encounter and follow what happens next. A body may keep moving after a disturbance yet lose the organization that previously held it together. Another may recover its shape but take a different path. Understanding that difference could tell us which capacities depend on a particular body and which can be realized in other forms.

The prospect of finding such relationships motivates our interest in a structured space of possible patterns. We approach it through experiments small enough to inspect: how a body maintains itself, which changes alter its future, and whether a description learned in one setting helps us anticipate another.

## Experiments in form and possibility

### Which proof alternatives are usable?

[Wonton Soup](/dossiers/wonton-soup/) blocks tactics in Lean proof search and records the new search paths. The theorem remains fixed; the prover has the same budget but fewer available actions. Some runs still solve, sometimes with a different proof structure. Others fail within the budget.

The [controlled study](/research-notes/2026-06-10-taking-away-one-move-revealed-proof-alternatives/) tested an appealing prediction: theorems with more observed proof structures should be easier to solve after a tactic is blocked. The observed correlation was only 0.03. Counting proof variants did not reveal which dependencies they shared. The next useful description should distinguish alternative routes that use different resources from cosmetic variants of one route.

### What does a shape conceal?

[Flow Lenia](/dossiers/lenia-swarm/) lets us inspect the fields, initial conditions and update rules behind each simulated body. We can measure its shape, replay its development and change one part of the experiment while retaining the rest.

The [morphospace comparison](/dossiers/lenia-swarm/morphospace/) puts Lenia patterns, EmbryoMaker snapshots and fish landmark configurations into twelve shared shape measurements. It also shows the cost of that common description: closeness in the shared measurements need not mean closeness in a system's native description. The fish-near group gave us a concrete lead, but its five densely checked cases did not survive both loop-transport controls.

The next question is whether a body's shape helps predict its response to an obstacle. Existing shape/activity and shape/locomotion comparisons provide a starting point. The new test should compare predictions based on shape alone with predictions that also use rule parameters, on the same held-out bodies. A particularly informative failure would be similar-looking bodies responding differently in a way that their generating rules explain.

### What does composition let us calculate?

The [poly-morphogenesis study](https://github.com/Specter-Research-Labs/research-registry/tree/main/addenda/poly-morphogenesis#current-result) expresses a reaction–diffusion system through cells and their connections, building on Grodstein, McMillen and Levin's closed-loop model [@grodstein2023]. Removing connections can separate the equations into independently simulated components. That formal decomposition is distinct from predicting which altered arrangement produces the largest change in the final pattern.

The earlier tissue drafts blurred those tasks. The implementation audit distinguishes altered wiring from initialization, intervention on a settled pattern, and retrospective scoring of outcomes. The proposed biological extension—predicting how a living tissue responds to disrupted coupling—requires evidence beyond those simulations.

A useful test for the compositional method is whether it computes the same outcome as the full coupled simulation with less work, and whether a ranking formed before the outcomes are opened predicts them. Category theory supplies a language for the construction; the experiments must establish its practical benefit.

### A paused material-memory pilot

The [Jolt pilot](/dossiers/jolt-material-memory/) tested history-dependent updates in rigid-body assemblies. Some configurations retained a displacement, but the tested memory rules impaired damage recovery, and a positive comparison changed sign under a different layout. It remains a small, paused investigation. It does not establish adaptive recovery or a common mechanism with the other systems.

## What would count as a shared pattern?

A morphospace describes forms through selected coordinates. A dynamical state space contains the variables needed to evolve the system. A parameter space describes the rules or configurations we vary. These spaces are related, but a point in one is not automatically a point in another. Collapsing them would conceal exactly the differences we want to investigate.

<figure class="morphospace-figure wide">
<img src="../../assets/blog/research-program-overview/fig-kinds-of-spaces.svg" alt="Conceptual diagram separating system configurations, mathematical models and a proposed ambient pattern space." />
<figcaption>A philosophical schema, not a measured map. The proposed step from a successful model to an embodiment-independent pattern requires an argument beyond fitting the observations.</figcaption>
</figure>

We can make progress without settling the ontology. Choose a candidate relationship in one system, specify a correspondence to a second, and predict what an intervention should do there. Then change the measurement or representation and check whether the relationship persists. Failure may reveal a poor correspondence, a measurement artifact, or a genuinely system-specific mechanism.

One candidate is **the dependence of recovery on distinct available routes**. Wonton's negative result warns us that counting alternatives is insufficient: they may all depend on the same tactic. In Lenia, a variety of visible forms may likewise conceal a narrow set of sustaining dynamics. That analogy suggests a test, not a result: does a description of independent dynamical possibilities predict response better than the diversity of observed outcomes?

A second candidate concerns **the difference between retention and recoverability**. A state can become harder to disturb without becoming better at returning after a large disturbance. The Lenia developmental experiments and the Jolt pilot make that distinction worth measuring separately. They do not yet establish one law governing both.

## Finding relationships we can use

Polynomial functors describe state-dependent interfaces and their composition [@niu2024]; persistent homology describes topological features across distance scales [@edelsbrunner2002]. Both are useful only when we specify the objects, maps and measurements involved. A loop in a sampled shape cloud is not proof that the enclosed forms are impossible. A factorization of equations is not evidence that a tissue has goals.

The broader conjecture is that some relationships will survive changes in material, representation and scale. To earn that claim, we need a prediction that travels between systems with few adjustable assumptions and outperforms a simpler system-specific explanation. That is the work a catalogue of forms, a controlled intervention and a reproducible trace can begin to support.

The companion [note on structural realism](/research-notes/from-structural-realism-to-platonic-space/) develops the philosophical question this leaves open: what would a successful prediction across different embodiments tell us about the reality of the pattern itself?

