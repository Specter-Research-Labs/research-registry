#import "../../../addenda/typst-field-manual/specter-paper.typ": author, paper

#paper(
  title: "The Geometry of a Synthetic Morphospace",
  subtitle: "Flow Lenia, common morphology, and localized topology",
  note: "SPECTER LABS FIELD NOTE • B-002",
  authors: (
    author("Ludwig Pouey", affiliation: "Specter Labs"),
  ),
  date: "May 2026",
  keywords: ("morphospace", "Flow Lenia", "EmbryoMaker", "persistent homology", "transport"),
  abstract: [
    We use Flow Lenia as a fully observable synthetic morphospace. The current analysis compares 25,167 Lenia specimens with 859 EmbryoMaker snapshots and 232 Dryad fish outlines in a shared 12-axis morphology layer. Persistent homology finds non-trivial loop structure in all three clouds, while localized transport analysis identifies a fish-near H1 neighborhood with transport enrichment. Dense validation narrows the holonomy claim: the signal is currently cohort-level and neighborhood-level, not a settled universal per-specimen witness.
  ],
)[

= Current Claim

Flow Lenia gives us a controlled genotype-to-phenotype map. The genotype is a concrete rule parameterization; the phenotype is a measured shape and trajectory after simulation. This makes fiber-bundle language operational: fibers are sets of genotypes near the same phenotype, sections are inverse-design rules, and holonomy is a transport test around closed phenotype loops.

The current public article is the canonical version of this note. It replaces the early 96-creature demo and the old single-loop holonomy language with the May 2026 packet:

+ 25,167 Flow Lenia specimens in the shared morphology layer.
+ 8,192 no-food 256x256 2-channel specimens with exact dense TDA.
+ 859 EmbryoMaker legacy snapshots and 232 Dryad fish outlines in the same normalized 12-axis descriptor space.
+ 4,802 flow-supported transport groups.

= Topology

On the full Lenia cohort, exact dense Vietoris-Rips is skipped because the cloud is too large, so the main result uses landmark TDA. At 4,096 landmarks, the Lenia cloud has 4,930 H1 intervals, with top persistence 2.78. The no-food 8,192 cohort is small enough for exact dense TDA and has 7,275 H1 intervals, with top persistence 0.80.

EmbryoMaker and Dryad fish also show non-trivial H1 in the same descriptor layer. EmbryoMaker has 297 exact H1 intervals with top persistence 0.29. Dryad fish has 66 exact H1 intervals with top persistence 0.64. Raw interval counts should not be compared directly across different sample sizes; the point is that the same topology machinery sees loop structure in each cloud, at different scales.

= Transport

The strongest current transport result is local. A fish-near H1 neighborhood, ranked 25th by persistence in the localized scan, has persistence 0.563. In its 256-neighbor patch, the fish distance median is 3.30 against a global fish median of 5.90, while the EmbryoMaker median is 11.98 against a global EmbryoMaker median of 4.46. The same neighborhood has 32 matched transport groups, with observed state-closure effect 4.94e-5 against a global mean of 9.73e-6 and a stratified p-value of about 0.0002.

Holonomy remains the right test, but the claim is narrower than the early draft. Across 4,802 flow-supported transport groups, 109 pass strict positive surplus at three rectangle scales for both state closure and ratio. Under permutation, the both-metric all-scale count is not strong enough by itself, while ratio-only and state-only tails are stronger. Dense validation further narrows the interpretation: the broad top-five rerun leaves one strong survivor, and the fish-near rerun leaves no witness that survives both state and ratio controls.

= Next

The work now splits into two tracks. Creature discovery searches for better Flow Lenia organisms. Morphospace cartography sweeps broad rule families, compares Lenia to EmbryoMaker and fish, computes TDA, and validates lifted loops. They should inform each other without becoming the same task.

]
