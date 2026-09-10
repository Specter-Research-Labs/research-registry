---
title: "The Geometry of a Synthetic Morphospace"
release: "draft"
summary: Flow Lenia as an inspectable synthetic morphospace for making Levin-style morphospace questions computational, then comparing the result with EmbryoMaker morphology snapshots and Dryad fish landmark measurements.
toc: true
---

# The Geometry of a Synthetic Morphospace

*Earlier draft. The current account is [How much does shape explain?](/dossiers/lenia-swarm/morphospace/). This draft preserves the earlier theoretical framing and is not a separate set of findings.*


A shape measurement omits most of the process that produced the shape. For a Flow Lenia specimen, we can inspect those omitted variables: its rule parameters, initial field and subsequent dynamics. This makes a concrete question possible. If we return to the same measured shape after a sequence of small rule changes, do we also return to the starting rule?

[Lenia](https://arxiv.org/abs/1812.05433) produces persistent patterns through local updates to a concentration field. Flow Lenia conserves and transports matter rather than creating and removing it through the basic Lenia growth update. A persistent body can move while its local concentrations continually change. Knowing the update rule lets us replay the process and test a controlled alteration, although a complete replay also requires its initial state and numerical settings.

A morphospace places forms in coordinates defined by chosen measurements. We compared Flow Lenia with EmbryoMaker simulation snapshots and fish landmark configurations through twelve shared descriptors. That common language makes otherwise different records comparable, while discarding much of their native information. The fiber vocabulary used below describes rule settings associated with a measured form; it does not establish a correspondence with an embryo's biological control mechanisms.

Two questions organize the earlier analysis. First, how do the sampled forms compare in the common measurements? Second, when numerical transport follows a closed path through measured shapes, does the rule adjustment close too? A return in descriptor coordinates need not reproduce the full visible body. The result also depends on the transport procedure and must be compared with retraced-path controls.

## The Map

At the center is the genotype-to-phenotype map $\pi$.

- **Genotype:** the Flow Lenia rule parameters (channels, kernels, growth functions, channel coupling weights, etc.).
- **Phenotype:** the measured morphology and motion of a specimen (extent, elongation, compactness, symmetry, components, transport, etc.).
- **Projection $\pi$:** fix the initial condition and numerical settings, run the simulation, then measure the terminal or trajectory-level phenotype.
- **Fiber over a phenotype:** the set of genotypes that land near the same measured morphology.

Three things over the fiber are worth naming:

- **Section:** given a target phenotype, find a genotype that produces it when you run the simulation. The inverse-design problem.
- **Connection:** for a small intended change to the phenotype, the genotype adjustment that delivers it, found by running the simulation forward and checking.
- **Holonomy:** pick a small sequence of target phenotypes that starts and ends at the same point. For each step, find the genotype adjustment that lands on the next target. After completing the sequence, compare the final genotype to the starting one. If they differ, the phenotype loop did not close in genotype space.

Holonomy is the one we actually run in this report. The other two come up later. A residual rule difference is a candidate sign of information omitted by the descriptor. Retrace controls and scale tests ask whether it exceeds the numerical procedure's own closure error. “Fiber” and “connection” here describe the computational construction; they do not prove that the sampled map is a smooth fiber bundle.

<figure class="morphospace-figure wide">
<img src="../../assets/blog/lenia-morphospace-report/fig-fiber-bundle.svg" alt="Fiber bundle schematic showing a phenotype base space, genotype fibers, and a projection." />
<figcaption>Flow Lenia has a concrete genotype-to-phenotype map. The fiber over a phenotype is the set of parameterizations that produce similar measured forms.</figcaption>
</figure>

## The Corpus

The May 19 common-morphology comparison ran over four cohorts:

| Cohort | Count | Role |
|---|---:|---|
| Flow Lenia, broad comparison cohort | 25,167 | full synthetic morphospace spanning multiple rule families |
| Flow Lenia, single rule-family slice | 8,192 | clean internal control, small enough for exact persistent homology |
| [EmbryoMaker morphology snapshots](https://github.com/HugoCanoFernandez/Morphospace_exploration_EMaker) | 859 | developmental morphospace comparison |
| [Dryad fish landmark measurements](https://datadryad.org/dataset/doi:10.5061/dryad.n2z34tn2t) | 232 | biological shape comparison |

Every specimen carries the same 12 normalized morphology descriptors, and the distance and topology pipelines run identically across the three clouds. The comparison is no longer just a gallery, since the same metric and the same persistence computation give comparable numbers across Lenia, EmbryoMaker, and the fish.

## Loop Structure

Persistent homology follows connected components and loops as the distance used to join neighbouring observations increases. A long-lived loop identifies a gap that persists across distance scales in this sample. Its persistence is not proof that the missing forms are impossible, and a short-lived loop is not automatically noise. Sampling density, the distance metric and the representation all affect the result.

All three clouds contain closed loops, with the same pipeline finding 297 in the [EmbryoMaker morphology snapshots](https://github.com/HugoCanoFernandez/Morphospace_exploration_EMaker) and 66 in the [Dryad fish landmark configurations](https://datadryad.org/dataset/doi:10.5061/dryad.n2z34tn2t), so the presence of loop structure is not a Lenia artifact. What separates the substrates is how long the loops hold up under widening: the longest Lenia loop stays visible across roughly four times the widening of the longest fish loop and almost ten times the longest in EmbryoMaker (top $H_1$ persistence 2.78, against 0.64 and 0.29). That headroom is what lets us walk along a Lenia loop and watch what the rule layer is doing without the descriptor signal washing out by the second step.

The single-family 8,192-specimen cohort has a longest-loop persistence of 0.80 under the recorded analysis, compared with 2.78 in the broad Lenia sample. That comparison changes sample size and rule-family coverage together. It does not isolate their effects or rule out sampling explanations for differences between cohorts.

<figure class="morphospace-figure wide">
<img src="../../assets/blog/lenia-morphospace-report/fig-persistence.svg?v=axis-20260520" alt="Persistence barcode schematic for H0 and H1 features." />
<figcaption>Each bar tracks one feature in the morphology cloud (a connected component or a loop) across distance scales. Long bars are features that survive as you zoom out; short bars vanish almost immediately.</figcaption>
</figure>

## Biological Distance

Two questions. How close does the broad Lenia cloud sit to the [EmbryoMaker morphology snapshots](https://github.com/HugoCanoFernandez/Morphospace_exploration_EMaker) and to the [Dryad fish landmark configurations](https://datadryad.org/dataset/doi:10.5061/dryad.n2z34tn2t)? And is that closeness uniform across the 25,167 Lenia specimens, or are there pockets that lean one direction more than others?

A visually selected resemblance would be weak evidence. The more specific comparison asks whether a group selected from Lenia's own measured geometry, before reference to either external collection, is closer to one external collection than the full Lenia sample is.

On average, the distances are unsurprising. The typical EmbryoMaker snapshot has a Lenia neighbor within about two units of normalized descriptor distance (median 1.91), and the typical fish landmark configuration within about three and a half (median 3.39). Read from the other side the medians are larger (4.46 to EmbryoMaker, 5.90 to fish), because nearest-neighbour distances are directional and depend on the sizes and distributions of both collections. Taken as a whole, Lenia ends up looking more cell-aggregate-shaped than fish-shaped, which is what we expected from the rule families we sampled.

One 256-specimen patch in the Lenia cloud, defined as a single $H_1$ neighborhood in the cloud's own descriptor geometry and identified without reference to the biological data, runs the global pattern in reverse. Inside the patch, the median Lenia-to-fish distance is roughly half what it is across the broader cloud (3.30 versus 5.90), and the median Lenia-to-EmbryoMaker distance is almost three times larger (11.98 versus 4.46). A composite bridge score (Lenia-to-fish distance minus Lenia-to-EmbryoMaker distance, so negative means closer to fish than to embryos) swings from a global mean of $+0.6$ to a local mean of $-8.2$ across the patch, which is a reversal of the group mean, not a claim that every one of the 256 specimens reverses, and the recorded permutation comparison gave a p-value of roughly 0.001 for the fish tilt under its specified null. The top transport witnesses inside the patch replay as elongated, directional, streak-shaped creatures rather than the radially symmetric blobs that dominate the rest of the cloud:

<figure class="morphospace-figure wide">
<iframe src="../../assets/blog/lenia-morphospace-report/fig-fish-near-witnesses.html?v=fish-near-20260524" title="Six specimens from the 256-member fish-near patch, replayed as autoplaying loops." style="width: 100%; height: 760px; border: 1px solid rgba(11,14,20,0.10); background: #ffffff;" loading="lazy"></iframe>
</figure>

The same group also showed elevated rule-transport residue in the initial analysis: its 32 matched transport groups averaged about five times the global residue. The recorded stratified permutation comparison was approximately 0.0005. This motivated a follow-up; it did not make the two measurements statistically independent or establish a biological mechanism. Crucially, none of the five densely retested fish-near groups passed both joint controls.

## Transport Residue

flow-map-elite-38-4984EC16 walks a closed loop in phenotype space. It returns to within $7.7 \times 10^{-5}$ of where it started, in the normalized descriptor coordinates. An absolute coordinate difference is not a percentage without a specified denominator. Across that same loop, its rule parameters do not return. The matched control is an axis-retrace: the same walk played out and then back along its own path, which should close exactly. Against that baseline the closed loop leaves about 2.8% more mass residue on average, and at its widest scale its closure ratio runs 150% of the retrace control's. The descriptor came back. The rule did not.

The example tests what the descriptor omits under this transport procedure. Ending near the same measured form with different rule parameters demonstrates non-uniqueness only to the extent that the controls exclude numerical closure error. The residue does not quantify all information discarded by the descriptor, and it does not show that the external fish or EmbryoMaker studies assumed identical dynamics for similar forms.

At the cohort level this is a tail effect, not a population effect. Of 4,802 flow-supported transport groups, 109 (about 2.3 percent) pass a strict positive-surplus criterion at small, medium, and wide rectangle scales for both state closure and ratio. Under scale permutation, the joint state-and-ratio criterion is marginal (p around 0.094); the single-metric tails are clear (p around 0.0002 for ratio only, 0.008 for state only). In the broad top-five dense rerun, flow-map-elite-38 above was the only specimen that survived both joint controls. In the fish-near localized dense rerun, none of the five checked groups survived both, though one survived by state only and one by ratio only.

The result is uneven: the single-metric tails were stronger than the joint criterion, one broad-cohort specimen survived the dense joint checks, and the fish-near follow-up did not. The current report presents those distinctions together rather than treating the initial local enrichment as a confirmed transport effect.

<figure class="morphospace-figure wide">
<img src="../../assets/blog/lenia-morphospace-report/fig-holonomy-schematic.svg?v=transport-20260520" alt="Schematic loop transport experiment for holonomy." />
<figcaption>A closed loop in phenotype space, walked step by step in parameter space. If the parameter state does not return to where it started, the gap is the transport residue we want to measure.</figcaption>
</figure>

## What the earlier result led to

Discovery and measurement serve different purposes. A gallery can select coherent, visually legible movers; a morphology analysis must retain the cohort selected by its stated sampling procedure, including less attractive fragmented patterns. The coherent bodies in the later obstacle experiment are a separate cohort from the fish-near group.

The next comparison asks whether shape predicts response. A body can retain matter while losing organization, and a heading change need not mean turning away from an obstacle. Progress, turning, connected-body coherence and recovery therefore need separate measurements.

The [current report](/dossiers/lenia-swarm/morphospace/) links the [five-body obstacle assay](/dossiers/lenia-swarm/morphospace/obstacle-response/) and states what it has not yet tested. The broader experiment would fit predictions from shape alone and from shape plus rule parameters, then compare both on the same held-out bodies. Existing shape/activity and shape/locomotion comparisons belong in that argument; obstacle response is an additional target, not the first attempt to connect shape with behaviour.

A relation that transfers to another system would be more interesting still, but it requires a specified correspondence and a new prediction. Rule-transport residue in Flow Lenia is not already a measurement of bioelectric memory in living tissue.

---

This article reports on work from the [Lenia Swarm](/dossiers/lenia-swarm/) dossier (D-003). The numbers above come from the May 19, 2026 common-morphology and localized-loop analysis packet, plus the May 21, 2026 interface/arrangement pilot.
